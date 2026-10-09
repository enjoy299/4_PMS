#!/usr/bin/env python3
"""
探索测试脚本 —— 自由遍历系统所有页面，寻找问题。

使用方法：
    python scripts/run_explore.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.explorer_agent import ExplorerAgent


def main():
    print("=" * 50)
    print("  探索性测试：遍历所有页面，寻找潜在问题")
    print("=" * 50)
    agent = ExplorerAgent()
    agent.run_all()


if __name__ == "__main__":
    main()
