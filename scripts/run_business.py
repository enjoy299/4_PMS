#!/usr/bin/env python3
"""
独立脚本：为指定模块生成业务全景图（业务梳理阶段）。

用法：
    python scripts/run_business.py              # 所有模块
    python scripts/run_business.py 首页          # 指定模块（可带数字前缀，如 1、首页）
"""
import sys
from pathlib import Path

# 把项目根目录加入搜索路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from agents.business_agent import BusinessAgent

console = Console()


def main():
    console.print("\n[bold cyan]>>> 业务梳理（独立脚本）[/bold cyan]\n")

    module_name = sys.argv[1] if len(sys.argv) > 1 else None

    agent = BusinessAgent()

    if module_name:
        console.print(f"[bold]模块：{module_name}[/bold]")
        agent.analyze(module_name)
    else:
        console.print("[bold]所有模块[/bold]")
        agent.analyze_all()

    console.print("\n[bold green]>>> 业务梳理完成，业务全景图输出至 output/01_business/[/bold green]\n")


if __name__ == "__main__":
    main()
