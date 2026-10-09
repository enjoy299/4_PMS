# 测试执行固化设计：桥接首跑 + AI 固化脚本 + 零 token 回归

> 日期：2026-09-30 状态：用户已确认设计方案
> 借鉴 Playwright 官方三 Agent 模型（Planner → Generator → Healer），结合项目现状裁剪为两阶段落地方案

## 1. 背景与目标

### 1.1 问题

当前框架有两条执行线，但缺少"从 AI 探索到可重复脚本"的固化闭环：

- **桥接模式**（`qoder-plan`）：AI 通过 MCP 操控浏览器，灵活但每次消耗 token，不适合高频回归
- **脚本模式**（`test`）：Playwright SDK 直连，零 token 但选择器硬编码、维护成本高

两条线独立运行，桥接模式的执行成果（哪些用例能跑通、实际操作路径是什么）没有被固化为可复用的脚本资产。

### 1.2 目标

实现"首次用 AI 验证 → 固化为脚本 → 后续零 token 回归"的三阶段闭环：

```
Phase 1（桥接首跑）→ Phase 2（AI 固化）→ Phase 3（零 token 回归）
```

### 1.3 设计原则

- **复用现有资产**：`test_actions/` 函数库、`TesterAgent._execute_action()` 映射逻辑、`records.jsonl` 契约
- **不改现有契约**：不修改桥接模式的 `records.jsonl` 格式
- **最小改造量**：新增 `solidify` 命令 + `solidify_agent.py`，`TesterAgent` 仅新增脚本发现逻辑
- **自愈留作后续迭代**：本次不做 Healer，但脚本格式预留自愈扩展点

## 2. 整体架构

### 2.1 三阶段流程

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1：首次验证（消耗 token，只跑一次）                         │
│                                                                 │
│  python run.py qoder-plan 知识管理                               │
│  → 生成 test_plan_知识管理.md                                    │
│  → Qoder 桥接 MCP 操控浏览器逐条执行                              │
│  → records.jsonl（pass/fail/blocked/...）                        │
│  → 作用：验证用例可行性，筛出真实 bug 和不可执行的用例                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 2：固化（消耗少量 token，只跑一次）                          │
│                                                                 │
│  python run.py solidify 知识管理                                  │
│  → 读取 records.jsonl 中 status=pass 的用例                       │
│  → 读取对应 Markdown 用例（步骤 + 断言）                           │
│  → 生成 solidify_plan（提示词 + 用例清单）                         │
│  → Qoder 读取 solidify_plan，通过 MCP 打开浏览器                   │
│     实时查看页面元素，生成 Playwright Python 脚本                   │
│  → 脚本存到 test_scripts/{模块名}_solidified.py                   │
│  → 脚本复用 test_actions/ 已有函数库                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 3：回归执行（零 token，可重复 N 次）                         │
│                                                                 │
│  python run.py test 知识管理                                      │
│  → TesterAgent 优先加载 test_scripts/{模块名}_solidified.py       │
│  → Playwright SDK 直接执行，零 token                               │
│  → 生成报告（Markdown / HTML / Excel）                             │
│  → 若无固化脚本，回退到现有自然语言解析执行（兜底）                    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 与 Playwright 官方三 Agent 模型的对应关系

| Playwright 官方 | 本项目对应 | 说明 |
|----------------|-----------|------|
| Planner（探索 → Markdown 计划） | `qoder-plan`（桥接模式） | 已有，生成测试计划并执行 |
| Generator（计划 → 可执行脚本） | `solidify`（本次新增） | AI 看页面生成 Playwright 脚本 |
| Healer（失败 → 自动修复） | 后续迭代 | 本次不做，但脚本格式预留扩展点 |

## 3. 关键组件

### 3.1 新增命令：`python run.py solidify`

```
用法：
  python run.py solidify 知识管理           # 固化该模块通过的用例为脚本
  python run.py solidify 知识管理 --all     # 包含 fail 的用例（AI 标注为待修复）
  python run.py solidify 知识管理 --p0      # 只固化 P0 级用例
```

命令调度：在 `run.py` 的 `COMMANDS` 字典中注册 `solidify` → `cmd_solidify`。

### 3.2 新增模块：`agents/solidify_agent.py`

职责：

1. **读取执行结果**：加载指定模块最新 run 的 `records.jsonl`，筛选 `status=pass` 的用例
2. **读取用例源文件**：根据 `case_id` 反查 Markdown 用例文件，提取步骤和断言
3. **生成固化计划**：输出 `qoder_workspace/solidify_plan_{模块名}.md`
4. **打印使用指引**：提示用户在 Qoder 对话中读取固化计划并执行

核心函数：

```python
def generate_solidify_plan(module_name: str, level: str = "pass_only") -> Path:
    """
    从已通过的用例生成固化计划。
    
    参数：
        module_name: 业务模块名（如"知识管理"）
        level: 固化范围
            - "pass_only" 只固化 status=pass 的用例（默认）
            - "all" 包含 fail 的用例（AI 会标注为待修复）
            - "p0" 只固化 P0 级且通过的用例
    
    返回：
        固化计划文件路径
    """
```

### 3.3 固化计划文件格式

文件路径：`qoder_workspace/solidify_plan_{模块名}.md`

```markdown
# 脚本固化计划（知识管理）

**生成时间**: 2026-09-30 15:00:00
**目标系统**: <APP_URL>
**来源 run_id**: 知识管理_20260930_140000
**通过用例数**: 15 条
**脚本输出路径**: test_scripts/知识管理_solidified.py

## 执行说明

请按以下计划生成 Playwright Python 脚本。对每条用例：
1. 用 Playwright MCP 打开浏览器并登录系统
2. 导航到对应模块页面
3. 逐步执行操作，记录每步的实际选择器
4. 验证断言是否成立
5. 将整条用例翻译为 Python 函数

## 脚本生成规范

1. **优先复用 test_actions/ 函数库**：
   - 登录用 `ALL_SKILLS["login"](page)`
   - 点击按钮用 `ALL_SKILLS["click_button"](page, "按钮文字")`
   - 填写输入框用 `ALL_SKILLS["fill_input"](page, "标签", "值")`
   - 点击菜单用 `ALL_SKILLS["click_menu"](page, "菜单名")`
   - 如果 test_actions 函数能覆盖操作，不要自己写选择器

2. **test_actions 不够用时才写自定义选择器**：
   - 优先用 `page.get_by_text()` / `page.get_by_role()`
   - 其次用 CSS 选择器
   - 避免用 XPath（除非必要）

3. **每个用例生成一个函数**，签名为：
   ```python
   def TC_子模块_序号(page: Page) -> dict:
       """用例标题"""
       # 步骤...
       # 断言...
       return {"status": "pass"}  # 或 "fail"
   ```

4. **最后生成 CASES 注册表**：
   ```python
   CASES = [
       {"id": "TC-知识管理-分类管理-001", "fn": TC_分类管理_001, "name": "验证新建一级分类"},
       ...
   ]
   ```

5. **脚本头部注释**：包含生成时间、来源 run_id、用例数

## 通过的用例（共 15 条）

### TC-知识管理-分类管理-001 - 验证在文档知识库下新建一级分类功能正常
**操作步骤**:
1. 点击左侧"文档知识库"节点
2. 点击"新建分类"按钮
3. 输入分类名称"测试分类A"
4. 点击保存

**预期结果**:
1. 弹窗关闭
2. 新分类"测试分类A"出现在文档知识库树的一级节点中

### TC-知识管理-分类管理-002 - ...
```

### 3.4 生成的固化脚本格式

文件路径：`test_scripts/{模块名}_solidified.py`

```python
"""
固化脚本：知识管理
生成时间：2026-09-30 15:00:00
来源 run_id：知识管理_20260930_140000
用例数：15 条（全部通过桥接验证）
生成方式：AI 通过 MCP 实时查看页面后生成

注意：本脚本由 AI 自动生成，选择器基于生成时的页面结构。
如果 UI 改版导致脚本失败，请重新运行 python run.py solidify 知识管理
"""
import sys
sys.path.insert(0, '.')
from playwright.sync_api import Page
from test_actions import ALL_SKILLS


def setup(page: Page):
    """登录并导航到知识管理页面"""
    ALL_SKILLS["login"](page)
    ALL_SKILLS["click_menu"](page, "知识管理")
    page.wait_for_timeout(2000)


def TC_分类管理_001(page: Page) -> dict:
    """验证在文档知识库下新建一级分类功能正常"""
    try:
        # 步骤 1：点击左侧"文档知识库"节点
        ALL_SKILLS["click_menu"](page, "文档知识库")
        page.wait_for_timeout(1000)
        
        # 步骤 2：点击"新建分类"按钮
        ALL_SKILLS["click_new_category"](page)
        page.wait_for_timeout(1000)
        
        # 步骤 3：输入分类名称
        ALL_SKILLS["fill_input"](page, "分类名称", "QAuto-TC001")
        
        # 步骤 4：点击保存
        ALL_SKILLS["click_button"](page, "保存")
        page.wait_for_timeout(2000)
        
        # 断言 1：弹窗关闭（通过检查弹窗是否不可见）
        dialog = page.locator('.el-dialog:visible')
        assert dialog.count() == 0, "弹窗未关闭"
        
        # 断言 2：新分类出现在树中
        tree_text = page.locator('.el-tree').text_content() or ""
        assert "QAuto-TC001" in tree_text, "新分类未出现在树中"
        
        return {"status": "pass"}
    except AssertionError as e:
        return {"status": "fail", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ... 更多用例函数 ...


# 用例注册表
CASES = [
    {
        "id": "TC-知识管理-分类管理-001",
        "fn": TC_分类管理_001,
        "name": "验证在文档知识库下新建一级分类功能正常",
        "priority": "P0",
        "module": "分类管理",
    },
    # ...
]
```

### 3.5 `TesterAgent` 改造：支持加载固化脚本

在 `TesterAgent.run_suite()` 和 `run_all_suites()` 中新增脚本发现逻辑：

```python
def _try_load_solidified_script(self, module_name: str) -> list | None:
    """尝试加载固化脚本。
    
    查找 test_scripts/{模块名}_solidified.py，存在则动态导入并返回 CASES 列表。
    不存在则返回 None（调用方回退到现有自然语言解析执行）。
    """
    script_path = TEST_SCRIPTS_DIR / f"{module_name}_solidified.py"
    if not script_path.exists():
        return None
    
    # 动态导入
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"solidified_{module_name}", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    return module.CASES
```

执行逻辑变更：

```python
# 在 run_suite() / _execute_suite_with_page() 中：
solidified = self._try_load_solidified_script(module_name)
if solidified:
    logger.info(f"加载固化脚本：{len(solidified)} 条用例（零 token 模式）")
    results = self._run_solidified_cases(page, solidified, module_name)
else:
    logger.info("无固化脚本，使用自然语言解析模式")
    # 现有逻辑不变
```

### 3.6 固化脚本执行器

新增 `_run_solidified_cases()` 方法：

```python
def _run_solidified_cases(self, page, cases: list, module_name: str) -> list:
    """执行固化脚本中的用例。
    
    每个用例调用其 fn(page) 函数，捕获返回值作为结果。
    复用现有的报告生成逻辑。
    """
    results = []
    
    # 执行 setup（登录 + 导航）
    # 注意：setup 函数由固化脚本定义，因为不同模块的导航路径不同
    # 如果没有 setup，使用现有的 _navigate_to_module_menu
    
    for case_info in cases:
        case_id = case_info["id"]
        case_fn = case_info["fn"]
        
        start_time = datetime.now()
        try:
            result = case_fn(page)
            status = result.get("status", "error")
            error = result.get("error", "")
        except Exception as e:
            status = "error"
            error = str(e)[:300]
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        results.append({
            "id": case_id,
            "name": case_info.get("name", ""),
            "priority": case_info.get("priority", "P1"),
            "module": case_info.get("module", module_name),
            "status": status,
            "duration": elapsed,
            "error": error,
            "assertions": [],  # 固化脚本内部处理断言
            "output": f"固化脚本执行：{status}",
        })
    
    return results
```

## 4. 数据流与文件约定

### 4.1 文件路径

```
output/06_reports/triage/{run_id}/records.jsonl
  ↑ Phase 1 产物，Phase 2 的输入

qoder_workspace/solidify_plan_{模块名}.md
  ↑ Phase 2 的固化计划（AI 读取后生成脚本）

test_scripts/{模块名}_solidified.py
  ↑ Phase 2 的输出，Phase 3 的输入
```

### 4.2 命名约定

| 产物 | 命名规则 | 示例 |
|------|---------|------|
| 固化计划 | `solidify_plan_{模块名}.md` | `solidify_plan_知识管理.md` |
| 固化脚本 | `{模块名}_solidified.py` | `知识管理_solidified.py` |

### 4.3 状态映射

桥接执行结果 → 固化范围：

| records.jsonl status | 默认（pass_only） | --all 模式 |
|---------------------|------------------|-----------|
| pass | 纳入固化 | 纳入固化 |
| fail | 跳过 | 纳入（AI 标注为待修复） |
| blocked / skipped / error | 跳过 | 跳过 |
| manual | 跳过 | 跳过 |

## 5. 明确排除项

| 排除项 | 理由 | 后续迭代建议 |
|--------|------|------------|
| 自愈（Healer） | 本次先跑通主流程，自愈是独立能力 | Phase 2 迭代：脚本失败时 AI 分析失败原因并更新选择器 |
| 修改桥接契约 | 不改 `records.jsonl` 格式，保持向后兼容 | 如需更丰富的 Trace，后续可扩展 |
| 修改现有 `test` 命令核心逻辑 | 只新增"优先加载固化脚本"的发现逻辑 | 现有自然语言解析模式作为兜底保留 |
| CI/CD 集成 | 固化脚本生成依赖 AI，不适合无人值守 | 固化后的脚本本身可接入 CI |

## 6. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| AI 生成的选择器不稳定 | 回归时脚本失败 | 固化计划中明确要求优先用 test_actions 函数；失败后重新 solidify |
| 固化脚本与页面版本绑定 | UI 改版后脚本全挂 | 脚本头部注释标注生成时间；UI 改版后重新 solidify |
| 固化脚本的断言不如代码精确 | 漏检真实 bug | 固化计划中要求使用 assert + 明确错误信息；后续引入 Healer |
| records.jsonl 中 pass 但实际未执行到位 | 固化了错误的操作路径 | 依赖桥接阶段的 records 质量（已有 triage 机制保障） |

## 7. 成功标准

1. 能对任意模块执行 `python run.py solidify {模块名}`，生成固化计划
2. AI 读取固化计划后，能生成可执行的 Playwright 脚本
3. 固化脚本能通过 `python run.py test {模块名}` 执行，且结果与桥接执行一致
4. 回归执行时 token 消耗为零（纯 Playwright SDK 执行）
