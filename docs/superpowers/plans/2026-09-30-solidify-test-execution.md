# 测试执行固化（Solidify）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现"桥接首跑 → AI 固化脚本 → 零 token 回归"三阶段闭环，新增 `solidify` 命令将已通过桥接验证的用例固化为 Playwright Python 脚本。

**Architecture:** 新增 `agents/solidify_agent.py` 负责读取 `records.jsonl` 中通过的用例并生成固化计划 Markdown；`run.py` 新增 `solidify` 命令入口；`agents/tester_agent.py` 新增脚本发现逻辑，优先加载固化脚本执行，无固化脚本时回退到现有自然语言解析模式。

**Tech Stack:** Python 3.10+, Playwright sync API, pytest, pathlib, importlib

**Spec:** `docs/superpowers/specs/2026-09-30-solidify-test-execution-design.md`

---

## File Structure

| 操作 | 文件路径 | 职责 |
|------|---------|------|
| Create | `agents/solidify_agent.py` | 固化计划生成器：读取 records → 筛选通过的用例 → 生成 solidify_plan.md |
| Modify | `run.py` | 新增 `solidify` 命令入口 + `cmd_solidify()` 函数 |
| Modify | `agents/tester_agent.py` | 新增 `_try_load_solidified_script()` 和 `_run_solidified_cases()` 方法 |
| Create | `tests/test_solidify.py` | 固化功能单元测试 |

---

### Task 1: 创建 `agents/solidify_agent.py` 核心函数

**Files:**
- Create: `agents/solidify_agent.py`

- [ ] **Step 1: 创建 solidify_agent.py 骨架**

```python
"""
脚本固化模块 —— 把桥接验证通过的用例固化为可重复执行的 Playwright 脚本。

核心流程：
  1. 读取 records.jsonl 中 status=pass 的用例
  2. 读取对应 Markdown 用例文件（步骤 + 断言）
  3. 生成 solidify_plan_{模块名}.md（AI 读取后通过 MCP 看页面生成脚本）

使用方式：
  1. python run.py qoder-plan 知识管理     # Phase 1：桥接首跑
  2. python run.py solidify 知识管理        # Phase 2：生成固化计划
  3. 在 Qoder 对话中读取固化计划，生成脚本
  4. python run.py test 知识管理            # Phase 3：零 token 回归
"""
import re
import json
from pathlib import Path
from datetime import datetime

from core.config import (
    ROOT, DESIGN_WORKSPACE_DIR, CASES_DIR, APP_URL,
    TEST_SCRIPTS_DIR,
)
from core.triage import list_runs, load_records
from utils.logger import get_logger

logger = get_logger("solidify")

# Qoder 工作区（与 qoder_bridge.py 共用）
QODER_WORKSPACE = ROOT / "qoder_workspace"
QODER_WORKSPACE.mkdir(parents=True, exist_ok=True)


def _find_latest_run_for_module(module_name: str) -> str | None:
    """找到指定模块最新一次的 run_id。
    
    扫描 list_runs()，按 run_id 前缀匹配模块名。
    返回 run_id 或 None（无记录）。
    """
    runs = list_runs()
    if not runs:
        return None
    
    # 清洗模块名用于匹配（去除数字前缀和特殊字符）
    clean = re.sub(r'[^\w\u4e00-\u9fff]', "", module_name or "")
    
    for rid in runs:
        # run_id 格式：{模块名}_{时间戳}，直接检查是否包含模块名
        if clean and clean in rid:
            return rid
        # 也尝试原始模块名
        if module_name and module_name in rid:
            return rid
    
    return None


def _load_passed_cases(records: list) -> list:
    """从 records 中筛选 status=pass 的用例。
    
    返回通过的记录列表（每条包含 case_id, name, module, steps, assertions）。
    """
    passed = []
    for rec in records:
        if rec.get("status") == "pass":
            passed.append({
                "case_id": rec.get("case_id", "?"),
                "name": rec.get("name", ""),
                "module": rec.get("module", ""),
                "priority": rec.get("priority", ""),
                "steps": rec.get("steps", []),
                "assertions": rec.get("assertions", []),
                "precondition": rec.get("precondition", ""),
                "test_data": rec.get("test_data", ""),
            })
    return passed


def _find_case_source_file(case_id: str, module_name: str) -> Path | None:
    """根据 case_id 和模块名查找对应的 Markdown 用例文件。
    
    搜索顺序：
    1. CASES_DIR/{module_name}/ 下的 *-用例*.md
    2. DESIGN_WORKSPACE_DIR 下的 *-用例*.md
    """
    # 清洗模块名
    clean_module = re.sub(r"^\d+[、_.\-\s]+", "", module_name).strip()
    
    # 策略 1：模块子目录
    module_dir = CASES_DIR / clean_module
    if module_dir.exists():
        candidates = list(module_dir.rglob("*-用例*.md"))
        if candidates:
            # 取最新的
            return max(candidates, key=lambda p: p.stat().st_mtime)
    
    # 策略 2：全局搜索
    all_files = list(CASES_DIR.rglob("*-用例*.md"))
    all_files += list(DESIGN_WORKSPACE_DIR.rglob("*-用例*.md"))
    
    # 按模块名过滤
    for f in sorted(all_files, key=lambda p: p.stat().st_mtime, reverse=True):
        if clean_module in f.stem or clean_module in f.parent.name:
            return f
    
    return None


def _extract_case_from_markdown(md_file: Path, case_id: str) -> dict | None:
    """从 Markdown 用例文件中提取指定 case_id 的步骤和断言。
    
    支持竖排表格格式（每个用例一个 ### 标题 + 小表格）。
    返回 {"steps": "1. xxx\n2. yyy", "assertions": "1. xxx\n2. yyy"} 或 None。
    """
    if not md_file or not md_file.exists():
        return None
    
    content = md_file.read_text(encoding="utf-8")
    
    # 按 ### TC- 分割用例块
    blocks = re.split(r'###\s+(TC-[^\n]+)', content)
    
    for i in range(1, len(blocks), 2):
        header = blocks[i].strip()
        block_content = blocks[i + 1] if i + 1 < len(blocks) else ""
        
        # 匹配 case_id（支持部分匹配，如 TC-知识管理-分类管理-001 匹配 TC-知识管理-分类管理-001）
        if case_id in header:
            # 提取步骤和断言
            steps = ""
            assertions = ""
            
            for line in block_content.split("\n"):
                line = line.strip()
                if not line.startswith("|"):
                    continue
                parts = [p.strip() for p in line.strip("|").split("|")]
                if len(parts) < 2:
                    continue
                key = parts[0].strip().replace(" ", "")
                value = parts[1].strip()
                
                if key in ("测试步骤", "操作步骤"):
                    steps = value
                elif key in ("预期结果",):
                    assertions = value
            
            return {"steps": steps, "assertions": assertions}
    
    return None


def generate_solidify_plan(module_name: str, level: str = "pass_only") -> Path | None:
    """
    从已通过的用例生成固化计划。
    
    参数：
        module_name: 业务模块名（如"知识管理"）
        level: 固化范围
            - "pass_only" 只固化 status=pass 的用例（默认）
            - "all" 包含 fail 的用例（AI 会标注为待修复）
            - "p0" 只固化 P0 级且通过的用例
    
    返回：
        固化计划文件路径；无可用数据时返回 None
    """
    # 1. 找到该模块最新的 run
    run_id = _find_latest_run_for_module(module_name)
    if not run_id:
        logger.error(f"未找到模块 '{module_name}' 的执行记录。请先运行：python run.py qoder-plan {module_name}")
        return None
    
    logger.info(f"使用 run_id: {run_id}")
    
    # 2. 加载记录
    records, dups, malformed = load_records(run_id)
    if not records:
        logger.error(f"run {run_id} 中无有效记录")
        return None
    
    logger.info(f"总记录 {len(records)} 条（重复 {dups}，损坏 {malformed}）")
    
    # 3. 筛选用例
    if level == "pass_only":
        cases = _load_passed_cases(records)
    elif level == "p0":
        cases = [c for c in _load_passed_cases(records) if c.get("priority", "").upper() == "P0"]
    elif level == "all":
        # 包含 fail 的用例
        cases = []
        for rec in records:
            if rec.get("status") in ("pass", "fail"):
                cases.append({
                    "case_id": rec.get("case_id", "?"),
                    "name": rec.get("name", ""),
                    "module": rec.get("module", ""),
                    "priority": rec.get("priority", ""),
                    "status": rec.get("status", ""),
                    "steps": rec.get("steps", []),
                    "assertions": rec.get("assertions", []),
                    "precondition": rec.get("precondition", ""),
                    "test_data": rec.get("test_data", ""),
                })
    else:
        logger.error(f"未知 level: {level}")
        return None
    
    if not cases:
        logger.warning(f"无符合条件的用例（level={level}）")
        return None
    
    logger.info(f"筛选出 {len(cases)} 条用例待固化")
    
    # 4. 查找用例源文件（用于补充步骤和断言的原始文本）
    source_file = _find_case_source_file(cases[0]["case_id"], module_name)
    if source_file:
        logger.info(f"用例源文件：{source_file}")
    
    # 5. 生成固化计划 Markdown
    plan_lines = [
        f"# 脚本固化计划（{module_name}）",
        f"",
        f"**生成时间**: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"**目标系统**: {APP_URL}",
        f"**来源 run_id**: {run_id}",
        f"**用例数**: {len(cases)} 条",
        f"**脚本输出路径**: {TEST_SCRIPTS_DIR / f'{module_name}_solidified.py'}",
        f"",
        f"## 执行说明",
        f"",
        f"请按以下计划生成 Playwright Python 脚本。对每条用例：",
        f"1. 用 Playwright MCP 打开浏览器并登录系统",
        f"2. 导航到对应模块页面",
        f"3. 逐步执行操作，记录每步的实际选择器",
        f"4. 验证断言是否成立",
        f"5. 将整条用例翻译为 Python 函数",
        f"",
        f"## 脚本生成规范",
        f"",
        f"1. **优先复用 test_actions/ 函数库**：",
        f"   - 登录用 `ALL_SKILLS[\"login\"](page)`",
        f"   - 点击按钮用 `ALL_SKILLS[\"click_button\"](page, \"按钮文字\")`",
        f"   - 填写输入框用 `ALL_SKILLS[\"fill_input\"](page, \"标签\", \"值\")`",
        f"   - 点击菜单用 `ALL_SKILLS[\"click_menu\"](page, \"菜单名\")`",
        f"   - 如果 test_actions 函数能覆盖操作，不要自己写选择器",
        f"",
        f"2. **test_actions 不够用时才写自定义选择器**：",
        f"   - 优先用 `page.get_by_text()` / `page.get_by_role()`",
        f"   - 其次用 CSS 选择器",
        f"   - 避免用 XPath（除非必要）",
        f"",
        f"3. **每个用例生成一个函数**，签名为：",
        f"   ```python",
        f"   def TC_子模块_序号(page: Page) -> dict:",
        f"       \"\"\"用例标题\"\"\"",
        f"       # 步骤...",
        f"       # 断言...",
        f"       return {{\"status\": \"pass\"}}  # 或 \"fail\"",
        f"   ```",
        f"",
        f"4. **最后生成 CASES 注册表**：",
        f"   ```python",
        f"   CASES = [",
        f"       {{\"id\": \"TC-xxx-001\", \"fn\": TC_xxx_001, \"name\": \"用例标题\",",
        f"        \"priority\": \"P0\", \"module\": \"子模块名\"}},",
        f"       # ...",
        f"   ]",
        f"   ```",
        f"",
        f"5. **脚本头部注释**：包含生成时间、来源 run_id、用例数",
        f"",
    ]
    
    # 按状态分组
    passed_cases = [c for c in cases if c.get("status") != "fail"]
    failed_cases = [c for c in cases if c.get("status") == "fail"]
    
    if passed_cases:
        plan_lines.append(f"## 通过的用例（共 {len(passed_cases)} 条）")
        plan_lines.append("")
        
        for case in passed_cases:
            case_id = case["case_id"]
            case_name = case["name"]
            priority = case.get("priority", "P1")
            
            plan_lines.append(f"### {case_id} - {case_name} (优先级: {priority})")
            plan_lines.append("")
            
            # 尝试从源文件补充步骤
            source_data = _extract_case_from_markdown(source_file, case_id) if source_file else None
            
            # 步骤
            if source_data and source_data.get("steps"):
                plan_lines.append(f"**操作步骤**:")
                plan_lines.append(source_data["steps"])
            elif case.get("steps"):
                plan_lines.append(f"**操作步骤**:")
                for s in case["steps"]:
                    order = s.get("order", "")
                    action = s.get("action", "")
                    plan_lines.append(f"{order}. {action}")
            plan_lines.append("")
            
            # 断言
            if source_data and source_data.get("assertions"):
                plan_lines.append(f"**预期结果**:")
                plan_lines.append(source_data["assertions"])
            elif case.get("assertions"):
                plan_lines.append(f"**预期结果**:")
                for a in case["assertions"]:
                    text = a.get("text", "") if isinstance(a, dict) else str(a)
                    plan_lines.append(f"- {text}")
            plan_lines.append("")
    
    if failed_cases:
        plan_lines.append(f"## 失败的用例（共 {len(failed_cases)} 条，AI 标注为待修复）")
        plan_lines.append("")
        
        for case in failed_cases:
            case_id = case["case_id"]
            case_name = case["name"]
            
            plan_lines.append(f"### {case_id} - {case_name} (状态: fail)")
            plan_lines.append("")
            plan_lines.append(f"> **注意**：此用例在桥接执行中失败，请检查原因并尝试修复。")
            plan_lines.append("")
    
    # 写入文件
    plan_filename = f"solidify_plan_{module_name}.md"
    plan_path = QODER_WORKSPACE / plan_filename
    plan_path.write_text("\n".join(plan_lines), encoding="utf-8")
    
    logger.info(f"固化计划已生成：{plan_path}")
    logger.info(f"包含 {len(cases)} 条用例")
    
    # 打印使用指引
    print(f"\n{'=' * 60}")
    print(f"  固化计划已生成！")
    print(f"  文件：{plan_path}")
    print(f"  用例数：{len(cases)}")
    print(f"{'=' * 60}")
    print(f"\n  下一步：在 Qoder 对话中输入：")
    print(f"  \"请读取 {plan_path.resolve()} 并按规范生成 Playwright 脚本\"")
    print(f"")
    print(f"  脚本生成后，运行回归测试：")
    print(f"  python run.py test {module_name}")
    print(f"")
    
    return plan_path
```

- [ ] **Step 2: 验证文件创建成功**

Run: `python -c "from agents.solidify_agent import generate_solidify_plan; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agents/solidify_agent.py
git commit -m "feat: add solidify_agent module for test script solidification"
```

---

### Task 2: 在 `run.py` 中注册 `solidify` 命令

**Files:**
- Modify: `run.py`

- [ ] **Step 1: 在 run.py 顶部导入区添加导入**

在 `run.py` 的 `from agents.qoder_bridge import generate_test_plan` 附近（约第 97 行），确认后续 `cmd_solidify` 中会导入 `generate_solidify_plan`（延迟导入，无需在顶部添加）。

- [ ] **Step 2: 在 run.py 中添加 `cmd_solidify` 函数**

在 `cmd_qoder_plan()` 函数后面（约第 260 行后）添加：

```python
def cmd_solidify():
    """把桥接验证通过的用例固化为 Playwright 脚本（Phase 2）。

    用法：
        python run.py solidify 模块名 [--all|--p0]
          --all  包含 fail 的用例（AI 标注为待修复）
          --p0   只固化 P0 级且通过的用例
          不加参数  只固化 status=pass 的用例（默认）
    """
    console.print("\n[bold green]>>> 生成脚本固化计划[/bold green]\n")

    args = [a for a in sys.argv[2:] if not a.startswith("-")]
    flags = {a.lower() for a in sys.argv[2:] if a.startswith("-")}
    module_name = args[0] if args else None

    if not module_name:
        console.print("[red]错误：请指定模块名，如：python run.py solidify 知识管理[/red]")
        sys.exit(1)

    # 确定固化范围
    if "--all" in flags:
        level = "all"
    elif "--p0" in flags:
        level = "p0"
    else:
        level = "pass_only"

    level_label = {"pass_only": "仅通过项", "all": "全部（含失败）", "p0": "P0 且通过"}[level]
    console.print(f"[dim]固化范围：{level_label}｜模块：{module_name}[/dim]\n")

    from agents.solidify_agent import generate_solidify_plan
    result = generate_solidify_plan(module_name, level=level)

    if not result:
        console.print("[red]固化计划生成失败，请检查上方日志[/red]")
        sys.exit(1)
```

- [ ] **Step 3: 在 COMMANDS 字典中注册 solidify 命令**

在 `run.py` 的 `COMMANDS` 字典中（约第 454 行），在 `"qoder-plan"` 行后面添加：

```python
    "solidify":      (cmd_solidify,      "固化通过的用例为 Playwright 脚本"),
```

- [ ] **Step 4: 在 cmd_help 的帮助表格中添加 solidify 行**

在 `cmd_help()` 函数的表格中（约第 396 行 `"qoder-plan"` 行后），添加：

```python
    table.add_row("solidify", "固化通过的用例为 Playwright 脚本 [--all|--p0]", "推荐·固化")
```

- [ ] **Step 5: 验证命令注册成功**

Run: `python run.py help`
Expected: 帮助表格中出现 `solidify` 行

- [ ] **Step 6: Commit**

```bash
git add run.py
git commit -m "feat: register solidify command in run.py"
```

---

### Task 3: 修改 `TesterAgent` 支持加载固化脚本

**Files:**
- Modify: `agents/tester_agent.py`

- [ ] **Step 1: 在 TesterAgent 类中添加 `_try_load_solidified_script` 方法**

在 `TesterAgent` 类中（`_env_cleanup` 方法后面，约第 92 行后）添加：

```python
    def _try_load_solidified_script(self, module_name: str) -> list | None:
        """尝试加载固化脚本。
        
        查找 test_scripts/{模块名}_solidified.py，存在则动态导入并返回 CASES 列表。
        不存在则返回 None（调用方回退到现有自然语言解析执行）。
        """
        # 清洗模块名
        clean_name = re.sub(r"^\d+[、_.\-\s]+", "", module_name).strip()
        script_path = TEST_SCRIPTS_DIR / f"{clean_name}_solidified.py"
        
        if not script_path.exists():
            logger.debug(f"无固化脚本：{script_path}")
            return None
        
        logger.info(f"发现固化脚本：{script_path}")
        
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                f"solidified_{clean_name}", script_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            cases = getattr(module, "CASES", None)
            if not cases:
                logger.warning(f"固化脚本无 CASES 注册表：{script_path}")
                return None
            
            logger.info(f"加载固化脚本成功：{len(cases)} 条用例")
            return cases
        except Exception as e:
            logger.error(f"加载固化脚本失败：{e}")
            return None
```

- [ ] **Step 2: 在 TesterAgent 类中添加 `_run_solidified_cases` 方法**

紧接 `_try_load_solidified_script` 方法后面添加：

```python
    def _run_solidified_cases(self, page, cases: list, module_name: str) -> list:
        """执行固化脚本中的用例。
        
        每个用例调用其 fn(page) 函数，捕获返回值作为结果。
        """
        results = []
        clean_name = re.sub(r"^\d+[、_.\-\s]+", "", module_name).strip()
        
        for case_info in cases:
            case_id = case_info.get("id", "TC-???")
            case_fn = case_info.get("fn")
            case_name = case_info.get("name", "")
            priority = case_info.get("priority", "P1")
            module = case_info.get("module", clean_name)
            
            if not case_fn:
                logger.warning(f"用例 {case_id} 无 fn 函数，跳过")
                continue
            
            reset_run(clean_name, case_id)
            start_time = datetime.now()
            
            try:
                result = case_fn(page)
                status = result.get("status", "error") if isinstance(result, dict) else "error"
                error = result.get("error", "") if isinstance(result, dict) else ""
            except Exception as e:
                status = "error"
                error = str(e)[:300]
                logger.error(f"  用例 {case_id} 执行出错：{e}")
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            results.append({
                "id": case_id,
                "name": case_name,
                "priority": priority,
                "module": module,
                "status": status,
                "duration": elapsed,
                "error": error,
                "assertions": [],
                "output": f"固化脚本执行：{status}",
            })
            
            logger.info(f"  {case_id} => {status.upper()} ({elapsed:.1f}秒)")
        
        return results
```

- [ ] **Step 3: 修改 `_execute_suite_with_page` 方法，优先使用固化脚本**

在 `_execute_suite_with_page` 方法中（约第 985 行），在 `cases = self.parse_markdown_cases(md_file)` 后面、`module_name = ...` 后面添加固化脚本检测逻辑：

找到这段代码（约第 985-991 行）：
```python
        cases = self.parse_markdown_cases(md_file)
        if not cases:
            logger.error(f"未解析到用例：{md_file}")
            return None

        module_name = md_file.stem.replace("-用例", "").split("-", 1)[-1] if "-" in md_file.stem else md_file.stem
        logger.info(f"执行：{module_name} - {len(cases)} 个用例")
```

替换为：
```python
        module_name = md_file.stem.replace("-用例", "").split("-", 1)[-1] if "-" in md_file.stem else md_file.stem
        
        # 优先尝试加载固化脚本
        solidified = self._try_load_solidified_script(module_name)
        if solidified:
            logger.info(f"执行（固化脚本）：{module_name} - {len(solidified)} 条用例")
            results = []
            try:
                logger.info(f"导航到模块：{module_name}")
                nav_result = self._navigate_to_module_menu(page, module_name)
                page.wait_for_timeout(2000)
                
                results = self._run_solidified_cases(page, solidified, module_name)
            except Exception as e:
                logger.error(f"固化脚本执行出错：{e}")
            
            if results:
                report = self.reporter.build_and_save(module_name, results)
                return report
            return None
        
        # 无固化脚本，回退到自然语言解析模式
        cases = self.parse_markdown_cases(md_file)
        if not cases:
            logger.error(f"未解析到用例：{md_file}")
            return None

        logger.info(f"执行：{module_name} - {len(cases)} 个用例")
```

- [ ] **Step 4: 验证修改后语法正确**

Run: `python -c "from agents.tester_agent import TesterAgent; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add agents/tester_agent.py
git commit -m "feat: add solidified script loading in TesterAgent"
```

---

### Task 4: 编写单元测试

**Files:**
- Create: `tests/test_solidify.py`

- [ ] **Step 1: 编写测试**

```python
"""固化功能单元测试。"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agents.solidify_agent import (
    _find_latest_run_for_module,
    _load_passed_cases,
    _extract_case_from_markdown,
)


class TestLoadPassedCases:
    """测试 _load_passed_cases 函数。"""

    def test_filters_pass_only(self):
        records = [
            {"case_id": "TC-001", "status": "pass", "name": "用例1"},
            {"case_id": "TC-002", "status": "fail", "name": "用例2"},
            {"case_id": "TC-003", "status": "pass", "name": "用例3"},
        ]
        result = _load_passed_cases(records)
        assert len(result) == 2
        assert result[0]["case_id"] == "TC-001"
        assert result[1]["case_id"] == "TC-003"

    def test_empty_records(self):
        assert _load_passed_cases([]) == []

    def test_no_pass_records(self):
        records = [
            {"case_id": "TC-001", "status": "fail"},
            {"case_id": "TC-002", "status": "blocked"},
        ]
        assert _load_passed_cases(records) == []


class TestFindLatestRun:
    """测试 _find_latest_run_for_module 函数。"""

    @patch("agents.solidify_agent.list_runs")
    def test_finds_matching_run(self, mock_list_runs):
        mock_list_runs.return_value = [
            "知识管理_20260930_140000",
            "项目管理_20260929_100000",
        ]
        result = _find_latest_run_for_module("知识管理")
        assert result == "知识管理_20260930_140000"

    @patch("agents.solidify_agent.list_runs")
    def test_returns_none_when_no_match(self, mock_list_runs):
        mock_list_runs.return_value = ["项目管理_20260929_100000"]
        result = _find_latest_run_for_module("知识管理")
        assert result is None

    @patch("agents.solidify_agent.list_runs")
    def test_returns_none_when_empty(self, mock_list_runs):
        mock_list_runs.return_value = []
        result = _find_latest_run_for_module("知识管理")
        assert result is None


class TestExtractCaseFromMarkdown:
    """测试 _extract_case_from_markdown 函数。"""

    def test_extracts_steps_and_assertions(self, tmp_path):
        md_content = """# 测试用例

### TC-知识管理-分类管理-001 验证新建分类

| 字段 | 值 |
|------|-----|
| 用例ID | TC-知识管理-分类管理-001 |
| 模块 | 分类管理 |
| 测试步骤 | 1. 点击文档知识库 2. 点击新建分类 3. 输入名称 4. 保存 |
| 预期结果 | 1. 弹窗关闭 2. 新分类出现在树中 |
"""
        md_file = tmp_path / "test.md"
        md_file.write_text(md_content, encoding="utf-8")
        
        result = _extract_case_from_markdown(md_file, "TC-知识管理-分类管理-001")
        assert result is not None
        assert "点击文档知识库" in result["steps"]
        assert "弹窗关闭" in result["assertions"]

    def test_returns_none_for_missing_case(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# empty", encoding="utf-8")
        
        result = _extract_case_from_markdown(md_file, "TC-NOT-EXIST")
        assert result is None

    def test_returns_none_for_missing_file(self):
        result = _extract_case_from_markdown(Path("/nonexistent.md"), "TC-001")
        assert result is None
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_solidify.py -v`
Expected: 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_solidify.py
git commit -m "test: add unit tests for solidify_agent"
```

---

### Task 5: 端到端验证（手动）

**Files:** 无新增文件

- [ ] **Step 1: 确认现有桥接执行记录**

确保 `output/06_reports/triage/` 下有至少一个 run 的 `records.jsonl`。

Run: `python run.py triage --list`
Expected: 列出可用的 run_id

- [ ] **Step 2: 生成固化计划**

Run: `python run.py solidify 知识管理`（替换为实际有记录的模块名）
Expected: 生成 `qoder_workspace/solidify_plan_知识管理.md`

- [ ] **Step 3: 检查固化计划内容**

打开生成的 `solidify_plan_*.md`，确认：
- 头部包含生成时间、run_id、用例数
- 包含通过的用例列表（步骤 + 断言）
- 包含脚本生成规范说明

- [ ] **Step 4: 最终 Commit**

```bash
git add -A
git commit -m "feat: complete solidify feature - bridge first run, AI solidify, zero-token regression"
```

---

## 完成标准

1. `python run.py solidify 模块名` 能成功生成固化计划
2. 固化计划包含通过的用例清单和脚本生成规范
3. `python run.py test 模块名` 能自动发现并加载固化脚本
4. 无固化脚本时回退到现有自然语言解析模式
5. 单元测试全部通过
