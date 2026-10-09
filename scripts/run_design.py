#!/usr/bin/env python3
"""
设计脚本 —— 两步连续：测试点 + 风险台账 -> 测试用例（无确认停顿，CI 兼容）。

使用方法：
    python scripts/run_design.py              # 所有模块：两步连续（测试点 -> 用例）
    python scripts/run_design.py 知识管理      # 指定模块：两步连续

说明：
    推荐分步执行以获得拍板门禁：
    先 python scripts/run_testpoints.py 模块 -> 对确认列拍板（⬜ -> ✅）->
    再 python scripts/run_testcases.py 模块。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.designer_agent import DesignerAgent


def main():
    agent = DesignerAgent()

    if len(sys.argv) > 1:
        module_name = sys.argv[1]
        print(f"设计（两步连续：测试点 -> 用例）：{module_name}")
        agent.design(module_name)
        return

    agent.design_all()


if __name__ == "__main__":
    main()
