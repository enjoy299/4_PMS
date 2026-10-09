"""确认列放行门禁（run.py _confirmation_gate）回归测试。

历史缺陷：_lint_confirmations.py 曾无任何代码调用方（纯手工执行），
Quality Gate 不在关键路径上、形同装饰。现接线为：
  - export 硬门禁：FAIL 阻断 exit 1（--force 显式豁免）；
  - testcases / pipeline Step7 软门禁：告警不阻断（草稿先行工作流）。
"""
import scripts._lint_confirmations as lint_mod
import run


class _FakeLint:
    """替身：记录入参并返回预设的未拍板数。"""

    def __init__(self, pending: int):
        self.pending = pending
        self.calls: list[list[str]] = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        return self.pending


def test_gate_pass_returns_true(monkeypatch):
    """pending=0 时放行（blocking=True 也不退出）。"""
    fake = _FakeLint(0)
    monkeypatch.setattr(lint_mod, "main", fake)

    assert run._confirmation_gate(["知识管理"], blocking=True, stage="测试") is True
    assert fake.calls == [["知识管理"]]          # 模块名透传给 lint


def test_gate_blocking_fails_with_exit_code_1(monkeypatch):
    """硬门禁：FAIL 以退出码 1 阻断（CI 可感知）。"""
    monkeypatch.setattr(lint_mod, "main", _FakeLint(3))

    try:
        run._confirmation_gate(None, blocking=True, stage="Excel 导出")
    except SystemExit as e:
        assert e.code == 1
    else:
        raise AssertionError("blocking=True 且 FAIL 时必须 sys.exit(1)")


def test_gate_non_blocking_warns_and_continues(monkeypatch):
    """软门禁：FAIL 只告警，返回 False、不退出。"""
    monkeypatch.setattr(lint_mod, "main", _FakeLint(3))

    assert run._confirmation_gate(None, blocking=False, stage="用例生成前") is False


def test_gate_none_modules_means_autodiscover(monkeypatch):
    """modules=None/[] 时传空列表，由 lint 自动发现全部模块。"""
    fake = _FakeLint(0)
    monkeypatch.setattr(lint_mod, "main", fake)

    assert run._confirmation_gate(None, blocking=False, stage="t") is True
    assert fake.calls == [[]]
