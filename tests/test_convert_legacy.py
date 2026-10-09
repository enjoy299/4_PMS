"""契约回归样本：真实历史产物 `test_result_P0_km_20260907.json` 转换 + 过规则层。

断言的是 spec §9.2 的期望：两条已记录的 Bug 不得被判成环境/执行问题，必须走 R7 送 LLM；
未执行的 pending_cases 按 blocker 文本分流，且写盘后重读无损。
"""
import importlib.util
from pathlib import Path

import pytest

from core import config
from core.triage import (apply_rule_layer, append_records, compute_summary, load_records,
                         merge_decisions, to_result_rows)

REPO = Path(__file__).resolve().parents[1]
LEGACY = REPO / "qoder_workspace" / "test_result_P0_km_20260907.json"


def _load_converter():
    spec = importlib.util.spec_from_file_location(
        "_convert_legacy_result", REPO / "scripts" / "_convert_legacy_result.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def converted(tmp_path, monkeypatch):
    mod = _load_converter()
    monkeypatch.setattr(config, "TRIAGE_DIR", tmp_path / "triage")
    records, run_id = mod.convert(LEGACY)
    return records, run_id


def test_legacy_shape_preserved(converted):
    records, run_id = converted
    assert run_id == "P0_km_20260907"
    assert len(records) == 12                       # 1 条已执行 + 11 条 pending
    assert all(r["executor"] == "qoder_mcp" for r in records)


def test_no_account_name_leaks_into_records(converted):
    """凭据不落盘这条规则同样管住转换器：`meta.test_account` 不得被抄进 `precondition`。"""
    records, _ = converted
    assert all("zgn" not in r["precondition"] for r in records)


def test_executed_case_goes_to_rule_r7_not_env_or_exec(converted):
    records, _ = converted
    case = next(r for r in records if r["case_id"] == "TC-CAT-001")
    assert case["status"] == "fail"
    assert all(s["outcome"] == "ok" for s in case["steps"])    # SUSPECT 步骤仍是「做了」
    assert any(a["verdict"] == "fail" for a in case["assertions"])
    apply_rule_layer([case])
    assert case["triage"]["category"] == "NEEDS_HUMAN"
    assert "R7" in case["triage"]["rationale"]                   # 送 LLM，不冒充定性
    assert case["bug_draft"]["id"] == "BUG-CAT-01"              # 旧 Bug 草稿不丢


def test_pending_cases_split_by_blocker_text(converted):
    records, _ = converted
    apply_rule_layer(records)
    cats = {r["case_id"]: r["triage"]["category"] for r in records}
    assert cats["TC-KM-001"] == "DATA_PRECOND"       # 本地路径未准备
    assert cats["TC-CAT-014"] == "DATA_PRECOND"      # 需要先造空分类
    assert cats["TC-KM-002"] == "DATA_PRECOND"       # 依赖 TC-KM-001（含空格写法）
    assert cats["TC-CAT-002"] == "DATA_PRECOND"      # 前置数据无法保证
    assert cats["TC-CAT-018"] == "NEEDS_HUMAN"       # blocker 写「无」，不得塞进阻塞逃分母
    blocked = [r for r in records if r["status"] == "blocked"]
    assert len(blocked) == 11
    # 历史 pending 没人验证过前置：转换器只能写「未知」（写 False 会被 R6 主判据全部塞进数据前置桶）
    assert all(r["precondition_met"] is None for r in blocked)


def test_blocker_text_survives_as_unblock_hint(converted):
    """规则层不得用通用文案擦掉 blocker 自带的解除路径——报告里 BLOCKED 独立表靠它。"""
    records, _ = converted
    apply_rule_layer(records)
    km2 = next(r for r in records if r["case_id"] == "TC-KM-002")
    assert "TC-KM-001" in km2["triage"]["unblock_hint"]


def test_summary_buckets_sum_equals_total(converted):
    records, _ = converted
    apply_rule_layer(records)
    s = compute_summary(merge_decisions(records, {}, {}))
    assert s["总用例"] == 12
    assert s["总用例"] == sum(v for k, v in s.items()
                            if k not in ("总用例", "通过率", "有效通过率", "移出分母"))
    assert s["数据前置未满足"] == 5 and s["待人工裁决"] == 7
    assert s["环境阻塞"] == 0 and s["真实缺陷"] == 0        # 铁律：自动层不得定性 PRODUCT_BUG


def test_written_jsonl_reload_is_lossless(converted, tmp_path, monkeypatch):
    records, run_id = converted
    monkeypatch.setattr(config, "TRIAGE_DIR", tmp_path / "triage")
    append_records(records, run_id)
    reloaded, dup, malformed = load_records(run_id)
    assert dup == 0 and malformed == 0 and len(reloaded) == 12


def test_to_result_rows_feeds_legacy_reporter(converted):
    records, _ = converted
    rows = to_result_rows(records)
    assert rows[0]["id"] == "TC-CAT-001"
    assert rows[0]["status"] in ("pass", "fail", "error", "manual", "blocked", "skipped")
    assert isinstance(rows[0]["assertions"], list) and rows[0]["assertions"][0]["passed"] is True
    assert "→" in rows[0]["steps"]
