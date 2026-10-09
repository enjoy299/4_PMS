---
name: module-e2e-test-pipeline
description: 按单个模块端到端跑通本框架的 HITL 测试流水线（一步一停：每阶段停等用户确认）：探索(00)→业务梳理(01)→需求拆分(02)→双验鲜门禁(02_5：module-deep-dive ＋ prototype-ui-compare)→需求理解/测试点/用例(03)→评审(04)→导出(05)→浏览器MCP真实执行→三格式报告(06)，以在线原型+真实系统为输入。当用户要求“把某模块从需求理解到测试点再到测试报告完整跑一遍”“跑全流程/端到端/e2e/模块流水线”，或指定模块（工业APP、知识管理、项目管理、基础数据管理等）走通全链路时使用此 skill。
---

# 模块端到端测试流水线（HITL 编排）

## 定位

把 `output/00~06` 全阶段针对**单个模块**串起来跑一遍。框架只负责生成提示词 / 测试计划 / 落盘产物；**真实的需求分析、浏览器执行、结果判定、报告撰写由 Qoder（你）完成**，再把产物写回框架期望的路径（人在环路 HITL；一步一停门禁见「阶段门禁协议」节）。

- **输入**：`inputs/requirements/<需求>.md` + `inputs/online_prototypes.yaml`（+ `inputs/prototypes/<模块>/`）+ `.env`（账号/URL）。
- **输出**：`output/00_explore … 06_reports` 各阶段产物 + 三格式测试报告。

```
explore 00 → business 01 → analyze 02 → 验鲜 02_5 → understand/design 03 → review 04 → export 05 → 执行+报告 06
   本 skill 逐阶段编排：脚本产提示词 → Qoder 做真实工作并写产物 → 下游阶段读产物
```

## 四条铁律

1. **真实执行、非阻塞**：各 `scripts/run_<stage>.py` 内部用 `read_response()` 读 stdin 等人工回贴。用 `'' |` 管道喂空输入让它立即 EOF 返回（返回 `""`，不阻塞），脚本照常写出提示词；随后**由你**完成分析并把结果写到产物路径。响应文件为**消费即归档**（读过即改名 `*_response_consumed_*.md`），重跑同一任务不会串轮消费旧回复。
2. **单模块**：一律用 `scripts/run_<stage>.py <模块名>`，不要用 `python run.py pipeline`（那是 `*_all()` 全模块）。
3. **先清污染**：开跑前删除该模块**旧的** `02、02_5~06` 产物（含旧元素对比报告 `02_5_prototype_diff/<模块>/`），避免上一轮旧编号/旧文件混入本轮（旧 explore 常导致 business 读不到而跳过）。同一批产物统一用**一个时间戳**。
4. **一步一停（阶段门禁）**：每个主线阶段产物写盘后立即停——出【阶段确认卡】、写状态文件、结束本轮等用户确认；未确认或存在未拍板 ⬜ 时严禁推进下一阶段（协议与 14 关门禁表见「阶段门禁协议」节）。

---

## 阶段编排（复制此清单跟踪进度）

```
模块流水线进度（模块名 = <MODULE>）：
（⏸ = 阶段门禁停点：完成即停、出确认卡等回复；⛔ = 需无未拍板 ⬜ 才放行；协议见「阶段门禁协议」节）
- [ ] 0 准备：确认 inputs/requirements、online_prototypes.yaml、.env；删除 <MODULE> 旧 02、02_5~06 产物；初始化门禁状态 qoder_workspace/pipeline_gate/<MODULE>.json（新轮重置 G1~G14 = not_started）
- [ ] 1 探索 00：run_explore / qoder-explore → 你用 browser MCP 探索在线原型+真实系统 → 写 00_explore/<MODULE>/ ⏸G1
- [ ] 2 业务 01：'' | run_business <MODULE> → 写业务全景图到 01_business/ ⏸G2
- [ ] 3 拆分 02：'' | run_analyze <MODULE> → 写 02_split_requirements/<MODULE>/NN-子模块.md ⏸G3⛔（风险清单无 ⬜ 才放行）
- [ ] 3.5 验鲜 02_5（双门禁，带豁免）：module-deep-dive（业务事实验鲜）⏸G4⛔ → 02_5b 视觉实现验鲜（**二选一**：prototype-ui-compare 全自动双源对比 / prototype-ui-manual-compare 人工路径只出页面清单）⏸G5⛔ → 深探核对记录 + 元素对比报告或页面清单 output/02_5_prototype_diff/<MODULE>/；需拍板项汇入 02 风险汇总生成拍板单；豁免须记理由（无原型 / 已报告且无变更走增量）；03 三子步须显式引用（见「验鲜门禁」节）
- [ ] 4 理解 03：'' | run_understand <MODULE> → 写 需求理解.md（§7 待确认问题表必带末列「确认结论(业务填)」，⬜ 问句 → 业务 ✅；⬜ 多/跨文档重复时用拍板单集中拍板：`python scripts/_backfill_confirmations.py gen <MODULE>`，工作流见 skill：requirement-testing-flow §确认拍板工作流） ⏸G6⛔
- [ ] 5 设计 03：'' | run_design <MODULE> → 写 测试点.md + 用例.md + design/test_points_<MODULE>.xlsx ⏸G7⛔（测试点 L3 后停）→ ⏸G8⛔（用例 L4 后停）
- [ ] 6 评审 04：'' | run_review <MODULE> → 写评审报告（记录 P0/P1/P2） ⏸G9
- [ ] 7 导出 05：ExcelExportAgent().export('<MODULE>') → 05_export/ 两个 xlsx ⏸G10
- [ ] 8 计划：python run.py qoder-plan <MODULE> → qoder_workspace/test_plan_<MODULE>.md（含「前置样本准备」清单：执行前逐项清零 ⬜→✅，缺样本用例直接判 BLOCKED 不盲试） ⏸G11（执行前必停）
- [ ] 9 执行：browser MCP 按 test_plan 真实执行全部用例，截图存证 → 见 browser-execution.md ⏸G12（执行后停：结果+证据齐）
- [ ]10 报告：ReportExporter().build_and_save('<MODULE>', results) → 06_reports md/html/excel + 主报告（含 BLOCKED 专章） ⏸G13（报告后停）
- [ ]11 清理 ⏸G14（确认后执行）：删除执行期间创建的测试数据；还原任何移动/状态变更；共享数据只“确认→取消”不真删
```

### 命令速查（`<MODULE>` 换成实际模块名，PowerShell 用 `'' |` 喂空 stdin）

| 阶段 | 命令 | 你产出的真实工作 → 落盘路径 |
|---|---|---|
| 1 探索 | `python scripts/run_explore.py` 或 `python run.py qoder-explore` | browser MCP 探真实系统+在线原型 → `output/00_explore/<MODULE>/`（功能地图+页面探索记录，只记事实） |
| 2 业务 | `'' \| python scripts/run_business.py <MODULE>` | 交叉比对探索事实×需求 → `output/01_business/`（业务全景图：角色/功能/实体/依赖/流程） |
| 3 拆分 | `'' \| python scripts/run_analyze.py <MODULE>` | → `output/02_split_requirements/<MODULE>/NN-子模块.md`（模块化需求，**保留需求原文关键约束**） |
| 3.5 验鲜 | 无脚本（skill 编排）：`module-deep-dive` ＋ 02_5b 二选一（`prototype-ui-compare` 全自动 / `prototype-ui-manual-compare` 人工清单） | 全自动：browser MCP 双源采集对比 → `output/00_explore/modules/<MODULE>-深探核对.md` + `output/02_5_prototype_diff/<MODULE>/`（元素对比报告+双源截图）；人工：AI 只出 `页面清单.md` 交人工对比（不流转下游）。需拍板项 → `python -X utf8 scripts/_backfill_confirmations.py gen <MODULE> --format xlsx` |
| 4 理解 | `'' \| python scripts/run_understand.py <MODULE>` | → `output/03_design/test_cases/<MODULE>/需求理解.md`（§7 必带「确认结论(业务填)」末列；⬜ 多时用 `python scripts/_backfill_confirmations.py gen <MODULE>` 生成拍板单集中拍板回填；**有 02_5 报告/深探记录时显式作为额外输入引用**） |
| 5 设计 | `'' \| python scripts/run_design.py <MODULE>` | → 同目录 `测试点.md`+`用例.md`+`design/test_points_<MODULE>.xlsx`（用例含 REQ-/TP- 追溯） |
| 6 评审 | `'' \| python scripts/run_review.py <MODULE>` | → `output/04_review/`（覆盖度/质量，缺陷分级 P0/P1/P2） |
| 7 导出 | `python -c "from agents.excel_export_agent import ExcelExportAgent; ExcelExportAgent().export('<MODULE>')"` | → `output/05_export/test_cases_<MODULE>.xlsx`+`test_points_<MODULE>.xlsx`；直接调 agent 不走 run.py 门禁，导出前先跑 `python scripts/_lint_confirmations.py <MODULE>` 自查确认列（`python run.py export` 已内置硬门禁：未拍板即阻断，`--force` 豁免） |
| 8 计划 | `python run.py qoder-plan <MODULE>` | → `qoder_workspace/test_plan_<MODULE>.md`（浏览器可执行计划：按模块分节 + 头部「前置样本准备」清单） |
| 10 报告 | 见 report-generation.md | → `output/06_reports/{markdown,html,excel}/` + 主报告 md |

> 若脚本因产物已存在而跳过：先删旧产物再跑；或直接用同名 `agents/*_agent.py` 的方法按模块处理。

---

## 阶段门禁协议（一步一停）

**默认一步一停**：每个主线阶段产物写盘后，执行「停止三步曲」——① 输出【阶段确认卡】 → ② 写状态文件 → ③ 结束本轮回复等确认；收到确认前，严禁调用任何下一阶段命令或浏览器操作。

**五条规则**

1. **阶段完成即停**：产物写盘后立即出卡 + 写状态，不再推进。
2. **开工前校验**：每阶段开工前先读 `qoder_workspace/pipeline_gate/<MODULE>.json`；上游未 `confirmed`，或本关滞留 `blocked_unfilled` → 拒绝推进，给出解除路径。
3. **放行双条件**：用户显式确认 + 相关产物无未拍板 ⬜（口径同 `python scripts/_lint_confirmations.py <MODULE>`）。⛔ 关卡存在 ⬜ 时禁止放行，唯一出口是完成拍板回填（gen → 业务填 → backfill → lint）；**流水线门禁不设旁路**（脚本层 `run.py export --force` 保留原状，仅供 CI 内部评审）。
4. **回复词表**：`继续/确认`＝放行；`继续到 G<x>`＝连续放行至该关再停；`改：<意见>`＝修订产物后重出卡；`回退 G<x>`＝回到该关；其他＝保持等待。
5. **免停情形**：被豁免/跳过的阶段、增量轮次未重跑且已 confirmed 的阶段不产生停点（状态记 `exempted` 或沿用）。

**阶段确认卡模板**（正常 ≤6 行；⛔ 阻断时附「解除指引」一行）

```
⏸ G3 拆分02 完成 — 等待确认
产物：<产物路径列表>
摘要：<3-5 行关键结论>
待确认：⬜ 未拍板 N 项（编号…）｜差异 N 条｜P0 N 个
状态：blocked_unfilled（未拍板未清不可放行）
解除指引：python -X utf8 scripts/_backfill_confirmations.py gen <MODULE> --format xlsx → 业务填 → backfill → lint
下一步预告：G4 深探核对（验鲜 4a）
请回复：继续 ／ 继续到 G<x> ／ 改：<意见> ／ 回退 G<x>
```

**门禁表（14 停，与主线阶段一一对应）**

| 关 | 阶段 | 放行条件 |
|---|---|---|
| G1 | 探索 00 | 继续 |
| G2 | 业务 01 | 继续 |
| G3 | 拆分 02 ⛔ | 继续 + 无 ⬜（拍板单闭环） |
| G4 | 验鲜 4a 深探核对 ⛔ | 继续 + 拍板类差异闭环 |
| G5 | 验鲜 4b 元素对比 ⛔ | 继续 + 拍板类差异闭环 |
| G6 | 需求理解 03a ⛔ | 继续 + 无 ⬜ |
| G7 | 测试点 03b-1 ⛔ | 继续 + 无 ⬜（L3 测试点） |
| G8 | 用例 03b-2 ⛔ | 继续 + 无 ⬜（L4 用例） |
| G9 | 评审 04 | 继续（P0 置顶显式确认，不硬阻断） |
| G10 | 导出 05 | 继续（export 硬门禁照旧兜底） |
| G11 | 执行前（计划后） | 继续（必停：计划 + 前置样本清单已澄清 + 副作用清单） |
| G12 | 执行 06a | 继续（执行小结 + 截图证据完整性） |
| G13 | 报告 06b | 继续（含 BLOCKED 处置/复测命令） |
| G14 | 清理 | 确认后执行 |

**状态文件**：`qoder_workspace/pipeline_gate/<MODULE>.json`（**不放 output/**，避免被开跑前「清污染」删除）

```json
{
  "module": "<MODULE>",
  "current": "G3",
  "updated_at": "YYYY-MM-DDTHH:MM:SS",
  "stages": {
    "G3": {"status": "blocked_unfilled", "pending": 1, "pending_items": ["PC-02"],
           "artifacts": ["..."], "summary": "", "confirmed_at": "", "note": ""}
  }
}
```

`status` 枚举：`not_started / awaiting_confirm / blocked_unfilled / confirmed / exempted`。恢复流程：读 `current` → 看该关状态 → ⛔ 未清先走解除指引 → 用户确认后改 `confirmed` → 进入下一关。

---

## 验鲜门禁（阶段 3.5）要点

02→03 之间设**双验鲜门禁**（默认必做，带豁免）。流程见 skill：`module-deep-dive`（业务事实验鲜：字段级事实 + 三方核对）与 02_5b 视觉实现验鲜二选一：`prototype-ui-compare`（AI 全自动，元素对比报告）/ `prototype-ui-manual-compare`（人工路径，只出页面清单），产物均落 `output/02_5_prototype_diff/<MODULE>/`。

- **停点（⏸G4 → ⏸G5）**：4a 深探核对完成后出【阶段确认卡】停一次（⏸G4）；4b 元素对比完成后出卡再停一次（⏸G5）（见「阶段门禁协议」节）。
- **执行顺序**：先 `module-deep-dive` 确认页面可达，再走 02_5b 视觉验鲜；两者可独立豁免，但豁免理由都要写进产物或记录。
- **02_5b 双路径（二选一，选择权在人）**：①`prototype-ui-compare`（AI 全自动：双源采集+差异报告+拍板/枚举判定闭环，产物供 03/04/06 消费）；②`prototype-ui-manual-compare`（人工轻量路径：AI 仅梳理输出 `页面清单.md`，人工自行双源对比，零浏览器 token，**产物不向下游流转**、人工差异记录自处理；若后续需 AI 报告，再跑①即可，增量豁免口径不变）。⏸G5 停点对两条路径同样生效；⛔ 拍板闭环仅适用于路径①（路径②的差异闭环责任在人）。
- **豁免条件**：①该模块无原型入口（记 N/A）；②已有报告且原型/系统均无变更（只做增量）；③深探侧跳过条件（模块极简/纯回归/距全站探索极短且无发版）。**全新一轮（需求变更/发版）删旧报告全量重比**。
- **差异去向**：需拍板 → 02 风险汇总新增章 → 拍板单闭环（`python -X utf8 scripts/_backfill_confirmations.py gen <MODULE> --format xlsx`）；已裁决（分类树形态以动态多级为准、分页以真实系统为准）→ 直接结论；轻微文案 → 03 测试点断言；疑似缺陷 → 06 验证。
- **下游引用**：脚本不自动读 02_5——03 三子步（需求理解/测试点/用例）须把报告**显式作为额外输入**引用，映射见 prototype-ui-compare skill §差异去向。

---

## 浏览器执行（阶段 9）要点

用 `browser-use` MCP（首次调用前需在本会话读过对应 tool 的 JSON schema）。**详细技巧与可复用代码片段见 [browser-execution.md](browser-execution.md)**。核心五条：

1. **瞬时 toast 捕获**：Element Plus 的 `.el-message` 约 3s 自动消失，异步读取/截图会漏。先注入全局 `MutationObserver` 把新增提示文本存到 `window.__capturedToasts`，事后再读——这是拿到“当前分类下有工业APP，不允许删除！”等关键校验文案的唯一可靠手段。
2. **EP 输入**：`fill`/`type_text` 对 Element Plus 输入框常不触发 `v-model`。改用原生 setter + `dispatchEvent('input')`；`el-select` 用 `.click()` 展开、点 `.el-select-dropdown__item` 选择（见片段）。
3. **弹窗可见性**：用 `.el-overlay` 的 `display!=none` 判断，不要用 `.el-dialog`（其 display 恒为 block，会误判）。区分工具栏按钮与行级按钮用 `!b.closest('td')`。
4. **有副作用用例**：删除/入库/移动会改真实数据。能自建的先自建后删；**共享数据只走“确认→取消”**（同样能验证按钮行为并留下 toast 证据）；任何移动操作执行完**还原**（如 A→B 后再 B→A）。
5. **前置样本先行（防 BLOCKED）**：执行前先对照计划头部「前置样本准备」清单逐项清零（⬜→✅），样本类型如第二账号/特定状态/多版本/树多选/跨模块依赖；无法提供的样本**不盲试**——对应用例直接判 `BLOCKED` 并填 `unblock_hint`，盲试得出的失败结论不可信。

---

## 报告生成（阶段 10）要点

用 `exporters/report_exporter.py` 的 `build_and_save('<MODULE>', results)` 一次性产出 md/html/excel（受 `config.REPORT_FORMAT` 控制，默认 `md,html,excel`）。`results` 结构、字段映射、**BLOCKED→manual** 映射、主报告模板见 [report-generation.md](report-generation.md)。

三态口径：**PASS/FAIL** 为真实判定；无法自动验证或被阻塞的记 **manual/BLOCKED**（不伪造 pass/fail）。主报告需含：执行汇总表、缺陷清单（BUG/DIFF/DEV 编号）、BLOCKED 专章（每条写清阻塞根因+复测前置）、数据清理说明、本轮框架能力发现。

---

## 常见坑（务必规避）

- **`load_prompt` 占位符渲染**（已修复）：旧版缺占位符时 KeyError → 回退返回**整份未替换模板**（提示词里出现字面 `{模块缩写}` 等）；模板含孤立花括号时 ValueError 直接崩溃。现版改用 `format_map` + `__missing__` 兜底：缺参仅保留对应占位符原文并 **WARNING 点名**（fail-loud），孤立花括号 ERROR 告警后返回原模板；输出示例字段须写 `{{ }}` 转义（analyst/reviewer 已统一）。回归测试：`tests/test_prompt_loader_and_response.py`（全模板渲染自检 + 调用点参数契约）。
- **旧产物污染**：跨轮残留的旧 `02~06` 文件（尤其旧编号 `02_split_requirements`、旧 `用例.md`）会被下游误读。每轮开跑前清理，统一时间戳。
- **业务梳理被跳过**：`business` 依赖上游 `00_explore` 产物；若 explore 未落盘，business 会静默跳过。确认 explore 产物存在再跑 business。
- **evaluate_script 同步性**：脚本同步执行返回，Vue 弹窗/下拉是异步渲染；“点击”与“读取渲染结果”要分成两次调用。
- **用例判定要贴需求原文**：设计阶段必须保留需求的关键约束（如“描述最多 255 字符”），否则用例预期会偏离需求、评审/执行失去基准。

---

## 实例：工业APP（参考基准）

- 输入：`inputs/requirements/11、工业APP.md` + 在线原型（`inputs/online_prototypes.yaml`）+ 真实系统 `http://10.61.196.105:9092/`（zgn）。
- 拆分出 `02-分类管理`/`03-工业APP维护`，设计 43 条用例（REQ-IA-CAT-001~011 / REQ-IA-APP-001~011 追溯），导出 43 条。
- 02_5 验鲜：元素对比报告 18 条差异（D-01~D-18）；裁决类（分类树/分页）直接结论、轻微项转测试点、PC-01~04 汇入 `04-风险清单与待确认汇总.md` 走拍板单（PC-01/03/04 已回填，PC-02 待业务）。
- 真实执行：**PASS 31 / FAIL 2 / BLOCKED 10**，可执行通过率 ~94%；缺陷 BUG-01（列表已发布 vs 详情编辑中）、DIFF-01/02/03、DEV-01。
- 报告：`output/06_reports/{markdown,html,excel}/<时间戳>_工业APP.*` + `工业APP_测试执行报告_<日期>.md` + 9 张截图。
- 清理：自建 QD 分类全部删除、移动操作还原、共享 APP 只“确认→取消”。
