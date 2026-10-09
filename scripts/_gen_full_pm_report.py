# -*- coding: utf-8 -*-
"""
项目详情管理全量测试报告生成器。
基于 test_result_full_pm.json 生成含 Bugs sheet 的 Excel 报告。
"""
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exporters.report_exporter import ReportExporter

ROOT = Path(__file__).resolve().parents[1]
RESULT_JSON = ROOT / "qoder_workspace" / "test_result_full_pm.json"

# 加载结果
data = json.loads(RESULT_JSON.read_text(encoding="utf-8"))
cases = data["cases"]
bugs = data.get("bugs", [])

# 转换为 ReportExporter 需要的 results 格式
results = []
for c in cases:
    status_map = {"PASS": "pass", "FAIL": "fail", "MANUAL": "manual",
                  "BLOCKED": "error", "NOT_RUN": "error"}
    r = {
        "id": c["case_id"],
        "name": c["name"],
        "module": c["module"],
        "case_type": c.get("case_type", "正向"),
        "priority": c["priority"],
        "status": status_map.get(c["status"], "error"),
        "duration": c.get("duration_sec", 0),
        "precondition": c.get("precondition", ""),
        "steps": c.get("steps", ""),
        "expected": c.get("expected", ""),
        "test_data": c.get("test_data", "-"),
        "req_source": c.get("req_source", ""),
        "test_point_ref": c.get("test_point_ref", ""),
        "assertions": [],
        "output": "",
        "actual": c.get("note", ""),
    }
    # 添加断言详情
    if c.get("assertions"):
        r["assertions"] = [
            {"text": a["text"], "passed": a["passed"]}
            for a in c["assertions"]
        ]
    results.append(r)

# 生成报告
exporter = ReportExporter()
report = exporter.build_and_save("项目详情管理_全量", results, bugs=bugs)

# 打印统计
s = report["summary"]
print(f"\n=== 项目详情管理全量测试报告 ===")
print(f"总数: {s['total']}  通过: {s['passed']}  失败: {s['failed']}  "
      f"错误/未执行: {s['errors']}  人工: {s['manual']}  通过率: {s['pass_rate']}")
print(f"Bug 数: {len(bugs)}")
