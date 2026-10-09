"""
技能：树形工具栏操作 —— 点击分类树的 5 个图标按钮。

适用场景：
  知识管理、工业APP 等模块的分类树操作按钮。

按钮结构（.tree-toolbar 容器内的 5 个图标按钮）：
  [0] 新建分类 - 文件夹加号图标
  [1] 编辑分类 - 铅笔图标
  [2] 删除分类 - 垃圾桶图标
  [3] 上移     - 上箭头图标
  [4] 下移     - 下箭头图标

注意：这些按钮没有文字标签，只有图标，必须用位置选择器定位。
"""
from utils.logger import get_logger

logger = get_logger("skill_tree_toolbar")


def _get_tree_toolbar_button(page, index: int) -> str:
    """
    点击树形工具栏的第 N 个图标按钮（0-based）。

    参数：
        page: Playwright Page 对象
        index: 按钮索引（0=新建分类, 1=编辑分类, 2=删除分类, 3=上移, 4=下移）

    返回：
        操作结果描述
    """
    button_names = ["新建分类", "编辑分类", "删除分类", "上移", "下移"]
    if index < 0 or index >= len(button_names):
        return f"按钮索引越界：{index}（有效范围 0-4）"

    button_name = button_names[index]

    try:
        # 策略 1：使用 tree-toolbar 容器 + nth-child 定位
        selector = f'.tree-toolbar button:nth-child({index + 1})'
        el = page.query_selector(selector)
        if el:
            el.click()
            page.wait_for_timeout(1000)
            return f"已点击：{button_name}（tree-toolbar 按钮 [{index}]）"

        # 策略 2：使用 tree-btn 类名 + 位置
        selector = f'button.tree-btn:nth-of-type({index + 1})'
        el = page.query_selector(selector)
        if el:
            el.click()
            page.wait_for_timeout(1000)
            return f"已点击：{button_name}（tree-btn [{index}]）"

        # 策略 3：获取所有 tree-btn 按钮，按索引点击
        buttons = page.query_selector_all('button.tree-btn')
        if buttons and index < len(buttons):
            buttons[index].click()
            page.wait_for_timeout(1000)
            return f"已点击：{button_name}（tree-btn 列表 [{index}]）"

        return f"未找到树形工具栏按钮 [{index}]：{button_name}"

    except Exception as e:
        return f"点击 {button_name} 异常：{e}"


def click_new_category(page) -> str:
    """点击"新建分类"按钮（tree-toolbar 第 1 个按钮）。"""
    return _get_tree_toolbar_button(page, 0)


def click_edit_category(page) -> str:
    """点击"编辑分类"按钮（tree-toolbar 第 2 个按钮）。"""
    return _get_tree_toolbar_button(page, 1)


def click_delete_category(page) -> str:
    """点击"删除分类"按钮（tree-toolbar 第 3 个按钮）。"""
    return _get_tree_toolbar_button(page, 2)


def click_move_up(page) -> str:
    """点击"上移"按钮（tree-toolbar 第 4 个按钮）。"""
    return _get_tree_toolbar_button(page, 3)


def click_move_down(page) -> str:
    """点击"下移"按钮（tree-toolbar 第 5 个按钮）。"""
    return _get_tree_toolbar_button(page, 4)
