#!/usr/bin/env python3
"""
AI Web 自动化测试框架 —— 启动入口（Qoder 版）

架构：
  AI 分析由 Qoder 对话完成（提示词自动复制到剪贴板），
  浏览器操作有两种方式：
    1. Playwright 纯脚本（test / explore 命令）
    2. Qoder 桥接模式（qoder-plan / qoder-explore 命令）
       框架生成测试计划 → 在 Qoder 对话中执行 → Qoder 用内置 MCP 工具操控浏览器

使用方法：
    python run.py pipeline     # 完整流水线：业务梳理 -> 分析 -> 理解 -> 设计（两步）-> 评审 -> 导出 -> 执行
    python run.py business     # 业务梳理：探索产物+需求 -> 业务全景图
    python run.py analyze      # 分析需求文档，提取测试点
    python run.py testpoints   # 设计第一步：需求理解（自适应）+ 测试点 + 风险台账
    python run.py testcases    # 设计第二步：消费最新批次测试点 -> 生成测试用例
    python run.py design       # 设计两步连续（testpoints + testcases，无确认停顿，CI 兼容）
    python run.py review       # 审核测试用例质量
    python run.py export [--force]  # 导出 Excel 用例（确认列门禁：未拍板即阻断，--force 豁免）
    python run.py test         # 使用 Playwright 执行测试用例（脚本模式）
    python run.py triage       # 结果分流：列出可分流的 run（加 run_id 则直接分流）
    python run.py triage 知识管理_20260914_173000 --llm  # 含 LLM 复判的分流与发版门禁
    python run.py qoder-plan   # 生成 Qoder 测试计划（推荐，无需额外 API）
    python run.py explore      # 探索性测试（脚本模式）
    python run.py qoder-explore # 生成 Qoder 探索计划
    python run.py prototype    # 截取在线原型图
    python run.py help         # 显示帮助信息
"""
import sys
from pathlib import Path

# 把项目根目录加入搜索路径
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

BANNER = """
[bold cyan]  AI Web Test Framework (Qoder Edition)[/bold cyan]
  AI 分析由 Qoder 对话完成 | 浏览器由 Playwright / Qoder 桥接操控
  Type [bold]python run.py help[/bold] for commands
"""


def print_banner():
    """显示欢迎横幅。"""
    console.print(Panel(BANNER, border_style="cyan", expand=False))


def _confirmation_gate(modules: list[str] | None, *, blocking: bool, stage: str) -> bool:
    """确认列放行门禁：调用 scripts/_lint_confirmations.py 统计未拍板项。

    门禁口径与手工命令一致（python scripts/_lint_confirmations.py）：
      产物确认列中仍有任意未确认问句即 FAIL。
      blocking=True：FAIL 直接阻断并退出（exit 1），用于对外交付边界（export）；
      blocking=False：只打醒目告警、流程继续（草稿先行的工作流：testcases / pipeline）。
    返回 True=放行 / False=未通过（仅非阻塞模式会返回 False）。

    注：scripts/ 无 __init__.py，走 PEP 420 命名空间包导入（项目根已在 sys.path[0]）。
    """
    from scripts._lint_confirmations import main as lint_main

    console.print(f"\n[bold cyan]>>> 确认列放行检查（{stage}）[/bold cyan]")
    pending = lint_main(modules or [])          # None/[] -> lint 自动发现全部模块
    if pending == 0:
        console.print("  [green]√ 确认列已全部拍板，放行[/green]")
        return True
    if blocking:
        console.print(f"  [red]× {pending} 项未拍板，已阻断：{stage}[/red]")
        console.print("  [yellow]处理：按上方 [TODO] 清单，把产物中「确认结论(业务填)」列的"
                      "未确认问句就地改为已确认结论，再重跑本命令[/yellow]")
        console.print("  [yellow]豁免：python run.py export --force"
                      "（明知未拍板仍导出，仅供内部评审，不建议对外交付）[/yellow]")
        sys.exit(1)
    console.print(f"  [yellow]! {pending} 项未拍板：下游将按待确认生成（引用原问句），"
                  f"拍板后请重跑以更新为确定性内容[/yellow]")
    return False


# ========== 命令函数（全部同步执行，不再需要 asyncio） ==========

def cmd_pipeline():
    """完整流水线：业务梳理 -> 分析 -> 理解 -> 设计（两步）-> 评审 -> 导出 -> 执行。"""
    console.print("\n[bold green]>>> 完整流水线启动[/bold green]\n")

    from agents.business_agent import BusinessAgent
    from agents.analyst_agent import AnalystAgent
    from agents.understanding_agent import UnderstandingAgent
    from agents.designer_agent import DesignerAgent
    from agents.reviewer_agent import ReviewerAgent
    from agents.excel_export_agent import ExcelExportAgent
    from agents.qoder_bridge import generate_test_plan

    console.print("[bold]Step 1/8: 业务梳理 -> 生成业务全景图[/bold]")
    business = BusinessAgent()
    business.analyze_all()

    console.print("\n[bold]Step 2/8: 分析需求 -> 拆分需求文档[/bold]")
    analyst = AnalystAgent()
    analyst.analyze_all()

    console.print("\n[bold]Step 3/8: 需求理解 -> 生成需求理解文档[/bold]")
    understanding = UnderstandingAgent()
    understanding.understand_all()

    console.print("\n[bold]Step 4/8: 设计第一步 -> 需求理解（自适应）+ 测试点 + 风险台账[/bold]")
    designer = DesignerAgent()
    designer.testpoints_all()

    console.print("\n[bold]Step 5/8: 设计第二步 -> 测试用例（消费最新批次测试点）[/bold]")
    designer.cases_all()

    console.print("\n[bold]Step 6/8: 评审测试用例[/bold]")
    reviewer = ReviewerAgent()
    reviewer.review_all()

    console.print("\n[bold]Step 7/8: 导出 Excel 用例[/bold]")
    # pipeline 为连续模式（无拍板停顿）：门禁只提醒不阻断，导出物仅供内部评审
    _confirmation_gate(None, blocking=False,
                       stage="导出前（pipeline 连续模式，提醒不阻断）")
    exporter = ExcelExportAgent()
    exporter.export_all()

    console.print("\n[bold]Step 8/8: 生成 Qoder MCP 测试计划（主执行路径）[/bold]")
    generate_test_plan()
    console.print("[dim]  下一步：在 Qoder 对话中读取 qoder_workspace/test_plan.md 执行测试[/dim]")
    console.print("[dim]  脚本模式（备用/CI，不依赖 Qoder）：python run.py test[/dim]")
    console.print("[dim]  执行完成后分流与出报告：python run.py triage --list → python run.py triage <run_id>[/dim]")

    console.print("\n[bold green]>>> 流水线完成[/bold green]\n")


def cmd_business():
    """业务梳理：交叉比对探索产物与需求，生成业务全景图。支持 `python run.py business 模块名`。"""
    console.print("\n[bold cyan]>>> 业务梳理 -> 业务全景图[/bold cyan]\n")
    from agents.business_agent import BusinessAgent
    agent = BusinessAgent()
    module_name = sys.argv[2] if len(sys.argv) > 2 else None
    if module_name:
        agent.analyze(module_name)
    else:
        agent.analyze_all()


def cmd_analyze():
    """分析需求文档，提取测试点。"""
    console.print("\n[bold cyan]>>> 分析需求[/bold cyan]\n")
    from agents.analyst_agent import AnalystAgent
    agent = AnalystAgent()
    agent.analyze_all()


def cmd_understand():
    """生成需求理解文档。"""
    console.print("\n[bold cyan]>>> 需求理解[/bold cyan]\n")
    from agents.understanding_agent import UnderstandingAgent
    agent = UnderstandingAgent()
    agent.understand_all()


def cmd_testpoints():
    """设计第一步：需求理解（自适应）+ 测试点 + 风险台账。支持 `python run.py testpoints 模块名`。"""
    console.print("\n[bold cyan]>>> 设计第一步：测试点 + 风险台账（需求理解自适应）[/bold cyan]\n")
    from agents.designer_agent import DesignerAgent
    agent = DesignerAgent()
    module_name = sys.argv[2] if len(sys.argv) > 2 else None
    if module_name:
        agent.design_testpoints(module_name)
    else:
        agent.testpoints_all()


def cmd_testcases():
    """设计第二步：消费最新批次测试点生成测试用例。支持 `python run.py testcases 模块名`。"""
    console.print("\n[bold cyan]>>> 设计第二步：测试用例（消费最新批次测试点）[/bold cyan]\n")
    from agents.designer_agent import DesignerAgent
    agent = DesignerAgent()
    module_name = sys.argv[2] if len(sys.argv) > 2 else None
    # 软门禁：测试点确认列未拍板时告警不阻断（允许先生成用例草稿再拍板的重跑顺序）
    _confirmation_gate([module_name] if module_name else None, blocking=False,
                       stage="测试用例生成前（未拍板项将按待确认生成）")
    if module_name:
        agent.design_cases(module_name)
    else:
        agent.cases_all()


def cmd_design():
    """设计两步连续：测试点 -> 用例（无确认停顿，CI 兼容；推荐分步以获得拍板门禁）。"""
    console.print("\n[bold cyan]>>> 设计测试用例（两步连续：测试点 -> 用例）[/bold cyan]\n")
    console.print("[dim]推荐分步拍板：python run.py testpoints 模块 → 拍板确认列 → python run.py testcases 模块[/dim]\n")
    from agents.designer_agent import DesignerAgent
    agent = DesignerAgent()
    agent.design_all()


def cmd_review():
    """评审测试用例质量。"""
    console.print("\n[bold cyan]>>> 评审测试用例[/bold cyan]\n")
    from agents.reviewer_agent import ReviewerAgent
    agent = ReviewerAgent()
    agent.review_all()


def cmd_review_iter():
    """评审→优化迭代闭环：评审用例 → 解析反馈 → 定向优化 → 再评审，直到通过或达上限。"""
    args = [a for a in sys.argv[2:] if not a.startswith("-")]
    flags = {a for a in sys.argv[2:] if a.startswith("-")}
    module_name = args[0] if args else None
    max_iter = 3
    if "--max" in flags:
        idx = [a for a in sys.argv[2:] if a.startswith("-")].index("--max")
        # --max N 形式：取下一个非 flag 参数
        rest = [a for a in sys.argv[2:] if not a.startswith("-")]
        if len(rest) > (1 if module_name else 0):
            try:
                max_iter = int(rest[1 if module_name else 0])
            except ValueError:
                pass

    console.print("\n[bold cyan]>>> 评审→优化迭代闭环[/bold cyan]\n")
    console.print(f"  模块：{module_name or '全部'} ｜ 最大迭代：{max_iter} 轮")
    console.print(f"  通过阈值：{'完全通过' if '--strict' in flags else '有条件通过即通过'}\n")

    from core.review_feedback import ReviewIterateController

    if module_name:
        ctrl = ReviewIterateController(
            module_name=module_name,
            max_iterations=max_iter,
            pass_threshold=("pass" if "--strict" in flags else "conditional_pass"),
        )
        result = ctrl.run()
        _print_iter_result(result)
    else:
        # 全部模块：逐个迭代
        from core.config import CASES_DIR
        parents = [d.name for d in sorted(CASES_DIR.iterdir())
                   if d.is_dir() and d.name != "archive"] if CASES_DIR.exists() else []
        if not parents:
            console.print("[yellow]未找到用例目录，请先运行 python run.py testcases[/yellow]")
            return
        for mod in parents:
            console.print(f"\n[bold]--- 模块：{mod} ---[/bold]")
            ctrl = ReviewIterateController(
                module_name=mod,
                max_iterations=max_iter,
                pass_threshold=("pass" if "--strict" in flags else "conditional_pass"),
            )
            result = ctrl.run()
            _print_iter_result(result)


def _print_iter_result(result: dict):
    """打印迭代结果摘要。"""
    if result["success"]:
        console.print(
            f"[bold green]  迭代成功：{result['iterations']} 轮后通过"
            f"（{result['final_verdict']}）[/bold green]"
        )
    else:
        console.print(
            f"[bold red]  迭代未通过：{result['iterations']} 轮后"
            f"结论为 {result['final_verdict']}，建议人工介入[/bold red]"
        )
    if result.get("final_report"):
        console.print(f"  [dim]最终报告：{result['final_report']}[/dim]")


def cmd_export():
    """导出测试用例到 Excel（硬门禁：确认列未拍板即阻断；--force 显式豁免）。"""
    force = "--force" in sys.argv[2:]
    console.print("\n[bold cyan]>>> 导出 Excel 用例[/bold cyan]\n")
    if force:
        console.print("  [yellow]--force：跳过确认列门禁，导出物仅供内部评审[/yellow]")
    else:
        # 对外交付边界：未拍板即阻断（exit 1，CI 可感知）
        _confirmation_gate(None, blocking=True, stage="Excel 导出")
    from agents.excel_export_agent import ExcelExportAgent
    agent = ExcelExportAgent()
    agent.export_all()


def cmd_test():
    """使用 Playwright 执行测试用例（脚本模式 · 备用/CI 路径；推荐主路径用 qoder-plan）。"""
    console.print("\n[bold cyan]>>> 执行测试（脚本模式 · 备用/CI 路径）[/bold cyan]\n")
    console.print("[dim]推荐主执行路径：python run.py qoder-plan（Qoder MCP 桥接）[/dim]\n")
    from agents.tester_agent import TesterAgent
    agent = TesterAgent()
    agent.run_all_suites()


def cmd_qoder_plan():
    """生成 Qoder 测试计划（推荐模式，无需额外 API）。

    用法：
        python run.py qoder-plan [模块名] [--p0|--retry]
          --p0     只跑 P0 级用例（冒烟/关键路径）
          --retry  只重跑上次失败的用例
          不加参数  全量执行
    """
    console.print("\n[bold green]>>> 生成 Qoder 测试计划[/bold green]\n")

    args = [a for a in sys.argv[2:] if not a.startswith("-")]
    flags = {a.lower() for a in sys.argv[2:] if a.startswith("-")}
    module_name = args[0] if args else None

    # 确定执行层级
    if "--p0" in flags:
        level = "p0"
    elif "--retry" in flags:
        level = "retry"
    else:
        level = "full"

    level_label = {"p0": "P0 冒烟", "retry": "重跑失败项", "full": "全量"}[level]
    console.print(f"[dim]执行层级：{level_label}｜模块：{module_name or '全部'}[/dim]\n")

    from agents.qoder_bridge import generate_test_plan
    generate_test_plan(module_name, level=level)


def cmd_solidify():
    """把桥接验证通过的用例固化为 Playwright 脚本（Phase 2）。

    用法：
        python run.py solidify 模块名 [--all|--p0]
          --all  包含 fail 的用例（AI 标注为待修复）
          --p0   只固化 P0 级且通过的用例
          不加参数  只固化 status=pass 的用例（默认）
    """
    console.print("\n[bold green]>>> 生成脚本固化计划[/bold green]\n")

    args = [a for a in sys.argv[2:] if not a.startswith("-")]
    flags = {a.lower() for a in sys.argv[2:] if a.startswith("-")}
    module_name = args[0] if args else None

    if not module_name:
        console.print("[red]错误：请指定模块名，如：python run.py solidify 工业APP[/red]")
        sys.exit(1)

    # 确定固化范围
    if "--all" in flags:
        level = "all"
    elif "--p0" in flags:
        level = "p0"
    else:
        level = "pass_only"

    level_label = {"pass_only": "仅通过项", "all": "全部（含失败）", "p0": "P0 且通过"}[level]
    console.print(f"[dim]固化范围：{level_label}｜模块：{module_name}[/dim]\n")

    from agents.solidify_agent import generate_solidify_plan
    result = generate_solidify_plan(module_name, level=level)

    if not result:
        console.print("[red]固化计划生成失败，请检查上方日志[/red]")
        sys.exit(1)


def cmd_explore():
    """探索性测试：遍历系统所有页面，寻找潜在 bug（脚本模式）。"""
    console.print("\n[bold cyan]>>> 探索性测试（脚本模式）[/bold cyan]\n")
    from agents.explorer_agent import ExplorerAgent
    agent = ExplorerAgent()
    agent.run_all()


def cmd_qoder_explore():
    """生成 Qoder 探索测试计划。"""
    console.print("\n[bold green]>>> 生成 Qoder 探索计划[/bold green]\n")

    from agents.qoder_bridge import generate_explore_plan
    generate_explore_plan()


def cmd_prototype():
    """截取在线原型页面截图。"""
    console.print("\n[bold cyan]>>> 截取在线原型[/bold cyan]\n")
    from core.prototype_loader import PrototypeLoader
    loader = PrototypeLoader()
    results = loader.capture_all()
    if not results:
        console.print("  未配置在线原型，请编辑 [yellow]inputs/online_prototypes.yaml[/yellow]")
    for module, paths in results.items():
        console.print(f"  {module}: {len(paths)} 张截图已保存")


def cmd_triage():
    """结果分流：读 records.jsonl → 三层判定 → 分流产物与报告。

    用法：`python run.py triage <run_id>`（加 `--llm` 先走一遍 LLM 复判；加 `--validate`
    只做契约与未执行缺口校验）；不带参数或 `--list` 列出可用 run。
    """
    args = [a for a in sys.argv[2:] if not a.startswith("-")]
    flags = {a for a in sys.argv[2:] if a.startswith("-")}
    from agents.triage_agent import triage_pipeline
    from core.triage import list_runs

    if "--list" in flags or not args:
        runs = list_runs()
        if not runs:
            console.print("  [yellow]暂无分流记录[/yellow]：先跑 [bold]python run.py qoder-plan 模块名[/bold] "
                          "生成带契约的计划，让 Qoder 按契约写 records.jsonl；或用 "
                          "[bold]python scripts/_convert_legacy_result.py <json>[/bold] 转换历史结果")
            return
        console.print("\n[bold cyan]>>> 可分流的 run（新的在前）[/bold cyan]\n")
        for rid in runs:
            console.print(f"  [bold]{rid}[/bold]")
        console.print("\n[dim]用法：python run.py triage <run_id> [--llm|--validate][/dim]\n")
        return

    rid = args[0]

    # 校验模式（MCP 为唯一入口时尤其重要）：只查契约合规与未执行缺口，不做分流、不出报告
    if "--validate" in flags:
        from core.triage import (load_records, load_plan_cases, diff_plan_vs_records,
                                 validate_record)
        records, dups, malformed = load_records(rid)
        gaps = diff_plan_vs_records(load_plan_cases(rid), records)
        bad = {r.get("case_id", "?"): v for r in records for v in [validate_record(r)] if v}
        console.print(f"  计划 {gaps['planned']} 条 ｜ 已记录 {gaps['recorded']} 条 ｜ "
                      f"缺口 {len(gaps['missing'])} 条 ｜ 计划外 {len(gaps['extra'])} 条")
        if gaps["missing"]:
            console.print(f"  [yellow]未执行（计划内但无记录）：{', '.join(gaps['missing'])}[/yellow]")
        if gaps["extra"]:
            console.print(f"  [red]不在计划内（case_id 可能写错）：{', '.join(gaps['extra'])}[/red]")
        for cid, errs in bad.items():
            console.print(f"  [red]契约违规 {cid}：{'; '.join(errs)}[/red]")
        if dups or malformed:
            console.print(f"  [dim]重复 case_id {dups} 条｜损坏行 {malformed} 行[/dim]")
        if not load_plan_cases(rid):
            console.print("  [dim]本 run 无 plan_cases.json（旧数据或人工指定的 run），缺口校验已跳过[/dim]")
        ok = not (gaps["missing"] or gaps["extra"] or bad or malformed)
        # 状态标记不用 ✓ ✗ ✅ ❌：中文 Windows 控制台是 cp936，这类字符会直接 UnicodeEncodeError
        console.print("  [green]√ 校验通过[/green]" if ok else "  [red]× 校验不通过[/red]")
        sys.exit(0 if ok else 1)

    console.print(f"\n[bold cyan]>>> 结果分流：{rid}[/bold cyan]\n")
    out = triage_pipeline(rid, do_llm="--llm" in flags)
    if out.get("error"):
        console.print(f"  [red]× {out['error']}[/red]")
        sys.exit(1)
    s, g = out["summary"], out["gate"]
    console.print(f"  总 {s['总用例']} ｜ 通过 {s['通过']} ｜ 缺陷 {s['真实缺陷']} ｜ "
                  f"环境 {s['环境阻塞']} ｜ 数据 {s['数据前置未满足']} ｜ 用例 {s['用例问题']} ｜ "
                  f"执行 {s['执行未到位']} ｜ 待裁决 {s['待人工裁决']}")
    console.print(f"  通过率 {s['通过率']}% ｜ 有效通过率 {s['有效通过率']}%"
                  f"（移出分母 {s['移出分母']}） ｜ 人工拍板 {out['human_decided']} 条")
    if out["llm"].get("reviewed"):
        console.print(f"  LLM 复判：送判 {out['llm']['reviewed']} 条，可解析 "
                      f"{out['llm']['parsed']} 条")

    def rel(p) -> str:
        """产物路径按相对项目根打印：绝对路径在 80 列终端里会把一行挤成三行。"""
        try:
            return str(Path(str(p)).relative_to(Path(__file__).parent))
        except ValueError:                      # 不在项目内（自定义输出目录）就原样给出
            return str(p)

    for key, val in out["artifacts"].items():
        for one in (val if isinstance(val, list) else [val]):
            console.print(f"  [dim]{key}: {rel(one)}[/dim]")
    verdict = {"allow": "[bold green]建议发版[/bold green]",
               "reject": "[bold red]不具备出结论条件[/bold red]",
               "na": "[bold yellow]N/A（CI 浅分流，未做缺陷定性）[/bold yellow]"}[g["verdict"]]
    console.print(f"\n  发版建议：{verdict}")
    if g["verdict"] != "na":
        # `na` 的 note 与上面的文案同义，再追一行只会把屏幕挤到换行
        console.print(f"  [dim]{g['note']}[/dim]")
    if g["pending"]:
        console.print(f"  [yellow]待裁决 {g['pending']} 项[/yellow]：打开 "
                      f"output/06_reports/triage/{rid}/pending_review.md；或在人在场的终端重跑本命令逐条拍板")
    if g["blocks_exit_code"]:
        sys.exit(1)


def cmd_help():
    """显示帮助信息。"""
    table = Table(box=box.ROUNDED, title="可用命令", border_style="cyan")
    table.add_column("命令", style="bold yellow", width=14)
    table.add_column("说明")
    table.add_column("模式", style="dim")
    table.add_row("pipeline", "完整流水线：业务梳理 -> 分析 -> 理解 -> 设计（两步）-> 评审 -> 导出 -> 执行", "全部")
    table.add_row("business", "交叉比对探索产物与需求 -> 生成业务全景图", "第 1 步")
    table.add_row("analyze", "分析需求文档 -> 拆分模块化需求", "第 2 步")
    table.add_row("understand", "生成需求理解文档 -> 用户确认", "第 3 步")
    table.add_row("testpoints", "设计第一步：需求理解（自适应）+ 测试点 + 风险台账 -> 拍板", "第 4 步·A")
    table.add_row("testcases", "设计第二步：消费已拍板测试点 -> 生成测试用例 -> 拍板", "第 4 步·B")
    table.add_row("design", "两步连续：测试点 -> 用例（无确认停顿，CI 兼容）", "第 4 步")
    table.add_row("review", "评审测试用例质量和覆盖度", "第 5 步")
    table.add_row("review-iter", "评审→优化迭代闭环（定向修补，直到通过或达上限）", "第 5 步+" )
    table.add_row("export", "导出用例到 Excel（确认列门禁：未拍板即阻断，--force 豁免）", "第 6 步")
    table.add_row("test", "Playwright 脚本执行（备用/CI 路径）", "脚本模式")
    table.add_row("qoder-plan", "生成 Qoder MCP 测试计划 [--p0|--retry]", "推荐·主路径")
    table.add_row("solidify", "固化通过的用例为 Playwright 脚本 [--all|--p0]", "推荐·固化")
    table.add_row("triage", "结果分流：拆出真实缺陷/用例问题/未执行/环境数据", "推荐·收尾")
    table.add_row("explore", "探索性测试，遍历所有页面寻找 bug", "脚本模式")
    table.add_row("qoder-explore", "生成 Qoder 探索计划，在 Qoder 中执行", "推荐")
    table.add_row("prototype", "截取在线原型页面截图", "准备")
    table.add_row("help", "显示此帮助信息", "-")
    console.print(table)

    console.print("\n[bold]快速入门：[/bold]")
    console.print("  1. 编辑 [yellow].env[/yellow] 文件 - 设置 APP_URL 和登录账号")
    console.print("  2. 把需求文档放到 [yellow]inputs/requirements/[/yellow]（.md 或 .txt 格式）")
    console.print("  3. 运行：[bold green]python run.py analyze[/bold green]")
    console.print("  4. 提示词会自动复制到剪贴板，粘贴到 Qoder 对话中获取分析结果")
    console.print("  5. 将 Qoder 的回复粘贴回终端（或保存到 ai_workspace/ 文件后按回车）")
    console.print("")

    console.print("[bold]Qoder 桥接模式（推荐）：[/bold]")
    console.print("  1. 先运行 [bold green]python run.py testpoints[/bold green] 生成测试点，并对确认列拍板（未拍板改已确认，符号见产物文件）")
    console.print("  2. 运行 [bold green]python run.py testcases[/bold green] 生成测试用例（或 [dim]python run.py design 两步连续[/dim]）")
    console.print("  3. 运行 [bold green]python run.py qoder-plan[/bold green] 生成测试计划")
    console.print("  4. 在 Qoder 对话中说：\"请读取 qoder_workspace/test_plan.md 并执行测试\"")
    console.print("  5. Qoder 会使用内置 Playwright MCP 工具自动操控浏览器")
    console.print("")

    console.print("[bold]工作流程（7 阶段，对应 output/00~06 目录）：[/bold]")
    console.print("  [cyan]探索[/cyan] 00_explore -> [cyan]业务梳理[/cyan] 01_business -> [cyan]分析[/cyan] 02_split -> [cyan]理解[/cyan] 03_design")
    console.print("  -> [cyan]设计[/cyan] 测试点 -> 用例（两步，中间人工拍板）-> [cyan]评审[/cyan] 04_review -> [cyan]导出[/cyan] 05_export -> [cyan]执行[/cyan] -> 06_reports 报告")
    console.print("  [dim]注：探索/业务产物作为上游业务基线，被分析/理解/设计提示词引用[/dim]")
    console.print("")

    console.print("[bold]独立脚本（推荐）：[/bold]")
    console.print("  python scripts/run_business.py 模块名   # 业务梳理指定模块")
    console.print("  python scripts/run_analyze.py 模块名   # 分析指定模块")
    console.print("  python scripts/run_understand.py 模块名 # 理解指定模块")
    console.print("  python scripts/run_testpoints.py 模块名 # 设计第一步：测试点+风险台账")
    console.print("  python scripts/run_testcases.py 模块名  # 设计第二步：测试用例")
    console.print("  python scripts/run_design.py 模块名   # 设计两步连续（测试点 -> 用例）")
    console.print("  python scripts/run_review.py 模块名   # 审核指定模块")
    console.print("  python scripts/run_test.py 模块名     # 测试指定模块")
    console.print("  python scripts/confirmation_bridge.py export [模块]  # 导出待拍板清单 xlsx（给业务填）")
    console.print("  python scripts/confirmation_bridge.py apply [xlsx] [--dry-run]  # 业务结论回流回写源 md")
    console.print("  python scripts/run_explore.py          # 探索性测试")
    console.print("  python scripts/run_prototype.py        # 截取原型图")


# ========== 命令调度器 ==========

COMMANDS = {
    "pipeline":      (cmd_pipeline,      "完整流水线"),
    "business":      (cmd_business,      "探索+需求 -> 业务全景图"),
    "analyze":       (cmd_analyze,       "需求 -> 拆分需求"),
    "understand":    (cmd_understand,    "拆分需求 -> 需求理解文档"),
    "testpoints":    (cmd_testpoints,    "设计第一步：理解+测试点+风险台账"),
    "testcases":     (cmd_testcases,     "设计第二步：测试点 -> 测试用例"),
    "design":        (cmd_design,        "两步连续：测试点 -> 用例（兼容）"),
    "review":        (cmd_review,        "评审测试用例"),
    "review-iter":   (cmd_review_iter,   "评审→优化迭代闭环 [--max N] [--strict]"),
    "export":        (cmd_export,        "导出 Excel 用例（确认列门禁·--force 豁免）"),
    "test":          (cmd_test,          "执行测试（Playwright 脚本·备用）"),
    "qoder-plan":    (cmd_qoder_plan,    "生成 Qoder MCP 测试计划（推荐·主路径）"),
    "solidify":      (cmd_solidify,      "固化通过的用例为 Playwright 脚本 [--all|--p0]"),
    "triage":        (cmd_triage,        "结果分流：失败归因 + 有效通过率 + 发版门禁"),
    "explore":       (cmd_explore,       "探索性测试（Playwright 脚本）"),
    "qoder-explore": (cmd_qoder_explore, "生成 Qoder 探索计划"),
    "prototype":     (cmd_prototype,     "截取原型图"),
    "help":          (cmd_help,          "显示帮助"),
}


def main():
    """主函数。"""
    print_banner()

    if len(sys.argv) < 2:
        cmd_help()
        return

    cmd = sys.argv[1].lower().strip()

    if cmd not in COMMANDS:
        console.print(f"[red]未知命令：{cmd}[/red]")
        cmd_help()
        sys.exit(1)

    func, _ = COMMANDS[cmd]
    func()


if __name__ == "__main__":
    main()
