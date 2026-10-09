"""用例/测试点 ID 新格式（TC-模块名-子模块名-编号）的生成与解析回归。

背景：旧编号 `TC-<模块缩写>-<NNN>`（如 TC-CAT-001）跨模块会撞号（实测全量 151 条中
19 个 case_id 重名）。新格式在编号中自带「模块名-子模块名」段，天然全局唯一；未拆分子
模块时退化为「模块名」（如 TC-首页-001）。本文件锁定三处关键行为：

1. `DesignerAgent._id_prefix`：三段拼接、退化与数字前缀清洗；
2. Tester 用例解析：新格式与历史旧格式可在同一份文件中并存解析；
3. Excel 导出解析：测试点/用例解析器均接受新格式编号。
"""
from agents.designer_agent import DesignerAgent
from agents.excel_export_agent import _parse_test_cases, _parse_test_points
from agents.tester_agent import TesterAgent as _TesterAgent  # 别名：避免 pytest 误收集 Test* 类


# ──────────────────────────────────────────────
#  1. ID 前缀生成（designer_agent）
# ──────────────────────────────────────────────

def test_id_prefix_concats_module_and_submodule():
    """拆分目录下的子模块 → 「模块名-子模块名」。"""
    assert DesignerAgent._id_prefix("知识管理", "分类管理") == "知识管理-分类管理"
    assert DesignerAgent._id_prefix("工业APP", "工业APP维护") == "工业APP-工业APP维护"


def test_id_prefix_degrades_when_no_submodule():
    """未拆分子模块（需求文件在 02 根目录 / 父名与子模块同名）→ 退化为「模块名」。"""
    assert DesignerAgent._id_prefix("02_split_requirements", "首页") == "首页"
    assert DesignerAgent._id_prefix("首页", "首页") == "首页"
    assert DesignerAgent._id_prefix("", "首页") == "首页"


def test_id_prefix_strips_numbering_on_parent():
    """父目录带数字/顿号前缀（如 11、工业APP）时先清洗再拼接。"""
    assert DesignerAgent._id_prefix("11、工业APP", "分类管理") == "工业APP-分类管理"


# ──────────────────────────────────────────────
#  2. Tester 解析：新旧格式共存
# ──────────────────────────────────────────────

_NEW_CASE_MD = """### TC-知识管理-分类管理-001 验证新增分类功能正常

| 字段 | 值 |
|---|---|
| 用例ID | TC-知识管理-分类管理-001 |
| 模块 | 分类管理 |
| 用例标题 | 验证新增分类功能正常 |
| 优先级 | P0 |
| 操作步骤 | 1. 点击[新增]按钮 2. 输入分类名称 |
| 预期结果 | 1. 保存成功 |
"""

_LEGACY_CASE_MD = """### TC-CAT-002 验证旧格式编号仍可解析

| 字段 | 值 |
|---|---|
| 用例ID | TC-CAT-002 |
| 模块 | 分类管理 |
| 用例标题 | 验证旧格式编号仍可解析 |
"""


def test_tester_parser_accepts_new_and_legacy_ids():
    """同一文件（重跑携带旧批 + 本批新增）中新旧编号都能被 ### TC- 分割并解析。"""
    cases = _TesterAgent()._parse_vertical_table_cases(_NEW_CASE_MD + "\n" + _LEGACY_CASE_MD)
    assert [c["id"] for c in cases] == ["TC-知识管理-分类管理-001", "TC-CAT-002"]
    assert cases[0]["name"] == "验证新增分类功能正常"
    assert cases[1]["name"] == "验证旧格式编号仍可解析"


# ──────────────────────────────────────────────
#  3. Excel 导出解析：新旧格式共存
# ──────────────────────────────────────────────

_TP_MD = """| 测试点编号 | 模块 | 需求来源 | 测试维度 | 测试点描述 | 优先级 | 是否依赖确认 | 备注 |
|---|---|---|---|---|---|---|---|
| TP-知识管理-分类管理-001 | 分类管理 | CAT-01 | 正向功能 | 验证新增分类功能正常 | P0 | 否 | - |
| TP-CAT-002 | 分类管理 | CAT-02 | 异常输入 | 旧格式编号仍可解析 | P1 | 否 | - |
"""


def test_excel_parser_accepts_new_and_legacy_ids():
    rows = _parse_test_points(_TP_MD)
    assert [r["测试点编号"] for r in rows] == ["TP-知识管理-分类管理-001", "TP-CAT-002"]

    cases = _parse_test_cases(_NEW_CASE_MD + "\n" + _LEGACY_CASE_MD)
    assert [c["用例ID"] for c in cases] == ["TC-知识管理-分类管理-001", "TC-CAT-002"]


# ──────────────────────────────────────────────
#  4. 提示词渲染：{ID前缀} 不残留（防 KeyError 静默降级）
# ──────────────────────────────────────────────

def test_design_prompts_render_id_prefix_without_leftover():
    """以 designer_agent 的实参渲染双模板：{ID前缀} 必须被替换，且新格式示例可见。"""
    from agents.agent_loader import load_prompt

    tp = load_prompt(
        "design_tp",
        拆分需求目录="output/02_split_requirements/知识管理",
        模块或功能="01-分类管理",
        模块编号="01",
        模块名="分类管理",
        ID前缀="知识管理-分类管理",
        测试点目录="output/03_design/test_points/知识管理",
        时间戳="20260929_1200",
        需求理解状态="已存在",
        需求理解文件="uh.md",
        需求理解输出路径="uh_new.md",
    )
    assert "{ID前缀}" not in tp
    assert "TP-知识管理-分类管理-001" in tp

    case = load_prompt(
        "design_case",
        拆分需求目录="output/02_split_requirements/知识管理",
        模块或功能="01-分类管理",
        模块编号="01",
        模块名="分类管理",
        ID前缀="知识管理-分类管理",
        测试用例目录="output/03_design/test_cases/知识管理",
        时间戳="20260929_1200",
        测试点文件="tp.md",
        风险台账文件="ledger.md",
        需求理解文件="uh.md",
    )
    assert "{ID前缀}" not in case
    assert "TC-知识管理-分类管理-001" in case
