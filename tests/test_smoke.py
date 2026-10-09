"""骨架冒烟：验证仓库根可被 import、分流配置可读。"""
from core import config


def test_triage_config_defaults():
    assert config.TRIAGE_ENABLED is False
    assert config.TRIAGE_DIR.name == "triage"
    assert 0.0 < config.TRIAGE_CONF_THRESHOLD <= 1.0
    assert config.TRIAGE_DIR.exists()
