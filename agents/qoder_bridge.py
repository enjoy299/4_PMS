"""
Qoder 桥接模块 —— 替代 DashScope AI 浏览器控制。

核心思路：
  框架负责解析用例、生成结构化测试计划，
  用户在 Qoder 对话中直接让 Qoder 读取计划并操控浏览器执行测试。

使用方式：
  1. python run.py qoder-plan   → 生成测试计划文件
  2. 在 Qoder 对话中说："请读取 qoder_workspace/test_plan.md 并执行测试"
  3. Qoder 使用内置 Playwright MCP 工具操控浏览器

也支持探索模式：
  1. python run.py qoder-explore → 生成探索计划文件
  2. 在 Qoder 对话中说："请读取 qoder_workspace/explore_plan.md 并探索测试"
"""
import json
import re
from pathlib import Path
from datetime import datetime

from core.config import (
    DESIGN_WORKSPACE_DIR, APP_URL,
    ROOT, SCREENSHOTS_DIR, REPORTS_DIR, TRIAGE_DIR, TRIAGE_ENABLED,
)
from core.triage import make_run_id, write_plan_cases
from utils.logger import get_logger

logger = get_logger("qoder_bridge")

# Qoder 工作区（存放生成的计划文件）
QODER_WORKSPACE = ROOT / "qoder_workspace"
QODER_WORKSPACE.mkdir(parents=True, exist_ok=True)


def _result_contract_block(run_id: str, record_path) -> list:
    """线 2 的结果契约说明。JSON 示例用字符串拼接而非 f-string，避开花括号转义。"""
    return [
        "",
        "## 【硬性收尾门禁】结果必须按契约写入 JSONL",
        "",
        f"**未写入 `{record_path}` = 本次执行未完成**，不得口头汇报「已执行完」。",
        f"**计划内每一条用例都要在 JSONL 里占一行**（确实没做的写 `status: \"skipped\"` 并在 `error` 里写原因），",
        f"本 run 的用例全集已存于 `{(TRIAGE_DIR / run_id / 'plan_cases.json').as_posix()}`；",
        f"写完后运行 `python run.py triage {run_id} --validate`：它会校验契约并列出「计划 N / 已记录 M / 缺口 K」。",
        "",
        "### 必填字段与取值",
        "",
        f"- `run_id` / `executor`：`run_id` 固定填 `{run_id}`；`executor` 固定填 `qoder_mcp`",
        "- `case_id` / `name` / `module` / `status`：`status` ∈ `pass` / `fail` / `error` / "
        "`manual` / `blocked` / `skipped`（**不要用大写 PASS**）",
        "- `precondition` / `test_data` / `error`：无内容写空串，**不得缺键**",
        "- `precondition_met`：三态 `true` / `false` / `null`。只有你**明确验证过**前置没建立才填 `false`；"
        "不知道就填 `null`（填错会把用例错推进「数据前置未满足」桶并移出失败率分母）",
        "- `steps[]`：`{order, action, outcome, detail}`；`outcome` ∈ `ok`（真做了）/ `element_not_found` / "
        "`skipped`（想做但没做成，含工具不支持）/ `noop`（有意不执行：已在目标页、纯观察步骤）/ "
        "`unknown`（你没确认）；`detail` 写实际看到的现象（含可疑行为，如字符被静默过滤）",
        "- `assertions[]`：`{text, verdict, reason, evidence_refs}`；`verdict` ∈ `pass` / `fail` / "
        "`unverifiable`。**禁止新增或改写断言原文**，只能对计划里给定的断言下判定",
        "- `url_at_failure` / `screenshots[]` / `log_path` / `console_errors[]`：失败时尽量填全。",
        f"  截图必须存 `output/06_reports/screenshots/{run_id}/{{case_id}}_{{动作}}.png`（目录不存在先创建），",
        "  `screenshots[]` 填仓库相对路径；无截图就留空数组，**不得填不存在的文件名**。",
        "- `triage`：执行阶段留空（`category: \"\"`, `source: \"none\"`），由 `run.py triage` 填",
        "- 若你主张 `ENV_BLOCK` / `DATA_PRECOND`，必须同时给 `unblock_hint`（否则会被回落为待人工裁决）",
        "",
        "### 完整示例（照抄结构，替换内容）",
        "",
        "```json",
        "{",
        f'  "run_id": "{run_id}",',
        '  "executor": "qoder_mcp",',
        '  "case_id": "TC-知识管理-分类管理-001",',
        '  "name": "验证在文档知识库下新建一级分类功能正常",',
        '  "module": "分类管理",',
        '  "priority": "P0",',
        '  "case_type": "正向",',
        '  "test_point_ref": "TP-知识管理-分类管理-001",',
        '  "req_source": "CAT-01,CAT-04",',
        '  "started_at": "2026-09-14T17:30:05+08:00",',
        '  "duration_sec": 180,',
        '  "status": "fail",',
        '  "precondition": "已登录，进入知识管理页面",',
        '  "precondition_met": true,',
        '  "test_data": "分类名称：QAuto-CAT001-0914",',
        '  "error": "保存后新分类挂在 level=5 而非 level=2",',
        '  "steps": [',
        '    {"order": 1, "action": "点击左侧\\"文档知识库\\"节点", "outcome": "ok", "detail": "treeitem 展开"},',
        '    {"order": 2, "action": "点击\\"新增分类\\"按钮", "outcome": "ok", "detail": "弹窗打开"},',
        '    {"order": 3, "action": "输入分类名称", "outcome": "ok", "detail": "SUSPECT：- 被静默过滤"}',
        '  ],',
        '  "assertions": [',
        '    {"text": "弹窗关闭", "verdict": "pass", "reason": "", "evidence_refs": []},',
        '    {"text": "新分类作为一级分类出现在文档知识库下", "verdict": "fail",',
        '     "reason": "实际挂在 level=5", "evidence_refs": ["TC-知识管理-分类管理-001_保存后层级.png"]}',
        '  ],',
        '  "url_at_failure": "http://.../knowledgeManger",',
        f'  "screenshots": ["output/06_reports/screenshots/{run_id}/TC-知识管理-分类管理-001_保存后层级.png"],',
        '  "log_path": "",',
        '  "console_errors": [],',
        '  "triage": {"category": "", "source": "none", "confidence": 0.0, "rationale": "",',
        '             "suggested_action": "", "unblock_hint": "", "decided_by": "",',
        '             "decided_at": "", "overridden": false},',
        '  "bug_draft": null,',
        '  "retry_count": 0,',
        '  "needs_reconfirm": false',
        "}",
        "```",
        "",
        "> 契约违规的行会被自动降级为「待人工裁决」并记入 `triage_errors.log`，不会中断执行。",
        "> 同一 `case_id` 重复写取最后一条（可用于自我更正），重复数会进入报告摘要。",
        "> ⚠ 因而**全量计划（不带模块名）下不同模块的同名 `case_id` 会互相覆盖**（历史旧格式编号如两个模块都有 `TC-CAT-001`；新格式 `TC-模块名-子模块名-编号` 自带模块段，天然不撞号）：",
        ">   生成计划时若检出撞号会打印告警，建议按模块分别生成计划分别执行。",
    ]


# ── 前置样本准备（执行前清零防 BLOCKED）────────────────────────────────
# 样本类型自动归类规则：按序匹配、先命中先归类（归类仅供参考，最终以人工确认为准）
_SAMPLE_TYPE_RULES = (
    ("账号类", ("第二账号", "第二个账号", "其他账号", "其他用户", "另一用户", "不同用户", "跨用户")),
    ("版本样本", ("多版本", "多个版本", "版本历史", "历史版本", "低版本", "两个版本")),
    ("状态样本", ("编辑中", "已发布", "未发布", "已入库", "未入库", "审批", "驳回", "下线")),
    ("跨模块", ("模板", "知识包", "引用", "关联", "任务")),
    ("存量数据", ("已存在", "已有", "预置", "包含", "不少于", "至少", "存在", "含")),
)
# 前置里显式给出「用某用例先创建 / 复用」路径 → 可自建，不必人工准备
_SELF_BUILD_HINTS = ("可先用", "先用", "先创建", "提前创建",
                     "由 TC-", "由TC-", "来自 TC-", "来自TC-", "复用 TC-", "复用TC-")
# 各类型样本的建议动作（渲染用）
_SAMPLE_TYPE_SUGGESTIONS = {
    "账号类": "准备独立第二账号（无痕窗口 / 另一浏览器配置）",
    "版本样本": "人工构造多版本数据（同一对象至少 2 个版本）",
    "状态样本": "人工构造对应状态样本（如将样本置为「编辑中」）",
    "跨模块": "先在依赖模块建好关联数据（模板 / 知识包等）",
    "存量数据": "确认系统存量满足；不足则人工补建，或按前序用例先后创建",
    "可自建": "按用例步骤先行创建，用后按该用例清理动作清理",
    "默认环境": "登录系统并进入对应页面即可，无需额外准备",
}


def _classify_precondition(text: str) -> tuple:
    """前置条件 → (样本类型, 是否可自建)。归类仅供参考，最终以人工确认为准。"""
    if any(h in text for h in _SELF_BUILD_HINTS):
        return "可自建", True
    for type_name, kws in _SAMPLE_TYPE_RULES:
        if any(k in text for k in kws):
            return type_name, False
    return "默认环境", False


def _collect_precondition_samples(cases: list) -> list:
    """
    汇总用例前置条件 → 前置样本清单（去重聚合 + 关键词归类 + 建议动作）。

    返回条目 dict：text / type / case_ids / case_count / self_buildable / default_env / suggestion
    排序：需人工准备在前 → 可自建居中 → 默认环境垫底（组内保持首次出现顺序）。
    """
    buckets: dict = {}
    for case in cases:
        raw = (case.get("precondition") or "").strip()
        if not raw or raw == "-":   # 竖排解析器不过滤 “-” 占位符，此处统一视为空
            continue
        norm = re.sub(r"\s+", " ", raw)
        entry = buckets.get(norm)
        if entry is None:
            type_name, self_buildable = _classify_precondition(norm)
            entry = {
                "text": norm,
                "type": type_name,
                "case_ids": [],
                "self_buildable": self_buildable,
                "default_env": type_name == "默认环境",
                "suggestion": _SAMPLE_TYPE_SUGGESTIONS[type_name],
            }
            buckets[norm] = entry
        cid = case.get("id", "")
        if cid and cid not in entry["case_ids"]:
            entry["case_ids"].append(cid)

    entries = list(buckets.values())
    for e in entries:
        e["case_count"] = len(e["case_ids"])
    # list.sort 稳定：同类内保持首次出现顺序
    entries.sort(key=lambda e: (e["default_env"], e["self_buildable"]))
    return entries


def _render_sample_section(samples: list) -> list:
    """渲染「前置样本准备」节：说明 + 表格 + 统计行（插在计划正文之前）。"""
    manual = [s for s in samples if not s["default_env"] and not s["self_buildable"]]
    buildable = [s for s in samples if s["self_buildable"]]
    default_env = [s for s in samples if s["default_env"]]

    lines = [
        "## 前置样本准备（执行前清零，防 BLOCKED）",
        "",
        "执行前请先逐项落实下列样本（「就绪」列 ⬜ → ✅）；样本不齐就开跑，相关用例会被跑成 BLOCKED：",
        "",
        "1. 每项样本准备完成后，把「就绪」列改为 ✅；执行时如实填写 `precondition_met`",
        "2. 确实无法提供的样本：对应用例**直接记 `blocked`** 并填 `unblock_hint`，不要盲试（盲试得出的失败结论不可信）",
        "3. 标注「可自建」的项：按对应用例步骤先行创建，用后按该用例的清理动作清理",
        "",
        "| # | 前置·样本 | 类型 | 依赖用例 | 建议动作 | 就绪 |",
        "|---|-----------|------|----------|----------|------|",
    ]
    idx = 0
    for s in manual + buildable:
        idx += 1
        refs = s["case_ids"][:5]
        case_ref = "、".join(refs) if refs else "—"
        if s["case_count"] > 5:
            case_ref += f" 等{s['case_count']}条"
        text_cell = s["text"].replace("|", "｜")
        lines.append(f"| {idx} | {text_cell} | {s['type']} | {case_ref} | {s['suggestion']} | ⬜ |")
    if default_env:
        idx += 1
        env_cases = len({c for s in default_env for c in s["case_ids"]})
        lines.append(f"| {idx} | 基础环境：登录并进入各模块页面（{env_cases} 条用例的常规前置） "
                     f"| 默认环境 | — | 登录即满足，无需额外准备 | ✅ |")
    lines.append("")
    lines.append(f"共 {len(samples)} 项样本：需人工准备 {len(manual)} ｜ 可自建 {len(buildable)} "
                 f"｜ 默认环境 {len(default_env)}（登录即满足）")
    lines.append("")
    return lines


def generate_test_plan(module_name: str = None, level: str = "full") -> Path:
    """
    从测试用例文件生成 Qoder 可读取的测试计划。

    参数：
        module_name: 业务模块名（如“知识管理”），为 None 则生成全量计划
        level: 执行层级
            - "full"  全量执行（默认）
            - "p0"    只执行 P0 级用例（冒烟/关键路径）
            - "retry" 只重跑上次失败的用例

    命名约定：
        - 指定模块 + 层级：`qoder_workspace/test_plan_{模块名}_{P0|retry}.md`
        - 全量：`qoder_workspace/test_plan.md`

    目录约定：
        - 扫描 `output/03_design/test_cases/{业务模块}/*-用例*.md`，同 stem 取时间最新的一份
        - 兼容旧平铺目录（递归 glob）

    返回：
        测试计划文件路径
    """
    from agents.tester_agent import TesterAgent

    tester = TesterAgent()

    # --retry 模式：加载上次执行失败的 case_id 集合
    retry_case_ids: set = set()
    if level == "retry":
        from core.triage import list_runs, load_records
        runs = list_runs()
        if not runs:
            logger.error("无历史执行记录，无法重跑失败项。请先执行测试。")
            return None
        latest_rid = runs[0]  # list_runs 已按时间倒序
        records, _, _ = load_records(latest_rid)
        retry_case_ids = {r.get("case_id") for r in records
                         if r.get("status") not in ("pass", "skipped")}
        if not retry_case_ids:
            logger.info(f"上次执行（{latest_rid}）全部通过，无需重跑")
            return None
        logger.info(f"重跑模式：从 {latest_rid} 中找到 {len(retry_case_ids)} 条失败用例")

    def _strip_ts(stem: str) -> str:
        return re.sub(r"_\d{8}_\d{4}$", "", stem)

    # 查找测试用例文件（递归 + 带时间戳兼容）
    test_cases_dir = DESIGN_WORKSPACE_DIR / "test_cases"
    if module_name:
        module_dir = test_cases_dir / module_name
        if module_dir.exists() and module_dir.is_dir():
            all_files = list(module_dir.rglob("*-用例.md")) + list(module_dir.rglob("*-用例_*.md"))
        else:
            # 回退：在全量用例中按模块名包含匹配
            all_files = [
                f for f in (list(test_cases_dir.rglob("*-用例.md")) + list(test_cases_dir.rglob("*-用例_*.md")))
                if module_name in f.stem or module_name in f.parent.name
            ]
    else:
        all_files = list(test_cases_dir.rglob("*-用例.md")) + list(test_cases_dir.rglob("*-用例_*.md"))

    if not all_files:
        logger.error(f"未找到测试用例文件：{test_cases_dir}，请先运行：python run.py design")
        return None

    # 同一目录、同一去时间戳 stem → 只保留最新一份
    groups: dict[tuple, list] = {}
    for f in all_files:
        key = (str(f.parent), _strip_ts(f.stem))
        groups.setdefault(key, []).append(f)
    md_files = sorted(sorted(vs)[-1] for vs in groups.values())

    # run_id 必须在拼 plan_lines 之前定：计划头部要写死它，执行者不得自拟
    level_suffix = {"p0": "_P0", "retry": "_retry", "full": ""}[level]
    run_id = make_run_id((module_name or "全量") + level_suffix)
    record_path = TRIAGE_DIR / run_id / "records.jsonl"
    shot_dir = SCREENSHOTS_DIR / run_id
    plan_case_ids = []      # 收集计划内全部 case_id，循环结束后写 plan_cases.json
    run_line = (f"**run_id**: {run_id}　**结果文件（必须写入）**: {record_path}"
                if TRIAGE_ENABLED else "")

    level_tag = {"p0": "｜层级: P0 冒烟", "retry": "｜层级: 重跑失败项", "full": ""}[level]
    plan_lines = [
        f"# Qoder 测试执行计划" + (f"（{module_name}）" if module_name else "") + level_tag,
        f"",
        f"**生成时间**: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"**目标系统**: {APP_URL}",
        *([run_line] if run_line else []),
        f"**凭据**: 不写入计划文件；登录时从项目根 `.env` 的 `TEST_USERNAME` / `TEST_PASSWORD` 读取，严禁把口令写入任何产物（计划 / 记录 / 截图 / 日志 / 报告）",
        f"",
        f"## 执行说明",
        f"",
        f"请按以下计划执行测试。对每个测试用例：",
        f"1. 使用 Playwright MCP 工具打开浏览器并登录系统",
        f"2. 导航到对应模块页面",
        f"3. 按操作步骤逐步执行",
        f"4. 每步操作后截图作为证据",
        f"5. 检查预期结果是否满足",
        f"6. 记录通过/失败状态",
        f"",
    ]

    # 第一遍：解析全部用例块（供跨模块汇总前置样本与正文输出共用）
    parsed_blocks = []   # [(sub_name, md_file, cases)]
    for md_file in md_files:
        stem_no_ts = _strip_ts(md_file.stem)
        mod_name = stem_no_ts.replace("-用例", "").split("-", 1)[-1] if "-" in stem_no_ts else stem_no_ts
        # 若文件在业务模块子目录下，优先用目录名（如 “知识管理/01-分类管理-用例.md” → “分类管理”）
        sub_name = mod_name
        cases = tester.parse_markdown_cases(md_file)

        if not cases:
            continue

        # 按执行层级过滤用例
        if level == "p0":
            cases = [c for c in cases if (c.get("priority") or "").upper() == "P0"]
        elif level == "retry":
            cases = [c for c in cases if c.get("id") in retry_case_ids]

        if not cases:
            continue

        parsed_blocks.append((sub_name, md_file, cases))

    # 前置样本清单：跨模块去重汇总，执行前清零防 BLOCKED（插在正文之前）
    samples = _collect_precondition_samples([c for _, _, cs in parsed_blocks for c in cs])
    if samples:
        plan_lines.extend(_render_sample_section(samples))

    # 第二遍：逐模块输出正文
    total_cases = 0
    for sub_name, md_file, cases in parsed_blocks:
        plan_lines.append(f"## 模块：{sub_name} 　【源文件：{md_file.parent.name}/{md_file.name}】")
        plan_lines.append(f"")
        plan_lines.append(f"共 {len(cases)} 个测试用例。")
        plan_lines.append(f"")

        for i, case in enumerate(cases, 1):
            case_id = case.get("id", f"TC-{i}")
            case_name = case.get("name", "未命名")
            priority = case.get("priority", "P1")
            steps = case.get("steps", [])
            assertions = case.get("assertions", [])
            precondition = (case.get("precondition") or "").strip()
            test_data = (case.get("test_data") or "").strip()
            # 竖排解析器不过滤 “-” 占位符：此处统一视为空，不写进计划
            if precondition == "-":
                precondition = ""
            if test_data == "-":
                test_data = ""

            plan_lines.append(f"### {case_id} - {case_name} (优先级: {priority})")
            plan_case_ids.append(case_id)
            plan_lines.append(f"")

            if precondition:
                plan_lines.append(f"**前置条件**: {precondition}")
            if test_data:
                plan_lines.append(f"**测试数据**: {test_data}")
            if precondition or test_data:
                plan_lines.append(f"")

            if steps:
                plan_lines.append(f"**操作步骤**:")
                for s in steps:
                    order = s.get("order", "")
                    action = s.get("action", "")
                    plan_lines.append(f"{order}. {action}")
                plan_lines.append(f"")

            if assertions:
                plan_lines.append(f"**预期结果**:")
                for a in assertions:
                    plan_lines.append(f"- {a}")
                plan_lines.append(f"")

            total_cases += 1

    # 结果记录段：开关开 = 契约硬门禁；开关关 = 旧版一张 PASS/FAIL 表（一键回退）
    if TRIAGE_ENABLED:
        plan_lines.extend(_result_contract_block(run_id, record_path))
        plan_lines.extend([
            "",
            "## 执行进度小结（人类可读，供收尾报告引用）",
            "",
            "计划内**每条**用例都要在这里占一行，没做的写 `skipped` 并说明原因，不得省略行：",
            "",
            "| 用例 ID | 用例名称 | 状态 | 分流建议 | 备注 |",
            "|---------|----------|------|----------|------|",
            "| TC-知识管理-分类管理-001 | xxx | pass/fail/blocked/skipped/error/manual | 6 类之一或留空 | 说明 |",
            "",
            f"截图目录（先建再写）: `{shot_dir}`，文件名格式：用例ID_动作或阶段.png（例 TC-知识管理-分类管理-001_保存后层级.png）",
        ])
    else:
        plan_lines.extend([
            f"## 测试结果记录",
            f"",
            f"执行完成后，请按以下格式记录结果：",
            f"",
            f"| 用例 ID | 用例名称 | 状态 | 备注 |",
            f"|---------|----------|------|------|",
            f"| TC-知识管理-分类管理-001 | xxx | PASS/FAIL | 说明 |",
            f"",
            f"截图保存到: {SCREENSHOTS_DIR}",
        ])

    # 写入文件（命名带模块 + 层级后缀）
    name_parts = [p for p in [module_name, level_suffix.lstrip("_")] if p]
    plan_filename = f"test_plan_{'_'.join(name_parts)}.md" if name_parts else "test_plan.md"
    plan_path = QODER_WORKSPACE / plan_filename
    plan_path.write_text("\n".join(plan_lines), encoding="utf-8")

    # 用例全集落盘（缺口校验的唯一基准）：往 `records.jsonl` 里数行数永远数不出「没跑的」
    unique_case_ids = list(dict.fromkeys(plan_case_ids))
    collisions = sorted({c for c in unique_case_ids if plan_case_ids.count(c) > 1})
    plan_cases_path = None
    if TRIAGE_ENABLED:
        plan_cases_path = write_plan_cases(
            run_id, unique_case_ids, module=module_name or "全量",
            source_file=str(md_files[0].parent) if md_files else "")
        if collisions:
            logger.warning(f"计划内 case_id 撞号 {len(collisions)} 个：{collisions}；"
                           f"同 case_id 的记录会互相覆盖，建议按模块分别生成计划")

    logger.info(f"测试计划已生成：{plan_path}")
    logger.info(f"包含 {total_cases} 个测试用例")

    # 同时打印使用指引
    print(f"\n{'=' * 60}")
    print(f"  测试计划已生成！")
    print(f"  文件：{plan_path}")
    print(f"  用例数：{total_cases}")
    print(f"{'=' * 60}")
    if samples:
        pending = [s for s in samples if not s["default_env"]]
        manual_n = sum(1 for s in pending if not s["self_buildable"])
        build_n = len(pending) - manual_n
        print(f"\n  前置样本清单：共 {len(samples)} 项"
              f"（需人工准备 {manual_n} ｜ 可自建 {build_n} ｜ 默认环境 {len(samples) - len(pending)}）")
        for s in pending[:8]:
            print(f"    [待备] [{s['type']}] {s['text'][:60]}（{s['case_count']} 条用例）")
        if len(pending) > 8:
            print(f"    … 其余 {len(pending) - 8} 项详见计划文件「前置样本准备」节")
    if TRIAGE_ENABLED:
        print(f"\n  结果必须写入：{record_path}")
        print(f"  计划内用例 {len(unique_case_ids)} 条（去重后）→ {plan_cases_path}")
        print(f"  执行完请跑：python run.py triage {run_id} --validate")
        if collisions:
            print(f"  ⚠ case_id 撞号 {len(collisions)} 个（{', '.join(collisions[:5])}），"
                  f"同 case_id 记录会互相覆盖，建议按模块分别执行")
    print(f"\n  下一步：在 Qoder 对话中输入：")
    print(f"  \"请读取 {plan_path.resolve()} 并执行测试\"")
    print(f"")

    return plan_path


def generate_explore_plan(max_pages: int = 20) -> Path:
    """
    生成 Qoder 探索测试计划。

    参数：
        max_pages: 最多探索页面数

    返回：
        探索计划文件路径
    """
    plan_lines = [
        f"# Qoder 探索测试计划",
        f"",
        f"**生成时间**: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"**目标系统**: {APP_URL}",
        f"**凭据**: 不写入本文件；登录时从项目根 `.env` 的 `TEST_USERNAME` / `TEST_PASSWORD` 读取，严禁把口令写入任何产物",
        f"**最大探索页面数**: {max_pages}",
        f"",
        f"## 探索任务",
        f"",
        f"请对目标系统进行自由探索测试：",
        f"",
        f"### 1. 登录系统",
        f"- 打开 {APP_URL}",
        f"- 从 `.env` 读取 `TEST_USERNAME` / `TEST_PASSWORD` 登录（不得把口令写进任何记录、截图、报告）",
        f"",
        f"### 2. 遍历页面",
        f"- 点击左侧菜单，尽可能多地打开不同页面",
        f"- 最多访问 {max_pages} 个页面",
        f"",
        f"### 3. 检查项目",
        f"对每个页面检查以下内容：",
        f"- 页面是否正常加载（无 404/500 错误）",
        f"- 页面内容是否正常显示（无空白区域）",
        f"- 页面布局是否正常（无明显的 UI 问题）",
        f"- 功能按钮是否可以点击",
        f"- 表格数据是否正常加载",
        f"- 控制台是否有报错",
        f"",
        f"### 4. 结果记录",
        f"探索完成后，请记录：",
        f"- 访问的所有页面列表（页面名称 + URL）",
        f"- 发现的所有问题（问题描述 + 所在页面 + 截图）",
        f"- 总体评估",
        f"",
        f"截图保存到: {SCREENSHOTS_DIR}",
    ]

    plan_path = QODER_WORKSPACE / "explore_plan.md"
    plan_path.write_text("\n".join(plan_lines), encoding="utf-8")

    logger.info(f"探索计划已生成：{plan_path}")

    print(f"\n{'=' * 60}")
    print(f"  探索计划已生成！")
    print(f"  文件：{plan_path}")
    print(f"{'=' * 60}")
    print(f"\n  下一步：在 Qoder 对话中输入：")
    print(f"  \"请读取 {plan_path.resolve()} 并执行探索测试\"")
    print(f"")

    return plan_path
