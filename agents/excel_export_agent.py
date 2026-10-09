"""
Excel 导出智能体 —— 流水线第 4 步：将评审通过的测试点和测试用例导出为 Excel 格式。

工作流程：
  1. 读取测试点文件（output/03_design/*-测试点.md）
  2. 读取用例设计文件（output/03_design/*-用例.md）
  3. 读取评审报告（output/04_review/）
  4. 根据评审结果过滤
  5. 生成合并 Excel 文件（output/05_export/）：测试点+用例 合并在一个 xlsx（两个 Sheet）
"""
import re
from pathlib import Path
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from agents.agent_loader import load_prompt
from core.config import (
    DESIGN_WORKSPACE_DIR, REVIEW_DIR, FINAL_CASES_DIR,
    TESTPOINTS_DIR, CASES_DIR, SPEC_DIR,
    get_module_dir, find_module_file,
)
from core.brain import save_prompt, read_response
from utils.logger import get_logger

logger = get_logger("excel_export")


# ──────────────────────────────────────────────
#  Markdown 解析工具函数
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
#  字段名标准化映射（容错：AI 可能输出的变体列名）
# ──────────────────────────────────────────────

_TP_FIELD_ALIASES = {
    "测试点编号": "测试点编号",
    "编号": "测试点编号",
    "测试点ID": "测试点编号",
    "ID": "测试点编号",
    "模块": "模块",
    "子模块": "模块",
    "功能模块": "模块",
    "需求来源": "需求来源",
    "需求编号": "需求来源",
    "需求引用": "需求来源",
    "关联需求": "需求来源",
    "测试维度": "测试维度",
    "维度": "测试维度",
    "测试类型": "测试维度",
    "测试点描述": "测试点描述",
    "描述": "测试点描述",
    "测试内容": "测试点描述",
    "测试目标": "测试点描述",
    "优先级": "优先级",
    "是否依赖确认": "是否依赖确认",
    "依赖确认": "是否依赖确认",
    "待确认": "是否依赖确认",
    "是否待确认": "是否依赖确认",
    "备注": "备注",
    "说明": "备注",
}

_CASE_FIELD_ALIASES = {
    "用例 ID": "用例ID",
    "用例ID": "用例ID",
    "用例编号": "用例ID",
    "ID": "用例ID",
    "编号": "用例ID",
    "用例标题": "用例标题",
    "标题": "用例标题",
    "模块": "模块",
    "子模块": "模块",
    "功能模块": "模块",
    "需求来源": "需求来源",
    "需求编号": "需求来源",
    "关联需求": "需求来源",
    "测试点 ID": "测试点ID",
    "测试点ID": "测试点ID",
    "测试点编号": "测试点ID",
    "关联测试点": "测试点ID",
    "优先级": "优先级",
    "用例类型": "用例类型",
    "类型": "用例类型",
    "前置条件": "前置条件",
    "前提条件": "前置条件",
    "前置": "前置条件",
    "测试步骤": "操作步骤",
    "操作步骤": "操作步骤",
    "步骤": "操作步骤",
    "测试数据": "测试数据",
    "数据": "测试数据",
    "预期结果": "预期结果",
    "期望结果": "预期结果",
    "预期": "预期结果",
    "清理动作": "清理动作",
    "清理": "清理动作",
    "后置操作": "清理动作",
    "备注": "备注",
    "说明": "备注",
}

# 允许值标准化
_VALID_DIMENSIONS = {"正向功能", "异常输入", "边界值", "状态流转", "权限控制"}
_VALID_PRIORITIES = {"P0", "P1", "P2"}
_VALID_CASE_TYPES = {"正向", "异常", "边界", "权限", "状态", "配置", "数据一致性"}


def _normalize_value(field: str, val: str) -> str:
    """标准化字段值，修正常见偏差。"""
    val = val.strip()
    if field == "测试维度":
        # 尝试匹配允许值
        for allowed in _VALID_DIMENSIONS:
            if allowed in val:
                return allowed
    elif field == "优先级":
        for allowed in _VALID_PRIORITIES:
            if allowed in val.upper():
                return allowed
    elif field == "用例类型":
        for allowed in _VALID_CASE_TYPES:
            if allowed in val:
                return allowed
    elif field == "是否依赖确认":
        if "是" in val:
            return "是"
        if "否" in val:
            return "否"
    return val


def _parse_test_points(md_text: str) -> list[dict]:
    """从 Markdown 解析测试点表格，返回字段列表。

    支持三种格式：
    - 新格式（8列）：测试点编号 | 模块 | 需求来源 | 测试维度 | 测试点描述 | 优先级 | 是否依赖确认 | 备注
    - 旧格式（3列）：测试点编号 | 描述 | 优先级
    - 表头容错：通过字段名别名自动识别列
    """
    rows = []
    header_cols = None  # 表头列映射
    is_new_format = False
    warned = False

    for line in md_text.splitlines():
        line = line.strip()

        # 检测表头行
        if line.startswith("|") and "测试点编号" in line:
            is_new_format = True
            # 解析表头列名，建立列索引 → 标准字段名 的映射
            raw_cols = [c.strip() for c in line.split("|")[1:-1]]
            header_cols = []
            for col_name in raw_cols:
                std_name = _TP_FIELD_ALIASES.get(col_name)
                if std_name is None:
                    # 模糊匹配
                    for alias, std in _TP_FIELD_ALIASES.items():
                        if alias in col_name or col_name in alias:
                            std_name = std
                            break
                header_cols.append(std_name)  # 未识别的列为 None
            continue

        # 跳过分隔行
        if line.startswith("|---") or line.startswith("|-"):
            continue

        if line.startswith("|") and "TP-" in line:
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 3 and cells[0].startswith("TP-"):
                if is_new_format and header_cols and len(cells) >= len(header_cols):
                    # 新格式：按表头映射列
                    row = {
                        "测试点编号": "", "模块": "", "需求来源": "-",
                        "测试维度": "正向功能", "测试点描述": "",
                        "优先级": "P1", "是否依赖确认": "否", "备注": "-",
                    }
                    for idx, std_name in enumerate(header_cols):
                        if std_name and idx < len(cells):
                            row[std_name] = _normalize_value(std_name, cells[idx])
                    # 校验必填字段
                    if not row["测试点编号"]:
                        row["测试点编号"] = cells[0]
                    if not row["测试点描述"] and len(cells) > 4:
                        row["测试点描述"] = cells[4]
                    rows.append(row)
                elif is_new_format and len(cells) >= 8:
                    # 回退：按位置映射 8 列
                    rows.append({
                        "测试点编号": cells[0],
                        "模块": cells[1],
                        "需求来源": cells[2],
                        "测试维度": _normalize_value("测试维度", cells[3]),
                        "测试点描述": cells[4],
                        "优先级": _normalize_value("优先级", cells[5]),
                        "是否依赖确认": _normalize_value("是否依赖确认", cells[6]),
                        "备注": cells[7] if len(cells) > 7 else "-",
                    })
                else:
                    # 旧格式：3列（编号 | 描述 | 优先级）
                    rows.append({
                        "测试点编号": cells[0],
                        "模块": "测试点清单",
                        "需求来源": "-",
                        "测试维度": "正向功能",
                        "测试点描述": cells[1],
                        "优先级": _normalize_value("优先级", cells[2]),
                        "是否依赖确认": "否",
                        "备注": "-",
                    })

    if not warned and rows:
        # 输出解析统计日志
        logger.info(f"  测试点解析完成：{len(rows)} 条")
    return rows


def _parse_test_cases(md_text: str) -> list[dict]:
    """从 Markdown 解析测试用例，返回字段列表。

    容错能力：
    - 支持字段名别名自动识别（如"测试步骤"→"操作步骤"、"子模块"→"模块"）
    - 自动标准化允许值（如"异常"→"异常"、"p0"→"P0"）
    - 缺失字段自动填充默认值
    """
    cases: list[dict] = []
    current: dict | None = None

    for line in md_text.splitlines():
        ls = line.strip()
        if ls.startswith("### TC-"):
            if current:
                cases.append(current)
            m = re.match(r"### (TC-\S+)\s+(.*)", ls)
            current = {
                "用例ID": m.group(1) if m else "",
                "用例标题": m.group(2) if m else "",
                "模块": "",
                "需求来源": "-",
                "测试点ID": "-",
                "用例类型": "正向",
                "前置条件": "",
                "测试数据": "-",
                "操作步骤": "",
                "预期结果": "",
                "清理动作": "-",
                "备注": "-",
                "优先级": "",
            }
            continue
        if current and ls.startswith("|") and not ls.startswith("|---"):
            cells = [c.strip() for c in ls.split("|")[1:-1]]
            if len(cells) >= 2:
                key, val = cells[0].strip(), cells[1].strip()
                val = val.replace("<br>", "\n")
                # 通过别名映射标准化字段名
                field = _CASE_FIELD_ALIASES.get(key)
                if field is None:
                    # 模糊匹配：尝试部分匹配
                    for alias, std in _CASE_FIELD_ALIASES.items():
                        if alias in key or key in alias:
                            field = std
                            break
                if field:
                    current[field] = _normalize_value(field, val)
                # 推断用例类型（如果 AI 未填写或填写了不在允许值中的内容）
                if current.get("用例类型", "") not in _VALID_CASE_TYPES:
                    title = current.get("用例标题", "")
                    if any(kw in title for kw in ["不", "禁止", "无法", "缺少", "不足", "不支持"]):
                        current["用例类型"] = "异常"
                    elif any(kw in title for kw in ["禁用", "不可"]):
                        current["用例类型"] = "状态"
                    else:
                        current["用例类型"] = "正向"
    if current:
        cases.append(current)

    if cases:
        logger.info(f"  用例解析完成：{len(cases)} 条")
    return cases


def _extract_module_number(module_name: str) -> str:
    """从需求文件名中提取模块编号（补零到两位）。"""
    # 先尝试从模块名本身提取（如 "01-项目管理" → "01"）
    m = re.match(r"^(\d+)", module_name)
    if m:
        return m.group(1).zfill(2)
    # 再从 inputs/requirements/ 目录中查找
    for f in SPEC_DIR.glob("*"):
        if f.is_file() and module_name in f.stem:
            m2 = re.match(r"^(\d+)", f.stem)
            if m2:
                return m2.group(1).zfill(2)
    return "00"


def _build_combined_xlsx(
    tp_data: list[dict],
    case_data: list[dict],
    module_name: str,
    module_num: str,
    output_path: Path,
):
    """生成合并 Excel 文件（两个 Sheet：测试点 + 测试用例）。"""
    wb = Workbook()

    # 样式
    hdr_font = Font(bold=True, color="FFFFFF", size=10)
    hdr_fill = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
    hdr_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell_align = Alignment(vertical="top", wrap_text=True)
    border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    # ── Sheet 1: 测试点 ──
    ws1 = wb.active
    ws1.title = "测试点"
    tp_headers = ["测试点编号", "模块", "需求来源", "测试维度", "测试点描述", "优先级", "是否依赖确认", "备注"]
    for col, h in enumerate(tp_headers, 1):
        c = ws1.cell(row=1, column=col, value=h)
        c.font, c.fill, c.alignment, c.border = hdr_font, hdr_fill, hdr_align, border
    for r, row in enumerate(tp_data, 2):
        for col, h in enumerate(tp_headers, 1):
            c = ws1.cell(row=r, column=col, value=row.get(h, ""))
            c.alignment, c.border = cell_align, border
    for i, w in enumerate([14, 12, 10, 10, 35, 8, 12, 15], 1):
        ws1.column_dimensions[ws1.cell(row=1, column=i).column_letter].width = w
    ws1.freeze_panes = "A2"

    # ── Sheet 2: 测试用例 ──
    ws2 = wb.create_sheet("测试用例")
    case_headers = [
        "用例ID", "模块", "需求来源", "测试点ID", "用例标题", "优先级", "用例类型",
        "前置条件", "测试数据", "操作步骤", "预期结果", "清理动作", "备注",
    ]
    for col, h in enumerate(case_headers, 1):
        c = ws2.cell(row=1, column=col, value=h)
        c.font, c.fill, c.alignment, c.border = hdr_font, hdr_fill, hdr_align, border
    for r, row in enumerate(case_data, 2):
        for col, h in enumerate(case_headers, 1):
            c = ws2.cell(row=r, column=col, value=row.get(h, ""))
            c.alignment, c.border = cell_align, border
    for i, w in enumerate([14, 12, 10, 12, 30, 8, 8, 35, 15, 35, 30, 15, 10], 1):
        ws2.column_dimensions[ws2.cell(row=1, column=i).column_letter].width = w
    ws2.freeze_panes = "A2"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    logger.info(f"  合并导出：{output_path.name}（测试点 {len(tp_data)} 条 + 用例 {len(case_data)} 条）")


# ──────────────────────────────────────────────
#  ExcelExportAgent 主类
# ──────────────────────────────────────────────

class ExcelExportAgent:
    """
    Excel 导出智能体类 —— 负责将测试点和测试用例导出为合并 Excel 格式（流程步骤 4）。
    输出到 output/05_export/{模块名}/{编号}-{模块名}-测试点+测试用例_{时间}.xlsx
    """

    def export(self, module_name: str) -> list[Path]:
        """导出指定模块的测试点和测试用例为合并 Excel，返回生成的文件列表。"""
        output_files = []
        actual_module = None

        # 查找测试点和用例文件
        tp_file = self._find_file_by_suffix(module_name, "-测试点")
        case_file = self._find_file_by_suffix(module_name, "-用例")

        if not tp_file and not case_file:
            logger.error(f"测试点和用例文件均未找到：{module_name}")
            return output_files

        # 确定模块名
        for f in [tp_file, case_file]:
            if f:
                actual_module = f.stem.split("-用例")[0].split("-测试点")[0]
                break

        # 提取模块编号
        module_num = _extract_module_number(actual_module)

        # 获取模块专属输出目录
        module_output_dir = get_module_dir(FINAL_CASES_DIR, actual_module)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 解析测试点
        tp_data = []
        if tp_file:
            tp_data = _parse_test_points(tp_file.read_text(encoding="utf-8"))
            logger.info(f"  解析测试点：{len(tp_data)} 条 ← {tp_file.name}")

        # 解析用例
        case_data = []
        if case_file:
            case_data = _parse_test_cases(case_file.read_text(encoding="utf-8"))
            logger.info(f"  解析用例：{len(case_data)} 条 ← {case_file.name}")

        # 生成合并 xlsx
        output_path = module_output_dir / f"{module_num}-{actual_module}-测试点+测试用例_{ts}.xlsx"
        _build_combined_xlsx(tp_data, case_data, actual_module, module_num, output_path)
        output_files.append(output_path)

        print(f"\n{'=' * 60}")
        print(f"  导出完成：{actual_module}")
        print(f"{'=' * 60}")
        print(f"  测试点：{len(tp_data)} 条")
        print(f"  测试用例：{len(case_data)} 条")
        print(f"  输出文件：{output_path}")

        return output_files

    def _find_file_by_suffix(self, module_name: str, suffix: str) -> Path | None:
        """在多个目录中递归查找匹配 suffix 的文件（兼容带时间戳后缀的命名）。

        新命名例：`{stem}-用例_{YYYYMMDD_HHMM}.md`；旧命名：`{stem}-用例.md`。
        同一 stem 存在多份时取排序最后（时间最新）的一份。
        """
        clean_name = re.sub(r"^\d+[、_.\-\s]+", "", module_name).strip()
        search_names = [module_name, clean_name] if clean_name != module_name else [module_name]

        search_dirs = []
        # 1. 先在模块子目录中查找
        for subdir in DESIGN_WORKSPACE_DIR.iterdir():
            if subdir.is_dir():
                search_dirs.append(subdir)
        # 2. 然后在特定目录查找
        if suffix == "-用例":
            search_dirs.extend([CASES_DIR, DESIGN_WORKSPACE_DIR])
        elif suffix == "-测试点":
            search_dirs.extend([TESTPOINTS_DIR, DESIGN_WORKSPACE_DIR])
        else:
            search_dirs.append(DESIGN_WORKSPACE_DIR)

        def _strip_ts(stem: str) -> str:
            return re.sub(r"_\d{8}_\d{4}$", "", stem)

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            cands = list(search_dir.rglob(f"*{suffix}.md")) + list(search_dir.rglob(f"*{suffix}_*.md"))
            # 过滤仅取时间戳为 8+4 数字的命名，避免误匹到不相关后缀
            cands = [f for f in cands if not re.search(r"_\d{8}_\d{4}\.md$", f.name) or f.name.endswith(f"{suffix}.md") or re.search(rf"{re.escape(suffix)}_\d{{8}}_\d{{4}}\.md$", f.name)]
            matched = []
            for f in sorted(set(cands)):
                core = _strip_ts(f.stem).replace(suffix, "")
                stem_clean = re.sub(r"^\d+[、_.\-\s]+", "", core).strip()
                for name in search_names:
                    name_clean = re.sub(r"^\d+[、_.\-\s]+", "", name).strip()
                    if stem_clean == name_clean or name_clean in core or core in name_clean:
                        matched.append(f)
                        break
            if matched:
                return sorted(matched)[-1]
        return None

    def export_all(self):
        """导出所有模块的测试点和测试用例到合并 Excel。"""
        module_names = set()

        def _strip_ts(stem: str) -> str:
            return re.sub(r"_\d{8}_\d{4}$", "", stem)

        # 从子目录收集（新目录约定：test_points/{业务模块}/ …）
        for subdir in DESIGN_WORKSPACE_DIR.iterdir():
            if subdir.is_dir():
                for inner in subdir.iterdir():
                    if inner.is_dir():
                        module_names.add(inner.name)

        # 从文件收集（兼容新旧两种命名）
        for suffix in ["-用例", "-测试点"]:
            for root in [DESIGN_WORKSPACE_DIR, CASES_DIR, TESTPOINTS_DIR]:
                if not root.exists():
                    continue
                for f in list(root.rglob(f"*{suffix}.md")) + list(root.rglob(f"*{suffix}_*.md")):
                    core = _strip_ts(f.stem).replace(suffix, "")
                    if core:
                        module_names.add(core)

        if not module_names:
            logger.error("未找到测试点或用例文件")
            return

        logger.info(f"Excel 导出智能体：{len(module_names)} 个模块")
        for module_name in sorted(module_names):
            logger.info(f"  导出中：{module_name}")
            self.export(module_name)
