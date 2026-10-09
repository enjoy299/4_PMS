"""
人工确认机制 —— 让 AI 在不确定的地方暂停，等待人类审核。

通俗理解：
  AI 不是万能的，有时候它分析需求时会遇到模糊不清的描述。
  这时它不会自作主张，而是暂停下来，把这些不确定的内容展示给你看，
  让你决定是保留、删除还是修改这些内容。

三个使用场景：
  1. 不确定的测试点 —— AI 分析需求时遇到模糊描述
  2. 生成的测试用例 —— AI 设计完用例后让你审核
  3. 分析结果摘要 —— 展示分析结果让你确认
"""
# rich 库用于在终端中显示美观的表格、面板和交互提示
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt  # 用于在终端接收用户输入
from rich.table import Table
from rich import box

console = Console()

# ── 分流人工门禁（Task 9）──
from datetime import datetime

from core import config as _cfg          # 取属性而非导入值：保证测试可 monkeypatch、运行时读最新值
from core.triage import CATEGORIES, save_decisions

_CATEGORY_BY_CHOICE = {"bug": "PRODUCT_BUG", "case": "CASE_DEFECT", "env": "ENV_BLOCK",
                       "data": "DATA_PRECOND", "exec": "EXEC_INCOMPLETE"}


def _safe_ask(prompt_text, choices, default):
    """
    安全版本的 Prompt.ask，在非交互环境（管道、CI/CD）下不会崩溃。

    当遇到 EOFError 时（说明没有可用的终端输入），自动返回默认值，
    并在日志中提示用户。
    """
    try:
        return Prompt.ask(prompt_text, choices=choices, default=default)
    except EOFError:
        console.print(f"  [dim]（非交互环境，自动选择默认值：{default}）[/dim]")
        return default


def confirm_test_points(module_name: str, uncertain_items: list[dict]) -> list[dict]:
    """
    让人工确认不确定的测试点。

    当 AI 分析需求时，遇到不确定的测试点会调用这个函数。
    它会在终端显示每个不确定的测试点，让你选择：
      - keep：保留这个测试点
      - drop：删除这个测试点
      - edit：修改测试点的描述后再保留

    参数：
        module_name: 模块名称（如 “用户登录”）
        uncertain_items: AI 不确定的测试点列表
            每个测试点包含：id（编号）、text（描述）、reason（不确定的原因）

    返回：
        经过人工确认后的测试点列表
    """
    from core.config import HUMAN_CONFIRM
    # 如果配置中关闭了人工确认，直接返回所有不确定的测试点
    if not HUMAN_CONFIRM:
        return uncertain_items

    # 在终端显示警告面板
    console.print(Panel(
        f"[bold yellow]注意：{module_name} - 以下测试点需要人工确认[/bold yellow]",
        title="人工确认", border_style="yellow",
    ))

    kept = []  # 存放确认保留的测试点
    # 逐个展示不确定的测试点，等待你的决策
    for item in uncertain_items:
        # 用表格展示当前测试点的详细信息
        table = Table(box=box.ROUNDED, show_header=False, border_style="yellow")
        table.add_column("字段", style="bold cyan", width=12)
        table.add_column("内容")
        table.add_row("编号", item.get("id", ""))
        table.add_row("测试点", item.get("text", ""))
        table.add_row("原因", item.get("reason", "需求描述不清晰"))
        console.print(table)

        # 等待用户输入：keep（保留）、drop（删除）、edit（修改）
        choice = _safe_ask("  操作", choices=["keep", "drop", "edit"], default="keep")
        if choice == "keep":
            kept.append(item)
        elif choice == "edit":
            new_text = _safe_ask("  修改后的描述", choices=None, default=item.get("text", ""))
            item["text"] = new_text
            item["human_edited"] = True  # 标记为人工编辑过
            kept.append(item)
        # 如果选择 drop，什么都不做，该测试点就不会被保留

    console.print(f"  确认结果：保留了 {len(kept)}/{len(uncertain_items)} 个测试点\n")
    return kept


def confirm_test_cases(module_name: str, cases: list[dict]) -> list[dict]:
    """
    让人工审核 AI 生成的测试用例。

    AI 设计完测试用例后，会调用这个函数让你逐个审核。
    你可以选择：
      - a (approve)：批准这个用例
      - e (edit)：修改用例名称和断言后再批准
      - r (reject)：拒绝这个用例
      - q (quick approve)：一键批准剩余所有用例

    参数：
        module_name: 模块名称
        cases: AI 生成的测试用例列表

    返回：
        经过审核批准的测试用例列表
    """
    from core.config import HUMAN_CONFIRM
    if not HUMAN_CONFIRM:
        return cases

    # 显示审核面板，告知用户操作方式
    console.print(Panel(
        f"[bold cyan]审核测试用例：{module_name}[/bold cyan]\n"
        f"[a]=批准  [e]=编辑  [r]=拒绝  [q]=批准全部并继续",
        title="用例审核", border_style="cyan",
    ))

    approved = []  # 存放审核通过的用例
    for i, case in enumerate(cases, 1):
        # 用表格展示当前用例的详细信息
        table = Table(box=box.ROUNDED, border_style="cyan")
        table.add_column("字段", style="bold", width=12)
        table.add_column("内容")
        table.add_row("编号", case.get("id", ""))
        table.add_row("名称", case.get("name", ""))
        table.add_row("优先级", case.get("priority", ""))
        # 格式化显示操作步骤
        steps_text = "\n".join(f"  {s.get('order','')}. {s.get('action','')}" for s in case.get("steps", []))
        table.add_row("步骤", steps_text)
        # 格式化显示断言（预期结果的检查项）
        asserts_text = "\n".join(f"  - {a}" for a in case.get("assertions", []))
        table.add_row("断言", asserts_text)
        console.print(f"\n  -- 用例 [{i}/{len(cases)}] --")
        console.print(table)

        # 等待用户输入审核操作
        choice = _safe_ask("  操作", choices=["a", "e", "r", "q"], default="a")
        if choice == "q":
            # 一键批准剩余所有用例
            approved.extend(cases[i-1:])
            console.print("  已批准所有剩余用例")
            break
        elif choice == "a":
            approved.append(case)  # 批准当前用例
        elif choice == "e":
            # 编辑用例：可以修改名称和断言
            new_name = _safe_ask("  用例名称", choices=None, default=case.get("name", ""))
            case["name"] = new_name
            for j, assertion in enumerate(case.get("assertions", [])):
                edit = _safe_ask(f"  断言 {j+1}（直接回车保持不变）", choices=None, default=assertion)
                case["assertions"][j] = edit
            approved.append(case)
        # 如果选择 r，当前用例被拒绝，不加入 approved 列表

    console.print(f"\n  审核完成：{len(approved)}/{len(cases)} 个用例通过\n")
    return approved


def show_analysis_summary(module_name: str, analysis_result: dict):
    """
    显示分析结果摘要，让你在继续下一步之前了解 AI 的分析情况。

    参数：
        module_name: 模块名称
        analysis_result: AI 的分析结果，包含统计信息
    """
    console.print(Panel(
        f"[bold green]{module_name} 分析完成[/bold green]",
        border_style="green",
    ))
    # 用表格展示各类测试点的数量
    table = Table(box=box.ROUNDED, title="测试点汇总")
    table.add_column("类型", style="bold")
    table.add_column("数量", justify="right")
    for tp_type, count in analysis_result.get("stats", {}).items():
        table.add_row(tp_type, str(count))
    console.print(table)
    # 如果有需要人工确认的测试点，显示提示
    if analysis_result.get("uncertain_count", 0) > 0:
        console.print(f"\n  [yellow]{analysis_result['uncertain_count']} 个测试点需要人工确认[/yellow]")


# ── 分流结论的人工裁决门禁 ────────────────────────────────
def _safe_ask_text(prompt_text, default=""):
    """自由文本输入的安全版（`_safe_ask` 只管选项题）。EOF 时返回 default。"""
    try:
        return Prompt.ask(prompt_text, default=default).strip()
    except EOFError:
        console.print("  [dim]（非交互环境，自动填入默认值）[/dim]")
        return default


def _suggest_category(rec: dict) -> str:
    """机器建议类别：含铁律字样的项意为“LLM 认为是真缺陷”，默认建议给人 `[bug]`。"""
    tri = rec["triage"]
    why = tri.get("rationale", "") or ""
    if "铁律" in why or "R7" in why:
        return "PRODUCT_BUG"
    if "R1" in why or "R2" in why or "R3" in why:
        return "ENV_BLOCK"
    if "R6" in why:
        return "DATA_PRECOND"
    return "NEEDS_HUMAN"


def _q_eligible(rec: dict) -> bool:
    """`[q]` 只能批量接受 LLM 高置信、且结论不是 PRODUCT_BUG / BLOCKED 类的项。

    否则「一路 q」会把真缺陷顺手定性、或把用例批量塞进 BLOCKED 逃过分母。
    """
    tri = rec["triage"]
    if _suggest_category(rec) in ("PRODUCT_BUG", "ENV_BLOCK", "DATA_PRECOND"):
        return False
    if tri.get("source") != "llm":
        return False
    return float(tri.get("confidence", 0) or 0) >= _cfg.TRIAGE_CONF_THRESHOLD


def _needs_human(rec: dict) -> bool:
    """待人工项 = 机器定不下来的（NEEDS_HUMAN）+ LLM 已判但未经人确认的。

    第二类必须进门禁，否则 `[q]`「接受剩余建议」永远无事可做，
    `overridden`/quarantine（专收被人工推翻的 LLM 结论）也永远不会有数据。
    """
    tri = rec["triage"]
    return tri.get("category") == "NEEDS_HUMAN" or tri.get("source") == "llm"


def confirm_triage_decisions(run_id: str, merged: dict) -> dict:
    """逐条裁决待人工项，返回并落盘 `decisions.yaml`。

    参数：
        run_id: 分流 run ID
        merged: `merge_decisions()` 的输出（已含规则+LLM 结论）

    返回：
        decisions 字典（key = case_id）；已写入 `decisions.yaml` 持久留证。
    """
    now = datetime.now().isoformat(timespec="seconds")
    pending = [r for r in merged.values() if _needs_human(r)]
    if not pending:
        console.print("  [green]无需人工裁决：分流结论已全部落定[/green]")
        return {}

    decisions: dict = {}

    # --- CI / 人在场两种模式（不阻塞：人在不在都往下走，但未确认项不会被当作人工定性）---
    if not _cfg.HUMAN_CONFIRM:
        for rec in pending:
            if rec["triage"].get("source") == "llm":
                continue          # LLM 已有结论，CI 不替人签字，也不再叠一层建议
            sugg = _suggest_category(rec)
            decisions[rec["case_id"]] = {
                "final_category": sugg if sugg != "PRODUCT_BUG" else "NEEDS_HUMAN",
                "decided_by": "auto:ci", "decided_at": now,
                "confirmed_by_human": False,
                "note": "CI 浅分流：机器建议未经人确认，事后需核",
            }
        if decisions:
            save_decisions(run_id, decisions)
        console.print(f"  [yellow]HUMAN_CONFIRM=false：{len(decisions)} 项按建议落库并标记待重确认，"
                      f"不做发版结论[/yellow]")
        return decisions

    console.print(Panel(f"待人工裁决 {len(pending)} 项 ｜ 铁律：PRODUCT_BUG 定性必须由你拍板",
                        border_style="yellow", expand=False))
    idx = 0
    while idx < len(pending):
        rec = pending[idx]
        tri = rec["triage"]
        cid = rec["case_id"]
        sugg = _suggest_category(rec)
        console.print(f"\n[bold][{idx + 1}/{len(pending)}] {cid}[/bold] {rec.get('name', '')}"
                      f"  （{rec.get('module', '')}｜{rec.get('status', '')}｜机器结论："
                      f"{tri.get('category', '')}/{tri.get('source', '')}）")
        console.print(f"  机器依据: {tri.get('rationale', '')}")
        console.print("  断言: " + "；".join(f"{a.get('text')}={a.get('verdict')}"
                                            for a in rec.get("assertions", [])[:4]))
        console.print(f"  现象: {(rec.get('error') or '')[:120]}")
        if rec.get("llm_proposal"):                       # LLM 只能提案，提案内容必须递到人眼前
            prop = rec["llm_proposal"]
            console.print(f"  [magenta]LLM 提案（置信 {prop.get('confidence')}）: {prop.get('rationale', '')}[/magenta]")
            for ev in (prop.get("evidence_cited") or [])[:3]:
                console.print(f"    · {ev}")
            if prop.get("bug_draft"):
                console.print(f"    Bug 草稿: {prop['bug_draft']}")
        if tri.get("suggested_action"):
            console.print(f"  建议动作: {tri['suggested_action']}")
        ans = _safe_ask("[bug]真缺陷 [case]用例问题 [env]环境 [data]补前置 [exec]执行不到位 "
                        "[skip]标阻塞 [edit]自写 [q]接受剩余建议",
                        ["bug", "case", "env", "data", "exec", "skip", "edit", "q"],
                        "bug" if sugg == "PRODUCT_BUG" else "case")

        if ans == "q":
            batched = 0
            for other in pending:
                if other["case_id"] in decisions or not _q_eligible(other):
                    continue
                decisions[other["case_id"]] = {
                    "final_category": other["triage"]["category"],
                    "decided_by": "human:quick-accept", "decided_at": now,
                    "confirmed_by_human": True, "note": "批量接受 LLM 高置信建议",
                }
                batched += 1
            left = [p["case_id"] for p in pending if p["case_id"] not in decisions]
            console.print(f"  已批量接受 {batched} 项；{len(left)} 项不得批量接受，保持待裁决")
            idx = len(pending)          # 不再重问，避免「一直按 q」死循环；下次跑仍会列出
            continue

        if ans == "edit":
            cat = _safe_ask_text(f"结论（{'/'.join(CATEGORIES)} 之一，拼写错误则本轮不记录）", "")
            if cat in CATEGORIES:
                decisions[cid] = {"final_category": cat, "decided_by": "human:edit",
                                  "decided_at": now, "confirmed_by_human": True,
                                  "note": _safe_ask_text("备注", "")}
            else:
                console.print("  [red]类别非法，本条保持待裁决[/red]")
            idx += 1
            continue

        if ans == "skip":
            hint = _safe_ask_text("unblock_hint（如何解除阻塞，必填）", "")
            if not hint:
                console.print("  [red]未给出解除路径，不收「标阻塞」，本条继续挂待人工裁决[/red]")
                idx += 1
                continue
            cat = "DATA_PRECOND" if sugg == "DATA_PRECOND" else "ENV_BLOCK"
            decisions[cid] = {"final_category": cat, "decided_by": "human:skip",
                              "decided_at": now, "confirmed_by_human": True,
                              "unblock_hint": hint, "note": "人工标为阻塞（移出分母）"}
            idx += 1
            continue

        cat = _CATEGORY_BY_CHOICE.get(ans, "CASE_DEFECT")
        entry = {"final_category": cat, "decided_by": "human", "decided_at": now,
                 "confirmed_by_human": True, "note": ""}
        if cat == "PRODUCT_BUG":
            entry["severity"] = _safe_ask_text("严重程度 S1/S2/S3/S4", "S2")
            entry["note"] = _safe_ask_text("一句话确认理由（写进 Bug 草稿）", "")
        if cat in ("ENV_BLOCK", "DATA_PRECOND"):
            entry["unblock_hint"] = _safe_ask_text("unblock_hint（如何解除）",
                                                   tri.get("unblock_hint") or "")
        decisions[cid] = entry
        idx += 1

    if decisions:
        path = save_decisions(run_id, decisions)
        console.print(f"  [green]人工结论已落盘：{path}[/green]")
    return decisions
