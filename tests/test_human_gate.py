"""人工门禁：定性必须出自人、`[q]` 不得成为逃分母的后门、CI 不得阻塞流水线。"""
import copy

import pytest

from core import config
from core.human_confirm import confirm_triage_decisions
from core.triage import evaluate_gate, load_decisions, merge_decisions, new_record, save_decisions


BASE = new_record(run_id="r", case_id="TC-0", module="知识管理")


def _rec(cid, **tri):
    r = copy.deepcopy(BASE)
    r["case_id"] = cid
    r["name"] = f"用例 {cid}"
    r["status"] = "fail"
    r["triage"] = {**r["triage"], **{"category": "NEEDS_HUMAN", "source": "rule",
                                     "confidence": 0.0, "rationale": "R7：疑似真实缺陷",
                                     "suggested_action": "", "unblock_hint": ""}, **tri}
    return r


@pytest.fixture(autouse=True)
def _triage_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRIAGE_DIR", tmp_path / "triage")


def _answers(seq):
    """按顺序弹出预设回答（同时覆盖选项题与自由输入题）。"""
    it = iter(seq)
    return lambda *a, **kw: next(it)


def test_human_can_confirm_product_bug(monkeypatch):
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    monkeypatch.setattr("core.human_confirm._safe_ask", _answers(["bug"]))
    monkeypatch.setattr("core.human_confirm._safe_ask_text", _answers(["S2", "名称被静默过滤"]))
    merged = {"TC-001": _rec("TC-001")}
    decisions = confirm_triage_decisions("r1", merged)
    assert decisions["TC-001"]["final_category"] == "PRODUCT_BUG"
    assert decisions["TC-001"]["confirmed_by_human"] is True
    remerged = merge_decisions(list(merged.values()), {}, decisions)
    assert remerged["TC-001"]["triage"]["category"] == "PRODUCT_BUG"   # 人拍板后铁律放行
    assert remerged["TC-001"]["triage"]["decided_by"]


def test_human_decisions_are_persisted(monkeypatch):
    """返回值不算证据：人工裁决必须落 `decisions.yaml`，否则重跑一次就丢了。"""
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    monkeypatch.setattr("core.human_confirm._safe_ask", _answers(["case"]))
    monkeypatch.setattr("core.human_confirm._safe_ask_text", _answers([""]))
    confirm_triage_decisions("r6", {"TC-006": _rec("TC-006")})
    back = load_decisions("r6")
    assert back["TC-006"]["final_category"] == "CASE_DEFECT"
    assert back["TC-006"]["confirmed_by_human"] is True


def test_ci_mode_never_blocks_but_marks_unconfirmed(monkeypatch):
    monkeypatch.setattr(config, "HUMAN_CONFIRM", False)
    merged = {"TC-002": _rec("TC-002")}
    decisions = confirm_triage_decisions("r2", merged)     # 不得调用任何 input
    assert decisions["TC-002"]["confirmed_by_human"] is False
    remerged = merge_decisions(list(merged.values()), {}, decisions)
    assert remerged["TC-002"]["triage"]["category"] == "NEEDS_HUMAN"
    assert remerged["TC-002"]["needs_reconfirm"] is True
    gate = evaluate_gate(remerged, mode="report_only")
    assert gate["verdict"] == "na" and gate["blocks_exit_code"] is False


def test_quick_accept_cannot_qualify_bug_or_block(monkeypatch):
    """`[q]` 只批量接受 LLM 高置信且非 PRODUCT_BUG/BLOCKED 的项。"""
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    calls = []

    def ask(prompt_text, choices, default):
        calls.append(default)
        return "q" if len(calls) == 1 else default       # 首轮走 [q]，剩余项按默认值逐条走

    monkeypatch.setattr("core.human_confirm._safe_ask", ask)
    monkeypatch.setattr("core.human_confirm._safe_ask_text", lambda *a, **k: "")
    merged = {
        "TC-003": _rec("TC-003", category="CASE_DEFECT", source="llm", confidence=0.9,
                       rationale="铁律：llm 层拒绝定性 PRODUCT_BUG（分流铁律）"),   # 含铁律字样
        "TC-004": _rec("TC-004", category="CASE_DEFECT", source="llm", confidence=0.9,
                       rationale="断言与需求无关，建议重写"),
    }
    decisions = confirm_triage_decisions("r3", merged)
    assert decisions["TC-004"]["final_category"] == "CASE_DEFECT"
    assert "TC-003" not in decisions                      # 铁律拒绝项不得被 q 扫掉，得继续挂待裁决


def test_llm_conclusion_is_reconfirmed_and_overridable(monkeypatch):
    """LLM 改判过的项必须进门禁；人推翻后 `overridden` 才会为 quarantine 提供数据。"""
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    monkeypatch.setattr("core.human_confirm._safe_ask", _answers(["env"]))
    monkeypatch.setattr("core.human_confirm._safe_ask_text", _answers(["重启网关后重跑"]))
    merged = {"TC-009": _rec("TC-009", category="CASE_DEFECT", source="llm", confidence=0.9,
                             rationale="断言与需求无关")}
    decisions = confirm_triage_decisions("r9", merged)
    assert decisions["TC-009"]["final_category"] == "ENV_BLOCK"
    remerged = merge_decisions(list(merged.values()), {}, decisions)["TC-009"]
    assert remerged["triage"]["category"] == "ENV_BLOCK"
    assert remerged["triage"]["overridden"] is True
    assert remerged["triage"]["unblock_hint"] == "重启网关后重跑"


def test_blocked_choice_requires_hint(monkeypatch):
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    monkeypatch.setattr("core.human_confirm._safe_ask", _answers(["skip"]))
    monkeypatch.setattr("core.human_confirm._safe_ask_text", _answers([""]))   # 空 hint
    merged = {"TC-005": _rec("TC-005")}
    decisions = confirm_triage_decisions("r4", merged)
    assert "TC-005" not in decisions                      # 未说明解除路径 → 不收，继续挂待裁决


def test_edit_with_illegal_category_is_not_recorded(monkeypatch):
    """自写结论拼错类别时不得静默当成某一类收下。"""
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    monkeypatch.setattr("core.human_confirm._safe_ask", _answers(["edit"]))
    monkeypatch.setattr("core.human_confirm._safe_ask_text", _answers(["PRODUCT-PENDING"]))
    decisions = confirm_triage_decisions("r7", {"TC-007": _rec("TC-007")})
    assert decisions == {}


def test_no_pending_case_returns_empty(monkeypatch):
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    merged = {"TC-008": _rec("TC-008", category="OK", source="rule", confidence=1.0,
                             rationale="R0：确认通过")}
    assert confirm_triage_decisions("r8", merged) == {}
