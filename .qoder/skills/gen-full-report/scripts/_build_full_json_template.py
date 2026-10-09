# -*- coding: utf-8 -*-
"""
全量测试结果 JSON 构建器 —— 模板。

使用方法：
1. 复制本文件到 scripts/ 目录，改名为 _build_full_{模块缩写}_json.py
2. 修改下方 ── 配置 ── 区域的 3 个变量
3. 填充 ALL_CASES（用例定义）和 executed（执行结果）
4. 运行: python scripts/_build_full_{模块缩写}_json.py
"""
import json
import re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]

# ── 配置（按模块修改） ──
MODULE_NAME = "模块中文名"                          # ← 改这里
OUT_JSON_NAME = "test_result_full_xxx.json"         # ← 改这里
CASE_MD_PATH = "output/03_design/test_cases/模块名/用例文件.md"  # ← 改这里
# ──────────────────────────────

OUT_JSON = ROOT / "qoder_workspace" / OUT_JSON_NAME
CASE_MD = ROOT / CASE_MD_PATH


def _parse_case_md(path: Path) -> dict:
    """解析用例 markdown（### TC-XXX 块中 | 字段 | 值 | 格式）。"""
    result = {}
    if not path.exists():
        return result
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r'(?=^### (TC-[\w-]+))', text, flags=re.MULTILINE)
    field_map = {"前置条件": "precondition", "操作步骤": "steps",
                 "预期结果": "expected", "测试数据": "test_data"}
    for block in blocks:
        m = re.match(r'^### (TC-[\w-]+)', block)
        if not m:
            continue
        cid = m.group(1)
        fields = {}
        for cn, key in field_map.items():
            pat = rf'\|\s*{cn}\s*\|\s*(.+?)\s*\|'
            mm = re.search(pat, block)
            if mm:
                raw = mm.group(1).strip()
                raw = raw.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')
                raw = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', raw)
                fields[key] = raw
            else:
                fields[key] = ""
        result[cid] = fields
    return result


_CASE_FIELDS = _parse_case_md(CASE_MD)

# ── 全部用例定义（从用例 MD 提取，每条一行） ──
ALL_CASES = [
    # {"case_id":"TC-XXX-001","name":"用例标题","module":"子模块名","priority":"P0","case_type":"正向","req_source":"XXX-01","test_point_ref":"TP-XXX-001"},
    # ... 按实际用例填充
]

# ── 执行结果（测试执行后逐条填入） ──
executed = {
    # "TC-XXX-001": {"status":"PASS","duration_sec":5,"note":"实际结果描述"},
    # 状态取值: PASS / FAIL / BLOCKED / NOT_RUN / MANUAL
    # ... 按实际结果填充
}

# ── 发现的 BUG（可选） ──
bugs = [
    # {
    #     "id": "BUG-XXX-001",
    #     "title": "BUG 标题",
    #     "severity": "严重",       # 严重/一般/轻微
    #     "related_case": "TC-XXX-001",
    #     "description": "详细描述",
    #     "expected": "预期行为",
    #     "actual": "实际行为",
    #     "req_source": "XXX-01",
    #     "affected_cases": ["TC-XXX-001"],
    # },
]

# ── 组装（无需修改） ──
cases = []
for defn in ALL_CASES:
    cid = defn["case_id"]
    ex = executed.get(cid, {})
    fields = _CASE_FIELDS.get(cid, {})
    cases.append({
        **defn,
        "precondition": fields.get("precondition", ""),
        "steps": fields.get("steps", ""),
        "expected": fields.get("expected", ""),
        "test_data": fields.get("test_data", ""),
        "status": ex.get("status", "NOT_RUN"),
        "duration_sec": ex.get("duration_sec", 0),
        "note": ex.get("note", ""),
        "assertions": ex.get("assertions", []),
    })

output = {
    "module": MODULE_NAME,
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "total": len(cases),
    "passed": sum(1 for c in cases if c["status"] == "PASS"),
    "failed": sum(1 for c in cases if c["status"] == "FAIL"),
    "blocked": sum(1 for c in cases if c["status"] == "BLOCKED"),
    "not_run": sum(1 for c in cases if c["status"] == "NOT_RUN"),
    "bugs": bugs,
    "cases": cases,
}

OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
OUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"已写入 {OUT_JSON}")
print(f"总数: {output['total']}  通过: {output['passed']}  失败: {output['failed']}  阻塞: {output['blocked']}  未执行: {output['not_run']}")
print(f"Bug 数: {len(bugs)}")
