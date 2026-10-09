# 测试执行结果分流（Result Triage）设计

> 日期：2026-09-14　状态：已与用户分三节逐条确认，2026-09-15 按「MCP 为唯一执行路径」修订范围
> 范围决定：两条执行线统一数据契约，分流作为「执行后、报告前」的独立环节（方案 B：规则层 + LLM 复判 + 人工门禁）
> **执行线优先级（2026-09-15 用户修订）**：本期只把 Qoder MCP 线跑熟，Playwright 脚本线降为备用且**本期不改动**（其契约接入与假 PASS 治理延至二期）；分流内核与报告不依赖线 1 代码。

## 1. 背景与问题

框架目前有两条执行线，且**两条线的结果契约割裂**：

- **线 1 · Playwright 脚本线**（`run.py test` / `scripts/run_test.py`，定位「备用/CI」）：
  `TesterAgent._run_case` 产出 result dict，状态四态 `pass/fail/manual/error`，断言三态 `passed/verifiable/reason`，交 `ReportExporter.build_and_save` 出三格式报告。
- **线 2 · Qoder MCP 线**（`run.py qoder-plan`，定位「推荐主路径」）：
  生成 `qoder_workspace/test_plan_*.md` → Qoder 用 MCP 真操作浏览器 → **自由格式手写** `test_result_*.json`（无 schema 约束）。

三个具体缺陷：

1. **失败不分类**：真实缺陷、用例自身写错（幻觉断言）、步骤根本没执行到位、环境不可达、前置数据没备——全混在 `FAIL` 里进报告，失败率与发版结论被污染。
2. **假 PASS 隐患**：`_run_case` 里步骤「未找到元素，自动跳过」只 `logger.warning` 后 `continue`，随后断言仍在**没操作到位的页面**上跑；`_get_scope_text` 的兜底作用域含 `main`/`[role=main]`，整页文本命中即可能判 PASS。
3. **线 2 报告靠手抄**：`scripts/gen_p0_report.py` 把执行结果 `results = [...]` **硬编码进 Python 源码**，而非读取执行产生的 JSON，二者可能不一致且无从校验。

## 2. 范围与总体方案

- **覆盖范围**：两条线共用同一数据契约（本期只有 MCP 线写入）；分流环节挂在报告层，命令 `python run.py triage`。
- **分类引擎**：三层漏斗 —— 规则层（确定性、吃掉高置信度）→ LLM 复判层（只处理规则拿不准的语义判断）→ 人工门禁（关键定性与改判由人拍板）。
- **不改变**：线 1 的四态状态语义与代码保留原样（备用/CI 路径，本期不接入契约）；`ReportExporter` 三格式产出形态保留（内容扩展）；框架「AI 分析由 Qoder 对话完成、无需 API Key」的特性保留。
- **本期不动线 1**：原设计的线 1 假 PASS 治理随备用线延后。铁律②（步骤未到位 → 状态上限 `manual`）**不受影响**，因为它由规则层 R4 + 报告层派生状态实现，作用于 `records.jsonl` 里的任何记录，MCP 线自己声明的步骤 `outcome` 同样被治理。代价：备用线自身的静默跳过与 `_env_preflight()` 整批消失仍照旧。

## 3. 分类法（6 类）

| 类别 | 含义 | 状态改判 | 出口 |
|---|---|---|---|
| `PRODUCT_BUG` | 真实缺陷：行为偏离需求 | 保持 `fail` | Bug 草稿（需人确认 severity） |
| `CASE_DEFECT` | 用例/断言自身问题（含幻觉断言、断言无法定位） | `manual` | 回灌设计阶段的用例修复清单，**不提 Bug** |
| `EXEC_INCOMPLETE` | 步骤未真正执行到位（元素未找到、动作不支持被跳过） | `manual` | 定位器/动作映射修复清单后重跑 |
| `ENV_BLOCK` | 环境不可达、服务未起、5xx、会话掉线 | `blocked` | 修环境后重跑（不计入失败率分母） |
| `DATA_PRECOND` | 前置数据/账号/文件未准备 | `blocked` | 补前置后重跑（强制 `unblock_hint`） |
| `NEEDS_HUMAN` | 兜底：规则与 LLM 都拿不准，或需人定性 | 不改判 | 留在 `pending_review.md`，卡收尾门禁 |

**另有非失败基线 `OK`**：全部步骤真实执行、全部断言通过时判 `OK`，不分流、不进失败桶（规则表中记作 R0）。有此哨兵值才能把「无需处理」与「待人工裁决」分开，且使 8 段摘要各桶之和恒等于总用例数。

**`FLAKY` 本期不做**（依赖自动重跑机制，属独立一块）；schema 预留 `retry_count` 字段占位，恒为 0。

**铁律：规则层与 LLM 层都不得单独把用例定性为 `PRODUCT_BUG` 并写入发版结论——必须经人工门禁确认。** 依据：Testing Frontier 实测无人工清单时各模型 F1 均 < 30%，给出清单后升至 49.2%，即「AI 是合格执行者、不可靠规划者」。

## 4. 数据契约

### 4.1 TriageRecord（每用例一行 JSONL）

```json
{
  "run_id": "知识管理_20260914_173000",
  "executor": "playwright_script",
  "case_id": "TC-CAT-001",
  "name": "文档知识库下新建一级分类",
  "module": "分类管理",
  "priority": "P0",
  "case_type": "正向",
  "test_point_ref": "TP-CAT-001",
  "req_source": "CAT-01,CAT-04",
  "started_at": "2026-09-14T17:30:05+08:00",
  "duration_sec": 8.5,
  "status": "manual",
  "precondition": "已登录，进入知识管理页面",
  "precondition_met": true,
  "test_data": "分类名称：P0测试分类",
  "error": "",
  "steps": [
    {"order": 1, "action": "点击左侧\"文档知识库\"", "outcome": "ok", "detail": "treeitem 展开"},
    {"order": 2, "action": "点击\"新建分类\"按钮", "outcome": "element_not_found", "detail": "图标按钮选择器全部落空"}
  ],
  "assertions": [
    {"text": "弹窗关闭", "verdict": "unverifiable", "reason": "未定位到结果容器", "evidence_refs": []}
  ],
  "url_at_failure": "http://.../knowledgeManger",
  "screenshots": ["output/06_reports/screenshots/.../MANUAL_TC-CAT-001.png"],
  "log_path": "logs/run_20260914_173005_知识管理_TC-CAT-001.log",
  "console_errors": [],
  "triage": {
    "category": "EXEC_INCOMPLETE",
    "source": "rule",
    "confidence": 0.9,
    "rationale": "R4：步骤 2 element_not_found，断言在未到位页面上执行",
    "suggested_action": "补充图标按钮定位器后重跑",
    "unblock_hint": "",
    "decided_by": "",
    "decided_at": "",
    "overridden": false
  },
  "bug_draft": null,
  "retry_count": 0,
  "needs_reconfirm": false
}
```

字段约束：

- `steps[].outcome` ∈ `ok`（动作确实完成）/ `element_not_found` / `skipped`（含「动作未被实现」）/ `noop`（观察类与「已在目标页」等有意不执行）/ `unknown`（执行者未能声明），`ok` 与 `noop` 均视为真实到位，仅 `element_not_found`、`skipped` 触发 R4；`assertions[].verdict` ∈ `pass` / `fail` / `unverifiable`，直接映射 `_check_assertion` 三态。
- **不区分「关键步骤」**：任一步骤出现 `element_not_found` 或 `skipped`，用例状态上限即 `manual`，不得判 `pass`。理由：判据是「步骤有没有被真正执行」而非「步骤是否失败」，连「预期就该找不到」的负向用例也需人确认到底找没找到；此简化换取规则可判定性，避免分类器复杂化。
- 字段约束补充：`precondition`、`test_data`（R6 数据前置判定的依据之一）、`error`（R2 环境关键字判定的唯一依据）为必填字段，无内容时写空串而非缺键；`blocked` 不写入 `status`（见下）。
- `precondition_met` ∈ `true` / `false` / `null`（**三态**，R6 的主判据）：`false` = 执行者明确声明前置条件没建立成功；`null` = 未知（不参与 R6）。线 1 由登录/导航结果填，线 2 由 MCP 执行者按实际情况填，旧数据转换器对 `pending_cases` 填 `false`。

- `triage.source` ∈ `rule` / `llm` / `human`；`confidence < 0.7`（阈值可配）一律降级为 `NEEDS_HUMAN`。
- `ENV_BLOCK` / `DATA_PRECOND` 必须填 `unblock_hint`，缺失则拒收改判并回落 `NEEDS_HUMAN`。
- `executor` 决定统计与隔离归属：`playwright_script` | `qoder_mcp`。
- **`blocked` 是分流层派生状态**：`records.jsonl` 里的 `status` 仍只写原始四态（`pass/fail/manual/error`），由执行线写入、不改语义；`blocked` 只在三层结论合并后、报告展示与通过率计算时派生。这样线 1 的既有产物与单测不受影响。
- 同一 `case_id` 的重复记录数 `duplicates` 记入 `triage_errors.log` 与该 run 摘要，不进 record 字段。

### 4.2 存储布局与 run_id

```
output/06_reports/triage/{run_id}/
├── records.jsonl        # 统一执行事实 + 规则层结论（每用例一行，可增量 append）
├── plan_cases.json      # 本 run 计划内的 case_id 全集（`qoder-plan` 生成），用于「未执行缺口」校验
├── llm_review.jsonl     # LLM 复判结论（仅疑难项）
├── llm_raw/             # LLM 原始回复（解析失败时留证）
├── decisions.yaml       # 人工裁决结论（最高优先级，人拍板的持久证据）
├── pending_review.md    # 待人工裁决清单
├── triage_用例修复清单.md
├── triage_errors.log    # 损坏行/契约违规等非致命记录
└── bug_drafts/BUG-{模块}-{序号}.md
```

`run_id` 命名：MCP 线由 `python run.py qoder-plan {模块}` 生成计划时确定（`{清洗后模块名}_{YYYYMMDD_HHMMSS}`）并同时生成 `plan_cases.json`，执行者不得自拟（避免历史那种 `P0_km_20260907` 手编 id 与计划对不上）；线 1 延后，其自动 run_id 规则保留在契约里。同一 `case_id` 重复记录取最后一条（见上文 `duplicates` 说明）。

### 4.3 两条线如何写入同一契约

- **MCP 线（本期唯一入口）**：`generate_test_plan` 在计划末尾内嵌「结果契约 + 字段填写要求 + 一条完整示例」，并把**「必须按契约 append 到 `records.jsonl`」写成硬性收尾门禁**（未写 = 执行未完成），取代现在只要求填一张 Markdown 表格、事后手抄的做法。因它成为唯一入口，本期一并加固：
  - **未执行必须可见**：计划生成时写 `plan_cases.json`（计划内 case_id 全集），`python run.py triage {run_id} --validate` 比对 `records.jsonl`，报「计划 N 条 / 已记录 M 条 / 缺口 K 条」并把缺口写进报告；缺口存在时 `--validate` 退出码非 0。治的是上次「12 条只跑 1 条、剩 11 条手写 `pending_cases`」。
  - **证据链命名**：截图必须落 `output/06_reports/screenshots/{run_id}/{case_id}_{说明}.png`（线 1 由 `core/hooks.py` 保证，MCP 线此前无任何约定），record 的 `screenshots[]` 填该相对路径。
  - **凭据不落盘**：计划文件不再写 `TEST_USERNAME / TEST_PASSWORD` 明文，改为指向 `.env` 由执行时读取；`qoder_workspace/test_plan*.md` 取消 git 跟踪（口令已随历史文件入库，属既存泄漏，止血优先，历史改写另行决定）。
- **线 1（二期）**：`_run_case` 收尾组装 record 并 append；`_execute_action` 的「未找到/已跳过」改为结构化 `outcome`；`_env_preflight()` 失败时为全部用例写 `ENV_BLOCK` 后中止。本期不做，`run.py test` 行为与产物完全不变。
- **旧数据**：`scripts/_convert_legacy_result.py` 一次性把 `test_result_*.json` 映射为 `records.jsonl`，历史产物不作废，并充当契约的回归样本。

### 4.4 报告层重构

`ReportExporter` 新增 `build_from_records(run_id)`：从 `records.jsonl` + 三层结论合并后生成报告；`gen_*_report.py` 入口保留、内部改为读契约（铲除「把执行结果抄进 Python 源码」）。摘要由 4 段变 8 段，并把非产品问题移出失败率分母：

```
总用例 40 | 通过 22 | 真实缺陷 3 | 环境阻塞 5 | 数据前置未满足 4 | 用例问题 2 | 执行未到位 3 | 待人工裁决 1
有效通过率 = 22 / (40 - 5 - 4)
```

- **有效通过率** = `通过 / (总用例 - ENV_BLOCK - DATA_PRECOND)`，与原「通过率」并列展示，并注明移出数量。
- **Excel / HTML / MD 三份报告统一增列**：`分流类别`、`判定来源`、`置信度`、`裁决人`；`结论` 列取值扩展为 `PASSED / FAILED / BLOCKED / 待人工裁决`；`BLOCKED` 项在报告中**单独成表**（不进摘要大数字，也不隐藏）。
- 契约层提供 `to_result_rows(records)` 反向映射（契约 → 旧 result 行），使旧 `build_and_save()` 路径仍可从 `records.jsonl` 生成，作 `gen_*_report.py` 薄封装的数据源。
- `TRIAGE_ENABLED=false` 时完全退回旧行为（四态摘要、无分流列），保证可回滚。

## 5. 三层漏斗

### 5.1 规则层（`core/triage.py`，按序先命中先定）

| 序 | 条件（全部为可观测事实） | 判为 | conf | 建议动作 |
|---|---|---|---|---|
| R0 | `status=pass` 且所有 step `outcome ∈ {ok, noop}` 且至少一条断言且全部 `pass` | OK | 1.0 | 无需处理 |
| R1 | 该 run `_env_preflight()` 失败 / `TargetNotReadyError` | ENV_BLOCK | 1.0 | 修环境后整 run 重跑 |
| R2 | `status=error` 且 error 含 `ECONNREFUSED`/`net::ERR`/`404`/`500`/`Timeout` | ENV_BLOCK | 0.9 | 查服务与网络 |
| R3 | `url_at_failure` 含 `/login`（会话掉线连锁失败），**排除登录模块/登录用例本身** | ENV_BLOCK | 0.85 | 改用 `storageState` 持久化登录态后重跑；若已持久化仍复现，用人 `[bug]`/`[edit]` 推翻本归类 |
| R4 | 存在 `steps[].outcome ∈ {element_not_found, skipped}` | EXEC_INCOMPLETE | 0.9 | 修定位器 / 补 `_execute_action` 动作映射 |
| R5 | 全部断言 `verdict=unverifiable`（reason 命中「缺少可定位目标」/「未定位到结果容器」） | CASE_DEFECT | 0.9 | 回灌 design 阶段重写断言 |
| R6 | `precondition_met=false`（转换器对 `pending_cases` 也填此值），或 `status ∈ {fail, error, manual}` 且 `precondition`/`test_data`/`error`/`detail` 命中未备齐关键字（未准备/无法提供/缺少测试数据/需要先造/未上传/依赖TC-） | DATA_PRECOND | 0.9 | 补前置（强制 `unblock_hint`） |
| R7 | `status=fail` 且无 step 为 `element_not_found`/`skipped`，且至少一条可验证断言为 `fail`（`unknown` 不阻塞本条：执行者未声明步骤细节不应掉进执行问题） | **不下结论 → 送 LLM**（暂记 NEEDS_HUMAN） | — | — |
| R8 | 其他混合态（如 `pass` 但含 `unverifiable` 断言） | NEEDS_HUMAN | 0 | 人工裁决 |

规则层**永不产出 `PRODUCT_BUG`**（写进代码注释与文档；单测含此负向断言）。

> **R3 为何归 ENV_BLOCK**：登录态未持久化是测试基础设施缺口（主流四大护栏之一），非产品缺陷；`tester_agent` 现在撞见 `/login` 就重新登录，已将掉线当环境事件处理。不给它加重跑比对规则（那是二期 FLAKY 的活），靠人工门禁 `[bug]`/`[edit]` 推翻 + `overridden=true` 记录作为出口，稳定后二期再沉淀新规则。

### 5.2 LLM 复判层（`agents/triage_agent.py` + `agents/triage_prompt.md`）

- **输入包**（逐条疑难用例）：断言原文与 `expected_results` 逐条；**`req_source` 指向的需求原文片段**（从 `output/02_split_requirements/{模块}.md` 按 ID 精确抽取——即「把人工清单喂给 AI」）；失败现象（`actual`、`url_at_failure`、截图路径、console errors）；规则层已排除项。
- **输出契约**：`{case_id, verdict, confidence, rationale, evidence_cited[], suggested_fix, bug_draft{title,severity,reproduce[],expected,actual}}`
- **三条纪律**：① 禁止新增或改写断言，只能对给定断言下判定；② 拿不准一律回落 `NEEDS_HUMAN`；③ `confidence < 0.7` 自动降级为 `NEEDS_HUMAN`。
- **交互机制**：沿用 `core/brain.py` 的 `save_prompt` / `read_response`（`ai_workspace/triage_{run_id}_prompt.md` / `_response.md`），不新造机制、不需要 API Key。

### 5.3 人工门禁（`core/human_confirm.confirm_triage_decisions()`）

- **四类必须人拍板**：R8；LLM 低置信；结论为 `PRODUCT_BUG`（severity 归人）；任何改判为 `BLOCKED` 的（防滥用）。
- **逐条选项**：`[bug]` 确认真实缺陷 → 出 Bug 草稿；`[case]` 用例问题回灌设计；`[env]` 环境；`[data]` 补前置；`[skip]` 标 BLOCKED（强制输入 `unblock_hint`）；`[edit]` 自写结论；`[q]` 批量接受剩余建议。
- **`[q]` 作用域限制**：只批量接受 `source=llm` 且 `confidence ≥ 0.7` 且结论**不是** `PRODUCT_BUG` / `BLOCKED` 的项；遇后者重新逐条出表，防止「一路 q」把真缺陷顺手定性、或把用例批量塞进 BLOCKED 逃过分母。
- **CI（`HUMAN_CONFIRM=false`）**：不阻塞流程，按 LLM/规则建议落库并置 `needs_reconfirm=true`，在 `pending_review.md` 排队事后核；**报告不发版结论（见 §6：结论为 N/A、不影响退出码）**。
- **`decisions.yaml` 条目**：`case_id / final_category / decided_by / decided_at / overridden（是否推翻上层结论）/ note`。
- **结论合并优先级**：`decisions.yaml`（人） > `llm_review.jsonl`（LLM） > 规则层；冲突时以高层为准并记录 `overridden=true`。

## 6. 下游动作与门禁

| 类别 | 出口 |
|---|---|
| PRODUCT_BUG（人确认后） | `bug_drafts/BUG-{模块}-{序号}.md`，按 comprehensive-testing-workflow 的 Bug 模板预填（关联用例、环境+浏览器、req_source、复现步骤=steps、预期=assertions、实际=actual、截图路径），人只补 severity |
| CASE_DEFECT | 汇总 `triage_用例修复清单.md`（case_id、断言原文、判定理由、建议改写方向），下轮 `run.py design`/`review` 作为输入引用；**本期不改 designer/reviewer 代码** |
| EXEC_INCOMPLETE | 定位器/动作映射修复清单，指回 `test_actions/` 与用例步骤描述 |
| ENV_BLOCK / DATA_PRECOND | 状态改判 `blocked`，进报告独立表 + `unblock_hint` 必填 |
| NEEDS_HUMAN | 留在 `pending_review.md`，卡收尾门禁 |

**收尾门禁（区分两种模式，关键）**：

- **人在场（`HUMAN_CONFIRM=true`）→ `strict`**：存在未裁决 `NEEDS_HUMAN`，或 `BLOCKED` 缺 `unblock_hint` → 发版建议强制降级为「❌ 不具备出结论条件」，不得写「建议发版」；BLOCKED 逐项在收尾报告列明遗留，否则同样卡住。
- **CI（`HUMAN_CONFIRM=false`）→ `report_only`**：发版建议字段为 **N/A**（不是「否决」），报告标注「本次为浅分流，未做缺陷定性」，附待确认清单；**不影响退出码、不阻塞流水线**。设计理由：人不在场时根本不存在发版决策，把「未定论」伪装成「否决」会让人为了让流水线通过而整个绕过分流层；铁律仍未放宽（自动层照样不定性）。不新增 `TRIAGE_GATE` 配置，两种语义直接由 `HUMAN_CONFIRM` 推导。

**quarantine（本期只记录不重跑）**：`executor=qoder_mcp` 且被人推翻过的用例进 `quarantine.md`，与人工用例分开统计，作为第二期 FLAKY 判定的数据基础。

## 7. 文件级改动清单

**新建**：`core/triage.py`、`agents/triage_agent.py`、`agents/triage_prompt.md`、`scripts/_convert_legacy_result.py`
**修改**：`agents/tester_agent.py`（outcome 结构化 + manual 改判 + append record + 预检失败写 ENV_BLOCK）、`exporters/report_exporter.py`（`build_from_records` + 8 段摘要 + 有效通过率 + BLOCKED 独立表 + 收尾门禁 + 三格式新列）、`core/human_confirm.py`（`confirm_triage_decisions`）、`agents/qoder_bridge.py`（计划内嵌契约与硬性门禁）、`core/config.py`（`TRIAGE_DIR`、`TRIAGE_CONF_THRESHOLD`、`TRIAGE_ENABLED` + 建目录）、`run.py`（`triage` 命令 + help + pipeline 提示）
**保留入口、铲除硬编码**：`scripts/gen_p0_report.py`、`gen_iap_report.py`、`gen_p2_report.py` 三个脚本**入口保留**（命令习惯不变），内部改为读 `records.jsonl` → 调 `build_from_records()` 的薄封装，数据源强制切到统一契约；一个提交周期确认稳定后再删脚本本身（它们现在是「把执行结果抄进 Python 源码」的失真源头，只要还在，就会有人再手写第四个、绕过分流层）
**文档**：仅更新 `README.md`（06 阶段增加分流说明）；**本期不改 `.qoder/skills/` 下任何技能文档**（`module-e2e-test-pipeline`、`test-report-format` 的滞后另议）
**本期不动**：`test_scripts/` 里的空壳历史文件（另话题单独决定）

## 8. 错误处理

| 异常 | 处理 |
|---|---|
| `records.jsonl` 行损坏 | 跳过 + 记 `triage_errors.log`，不中断 |
| LLM 回复不合 JSON 契约 | 回落 `NEEDS_HUMAN`，原文存 `llm_raw/`（不猜、不硬解析） |
| `req_source` 找不到需求片段 | 输入包标注缺失，仍送判但置信度封顶 0.6 → 必进人工 |
| BLOCKED 缺 `unblock_hint` | 拒收改判，回落 `NEEDS_HUMAN` |
| 同 `case_id` 重复记录 | 取最后一条并统计 `duplicates` |
| `decisions.yaml` 引用不存在的 case | 警告 + 忽略孤儿决策，不崩 |
| 非交互终端 | 沿用 `_safe_ask` 默认值行为，标 `needs_reconfirm=true` |
| `TRIAGE_ENABLED=false` | 完整退回现有四态行为与旧报告格式（一键回退） |

## 9. 测试策略

1. **单测 `core/triage.py`**：R1–R8 各一条 record fixture，断言类别与置信度；负向断言「规则层输出中不得出现 PRODUCT_BUG」；合并优先级（人 > LLM > 规则）与 `overridden` 标记。
2. **契约回归样本**：`_convert_legacy_result.py` 转换 `qoder_workspace/test_result_P0_km_20260907.json` 后跑规则层，期望 BUG-CAT-01/02 落 R7→LLM，而非被判环境/执行问题。
3. **端到端**：用 `TARGET_SERVERS` 起本地 mock 页跑 `test → triage → 报告`，人工核对 8 段摘要、有效通过率、BLOCKED 独立表；再验证 `TRIAGE_ENABLED=false` 完全退回旧行为。
4. **门禁验证**：故意留一条 `NEEDS_HUMAN` 与一条缺 `unblock_hint` 的 BLOCKED；`HUMAN_CONFIRM=true` 下确认报告不出「建议发版」，`HUMAN_CONFIRM=false` 下确认发版建议为 N/A 且退出码为 0。

## 10. 分期与 YAGNI 边界

- **本期**：数据契约 + 线 1 outcome 结构化与假 PASS 治理 + 线 2 契约硬门禁 + 规则层 + LLM 复判 + 人工门禁 + Bug 草稿 + 报告集成与收尾校验 + 旧数据转换。
- **第二期（明确不做）**：FLAKY 自动重跑与 `retry_count` 利用；quarantine 统计看板；`decisions.yaml` 中人工推翻模式自动沉淀为新规则；BLOCKED 解除后自动跟跑。
- **永不纳入本模块**：Jira/GitHub 缺陷单同步（只出 Markdown 草稿）；重构 `test_actions` 中文动作解析；改动 designer/reviewer 逻辑；CI 内自动调用 LLM（框架无 API Key 是有意设计）。
- **CI 职责界定**：线 1 在无人/Qoder 会话时只做「冒烟 + 规则层浅分流」，R7 停在 `NEEDS_HUMAN`，报告结论为 **N/A** 而非「否决」——既不阻塞流水线，也不假装权威；不为放宽铁律而允许自动定性。

## 11. 关键决策记录

| 决策 | 取舍与理由 |
|---|---|
| 统一 schema、分流挂报告层（方案 C）而非只做一条线 | 两条线结果割裂是根因；顺带断掉「结果硬编码进 py 源码」的失真链路 |
| 规则预分 + LLM 复判 + 人工门禁（方案 B）而非纯规则/纯 LLM | 规则吃结构化事实零成本；①定性是语义活必须 LLM+人；纯 LLM 不可复现且有「默认无缺陷」偏见 |
| 步骤未到位判 `manual` 而非 `fail` | 与既有「不假装通过、不确定交人工」的三态设计哲学一致；判 fail 会污染失败率并引人追不存在的 Bug |
| 线 2 强制按契约写 `records.jsonl` + 旧数据一次性转换 | 淘汰自由格式手写；留转换器使历史产物与报告可校验 |
| 环境/数据改判 BLOCKED 且移出分母 + 三条防滥用约束 | 防「测不动就推给环境」：hint 必填、独立成表、收尾必须清零或写明遗留 |
| `[q]` 批量放行排除 PRODUCT_BUG/BLOCKED | 逐条点会在几十项时逼人放弃门禁，门禁失效比没有更糟；但不能成为定性逃逸口 |
| CASE_DEFECT 回灌设计阶段、只出清单不改代码 | Bug 库不被「需求没写清」污染；同时避免范围从分流膨胀成重构设计阶段 |
| 不区分关键步骤，任一步未执行即不得判 pass | 用规则可判定性换一点严格性；负向用例也需人确认找没找到 |
| 会话掉线（R3）归 ENV_BLOCK、不加重跑规则 | 属登录态未持久化的基础设施缺口；出口交给人工 `[bug]`/`[edit]` 推翻并记 `overridden`，避开二期 FLAKY 机制 |
| CI 下发版结论为 N/A 而非「不具备条件」 | 保留铁律（自动层不定性）同时避免夜间流水线被假阻塞；不新增 gate 配置，语义由 `HUMAN_CONFIRM` 推导 |
| 本期不动 `.qoder/skills/` 文档 | 技能是用户资产，改动需单独确认 |
| 保留完整三层方案（含 Excel/HTML 分流列、契约 `OK`/`precondition_met`/`noop` 扩展） | 曾评估过只改 Markdown、并用文本关键字代替前置声明的瘦身方案（B），用户最终选择完整落地：分流结论不能只在 MD 可见，R6 靠文本猜关键字会漏判/误判，`OK` 哨兵使 8 段桶和恒等于总数可自校验 |
| MCP 线为唯一执行路径、Playwright 线整体延后（2026-09-15） | 用户只要跑熟一条线；省掉风险最高的 `_classify_step_outcome`（与 `_execute_action` 中文返回文案强耦合）与其行号级改动；铁律② 因实现在规则层/派生状态而不丢失；备用线暂不可分流是可接受代价 |
| MCP 成为唯一入口后加固 Task 6（plan_cases 缺口校验 + 截图命名 + 计划侧固定 run_id） | 唯一入口意味着任何漏填都会静默变成「没测过」；缺口校验把「没执行」与「执行了但失败」分开，正是分流的前提；手编 run_id 会让计划与产物对不上 |
| 计划文件不再写明文凭据，且 `test_plan*.md` 取消 git 跟踪 | 凭据已随 6 个已跟踪计划文件进入版本历史，属既存泄漏；本期先止血（新文件不写 + 不再跟踪 + 现存文件脱敏改写），历史改写（filter-branch）风险高需单独决策 |

## 12. 配置项

```
TRIAGE_ENABLED=true          # 总开关，false 时完整退回旧行为
TRIAGE_CONF_THRESHOLD=0.7    # 低于此置信度降级为 NEEDS_HUMAN
HUMAN_CONFIRM=true           # 复用既有开关，CI 置 false 时门禁不阻塞
```

## 13. 参考

- [TestQuality: Playwright Test Agents & MCP — 2026 Architecture Guide](https://testquality.com/playwright-test-agents-mcp-architecture-2026/)（Agent 失败模式三分法：幻觉断言/工具循环耗尽/上下文退化；两阶段拆分；AI 合格执行者不可靠规划者）
- [browser-use/qa-use](https://github.com/browser-use/qa-use)、[naodeng/awesome-qa-skills](https://github.com/naodeng/awesome-qa-skills)、fishzjp/qa-skills（文件即状态、人工裁决检查点）、vostride/agent-qa（result-triage / debug-fix）
- 本地 skill `comprehensive-testing-workflow` 第 5.4 节 Bug 分流决策与 Phase 5 Bug 模板
