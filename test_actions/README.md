# test_actions/ — 浏览器操作技能

这个文件夹定义了 AI 操控浏览器时能使用的各种"技能"。每个技能文件包含一组相关的操作，AI 在执行测试时可以调用这些技能来完成具体的浏览器操作。

## 文件说明

| 文件 | 技能类别 | 包含的操作 |
|------|----------|-----------|
| `__init__.py` | 技能注册中心 | 把所有技能合并成一个统一的工具集，供测试智能体使用 |
| `auth.py` | 登录/登出 | `login`（自动填写账号密码登录）、`logout`（退出登录） |
| `navigation.py` | 页面导航 | `go_to_page`（跳转到指定页面）、`click_menu`（点击菜单或链接） |
| `form_ops.py` | 表单操作 | `fill_input`（填写输入框）、`click_button`（点击按钮） |
| `assertions.py` | 断言检查 | `check_url`（检查网址是否正确）、`check_page_errors`（检查页面是否有错误提示） |
| `data_check.py` | 数据校验 | `check_table`（读取表格行数）、`read_page_numbers`（读取页面上的统计数字） |
| `screenshot.py` | 截图取证 | `take_evidence_screenshot`（截取当前页面作为测试证据） |
| `tree_toolbar_ops.py` | 树形工具栏 | `click_new_category`（新建分类）、`click_edit_category`（编辑分类）、`click_delete_category`（删除分类）、`click_move_up`（上移）、`click_move_down`（下移） |
| `README_tree_toolbar.md` | 技能文档 | 树形工具栏技能的详细说明和使用示例 |

## 添加新技能

1. 在本目录创建新文件（如 `pdf_download.py`）
2. 在文件中用 `Tools()` 创建工具集并定义操作函数
3. 在 `__init__.py` 中导入并注册
