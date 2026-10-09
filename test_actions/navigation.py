"""
技能：页面导航 —— 使用 Playwright 访问指定页面、点击菜单。

改造说明：
  原版本使用 browser-use 的 Tools 装饰器。
  改造后改为普通的 Playwright 函数。
"""
from core.config import APP_URL
from utils.logger import get_logger

logger = get_logger("skill_nav")


def go_to_page(page, path: str) -> str:
    """
    导航到指定页面。

    参数：
        page: Playwright 的 Page 对象
        path: 页面路径，如 /projectList 或完整网址

    返回：
        操作结果描述
    """
    url = f"{APP_URL}{path}" if path.startswith("/") else path
    try:
        page.goto(url, wait_until="networkidle", timeout=15000)
        return f"已导航到：{url}"
    except Exception as e:
        return f"导航异常：{e}"


def click_menu(page, text: str) -> str:
    """
    点击包含指定文字的菜单或链接。

    参数：
        page: Playwright 的 Page 对象
        text: 菜单中要查找并点击的文字

    返回：
        操作结果描述
    """
    # 按优先级尝试不同的选择器
    selectors = [
        f'a:has-text("{text}")',
        f'button:has-text("{text}")',
        f'span:has-text("{text}")',
        f'div[role="menuitem"]:has-text("{text}")',
        f'text="{text}"',
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                el.click()
                page.wait_for_load_state("networkidle", timeout=10000)
                return f"已点击：{text}"
        except Exception:
            continue
    return f"未找到菜单：{text}"
