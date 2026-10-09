# AI Web 自动化测试框架

基于 AI + 浏览器自动化的智能测试框架，能够自动分析需求、设计测试用例、执行测试并生成报告。

AI 分析由 **Qoder 对话**完成（脚本生成提示词并复制到剪贴板，用户把 Qoder 的回复粘贴回来）；浏览器操作有两种方式：**Playwright 纯脚本**（`test` / `explore`）或 **Qoder 桥接 MCP**（`qoder-plan` / `qoder-explore`）。

## 完整工作流程（7 阶段，对应 output/00~06）

```
探索 00_explore → 业务梳理 01_business → 需求拆分 02_split_requirements
  → 需求理解 + 测试点/用例设计 03_design → 评审 04_review → 导出 05_export → 执行/报告 06_reports
```

> 探索（00）与业务梳理（01）产出的「业务全景图」作为上游业务基线，会被注入到拆分/理解/设计（02/03）的提示词中，作为比原始需求更贴近真实页面的事实输入。

## 快速开始

1. 编辑 `.env` 文件，设置 `APP_URL`、`TEST_USERNAME`、`TEST_PASSWORD`
2. 把需求文档放到 `inputs/requirements/`（支持 .md 和 .txt）
3. 运行完整流水线：`python run.py pipeline`
4. 输入 `python run.py help` 查看所有命令

## 目录结构（按使用流程排序）

### 第一阶段：用户准备（需要你手动操作）

| 顺序 | 文件夹 | 你需要做什么 |
|:----:|--------|------------|
| 1 | `inputs/requirements/` | **放需求文档**。把要测试的功能说明写成 .md 或 .txt 文件放进来，这是整个流程的起点 |
| 2 | `inputs/prototypes/` | **放原型截图**（可选）。如果有 UI 设计稿截图放进来，AI 分析时会更准确 |
| 3 | `inputs/online_prototypes.yaml` | **配置在线原型**（可选）。填写在线设计稿网站的地址，AI 会自动打开截图 |
| 4 | `inputs/api_docs/` | **放 API 文档**（预留，暂不使用） |

### 第二阶段：探索与业务梳理（上游基线）

| 阶段 | 文件夹/产出 | 做什么 |
|:----:|------------|--------|
| 00 | `output/00_explore/` | **系统探索**产物：功能地图、页面探索记录（由 explore-web-system skill 或 `explorer_agent.py` 得到） |
| 01 | `output/01_business/` | **业务梳理智能体**（`business_agent.py`）交叉比对探索产物 + 需求 → 业务全景图 |

### 第三阶段：需求拆分与用例设计（自动生成，可查看和修改）

| 阶段 | 文件夹/文件 | 做什么 |
|:----:|------------|--------|
| 02 | `output/02_split_requirements/` | **分析智能体**（`analyst_agent.py`）将需求按业务领域拆分为模块化需求 |
| 03 | `output/03_design/test_points/` | **需求理解智能体**（`understanding_agent.py`）生成需求理解文档；分析产出的**测试点** |
| 03 | `output/03_design/test_cases/` | **设计智能体**（`designer_agent.py`）根据需求/测试点设计出**测试用例**（操作步骤 + 预期结果） |
| 04 | `output/04_review/` | **审核智能体**（`reviewer_agent.py`）检查用例质量，生成**评审报告** |
| 05 | `output/05_export/` | **导出智能体**（`excel_export_agent.py`）将测试点 + 用例合并导出为 Excel（两 Sheet） |

> 各智能体把提示词写入 `ai_workspace/` 并复制到剪贴板，需在 Qoder 对话中获取回复后回传。

### 第四阶段：执行测试

| 阶段 | 文件夹/文件 | 做什么 |
|:----:|------------|--------|
| 6 | `test_actions/` | 提供浏览器操作技能（登录、导航、填表、断言、截图等），供 Playwright 脚本调用 |
| 6 | `agents/tester_agent.py` | **测试执行智能体**生成并执行 Playwright 脚本，逐条跑用例，记录通过/失败（或通过 `qoder_bridge.py` 交由 Qoder MCP 执行） |

### 第五阶段：查看结果（自动生成）

| 阶段 | 文件夹 | 生成了什么 |
|:----:|--------|----------|
| 06 | `output/06_reports/markdown/` | Markdown 格式的测试报告 |
| 06 | `output/06_reports/html/` | HTML 网页格式的测试报告（双击即可在浏览器中查看） |
| 06 | `output/06_reports/excel/` | Excel 表格格式的测试报告 |
| 06 | `output/06_reports/screenshots/` | 测试过程中的截图证据 |
| - | `logs/` | 运行日志（记录每一步操作的详细信息） |

### 支撑模块

| 文件夹 | 作用 |
|--------|------|
| `scripts/` | 流水线各阶段的独立执行脚本，可单独运行某个阶段 |
| `test_scripts/` | 手动编写的测试执行脚本，针对具体系统定制，适合回归测试 |
| `ai_workspace/` | AI 提示词工作区，保存生成的 prompt 文件供调试和回溯 |
| `agents/qoder_bridge.py` | Qoder 桥接模块，生成测试计划供 Qoder IDE 的 Playwright MCP 执行 |
| `exporters/` | 数据导出工具，负责把测试点、用例、报告生成为各种格式的文件 |
| `utils/` | 通用工具（日志记录），被所有模块共同使用 |

## 主要文件

| 文件 | 用途 |
|------|------|
| `run.py` | 程序入口，所有命令从这里启动 |
| `.env` | 配置文件，设置目标网址、测试账号等 |
| `requirements.txt` | Python 依赖包列表 |

## 关于 agents / .agents / .qoder·skills 三个易混目录

本项目里有三个名字相近、但用途完全不同的目录，勿混淆：

| 目录 | 是什么 | 谁读它 | 删了会怎样 |
|------|--------|--------|-----------|
| `agents/` | 框架核心业务代码：各「智能体」模块（analyst/designer/tester…）+ `*_prompt.md` | Python 运行时（`run.py` 导入执行） | 流水线直接跑不起来 |
| `.qoder/skills/` | **驱动本流水线的定制测试技能**（explore-web-system、analyze-requirements、design-test-cases 等 12 个） | Qoder 编码助手按需加载 | 工作流技能缺失 |
| `.agents/skills/` | 从 GitHub 装的通用外部技能包（webapp-testing、test-driven-development… 见 `skills-lock.json`） | Qoder 编码助手按需加载 | 不影响框架运行，仅少几个通用技能 |

> 要点：`agents/` 是「程序的一部分」；`.qoder/skills/` 与 `.agents/skills/` 是给 AI 助手看的「说明书」，Python 代码不导入它们。真正与测试业务强相关的是 `.qoder/skills/`，`.agents/skills/` 仅 `webapp-testing` 的就绪探测能力已被移植进框架（见 `core/env_ready.py`）。
