"""
技能注册中心 —— 汇总所有浏览器操作技能。

改造说明：
  原版本使用 browser-use 的 Tools 注册机制。
  改造后改为简单的函数导入汇总，供测试脚本直接调用。

所有技能函数都接收 Playwright Page 对象作为第一个参数。
"""
from test_actions.auth import login, logout, check_session
from test_actions.navigation import go_to_page, click_menu
from test_actions.form_ops import fill_input, click_button
from test_actions.screenshot import take_evidence_screenshot
from test_actions.assertions import check_url, check_page_errors
from test_actions.data_check import check_table, read_page_numbers
from test_actions.tree_toolbar_ops import (
    click_new_category, click_edit_category, click_delete_category,
    click_move_up, click_move_down
)

# 所有可用的技能函数列表
ALL_SKILLS = {
    "login": login,
    "logout": logout,
    "check_session": check_session,
    "go_to_page": go_to_page,
    "click_menu": click_menu,
    "fill_input": fill_input,
    "click_button": click_button,
    "take_screenshot": take_evidence_screenshot,
    "check_url": check_url,
    "check_page_errors": check_page_errors,
    "check_table": check_table,
    "read_page_numbers": read_page_numbers,
    # 树形工具栏图标按钮
    "click_new_category": click_new_category,
    "click_edit_category": click_edit_category,
    "click_delete_category": click_delete_category,
    "click_move_up": click_move_up,
    "click_move_down": click_move_down,
}
