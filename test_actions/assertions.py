"""
技能：断言检查 —— 使用 Playwright 验证页面状态是否符合预期。

改造说明：
  原版本使用 browser-use 的 Tools 装饰器。
  改造后改为普通的 Playwright 函数。
"""
from utils.logger import get_logger

logger = get_logger("skill_assert")


def check_url(page, expected: str) -> str:
    """
    检查当前网址是否包含预期的文字。

    参数：
        page: Playwright 的 Page 对象
        expected: 预期网址中应该包含的文字

    返回：
        检查结果描述
    """
    url = page.url or ""
    if expected in url:
        return f"网址包含 {expected}"
    return f"网址断言失败：预期包含 '{expected}'，实际网址：{url}"


def check_page_errors(page) -> str:
    """
    检查页面是否有错误提示消息（红字、警告、toast 等）。

    参数：
        page: Playwright 的 Page 对象

    返回：
        检查结果描述
    """
    errors = []
    selectors = [".error", ".ant-message-error", ".el-message--error", "[role='alert']"]
    for sel in selectors:
        try:
            elements = page.query_selector_all(sel)
            for el in elements:
                text = el.text_content()
                if text and text.strip():
                    errors.append(text.strip())
        except Exception:
            continue

    if errors:
        return f"发现错误：{'; '.join(errors)}"
    return "页面没有错误提示"
