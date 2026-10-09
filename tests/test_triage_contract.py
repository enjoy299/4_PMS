"""契约读写：字段完整性、枚举合法性、损坏行降级、重复 case_id 去重。"""
import copy
from pathlib import Path

import pytest

from core import config
from core.triage import (
    FINAL_CATEGORIES, STEP_OUTCOMES, new_record, validate_record,
    append_records, load_records, record_from_result, make_run_id,
)


@pytest.fixture
def run_dir(tmp_path, monkeypatch):
    d = tmp_path / "triage" / "知识管理_20260914_173000"
    monkeypatch.setattr(config, "TRIAGE_DIR", d.parent)
    return d.name


def test_new_record_is_complete_and_valid(run_dir):
    rec = new_record(run_id=run_dir, case_id="TC-CAT-001", module="知识管理")
    assert validate_record(rec) == []
    assert rec["triage"]["category"] == ""            # 未经分流 = 空串
    assert rec["precondition_met"] is None            # 三态默认为「未知」


def test_enum_guards_reject_bad_values(run_dir):
    rec = new_record(run_id=run_dir, case_id="TC-001", module="知识管理")
    assert "noop" in STEP_OUTCOMES and "OK" in FINAL_CATEGORIES
    bad = copy.deepcopy(rec)
    bad["steps"] = [{"order": 1, "action": "a", "outcome": "已跳过", "detail": ""}]
    bad["precondition_met"] = "yes"
    bad["assertions"] = [{"text": "t", "verdict": "成功", "reason": "", "evidence_refs": []}]
    bad["triage"]["category"] = "FLAKY"
    errs = validate_record(bad)
    assert "step.outcome 非法:已跳过" in errs
    assert "precondition_met 非三态:yes" in errs
    assert "assertion.verdict 非法:成功" in errs
    assert "category 非法:FLAKY" in errs


def test_record_from_result_maps_assertions_and_precondition(run_dir):
    result = {
        "case_id": "TC-CAT-001", "name": "新建一级分类", "module": "知识管理",
        "status": "manual", "duration_sec": 8.5, "precondition": "已登录",
        "precondition_met": True, "test_data": "分类名：P0测试分类",
        "actual": "未找到：新建分类", "screenshot": ["a.png"], "log": "b.log",
        "steps": [{"order": 1, "action": "点击\"新建分类\"", "outcome": "element_not_found",
                   "detail": "未找到：新建分类"}],
        "assertions": [{"text": "弹窗关闭", "passed": False, "verifiable": False,
                        "reason": "无法自动验证：缺少可定位目标"}],
    }
    rec = record_from_result(result, run_id=run_dir, executor="playwright_script")
    assert validate_record(rec) == []
    assert rec["assertions"][0]["verdict"] == "unverifiable"
    assert rec["precondition_met"] is True


def test_append_and_load_dedupes_by_case_id(run_dir):
    a1 = new_record(run_id=run_dir, case_id="TC-001", module="知识管理", status="fail")
    a2 = new_record(run_id=run_dir, case_id="TC-001", module="知识管理", status="pass")
    append_records([a1, a2, new_record(run_id=run_dir, case_id="TC-002", module="知识管理")], run_dir)
    recs, dup, malformed = load_records(run_dir)
    assert dup == 1 and malformed == 0
    assert len(recs) == 2
    assert {r["case_id"]: r["status"] for r in recs}["TC-001"] == "pass"   # 取最后一条


def test_append_records_downgrades_invalid_and_logs(run_dir, tmp_path):
    bad = new_record(run_id=run_dir, case_id="TC-BAD", module="知识管理")
    bad["status"] = "成功"
    append_records([bad], run_dir)
    recs, _, _ = load_records(run_dir)
    assert recs[0]["triage"]["category"] == "NEEDS_HUMAN"
    assert "status 非法" in recs[0]["triage"]["rationale"]
    assert (tmp_path / "triage" / run_dir / "triage_errors.log").exists()


def test_make_run_id_strips_illegal_chars():
    assert make_run_id("7、知识管理", "20260914_173000") == "7知识管理_20260914_173000"


def test_plan_cases_roundtrip_and_gap(run_dir):
    from core.triage import write_plan_cases, load_plan_cases, diff_plan_vs_records
    write_plan_cases(run_dir, case_ids=["TC-001", "TC-002", "TC-003"],
                     module="知识管理", source_file="output/03_design/test_cases/知识管理/x.md")
    plan = load_plan_cases(run_dir)
    assert plan["case_ids"] == ["TC-001", "TC-002", "TC-003"]
    assert plan["run_id"] == run_dir

    recs = [{"case_id": "TC-001"}, {"case_id": "TC-004"}]
    gap = diff_plan_vs_records(plan, recs)
    assert gap["planned"] == 3 and gap["recorded"] == 1
    assert gap["missing"] == ["TC-002", "TC-003"]     # 计划内但没记录 = 未执行
    assert gap["extra"] == ["TC-004"]                 # 记了但不在计划内 = case_id 写错
    assert diff_plan_vs_records(None, recs)["missing"] == []   # 无 plan_cases 时降级为不报缺口


def test_load_plan_cases_returns_none_when_absent_or_broken(run_dir):
    from core.triage import load_plan_cases
    assert load_plan_cases(run_dir) is None
    p = Path(config.TRIAGE_DIR) / run_dir / "plan_cases.json"
    p.parent.mkdir(parents=True, exist_ok=True)   # 读接口不建目录，写坏样本前自己先建
    p.write_text("{broken", encoding="utf-8")
    assert load_plan_cases(run_dir) is None
