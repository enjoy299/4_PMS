"""qoder-plan「前置样本准备」清单（BLOCKED 歼灭战前置）的汇总与归类回归。

背景：工业APP 实测出现 7 条 BLOCKED，根因集中在「编辑中状态样本 / 多版本样本」
等前置样本缺失——到执行阶段才发现。qoder-plan 现在会从用例前置条件自动汇总
「前置样本准备」清单（去重聚合 + 关键词归类 + 建议动作），执行前先清零。

本文件锁定 `agents/qoder_bridge.py::_collect_precondition_samples` 的关键行为：
1. 空前置跳过、同文本去重聚合、依赖用例合并；
2. 关键词归类（状态样本 / 账号类 / 版本样本 / 可自建 / 默认环境）；
3. 排序：需人工准备 → 可自建 → 默认环境（垫底）。
"""
from agents.qoder_bridge import _collect_precondition_samples


def _case(cid, precondition, test_data=""):
    return {"id": cid, "name": f"用例{cid}", "precondition": precondition, "test_data": test_data}


def test_empty_and_blank_precondition_skipped():
    """无前置条件的用例不产生样本条目（含竖排解析器的“-”占位符）。"""
    assert _collect_precondition_samples([]) == []
    assert _collect_precondition_samples([_case("TC-A-001", ""), _case("TC-A-002", "   ")]) == []
    assert _collect_precondition_samples([_case("TC-A-003", "-")]) == []


def test_duplicate_precondition_merged_with_case_refs():
    """同一前置文本去重为一条，依赖用例合并、计数正确。"""
    samples = _collect_precondition_samples([
        _case("TC-A-001", "已登录，进入工业APP页面"),
        _case("TC-A-002", "已登录，进入工业APP页面"),
    ])
    assert len(samples) == 1
    assert samples[0]["case_count"] == 2
    assert samples[0]["case_ids"] == ["TC-A-001", "TC-A-002"]


def test_status_sample_classified():
    """「编辑中」等状态样本 → 状态样本，需人工准备。"""
    samples = _collect_precondition_samples([
        _case("TC-A-001", "已登录，系统中存在一个「编辑中」状态的工业APP"),
    ])
    assert samples[0]["type"] == "状态样本"
    assert samples[0]["default_env"] is False
    assert samples[0]["self_buildable"] is False


def test_self_buildable_precondition_detected():
    """前置里给出「可先用 TC-xxx 创建」路径 → 可自建，不必人工准备。"""
    samples = _collect_precondition_samples([
        _case("TC-A-001", "已登录，存在一个带描述的分类(可先用 TC-A-003 创建「QD测试分类A」并填描述)"),
    ])
    assert samples[0]["type"] == "可自建"
    assert samples[0]["self_buildable"] is True
    assert samples[0]["default_env"] is False


def test_default_env_precondition_detected():
    """纯登录/导航类前置 → 默认环境（无需额外准备）。"""
    samples = _collect_precondition_samples([
        _case("TC-A-001", "已登录系统，进入工业APP页面(/industrialApp)，左侧分类树已加载"),
    ])
    assert samples[0]["type"] == "默认环境"
    assert samples[0]["default_env"] is True


def test_ordering_manual_then_buildable_then_default():
    """排序：需人工准备 → 可自建 → 默认环境（垫底）。"""
    samples = _collect_precondition_samples([
        _case("TC-A-001", "已登录，进入工业APP页面"),
        _case("TC-A-002", "已登录，系统中存在一个「编辑中」状态的工业APP"),
        _case("TC-A-003", "已登录，存在一个带描述的分类(可先用 TC-A-004 创建)"),
    ])
    assert [s["type"] for s in samples] == ["状态样本", "可自建", "默认环境"]


def test_account_and_version_samples_classified():
    """账号类与版本样本归类。"""
    samples = _collect_precondition_samples([
        _case("TC-A-001", "已登录，另有一个第二账号可用于跨用户验证"),
        _case("TC-A-002", "已登录，存在一个多版本的工业APP（至少2个版本）"),
    ])
    types = {s["type"] for s in samples}
    assert "账号类" in types
    assert "版本样本" in types
