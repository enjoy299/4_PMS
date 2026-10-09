"""确认列放行检查：剩余未拍板项统计 + 层间新鲜度（mtime）比对。

用法：python scripts/_lint_confirmations.py [模块名 ...]
不带参数则扫描全部模块（以 01_business / 02_split_requirements 出现过的模块为准）。

约定（与 business/analyst/understanding/design_tp/design_case 提示词的确认列一致）：
  确认列初始 `⬜ <问句>`，业务拍板后把 `⬜` 换成 `✅ <结论>`；
  引用上游未闭项时只写编号不复制 ⬜（防误计）；依赖上游未拍板项的行填 `-`。

确认载体按层组织（横排表格行 / 竖排字段行均按行扫 ⬜，兼容两种结构）：
  L1 基线：01 业务全景图 + 02 风险清单与待确认汇总；
  L2 需求理解：03_design 根级固定名 + 子目录批次，每子模块取最新；
  L3 测试点 + 风险台账：每子模块各取最新批次（排除 archive）；
  L4 测试用例：每子模块取最新批次（排除 archive）；
  L5 评审 / 导出：不承载确认列，只参与新鲜度比对。

只读不改，做两件事：
  1. 统计 L1~L4 的确认列——还有 ⬜ 即 FAIL：拍板后再放行下一级；
  2. 层间新鲜度：Lk 产物应晚于 L1..L(k-1) 的最后修改时间，
     早于则提示「可能在确认前生成，建议重跑该级」（WARN，不影响结果）。

说明：控制台输出不打印 ⬜/✅ 原字符（GBK 终端无法编码），统一显示为[未确认]/[已确认]。
"""
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
BUSINESS_DIR = OUTPUT / "01_business"
SPLIT_DIR = OUTPUT / "02_split_requirements"
TESTPOINTS_DIR = OUTPUT / "03_design" / "test_points"
CASES_DIR = OUTPUT / "03_design" / "test_cases"
REVIEW_DIR = OUTPUT / "04_review"
EXPORT_DIR = OUTPUT / "05_export"

# 02 目录下承载确认列的文件名标记（业务全景图 / 风险清单与待确认汇总）
UPSTREAM_MARKS = ("业务全景图", "风险清单与待确认汇总")
CLEAN = re.compile(r"^\d+[、_.\-\s]+")

# 03_design 批次文件名：{子模块stem}-{类型}_{时间戳}.md（时间戳可缺省，兼容根级需求理解固定名）
_KIND_RE = re.compile(
    r"^(?P<stem>.+?)-(?P<kind>风险清单与待确认汇总|测试点|用例)(?:_\d{8}_\d{4})?\.md$")

# 层定义：L1~L4 承载确认列（参与 ⬜ 统计），L5 只做新鲜度；层名 -> 新鲜度 WARN 的建议命令
L1, L2, L3, L4, L5 = "基线(01/02)", "需求理解", "测试点/台账", "用例", "评审/导出"
_CONFIRM_LAYERS = {L1, L2, L3, L4}
_LAYER_HINTS = {
    L2: "python run.py understand <模块>（或重跑 testpoints 自适应消费）",
    L3: "python run.py testpoints <模块>",
    L4: "python run.py testcases <模块>",
    L5: "python run.py review <模块> 后 python run.py export",
}


def _clean(name: str) -> str:
    """去除数字前缀（'7、知识管理' -> '知识管理'）。"""
    return CLEAN.sub("", name).strip()


def _modules():
    """从 01/02 目录收集模块清单（清洗数字前缀后去重）。"""
    names = set()
    if BUSINESS_DIR.is_dir():
        for p in BUSINESS_DIR.glob("*-业务全景图.md"):
            if not p.stem.startswith("00-"):          # 00- 为系统级，单独扫描
                names.add(_clean(p.stem.replace("-业务全景图", "")))
    if SPLIT_DIR.is_dir():
        for p in SPLIT_DIR.iterdir():
            if p.is_dir():
                names.add(_clean(p.name))
            elif p.suffix == ".md":
                names.add(_clean(p.stem))
    return sorted(n for n in names if n)


def _req_stems(module: str) -> list[str]:
    """该模块 02 拆分产物的文件 stem（供 03_design 根级文件按 stem 过滤归属）。"""
    sub = SPLIT_DIR / module
    if sub.is_dir():
        return [p.stem for p in sorted(sub.rglob("*.md"))]
    return [p.stem for p in sorted(SPLIT_DIR.glob("*.md")) if _clean(p.stem) == module]


def _layer1_files(module: str) -> list[Path]:
    """L1 基线：业务全景图 + 02 风险清单与待确认汇总（含旧版根级单文件拆分兼容）。"""
    files: list[Path] = []
    biz = BUSINESS_DIR / f"{module}-业务全景图.md"
    if biz.exists():
        files.append(biz)
    sub = SPLIT_DIR / module
    if sub.is_dir():
        for p in sorted(sub.rglob("*.md")):
            if any(mk in p.name for mk in UPSTREAM_MARKS):
                files.append(p)
    else:                                            # 旧版单文件拆分：整个文件承载确认列
        for p in sorted(SPLIT_DIR.glob("*.md")):
            if _clean(p.stem) == module:
                files.append(p)
    return files


def _layer2_files(module: str, req_stems: list[str]) -> list[Path]:
    """L2 需求理解：根级固定名 + 子目录批次，按子模块 stem 分组取 mtime 最新。

    存储名可带数字前缀（如 '01-知识维护-需求理解_20260918_1652.md'），匹配前双侧去前缀。
    """
    sub = TESTPOINTS_DIR / module
    dirs = [sub, TESTPOINTS_DIR] if sub.is_dir() else [TESTPOINTS_DIR]
    wants = {s: _clean(s) for s in req_stems}
    cands: dict[str, list[Path]] = {}
    for d in dirs:
        for p in d.glob("*需求理解*.md"):
            if "archive" in p.parts:
                continue
            core = _clean(p.stem)
            for s, want in wants.items():
                if want and core.startswith(f"{want}-需求理解"):
                    cands.setdefault(s, []).append(p)
                    break
    if not cands:
        return []
    return [max(ps, key=lambda p: p.stat().st_mtime) for ps in cands.values()]


def _latest_batches(d: Path, kinds: tuple[str, ...]) -> list[Path]:
    """目录 d 内 {stem}-{kind}_{ts}.md 按 (stem, kind) 分组取文件名最新批次（排除 archive）。"""
    latest: dict[tuple[str, str], Path] = {}
    if not d.is_dir():
        return []
    for p in sorted(d.glob("*.md")):                 # 文件名含时间戳，sorted 后覆盖即最新
        if "archive" in p.parts:
            continue
        m = _KIND_RE.match(p.name)
        if m and m.group("kind") in kinds:
            latest[(m.group("stem"), m.group("kind"))] = p
    return list(latest.values())


def _layer3_files(module: str) -> list[Path]:
    """L3 测试点 + 风险台账：test_points/{父模块}/ 下每子模块各取最新批次。"""
    return _latest_batches(TESTPOINTS_DIR / module, ("测试点", "风险清单与待确认汇总"))


def _layer4_files(module: str) -> list[Path]:
    """L4 测试用例：test_cases/{父模块}/ 下每子模块取最新批次。"""
    return _latest_batches(CASES_DIR / module, ("用例",))


def _layer5_files(module: str) -> list[Path]:
    """L5 评审 / 导出：04_review、05_export 下该模块全部产物（archive/ 归档区不计）。"""
    files: list[Path] = []
    for base in (REVIEW_DIR, EXPORT_DIR):
        d = base / module
        if d.is_dir():
            files += [p for p in d.rglob("*")
                      if p.is_file() and "archive" not in p.parts]
    return files


def _brief(line: str) -> str:
    """表格行摘要：去竖线、⬜/✅ 转文字、其余 GBK 外字符（🟡🔴🟢等）降级为 ?，截断。"""
    text = (line.replace("|", " ")
                .replace("⬜", "[未确认]")
                .replace("✅", "[已确认]")
                .strip())
    text = text.encode("gbk", errors="replace").decode("gbk")
    return text[:80] + ("…" if len(text) > 80 else "")


def scan(title: str, layers: list[tuple[str, list[Path]]]) -> int:
    """逐层统计确认列（承载层计 ⬜/✅）+ 层间新鲜度，返回未拍板项数。

    layers 按链序排列：[(层名, 文件列表), ...]，如
    [("基线(01/02)", ...), ("需求理解", ...), ("测试点/台账", ...), ("用例", ...), ("评审/导出", ...)]。
    """
    confirm_files = [p for lname, files in layers if lname in _CONFIRM_LAYERS for p in files]
    if not confirm_files:
        print(f"[{title}] [WARN] 未找到承载确认列的产物"
              f"（01 业务全景图 / 02 风险清单 / 03 需求理解/测试点/台账/用例）")
        return 0

    pending: list[tuple[str, Path, int, str]] = []
    confirmed = 0
    # 层时间桶：层名 -> (该层最新 mtime, [文件])，供层间新鲜度链比对
    layer_times: list[tuple[str, float | None, list[Path]]] = []
    for lname, files in layers:
        mtimes: list[float] = []
        layer_paths: list[Path] = []
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                mtimes.append(path.stat().st_mtime)
            except OSError as e:
                print(f"  [WARN] 读取失败，跳过：{path}（{e}）")
                continue
            layer_paths.append(path)
            if lname not in _CONFIRM_LAYERS:
                continue
            for ln, line in enumerate(text.splitlines(), 1):
                if not line.lstrip().startswith("|"):     # 只统计表格行，忽略图例/说明行
                    continue
                if "⬜" in line:
                    pending.append((lname, path, ln, line))
                elif "✅" in line:
                    confirmed += 1
        layer_times.append((lname, max(mtimes) if mtimes else None, layer_paths))

    print(f"[{title}] 确认列：已确认 {confirmed} ｜ 未拍板 {len(pending)}")
    for lname, path, ln, line in pending:
        print(f"  [TODO] [{lname}] {path.relative_to(ROOT)}:{ln}  {_brief(line)}")

    # 层间新鲜度：Lk 的每个文件应晚于 L1..L(k-1) 的最后修改时间
    base: float | None = None
    base_name = ""
    for lname, latest, layer_paths in layer_times:
        if base is not None and latest is not None:
            for path in layer_paths:
                try:
                    if path.stat().st_mtime < base:
                        at = datetime.fromtimestamp(base).strftime("%Y-%m-%d %H:%M")
                        hint = _LAYER_HINTS.get(lname, "重跑该级").replace("<模块>", title)
                        print(f"  [WARN] {path.relative_to(ROOT)} 早于「{base_name}」最后修改（{at}），"
                              f"可能在确认前生成，建议重跑：{hint}")
                except OSError:
                    continue
        if latest is not None and (base is None or latest > base):
            base, base_name = latest, lname
    return len(pending)


def main(argv):
    mods = [_clean(a) for a in argv if _clean(a)] or _modules()
    if not mods:
        print("未发现任何模块（output/01_business、02_split_requirements 为空）")
        return 0
    total = 0
    sys_map = sorted(BUSINESS_DIR.glob("00-*-业务全景图.md")) if BUSINESS_DIR.is_dir() else []
    if sys_map:                                       # 系统级全景图影响所有模块，先扫
        total += scan("系统级", [(L1, sys_map)])
        print()
    for m in mods:
        stems = _req_stems(m)
        layers = [
            (L1, _layer1_files(m)),
            (L2, _layer2_files(m, stems)),
            (L3, _layer3_files(m)),
            (L4, _layer4_files(m)),
            (L5, _layer5_files(m)),
        ]
        total += scan(m, layers)
        print()
    print("RESULT:", "PASS（确认列已全部拍板）" if total == 0
          else f"FAIL（{total} 项未拍板，确认后再放行下一级）")
    return total    # 返回未拍板数：供库调用（run._confirmation_gate）计数展示；CLI 入口另行包成退出码 0/1


if __name__ == "__main__":
    # CLI 退出码保持 0/1 语义（非零即 FAIL，CI 判断不受未拍板数影响）
    sys.exit(0 if main(sys.argv[1:]) == 0 else 1)
