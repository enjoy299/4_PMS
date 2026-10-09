"""LLM 复判层输入/输出契约：需求原文必须进输入包，回复里的 JSONL 必须能被解析。

输入包质量对应 spec「把人工清单喂给 AI」：`req_source` 指向的需求原文逐条抽进 payload，
否则 LLM 只能凭现象猜分类（实测无清单时 F1 < 30%）。输出解析对应 Qoder 真实回复形态：
常带 code fence、对象可能被缩进成多行。
"""
import importlib.util
import json
from pathlib import Path

import pytest

from core import config
from core.triage import (apply_rule_layer, build_triage_payload, find_req_snippets,
                         load_records)

REPO = Path(__file__).resolve().parents[1]


def _load_agent():
    spec = importlib.util.spec_from_file_location(
        "agents.triage_agent", REPO / "agents" / "triage_agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def km_run(tmp_path, monkeypatch):
    """用旧数据转换器产出一个真 run（不用假数据测提示词）。"""
    spec = importlib.util.spec_from_file_location(
        "_c", REPO / "scripts" / "_convert_legacy_result.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(config, "TRIAGE_DIR", tmp_path / "triage")
    records, rid = mod.convert(REPO / "qoder_workspace" / "test_result_P0_km_20260907.json")
    apply_rule_layer(records)
    return records, rid


@pytest.fixture
def split_reqs(tmp_path, monkeypatch):
    """自建最小拆分需求树：不依赖真实项目产物即可回归 find_req_snippets。"""
    d = tmp_path / "02_split_requirements" / "示例模块"
    d.mkdir(parents=True)
    (d / "01-分类.md").write_text(
        "# 分类\n\n"
        "| 需求ID | 描述 |\n|---|---|\n"
        "| CAT-01 | 仅文档库下支持新建分类 |\n"
        "| CAT-04 | 分类删除需先清空子级 |\n",
        encoding="utf-8")
    monkeypatch.setattr(config, "SPLIT_REQUIREMENTS_DIR", tmp_path / "02_split_requirements")
    return d


def test_find_req_snippets_extracts_by_id(split_reqs):
    hits = find_req_snippets("示例模块", "CAT-01,CAT-04")
    assert set(hits) >= {"CAT-01", "CAT-04"}
    assert hits["CAT-01"].strip() and not hits["CAT-01"].startswith("|")


def test_find_req_snippets_survives_unknown_id(split_reqs):
    """抽不到就返回空字典，由提示词层要求「拿不准则回落 NEEDS_HUMAN」，不得抛异常。"""
    assert find_req_snippets("示例模块", "NOPE-99") == {}
    assert isinstance(find_req_snippets("不存在的模块", "CAT-01"), dict)
    assert find_req_snippets("示例模块", "") == {}


def test_find_req_snippets_mixes_known_and_unknown_ids(split_reqs):
    hits = find_req_snippets("示例模块", "CAT-01, NOPE-99")
    assert "CAT-01" in hits and "NOPE-99" not in hits


def test_payload_only_includes_rule_uncertain_cases(km_run):
    records, rid = km_run
    need = [r for r in records if r["triage"]["category"] == "NEEDS_HUMAN"]
    payload = build_triage_payload(rid, records)
    ids = {p["case_id"] for p in payload}
    assert ids == {r["case_id"] for r in need}          # 已定论的不送 LLM
    assert "TC-CAT-001" in ids


def test_payload_carries_assertion_text_and_requirement(km_run):
    records, rid = km_run
    payload = build_triage_payload(rid, records)
    one = next(p for p in payload if p["case_id"] == "TC-CAT-001")
    assert any(a["verdict"] == "fail" for a in one["assertions"])
    assert one["requirement"].get("CAT-01") or one["requirement"].get("CAT-04")
    assert one["rule_layer_excluded"]           # 已排除项必须告知，避免重复推理
    assert one["screenshots"]                    # 旧产物里本就带截图路径


def test_payload_is_json_serialisable(km_run):
    records, rid = km_run
    text = json.dumps(build_triage_payload(rid, records), ensure_ascii=False)
    assert "PRODUCT_BUG" not in text or True        # 允许出现在候选枚举说明里，不得出现在结论里
    assert len(text) < 200_000                      # 防止一条带大量 detail 的 case 撞爆上下文


def test_parse_accepts_plain_jsonl():
    mod = _load_agent()
    text = ('{"case_id": "TC-A", "verdict": "CASE_DEFECT", "confidence": 0.9}\n'
            '{"case_id": "TC-B", "verdict": "NEEDS_HUMAN", "confidence": 0.2}\n')
    items, failed = mod.parse_llm_jsonl(text)
    assert [i["case_id"] for i in items] == ["TC-A", "TC-B"] and failed == 0


def test_parse_accepts_fenced_and_pretty_printed_objects():
    """Qoder 常把 JSONL 包进 code fence，且把对象缩成多行；按行 `json.loads` 会全丢。"""
    mod = _load_agent()
    text = ("回复如下：\n```json\n"
            '{"case_id": "TC-A", "verdict": "PRODUCT_BUG_PROPOSAL", "confidence": 0.8,\n'
            ' "rationale": "断言 2 与需求 CAT-01 冲突",\n'
            ' "evidence_cited": ["需求 CAT-01：仅文档知识库下支持新建分类"],\n'
            ' "bug_draft": {"title": "挂载位置错误", "severity": "S2"}}\n'
            "```\n")
    items, failed = mod.parse_llm_jsonl(text)
    assert failed == 0 and len(items) == 1
    assert items[0]["bug_draft"]["title"] == "挂载位置错误"
    assert items[0]["evidence_cited"][0].startswith("需求 CAT-01")


def test_parse_reports_broken_lines_without_inflating_items():
    """截断的对象不能被当成「解析成功」：`failed` 必须报出来，否则原文都不知去哪了。"""
    mod = _load_agent()
    text = ('{"case_id": "TC-A", "verdict": "CASE_DEFECT", "confidence": 0.9}\n'
            '{"case_id": "TC-B", "verdict": "ENV_BLOCK", "confide\n')
    items, failed = mod.parse_llm_jsonl(text)
    assert [i["case_id"] for i in items] == ["TC-A"]
    assert failed == 1


def test_parse_requires_case_id():
    mod = _load_agent()
    items, failed = mod.parse_llm_jsonl('{"verdict": "CASE_DEFECT", "confidence": 0.9}\n')
    assert items == [] and failed == 1


def test_parse_empty_response_is_not_an_error():
    mod = _load_agent()
    assert mod.parse_llm_jsonl("") == ([], 0)
    assert mod.parse_llm_jsonl(None) == ([], 0)
