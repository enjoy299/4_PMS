#!/usr/bin/env python3
"""
审核脚本 —— 审核测试用例质量。

使用方法：
    python scripts/run_review.py              # 审核所有模块
    python scripts/run_review.py 知识管理      # 审核指定模块
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.reviewer_agent import ReviewerAgent
from core.config import CASES_DIR, DESIGN_WORKSPACE_DIR


def main():
    agent = ReviewerAgent()

    if len(sys.argv) > 1:
        module_name = sys.argv[1]
        print(f"审核模块：{module_name}")
        agent.review(module_name)
        return

    agent.review_all()


if __name__ == "__main__":
    main()
