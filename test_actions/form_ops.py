"""
技能：表单操作 —— 使用 Playwright 填写输入框、点击按钮。

改造说明：
  原版本使用 browser-use 的 Tools 装饰器。
  改造后改为普通的 Playwright 函数。
"""
from utils.logger import get_logger

logger = get_logger("skill_form")


def fill_input(page, label: str, value: str) -> str:
    """
    填写输入框。

    参数：
        page: Playwright 的 Page 对象
        label: 输入框的标签或占位符文字
        value: 要填写的内容

    返回：
        操作结果描述
    """
    selectors = [
        f'input[placeholder*="{label}"]',
        f'input[aria-label*="{label}"]',
        f'label:has-text("{label}") + input',
        f'label:has-text("{label}") ~ input',
        f'input[name*="{label}"]',
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                el.fill(value)
                return f"已填写 {label}: {value}"
        except Exception:
            continue
    return f"未找到输入框：{label}"


def click_button(page, text: str) -> str:
    """
    点击按钮。

    参数：
        page: Playwright 的 Page 对象
        text: 按钮上显示的文字

    返回：
        操作结果描述
    """
    # 策略 1：精确匹配
    selectors = [
        f'button:has-text("{text}")',
        f'a.btn:has-text("{text}")',
        f'input[type="submit"][value*="{text}"]',
        f'text="{text}"',
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                el.click()
                page.wait_for_load_state("networkidle", timeout=10000)
                return f"已点击按钮：{text}"
        except Exception:
            continue
    
    # 策略 2：部分匹配（如 "新建分类" 匹配 "新建"）
    # 提取关键词（去除"分类"、"知识"等后缀）
    import re
    keywords = re.sub(r'(分类 | 知识 | 文档 | 用户 | 角色 | 权限)$', '', text).strip()
    if keywords and keywords != text:
        partial_selectors = [
            f'button:has-text("{keywords}")',
            f'a.btn:has-text("{keywords}")',
        ]
        for sel in partial_selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    el.click()
                    page.wait_for_load_state("networkidle", timeout=10000)
                    return f"已点击按钮：{text} (匹配: {keywords})"
            except Exception:
                continue
    
    return f"未找到按钮：{text}"
