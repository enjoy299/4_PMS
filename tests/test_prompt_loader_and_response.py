"""框架健壮性回归：提示词渲染 fail-loud 与响应文件防串轮。

覆盖两个历史缺陷：
  1. agent_loader.load_prompt：缺参时静默返回未替换模板（现改为保留占位符 +
     WARNING 点名）；模板含孤立花括号时 ValueError 崩溃（现改为 ERROR 告警 + 返回原模板）。
  2. core.brain.read_response：重跑同一任务时静默消费上一轮遗留回复
     （现改为消费即归档 `*_response_consumed_*.md`，重跑不再误读）。
"""
import builtins

import pytest

from agents.agent_loader import PROMPTS_DIR, _PLACEHOLDER_RE, load_prompt
from core import brain

_ALL_TEMPLATES = sorted(PROMPTS_DIR.glob("*_prompt.md"))


@pytest.mark.parametrize("prompt_file", _ALL_TEMPLATES,
                         ids=[p.name for p in _ALL_TEMPLATES])
def test_all_prompt_templates_render_with_full_kwargs(prompt_file):
    """遍历全部 *_prompt.md：按模板声明全量填参，断言每个占位符都被真实替换。

    模板出现孤立花括号（语法错误）或占位符被静默丢弃时，本测试即失败。
    """
    agent_name = prompt_file.name[: -len("_prompt.md")]
    template = prompt_file.read_text(encoding="utf-8")
    required = set(_PLACEHOLDER_RE.findall(template))
    kwargs = {k: f"V_{k}" for k in required}

    rendered = load_prompt(agent_name, **kwargs)

    assert rendered, f"{prompt_file.name} 渲染结果为空"
    for key in required:
        assert f"V_{key}" in rendered, f"{prompt_file.name} 的占位符 {{{key}}} 未被替换"


def test_load_prompt_keeps_missing_placeholder_instead_of_silent_fallback():
    """只传部分参数时：已传的被替换、未传的占位符保留原文（不整体弃用模板）。"""
    rendered = load_prompt("design_tp", 模块名="分类管理")

    assert "分类管理" in rendered  # 已传参数正常替换
    assert "{ID前缀}" in rendered  # 未传参数保留原文，可被人工/下游发现
    assert "{拆分需求目录}" in rendered


def test_load_prompt_survives_stray_brace(tmp_path, monkeypatch):
    """模板含孤立花括号时不崩溃：ERROR 告警并返回原模板。"""
    (tmp_path / "bad_prompt.md").write_text("孤立花括号 { 测试", encoding="utf-8")
    monkeypatch.setattr("agents.agent_loader.PROMPTS_DIR", tmp_path)

    result = load_prompt("bad")

    assert result == "孤立花括号 { 测试"  # 不抛异常，原样返回


# 各 load_prompt 调用点的参数快照（与 agents/*.py 中的实参保持同步；
# business/triage 用定向 replace 渲染、excel_export 无代码加载点，不在此列）。
_CALL_SITE_KWARGS = {
    "analyst": dict(归一化需求文件路径="x", 拆分需求目录="y"),
    "design_tp": dict(拆分需求目录="x", 模块或功能="m", 模块编号="02", 模块名="n",
                      ID前缀="p-q", 测试点目录="d", 时间戳="t",
                      需求理解状态="s", 需求理解文件="f", 需求理解输出路径="o"),
    "design_case": dict(拆分需求目录="x", 模块或功能="m", 模块编号="02", 模块名="n",
                        ID前缀="p-q", 测试用例目录="d", 时间戳="t",
                        测试点文件="f", 风险台账文件="l", 需求理解文件="u"),
    "reviewer": dict(需求内容目录="a", 用例设计目录="b", 用例评审目录="c",
                     模块编号="01", 模块名="m"),
    "understanding": dict(拆分需求目录="a", 模块或功能="b", 输出目录="c"),
}


@pytest.mark.parametrize("agent_name", sorted(_CALL_SITE_KWARGS),
                         ids=sorted(_CALL_SITE_KWARGS))
def test_call_sites_provide_all_placeholders(agent_name):
    """调用点参数契约：模板声明的单层占位符必须被 agent 调用点全部传参。

    模板新增占位符而调用点未跟上时（历史缺陷根因），本测试即失败；
    输出示例字段则要求写成 {{{{ }}}} 转义（见 analyst/reviewer 模板）。
    """
    template = (PROMPTS_DIR / f"{agent_name}_prompt.md").read_text(encoding="utf-8")
    required = set(_PLACEHOLDER_RE.findall(template))
    kwargs = _CALL_SITE_KWARGS[agent_name]

    missing = sorted(required - set(kwargs))
    assert not missing, (f"{agent_name} 调用点漏传占位符 {missing}；"
                         f"若为模板输出示例字段，请改为 {{{{ {missing[0]} }}}} 形式转义")

    # 真实渲染路径：断言渲染可正常完成且非空（缺参会保留原文并 WARNING）
    assert load_prompt(agent_name, **kwargs)


def _silent_input(*_args, **_kwargs):
    """模拟 `'' | 脚本` 管道：input 立即 EOF，不阻塞。"""
    raise EOFError


def test_read_response_archives_consumed_file(tmp_path, monkeypatch):
    """文件读取路径：消费后立即归档；同一任务重跑不再读到旧回复（防串轮）。"""
    monkeypatch.setattr(brain, "AI_WORKSPACE_DIR", tmp_path)
    response_file = tmp_path / "demo_response.md"
    response_file.write_text("第一轮回复", encoding="utf-8")

    assert brain.read_response("demo") == "第一轮回复"

    consumed = list(tmp_path.glob("demo_response_consumed_*.md"))
    assert len(consumed) == 1
    assert consumed[0].read_text(encoding="utf-8") == "第一轮回复"
    assert not response_file.exists()

    # 重跑：response 已归档，走终端等待；管道 EOF 立即返回空，不消费旧内容
    monkeypatch.setattr(builtins, "input", _silent_input)
    assert brain.read_response("demo") == ""
    assert len(list(tmp_path.glob("demo_response_consumed_*.md"))) == 1  # 未产生新归档


def test_read_response_paste_also_archives(tmp_path, monkeypatch):
    """终端粘贴路径：内容落盘后同样归档，重跑不串轮。"""
    monkeypatch.setattr(brain, "AI_WORKSPACE_DIR", tmp_path)

    lines = iter(["粘贴的回复", "", ""])
    monkeypatch.setattr(builtins, "input", lambda: next(lines))

    assert brain.read_response("demo") == "粘贴的回复"

    consumed = list(tmp_path.glob("demo_response_consumed_*.md"))
    assert len(consumed) == 1
    assert consumed[0].read_text(encoding="utf-8") == "粘贴的回复"
    assert not (tmp_path / "demo_response.md").exists()


def test_read_response_empty_file_falls_through_to_paste(tmp_path, monkeypatch):
    """空响应文件不算已消费：走终端粘贴路径，文件保留不归档。"""
    monkeypatch.setattr(brain, "AI_WORKSPACE_DIR", tmp_path)
    (tmp_path / "demo_response.md").write_text("   \n", encoding="utf-8")
    monkeypatch.setattr(builtins, "input", _silent_input)

    assert brain.read_response("demo") == ""
    assert (tmp_path / "demo_response.md").exists()
    assert not list(tmp_path.glob("demo_response_consumed_*.md"))
