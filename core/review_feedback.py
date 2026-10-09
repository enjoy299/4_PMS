"""
评审反馈解析与迭代控制 —— 评审→优化闭环的核心引擎。

职责：
  1. 从评审报告 Markdown 中解析结构化反馈（评审结论、问题清单、改进建议）
  2. 生成面向 AI 的用例优化提示词（把评审反馈变成定向修改指令）
  3. 控制迭代循环（评审→优化→再评审，直到通过或达到上限）

设计原则：
  - 增量修补优于全量重生：只修复评审指出的问题，保留已通过的部分
  - 每轮迭代有明确的收敛判断（评审结论 + 严重问题数）
  - 最多迭代 3 轮，超过则交人工裁决
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.config import REVIEW_DIR, CASES_DIR
from utils.logger import get_logger

logger = get_logger("review_feedback")


# ==================== 数据结构 ====================

@dataclass
class ReviewIssue:
    """评审报告中的单条问题。"""
    issue_id: str            # 问题编号（如 "1"、"A-01"）
    severity: str            # "严重" | "一般" | "未确认项"
    case_id: str             # 涉及的用例 ID（如 "TC-xxx-001"，多条时逗号分隔）
    description: str         # 问题描述
    suggestion: str          # 修改建议


@dataclass
class ReviewFeedback:
    """从评审报告中提取的结构化反馈。"""
    verdict: str                             # "pass" | "conditional_pass" | "reject"
    verdict_text: str                        # 原始结论文本（如 "有条件通过"）
    issues: list[ReviewIssue] = field(default_factory=list)
    cases_to_modify: list[dict] = field(default_factory=list)   # [{case_id, content, reason}]
    cases_to_delete: list[dict] = field(default_factory=list)   # [{case_id, reason}]
    cases_to_add: list[dict] = field(default_factory=list)      # [{suggestion_id, scenario, priority, reason}]
    summary: dict = field(default_factory=dict)                 # {评审用例数, 通过数, 需修改数, ...}
    raw_content: str = ""                    # 评审报告原文


# ==================== 评审结论解析 ====================

def parse_verdict(content: str) -> tuple[str, str]:
    """从评审报告 Markdown 中解析评审结论。

    返回：(verdict_code, verdict_text)
      verdict_code: "pass" | "conditional_pass" | "reject" | "unknown"
      verdict_text: 原始结论文本
    """
    # 优先匹配"评审结论"章节
    conclusion_match = re.search(
        r"##\s*评审结论\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL
    )
    if conclusion_match:
        section = conclusion_match.group(1)
    else:
        section = content

    # 不通过（优先匹配，避免"不"被忽略）
    if re.search(r"不通过", section):
        m = re.search(r"[^\n]*不通过[^\n]*", section)
        return "reject", m.group(0).strip() if m else "不通过"
    # 有条件通过
    if re.search(r"有条件通过", section):
        m = re.search(r"[^\n]*有条件通过[^\n]*", section)
        return "conditional_pass", m.group(0).strip() if m else "有条件通过"
    # 通过
    if re.search(r"通过", section):
        m = re.search(r"[^\n]*通过[^\n]*", section)
        return "pass", m.group(0).strip() if m else "通过"

    return "unknown", "未识别"


# ==================== 评审报告解析 ====================

def parse_review_report(report_path: Path) -> ReviewFeedback:
    """从评审报告 Markdown 文件中解析结构化反馈。

    解析策略：按章节正则匹配，容忍格式差异（表格缺失时降级为纯文本提取）。
    """
    content = report_path.read_text(encoding="utf-8")
    verdict, verdict_text = parse_verdict(content)

    feedback = ReviewFeedback(
        verdict=verdict,
        verdict_text=verdict_text,
        raw_content=content,
    )

    # --- 评审概要表 ---
    summary_match = re.search(
        r"##\s*评审概要\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL
    )
    if summary_match:
        for m in re.finditer(r"\|\s*([^|]+)\s*\|\s*(\d+)\s*\|", summary_match.group(1)):
            feedback.summary[m.group(1).strip()] = int(m.group(2))

    # --- 严重问题 ---
    _parse_issue_table(content, "严重问题", "严重", feedback.issues)
    # --- 一般问题 ---
    _parse_issue_table(content, "一般问题", "一般", feedback.issues)
    # --- 未确认项 ---
    _parse_issue_table(content, "未确认项", "未确认项", feedback.issues)

    # --- 需要修改的用例 ---
    mod_match = re.search(
        r"###\s*需要修改的用例\s*\n(.*?)(?=\n###|\n##|\Z)", content, re.DOTALL
    )
    if mod_match:
        for m in re.finditer(
            r"\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|", mod_match.group(1)
        ):
            cid, mod_content, reason = (
                m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            )
            if cid and cid not in ("用例 ID", "用例ID", "---"):
                feedback.cases_to_modify.append(
                    {"case_id": cid, "content": mod_content, "reason": reason}
                )

    # --- 需要删除的用例 ---
    del_match = re.search(
        r"###\s*需要删除的用例\s*\n(.*?)(?=\n###|\n##|\Z)", content, re.DOTALL
    )
    if del_match:
        for m in re.finditer(
            r"\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|", del_match.group(1)
        ):
            cid, reason = m.group(1).strip(), m.group(2).strip()
            if cid and cid not in ("用例 ID", "用例ID", "---"):
                feedback.cases_to_delete.append(
                    {"case_id": cid, "reason": reason}
                )

    # --- 需要新增的用例 ---
    add_match = re.search(
        r"###\s*需要新增的用例\s*\n(.*?)(?=\n###|\n##|\Z)", content, re.DOTALL
    )
    if add_match:
        for m in re.finditer(
            r"\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|",
            add_match.group(1),
        ):
            sid, scenario, priority, reason = (
                m.group(1).strip(), m.group(2).strip(),
                m.group(3).strip(), m.group(4).strip(),
            )
            if sid and sid not in ("建议编号", "---"):
                feedback.cases_to_add.append({
                    "suggestion_id": sid, "scenario": scenario,
                    "priority": priority, "reason": reason,
                })

    return feedback


def _parse_issue_table(
    content: str, section_name: str, severity: str,
    target: list[ReviewIssue],
) -> None:
    """从指定章节的 Markdown 表格中解析问题列表（就地追加到 target）。"""
    pattern = rf"###\s*{re.escape(section_name)}.*?\n(.*?)(?=\n###|\n##|\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return
    for m in re.finditer(
        r"\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|",
        match.group(1),
    ):
        iid, case_id, desc, sug = (
            m.group(1).strip(), m.group(2).strip(),
            m.group(3).strip(), m.group(4).strip(),
        )
        if iid and iid not in ("问题编号", "---"):
            target.append(ReviewIssue(
                issue_id=iid, severity=severity,
                case_id=case_id, description=desc, suggestion=sug,
            ))


# ==================== 日志与展示 ====================

def log_feedback_summary(feedback: ReviewFeedback, iteration: int = 1,
                         max_iterations: int = 3) -> None:
    """在控制台打印评审反馈摘要（Rich 兼容，纯 print 也好看）。"""
    from rich.console import Console
    from rich.panel import Panel
    console = Console()

    verdict_colors = {
        "pass": "green", "conditional_pass": "yellow",
        "reject": "red", "unknown": "dim",
    }
    color = verdict_colors.get(feedback.verdict, "dim")

    console.print(Panel(
        f"[bold]评审结论：[{color}]{feedback.verdict_text}[/{color}]\n"
        f"迭代轮次：{iteration}/{max_iterations}\n"
        f"严重问题：{len([i for i in feedback.issues if i.severity == '严重'])} 条\n"
        f"一般问题：{len([i for i in feedback.issues if i.severity == '一般'])} 条\n"
        f"未确认项：{len([i for i in feedback.issues if i.severity == '未确认项'])} 条\n"
        f"需修改：{len(feedback.cases_to_modify)} 条 ｜ "
        f"需删除：{len(feedback.cases_to_delete)} 条 ｜ "
        f"需新增：{len(feedback.cases_to_add)} 条",
        title=f"评审反馈摘要（第 {iteration} 轮）",
        border_style=color, expand=False,
    ))


# ==================== 优化提示词生成 ====================

def build_optimize_prompt(
    case_content: str,
    feedback: ReviewFeedback,
    module_name: str,
    module_no: str = "01",
    id_prefix: str = "",
    output_dir: str = "",
    timestamp: str = "",
) -> str:
    """根据评审反馈生成用例优化提示词。

    核心思路：把评审反馈变成定向修改指令，让 AI 做精准修补而非全量重生。
    """
    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M")

    # 组装评审反馈摘要
    lines: list[str] = [
        f"## 评审反馈（第 {ts} 轮优化）",
        "",
        f"**评审结论**：{feedback.verdict_text}",
        "",
    ]

    if feedback.issues:
        lines.append("### 问题清单")
        lines.append("")
        lines.append("| 编号 | 严重级别 | 用例 ID | 问题描述 | 修改建议 |")
        lines.append("|------|----------|---------|----------|----------|")
        for iss in feedback.issues:
            lines.append(
                f"| {iss.issue_id} | {iss.severity} | {iss.case_id} "
                f"| {iss.description} | {iss.suggestion} |"
            )
        lines.append("")

    if feedback.cases_to_modify:
        lines.append("### 需要修改的用例")
        lines.append("")
        for item in feedback.cases_to_modify:
            lines.append(
                f"- **{item['case_id']}**：{item['content']}"
                f"（原因：{item['reason']}）"
            )
        lines.append("")

    if feedback.cases_to_delete:
        lines.append("### 需要删除的用例")
        lines.append("")
        for item in feedback.cases_to_delete:
            lines.append(f"- **{item['case_id']}**：{item['reason']}")
        lines.append("")

    if feedback.cases_to_add:
        lines.append("### 需要新增的用例")
        lines.append("")
        for item in feedback.cases_to_add:
            lines.append(
                f"- {item['suggestion_id']}：{item['scenario']}"
                f"（优先级 {item['priority']}，原因：{item['reason']}）"
            )
        lines.append("")

    feedback_block = "\n".join(lines)

    # 完整优化提示词
    prompt = f"""# 测试用例优化（基于评审反馈）

## 角色和任务

你是一名资深测试工程师，正在根据评审反馈优化测试用例。

请基于以下评审反馈，对现有测试用例进行**定向优化**（不是全量重新生成）。

## 现有测试用例

```markdown
{case_content}
```

{feedback_block}

## 优化规则

1. **定向修补**：只修改评审指出的问题，保留已通过评审的部分
2. **格式一致**：输出格式与原用例文件完全一致（14 字段属性表格）
3. **编号稳定**：已存在的用例 ID 不变（便于跨版本追溯）
4. **修改非删除**：被标记修改的用例就地修正，不要删除后重建
5. **新增追加**：需要新增的用例追加到文件末尾（在追溯校验之前），编号在现有最大序号后递增
6. **删除标记**：需要删除的用例从输出中移除
7. **确认列保持**：「确认结论(业务填)」字段的 ⬜/✅ 状态保持不变，除非评审明确指出需要修改
8. **追溯更新**：更新追溯校验部分，确保测试点覆盖矩阵反映最新状态

## 输出要求

1. 输出完整的优化后用例文件（可直接替换原文件）
2. 在文件开头添加演进说明：`> 演进说明：基于评审反馈优化，修改 N 条 / 删除 M 条 / 追加 K 条`
3. 更新末尾的追溯校验（追溯矩阵 + 未覆盖清单）
"""
    return prompt


# ==================== 迭代控制器 ====================

class ReviewIterateController:
    """评审-优化迭代控制器。

    用法：
        controller = ReviewIterateController(module_name="项目管理", max_iterations=3)
        result = controller.run()

    工作流：
        1. 评审当前用例 → 生成评审报告
        2. 解析评审结论：通过 → 结束；不通过 → 继续
        3. 解析评审反馈 → 生成优化提示词
        4. 用户将优化提示词粘贴到 Qoder → 取回优化结果 → 覆盖用例文件
        5. 回到步骤 1（最多 max_iterations 轮）
        6. 达到上限仍未通过 → 提示人工介入
    """

    def __init__(
        self,
        module_name: str,
        max_iterations: int = 3,
        pass_threshold: str = "conditional_pass",
    ):
        self.module_name = module_name
        self.max_iterations = max_iterations
        # pass_threshold: 什么评审结论算"可以通过"
        # "pass" = 必须完全通过才停；"conditional_pass" = 有条件通过也停（推荐）
        self.pass_threshold = pass_threshold
        self.history: list[ReviewFeedback] = []

    def _verdict_passes(self, verdict: str) -> bool:
        """判断评审结论是否达到退出阈值。"""
        if self.pass_threshold == "pass":
            return verdict == "pass"
        # conditional_pass（默认）：通过或有条件通过都算过
        return verdict in ("pass", "conditional_pass")

    def run(self) -> dict:
        """执行评审-优化迭代循环。

        返回：
            {
                "success": bool,
                "iterations": int,
                "final_verdict": str,
                "final_report": Path | None,
                "history": [ReviewFeedback, ...],
            }
        """
        from agents.reviewer_agent import ReviewerAgent
        from agents.designer_agent import DesignerAgent

        reviewer = ReviewerAgent()
        designer = DesignerAgent()

        console = self._get_console()

        for iteration in range(1, self.max_iterations + 1):
            console.print(
                f"\n[bold cyan]{'=' * 50}[/bold cyan]"
            )
            console.print(
                f"[bold cyan]  评审-优化迭代 第 {iteration}/{self.max_iterations} 轮"
                f"[/bold cyan]"
            )
            console.print(
                f"[bold cyan]{'=' * 50}[/bold cyan]\n"
            )

            # ---- Step A: 评审 ----
            console.print("[bold]Step A: 评审当前用例[/bold]")
            report_path = reviewer.review(self.module_name)
            if not report_path:
                console.print("[red]评审失败：未生成评审报告[/red]")
                return self._result(False, iteration, "unknown", None)

            # ---- Step B: 解析评审结论 ----
            feedback = parse_review_report(report_path)
            feedback.raw_content = report_path.read_text(encoding="utf-8")
            self.history.append(feedback)

            log_feedback_summary(feedback, iteration, self.max_iterations)

            # ---- Step C: 判断是否通过 ----
            if self._verdict_passes(feedback.verdict):
                console.print(
                    f"\n[bold green]  评审通过（{feedback.verdict_text}），"
                    f"迭代结束[/bold green]"
                )
                return self._result(True, iteration, feedback.verdict, report_path)

            severe = len([i for i in feedback.issues if i.severity == "严重"])
            if iteration >= self.max_iterations:
                console.print(
                    f"\n[bold red]  已达最大迭代次数（{self.max_iterations}），"
                    f"仍有 {severe} 条严重问题，建议人工介入[/bold red]"
                )
                return self._result(False, iteration, feedback.verdict, report_path)

            # ---- Step D: 用户确认 ----
            console.print(
                f"\n[yellow]评审发现 {severe} 条严重问题，"
                f"是否进入优化？[/yellow]"
            )
            confirm = input("  输入 y 继续优化，其他键跳过：").strip().lower()
            if confirm != "y":
                console.print("[dim]  用户跳过优化，迭代结束[/dim]")
                return self._result(False, iteration, feedback.verdict, report_path)

            # ---- Step E: 优化 ----
            console.print("\n[bold]Step E: 基于评审反馈优化用例[/bold]")
            ok = designer.design_with_feedback(self.module_name, feedback)
            if not ok:
                console.print("[red]优化失败，迭代中断[/red]")
                return self._result(False, iteration, feedback.verdict, report_path)

            console.print(
                "[dim]  优化完成，将进入下一轮评审验证[/dim]"
            )

        return self._result(False, self.max_iterations, "unknown", None)

    def _result(self, success: bool, iterations: int,
                verdict: str, report: Path | None) -> dict:
        return {
            "success": success,
            "iterations": iterations,
            "final_verdict": verdict,
            "final_report": report,
            "history": self.history,
        }

    @staticmethod
    def _get_console():
        from rich.console import Console
        return Console()
