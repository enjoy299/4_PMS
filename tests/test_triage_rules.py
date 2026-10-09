"""规则层逐条覆盖 R0-R8。核心是铁律的负向断言：规则层永不产出 PRODUCT_BUG。"""
import copy

from core.triage import run_rule_layer


REC = {
    "run_id": "x", "executor": "playwright_script", "case_id": "TC-001", "name": "n",
    "module": "知识管理", "submodule": "", "priority": "P0", "case_type": "正向",
    "test_point_ref": "", "req_source": "CAT-01",
    "started_at": "2026-09-14T17:00:00", "duration_sec": 1.0, "status": "pass",
    "precondition": "", "precondition_met": None, "test_data": "", "error": "",
    "steps": [], "assertions": [],
    "url_at_failure": "", "screenshots": [], "log_path": "", "console_errors": [],
    "triage": {"category": "", "source": "rule", "confidence": 0.0, "rationale": "",
               "suggested_action": "", "unblock_hint": "", "decided_by": "",
               "decided_at": "", "overridden": False},
    "bug_draft": None, "retry_count": 0, "needs_reconfirm": False,
}
STATUS_ALL = ("pass", "fail", "error", "manual", "blocked", "skipped")


def _rec(**kw):
    r = copy.deepcopy(REC)
    pm = kw.pop("precondition_met", None)
    r.update(kw)
    if pm is not None:
        r["precondition_met"] = pm
    return r


def test_r0_clean_pass_is_ok_not_triaged():
    r = _rec(status="pass",
             steps=[{"order": 1, "action": "点树节点", "outcome": "noop", "detail": "已查看："}],
             assertions=[{"text": "t", "verdict": "pass", "reason": "", "evidence_refs": []}])
    assert run_rule_layer(r)["category"] == "OK"


def test_r1_env_preflight_failed():
    assert run_rule_layer(_rec(status="error"), env_preflight_failed=True)["category"] == "ENV_BLOCK"


def test_r2_error_keywords():
    got = run_rule_layer(_rec(status="error", error="net::ERR_CONNECTION_REFUSED"))
    assert got["category"] == "ENV_BLOCK" and got["confidence"] == 0.9


def test_r3_login_redirect_is_env_block():
    assert run_rule_layer(_rec(status="fail", url_at_failure="http://x/login"))["category"] == "ENV_BLOCK"


def test_r3_excludes_login_module():
    got = run_rule_layer(_rec(status="fail", module="登录", url_at_failure="http://x/login"))
    assert got["category"] != "ENV_BLOCK"


def test_r4_step_not_executed_is_exec_incomplete():
    r = _rec(status="fail", steps=[{"order": 1, "action": "点新建", "outcome": "element_not_found", "detail": ""}])
    assert run_rule_layer(r)["category"] == "EXEC_INCOMPLETE"


def test_r4_skipped_action_also_counts():
    r = _rec(status="fail", steps=[{"order": 2, "action": "点编辑", "outcome": "skipped", "detail": "已执行（通用）"}],
             assertions=[{"text": "t", "verdict": "fail", "reason": "", "evidence_refs": []}])
    assert run_rule_layer(r)["category"] == "EXEC_INCOMPLETE"


def test_r5_all_unverifiable_is_case_defect():
    r = _rec(status="fail", assertions=[
        {"text": "a", "verdict": "unverifiable", "reason": "无法自动验证：缺少可定位目标", "evidence_refs": []}])
    assert run_rule_layer(r)["category"] == "CASE_DEFECT"


def test_r6_precondition_met_false_is_data_precond():
    r = _rec(status="fail", precondition_met=False,
             assertions=[{"text": "a", "verdict": "fail", "reason": "不符", "evidence_refs": []}])
    assert run_rule_layer(r)["category"] == "DATA_PRECOND"


def test_r6_text_keyword_fallback():
    r = _rec(status="manual", error="无法提供：缺少测试数据")
    got = run_rule_layer(r)
    assert got["category"] == "DATA_PRECOND" and got["unblock_hint"]


def test_r7_genuine_failure_goes_to_llm_as_needs_human():
    r = _rec(status="fail", steps=[{"order": 1, "action": "点新建", "outcome": "ok", "detail": ""}],
             assertions=[{"text": "弹窗关闭", "verdict": "fail", "reason": "仍存在", "evidence_refs": []}])
    got = run_rule_layer(r)
    assert got["category"] == "NEEDS_HUMAN" and got["confidence"] == 0.0


def test_r7_allows_unknown_step_outcome():
    """执行者未声明步骤细节（unknown）不应掉进「执行问题」，仍送 LLM。"""
    r = _rec(status="fail", steps=[{"order": 1, "action": "导航", "outcome": "unknown", "detail": ""}],
             assertions=[{"text": "弹窗关闭", "verdict": "fail", "reason": "仍存在", "evidence_refs": []}])
    assert run_rule_layer(r)["category"] == "NEEDS_HUMAN"


def test_r8_mixed_state_is_needs_human():
    r = _rec(status="pass", assertions=[{"text": "a", "verdict": "unverifiable", "reason": "r", "evidence_refs": []}])
    assert run_rule_layer(r)["category"] == "NEEDS_HUMAN"


def test_rule_layer_never_produces_product_bug():
    """铁律负向断言：穷举输入空间，规则层任何分支都不得产出 PRODUCT_BUG。

    `url_at_failure` 必须参与遍历：否则全部组合都被 R3（/login）先命中，
    其余分支一个也测不到，本测试形同虚设。
    """
    for st in STATUS_ALL:
        for out in ("ok", "element_not_found", "skipped", "noop", "unknown"):
            for verd in ("pass", "fail", "unverifiable"):
                for pm in (True, False, None):
                    for url in ("", "http://x/login"):
                        r = _rec(status=st, precondition_met=pm, error="缺少测试数据",
                                 url_at_failure=url,
                                 steps=[{"order": 1, "action": "a", "outcome": out, "detail": ""}],
                                 assertions=[{"text": "t", "verdict": verd,
                                              "reason": "无法自动验证：缺少可定位目标", "evidence_refs": []}])
                        assert run_rule_layer(r)["category"] != "PRODUCT_BUG", \
                            f"铁律被违反 st={st} out={out} v={verd} pm={pm} url={url}"
