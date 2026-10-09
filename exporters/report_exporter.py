"""
测试报告导出器 —— 把测试结果生成多种格式的报告。

通俗理解：
  测试执行完成后，需要把结果整理成报告，方便查看和存档。
  这个模块可以同时生成三种格式的报告：
    1. Markdown (.md) —— 轻量文本格式，方便在代码编辑器中查看
    2. HTML (.html) —— 网页格式，可以在浏览器中打开，有美观的样式
    3. Excel (.xlsx) —— 表格格式，方便在 Excel 中查看和筛选
"""
import json
from datetime import datetime
from html import escape
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter     # Excel 列数可变，不能手写 "A1:N1"
from core import config as _cfg   # 取属性而非导入值：运行时读最新配置，测试可 monkeypatch 隔离目录
from core.triage import BLOCKED_CATEGORIES   # BLOCKED 只按分流类别认定，与摘要同一口径
from utils.logger import get_logger

logger = get_logger("reporter")

# HTML 报告模板。变量全部是「整块 HTML 片段」而不是 scattered 字段：
# 卡片与表头列数在旧 4 态 / 分流 18 列两种模式下不同，拼好再注入可避免两处硬编码对不上。
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>{title}</title>
<style>
body{{font-family:-apple-system,"Microsoft YaHei",sans-serif;max-width:1180px;margin:0 auto;padding:20px;color:#333}}
h1{{color:#1a1a1a;border-bottom:2px solid #4CAF50;padding-bottom:10px}}
.summary{{display:flex;flex-wrap:wrap;gap:15px;margin:20px 0}}
.card{{padding:15px 25px;border-radius:8px;color:#fff;text-align:center;min-width:96px}}
.card h3{{margin:0;font-size:28px}}.card p{{margin:5px 0 0;font-size:13px}}
.pass{{background:#4CAF50}}.fail{{background:#f44336}}.error{{background:#ff9800}}.manual{{background:#9E9E9E}}.rate{{background:#2196F3}}
.total{{background:#37474F}}.bug{{background:#B71C1C}}.blocked{{background:#7B1FA2}}.pending{{background:#F9A825;color:#212121}}
table{{width:100%;border-collapse:collapse;margin:15px 0}}
th,td{{padding:10px;border:1px solid #ddd;text-align:left;vertical-align:top}}th{{background:#f5f5f5}}
.status-pass{{color:#4CAF50;font-weight:bold}}.status-fail{{color:#f44336;font-weight:bold}}.status-error{{color:#ff9800;font-weight:bold}}.status-manual{{color:#9E9E9E;font-weight:bold}}.status-blocked{{color:#7B1FA2;font-weight:bold}}.status-skipped{{color:#607D8B;font-weight:bold}}
.assertion{{margin:3px 0;padding:3px 8px;border-radius:3px;font-size:13px}}
.assert-pass{{background:#e8f5e9}}.assert-fail{{background:#ffebee}}.assert-manual{{background:#f0f0f0}}
.output{{background:#f8f8f8;padding:10px;border-radius:5px;font-size:13px;white-space:pre-wrap;max-height:200px;overflow:auto}}
.gate{{margin:14px 0;padding:10px 14px;border-left:4px solid #2196F3;background:#f4f8fb;font-size:14px}}
.gate-reject{{border-left-color:#f44336;background:#fff5f5}}
.gate-na{{border-left-color:#F9A825;background:#fffdf3}}
.c-ok{{color:#4CAF50;font-weight:bold}}.c-bug{{color:#B71C1C;font-weight:bold}}.c-blocked{{color:#7B1FA2;font-weight:bold}}.c-pending{{color:#F57F17;font-weight:bold}}.c-case{{color:#0288D1;font-weight:bold}}.c-exec{{color:#607D8B;font-weight:bold}}
.tag{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;background:#eee}}
.footer{{margin-top:30px;padding-top:15px;border-top:1px solid #ddd;color:#999;font-size:12px}}
</style></head><body>
<h1>{title}</h1>
<p><b>Time:</b> {timestamp} | <b>Duration:</b> {total_time}{meta}</p>
<div class="summary">{cards}</div>
{gate}
<h2>Detailed Results</h2>
<table><tr>{thead}</tr>{rows}</table>
{extra}
<div class="footer">{footer}</div>
</body></html>"""


def _cards(items) -> str:
    """items: [(css_class, value, label), ...] → 卡片 HTML。旧模式 5 张、分流模式 6 张。"""
    return "".join(f'<div class="card {cls}"><h3>{val}</h3><p>{label}</p></div>'
                   for cls, val, label in items)


class ReportExporter:
    """测试报告导出器类 —— 把测试结果生成多种格式的文件。"""

    def build_and_save(self, suite_name: str, results: list[dict], bugs: list = None) -> dict:
        """
        汇总测试结果并生成报告文件。

        流程：
        1. 统计通过/失败/错误的数量和通过率
        2. 根据配置的格式（MD/HTML/Excel）生成对应的报告文件
        3. 在终端打印结果摘要

        参数：
            suite_name: 测试套件名称（模块名）
            results: 所有测试用例的执行结果列表
            bugs: 可选的缺陷列表，若提供则在 Excel 中生成 Bugs 工作表

        返回：
            包含汇总数据和详情的报告字典
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")         # 可读时间戳
        ts_file = datetime.now().strftime("%Y%m%d_%H%M%S")      # 文件名用时间戳
        total = len(results)
        passed = sum(1 for r in results if r["status"]=="pass")   # 通过数
        failed = sum(1 for r in results if r["status"]=="fail")   # 失败数
        errors = sum(1 for r in results if r["status"]=="error")  # 错误数
        blocked = sum(1 for r in results if r["status"]=="blocked")  # 阻塞数
        skipped = sum(1 for r in results if r["status"]=="skipped")  # 跳过/未执行数
        manual = sum(1 for r in results if r["status"]=="manual")  # 需人工确认数
        total_time = sum(r.get("duration",0) for r in results)    # 总耗时
        pass_rate = f"{passed/total*100:.0f}%" if total else "N/A"  # 通过率
        
        # 报告按「格式 → 模块」两级目录存放（模块名 = suite_name），避免各模块报告平铺混在一起
        # 确保目录存在（配置在运行时读，便于测试隔离与改配置后不重启生效）
        md_dir = _cfg.MD_REPORTS_DIR / suite_name
        html_dir = _cfg.HTML_REPORTS_DIR / suite_name
        excel_dir = _cfg.EXCEL_REPORTS_DIR / suite_name
        for d in (md_dir, html_dir, excel_dir):
            d.mkdir(parents=True, exist_ok=True)
        
        # 组装报告数据
        report = {"suite_name":suite_name,"timestamp":ts,
                  "summary":{"total":total,"passed":passed,"failed":failed,"errors":errors,"blocked":blocked,"skipped":skipped,"manual":manual,"pass_rate":pass_rate,"total_time":f"{total_time:.1f}s"},
                  "details":results}
        if bugs:
            report["bugs"] = bugs
        # 根据配置的格式生成对应文件
        for fmt in _cfg.REPORT_FORMAT:
            if fmt=="md": self._save_md(ts_file,suite_name,report, md_dir)
            elif fmt=="html": self._save_html(ts_file,suite_name,ts,f"{total_time:.1f}s",passed,failed,errors,manual,pass_rate,results, html_dir)
            elif fmt=="excel": self._save_excel(ts_file,suite_name,report, excel_dir)
        self._print_summary(report)  # 在终端打印摘要
        return report

    # ── 分流版报告（数据源：records.jsonl）─────────────────────────
    _STATUS_ICON = {"pass": "PASSED", "fail": "FAILED", "error": "ERROR", "manual": "MANUAL",
                    "blocked": "BLOCKED", "skipped": "SKIPPED"}
    _STATUS_DISPLAY = {"pass": "Pass", "fail": "Fail", "error": "Error", "blocked": "Blocked",
                       "skipped": "Not Run", "manual": "Manual"}
    _CAT_CN = {"PRODUCT_BUG": "真实缺陷", "CASE_DEFECT": "用例问题", "EXEC_INCOMPLETE": "执行未到位",
               "ENV_BLOCK": "环境阻塞", "DATA_PRECOND": "数据前置未满足",
               "NEEDS_HUMAN": "待人工裁决", "OK": "通过"}
    _BUCKET_KEYS = ("通过", "真实缺陷", "环境阻塞", "数据前置未满足", "用例问题",
                    "执行未到位", "待人工裁决", "其他异常")

    def build_from_records(self, run_id: str, mode: str = None, ts_file: str = "",
                           quiet: bool = False) -> dict:
        """从统一契约出报告：`records.jsonl` → 规整三层结论 → 8 段摘要 + 有分流列的报告。

        与 `build_and_save()` 并存：后者是 `TRIAGE_ENABLED=false` 的一键退回路径。
        报告层**不自己判定**，只呈现（判定全在 `core/triage.py`）。
        `quiet=True` 只落盘不打印：被 `triage_pipeline` 驱动时，终端由编排层统一负责
        """
        from core.triage import (apply_rule_layer, compute_summary, derived_status,
                                 evaluate_gate, load_decisions, load_llm_review,
                                 load_records, merge_decisions, to_result_rows)

        records, dups, malformed = load_records(run_id)
        if not records:
            raise FileNotFoundError(
                f"records.jsonl 无有效记录：{_cfg.TRIAGE_DIR / run_id / 'records.jsonl'}")
        if dups or malformed:
            logger.warning(f"  records 质量：duplicates={dups} malformed={malformed}")
        # `apply_rule_layer` 会无条件覆盖传入记录的 triage，故只能喂还没结论的记录，
        # 否则转换器从 blocker 带进来的类别会被规则层重算冲掉。
        undecided = [r for r in records if not r.get("triage", {}).get("category")
                     or r["triage"].get("source") == "none"]
        if undecided:
            apply_rule_layer(undecided)          # 就地改写；已有结论的记录不被重算覆盖
        merged = merge_decisions(records, load_llm_review(run_id), load_decisions(run_id))
        for rec in merged.values():
            rec["status"] = derived_status(rec)  # blocked / manual 只在此派生，不回写 jsonl
        summary = compute_summary(merged)
        mode = mode or ("strict" if _cfg.HUMAN_CONFIRM else "report_only")
        gate = evaluate_gate(merged, mode=mode)
        rows = to_result_rows(list(merged.values()))
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        ts_file = ts_file or datetime.now().strftime("%Y%m%d_%H%M%S")
        total_time = sum(float(r.get("duration_sec", 0) or 0) for r in records)
        # 标题取多数模块而不取首条：整个 run 的报告被一条跨模块用例改名，人拿到文件才会发现拿错了。
        # `max` + 计数对首次出现的模块稳定，并列时不随记录顺序飘。
        module_counts: dict = {}
        for r in records:
            m = r.get("module")
            if m:
                module_counts[m] = module_counts.get(m, 0) + 1
        suite_name = max(module_counts, key=module_counts.get) if module_counts else run_id
        report = {
            "run_id": run_id,
            "suite_name": suite_name,
            "timestamp": ts, "total_time": f"{total_time:.1f}s", "mode": mode,
            "summary": summary, "gate": gate,
            "quality": {"duplicates": dups, "malformed": malformed},
            "blocked": [r for r in rows if self._is_blocked(r)],
            "details": rows,
        }

        # 报告按「格式 → 模块」两级目录存放（与 build_and_save 同一口径）
        md_dir = _cfg.MD_REPORTS_DIR / report["suite_name"]
        html_dir = _cfg.HTML_REPORTS_DIR / report["suite_name"]
        excel_dir = _cfg.EXCEL_REPORTS_DIR / report["suite_name"]
        for d in (md_dir, html_dir, excel_dir):
            d.mkdir(parents=True, exist_ok=True)
        for fmt in _cfg.REPORT_FORMAT:
            if fmt == "md":
                self._save_md_triage(ts_file, report["suite_name"], report, md_dir)
            elif fmt == "html":
                self._save_html_triage(ts_file, report["suite_name"], report, html_dir)
            elif fmt == "excel":
                self._save_excel_triage(ts_file, report["suite_name"], report, excel_dir)
        if not quiet:
            self._print_summary_triage(report)   # 脚本直接调本层时的唯一反馈
        return report

    def _save_md_triage(self, ts_file, suite_name, report, output_dir):
        """分流版 Markdown：8 段摘要 + 两个通过率 + 收尾门禁 + 分流结论表 + BLOCKED 独立表。"""
        from core.triage import md_escape as md         # 表格单元转义（竖线/换行会破坏表格）
        s, g, q = report["summary"], report["gate"], report["quality"]
        rows = sorted(report["details"], key=lambda x: str(x.get("id", "")))
        lines = [f"# {suite_name} - Test Report（分流版）\n",
                 f"**Run**: `{report['run_id']}`  ", f"**Time**: {report['timestamp']}  ",
                 f"**Duration**: {report['total_time']}  ", f"**门禁模式**: {report['mode']}  ",
                 f"**数据质量**: duplicates={q['duplicates']} malformed={q['malformed']}\n",
                 "## 摘要（8 段）\n", "| 项 | 数量 |", "|---|---|"]
        for k in ("总用例",) + self._BUCKET_KEYS:
            lines.append(f"| {k} | {s[k]} |")
        lines += ["", f"**通过率**: {s['通过率']}%（{s['通过']}/{s['总用例']}）  ",
                  f"**有效通过率**: {s['有效通过率']}%（分母移出 {s['移出分母']} 条环境/数据问题）  ",
                  "",
                  "> 两个通过率并列：前者是原始占比，后者才是可发版口径（环境/数据问题不算产品质量差）。"]
        if s["其他异常"]:
            lines += ["", f"> ⚠️ 「其他异常」{s['其他异常']} 条：结论类别缺失或非法，需查 `records.jsonl`。"]
        lines += ["", "## 收尾门禁\n",
                  f"- **发版建议**: {self._gate_text(g)}",
                  f"- 未裁决 {g['pending']} 项 / 缺解除方式 {g['no_hint']} 项 / 人工已确认缺陷 {len(g['bugs'])} 项",
                  f"- 依据: {g['note']}"]
        if g["bugs"]:
            lines.append("- 真实缺陷（人工已确认）: " + ", ".join(f"`{c}`" for c in g["bugs"]))
        lines += ["", "## 分流结论\n",
                  "| Case ID | 用例名称 | 结论 | 分流类别 | 判定来源 | 置信度 | 裁决人 | 说明 |",
                  "|---|---|---|---|---|---|---|---|"]
        for d in rows:
            lines.append(
                f"| {d.get('id', '')} | {self._name_of(d)} "
                f"| {self._conclusion(d)} "
                f"| {self._cat_cn(d)} | {d.get('triage_source') or '—'} "
                f"| {float(d.get('triage_confidence', 0) or 0):.2f} "
                f"| {d.get('triage_decided_by') or '—'} | {md(d.get('triage_rationale'))[:120]} |")
        lines.append("")
        lines += self._md_blocked(report["blocked"])
        lines += self._md_pending(rows, report["run_id"])
        lines.append("## Details\n")
        for d in rows:
            lines.append(f"### [{self._conclusion(d)}] [{d.get('id', '')}] {self._name_of(d)}")
            lines.append(f"- Priority: {d.get('priority', '')} | Type: {d.get('case_type', '')} "
                         f"| Module: {d.get('module', '')} | Duration: {float(d.get('duration', 0) or 0):.1f}s")
            lines.append(f"- Test Point: {d.get('test_point_ref', '')} | Req Source: {d.get('req_source', '')}")
            lines.append(f"- 分流: {self._cat_cn(d)}（{d.get('triage_source') or 'none'} / "
                         f"{float(d.get('triage_confidence', 0) or 0):.2f}）"
                         f"｜依据: {md(d.get('triage_rationale'))[:200]}")
            if d.get("precondition"):
                lines.append(f"- Precondition: {d['precondition']}"
                             f"（前置已建立：{self._tri(d.get('precondition_met'))}）")
            if d.get("steps"):
                lines.append(f"- Steps:\n\n```\n{d['steps']}\n```")
            if d.get("expected"):
                lines.append(f"- Expected:\n\n```\n{d['expected']}\n```")
            if d.get("test_data"):
                lines.append(f"- Test Data: {d['test_data']}")
            for a in d.get("assertions", []):
                m = "PASS" if a["passed"] else ("FAIL" if a.get("verifiable", True) else "MANUAL")
                reason = f" — {a['reason']}" if a.get("reason") else ""
                lines.append(f"- [{m}] {a['text']}{reason}")
            if d.get("actual"):
                lines.append(f"- Actual: {str(d['actual'])[:300]}")
            if d.get("screenshot"):
                lines.append(f"- 截图: {', '.join(d['screenshot'])}")
            lines.append("")
        path = output_dir / f"{ts_file}_{suite_name}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"  MD(分流): {path.name}")

    def _is_blocked(self, d: dict) -> bool:
        """是否算 BLOCKED：只看分流类别，不看原始 `status`。

        历史数据里原始 `status=blocked` 的用例远多于真正判为阻塞的（它们因未说明阻塞原因
        回落待人工裁决）。若这里按原始 status 取数，报告会同时出现「摘要 5 条阻塞」与
        「BLOCKED 表 11 行」两套口径。
        """
        return d.get("triage_category") in BLOCKED_CATEGORIES

    _NAME_MISSING = "（名称未记录，见用例库）"   # MD / HTML / Excel 共用，不在三处各写一份

    @staticmethod
    def _name_of(d: dict) -> str:
        """用例名称单元格（Markdown）：历史 run 的阻塞用例只存了 case_id + blocker，名称必为空。"""
        from core.triage import md_escape as md
        return md(d.get("name")) or ReportExporter._NAME_MISSING

    def _conclusion(self, d: dict) -> str:
        """结论列取值：`PASSED / FAILED / BLOCKED / 待人工裁决`（spec §4.4）。

        先判待人工裁决再判阻塞：一个尚未定论的用例，就算原始状态是 blocked，人也该先去看
        裁决而不是当成「已归因于环境」。
        """
        if d.get("triage_category") == "NEEDS_HUMAN":
            return "待人工裁决"
        if self._is_blocked(d):
            return "BLOCKED"
        return self._STATUS_ICON.get(d.get("status", ""), "?")

    def _cat_cn(self, d: dict) -> str:
        cat = d.get("triage_category") or ""
        return self._CAT_CN.get(cat, cat or "未分流")

    @staticmethod
    def _gate_text(gate: dict) -> str:
        return {"allow": "✅ 建议发版", "reject": "❌ 不具备出结论条件",
                "na": "N/A（CI 浅分流，未做缺陷定性，不影响退出码）"}.get(gate["verdict"], "?")

    @staticmethod
    def _tri(v) -> str:
        """契约三态 `True/False/None` 的可读形式（None 必须显式写「未声明」，不能留空让人当「是」）。"""
        return {True: "是", False: "否"}.get(v, "未声明")

    def _md_blocked(self, blocked: list) -> list:
        """BLOCKED **单独成表**：不进摘要大数字，也不隐藏。"""
        from core.triage import md_escape as md
        out = ["## BLOCKED（环境 / 数据前置，单独成表）\n"]
        if not blocked:
            return out + ["本轮无 BLOCKED。\n"]
        out += ["| Case ID | 用例名称 | 类别 | 阻塞现象 | 解除方式（unblock_hint） |",
                "|---|---|---|---|---|"]
        for d in sorted(blocked, key=lambda x: str(x.get("id", ""))):
            out.append(f"| {d.get('id', '')} | {self._name_of(d)} | {self._cat_cn(d)} "
                       f"| {md(d.get('actual'))[:120] or '—'} "
                       f"| {md(d.get('unblock_hint')) or '⚠️ 缺失（门禁会卡）'} |")
        out += ["", "> 防滥用：BLOCKED 不计入有效通过率分母，但收尾必须**解除或写明遗留**；"
                "想靠「测不动就推给环境」逃过分母，这里逐条可见。\n"]
        return out

    def _md_pending(self, rows: list, run_id: str) -> list:
        """待人工裁决小节：报告里指明怎么裁决，别让人去翻源码找命令。"""
        pending = [d for d in rows if d.get("triage_category") == "NEEDS_HUMAN"]
        if not pending:
            return []
        from core.triage import md_escape as md
        out = ["## 待人工裁决\n",
               f"交互裁决：`python run.py triage {run_id}`（逐条选项，结论写进 `decisions.yaml`）\n",
               "| Case ID | 用例名称 | 机器结论依据 | 建议动作 |", "|---|---|---|---|"]
        for d in pending:
            out.append(f"| {d.get('id', '')} | {self._name_of(d)} "
                       f"| {md(d.get('triage_rationale'))[:160]} | {md(d.get('triage_action')) or '—'} |")
        return out + [""]

    def _print_summary_triage(self, report):
        """终端摘要：一屏看清 8 段与发版建议（分流版的 `_print_summary`）。"""
        s, g = report["summary"], report["gate"]
        print(f"\n  {'=' * 66}")
        print(f"  {report['suite_name']}  run={report['run_id']}  mode={report['mode']}")
        print(f"  总 {s['总用例']}  通过 {s['通过']}  缺陷 {s['真实缺陷']}  环境 {s['环境阻塞']}  "
              f"数据 {s['数据前置未满足']}  用例 {s['用例问题']}  执行 {s['执行未到位']}  "
              f"待裁决 {s['待人工裁决']}")
        print(f"  通过率 {s['通过率']}%  有效通过率 {s['有效通过率']}%（移出分母 {s['移出分母']}）")
        print(f"  发版建议: {self._gate_text(g)}")
        print(f"  {'=' * 66}")

    def _save_md(self,ts_file,suite_name,report, output_dir):
        """生成 Markdown 格式的报告文件。"""
        s=report["summary"]
        lines=[f"# {suite_name} - Test Report\n",f"**Time**: {report['timestamp']}  ",
               f"**Pass Rate**: {s['pass_rate']} ({s['passed']}/{s['total']})  ",f"**Duration**: {s['total_time']}\n",
               "| Status | Count |","|---|---|",f"| Passed | {s['passed']} |",f"| Failed | {s['failed']} |",f"| Errors | {s['errors']} |",f"| Manual | {s['manual']} |\n","## Details\n"]
        for d in report["details"]:
            icon={"pass":"PASS","fail":"FAIL","error":"ERR","manual":"MANUAL"}.get(d["status"],"?")
            lines.append(f"### [{icon}] [{d['id']}] {d['name']}")
            lines.append(f"- Priority: {d.get('priority','')} | Type: {d.get('case_type','')} | Module: {d.get('module','')}")
            lines.append(f"- Test Point: {d.get('test_point_ref','')} | Req Source: {d.get('req_source','')}")
            if d.get('precondition'): lines.append(f"- Precondition: {d['precondition']}")
            if d.get('steps'): lines.append(f"- Steps: {d['steps']}")
            if d.get('expected'): lines.append(f"- Expected: {d['expected']}")
            if d.get('test_data'): lines.append(f"- Test Data: {d['test_data']}")
            for a in d.get("assertions",[]):
                m="PASS" if a["passed"] else ("FAIL" if a.get("verifiable",True) else "MANUAL")
                reason=f" — {a['reason']}" if a.get("reason") else ""
                lines.append(f"- [{m}] {a['text']}{reason}")
            if d.get("output"): lines.append(f"\n```\n{d['output'][:500]}\n```")
            if d.get("error"): lines.append(f"\n- **Error**: {d['error'][:200]}")
            lines.append("")
        path=output_dir/f"{ts_file}_{suite_name}.md"
        path.write_text("\n".join(lines),encoding="utf-8")
        logger.info(f"  MD: {path.name}")

    def _save_html(self,ts_file,suite_name,ts,total_time,passed,failed,errors,manual,rate,results, output_dir):
        """旧四态 HTML 报告（14 列 / 5 卡片）。列头与卡片改走公用构造函数，与分流版共用一套行渲染。"""
        cards = _cards([("pass", passed, "Passed"), ("fail", failed, "Failed"),
                        ("error", errors, "Errors"), ("manual", manual, "Manual"),
                        ("rate", rate, "Pass Rate")])
        rows = "".join(self._html_row(d, triage=False) for d in results)
        html = HTML_TEMPLATE.format(title=suite_name, timestamp=ts, total_time=total_time, meta="",
                                    cards=cards, gate="", thead=self._html_head(False), rows=rows,
                                    extra="", footer="AI Web Test Report | Qoder + Playwright")
        path = output_dir / f"{ts_file}_{suite_name}.html"
        path.write_text(html, encoding="utf-8")
        logger.info(f"  HTML: {path.name}")

    _TRIAGE_HEADS = ("分流类别", "判定来源", "置信度", "裁决人")
    _CONCL_CLS = {"OK": "c-ok", "PRODUCT_BUG": "c-bug", "ENV_BLOCK": "c-blocked",
                  "DATA_PRECOND": "c-blocked", "NEEDS_HUMAN": "c-pending",
                  "CASE_DEFECT": "c-case", "EXEC_INCOMPLETE": "c-exec"}
    _LEGACY_HEADS = ("ID", "Case", "Module", "Type", "Priority", "Status", "Time", "Precondition",
                     "Steps", "Expected", "Test Data", "Req Source", "Test Point", "Details")

    @classmethod
    def _html_head(cls, triage: bool) -> str:
        cols = list(cls._LEGACY_HEADS) + (list(cls._TRIAGE_HEADS) if triage else [])
        return "".join(f"<th>{c}</th>" for c in cols)

    @staticmethod
    def _cell(v) -> str:
        """表格单元转义。旧版直接拼字符串，断言原文里的 `<b>` 会破坏整张表，顺手修掉。

        注意：这会让旧 HTML 报告里“含尖括号的文本”从「被浏览器吃掉」变成「正常显示」，
        属修正而非回归；其余旧输出逐字不变。
        """
        return escape(str(v if v is not None else ""), quote=False).replace("\n", "<br>")

    def _html_row(self, d: dict, triage: bool) -> str:
        cell = self._cell
        st = d.get("status", "")
        detail = []
        for a in d.get("assertions", []):
            verifiable = a.get("verifiable", True)
            cls = "assert-pass" if a["passed"] else ("assert-fail" if verifiable else "assert-manual")
            mark = "PASS" if a["passed"] else ("FAIL" if verifiable else "MANUAL")
            reason = f' — {cell(a["reason"])}' if a.get("reason") else ""
            detail.append(f'<div class="assertion {cls}">[{mark}] {cell(a["text"])}{reason}</div>')
        err_text = d.get("error") or (d.get("actual") if triage else "")
        if err_text:
            detail.append(f'<div class="assertion assert-fail">{cell(str(err_text)[:100])}</div>')
        if d.get("output"):
            detail.append(f'<div class="output">{cell(d["output"][:300])}</div>')
        icon = self._conclusion(d) if triage else {"pass": "PASS", "fail": "FAIL",
                                                   "error": "ERR", "manual": "MANUAL"}.get(st, "?")
        # 结论配色跟分流类别而不是原始 `status`：沿用 `status-fail` 的红字会把
        # 「待人工裁决」（未定论）渲染成「已确认失败」，恰好把分流要传达的信息说反。
        concl_cls = self._CONCL_CLS.get(d.get("triage_category"), "") if triage else ""
        concl_cls = concl_cls or f"status-{cell(st)}"
        cells = [d.get("id", ""), d.get("name", ""), d.get("module", ""), d.get("case_type", ""),
                 d.get("priority", ""), None, f'{float(d.get("duration", 0) or 0):.1f}s',
                 d.get("precondition", ""), d.get("steps", ""), d.get("expected", ""),
                 d.get("test_data", ""), d.get("req_source", ""), d.get("test_point_ref", ""), None]
        html = (f'<tr><td>{cell(cells[0])}</td>'
                f'<td>{cell(cells[1]) or (self._NAME_MISSING if triage else "")}</td>'
                f'<td>{cell(cells[2])}</td>'
                f'<td>{cell(cells[3])}</td><td>{cell(cells[4])}</td>'
                f'<td class="{concl_cls}">{icon}</td><td>{cells[6]}</td>'
                f'<td>{cell(cells[7])}</td><td>{cell(cells[8])}</td><td>{cell(cells[9])}</td>'
                f'<td>{cell(cells[10])}</td><td>{cell(cells[11])}</td><td>{cell(cells[12])}</td>'
                f'<td>{"".join(detail)}</td>')
        if triage:
            html += (f'<td><span class="tag">{cell(self._cat_cn(d))}</span></td>'
                     f'<td>{cell(d.get("triage_source", "")) or "—"}</td>'
                     f'<td>{float(d.get("triage_confidence", 0) or 0):.2f}</td>'
                     f'<td>{cell(d.get("triage_decided_by", "")) or "—"}</td>')
        return html + "</tr>"

    def _save_html_triage(self, ts_file, suite_name, report, output_dir):
        """分流版 HTML：6 张卡片 + 18 列 + 门禁条 + BLOCKED 独立表。"""
        s, g, q = report["summary"], report["gate"], report["quality"]
        cards = _cards([("total", s["总用例"], "Total"), ("pass", s["通过"], "Passed"),
                        ("bug", s["真实缺陷"], "Product Bugs"),
                        ("blocked", s["环境阻塞"] + s["数据前置未满足"], "Env / Data Blocked"),
                        ("pending", s["待人工裁决"], "Pending Review"),
                        ("rate", f"{s['有效通过率']}%", "Effective Pass Rate")])
        gate_cls = {"allow": "gate", "reject": "gate gate-reject", "na": "gate gate-na"}[g["verdict"]]
        gate_html = (f'<p class="{gate_cls}"><b>发版建议：</b>{self._gate_text(g)}'
                     f'（未裁决 {g["pending"]} 项 / 缺解除方式 {g["no_hint"]} 项）<br>{self._cell(g["note"])}</p>')
        rows = "".join(self._html_row(d, True) for d in
                       sorted(report["details"], key=lambda x: str(x.get("id", ""))))
        extra = self._html_blocked_table(report["blocked"])
        html = HTML_TEMPLATE.format(
            title=suite_name, timestamp=report["timestamp"], total_time=report["total_time"],
            meta=f' | <b>Run:</b> {self._cell(report["run_id"])} | <b>Mode:</b> {report["mode"]}',
            cards=cards, gate=gate_html, thead=self._html_head(True), rows=rows, extra=extra,
            footer=(f"AI Web Test Report · Result Triage v1 | run={self._cell(report['run_id'])} "
                    f"| duplicates={q['duplicates']} malformed={q['malformed']} "
                    f"| 通过率 {s['通过率']}% · 有效通过率 {s['有效通过率']}%"))
        path = output_dir / f"{ts_file}_{suite_name}.html"
        path.write_text(html, encoding="utf-8")
        logger.info(f"  HTML(分流): {path.name}")

    def _html_blocked_table(self, blocked: list) -> str:
        """BLOCKED 独立表（与 MD 同一口径：只收分流类别为环境/数据阻塞的）。"""
        head = "<h2>BLOCKED（环境 / 数据前置，单独成表）</h2>"
        if not blocked:
            return head + "<p>本轮无 BLOCKED。</p>"
        rows = "".join(
            f'<tr><td>{self._cell(d.get("id", ""))}</td><td>{self._cell(d.get("name")) or self._NAME_MISSING}</td>'
            f'<td>{self._cell(self._cat_cn(d))}</td>'
            f'<td>{self._cell(str(d.get("actual", ""))[:200]) or "—"}</td>'
            f'<td>{self._cell(d.get("unblock_hint", "")) or "⚠️ 缺失（门禁会卡）"}</td></tr>'
            for d in sorted(blocked, key=lambda x: str(x.get("id", ""))))
        return (head + '<table><tr><th>Case ID</th><th>用例名称</th><th>类别</th>'
                '<th>阻塞现象</th><th>解除方式（unblock_hint）</th></tr>' + rows +
                '</table><p style="color:#7B1FA2;font-size:13px">防滥用：BLOCKED 不计入有效通过率分母，'
                '但收尾必须解除或写明遗留。</p>')

    def _save_excel(self,ts_file,suite_name,report, output_dir, triage=False):
        """生成 Excel 报告。`triage=True` 时 14→18 列，并另起 BLOCKED 工作表。"""
        wb=Workbook(); ws=wb.active; ws.title="Test Results"
        hfont=Font(bold=True,color="FFFFFF"); hfill=PatternFill(start_color="2E75B6",end_color="2E75B6",fill_type="solid")
        thin=Border(left=Side("thin"),right=Side("thin"),top=Side("thin"),bottom=Side("thin"))
        pass_fill=PatternFill(start_color="E2EFDA",end_color="E2EFDA",fill_type="solid")
        fail_fill=PatternFill(start_color="FCE4EC",end_color="FCE4EC",fill_type="solid")
        error_fill=PatternFill(start_color="FFF3E0",end_color="FFF3E0",fill_type="solid")
        manual_fill=PatternFill(start_color="EDEDED",end_color="EDEDED",fill_type="solid")
        blocked_fill=PatternFill(start_color="E1BEE7",end_color="E1BEE7",fill_type="solid")
        bug_fill=PatternFill(start_color="FFCDD2",end_color="FFCDD2",fill_type="solid")
        pending_fill=PatternFill(start_color="FFF9C4",end_color="FFF9C4",fill_type="solid")
        fills={"pass":pass_fill,"fail":fail_fill,"error":error_fill,"manual":manual_fill,
               "blocked":blocked_fill,"skipped":manual_fill}
        cat_fills={"OK":pass_fill,"PRODUCT_BUG":bug_fill,"NEEDS_HUMAN":pending_fill,
                   "ENV_BLOCK":blocked_fill,"DATA_PRECOND":blocked_fill,
                   "CASE_DEFECT":error_fill,"EXEC_INCOMPLETE":manual_fill}
        heads=["Case ID","Name","Module","Type","Priority","Status","Duration","Precondition",
               "Steps","Expected","Test Data","Req Source","Test Point","Assertion Details"]
        widths=[14,30,10,8,8,10,10,30,35,30,20,12,12,40]
        if triage:
            heads += list(self._TRIAGE_HEADS); widths += [16,10,9,14]
        ncol = len(heads); last = get_column_letter(ncol)
        cat_col = ncol - 3                       # 分流类别列 = 追加 4 列的第 1 列；非分流模式不会用到
        ws.merge_cells(f"A1:{last}1"); ws.cell(row=1,column=1,value=f"{suite_name} - Test Report").font=Font(bold=True,size=14)
        ws.merge_cells(f"A2:{last}2"); ws.cell(row=2,column=1,value=self._excel_subtitle(report, triage))
        for col,h in enumerate(heads,1):
            c=ws.cell(row=4,column=col,value=h); c.font=hfont; c.fill=hfill; c.border=thin
        for col,w in enumerate(widths,1):
            ws.column_dimensions[get_column_letter(col)].width = w
        for i,d in enumerate(report["details"],5):
            assertions="; ".join(
                ("PASS" if a["passed"] else ("FAIL" if a.get("verifiable",True) else "MANUAL")) + ": " + a["text"] + (f" ({a['reason']})" if a.get("reason") else "")
                for a in d.get("assertions",[])
            )
            err_text = d.get("error") or (d.get("actual") if triage else "")
            if err_text: assertions += f" [Error: {str(err_text)[:80]}]"
            vals=[d.get("id",""),
                  d.get("name") or (self._NAME_MISSING if triage else ""),   # 占位只在分流模式补，旧输出逐字不变
                  d.get("module",""),d.get("case_type",""),d.get("priority",""),
                  self._conclusion(d) if triage else self._STATUS_DISPLAY.get(d["status"], d["status"]),
                  f"{float(d.get('duration',0) or 0):.1f}s",d.get("precondition",""),d.get("steps",""),
                  d.get("expected",""),d.get("test_data",""),d.get("req_source",""),
                  d.get("test_point_ref",""),assertions]
            if triage:
                vals += [self._cat_cn(d), d.get("triage_source",""),
                         float(d.get("triage_confidence",0) or 0), d.get("triage_decided_by","")]
            for col,val in enumerate(vals,1):
                c=ws.cell(row=i,column=col,value=val); c.border=thin
                # 分流模式下底色跟类别：跟原始 status 会把「待人工裁决」刷成失败粉底
                f = cat_fills.get(d.get("triage_category")) if triage else None
                if col in (1,6): c.fill=f or fills.get(d["status"],PatternFill())
                elif triage and col == cat_col and f: c.fill=f
        if triage:
            self._excel_blocked_sheet(wb, report["blocked"], hfont, hfill, thin)
        # 可选 Bugs 工作表：report 中携带 bugs 列表时自动生成
        bugs = report.get("bugs")
        if bugs:
            self._excel_bugs_sheet(wb, bugs, hfont, hfill, thin)
        path=output_dir/f"{ts_file}_{suite_name}.xlsx"
        wb.save(path)
        logger.info(f"  Excel{'' if not triage else '(分流)'}: {path.name}")

    def _save_excel_triage(self, ts_file, suite_name, report, output_dir):
        """分流版 Excel：18 列 + BLOCKED 工作表。实际渲染复用 `_save_excel(triage=True)`。"""
        self._save_excel(ts_file, suite_name, report, output_dir, triage=True)

    def _excel_subtitle(self, report, triage: bool) -> str:
        """第 2 行副标题：旧模式保持原文案，分流模式改为 8 段 + 发版建议一行可读。"""
        if not triage:
            s = report["summary"]
            return (f"Time: {report['timestamp']}  Pass Rate: {s['pass_rate']}  "
                    f"Duration: {s['total_time']}  "
                    f"Pass: {s['passed']}  Fail: {s['failed']}  "
                    f"Blocked: {s.get('blocked',0)}  Not Run: {s.get('skipped',0)}  "
                    f"Manual: {s['manual']}")
        s = report["summary"]
        return (f"Run: {report['run_id']}  Time: {report['timestamp']}  Mode: {report['mode']}  "
                f"总 {s['总用例']} 通过 {s['通过']} 缺陷 {s['真实缺陷']} 环境 {s['环境阻塞']} "
                f"数据 {s['数据前置未满足']} 用例 {s['用例问题']} 执行 {s['执行未到位']} "
                f"待裁决 {s['待人工裁决']} 其他 {s['其他异常']}  "
                f"通过率 {s['通过率']}% 有效通过率 {s['有效通过率']}%  "
                f"发版建议: {self._gate_text(report['gate'])}")

    @staticmethod
    def _excel_bugs_sheet(wb, bugs: list, hfont, hfill, thin):
        """Bugs 工作表：列出本轮测试发现的所有缺陷。

        bugs 列表中每个元素可以是 dict（含 id/title/severity 等键）
        或纯字符串（仅 bug ID）。脚本侧负责适配格式。
        """
        b = wb.create_sheet("Bugs")
        heads = ["Bug ID", "Title", "Severity", "Reproduce", "Expected", "Actual",
                 "Req Source", "Affected Cases"]
        widths = [14, 40, 14, 50, 35, 35, 14, 30]
        bug_hdr_fill = PatternFill(start_color="C0392B", end_color="C0392B", fill_type="solid")
        sev_fills = {
            "致命": PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid"),
            "严重": PatternFill(start_color="FFCDD2", end_color="FFCDD2", fill_type="solid"),
            "一般": PatternFill(start_color="FFF9C4", end_color="FFF9C4", fill_type="solid"),
            "轻微": PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid"),
        }
        for col, h in enumerate(heads, 1):
            c = b.cell(row=1, column=col, value=h)
            c.font = Font(bold=True, color="FFFFFF"); c.fill = bug_hdr_fill; c.border = thin
        for col, w in enumerate(widths, 1):
            b.column_dimensions[get_column_letter(col)].width = w
        wrap = Alignment(wrap_text=True, vertical="top")
        for idx, bug in enumerate(bugs, 2):
            if isinstance(bug, dict):
                affected = ", ".join(bug.get("affected_cases", []))
                vals = [bug.get("id", ""), bug.get("title", ""), bug.get("severity", ""),
                        bug.get("reproduce", ""), bug.get("expected", ""), bug.get("actual", ""),
                        bug.get("req_source", ""), affected]
                sev_key = bug.get("severity", "")
            else:
                vals = [str(bug), "", "", "", "", "", "", ""]
                sev_key = ""
            for col, val in enumerate(vals, 1):
                c = b.cell(row=idx, column=col, value=val)
                c.border = thin; c.alignment = wrap
                if col == 3:  # Severity 列上色带
                    for k, fill in sev_fills.items():
                        if k in str(val):
                            c.fill = fill; break
        if not bugs:
            b.cell(row=2, column=1, value="（本轮无 Bug）")

    @staticmethod
    def _excel_blocked_sheet(wb, blocked: list, hfont, hfill, thin):
        """BLOCKED 单独一个工作表（不进大数字、也不隐藏）。"""
        b = wb.create_sheet("BLOCKED")
        b.append(["Case ID", "Name", "Module", "分流类别", "阻塞现象", "解除方式（unblock_hint）"])
        for c in b[1]:
            c.font, c.fill, c.border = hfont, hfill, thin
        for d in sorted(blocked, key=lambda x: str(x.get("id", ""))):
            b.append([d.get("id", ""), d.get("name") or ReportExporter._NAME_MISSING,
                      d.get("module", ""), d.get("triage_category", ""),
                      str(d.get("actual", ""))[:200], d.get("unblock_hint") or "⚠️ 缺失（门禁会卡）"])
        if not blocked:
            b.append(["（本轮无 BLOCKED）"])
        for col, w in zip("ABCDEF", (14, 30, 12, 16, 50, 50)):
            b.column_dimensions[col].width = w

    def _print_summary(self,report):
        """在终端打印测试结果摘要。"""
        s=report["summary"]
        print(f"\n  {'='*45}")
        print(f"  {report['suite_name']}")
        print(f"  PASS: {s['passed']}  FAIL: {s['failed']}  ERR: {s['errors']}  BLOCKED: {s.get('blocked',0)}  NOT_RUN: {s.get('skipped',0)}  MANUAL: {s['manual']}  Rate: {s['pass_rate']}")
        print(f"  {'='*45}")
