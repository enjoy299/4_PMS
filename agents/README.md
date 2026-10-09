# agents/ — AI 智能体

这个文件夹包含测试流水线中所有 AI 智能体的代码和提示词模板。每个智能体负责一个环节，像一个虚拟测试团队成员。

> 交互模型：AI 分析不再直连远程模型，而是由 **Qoder 对话**完成。智能体把组装好的提示词保存到 `ai_workspace/`（并复制到剪贴板），用户在 Qoder 里得到回复后粘贴回终端或存为 `_response.md`，智能体再解析结果（响应一经消费自动归档为 `*_response_consumed_*.md`，同一任务重跑不会串轮读到旧回复）。浏览器执行则通过 `test_actions/` 的 Playwright 纯脚本完成，无需 AI 控制浏览器。

## 流水线智能体（按 7 阶段顺序，对应 output/00~06）

| 阶段 | 文件 | 智能体 | 职责 | 输出 |
|:----:|------|--------|------|------|
| 0 | （由 explore-web-system skill / `explorer_agent.py` 承担） | 探索智能体 | 真实操作页面，记录页面事实、功能地图 | `output/00_explore/` |
| 1 | `business_agent.py` | 业务梳理智能体 | 交叉比对「探索产物 + 原始需求」，输出业务全景图（角色/权限/实体/数据流/依赖/流程/术语/需求缺口，含稳定 ID） | `output/01_business/{模块}-业务全景图.md` |
| 2 | `analyst_agent.py` | 分析智能体 | 读取需求文档 + 原型截图，按业务领域拆分模块化需求、提取测试点 | `output/02_split_requirements/`、`output/03_design/test_points/` |
| 3 | `understanding_agent.py` | 需求理解智能体 | 基于拆分需求生成需求理解文档，供用户确认 | `output/03_design/test_points/{模块}-需求理解.md` |
| 3 | `designer_agent.py` | 设计智能体 | 把测试点/需求转化为可执行测试用例（操作步骤 + 预期结果） | `output/03_design/` 用例文件 |
| 4 | `reviewer_agent.py` | 审核智能体 | 检查用例质量：覆盖度、可执行性、断言质量、优先级 | `output/04_review/*_review_*.md` |
| 5 | `excel_export_agent.py` | Excel 导出智能体 | 按评审结果过滤，将测试点 + 用例合并导出为双 Sheet Excel | `output/05_export/` |
| 6 | `tester_agent.py` | 测试执行智能体 | 生成并执行 Playwright 脚本，逐条跑用例、记录通过/失败 | `output/06_reports/` |
| 辅助 | `explorer_agent.py` | 探索智能体 | 用 Playwright 遍历系统所有页面，检查 404/500、空白页、控制台报错 | `output/06_reports/` 探索报告 |

## 支撑模块

| 文件 | 用途 |
|------|------|
| `__init__.py` | 包初始化文件，标记 agents 为 Python 包 |
| `base_agent.py` | 基础智能体父类。提供 `invoke_text()`（发文字提示词给 Qoder）、`invoke_with_images()`（发文字+图片），内部调用 `core.brain` 的 `save_prompt`/`read_response` |
| `agent_loader.py` | 提示词加载器。从 `*_prompt.md` 加载模板，支持 `{变量}` 替换（如 `{app_url}`、`{module}`），带缓存；缺参保留占位符原文并 WARNING 点名（fail-loud），字面花括号用 `{{ }}` 转义 |
| `upstream_context.py` | 上游业务基线注入器。为 analyze/understand/design 三个智能体的提示词拼接「系统级 + 模块级」探索/业务全景图引用，打通 00_explore、01_business 到下游的数据链 |
| `qoder_bridge.py` | Qoder 桥接模块。解析用例生成结构化测试计划/探索计划，供 Qoder IDE 内置 Playwright MCP 读取并操控浏览器执行（`run.py qoder-plan` / `qoder-explore`） |

## 提示词模板（`*_prompt.md`，由 `agent_loader` 加载）

| 文件 | 对应智能体 |
|------|-----------|
| `business_prompt.md` | 业务梳理智能体 |
| `analyst_prompt.md` | 分析智能体 |
| `understanding_prompt.md` | 需求理解智能体 |
| `designer_prompt.md` | 设计智能体 |
| `reviewer_prompt.md` | 审核智能体 |
| `excel_export_prompt.md` | Excel 导出智能体 |

## 协作关系

```
explore(00) → BusinessAgent(01 业务全景图)
    → AnalystAgent(02 拆分需求) → UnderstandingAgent(03 需求理解)
    → DesignerAgent(03 测试点+用例) → ReviewerAgent(04 评审)
    → ExcelExportAgent(05 合并 Excel) → TesterAgent(06 执行+报告)
```

上游 00/01 产物由 `upstream_context.build_upstream_context()` 注入到 02/03 的提示词中，作为比原始需求更贴近真实页面的事实基线。
