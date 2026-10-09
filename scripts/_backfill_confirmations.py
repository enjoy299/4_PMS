#!/usr/bin/env python3
"""确认拍板单：集中填写 → 一键回填源文档确认列。

用法：
    python scripts/_backfill_confirmations.py gen <模块> [--out 路径] [--force] [--format md|xlsx]
    python scripts/_backfill_confirmations.py backfill <拍板单.md|.xlsx> [--dry-run]

背景：同一根问题常散布在多份源文档（01 全景图 / 02 风险清单·歧义·缺口·基线 /
03 需求理解 §7），逐份就地填写易漏且易不一致。本脚本提供两步：
  gen      —— 扫描该模块全部承载确认列的源文档，把剩余 ⬜ 平铺生成拍板单骨架
              （AI 可再把同根问题合并成一行：结论编号换 C-NN、回填定位分号并入）；
  backfill —— 解析拍板单中已拍板的行，按「文件名:行号#编号」定位源文档表格行，
              把末列 ⬜ 格替换为 ✅ 结论（行内其余内容与 CRLF 行尾原样保留）。

双格式（gen --format 指定，backfill 按文件后缀自动识别，回填逻辑一致）：
  md（默认）—— Markdown 表格，对话/AI 聚类友好；结论列必须 `✅ <结论>`，含竖线 | 拒绝回填
  xlsx     —— Excel（业务填写友好）；结论列直接填结论文字（✅ 前缀可省），
               含竖线 | 自动替换为 / 并提示

md 拍板单格式（gen 产出，业务/AI 只改前 3 列，第 4 列勿动）：

    # <模块> · 确认拍板单（YYYY-MM-DD）
    | 结论编号 | 根问题 | 业务结论(业务填) | 回填定位（勿改） |
    |---|---|---|---|
    | C-01 | 版本由何操作产生？ | ✅ 编辑后入库产生新版本 | 歧义报告.md:12#AMB-002; 缺口审计报告.md:13#GAP-002 |

xlsx 拍板单列同 md 前 4 列（+末列「源文档（参考）」），A1 标题行与 md 标题格式一致。

规则：
  - md 第 3 列 `⬜ <问句>` → `✅ <结论>`，结论禁含竖线 |（拒绝回填）；
    xlsx 直接在结论列覆盖 ⬜ 预填写结论文字（✅ 前缀可省），竖线自动替换为 /
  - 定位串 `文件名:行号#编号`（行号可省，编号为准、行号仅校验）；同编号多行含 ⬜ 时全部回填同一结论
  - 幂等：目标行已无 ⬜ 视为已拍板，跳过；--dry-run 只预览不写盘
  - 漂移防护：结论格仍含「（拍板：」问句文本的判为未拍板（WARN 跳过），
    防预填 ⬜ 被外部编辑器改写成 ✅ 后误当结论回填
  - 拍板单不承载确认列语义，不参与 _lint_confirmations 统计（文件名避开
    「风险清单与待确认汇总/业务全景图」标记、不放入 test_points/ 目录即可）
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _lint_confirmations as lint          # 复用层扫描（含数字前缀容错）

ROOT = lint.ROOT
SPLIT_DIR = lint.SPLIT_DIR
BUSINESS_DIR = lint.BUSINESS_DIR
TESTPOINTS_DIR = lint.TESTPOINTS_DIR

CONFIRM_MARK = "确认结论(业务填)"                       # 确认列表头标记（收录条件）
TITLE_RE = re.compile(r"^#?\s*(.+?)\s*·\s*确认拍板单")   # # 可选：md 标题带 #，xlsx A1 不带
LOC_RE = re.compile(r"^(.+?\.md)(?::(\d+))?\s*#\s*(\S+)$")
ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|")      # 表格行首编号格
TYPE_MARK = re.compile(r"(未定义|有歧义|待确认|前后冲突|测试阻塞|已澄清|部分澄清|新增约束|冲突)")
MAX_Q = 80                                          # 根问题摘要截断长度


# ==================== 通用 ====================

def _source_files(module: str) -> list[Path]:
    """该模块承载确认列的源文档：01 全景图 + 02 全部含 ⬜ 表格行的 md + 03 需求理解最新批次。

    与 _lint_confirmations 口径对齐（L1 的 UPSTREAM_MARKS 之外，02 目录里
    歧义报告/缺口审计报告/需求质量基线报告等深度分析产物同样承载确认列，
    按「文件内容存在 ⬜ 表格行」动态收录）；L2 复用 lint 的取最新逻辑。
    """
    files: list[Path] = []
    seen: set[Path] = set()
    biz = BUSINESS_DIR / f"{module}-业务全景图.md"
    if biz.exists():
        files.append(biz)
        seen.add(biz)
    for p in lint._layer1_files(module) + lint._layer2_files(module, lint._req_stems(module)):
        if p not in seen and p.exists():
            files.append(p)
            seen.add(p)
    sub = SPLIT_DIR / module
    if sub.is_dir():                                # 02 目录其余深度分析报告：
        for p in sorted(sub.glob("*.md")):          # 仅收含确认列表头的（歧义/缺口/基线等），
            if p in seen or "archive" in p.parts:   # 探索覆盖状态类 ⬜（如需求校准报告）不收
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if CONFIRM_MARK not in text:
                continue
            if any(ln.lstrip().startswith("|") and "⬜" in ln
                   for ln in text.splitlines()):
                files.append(p)
                seen.add(p)
    return files


def _pending_rows(p: Path) -> list[tuple[int, str, str, str, str]]:
    """提取文件中含 ⬜ 的表格行 → [(行号, 编号, 类型/根问题, 风险描述, 末列问句原文)]。

    风险描述启发式：cells[1] 为短类型标记（未定义/有歧义…，≤12字）时取 cells[2]
    （风险清单/风险小结/歧义/缺口表结构）；否则 cells[1] 即问题描述（需求理解表）。
    """
    rows: list[tuple[int, str, str, str, str]] = []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rows
    for ln, line in enumerate(lines, 1):
        s = line.strip()
        if not s.startswith("|") or "⬜" not in s:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        ident = cells[0]
        brief = (cells[1] if len(cells) > 2 else cells[-1])[:MAX_Q]
        c1 = cells[1].replace(" ", "")
        if len(cells) > 3 and len(c1) <= 12 and TYPE_MARK.search(c1):
            desc = cells[2]                      # 风险描述逐字保留（不截断，防遗漏/改变）
        else:
            desc = brief
        rows.append((ln, ident, brief, desc, cells[-1]))
    return rows


def _prefill(desc: str, question: str) -> str:
    """结论列预填：风险描述与源文档一致 + 拍板问句（源确认列已带问句时沿用）。

    业务填写时整格覆盖为结论文字；⬜ 前缀保留未拍板语义（backfill 不误判）。
    """
    q = question[1:].strip() if question.startswith("⬜") else question.strip()
    if q:
        return f"⬜ {desc}（拍板：{q}）"
    return f"⬜ {desc}（请业务拍板）"


def _find_source(module: str, filename: str) -> Path | None:
    """按目录序定位源文档（02 子目录 → 03 test_points 子目录 → 01_business）。"""
    for d in (SPLIT_DIR / module, TESTPOINTS_DIR / module, BUSINESS_DIR):
        p = d / filename
        if p.exists():
            return p
    return None


def _disp(p: Path) -> str:
    """展示路径：ROOT 内用相对路径，ROOT 外（--out 可指向工作区外）用绝对路径。"""
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


# ==================== gen：生成拍板单 ====================

def cmd_gen(module: str, out: Path, force: bool, fmt: str = "md") -> int:
    files = _source_files(module)
    if not files:
        print(f"[{module}] 未发现承载 ⬜ 的源文档，无需拍板单")
        return 0
    today = date.today().isoformat()
    if out is None:
        out = SPLIT_DIR / module / f"确认拍板单_{date.today().strftime('%Y%m%d')}.{fmt}"
    if out.exists() and not force:
        print(f"[ERROR] 已存在：{out}（--force 覆盖，或 --out 换路径）")
        return 1

    groups: list[tuple[Path, list[tuple[int, str, str, str]]]] = []
    for p in files:
        rows = _pending_rows(p)
        if rows:
            groups.append((p, rows))
    src_count = len(groups)

    # 同编号多源行合并为一行（定位分号并入）：同一问题常同时承载于
    # 子文件风险小结 + 06 风险清单，合并后业务每题只填一次；
    # 跨编号同根合并仍留给 AI 聚类（结论编号换 C-NN）
    merged: list[tuple[str, str, str, list[str]]] = []      # (编号, 类型/根问题, 预填, 定位s)
    index: dict[str, int] = {}
    spots = 0
    for p, rows in groups:
        for ln, ident, brief, desc, question in rows:
            spots += 1
            loc = f"{p.name}:{ln}#{ident}"
            if ident in index:
                merged[index[ident]][3].append(loc)
            else:
                index[ident] = len(merged)
                merged.append((ident, brief, _prefill(desc, question), [loc]))

    if fmt == "xlsx":
        _gen_xlsx(module, out, today, merged)
        print(f"[{module}] Excel 拍板单已生成：{_disp(out)}"
              f"（{len(merged)} 个待拍板问题 / {spots} 处，源自 {src_count} 份文档）")
        print("下一步：业务在「业务结论(业务填)」列填结论文字（无需 ✅ 前缀）"
              "→ backfill 回填（先 --dry-run 预览）")
        return 0

    body: list[str] = []
    for ident, brief, prefill, locs in merged:
        body.append(f"| {ident} | {brief} | {prefill} | {'; '.join(locs)} |")

    head = [
        f"# {module} · 确认拍板单（{today}）",
        "",
        f"> 生成：`python scripts/_backfill_confirmations.py gen {module}`"
        f"（共 {len(merged)} 个待拍板问题 / {spots} 处，源自 {src_count} 份文档；"
        "同编号多源已自动合并为一行）",
        "> 填法：只改「业务结论(业务填)」列——`⬜ <问句>` 整格换成 `✅ <结论>`；结论内**禁用竖线 |**",
        "> 回填：`python scripts/_backfill_confirmations.py backfill <本文件>`"
        "（先加 `--dry-run` 预览）；回填只动末列 ⬜ 格，行内其余内容原样保留",
        "> 整理（可选，AI）：同根问题合并为一行——「结论编号」换 C-NN，"
        "「回填定位」多条用分号并入同一格；勿改 `文件名:行号#编号` 格式",
        "> 纪律：同根问题一次拍板、跨文档结论一致；拍板单不进 git 基线，"
        "回填完成后跑 `python scripts/_lint_confirmations.py " + module + "` 验证",
        "",
        "| 结论编号 | 根问题 | 业务结论(业务填) | 回填定位（勿改） |",
        "|---|---|---|---|",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(head + body) + "\n", encoding="utf-8")
    print(f"[{module}] 拍板单已生成：{_disp(out)}（{len(merged)} 个问题 / {spots} 处）")
    print("下一步：AI 聚类整理同根问题 → 业务填写 ✅ 结论 → backfill 回填")
    return 0


def _gen_xlsx(module: str, out: Path, today: str,
              merged: list[tuple[str, str, str, list[str]]]) -> None:
    """生成 Excel 拍板单：前 4 列与 md 版对齐 + 末列「源文档（参考）」。

    样式对齐项目导出习惯（表头 2E75B6 / 待填列浅黄 FFF9C4）；A1 标题与 md 版
    标题行格式一致（backfill 据此识别模块名）。
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "拍板单"
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
    todo_fill = PatternFill(start_color="FFF9C4", end_color="FFF9C4", fill_type="solid")
    gray = Font(color="808080")

    ws["A1"] = f"{module} · 确认拍板单（{today}）"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "填法：只在「业务结论(业务填)」列填结论文字（无需 ✅ 前缀），其余列勿动；同根问题可合并行（回填定位分号并入）"
    ws["A3"] = "回填：python scripts/_backfill_confirmations.py backfill <本文件>（先 --dry-run 预览）；结论含竖线 | 将自动替换为 /"
    ws["A2"].font = ws["A3"].font = Font(color="808080", size=9)

    ws.append([])                                     # 说明区与表格间空一行
    ws.append(["结论编号", "根问题", "业务结论(业务填)", "回填定位（勿改）", "源文档（参考）"])
    hrow = ws.max_row
    for col in range(1, 6):
        c = ws.cell(row=hrow, column=col)
        c.font = head_font
        c.fill = head_fill
    for ident, brief, prefill, locs in merged:
        ws.append([ident, brief, prefill, "; ".join(locs),
                   "; ".join(sorted({l.split(":")[0] for l in locs}))])
    for row in ws.iter_rows(min_row=hrow + 1, max_row=ws.max_row):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)
        row[2].fill = todo_fill                       # 待填列浅黄提示
        row[3].font = gray                            # 勿改列灰字
    for col, w in zip(range(1, 6), (14, 46, 52, 38, 22)):
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.freeze_panes = f"A{hrow + 1}"                  # 冻结表头
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)


# ==================== backfill：回填源文档 ====================

def _replace_last_pending(line: str, conclusion: str) -> str | None:
    """把行内最后一个含 ⬜ 的表格格替换为 ✅ 结论；无 ⬜ 返回 None。"""
    if "⬜" not in line:
        return None
    core = line.rstrip("\r")
    parts = core.split("|")
    idx = max(i for i, part in enumerate(parts) if "⬜" in part)
    parts[idx] = f" ✅ {conclusion} "
    tail = "\r" if line.endswith("\r") else ""
    return "|".join(parts) + tail


def _locate(lines: list[str], ident: str, hint_ln: int | None) -> list[int]:
    """按编号定位含 ⬜ 的表格行下标；行号仅作校验提示（允许漂移）。"""
    pat = re.compile(r"^\|\s*" + re.escape(ident) + r"\s*\|")
    hits = [i for i, s in enumerate(lines)
            if pat.match(s) and "⬜" in s]
    if not hits:                                    # 行首编号带粗体等包裹时放宽
        pat2 = re.compile(r"^\|\s*\**" + re.escape(ident) + r"\**\s*\|")
        hits = [i for i, s in enumerate(lines)
                if pat2.match(s) and "⬜" in s]
    if hint_ln and hits and all(abs(i + 1 - hint_ln) > 10 for i in hits):
        print(f"  [WARN] {ident} 行号漂移（提示 {hint_ln}，实际 {[i + 1 for i in hits]}），按编号回填")
    return hits


def _parse_locs(ident: str, loc_text: str) -> list[tuple[str, int | None, str]]:
    """解析回填定位列：分号分隔的「文件名:行号#编号」。"""
    locs: list[tuple[str, int | None, str]] = []
    for seg in loc_text.split(";"):
        seg = seg.strip()
        if not seg:
            continue
        lm = LOC_RE.match(seg)
        if not lm:
            print(f"  [ERROR] {ident} 定位串无法解析：{seg}")
            continue
        locs.append((lm.group(1), int(lm.group(2)) if lm.group(2) else None, lm.group(3)))
    return locs


def _parse_form_md(text: str) -> tuple[str, list[tuple[str, str, list[tuple[str, int | None, str]]]]]:
    """解析 Markdown 拍板单 → (模块, [(结论编号, 结论, 定位s)])。

    仅收第 3 列以 ✅ 开头的行；结论含竖线 |（回填 md 表格会破格）拒绝该行。
    """
    m = TITLE_RE.search(text)
    if not m:
        print("[ERROR] 拍板单缺标题行「# <模块> · 确认拍板单」")
        return "", []
    module = m.group(1).strip()
    decisions: list[tuple[str, str, list[tuple[str, int | None, str]]]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|") or s.startswith("|---") or s.startswith("|:---"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) != 4 or not cells[0]:
            continue
        conclusion = cells[2]
        if not conclusion.startswith("✅"):
            continue
        if "（拍板：" in conclusion:                    # 漂移防护同 xlsx 解析器
            print(f"  [WARN] {cells[0]} 疑似预填漂移（结论仍含「（拍板：」问句），"
                  f"判为未拍板跳过；请还原为 ⬜ 预填或填入真实结论：{conclusion[:50]}")
            continue
        if "|" in conclusion[1:].strip():
            print(f"  [ERROR] {cells[0]} 结论含竖线，拒绝回填：{conclusion[:50]}")
            continue
        body = conclusion[1:].strip()
        locs = _parse_locs(cells[0], cells[3])
        if locs:
            decisions.append((cells[0], body, locs))
    return module, decisions


def _parse_form_xlsx(form: Path) -> tuple[str, list[tuple[str, str, list[tuple[str, int | None, str]]]]]:
    """解析 Excel 拍板单 → (模块, decisions)；结论列非空且非 ⬜ 即视为已拍板。

    对业务从宽：✅ 前缀可省（纯结论文字即可）；结论含竖线 | 自动替换为 /
    （回填 md 表格需防破格），替换时提示。格内仍含「（拍板：」问句的
    视为未拍板（防预填 ⬜ 被外部编辑器改写成 ✅ 的漂移被误回填）。
    """
    from openpyxl import load_workbook

    wb = load_workbook(form, data_only=True)
    ws = wb.active
    module = ""
    for row in ws.iter_rows(min_row=1, max_row=min(5, ws.max_row or 1)):
        v = row[0].value
        if isinstance(v, str) and (m := TITLE_RE.search(v)):
            module = m.group(1).strip()
            break
    if not module:
        print(f"[ERROR] 拍板单缺标题「<模块> · 确认拍板单」：{form}")
        return "", []
    header_row = next((r for r in range(1, (ws.max_row or 1) + 1)
                       if str(ws.cell(row=r, column=1).value or "").strip() == "结论编号"), None)
    if header_row is None:
        print(f"[ERROR] 拍板单缺表头行「结论编号」：{form}")
        return module, []
    decisions: list[tuple[str, str, list[tuple[str, int | None, str]]]] = []
    for r in range(header_row + 1, (ws.max_row or 1) + 1):
        ident = str(ws.cell(row=r, column=1).value or "").strip()
        conclusion = str(ws.cell(row=r, column=3).value or "").strip()
        loc_text = str(ws.cell(row=r, column=4).value or "").strip()
        if not ident or not loc_text:
            continue
        if not conclusion or conclusion.startswith("⬜"):
            continue                                   # 结论列空 / 仍是 ⬜ 预填问句 → 未拍板
        if "（拍板：" in conclusion:                    # 漂移防护：⬜ 被外部编辑器改成 ✅ → 防误回填
            print(f"  [WARN] {ident} 疑似预填漂移（结论格仍含「（拍板：」问句），"
                  f"判为未拍板跳过；请还原为 ⬜ 预填或填入真实结论：{conclusion[:50]}")
            continue
        body = conclusion[1:].strip() if conclusion.startswith("✅") else conclusion
        if not body:
            continue
        if "|" in body:
            print(f"  [WARN] {ident} 结论含竖线，自动替换为 /：{body[:50]}")
            body = body.replace("|", "/")
        locs = _parse_locs(ident, loc_text)
        if locs:
            decisions.append((ident, body, locs))
    return module, decisions


def cmd_backfill(form: Path, dry_run: bool) -> int:
    if form.suffix.lower() == ".xlsx":
        module, decisions = _parse_form_xlsx(form)
    else:
        module, decisions = _parse_form_md(
            form.read_text(encoding="utf-8", errors="replace"))
    if not module:
        return 1

    if not decisions:
        print(f"[{module}] 拍板单中无已拍板结论（结论列均未填或格式不符），无可回填")
        return 0
    print(f"[{module}] 待回填 {len(decisions)} 条结论"
          f"{'（DRY-RUN 预览，不写盘）' if dry_run else ''}")

    # 按目标文件聚合，逐文件读改写（保持行尾与编码无损）
    by_file: dict[Path, list[tuple[str, str, int | None, str]]] = {}
    for ident, body, locs in decisions:
        for filename, hint_ln, target in locs:
            src = _find_source(module, filename)
            if src is None:
                print(f"  [FAIL] 源文档未找到：{module}/{filename}（{ident}）")
                continue
            by_file.setdefault(src, []).append((ident, body, hint_ln, target))

    done = skipped = failed = 0
    for src, items in by_file.items():
        with open(src, encoding="utf-8", newline="") as f:
            raw = f.read()
        nl = "\r\n" if "\r\n" in raw else "\n"
        lines = raw.split(nl)
        dirty = False
        for ident, body, hint_ln, target in items:
            hits = _locate(lines, target, hint_ln)
            if not hits:
                print(f"  [SKIP] {src.name}:{target} 无待拍板行（已 ✅ 或不存在），跳过")
                skipped += 1
                continue
            for i in hits:
                new = _replace_last_pending(lines[i], body)
                if new is None:
                    continue
                print(f"  [{'DRY' if dry_run else 'OK '}] {src.name}:{i + 1} {target} -> ✅ {body[:50]}")
                if not dry_run:
                    lines[i] = new
                    dirty = True
                done += 1
        if dirty:
            with open(src, "w", encoding="utf-8", newline="") as f:
                f.write(nl.join(lines))
    print(f"回填完成：{done} 处{'（预览）' if dry_run else ''} ｜ 跳过 {skipped} ｜ 失败 {failed}")
    print(f"验证：python scripts/_lint_confirmations.py {module}")
    return 0 if failed == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="确认拍板单：gen 生成 / backfill 回填")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen", help="扫描模块剩余 ⬜ 生成拍板单骨架")
    g.add_argument("module")
    g.add_argument("--out", type=Path, default=None)
    g.add_argument("--force", action="store_true")
    g.add_argument("--format", choices=("md", "xlsx"), default="md",
                   help="拍板单格式：md（默认）/ xlsx（Excel，业务填写友好）")
    b = sub.add_parser("backfill", help="按拍板单 ✅ 结论回填源文档")
    b.add_argument("form", type=Path)
    b.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "gen":
        return cmd_gen(args.module, args.out, args.force, args.format)
    if not args.form.exists():
        print(f"[ERROR] 拍板单不存在：{args.form}")
        return 1
    return cmd_backfill(args.form, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
