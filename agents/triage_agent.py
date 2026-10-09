"""LLM 复判智能体 —— 把规则层拿不准的用例打包成清单，交给 Qoder 对话复判。

与同类智能体的差异：不走 `agent_loader.load_prompt`（其 format 渲染会把 `{{MARKER}}`
转义消解为 `{MARKER}`），而是直接读提示词文件、保留 `{{MARKER}}` 原样标记并用
`.replace()` 渲染。AI 能力仍由 Qoder 对话提供，本模块不需要 API Key。

TRIAGE_SIMPLE=true 时：
  使用 `triage_prompt_simple.md`，LLM 可直接定性 PRODUCT_BUG（不经人工门禁），
  拿不准的才输出 NEEDS_HUMAN 交人工裁决。

TRIAGE_SIMPLE=false 时：
  铁律：本模块只产出**提案**。`PRODUCT_BUG_PROPOSAL` 会被 `core.triage.merge_decisions`
  强制回落 `NEEDS_HUMAN` 并连理由一起排队给人工门禁，真实缺陷定性只能由人拍板。
"""
import json
import re
from datetime import datetime
from pathlib import Path

from core.brain import save_prompt, read_response
from core.config import TRIAGE_CONF_THRESHOLD, TRIAGE_SIMPLE
from core.triage import (append_error_log, append_llm_review, build_triage_payload,
                         load_records, run_dir)
from utils.logger import get_logger

logger = get_logger("triage_agent")
PROMPT_FILE = Path(__file__).parent / "triage_prompt.md"
PROMPT_FILE_SIMPLE = Path(__file__).parent / "triage_prompt_simple.md"


class TriageAgent:
    """复判层：只处理规则层未定论的项，输出 `llm_review.jsonl`。"""

    def review(self, rid: str, dry_run: bool = False) -> dict:
        """返回 `{reviewed, parsed, raw_failed, prompt_path}`。`dry_run=True` 只出提示词不交互。"""
        records, dup, malformed = load_records(rid)
        if dup or malformed:
            append_error_log(rid, f"复判输入不干净：重复 case_id {dup} 条、坏行 {malformed} 条，"
                                  f"以最后一条为准")
        payload = build_triage_payload(rid, records)
        if not payload:
            logger.info("[triage] 无规则层未定论用例，LLM 复判跳过")
            return {"reviewed": 0, "parsed": 0, "raw_failed": 0, "prompt_path": ""}
        prompt = self._render(rid, payload)
        task_name = f"triage_{rid}"
        prompt_path = save_prompt(task_name, prompt)
        if dry_run:
            logger.info(f"[triage] dry-run：仅生成提示词 {prompt_path}")
            return {"reviewed": len(payload), "parsed": 0, "raw_failed": 0,
                    "prompt_path": str(prompt_path)}
        response = read_response(task_name)
        items, failed_lines = parse_llm_jsonl(response)
        append_llm_review(rid, items)
        if failed_lines:
            raw = run_dir(rid) / "llm_raw" / f"{datetime.now():%Y%m%d_%H%M%S}.md"
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(response, encoding="utf-8")
            append_error_log(rid, f"LLM 回复有 {failed_lines} 行无法解析，原文存：{raw}")
        missing = {p["case_id"] for p in payload} - {i.get("case_id") for i in items}
        if missing:
            # 漏答的用例留在 NEEDS_HUMAN，但必须留痕：否则人以为「AI 看过了、没问题」
            append_error_log(rid, f"LLM 未回复 {len(missing)} 条：{sorted(missing)}")
        return {"reviewed": len(payload), "parsed": len(items), "raw_failed": failed_lines,
                "prompt_path": str(prompt_path)}

    def _render(self, rid: str, payload: list) -> str:
        """TRIAGE_SIMPLE=true 时用简化提示词（允许直接定性 Bug）。"""
        template_path = PROMPT_FILE_SIMPLE if TRIAGE_SIMPLE else PROMPT_FILE
        template = template_path.read_text(encoding="utf-8")
        cases_json = json.dumps(payload, ensure_ascii=False, indent=2)
        return (template.replace("{{RUN_ID}}", rid)
                .replace("{{THRESHOLD}}", str(TRIAGE_CONF_THRESHOLD))
                .replace("{{N_CASES}}", str(len(payload)))
                .replace("{{CASES_JSON}}", cases_json))


def _iter_json_objects(text: str):
    """扫出括号平衡的顶层 JSON 对象（字符串内的花括号与转义不计入）。

    不能按行 `json.loads`：Qoder 常把 JSONL 包进 code fence，并把一个对象缩进成多行，
    逐行解析会把整批复判结论读成 0 条 —— 而 0 条看起来和「没有待复判用例」一模一样。
    """
    depth, start, in_str, esc = 0, None, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start:i + 1]
                start = None


_CASE_ID_RE = re.compile(r'"case_id"\s*:')


def parse_llm_jsonl(text: str) -> tuple:
    """解析复判回复，返回 `(items, failed)`。`failed` 含截断对象与缺 `case_id` 的对象。"""
    text = text or ""
    items, broken = [], 0
    for chunk in _iter_json_objects(text):
        try:
            d = json.loads(chunk)
        except json.JSONDecodeError:
            broken += 1
            continue
        if isinstance(d, dict) and d.get("case_id"):
            items.append(d)
        else:
            broken += 1
    # 被截断的对象永远平衡不了、扫不出来，用「问了几条」反推漏了几条
    expected = len(_CASE_ID_RE.findall(text))
    return items, max(broken, expected - len(items))


def triage_pipeline(rid: str, do_llm: bool = False, interactive: bool = None,
                    mode: str = None, make_report: bool = True) -> dict:
    """一次跑完分流闭环。返回 `{run_id, error, summary, gate, artifacts, report, llm, human_decided}`。

    TRIAGE_SIMPLE=true 时：
      - 默认启用 LLM（无需手动加 --llm）
      - 规则层只负责确认 OK，其余全交 LLM 判定
      - LLM 可直接定性 PRODUCT_BUG，拿不准的才交人工

    为何放在 agents 层而不是 `core/triage.py`：core 保持纯函数与文件读写，便于单测；
    本函数要串 `core.human_confirm`（交互）与 `exporters`（渲染），属编排。
    """
    from core import config as _cfg
    from core.triage import (apply_rule_layer, compute_summary, derived_status, evaluate_gate,
                             load_decisions, load_llm_review, load_records, merge_decisions,
                             write_artifacts)

    # 简化模式：默认启用 LLM，无需用户手动加 --llm
    if TRIAGE_SIMPLE:
        do_llm = True

    records, dups, malformed = load_records(rid)
    if not records:
        return {"run_id": rid, "error": f"records.jsonl 无有效记录（{rid}）：先执行测试，"
                                         f"或用 scripts/_convert_legacy_result.py 转换历史结果",
                "summary": {}, "report": None, "artifacts": {}, "llm": {}, "human_decided": 0,
                "gate": {"verdict": "na", "pending": 0, "no_hint": 0, "bugs": [],
                         "note": "无记录可分流", "blocks_exit_code": False}}

    undecided = [r for r in records if not r.get("triage", {}).get("category")
                 or r["triage"].get("source") == "none"]
    if undecided:
        apply_rule_layer(undecided)                  # 已有结论的记录不被重算覆盖
    llm_info = {"reviewed": 0, "parsed": 0}
    if do_llm:
        llm_info = TriageAgent().review(rid)

    merged = merge_decisions(records, load_llm_review(rid), load_decisions(rid))
    gate_mode = mode or ("strict" if _cfg.HUMAN_CONFIRM else "report_only")
    interactive = _cfg.HUMAN_CONFIRM if interactive is None else interactive
    # 先落一份给人看的产物：门禁要在人手里过，清单必须先存在（文件即状态）
    artifacts = write_artifacts(rid, merged, compute_summary(merged), dups, malformed, gate_mode)
    decided: dict = {}
    if interactive:
        from core.human_confirm import confirm_triage_decisions   # 延迟导入：测试可 monkeypatch
        decided = confirm_triage_decisions(rid, merged) or {}
        if decided:
            merged = merge_decisions(records, load_llm_review(rid), decided)
    for rec in merged.values():
        rec["status"] = derived_status(rec)
    summary = compute_summary(merged)
    artifacts = write_artifacts(rid, merged, summary, dups, malformed, gate_mode)   # 拍板后覆写
    gate = evaluate_gate(merged, mode=gate_mode)
    report = None
    if make_report:
        from exporters.report_exporter import ReportExporter
        report = ReportExporter().build_from_records(rid, mode=gate_mode, quiet=True)
    return {"run_id": rid, "error": "", "summary": summary, "gate": gate, "artifacts": artifacts,
            "report": report, "llm": llm_info, "human_decided": len(decided),
            "duplicates": dups, "malformed": malformed}
