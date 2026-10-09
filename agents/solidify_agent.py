"""
脚本固化模块 —— 把桥接验证通过的用例固化为可重复执行的 Playwright 脚本。

核心流程：
  1. 读取 records.jsonl 中 status=pass 的用例
  2. 读取对应 Markdown 用例文件（步骤 + 断言）
  3. 生成 solidify_plan_{模块名}.md（AI 读取后通过 MCP 看页面生成脚本）

使用方式：
  1. python run.py qoder-plan 工业APP        # Phase 1：桥接首跑
  2. python run.py solidify 工业APP           # Phase 2：生成固化计划
  3. 在 Qoder 对话中读取固化计划，生成脚本
  4. python run.py test 工业APP               # Phase 3：零 token 回归
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
    
    扫描 list_runs()，按 run_id 或 records 中的 module 字段匹配。
    返回 run_id 或 None（无记录）。
    """
    runs = list_runs()
    if not runs:
        return None
    
    # 清洗模块名用于匹配（去除数字前缀和特殊字符）
    clean = re.sub(r"^\d+[、_.\-\s]+", "", module_name or "").strip()
    
    for rid in runs:
        # 策略 1：run_id 直接包含模块名
        if clean and clean in rid:
            return rid
        if module_name and module_name in rid:
            return rid
        
        # 策略 2：检查 records 中的 module 字段
        records, _, _ = load_records(rid)
        for rec in records:
            rec_module = rec.get("module", "")
            if clean and (clean in rec_module or rec_module in clean):
                return rid
            if module_name and module_name in rec_module:
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
        
        if case_id in header:
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
        module_name: 业务模块名（如"知识管理"、"工业APP"）
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
    
    # 4. 查找用例源文件
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
