"""三层结论合并、8 段摘要、有效通过率、收尾门禁、`decisions.yaml` 读写。"""
import copy
import json

import pytest

from core import config
from core.triage import (
    compute_summary, derived_status, evaluate_gate, load_decisions, merge_decisions,
    new_record, run_dir, save_decisions, write_artifacts, _parse_decisions_fallback,
)

BASE = new_record(run_id="r1", case_id="TC-001", module="知识管理")
# 摘要里非桶的派生字段，算「桶和 == 总用例」这条自检不变量时必须排除
NON_BUCKET_KEYS = ("总用例", "通过率", "有效通过率", "移出分母")


@pytest.fixture
def rid(tmp_path, monkeypatch):
    d = tmp_path / "triage" / "R_MERGE_20260915_120000"
    monkeypatch.setattr(config, "TRIAGE_DIR", d.parent)
    return d.name


def _rec(cid, **kw):
    r = copy.deepcopy(BASE)
    r["case_id"] = cid
    r["status"] = kw.get("status", "fail")
    r["triage"] = {**r["triage"], **kw.get("triage", {})}
    return r


def test_human_overrides_llm_and_rule():
    recs = [_rec("TC-001", triage={"category": "NEEDS_HUMAN", "source": "rule"})]
    human = {"TC-001": {"final_category": "PRODUCT_BUG", "decided_by": "tester",
                        "severity": "S2", "note": "确认缺陷", "confirmed_by_human": True}}
    merged = merge_decisions(recs, {}, human)
    assert merged["TC-001"]["triage"]["category"] == "PRODUCT_BUG"
    assert merged["TC-001"]["triage"]["source"] == "human"
    assert merged["TC-001"]["triage"]["overridden"] is True


def test_llm_overrides_rule():
    recs = [_rec("TC-002", triage={"category": "NEEDS_HUMAN", "source": "rule", "confidence": 0.0})]
    llm = {"TC-002": {"verdict": "CASE_DEFECT", "confidence": 0.85, "rationale": "断言与需求无关",
                      "suggested_fix": "重写断言"}}
    t = merge_decisions(recs, llm, {})["TC-002"]["triage"]
    assert (t["category"], t["source"], t["confidence"]) == ("CASE_DEFECT", "llm", 0.85)


def test_low_confidence_llm_falls_back_to_needs_human():
    """LLM 结论被丢弃后，归属仍是规则层：写 llm 等于谎报是谁下的结论。"""
    recs = [_rec("TC-003", triage={"category": "NEEDS_HUMAN", "source": "rule"})]
    llm = {"TC-003": {"verdict": "DATA_PRECOND", "confidence": 0.4, "unblock_hint": ""}}
    t = merge_decisions(recs, llm, {})["TC-003"]["triage"]
    assert t["category"] == "NEEDS_HUMAN" and t["source"] == "rule"
    assert "低置信" in t["rationale"]


def test_llm_proposal_stays_needs_human_but_is_not_thrown_away():
    """提案不是结论，但也不能被丢进垃圾桶：人工门禁要看得见 LLM 的理由与 Bug 草稿。"""
    recs = [_rec("TC-020", triage={"category": "NEEDS_HUMAN", "source": "rule"})]
    llm = {"TC-020": {"verdict": "PRODUCT_BUG_PROPOSAL", "confidence": 0.9,
                      "rationale": "断言 2 与需求 CAT-01 冲突",
                      "evidence_cited": ["需求 CAT-01：仅文档知识库下支持新建分类"],
                      "bug_draft": {"title": "挂载位置错误", "severity": "S2"}}}
    merged = merge_decisions(recs, llm, {})["TC-020"]
    assert merged["triage"]["category"] == "NEEDS_HUMAN"
    assert merged["triage"]["source"] == "rule"          # 归属仍是规则层，写 llm 等于谎报定性者
    assert merged["llm_proposal"]["bug_draft"]["title"] == "挂载位置错误"
    assert merged["llm_proposal"]["evidence_cited"][0].startswith("需求 CAT-01")
    assert "待人工拍板" in merged["triage"]["rationale"]


def test_high_confidence_proposal_still_goes_to_human_bucket():
    """铁律①：置信度再高也不能翻过人工门禁，只能排队。"""
    recs = [_rec("TC-021", triage={"category": "NEEDS_HUMAN", "source": "rule"})]
    llm = {"TC-021": {"verdict": "PRODUCT_BUG_PROPOSAL", "confidence": 0.99, "rationale": "x"}}
    merged = merge_decisions(recs, llm, {})
    assert compute_summary(merged)["待人工裁决"] == 1
    assert compute_summary(merged)["真实缺陷"] == 0
    assert merged["TC-021"]["needs_reconfirm"] is True


def test_unconfirmed_human_product_bug_is_refused():
    """没经人真确认的 PRODUCT_BUG（如 CI 自动预写的建议）与 LLM 同权降级。"""
    recs = [_rec("TC-003B", triage={"category": "NEEDS_HUMAN", "source": "rule"})]
    human = {"TC-003B": {"final_category": "PRODUCT_BUG", "decided_by": "auto"}}
    merged = merge_decisions(recs, {}, human)["TC-003B"]
    assert merged["triage"]["category"] == "NEEDS_HUMAN"
    assert "未经人确认" in merged["triage"]["rationale"]


def test_unconfirmed_human_non_bug_is_not_attributed_to_human():
    """CI 预写的非 PRODUCT_BUG 建议同样不是人证：标成 human 会把 `needs_reconfirm` 假落。"""
    recs = [_rec("TC-022", triage={"category": "NEEDS_HUMAN", "source": "rule"})]
    human = {"TC-022": {"final_category": "ENV_BLOCK", "decided_by": "auto:ci"}}
    merged = merge_decisions(recs, {}, human)["TC-022"]
    assert merged["triage"]["source"] != "human"
    assert merged["triage"]["category"] == "NEEDS_HUMAN"
    assert merged["needs_reconfirm"] is True


def test_unconfirmed_ci_decision_does_not_wipe_llm_conclusion():
    """CI 预写的建议未被确认：不得采纳为人证，也不得反过来把 LLM 结论擦回 NEEDS_HUMAN。"""
    recs = [_rec("TC-025", triage={"category": "CASE_DEFECT", "source": "llm", "confidence": 0.9})]
    human = {"TC-025": {"final_category": "CASE_DEFECT", "decided_by": "auto:ci",
                        "confirmed_by_human": False}}
    merged = merge_decisions(recs, {}, human)["TC-025"]
    assert merged["triage"]["category"] == "CASE_DEFECT"
    assert merged["triage"]["source"] == "llm"
    assert merged["needs_reconfirm"] is True


def test_confirmed_human_blocked_category_keeps_unblock_hint():
    """人标的阻塞不得因「没把 unblock_hint 接下去」而被自己的降级规则退回。"""
    recs = [_rec("TC-023", triage={"category": "NEEDS_HUMAN", "source": "rule"})]
    human = {"TC-023": {"final_category": "ENV_BLOCK", "decided_by": "tester",
                        "confirmed_by_human": True, "unblock_hint": "重启网关后重跑"}}
    merged = merge_decisions(recs, {}, human)["TC-023"]
    assert merged["triage"]["category"] == "ENV_BLOCK"
    assert merged["triage"]["unblock_hint"] == "重启网关后重跑"
    assert merged["needs_reconfirm"] is False


def test_confirmed_human_blocked_without_hint_still_falls_back():
    """人也不能靠标阻塞逃分母：没写解除路径就仍算未说明原因。"""
    recs = [_rec("TC-024", triage={"category": "NEEDS_HUMAN", "source": "rule"})]
    human = {"TC-024": {"final_category": "DATA_PRECOND", "decided_by": "tester",
                        "confirmed_by_human": True}}
    merged = merge_decisions(recs, {}, human)["TC-024"]
    assert merged["triage"]["category"] == "NEEDS_HUMAN"
    assert "缺 unblock_hint" in merged["triage"]["rationale"]


def test_blocked_without_hint_becomes_needs_human():
    recs = [_rec("TC-004", triage={"category": "ENV_BLOCK", "source": "rule", "confidence": 0.9,
                                   "unblock_hint": ""})]
    t = merge_decisions(recs, {}, {})["TC-004"]["triage"]
    assert t["category"] == "NEEDS_HUMAN"


def test_non_human_product_bug_is_refused():
    """铁律：非人工来源的 PRODUCT_BUG 在合并层拒收，回落 NEEDS_HUMAN。"""
    recs = [_rec("TC-005", triage={"category": "PRODUCT_BUG", "source": "llm", "confidence": 0.95})]
    t = merge_decisions(recs, {}, {})["TC-005"]["triage"]
    assert t["category"] == "NEEDS_HUMAN"
    assert "铁律" in t["rationale"]


def test_ok_case_not_counted_as_pending():
    recs = [_rec("TC-006", status="pass", triage={"category": "OK", "source": "rule", "confidence": 1.0})]
    s = compute_summary(merge_decisions(recs, {}, {}))
    assert s["通过"] == 1 and s["待人工裁决"] == 0 and s["其他异常"] == 0


def test_bucket_sum_equals_total():
    recs = [_rec("TC-010", triage={"category": "ENV_BLOCK", "source": "rule", "confidence": 0.9,
                                   "unblock_hint": "起服务"}),
            _rec("TC-011", status="pass", triage={"category": "OK", "source": "rule", "confidence": 1.0}),
            _rec("TC-012", triage={"category": "NEEDS_HUMAN", "source": "rule"})]
    s = compute_summary(merge_decisions(recs, {}, {}))
    buckets = {k: v for k, v in s.items() if k not in NON_BUCKET_KEYS}
    assert s["总用例"] == sum(buckets.values()) == 3


def test_untitled_record_lands_in_other_bucket_not_silently_dropped():
    """未过规则层的记录（category 空）必须进「其他异常」，保证桶和==总用例这条自检不变量不被抹平。"""
    recs = [_rec("TC-011B", status="pass", triage={"category": "", "source": "none"})]
    s = compute_summary(merge_decisions(recs, {}, {}))
    assert s["其他异常"] == 1 and s["通过"] == 0


def test_effective_pass_rate_excludes_env_and_data():
    recs = [_rec("TC-013", status="pass", triage={"category": "OK", "source": "rule", "confidence": 1.0}),
            _rec("TC-014", triage={"category": "ENV_BLOCK", "source": "rule", "confidence": 0.9,
                                   "unblock_hint": "起服务"}),
            _rec("TC-015", triage={"category": "DATA_PRECOND", "source": "rule", "confidence": 0.9,
                                   "unblock_hint": "造数据"}),
            _rec("TC-016", triage={"category": "EXEC_INCOMPLETE", "source": "rule", "confidence": 0.9})]
    s = compute_summary(merge_decisions(recs, {}, {}))
    assert s["通过率"] == 25.0
    assert s["有效通过率"] == round(1 / 2 * 100, 1)      # 分母 4-1-1=2
    assert s["移出分母"] == 2


def test_derived_status_maps_blocked_and_manual():
    recs = [_rec("TC-017", triage={"category": "ENV_BLOCK", "source": "rule", "confidence": 0.9,
                                   "unblock_hint": "起服务"}),
            _rec("TC-018", status="fail", triage={"category": "CASE_DEFECT", "source": "rule",
                                                  "confidence": 0.9})]
    merged = merge_decisions(recs, {}, {})
    assert derived_status(merged["TC-017"]) == "blocked"
    assert derived_status(merged["TC-018"]) == "manual"


def test_strict_gate_blocks_on_needs_human_and_release_ready():
    recs = [_rec("TC-019", triage={"category": "NEEDS_HUMAN", "source": "rule"}),
            _rec("TC-020", triage={"category": "ENV_BLOCK", "source": "rule", "confidence": 0.9,
                                   "unblock_hint": "起服务"})]
    merged = merge_decisions(recs, {}, {})
    human = evaluate_gate(merged, mode="strict")
    assert human["verdict"] == "reject" and human["pending"] == 1
    clean = evaluate_gate({"TC-020": merged["TC-020"]}, mode="strict")
    assert clean["verdict"] == "allow"


def test_ci_gate_is_na_and_never_blocks():
    recs = [_rec("TC-021", triage={"category": "NEEDS_HUMAN", "source": "rule"})]
    g = evaluate_gate(merge_decisions(recs, {}, {}), mode="report_only")
    assert g["verdict"] == "na" and g["blocks_exit_code"] is False


# ── decisions.yaml：人工裁决是唯一能定性 PRODUCT_BUG 的入口，丢解读 = 铁律被静默绕过 ──
def test_save_then_load_decisions_roundtrip(rid):
    dec = {"TC-001": {"final_category": "PRODUCT_BUG", "confirmed_by_human": True,
                      "decided_by": "tester", "note": "确认缺陷：保存后层级挂错"}}
    save_decisions(rid, dec)
    got = load_decisions(rid)
    assert got["TC-001"]["final_category"] == "PRODUCT_BUG"
    assert got["TC-001"]["confirmed_by_human"] is True      # YAML 真值，不是字符串 "True"


def test_load_decisions_accepts_handwritten_list_style(rid):
    """列表式（`- case_id: X`）是 `save_decisions` 降级格式的写法，也是人手写时最自然的写法。

    若只认映射式，PyYAML 装与不装会产出两种互不兼容的文件，人签了字却被静默丢弃。
    """
    d = run_dir(rid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "decisions.yaml").write_text(
        "run_id: R_MERGE_20260915_120000\n\ndecisions:\n"
        "  - case_id: TC-002\n    final_category: PRODUCT_BUG\n"
        "    confirmed_by_human: true\n    decided_by: tester\n",
        encoding="utf-8")
    got = load_decisions(rid)
    assert got["TC-002"]["final_category"] == "PRODUCT_BUG"
    assert got["TC-002"]["confirmed_by_human"] is True


def test_fallback_parser_accepts_both_shapes_and_coerces_bools():
    """无 PyYAML 的机器上仍要能读：`confirmed_by_human` 留在字符串 \"true\" 会让人的定性永远失效。"""
    text = ("run_id: R\ndecided_at: 2026-09-15T12:00:00\ndecisions:\n"
            "  TC-003:\n    final_category: CASE_DEFECT\n    note: 断言写错\n"
            "  TC-004:\n    final_category: ENV_BLOCK\n    confirmed_by_human: false\n")
    got = _parse_decisions_fallback(text)
    assert got["TC-003"]["note"] == "断言写错"
    assert got["TC-004"]["confirmed_by_human"] is False
    assert "run_id" not in got and "decisions" not in got


def test_decisions_roundtrip_without_pyyaml(rid, monkeypatch):
    """真·降级：无 PyYAML 时 `save_decisions` 吐列表式，`load_decisions` 必须读得回来。"""
    import sys
    monkeypatch.setitem(sys.modules, "yaml", None)
    save_decisions(rid, {"TC-005": {"final_category": "PRODUCT_BUG", "confirmed_by_human": True,
                                    "decided_by": "tester"}})
    got = load_decisions(rid)
    assert got["TC-005"]["final_category"] == "PRODUCT_BUG"
    assert got["TC-005"]["confirmed_by_human"] is True


def test_unparseable_decisions_is_logged_not_silently_empty(rid):
    d = run_dir(rid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "decisions.yaml").write_text("这\t不是: [合法的 yaml\n", encoding="utf-8")
    assert load_decisions(rid) == {}
    assert (d / "triage_errors.log").exists()


# ── 分流产物：文件即状态，下一阶段只读文件，中断了也不丢 ──────────────
def test_write_artifacts_produces_handoff_files(rid):
    """待裁决清单/修复清单/quarantine 三件套必须落盘；环境阻塞不进「用例修复清单」。"""
    recs = [_rec("TC-100", triage={"category": "NEEDS_HUMAN", "source": "rule"}),
            _rec("TC-101", triage={"category": "CASE_DEFECT", "source": "rule", "confidence": 0.9,
                                   "suggested_action": "重写断言"}),
            _rec("TC-102", triage={"category": "EXEC_INCOMPLETE", "source": "llm", "confidence": 0.8,
                                   "suggested_action": "补图标定位器"}),
            _rec("TC-103", triage={"category": "ENV_BLOCK", "source": "rule", "confidence": 0.9,
                                   "unblock_hint": "起服务"})]
    merged = merge_decisions(recs, {}, {})
    out = write_artifacts(rid, merged, compute_summary(merged), duplicates=1, malformed=0,
                          mode="report_only")
    for name in ("pending_review", "fix_list", "quarantine"):
        assert out[name].exists() and out[name].read_text(encoding="utf-8").strip()
    text = out["pending_review"].read_text(encoding="utf-8")
    assert "TC-100" in text and "unblock_hint" in text
    fix = out["fix_list"].read_text(encoding="utf-8")
    assert "TC-101" in fix and "TC-102" in fix          # 用例问题与执行未到位都进修复清单
    assert "TC-103" not in fix                          # 环境阻塞不是「用例该修」的东西，进报告 BLOCKED 表
    assert json.loads(out["gate"].read_text(encoding="utf-8"))["mode"] == "report_only"


def test_bug_draft_needs_human_confirm_but_reuses_llm_draft(rid):
    """人只负责拍板定性（含严重程度），草稿正文允许沿用 LLM 写的，否则人还得重打一遍。"""
    recs = [_rec("TC-110", triage={"category": "NEEDS_HUMAN", "source": "rule"}),
            _rec("TC-111", triage={"category": "PRODUCT_BUG", "source": "llm", "confidence": 0.95})]
    recs[0]["module"] = recs[1]["module"] = "分类管理"
    llm = {"TC-110": {"verdict": "PRODUCT_BUG_PROPOSAL", "confidence": 0.9,
                      "rationale": "断言 2 与需求冲突",
                      "bug_draft": {"title": "名称被静默过滤", "expected": "提示不合规",
                                    "req_source": "CAT-04"}}}
    human = {"TC-110": {"final_category": "PRODUCT_BUG", "confirmed_by_human": True,
                        "decided_by": "tester", "severity": "S1", "note": "复现稳定"}}
    merged = merge_decisions(recs, llm, human)
    out = write_artifacts(rid, merged, compute_summary(merged), 0, 0, "strict")
    drafts = sorted((run_dir(rid) / "bug_drafts").glob("*.md"))
    assert len(drafts) == 1                             # TC-111 被铁律拒收 → 不出草稿
    body = drafts[0].read_text(encoding="utf-8")
    assert "名称被静默过滤" in body and "S1" in body and "TC-110" in body and "CAT-04" in body
    assert "人工确认" in body
    assert out["bug_drafts"] == drafts


def test_quarantine_lists_only_overridden_mcp_cases(rid):
    a = _rec("TC-120", triage={"category": "CASE_DEFECT", "source": "human", "confidence": 1.0,
                               "overridden": True, "decided_by": "tester"})
    a["executor"] = "qoder_mcp"
    b = _rec("TC-121", triage={"category": "CASE_DEFECT", "source": "human", "confidence": 1.0,
                               "overridden": True})
    b["executor"] = "playwright_script"
    merged = merge_decisions([a, b], {}, {})
    out = write_artifacts(rid, merged, compute_summary(merged), 0, 0, "strict")
    text = out["quarantine"].read_text(encoding="utf-8")
    assert "TC-120" in text and "TC-121" not in text


def test_write_artifacts_on_clean_run_still_leaves_files(rid):
    """全通过的 run 也要有一整套产物：下游按固定文件名取用，不该判断「这次有没有」。"""
    recs = [_rec("TC-130", status="pass",
                 triage={"category": "OK", "source": "rule", "confidence": 1.0})]
    out = write_artifacts(rid, merge_decisions(recs, {}, {}),
                          compute_summary({"x": recs[0]}), 0, 0, "strict")
    assert out["bug_drafts"] == []
    text = out["pending_review"].read_text(encoding="utf-8")
    assert "TC-130" not in text and "0 项" in text
    assert json.loads(out["gate"].read_text(encoding="utf-8"))["gate"]["verdict"] == "allow"
