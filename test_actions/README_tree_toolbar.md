# 树形工具栏操作技能

## 功能

提供分类树形工具栏的 5 个图标按钮操作。

## 适用模块

- 知识管理
- 工业APP
- 其他使用相同树形结构的模块

## 按钮结构

```
.tree-toolbar 容器内的 5 个图标按钮（无文字标签）：

┌─────────────────────────────────────┐
│  [📁+]  [✏️]  [🗑️]  [↑]  [↓]      │
│   新建  编辑  删除  上移  下移       │
└─────────────────────────────────────
```

| 索引 | 功能 | 方法 | 选择器 |
|------|------|------|--------|
| 0 | 新建分类 | `click_new_category()` | `.tree-toolbar button:nth-child(1)` |
| 1 | 编辑分类 | `click_edit_category()` | `.tree-toolbar button:nth-child(2)` |
| 2 | 删除分类 | `click_delete_category()` | `.tree-toolbar button:nth-child(3)` |
| 3 | 上移 | `click_move_up()` | `.tree-toolbar button:nth-child(4)` |
| 4 | 下移 | `click_move_down()` | `.tree-toolbar button:nth-child(5)` |

## 使用方法

### 在测试脚本中直接调用

```python
from test_actions import ALL_SKILLS

# 点击"新建分类"按钮
result = ALL_SKILLS["click_new_category"](page)

# 点击"编辑分类"按钮
result = ALL_SKILLS["click_edit_category"](page)

# 点击"删除分类"按钮
result = ALL_SKILLS["click_delete_category"](page)

# 点击"上移"按钮
result = ALL_SKILLS["click_move_up"](page)

# 点击"下移"按钮
result = ALL_SKILLS["click_move_down"](page)
```

### 在测试用例步骤中自动识别

测试用例步骤包含以下关键词时会自动调用对应技能：

- `点击"新建分类"` → `click_new_category()`
- `点击"编辑分类"` → `click_edit_category()`
- `点击"删除分类"` → `click_delete_category()`
- `点击"上移"` → `click_move_up()`
- `点击"下移"` → `click_move_down()`

## 注意事项

1. **按钮无文字标签**：这些按钮只有图标，不能用 `button:has-text("新建分类")` 定位
2. **必须用位置选择器**：使用 `.tree-toolbar button:nth-child(N)` 定位
3. **区分两个工具栏**：
   - `.tree-toolbar`：左侧分类操作按钮（5 个图标按钮）
   - `.toolbar`：右侧知识操作按钮（新建、删除、入库等文字按钮）
4. **点击前需选中树节点**：编辑、删除、上移、下移操作需要先选中一个分类节点

## 扩展示例

如果其他模块有类似的树形工具栏但按钮数量不同，可以继承此技能并修改按钮数量：

```python
from test_actions.tree_toolbar_ops import _get_tree_toolbar_button

def click_custom_button(page, index: int) -> str:
    """点击自定义树形工具栏按钮。"""
    return _get_tree_toolbar_button(page, index)
```
