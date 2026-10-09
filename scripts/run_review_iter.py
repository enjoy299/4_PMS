#!/usr/bin/env python3
"""
评审→优化迭代闭环脚本。

使用方法：
    python scripts/run_review_iter.py              # 所有模块迭代优化
    python scripts/run_review_iter.py 知识管理      # 指定模块迭代优化
    python scripts/run_review_iter.py 知识管理 --max 5  # 最大迭代 5 轮
    python scripts/run_review_iter.py 知识管理 --strict   # 必须完全通过才停止
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.review_feedback import ReviewIterateController
from core.config import CASES_DIR


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = {a for a in sys.argv[1:] if a.startswith("-")}
    module_name = args[0] if args else None

    max_iter = 3
    if "--max" in flags:
        rest = [a for a in sys.argv[1:] if not a.startswith("-")]
        if len(rest) > (1 if module_name else 0):
            try:
                max_iter = int(rest[1 if module_name else 0])
            except ValueError:
                pass

    strict = "--strict" in flags
    pass_threshold = "pass" if strict else "conditional_pass"

    if module_name:
        print(f"评审→优化迭代：{module_name}（最大 {max_iter} 轮）")
        ctrl = ReviewIterateController(
            module_name=module_name,
            max_iterations=max_iter,
            pass_threshold=pass_threshold,
        )
        result = ctrl.run()
        _print_result(result)
        return

    # 全部模块
    parents = [d.name for d in sorted(CASES_DIR.iterdir())
               if d.is_dir() and d.name != "archive"] if CASES_DIR.exists() else []
    if not parents:
        print("未找到用例目录，请先运行 python run.py testcases")
        return

    print(f"评审→优化迭代：全部 {len(parents)} 个模块（最大 {max_iter} 轮/模块）")
    for mod in parents:
        print(f"\n--- 模块：{mod} ---")
        ctrl = ReviewIterateController(
            module_name=mod,
            max_iterations=max_iter,
            pass_threshold=pass_threshold,
        )
        result = ctrl.run()
        _print_result(result)


def _print_result(result: dict):
    if result["success"]:
        print(f"  成功：{result['iterations']} 轮后通过（{result['final_verdict']}）")
    else:
        print(f"  未通过：{result['iterations']} 轮后结论为 {result['final_verdict']}")
    if result.get("final_report"):
        print(f"  最终报告：{result['final_report']}")


if __name__ == "__main__":
    main()
