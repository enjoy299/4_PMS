#!/usr/bin/env python3
"""
测试执行脚本 —— 使用 Playwright 执行测试用例。

使用方法：
    python scripts/run_test.py              # 执行所有模块的测试
    python scripts/run_test.py 知识管理      # 执行指定模块的测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.tester_agent import TesterAgent
from core.config import CASES_DIR, DESIGN_WORKSPACE_DIR, find_module_file


def main():
    agent = TesterAgent()

    if len(sys.argv) > 1:
        module_name = sys.argv[1]
        print(f"执行测试：{module_name}")
        
        # 先查找 Markdown 格式用例
        test_cases_dir = DESIGN_WORKSPACE_DIR / "test_cases"
        case_file = find_module_file(test_cases_dir, module_name, [".md"])
        if case_file:
            agent.run_suite_from_md(case_file)
            return
        
        # 回退到 YAML 格式
        case_file = find_module_file(CASES_DIR, module_name, [".yaml"])
        if case_file:
            agent.run_suite(case_file.stem)
            return
        
        print(f"未找到与 '{module_name}' 匹配的用例文件")
        print(f"请先运行 python scripts/run_design.py {module_name}")
        return

    agent.run_all_suites()


if __name__ == "__main__":
    main()
