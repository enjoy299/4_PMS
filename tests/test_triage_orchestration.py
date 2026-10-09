# -*- coding: utf-8 -*-
"""编排：records → 规则层 →（LLM）→ 产物 →（人工门禁）→ 重合并 → 报告 → 门禁退出码。"""
import sys

import pytest

from core import config
from core.triage import append_records, list_runs, new_record, save_decisions


def _rec(rid, cid, **kw):
    r = new_record(run_id=rid, case_id=cid, module="知识管理")
    r["name"] = kw.pop("name", f"用例{cid}")
    r["status"] = kw.pop("status", "fail")
    tri = kw.pop("triage", None)
    if tri is not None:
        r["triage"].update(tri)
    r.update(kw)
    return r


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRIAGE_DIR", tmp_path / "triage")
    monkeypatch.setattr(config, "MD_REPORTS_DIR", tmp_path / "md")
    monkeypatch.setattr(config, "HTML_REPORTS_DIR", tmp_path / "html")
    monkeypatch.setattr(config, "EXCEL_REPORTS_DIR", tmp_path / "xlsx")
    monkeypatch.setattr(config, "REPORT_FORMAT", ["md"])
    monkeypatch.setattr(config, "HUMAN_CONFIRM", False)     # 默认非交互，测试不卡 stdin
    return tmp_path


def _seed(rid="R1"):
    """1 条 OK + 1 条 R7（步骤到位、可验证断言失败）→ 待人工裁决。"""
    append_records([
        _rec(rid, "TC-001", status="pass",
             steps=[{"order": 1, "action": "点击新建", "outcome": "ok", "detail": ""}],
             assertions=[{"text": "弹窗关闭", "verdict": "pass", "reason": "", "evidence_refs": []}]),
        _rec(rid, "TC-004", status="fail",
             assertions=[{"text": "分类树出现新分类", "verdict": "fail", "reason": "",
                          "evidence_refs": []}]),
    ], rid)
    return rid


def test_list_runs_skips_empty_dirs_and_puts_newest_first(env):
    _seed("B_20260910_101010")
    (env / "triage" / "empty_run").mkdir(parents=True)                  # 只有产物不算 run
    _seed("A_20260912_101010")                                          # 后写 → 排在前
    runs = list_runs()
    assert runs[0] == "A_20260912_101010" and "B_20260910_101010" in runs
    assert "empty_run" not in runs


def test_pipeline_writes_artifacts_and_report(env):
    from agents.triage_agent import triage_pipeline
    out = triage_pipeline(_seed(), do_llm=False, make_report=True)
    assert out["error"] == ""
    assert out["summary"]["总用例"] == 2 and out["summary"]["待人工裁决"] == 1
    assert out["gate"]["verdict"] == "na"                    # HUMAN_CONFIRM=False → report_only
    assert not out["gate"]["blocks_exit_code"]               # CI 不得假阻塞流水线
    assert (env / "triage" / "R1" / "pending_review.md").exists()
    assert (env / "triage" / "R1" / "gate.json").exists()
    assert list((env / "md").rglob("*.md"))                  # 报告已生成（落在 格式/模块/ 子目录）


def test_pipeline_skips_llm_by_default_and_runs_on_request(env, monkeypatch):
    from agents import triage_agent
    calls = []
    monkeypatch.setattr(triage_agent.TriageAgent, "review",
                        lambda self, rid, dry_run=False: (calls.append(rid),
                                                          {"reviewed": 0, "parsed": 0,
                                                           "raw_failed": 0, "prompt_path": ""})[1])
    triage_agent.triage_pipeline(_seed("R2"), do_llm=False)
    assert calls == []
    triage_agent.triage_pipeline("R2", do_llm=True)
    assert calls == ["R2"]


def test_pipeline_remerges_after_human_gate(env, monkeypatch):
    """人工拍板后必须重跑合并：否则 `decisions.yaml` 写了却不进摘要与门禁。"""
    from agents import triage_agent

    def fake_gate(rid, merged):
        assert merged["TC-004"]["triage"]["category"] == "NEEDS_HUMAN"
        dec = {"TC-004": {"final_category": "PRODUCT_BUG", "confirmed_by_human": True,
                          "decided_by": "tester", "note": "确认缺陷", "decided_at": "2026-09-14T18:00:00",
                          "bug_draft": {"title": "分类未新增", "severity": "S2"}}}
        save_decisions(rid, dec)
        return dec

    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    monkeypatch.setattr("core.human_confirm.confirm_triage_decisions", fake_gate)
    out = triage_agent.triage_pipeline(_seed("R3"), make_report=False)
    assert out["summary"]["真实缺陷"] == 1 and out["summary"]["待人工裁决"] == 0
    assert out["gate"]["verdict"] == "allow"
    assert list((env / "triage" / "R3" / "bug_drafts").glob("*.md"))


def test_pipeline_on_missing_run_reports_clearly(env):
    from agents.triage_agent import triage_pipeline
    out = triage_pipeline("missing")
    assert "records.jsonl" in out["error"] and out["report"] is None
    assert out["summary"] == {}


def test_validate_flag_reports_missing_cases_and_exits_nonzero(env, monkeypatch, capsys):
    """缺口存在（计划 2 条只记录 1 条）时，--validate 必须指出来并不给退出码 0。"""
    from run import cmd_triage          # 函数内导入：CLI 不在收集期拉起来
    from core.triage import write_plan_cases
    write_plan_cases("R1", ["TC-001", "TC-002"], module="知识管理")
    append_records([_rec("R1", "TC-001")], "R1")
    monkeypatch.setattr(sys, "argv", ["run.py", "triage", "R1", "--validate"])
    with pytest.raises(SystemExit) as e:
        cmd_triage()
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert "TC-002" in out and "缺口 1" in out


def test_validate_flag_passes_when_complete(env, monkeypatch, capsys):
    from run import cmd_triage
    from core.triage import write_plan_cases
    write_plan_cases("R1", ["TC-001"], module="知识管理")
    append_records([_rec("R1", "TC-001")], "R1")
    monkeypatch.setattr(sys, "argv", ["run.py", "triage", "R1", "--validate"])
    with pytest.raises(SystemExit) as e:
        cmd_triage()
    assert e.value.code == 0


def test_pipeline_leaves_terminal_summary_to_the_cli(env, capsys):
    """终端摘要只打一份：报告层再另外打一屏，同一屏数字就会重复。"""
    from agents.triage_agent import triage_pipeline
    triage_pipeline(_seed(), make_report=True)
    assert "发版建议" not in capsys.readouterr().out


@pytest.mark.parametrize("argv,expect", [
    (["run.py", "triage", "not_a_run"], "无有效记录"),
    (["run.py", "triage", "R1", "--validate"], "校验不通过"),
])
def test_cli_output_survives_chinese_console(env, monkeypatch, argv, expect):
    """中文 Windows 控制台是 cp936：打一行就 UnicodeEncodeError 会把退出码与原因一起吞掉。

    `✓ ✗ ✅ ❌ ⚠` 都不在 GBK 里，状态标记只能靠 rich 颜色与文字表达。
    """
    import io
    import run as cli
    from rich.console import Console
    from core.triage import write_plan_cases

    buf = io.BytesIO()
    stream = io.TextIOWrapper(buf, encoding="gbk", errors="strict")
    monkeypatch.setattr(cli, "console", Console(file=stream, width=200))
    write_plan_cases("R1", ["TC-001", "TC-002"], module="知识管理")
    append_records([_rec("R1", "TC-001")], "R1")
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        cli.cmd_triage()
    stream.flush()
    assert expect in buf.getvalue().decode("gbk")
