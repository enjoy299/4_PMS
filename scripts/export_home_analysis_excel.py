"""
将 output/06_reports/首页/ 下的 Markdown 分析报告整合为多 Sheet 的 Excel 工作簿。

- Sheet 0：首页测试汇总（封面，含关键指标）
- Sheet 1..N：每个 .md 报告一个 Sheet，解析其中的表格 / 标题 / 正文
样式沿用项目 report_exporter：蓝色表头、细边框、PASS/FAIL 底色。
"""
import re
import sys
from pathlib import Path
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HOME_DIR = Path("output/06_reports/首页")
EXCEL_DIR = Path("output/06_reports/excel")
EXCEL_DIR.mkdir(parents=True, exist_ok=True)

# Sheet 名称映射（Excel 限制 31 字符，禁用 []:*?/\）
SHEET_MAP = {
    "20260907_准入检查与测试计划.md": "01_准入与测试计划",
    "20260907_冒烟测试报告.md": "02_冒烟测试报告",
    "20260907_测试执行记录.md": "03_测试执行记录",
    "20260907_探索式记录与发现清单.md": "04_探索与发现清单",
    "20260907_测试收尾报告.md": "05_测试收尾报告",
}

# ---- 样式 ----
HEADER_FILL = PatternFill("solid", start_color="2E75B6", end_color="2E75B6")
HEADER_FONT = Font(bold=True, color="FFFFFF")
SECTION_FILL = PatternFill("solid", start_color="DDEBF7", end_color="DDEBF7")
SECTION_FONT = Font(bold=True, color="1F4E78")
TITLE_FONT = Font(bold=True, size=14, color="1F4E78")
PASS_FILL = PatternFill("solid", start_color="E2EFDA", end_color="E2EFDA")
FAIL_FILL = PatternFill("solid", start_color="FCE4EC", end_color="FCE4EC")
BLOCK_FILL = PatternFill("solid", start_color="FFF3E0", end_color="FFF3E0")
THIN = Border(*[Side("thin")] * 4)
WRAP = Alignment(wrap_text=True, vertical="top")


def clean(text: str) -> str:
    """去除 Markdown 行内标记，保留纯文本。"""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"<br\s*/?>", " / ", text)
    return text.strip()


def split_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [clean(c) for c in cells]


def is_sep(line: str) -> bool:
    return bool(re.match(r"^\s*\|[\s:\-\|]+\|\s*$", line))


def status_fill(val: str):
    v = val.upper()
    if "PASS" in v or "✅" in val:
        return PASS_FILL
    if "FAIL" in v or "❌" in val:
        return FAIL_FILL
    if "BLOCK" in v or "SKIP" in v or "🚫" in val or "⏭" in val:
        return BLOCK_FILL
    return None


def render_md(ws, md_text: str):
    """把一段 Markdown 渲染进工作表：表格转网格，标题/正文转整行文本。"""
    r = 1
    lines = md_text.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        stripped = line.strip()
        # 表格块
        if stripped.startswith("|") and i + 1 < n and is_sep(lines[i + 1]):
            header = split_row(lines[i])
            for col, h in enumerate(header, 1):
                c = ws.cell(row=r, column=col, value=h)
                c.font = HEADER_FONT
                c.fill = HEADER_FILL
                c.border = THIN
                c.alignment = WRAP
            r += 1
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                cells = split_row(lines[i])
                for col in range(1, len(header) + 1):
                    val = cells[col - 1] if col - 1 < len(cells) else ""
                    c = ws.cell(row=r, column=col, value=val)
                    c.border = THIN
                    c.alignment = WRAP
                    fill = status_fill(val)
                    if fill:
                        c.fill = fill
                r += 1
                i += 1
            continue
        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if m:
            level, title = len(m.group(1)), clean(m.group(2))
            c = ws.cell(row=r, column=1, value=title)
            if level <= 2:
                c.font = TITLE_FONT
            else:
                c.font = SECTION_FONT
                c.fill = SECTION_FILL
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=14)
            r += 1
            i += 1
            continue
        # 列表 / 普通文本
        if stripped:
            txt = re.sub(r"^[-*]\s+", "• ", stripped)
            txt = re.sub(r"^\d+\.\s+", lambda mm: mm.group(0), txt)
            c = ws.cell(row=r, column=1, value=clean(txt))
            c.alignment = WRAP
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=14)
            r += 1
        i += 1


def autofit(ws):
    """按内容粗调列宽。"""
    widths = {}
    for row in ws.iter_rows():
        for c in row:
            if c.value and c.column_letter:
                length = max(len(s) for s in str(c.value).splitlines()) if c.value else 0
                # 中文按 1.8 宽度估算
                est = min(60, max(8, int(length * 1.6) + 2))
                widths[c.column_letter] = max(widths.get(c.column_letter, 0), est)
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def build_cover(ws, reports_info):
    ws.cell(row=1, column=1, value="首页（门户首页）· 测试分析汇总").font = Font(bold=True, size=16, color="1F4E78")
    ws.merge_cells("A1:D1")
    meta = [
        ("生成时间", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("被测环境", "<APP_URL>"),
        ("测试账号", "见仓库根 .env 的 TEST_USERNAME / TEST_PASSWORD（导出产物不写凭据）"),
        ("用例总数", "24（P0=10 / P1=10 / P2=4）"),
        ("P0 通过率", "10/10 = 100%"),
        ("整体结果", "PASS 15 / BLOCK 6 / SKIP 2 / FAIL 0"),
        ("功能缺陷", "0（无 S1/S2）"),
        ("发版建议", "✅ 核心功能建议发版（详见收尾报告）"),
    ]
    r = 3
    for k, v in meta:
        a = ws.cell(row=r, column=1, value=k); a.font = HEADER_FONT; a.fill = HEADER_FILL; a.border = THIN
        b = ws.cell(row=r, column=2, value=v); b.border = THIN; b.alignment = WRAP
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
        r += 1
    r += 1
    c = ws.cell(row=r, column=1, value="工作簿包含的 Sheet（对应 STLC 六阶段文档）")
    c.font = SECTION_FONT; c.fill = SECTION_FILL
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
    r += 1
    for name, src in reports_info:
        cc = ws.cell(row=r, column=1, value=f"• {name}   ←   {src}")
        cc.alignment = WRAP
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        r += 1
    ws.column_dimensions["A"].width = 20
    for col in "BCD":
        ws.column_dimensions[col].width = 28


def main():
    md_files = sorted([p for p in HOME_DIR.glob("*.md")], key=lambda p: p.name)
    if not md_files:
        print(f"未找到报告文件：{HOME_DIR}")
        return

    wb = Workbook()
    cover = wb.active
    cover.title = "00_首页测试汇总"

    reports_info = []
    for p in md_files:
        sheet_name = SHEET_MAP.get(p.name, p.stem[:28])
        reports_info.append((sheet_name, p.name))

    build_cover(cover, reports_info)

    for p in md_files:
        sheet_name = SHEET_MAP.get(p.name, p.stem[:28])
        ws = wb.create_sheet(title=sheet_name)
        render_md(ws, p.read_text(encoding="utf-8"))
        autofit(ws)
        ws.freeze_panes = "A2"

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = EXCEL_DIR / f"{ts}_首页_测试分析汇总.xlsx"
    wb.save(out)
    print(f"已生成：{out}")
    print(f"Sheet：{[ws.title for ws in wb.worksheets]}")


if __name__ == "__main__":
    main()
