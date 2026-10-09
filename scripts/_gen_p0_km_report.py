# -*- coding: utf-8 -*-
"""
一次性脚本：基于 qoder_workspace/test_result_P0_km_20260907.json +
test_plan_知识管理.md 中的 12 条 P0 用例，生成三格式测试报告（Excel/Markdown/HTML）。

用法：python scripts/_gen_p0_km_report.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.tester_agent import TesterAgent
from exporters.report_exporter import ReportExporter

ROOT = Path(__file__).resolve().parents[1]
RESULT_JSON = ROOT / "qoder_workspace" / "test_result_P0_km_20260907.json"
CASES_DIR = ROOT / "output" / "03_design" / "test_cases" / "知识管理"

# 从用例 md 加载全部 → 过滤 P0 → 关联测试点/需求来源
tester = TesterAgent()

# 三份最新用例文件
case_files = sorted(CASES_DIR.glob("*-用例_*.md"))
all_cases = []
for f in case_files:
    parsed = tester.parse_markdown_cases(f)
    for c in parsed:
        c["_source_file"] = f.name
    all_cases.extend(parsed)

p0_cases = [c for c in all_cases if c.get("priority") == "P0"]
print(f"[load] 共解析 {len(all_cases)} 条用例，P0 数量 = {len(p0_cases)}")

# 加载已执行结果
exec_result = json.loads(RESULT_JSON.read_text(encoding="utf-8"))
executed_map = {c["case_id"]: c for c in exec_result["cases"]}
pending_map = {p["case_id"]: p for p in exec_result.get("pending_cases", [])}


def fmt_steps(steps_list):
    """把 parse_markdown_cases 的 steps 结构拼成 '1. xxx 2. xxx' 字符串。"""
    if not steps_list:
        return ""
    parts = []
    for s in steps_list:
        order = s.get("order", "")
        action = s.get("action", "")
        # 清理 <br> 换行标记
        action = re.sub(r"<br\s*/?>", " ", str(action)).strip()
        parts.append(f"{order}. {action}")
    return " ".join(parts)


def fmt_assertions(assert_list):
    if not assert_list:
        return ""
    return " ".join(f"{i+1}. {a}" for i, a in enumerate(assert_list))


# 组装 results
results = []
for case in p0_cases:
    cid = case.get("id")
    base = {
        "id": cid,
        "name": case.get("name", ""),
        "module": case.get("module", ""),
        "case_type": case.get("case_type", "正向"),
        "priority": case.get("priority", "P0"),
        "precondition": case.get("precondition", ""),
        "steps": fmt_steps(case.get("steps", [])),
        "expected": fmt_assertions(case.get("assertions", [])),
        "test_data": case.get("test_data", "") or "-",
        "req_source": case.get("req_source", ""),
        "test_point_ref": case.get("test_point_ref", ""),
        "duration": 0,
        "assertions": [],
        "output": "",
        "error": "",
        "status": "error",  # 默认视为未执行
    }

    if cid in executed_map:
        # 已执行 → 用执行结果覆盖
        ex = executed_map[cid]
        base["status"] = {"PASS": "pass", "FAIL": "fail", "MANUAL": "manual"}.get(ex["status"], "error")
        base["duration"] = ex.get("duration_sec", 0)
        # 断言详情用执行结果里的 assertions
        base["assertions"] = [
            {"text": f"{a['target']}: 期望 {a['expected']} / 实际 {a['actual']}"
                     + (f" ({a.get('note')})" if a.get("note") else ""),
             "passed": a["passed"]}
            for a in ex.get("assertions", [])
        ]
        # 合并 bug 描述到 error
        raw_bugs = ex.get("bugs", [])
        if raw_bugs and isinstance(raw_bugs[0], dict):
            bugs_text = " ".join(
                f"【缺陷 {b['id']} ({b['severity']})】{b['title']}"
                for b in raw_bugs
            )
        else:
            # bugs 可能是纯字符串 ID 列表
            bugs_text = " ".join(f"【缺陷 {b}】" for b in raw_bugs) if raw_bugs else ""
        base["error"] = bugs_text
        # 步骤用实际执行过的
        if ex.get("steps_executed"):
            base["steps"] = " ".join(
                f"{s['order']}. {s['action']} 【{s['result']}】"
                for s in ex["steps_executed"]
            )
        # 附截图路径
        if ex.get("screenshots"):
            base["output"] = "截图: " + "; ".join(ex["screenshots"])
    elif cid in pending_map:
        # 未执行 → error + blocker 原因
        pb = pending_map[cid]
        base["error"] = f"未执行 (BLOCKED): {pb['blocker']}"
    else:
        base["error"] = "未执行：不在已执行列表中"

    results.append(base)

# 打印分布
p0_ids = [r["id"] for r in results]
print(f"[p0] 12 条 P0：{p0_ids}")

# 生成报告
exporter = ReportExporter()
bugs_data = exec_result.get("bugs", [])
report = exporter.build_and_save("知识管理_P0", results, bugs=bugs_data)

# 打印关键路径
print("\n=== 报告生成完毕 ===")
print(f"总数: {report['summary']['total']}  通过: {report['summary']['passed']}  失败: {report['summary']['failed']}  错误(含未执行): {report['summary']['errors']}  通过率: {report['summary']['pass_rate']}")
