"""
技能：截图取证 —— 使用 Playwright 截取当前页面截图作为测试证据。

改造说明：
  原版本使用 browser-use 的 Tools 装饰器。
  改造后改为普通的 Playwright 函数。
"""
from core.config import SCREENSHOTS_DIR
from datetime import datetime
from utils.logger import get_logger

logger = get_logger("skill_screenshot")


def take_evidence_screenshot(page, desc: str = "evidence") -> str:
    """
    截取当前页面的截图作为测试证据。

    参数：
        page: Playwright 的 Page 对象
        desc: 截图的简短描述

    返回：
        操作结果描述
    """
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = SCREENSHOTS_DIR / f"evidence_{ts}_{desc[:15]}.png"
        page.screenshot(path=str(path))
        logger.info(f"    截图已保存：{path.name}")
        return f"截图已保存：{path.name}"
    except Exception as e:
        return f"截图失败：{e}"
