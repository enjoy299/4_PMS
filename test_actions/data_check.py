"""
技能：数据校验 —— 使用 Playwright 读取页面上的表格数据和统计数字。

改造说明：
  原版本使用 browser-use 的 Tools 装饰器。
  改造后改为普通的 Playwright 函数。
"""
from utils.logger import get_logger

logger = get_logger("skill_data")


def check_table(page) -> str:
    """
    读取当前页面的表格，返回行数。

    参数：
        page: Playwright 的 Page 对象

    返回：
        表格行数描述
    """
    try:
        tables = page.query_selector_all("table")
        if not tables:
            return "页面上没有表格"
        rows = page.query_selector_all("table tr")
        return f"表格行数：{len(rows)}"
    except Exception as e:
        return f"读取表格失败：{e}"


def read_page_numbers(page) -> str:
    """
    读取页面上显示的统计数字（统计卡片、总数等）。

    参数：
        page: Playwright 的 Page 对象

    返回：
        页面上的数字列表
    """
    numbers = []
    selectors = [".stat-number", ".count", ".total", ".ant-statistic-content-value"]
    for sel in selectors:
        try:
            elements = page.query_selector_all(sel)
            for el in elements:
                text = el.text_content()
                if text and text.strip():
                    numbers.append(text.strip())
        except Exception:
            continue
    return f"页面数字：{', '.join(numbers) or '无'}"
