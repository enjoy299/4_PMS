# output/ 流水线目录契约书

> 本文件定义 AI Web 测试框架（Qoder Edition）**测试流水线各阶段的产物目录、职责、命名约定与数据依赖**，
> 使整条流程 **通顺（阶段衔接不断链）、严谨（职责边界清晰）、无遗漏（每阶段产物可追溯）**。
> 任何新增阶段或调整目录编号，都应以本文件为准同步更新 `core/config.py`、`run.py` 与相关 skill。

---

## 一、七阶段总览

```
inputs/requirements/{n}、{模块}.md          （原始需求，唯一人工输入）
        │
  ⓪ 系统探索      →  00_explore/            页面事实（功能地图 / 探索记录）
  ① 业务梳理      →  01_business/           业务全景图（探索×需求交叉比对）
  ② 需求拆分      →  02_split_requirements/ 模块化需求文件
  ③ 用例设计      →  03_design/             需求理解 + 测试点 + 测试用例
  ④ 用例评审      →  04_review/             评审报告
  ⑤ 设计导出      →  05_export/             测试点+测试用例 Excel（交付人审阅）
  ⑥ 执行与报告    →  06_reports/            执行记录 + 测试报告（人+机器双轨）
        ▲
        └── 上游业务基线（00+01）通过 agents/upstream_context 注入 ②③ 提示词，形成闭环
```

一键顺序执行：`python run.py pipeline`（Step 1/8 业务梳理 → … → Step 8/8 执行计划）。
单阶段执行：`python run.py <命令> [模块名]`，命令见下表。

---

## 二、各阶段契约

| 阶段 | 目录 | 命令 | 生成 Agent | 输入 → 输出 | 关键 Skill |
|---|---|---|---|---|---|
| ⓪ 探索 | `00_explore/` | `explore` / `qoder-explore` | explorer / Qoder MCP | URL → 功能地图、探索记录 | `explore-web-system` |
| ① 业务梳理 | `01_business/` | `business {模块}` | `BusinessAgent` | inputs + `00_explore` → 业务全景图 | `business-analysis` |
| ② 需求拆分 | `02_split_requirements/` | `analyze {模块}` | `AnalystAgent` | inputs (+业务基线) → 模块化需求 | `analyze-requirements`（标准）/ `comprehensive-requirements-analysis`（增强）|
| ③ 用例设计 | `03_design/` | `understand` / `testpoints` / `testcases` / `design {模块}` | `UnderstandingAgent` / `DesignerAgent` | `02` (+业务基线) → 理解/测试点+台账/用例 | `design-test-cases` / `comprehensive-test-case-design` |
| ④ 用例评审 | `04_review/` | `review {模块}` | `ReviewerAgent` | `03` → 评审报告 | `comprehensive-test-case-design`(质量门禁) |
| ⑤ 设计导出 | `05_export/` | `export {模块}` | `ExcelExportAgent` | `03` → 测试点+用例 Excel | `test-doc-format`、`export-test-docs` |
| ⑥ 执行报告 | `06_reports/` | `test` / `qoder-plan {模块}` | `TesterAgent` / Qoder 桥接 | 用例 → 执行记录 + 报告 | `test-report-format`、`comprehensive-testing-workflow` |

---

## 三、目录内部结构与命名约定

### 00_explore/
系统探索的**唯一事实来源**（只记事实、不推测）。
```
00_explore/
├── {模块}-功能地图.md          # 页面结构、路由、区块、字段清单
└── {角色}-{模块}-探索记录.md    # 逐页操作流水
```
> 命名卫生：文件以**模块名**为核心关键词（`business_agent` / `upstream_context` 依赖“文件名包含模块名”匹配）；角色前缀可有，但模块名不可缺。

### 01_business/
业务全景图（8 节：系统概览 / 角色权限矩阵 / 功能清单 / 业务实体关系 / 关键流程状态 / 领域术语 / 需求缺口与实现差异 / 待确认问题）。
```
01_business/{模块}-业务全景图.md        # {模块} 为清洗数字后的模块名
```
> 铁律：只梳理业务、不生成测试点/用例。

### 02_split_requirements/
**标准范式 = 简单垂直拆分**（每模块一个子目录，内含若干 `{nn}-{子模块}.md` + `风险清单与待确认汇总.md`）。
```
02_split_requirements/
└── {模块}/
    ├── 01-项目概述.md
    ├── 02-...md
    └── 05-风险清单与待确认汇总.md
```
**可选增强 = 深度分析 6 件套**（`comprehensive-requirements-analysis` 产物：需求全景图/歧义报告/缺口审计报告/边界用例目录/模块拆分方案/需求质量基线报告）。二者允许并存，但**下游用例设计只强制消费简单拆分文件**；深度 6 件套作为加分输入按需引用。

### 03_design/
两步设计（中间人工拍板）：第一步 `testpoints`（需求理解自适应 + 测试点 + 风险台账）→ 拍板确认列 → 第二步 `testcases`（消费最新批次测试点生成用例）→ 拍板 → 04 评审。
`design` 命令为两步连续（无停顿，CI 兼容）；`understand` 可选提前跑，产物被第一步自适应消费。
```
03_design/
├── {子模块}-需求理解.md                        # 根级固定名（understand / testpoints 补产，存在即消费）
├── test_points/{父模块}/
│   ├── {nn}-{子模块}-需求理解_{ts}.md          # 历史批次（兼容保留，按 mtime 取最新消费）
│   ├── {nn}-{子模块}-测试点_{ts}.md            # 9 列（第 9 列「确认结论(业务填)」）
│   └── {nn}-{子模块}-风险清单与待确认汇总_{ts}.md  # 测试设计版：§0 承接 02 未闭项 + §1/2 新增（R-03-/Q-03-）
└── test_cases/{父模块}/{nn}-{子模块}-用例_{ts}.md     # 14 字段竖排（第 14 字段「确认结论(业务填)」）
```
> 确认列例外规则：仅真实待确认行填 `⬜ <问句>？`；依赖上游未闭项的行填 `-`（拍板入口在上游）；
> 引用编号写【见需求理解 Q3】，不复制 ⬜（防 lint 误计）。
> 台账与测试点确认列**同源**：测试点自身新 ⬜ 必须同步进台账（编号互引）；
> 无测试点批次时 `testcases` 报错阻止（用例必须建立在测试点之上）。

### 04_review/
```
04_review/{模块}/{nn}-{模块}-用例-评审报告_{ts}.md
```

### 05_export/（设计态导出，交付人审阅）
**双 Sheet Excel**（`测试点` 8 列 + `测试用例` 13 列，样式见 `test-doc-format`）。
```
05_export/{模块}/{需求编号}-{模块}-测试点+测试用例_{时间戳}.xlsx
```
> 边界：**设计阶段**产出的测试点/用例 Excel 一律放 05；不得混入 06。

### 06_reports/（执行态，人+机器双轨）
```
06_reports/
├── excel/        # 执行报告（14 字段，test-report-format），命名 {时间戳}_{模块}.xlsx，直接放本目录
├── html/         # 同名 HTML 报告
├── markdown/     # 同名 MD 报告
├── screenshots/  # 失败截图 {run}_{step}_{FAIL}_{TC-ID}.png
├── allure-results/  # Allure 原始结果（仅 test 脚本模式产生）
└── {模块}/       # STLC 工作流文档：准入检查/冒烟/测试执行记录/探索式记录/测试收尾
```
> 边界：**执行阶段**产物（结果状态 PASS/FAIL/BLOCK/SKIP、断言、耗时）才进 06；设计态文件不进。

---

## 四、数据依赖链（防孤儿）

| 产物 | 生产者 | 消费者 | 接线位置 |
|---|---|---|---|
| `00_explore/*` | 探索 | ① 业务梳理；②③ 业务基线注入 | `business_agent._find_explore_files`；`upstream_context._find_explore` |
| `01_business/*-业务全景图.md` | ① BusinessAgent | ②③ 业务基线注入 | `upstream_context._find_business` |
| `02_split_requirements/{模块}/*.md` | ② AnalystAgent | ③ 理解/设计 | `understanding_agent` / `designer_agent` |
| `03_design/test_points/*`（测试点+台账） | ③ DesignerAgent（第一步） | ③ 用例设计（第二步）；确认列 lint | `designer_agent._latest_batch` |
| `03_design/test_cases/*` | ③ DesignerAgent（第二步） | ④ 评审；⑤ 导出；⑥ qoder-plan | `reviewer/excel_export/qoder_bridge` |

**关键闭环**：`agents/upstream_context.build_upstream_context()` 会在 `analyze` / `understand` / `design`
构建提示词时，自动追加“上游业务基线”引用块（若该模块有 00/01 产物），使探索与业务梳理真正进入下游数据链；
无产物时优雅降级（返回空串，不污染提示词）。

---

## 五、执行前检查清单

- [ ] `inputs/requirements/` 已放原始需求（`{n}、{模块}.md`）
- [ ] （建议）先 `explore` 再 `business {模块}`，产出 00/01 业务基线
- [ ] `02` 采用简单拆分为标准；如需深度分析再补 6 件套
- [ ] `05` 只放设计态 Excel，`06` 只放执行态报告，不串味
- [ ] 报告字段/样式符合 `test-doc-format`（05）与 `test-report-format`（06）
- [ ] 每级确认拍板后 commit 基线（`output/01_business`、`output/02_split_requirements`、`output/03_design`）

---

## 六、产物生命周期（次与次之间怎么处理）

产物按「是否含人工资产」与「跨次用途」分三类，禁止一刀切：

| 类别 | 产物 | 跨次策略 | 版本层 |
|---|---|---|---|
| ① 含人工确认的基线 | 01 业务全景图、02 拆分/风险清单、03 需求理解/测试点/风险台账/用例（均含确认列） | **携带增强**：再生成先读往期产物确认列，`✅ <结论>` 按内容对应原样携带（编号保持稳定）；与已确认结论矛盾时新增 `⬜ <矛盾点问句>`，不得静默覆盖（提示词已内置携带指令） | **git**：`output/01_business`、`output/02_split_requirements`、`output/03_design` 已放行入库，确认拍板后 commit |
| ② 纯机器批次 | 04 评审、05 导出 | **追加 + 最新批次为准 + 归档**：`scripts/_archive_batches.py` 每类保留最近 3 批（`--keep N` 可调），其余移入同级 `archive/` | 本地 `archive/`（不入库，防堆积） |
| ③ 执行态 | 06 报告/截图/日志 | run-ID 追加，永不覆盖 | 忽略（短周期快照） |

**放行节奏（配合确认列门禁，正序执行）**：

```bash
python scripts/_lint_confirmations.py {模块}          # ① 查未拍板 ⬜ + 层间新鲜度（FAIL 不放行）
# ② 在产物确认列就地拍板：⬜ → ✅ <结论>
python scripts/_archive_batches.py --dry-run           # ③ 预演归档（确认无误解后去掉 --dry-run 正式执行）
git add output/01_business output/02_split_requirements output/03_design
git commit -m "chore(output): {模块} 确认基线快照"       # ④ 确认后提交基线（误删/覆盖有后悔药）
# ⑤ 放行下一级：testpoints → 拍板 → testcases → 拍板 → review → export；仅重跑 mtime 早于上游确认的下游
```

> 归档规则：`archive/` 不参与 `_lint_confirmations.py` 统计，也不影响导出取「最新批次」；
> 需要翻查历史批次时去同级 `archive/` 目录。

---

## 七、编号沿革

`00_explore`、`01_business` 为流水线上游新增阶段；其后目录整体顺延为
`02_split_requirements / 03_design / 04_review / 05_export / 06_reports`。
历史运行记录目录 `ai_workspace/`、`qoder_workspace/` 为过程缓存，重跑会按新编号重生成，不作为契约对象。
