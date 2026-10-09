"""批次产物归档：03/04/05 每类文件保留最近 N 个时间戳批次，其余移入同级 archive/。

用法：
  python scripts/_archive_batches.py --dry-run          # 预演：只打印计划，不移动
  python scripts/_archive_batches.py                    # 实际归档（默认保留最近 3 批）
  python scripts/_archive_batches.py --keep 5           # 自定义保留批次数
  python scripts/_archive_batches.py 知识管理 --dry-run  # 只处理指定模块

规则（与 output/README.md「产物生命周期」一致）：
  - 批次命名约定：`{名称}_{YYYYMMDD_HHMM}.{ext}`（也兼容秒级 `HHMMSS`）；
    无时间戳后缀的文件（单跑产物）不动；
  - 分组：同一目录下去掉时间戳后同名的文件算一类，按时间戳保留最新 N 个；
  - 其余移动到该目录下的 archive/ 子目录（文件名不变）；
  - archive/ 不参与本脚本扫描，也不被 _lint_confirmations.py 统计。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_DIRS = [
    ROOT / "output" / "03_design" / "test_points",
    ROOT / "output" / "03_design" / "test_cases",
    ROOT / "output" / "04_review",
    ROOT / "output" / "05_export",
]
TS = re.compile(r"^(?P<base>.+)_(?P<ts>\d{8}_\d{4,6})$")
CLEAN = re.compile(r"^\d+[、_.\-\s]+")


def _clean(name: str) -> str:
    """去除数字前缀（'7、知识管理' -> '知识管理'）。"""
    return CLEAN.sub("", name).strip()


def _collect(module_filter: list[str]):
    """收集批次文件，按 (所在目录, 基础名) 分组为 [(时间戳, 路径)]。"""
    buckets: dict[tuple, list[tuple[str, Path]]] = {}
    for base_dir in BASE_DIRS:
        if not base_dir.is_dir():
            continue
        for path in sorted(base_dir.rglob("*")):
            if not path.is_file() or "archive" in path.parts:
                continue
            m = TS.match(path.stem)
            if not m:                                # 无时间戳的文件不动
                continue
            if module_filter:
                rel = path.relative_to(base_dir)
                if len(rel.parts) < 2 or _clean(rel.parts[0]) not in module_filter:
                    continue
            buckets.setdefault((path.parent, m.group("base")), []).append(
                (m.group("ts"), path))
    return buckets


def main(argv):
    dry, keep, mods = False, 3, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--dry-run":
            dry = True
        elif a == "--keep" and i + 1 < len(argv):
            keep = int(argv[i + 1])
            i += 1
        else:
            mods.append(_clean(a))
        i += 1

    buckets = _collect(mods)
    groups, moved = 0, 0
    for (parent, stem), items in sorted(buckets.items()):
        items.sort(key=lambda x: x[0])               # 按时间戳升序
        if len(items) <= keep:
            continue
        groups += 1
        old = items[:-keep]
        print(f"[{parent.relative_to(ROOT)}] {stem}：共 {len(items)} 批，"
              f"保留最近 {keep}，归档 {len(old)}")
        archive_dir = parent / "archive"
        for _ts, path in old:
            dest = archive_dir / path.name
            print(f"  [{'PLAN' if dry else 'MOVE'}] {path.name}")
            if not dry:
                archive_dir.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    print(f"    [SKIP] 目标已存在，跳过：{dest.name}")
                    continue
                path.rename(dest)
            moved += 1
    head = "[DRY-RUN] " if dry else ""
    tail = "（预演，未实际移动）" if dry else ""
    print(f"\n{head}共 {groups} 组超量，归档 {moved} 个文件{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
