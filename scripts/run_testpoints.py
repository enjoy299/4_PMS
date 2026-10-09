#!/usr/bin/env python3
"""
设计脚本（第一步）—— 需求理解（自适应）+ 测试点 + 风险清单与待确认汇总。

使用方法：
    python scripts/run_testpoints.py              # 所有模块：生成测试点与风险台账
    python scripts/run_testpoints.py 知识管理      # 指定模块：生成测试点与风险台账

说明：
    需求理解已存在（03_design 根级固定名 / 子目录最新批次）则直接消费，不重复生成；
    缺失时在同一对话内先补产需求理解，再挖测试点。
    产出后请对确认列（⬜）人工拍板（换成 ✅ 结论），再运行 run_testcases.py 生成用例。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.designer_agent import DesignerAgent


def main():
    agent = DesignerAgent()

    if len(sys.argv) > 1:
        module_name = sys.argv[1]
        print(f"设计第一步（测试点+风险台账）：{module_name}")
        agent.design_testpoints(module_name)
        return

    agent.testpoints_all()


if __name__ == "__main__":
    main()
