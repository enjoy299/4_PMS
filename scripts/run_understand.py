#!/usr/bin/env python3
"""
独立脚本：为指定模块生成需求理解文档。

用法：
    python scripts/run_understand.py              # 所有模块
    python scripts/run_understand.py 项目管理      # 指定模块
"""
import sys
from pathlib import Path

# 把项目根目录加入搜索路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from agents.understanding_agent import UnderstandingAgent

console = Console()


def main():
    console.print("\n[bold cyan]>>> 需求理解（独立脚本）[/bold cyan]\n")
    
    module_name = sys.argv[1] if len(sys.argv) > 1 else None
    
    agent = UnderstandingAgent()
    
    if module_name:
        console.print(f"[bold]模块：{module_name}[/bold]")
        agent.understand(module_name)
    else:
        console.print("[bold]所有模块[/bold]")
        agent.understand_all()
    
    console.print("\n[bold green]>>> 需求理解完成[/bold green]\n")


if __name__ == "__main__":
    main()
