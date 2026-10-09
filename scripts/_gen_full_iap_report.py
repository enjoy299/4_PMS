# -*- coding: utf-8 -*-
"""工业APP全量测试报告生成器。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exporters.report_exporter import ReportExporter

ROOT = Path(__file__).resolve().parents[1]
RESULT_JSON = ROOT / "qoder_workspace" / "test_result_full_iap.json"

data = json.loads(RESULT_JSON.read_text(encoding="utf-8"))
cases = data["cases"]
bugs = data.get("bugs", [])

results = []
for c in cases:
    status_map = {"PASS": "pass", "FAIL": "fail", "MANUAL": "manual",
                  "BLOCKED": "blocked", "NOT_RUN": "skipped"}
    raw_status = c.get("status", "NOT_RUN")
    mapped_status = status_map.get(raw_status, "error")
    note = c.get("note", "")
    # 构建 assertion 明细：NOT_RUN/BLOCKED 的原因放 error，PASS 的备注放 actual
    assertions = []
    error_text = ""
    actual_text = ""
    if raw_status in ("NOT_RUN", "BLOCKED"):
        error_text = f"[{raw_status}] {note}" if note else f"[{raw_status}]"
    elif raw_status == "FAIL":
        error_text = note
    elif raw_status == "PASS":
        actual_text = note
    if c.get("assertions"):
        assertions = [{"text": a["text"], "passed": a["passed"]} for a in c["assertions"]]
    r = {
        "id": c["case_id"],
        "name": c["name"],
        "module": c["module"],
        "case_type": c.get("case_type", "正向"),
        "priority": c["priority"],
        "status": mapped_status,
        "duration": c.get("duration_sec", 0),
        "precondition": c.get("precondition", ""),
        "steps": c.get("steps", ""),
        "expected": c.get("expected", ""),
        "test_data": c.get("test_data", ""),
        "req_source": c.get("req_source", ""),
        "test_point_ref": c.get("test_point_ref", ""),
        "assertions": assertions,
        "error": error_text,
        "output": "",
        "actual": actual_text,
    }
    results.append(r)

exporter = ReportExporter()
report = exporter.build_and_save("工业APP_全量", results, bugs=bugs)

s = report["summary"]
print(f"\n=== 工业APP全量测试报告 ===")
print(f"总数: {s['total']}  Pass: {s['passed']}  Fail: {s['failed']}  "
      f"Blocked: {s.get('blocked',0)}  Not Run: {s.get('skipped',0)}  "
      f"Manual: {s['manual']}  通过率: {s['pass_rate']}")
print(f"Bug 数: {len(bugs)}")
