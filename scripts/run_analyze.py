#!/usr/bin/env python3
"""
分析脚本 —— 读取需求文档，生成提示词，等待 Qoder 分析结果。

使用方法：
    python scripts/run_analyze.py              # 分析所有需求文档
    python scripts/run_analyze.py 知识管理      # 分析指定模块
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.analyst_agent import AnalystAgent
from core.config import SPEC_DIR, find_module_file


def main():
    agent = AnalystAgent()

    # 如果指定了模块名，只分析该模块
    if len(sys.argv) > 1:
        module_name = sys.argv[1]
        doc = find_module_file(SPEC_DIR, module_name, [".md", ".txt"])
        if doc:
            print(f"分析模块：{doc.stem}")
            agent.analyze(doc)
        else:
            print(f"未找到与 '{module_name}' 匹配的需求文档（目录：{SPEC_DIR}）")
        return

    # 没有指定模块，分析所有文档
    agent.analyze_all()


if __name__ == "__main__":
    main()
