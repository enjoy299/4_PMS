#!/usr/bin/env python3
"""
设计脚本（第二步）—— 消费最新批次测试点（含确认列）生成测试用例。

使用方法：
    python scripts/run_testcases.py              # 所有模块：生成测试用例
    python scripts/run_testcases.py 知识管理      # 指定模块：生成测试用例

前置条件：
    必须先运行 run_testpoints.py 生成测试点批次（无批次时本脚本会报错阻止），
    建议先对测试点确认列拍板（⬜ -> ✅）再生成用例，确保用例建立在已拍板事实之上。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.designer_agent import DesignerAgent


def main():
    agent = DesignerAgent()

    if len(sys.argv) > 1:
        module_name = sys.argv[1]
        print(f"设计第二步（测试用例）：{module_name}")
        agent.design_cases(module_name)
        return

    agent.cases_all()


if __name__ == "__main__":
    main()
