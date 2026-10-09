"""把旧 `qoder_workspace/test_result_*.json` 一次性映射为统一契约 `records.jsonl`。

映射表（旧 → 契约）：
  meta.run_id                                  → run_id（保留原值，便于与历史报告对照）
  meta.executor 含 qoder/mcp                   → executor="qoder_mcp"
  cases[].status FAIL/PASS/BLOCKED             → fail/pass/blocked（大写归小写）
  steps_executed[].result OK/SUSPECT           → outcome="ok"（SUSPECT 的疑点留在 detail，
                                                   因为步骤确实执行过，不当作执行问题）
  expected_results[].verdict PASS/FAIL/SKIPPED → assertions[].verdict pass/fail/unverifiable
  assertions[].{target,expected,actual,passed,note} → 追加为断言（text=target，reason 含期望/实际）
  bugs[0]                                      → bug_draft（信息保留，定性仍须人工确认）
  pending_cases[].blocker                      → status="blocked" + error/unblock_hint = blocker
                                                   （`precondition_met` 留 `null`，见下方说明）

用法：
  python scripts/_convert_legacy_result.py                       # 转换 qoder_workspace 下全部
  python scripts/_convert_legacy_result.py path/to/test_result_x.json
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.triage import append_records, new_record, run_dir   # noqa: E402


def _low(v) -> str:
    return str(v or "").strip().lower()


def _status_from(v: str) -> str:
    return {"pass": "pass", "passed": "pass", "ok": "pass",
            "fail": "fail", "failed": "fail",
            "blocked": "blocked", "skip": "skipped", "skipped": "skipped",
            "manual": "manual", "error": "error"}.get(_low(v), "error")


def _verdict_from(v: str) -> str:
    return {"pass": "pass", "passed": "pass", "ok": "pass",
            "fail": "fail", "failed": "fail",
            "skipped": "unverifiable", "unverifiable": "unverifiable"}.get(_low(v), "unverifiable")


def _steps_of(case: dict) -> list:
    out = []
    for s in case.get("steps_executed", []):
        res = _low(s.get("result", ""))
        out.append({"order": s.get("order", len(out) + 1), "action": s.get("action", ""),
                    "outcome": "element_not_found" if res in ("not_found", "missing", "notfound") else "ok",
                    "detail": f"[{s.get('result')}] {s.get('detail', '')}".strip()[:300]})
    return out


def _assertions_of(case: dict) -> list:
    out = []
    for e in case.get("expected_results", []):
        skipped = _low(e.get("verdict", "")) == "skipped"
        out.append({"text": e.get("text", ""), "verdict": _verdict_from(e.get("verdict", "")),
                    "reason": e.get("actual", "") or ("执行者标记 SKIPPED" if skipped else ""),
                    "evidence_refs": []})
    for a in case.get("assertions", []):
        reason = f"期望 {a.get('expected')} / 实际 {a.get('actual')}"
        if a.get("note"):
            reason += f"（{a['note']}）"
        out.append({"text": str(a.get("target", "")),
                    "verdict": "pass" if a.get("passed") else "fail",
                    "reason": reason, "evidence_refs": []})
    return out


def _first_fail_actual(case: dict) -> str:
    """从 `expected_results` 里第一条 FAIL 取实际现象，作为 `error` 的首选来源。"""
    for e in case.get("expected_results", []):
        if _low(e.get("verdict", "")) == "fail" and e.get("actual"):
            return str(e["actual"])
    return ""


def convert(path: Path) -> tuple:
    """返回 (records, run_id)。纯函数：不写盘，便于单测直接 import。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    meta = data.get("meta", {})
    run_id = meta.get("run_id") or path.stem.replace("test_result_", "")
    raw_exec = _low(meta.get("executor", ""))
    executor = "qoder_mcp" if ("mcp" in raw_exec or "qoder" in raw_exec) else "playwright_script"
    module = meta.get("module", "")
    now = datetime.now().isoformat(timespec="seconds")
    records = []

    for case in data.get("cases", []):
        bugs = case.get("bugs") or []
        rec = new_record(
            run_id=run_id, case_id=case.get("case_id", "?"),
            module=case.get("module", module) or module, executor=executor,
            name=case.get("name", ""), priority=case.get("priority", ""),
            case_type=case.get("type", ""),
            req_source=",".join(sorted({b.get("req_source", "") for b in bugs if b.get("req_source")})),
            started_at=case.get("start_time") or meta.get("start_time") or now,
            duration_sec=float(case.get("duration_sec", 0) or 0),
            status=_status_from(case.get("status", "error")),
            # 不抄 `meta.test_account`：凭据（含账号名）不进任何落盘产物
            precondition=case.get("precondition", "") or "已登录",
            precondition_met=True,        # 已进入执行的旧用例：无更强证据时计作前置已建立
            test_data=case.get("test_data", ""),
            error=_first_fail_actual(case) or "; ".join(b.get("title", "") for b in bugs),
            steps=_steps_of(case), assertions=_assertions_of(case),
            screenshots=case.get("screenshots", []), log_path=case.get("log", ""),
        )
        rec["submodule"] = case.get("module", "")
        rec["url_at_failure"] = meta.get("target_url", "")
        rec["bug_draft"] = bugs[0] if bugs else None
        records.append(rec)

    for p in data.get("pending_cases", []):
        blocker = p.get("blocker", "") or p.get("note", "")
        rec = new_record(
            run_id=run_id, case_id=p.get("case_id", "?"),
            module=p.get("module", module) or module, executor=executor,
            name=p.get("name", ""), priority=p.get("priority", ""),
            status="blocked",
            precondition=p.get("precondition", ""),
            # 历史 pending 从没被验证过前置，写 `false` 等于伪造事实：R6 主判据会把 11 条
            # 全塞进「数据前置未满足」并移出失败率分母。留 `null`（未知），让 blocker 文本去分流。
            precondition_met=None,
            test_data=p.get("test_data", ""), error=blocker,
            started_at=p.get("start_time") or meta.get("start_time") or now,
        )
        rec["triage"]["unblock_hint"] = blocker
        records.append(rec)

    return records, run_id


def main(argv: list) -> int:
    default_dir = Path(__file__).resolve().parents[1] / "qoder_workspace"
    targets = [Path(a) for a in argv] or sorted(default_dir.glob("test_result_*.json"))
    if not targets:
        print(f"未找到 {default_dir}/test_result_*.json")
        return 1
    for t in targets:
        recs, rid = convert(t)
        append_records(recs, rid)
        print(f"{t.name} → {run_dir(rid) / 'records.jsonl'}（{len(recs)} 条，run_id={rid}）")
        print(f"  下一步：python run.py triage {rid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
