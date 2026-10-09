"""
测试结果分流（Result Triage）
================================
把「执行事实」与「失败归因」分离：两条执行线写同一契约，规则层吃结构化事实，
LLM 层做语义复判，人工门禁对定性拍板。

铁律：规则层与 LLM 层都**不得单独**把用例定性为 PRODUCT_BUG 并写入发版结论，
必须经人工门禁确认。依据 Testing Frontier 实测：无人工清单时各模型 F1 < 30%，
给出清单后 49.2% —— AI 是合格执行者、不可靠规划者。

设计文档：docs/superpowers/specs/2026-09-14-result-triage-design.md
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from core import config as _cfg   # 取属性而非导入值：测试可 monkeypatch，运行时读到最新配置
                                   # Task 8 会开始用 _cfg.SPLIT_REQUIREMENTS_DIR

CATEGORIES = ("PRODUCT_BUG", "CASE_DEFECT", "EXEC_INCOMPLETE",
              "ENV_BLOCK", "DATA_PRECOND", "NEEDS_HUMAN")
# `OK` 是**非失败基线哨兵值**，仅用于 `triage.category` 的终态（由规则 R0 产出），
# 表示「确认通过、无需处理」。有它才能把「无需处理」与「待人工裁决」分开，
# 并使 8 段摘要各桶之和恒等于总用例数（自检不变量）。
FINAL_CATEGORIES = CATEGORIES + ("OK",)
# LLM 只能「提案」不能「定性」：提示词里要求真缺陷输出这个值，`merge_decisions` 强制回落 NEEDS_HUMAN。
_LLM_PROPOSAL = "PRODUCT_BUG_PROPOSAL"
STATUS_SET = ("pass", "fail", "error", "manual", "blocked", "skipped")
STEP_OUTCOMES = ("ok", "element_not_found", "skipped", "noop", "unknown")
ASSERT_VERDICTS = ("pass", "fail", "unverifiable")
SOURCES = ("rule", "llm", "human")

_REQUIRED_TOP = ("run_id", "executor", "case_id", "name", "module", "status",
                 "started_at", "precondition", "precondition_met", "test_data",
                 "error", "steps", "assertions")
_REQUIRED_TRIAGE = ("category", "source", "confidence", "rationale",
                    "suggested_action", "unblock_hint")


def make_run_id(module: str, ts: str = "") -> str:
    """线 1 用 `{清洗后模块名}_{YYYYMMDD_HHMMSS}`；线 2 由执行者指定。

    除 Windows 非法文件名字符外，还需去掉需求文档编号前缀里的中文顿号 / 逗号 / 句点
    （如 `7、知识管理` -> `7知识管理`），否则 run_id 会带出目录名难处理的字符。
    """
    safe = re.sub(r'[\\/:*?"<>|\s、，.．]+', "", module or "suite")
    return f"{safe}_{ts or datetime.now().strftime('%Y%m%d_%H%M%S')}"


def run_dir(run_id: str) -> Path:
    return _cfg.TRIAGE_DIR / run_id


def new_record(run_id: str, case_id: str, module: str = "", **kw) -> dict:
    """构造带全部必填键的记录。"""
    rec = {
        "run_id": run_id, "executor": kw.get("executor", "playwright_script"),
        "case_id": case_id, "name": kw.get("name", ""), "module": module,
        "submodule": kw.get("submodule", ""), "priority": kw.get("priority", ""),
        "case_type": kw.get("case_type", ""), "test_point_ref": kw.get("test_point_ref", ""),
        "req_source": kw.get("req_source", ""),
        "started_at": kw.get("started_at", datetime.now().isoformat(timespec="seconds")),
        "duration_sec": kw.get("duration_sec", 0.0), "status": kw.get("status", "pass"),
        "precondition": kw.get("precondition", ""),
        # 三态：True=已建立 / False=明确未建立（R6 主判据）/ None=未知（不参与 R6）
        "precondition_met": kw.get("precondition_met", None),
        "test_data": kw.get("test_data", ""),
        "error": kw.get("error", ""), "steps": kw.get("steps", []),
        "assertions": kw.get("assertions", []), "url_at_failure": kw.get("url_at_failure", ""),
        "screenshots": kw.get("screenshots", []), "log_path": kw.get("log_path", ""),
        "console_errors": kw.get("console_errors", []),
        "triage": {"category": "", "source": "none", "confidence": 0.0, "rationale": "",
                   "suggested_action": "", "unblock_hint": "", "decided_by": "",
                   "decided_at": "", "overridden": False},
        "bug_draft": None, "retry_count": 0, "needs_reconfirm": False,
    }
    return rec


def validate_record(rec: dict) -> list:
    """返回违规说明列表；空列表 = 合法。永不抛异常，由调用方决定降级策略。"""
    errs = [f"缺字段:{k}" for k in _REQUIRED_TOP if k not in rec]
    tri = rec.get("triage")
    if not isinstance(tri, dict):
        errs.append("triage 非对象")
    else:
        errs += [f"缺字段:triage.{k}" for k in _REQUIRED_TRIAGE if k not in tri]
    if rec.get("status") not in STATUS_SET:
        errs.append(f"status 非法:{rec.get('status')}")
    if "precondition_met" not in rec:
        errs.append("缺字段:precondition_met")
    elif rec["precondition_met"] not in (True, False, None):
        errs.append(f"precondition_met 非三态:{rec['precondition_met']}")
    if tri.get("category") not in ("", None) + FINAL_CATEGORIES:
        errs.append(f"category 非法:{tri.get('category')}")
    if tri.get("source") not in ("none",) + SOURCES:
        errs.append(f"source 非法:{tri.get('source')}")
    for s in rec.get("steps", []):
        if s.get("outcome") not in STEP_OUTCOMES:
            errs.append(f"step.outcome 非法:{s.get('outcome')}")
    for a in rec.get("assertions", []):
        if a.get("verdict") not in ASSERT_VERDICTS:
            errs.append(f"assertion.verdict 非法:{a.get('verdict')}")
    return errs


def record_from_result(result: dict, run_id: str, executor: str) -> dict:
    """线 1 的 result dict（含 `_check_assertion` 三态）映射为契约记录。"""
    assertions = [{"text": a.get("text", ""),
                   "verdict": "pass" if a.get("passed") else ("fail" if a.get("verifiable") else "unverifiable"),
                   "reason": a.get("reason", ""), "evidence_refs": []}
                  for a in result.get("assertions", [])]
    rec = new_record(
        run_id=run_id, case_id=result.get("case_id", "?"),
        module=result.get("module", ""),
        executor=executor, name=result.get("name", ""),
        priority=result.get("priority", ""), case_type=result.get("case_type", ""),
        test_point_ref=result.get("test_point", ""), req_source=result.get("req_source", ""),
        started_at=result.get("started_at") or datetime.now().isoformat(timespec="seconds"),
        duration_sec=result.get("duration_sec", 0.0), status=result.get("status", "pass"),
        precondition=result.get("precondition", ""),
        precondition_met=result.get("precondition_met", None),
        test_data=result.get("test_data", ""),
        error=result.get("actual", ""), steps=result.get("steps", []),
        assertions=assertions, url_at_failure=result.get("url_at_failure", ""),
        screenshots=result.get("screenshot", []), log_path=result.get("log", ""),
    )
    return rec


def append_records(records: list, rid: str) -> None:
    """追加写 `records.jsonl`；非法记录转 NEEDS_HUMAN 并记 triage_errors.log。"""
    d = run_dir(rid)
    d.mkdir(parents=True, exist_ok=True)
    bad_lines = []
    for rec in records:
        errs = validate_record(rec)
        if errs:
            bad_lines.append(f"{rec.get('case_id')}: {'; '.join(errs)}")
            rec["triage"].update(category="NEEDS_HUMAN", source="none", confidence=0.0,
                                 rationale=f"契约违规: {'; '.join(errs)}",
                                 suggested_action="人工裁决")
        with open(d / "records.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if bad_lines:
        append_error_log(rid, "record 契约违规降级 NEEDS_HUMAN:\n" + "\n".join(bad_lines))


def load_records(rid: str) -> tuple:
    """读 `records.jsonl`，同 case_id 取最后一条。返回 (records, duplicates, malformed_lines)。"""
    p = run_dir(rid) / "records.jsonl"
    if not p.exists():
        return [], 0, 0
    by_case, valid, malformed = {}, 0, 0
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        valid += 1
        by_case[rec.get("case_id", "?")] = rec     # 后写覆盖先写
    return list(by_case.values()), valid - len(by_case), malformed


def append_error_log(rid: str, msg: str) -> None:
    d = run_dir(rid)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "triage_errors.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")


def list_runs() -> list:
    """列出可分流的 run_id（新的在前）。只建了子目录但没有记录的不算 run。"""
    base = _cfg.TRIAGE_DIR
    if not base.exists():
        return []
    found = []
    for p in base.iterdir():
        rec = p / "records.jsonl"
        if p.is_dir() and rec.exists() and rec.stat().st_size > 0:
            found.append((rec.stat().st_mtime, p.name))
    return [name for _, name in sorted(found, reverse=True)]


def write_plan_cases(rid: str, case_ids: list, module: str = "", source_file: str = "") -> Path:
    """记录本 run 计划内的 case_id 全集，供 `--validate` 判断未执行缺口。由 `qoder-plan` 调用。"""
    d = run_dir(rid)
    d.mkdir(parents=True, exist_ok=True)
    payload = {"run_id": rid, "module": module, "source_file": source_file,
               "generated_at": datetime.now().isoformat(timespec="seconds"),
               "case_ids": list(case_ids)}
    (d / "plan_cases.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    return d / "plan_cases.json"


def load_plan_cases(rid: str):
    """读 `plan_cases.json`；不存在或损坏返回 None（缺口校验降级为跳过，不误报）。"""
    p = run_dir(rid) / "plan_cases.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) and "case_ids" in data else None


def diff_plan_vs_records(plan, records: list) -> dict:
    """计划 vs 实际记录的差集。`plan` 为 None 或为空时只报已记录数，missing/extra 留空。"""
    recorded = [r.get("case_id", "?") for r in (records or [])]
    planned = list((plan or {}).get("case_ids", []))
    if not planned:
        return {"planned": 0, "recorded": len(recorded), "missing": [], "extra": []}
    return {"planned": len(planned),
            "recorded": len([c for c in recorded if c in planned]),
            "missing": [c for c in planned if c not in recorded],
            "extra": [c for c in recorded if c not in planned]}


# ── 规则层：按序先命中先定 ─────────────────────────────────────────
# 铁律：本函数**永不产出 PRODUCT_BUG**。负向单测 test_rule_layer_never_produces_product_bug 守此。
# 真实缺陷定性必须经 LLM 提案 + 人工门禁确认。
_ENV_ERR_KEYWORDS = ("ECONNREFUSED", "net::ERR", "404", "500", "Timeout", "timed out", "连接被拒绝")
_MISSING_PRECOND_KEYWORDS = ("未准备", "无法提供", "缺少测试数据", "需要先", "未上传",
                             "依赖TC", "无法验证", "无法保证", "前置数据")
_UNVERIFIABLE_REASON_KEYWORDS = ("缺少可定位目标", "未定位到结果容器", "断言缺少可验证内容")
_BAD_STEP_OUTCOMES = ("element_not_found", "skipped")
_OK_STEP_OUTCOMES = ("ok", "noop")   # 二者均视为真实到位；noop=观察类/「已在目标页」有意不执行


def _texts_of(rec: dict) -> str:
    """R6 的文本判定域：前置、数据、错误现象、步骤明细四者拼接。"""
    parts = [rec.get("precondition", ""), rec.get("test_data", ""), rec.get("error", "")]
    parts += [s.get("detail", "") for s in rec.get("steps", [])]
    parts += [s.get("action", "") for s in rec.get("steps", [])]
    return " ".join(p for p in parts if p)


def _hit(text: str, keywords) -> str:
    """关键字匹配前对两侧都做空白归一化，避免「依赖 TC-知识管理-分类管理-001」与「依赖TC-知识管理-分类管理-001」两种写法漏判。"""
    norm = re.sub(r"\s+", "", text or "")
    for k in keywords:
        if re.sub(r"\s+", "", k) in norm:
            return k
    return ""


def _is_login_case(rec: dict) -> bool:
    module = rec.get("module", "") or ""
    name = rec.get("name", "") or ""
    cid = rec.get("case_id", "") or ""
    # 新格式 ID 自带模块名段（如 TC-登录-001）；旧格式靠 TC-AUTH 前缀识别
    return "登录" in module or "登录" in name or "登录" in cid or cid.upper().startswith("TC-AUTH")


def run_rule_layer(rec: dict, env_preflight_failed: bool = False) -> dict:
    """返回 `{category, confidence, rationale, suggested_action, unblock_hint}`。"""
    steps, asserts = rec.get("steps", []), rec.get("assertions", [])
    st, url, err = rec.get("status", ""), rec.get("url_at_failure", ""), rec.get("error", "")
    texts = _texts_of(rec)
    bad_steps = [s for s in steps if s.get("outcome") in _BAD_STEP_OUTCOMES]

    def out(cat, conf, why, act, hint=""):
        return {"category": cat, "confidence": conf, "rationale": why,
                "suggested_action": act, "unblock_hint": hint}

    if env_preflight_failed:
        return out("ENV_BLOCK", 1.0, "R1：环境预检未通过，本 run 用例未真实执行", "修环境后整 run 重跑",
                   "确认 TARGET_SERVERS 可达且登录凭据有效")
    if st == "pass" and steps and all(s.get("outcome") in _OK_STEP_OUTCOMES for s in steps) \
            and asserts and all(a.get("verdict") == "pass" for a in asserts):
        return out("OK", 1.0, "R0：步骤全部真实到位、全部断言通过", "无需处理")
    if st == "error" and (k := _hit(err, _ENV_ERR_KEYWORDS)):
        return out("ENV_BLOCK", 0.9, f"R2：error 命中环境关键字 {k}", "查服务与网络后重跑")
    if "/login" in (url or "") and not _is_login_case(rec):
        return out("ENV_BLOCK", 0.85, "R3：失败时停在 /login，会话掉线导致连锁失败（登录态未持久化）",
                   "改用 storageState 持久化登录态后重跑；若已持久化仍复现，人工推翻本归类")
    if st in ("fail", "error", "manual", "blocked") and rec.get("precondition_met") is False:
        return out("DATA_PRECOND", 0.9, "R6：执行者明确声明前置条件未建立（precondition_met=false）",
                   "补前置数据后重跑",
                   "按 precondition/test_data 补齐账号、文件与依赖数据")
    if st == "blocked":
        # blocked 只由转换器写入，执行线永不写。命中关键字归数据前置，否则未说明原因送人工。
        if k := _hit(texts, _MISSING_PRECOND_KEYWORDS):
            return out("DATA_PRECOND", 0.9, f"R6：blocker 命中未备齐关键字 {k}", "补前置条件后重跑",
                       rec.get("triage", {}).get("unblock_hint") or "补齐该用例声明的前置数据/账号/文件")
        return out("NEEDS_HUMAN", 0.0, "R8：blocked 但未说明阻塞原因", "人工裁决")
    if bad_steps:
        s = bad_steps[0]
        return out("EXEC_INCOMPLETE", 0.9,
                   f"R4：步骤 {s.get('order')} outcome={s.get('outcome')}，断言在未到位页面上执行",
                   "修定位器或补 _execute_action 动作映射后重跑")
    if st != "pass" and asserts and all(a.get("verdict") == "unverifiable" for a in asserts):
        # 守卫 `st != "pass"`：status=pass 且断言全不可验证是典型「幻觉通过」，
        # 不得被 R5 当成「用例写坏了」轻轻放过，必须落到下面 R8 送人工裁决。
        return out("CASE_DEFECT", 0.9, "R5：全部断言均不可自动验证（断言目标不可定位）",
                   "回灌 design 阶段重写为可定位断言")
    if st in ("fail", "error", "manual") and (k := _hit(texts, _MISSING_PRECOND_KEYWORDS)):
        return out("DATA_PRECOND", 0.9, f"R6：前置/测试数据未备齐（命中关键字 {k}）",
                   "补前置数据后重跑", "准备 record.precondition/test_data 中声明的数据与账号")
    real_fail = [a for a in asserts if a.get("verdict") == "fail"]
    if st == "fail" and real_fail:
        return out("NEEDS_HUMAN", 0.0,
                   "R7：步骤到位且存在可验证断言失败，疑似真实缺陷，规则层不下结论", "送 LLM 复判 / 人工裁决")
    if st == "pass":
        # 走到了这里说明 R0 未命中（无断言明细 / 断言不可验证 / step 为 unknown）：属混合态，不得自行算作通过
        return out("NEEDS_HUMAN", 0.0, "R8：status=pass 但缺可自证的事实（无断言或步骤未声明）", "人工裁决")
    return out("NEEDS_HUMAN", 0.0, "R8：混合态，规则层无法判定", "人工裁决")


def apply_rule_layer(records: list, env_preflight_failed: bool = False) -> list:
    for rec in records:
        res = run_rule_layer(rec, env_preflight_failed=env_preflight_failed)
        # 规则层未给出具体解除路径时，不擦掉已有 `unblock_hint`（转换器从 blocker 带进来的那条更具体）
        if not res.get("unblock_hint"):
            res["unblock_hint"] = rec["triage"].get("unblock_hint", "")
        rec["triage"].update(res)
        rec["triage"]["source"] = "rule"
    return records


# ── 结论文件读写 ───────────────────────────────────────────────
# `decisions.yaml` 的非裁决顶层字段（手改时易被当成一条用例读进来）
_DECISION_TOP_KEYS = ("run_id", "decided_at", "decisions")
# 降级解析时需要转 bool 的键（YAML 缺失时会把所有值读成字符串）
_BOOL_KEYS = ("confirmed_by_human", "overridden", "needs_reconfirm")


def load_llm_review(rid: str) -> dict:
    p = run_dir(rid) / "llm_review.jsonl"
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("case_id"):
                out[d["case_id"]] = d
    return out


def load_decisions(rid: str) -> dict:
    """读 `decisions.yaml`（人拍板证据）。文件不存在返回 {}；不因缺 PyYAML 或文件写坏而崩溃。

    无论解析成功还是失败，只要文件非空却读出 0 条裁决就记 `triage_errors.log`：
    人工裁决是唯一能定性 `PRODUCT_BUG` 的入口，静默丢弃会让人以为「已签过字就生效」。
    """
    p = run_dir(rid) / "decisions.yaml"
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError:
        data = _parse_decisions_fallback(text)
    else:
        try:
            data = yaml.safe_load(text) or {}
        except Exception as e:            # 写坏的 YAML 只可能来自手工编辑，必须留痕不能装没看见
            append_error_log(rid, f"decisions.yaml 解析失败，本次人工裁决未生效：{e}")
            return {}
    decisions = _normalize_decisions(data)
    if not decisions and text.strip():
        append_error_log(rid, "decisions.yaml 非空但解析出 0 条裁决：格式与约定不符，人工裁决未生效")
    return decisions


def _normalize_decisions(data) -> dict:
    """把 `decisions.yaml` 的两种写法统一成 `{case_id: {...}}`。

    列表式（`- case_id: X`）是 `save_decisions` 降级格式的写法、也是人手写最自然的写法；
    不归一的话它会解析成 list，`cid in human` 恒为假 —— 人的裁决凭空消失且不报错。
    """
    inner = data.get("decisions", data) if isinstance(data, dict) else data
    if isinstance(inner, dict):
        return {str(k): (v if isinstance(v, dict) else {})
                for k, v in inner.items() if k not in _DECISION_TOP_KEYS}
    if isinstance(inner, list):
        return {str(it["case_id"]): {k: v for k, v in it.items() if k != "case_id"}
                for it in inner if isinstance(it, dict) and it.get("case_id")}
    return {}


def _as_bool(key: str, value: str):
    """降级解析里只有已知布尔键做转换，避免把 `note: true story` 这类文本改坏。"""
    if key in _BOOL_KEYS:
        low = value.strip().lower()
        if low in ("true", "yes", "是"):
            return True
        if low in ("false", "no", "否"):
            return False
    return value


def _parse_decisions_fallback(text: str) -> dict:
    """PyYAML 缺失时的极简解析：列表式与映射式都认，值为空的 `key:` 行开一个 case 块。"""
    out, cur = {}, None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        k, v = s.split(":", 1)
        k, v = k.strip().lstrip("-").strip(), v.strip().strip("'\"")
        if k == "case_id" and v:
            cur, out[cur] = v, {}
            continue
        if not v:
            cur = None if k in _DECISION_TOP_KEYS else k
            if cur is not None:
                out[cur] = {}
            continue
        if cur is not None:
            out[cur][k] = _as_bool(k, v)
    return out


def save_decisions(rid: str, decisions: dict) -> Path:
    """写 `decisions.yaml`。优先用 PyYAML 真格式，缺失时降级为手写 YAML 风格文本。"""
    d = run_dir(rid)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "decisions.yaml"
    header = (f"# 人工裁决结论（最高优先级）—— 分流铁律要求 PRODUCT_BUG 定性必须出自本文件\n"
              f"run_id: {rid}\ndecided_at: {datetime.now().isoformat(timespec='seconds')}\n")
    try:
        import yaml
        body = yaml.safe_dump({"decisions": decisions}, allow_unicode=True, sort_keys=False)
        p.write_text(header + body, encoding="utf-8")
    except ImportError:
        # 降级写法：`decisions:` 不能同时出现在 header 里，否则同一文档里出现重复键
        lines = ["decisions:"]
        for cid, v in decisions.items():
            lines.append(f"  - case_id: {cid}")
            for k, val in v.items():
                lines.append(f"    {k}: {str(val)!r}")
        p.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return p


def append_llm_review(rid: str, items: list) -> None:
    d = run_dir(rid)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "llm_review.jsonl", "a", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


# ── 三层合并 ────────────────────────────────────────────────
_STATUS_BY_CATEGORY = {"CASE_DEFECT": "manual", "EXEC_INCOMPLETE": "manual"}
# 名字不带下划线：报告层（`exporters/report_exporter.py`）要用同一口径挑 BLOCKED，
# 跨模块不外泄私有；否则报告会按原始 status 取数，与摘要的类别桶分成两套口径。
BLOCKED_CATEGORIES = ("ENV_BLOCK", "DATA_PRECOND")


def merge_decisions(records: list, llm: dict, human: dict,
                    conf_threshold: float = None, simple: bool = None) -> dict:
    """人 > LLM > 规则，返回 {case_id: record}。

    simple=False（默认）：完整三层分流铁律——
      ① 非人工来源的 PRODUCT_BUG 一律拒收并回落 NEEDS_HUMAN；
      ② ENV_BLOCK/DATA_PRECOND 缺 `unblock_hint` 视为未说明阻塞原因，降级 NEEDS_HUMAN。

    simple=True：简化模式——
      LLM 可直接定性 PRODUCT_BUG（不经人工门禁），拿不准的才回落 NEEDS_HUMAN。
    """
    if conf_threshold is None:
        from core.config import TRIAGE_CONF_THRESHOLD
        conf_threshold = TRIAGE_CONF_THRESHOLD
    if simple is None:
        from core.config import TRIAGE_SIMPLE
        simple = TRIAGE_SIMPLE
    merged = {}
    for rec in records:
        cid = rec.get("case_id", "?")
        tri = dict(rec["triage"])
        low = []
        if cid in llm:
            v = llm[cid]
            conf, cat = float(v.get("confidence", 0) or 0), v.get("verdict", "")
            if simple and cat == _LLM_PROPOSAL:
                # 简化模式：把提案当作 AI 已确认的 PRODUCT_BUG
                tri.update({"category": "PRODUCT_BUG", "source": "llm", "confidence": conf,
                            "rationale": v.get("rationale", ""),
                            "suggested_action": v.get("suggested_fix", "") or tri.get("suggested_action", ""),
                            "unblock_hint": v.get("unblock_hint", "") or tri.get("unblock_hint", "")})
                rec["bug_draft"] = v.get("bug_draft") or rec.get("bug_draft")
            elif cat == _LLM_PROPOSAL:
                # 完整模式：提案不是结论，仍回落 NEEDS_HUMAN 排队给人工门禁
                rec["llm_proposal"] = {"confidence": conf, "rationale": v.get("rationale", ""),
                                       "evidence_cited": v.get("evidence_cited", []),
                                       "bug_draft": v.get("bug_draft")}
                low.append(f"LLM 提案真实缺陷（{_LLM_PROPOSAL}，置信 {conf}），待人工拍板")
                tri.update({"category": "NEEDS_HUMAN", "confidence": 0.0,
                            "suggested_action": v.get("suggested_fix", "") or tri.get("suggested_action", ""),
                            "unblock_hint": v.get("unblock_hint", "") or tri.get("unblock_hint", "")})
            elif cat and cat in CATEGORIES and conf >= conf_threshold:
                tri.update({"category": cat, "source": "llm", "confidence": conf,
                            "rationale": v.get("rationale", ""),
                            "suggested_action": v.get("suggested_fix", "") or tri.get("suggested_action", ""),
                            "unblock_hint": v.get("unblock_hint", "") or tri.get("unblock_hint", "")})
                # 简化模式下 LLM 直接定性 PRODUCT_BUG 时，接住 bug_draft
                if simple and cat == "PRODUCT_BUG":
                    rec["bug_draft"] = v.get("bug_draft") or rec.get("bug_draft")
            else:
                low.append(f"LLM 低置信({conf}<{conf_threshold})或结论非 6 类({cat or '空'})，已忽略")
        if cid in human:
            h = human[cid]
            hc = h.get("final_category", "")
            # 只要 `confirmed_by_human` 不是真值就不算人工裁决（CI 预写的建议、手改漏签等），
            # 否则 CI 预写的建议会被当成人工裁决：`source=human`、`needs_reconfirm=False`，等于机器替人签字。
            confirmed = h.get("confirmed_by_human") is True
            if confirmed and hc in CATEGORIES and hc != "PRODUCT_BUG":
                tri.update({"category": hc, "source": "human", "confidence": 1.0,
                            "rationale": h.get("note", "") or tri.get("rationale", ""), "decided_by": "",
                            # 人给的解除路径必须带下去：不接住的话，下面「BLOCKED 缺 unblock_hint 就降级」
                            # 那一判会把人刚标完的阻塞退回待裁决。
                            "unblock_hint": h.get("unblock_hint", "") or tri.get("unblock_hint", ""),
                            "decided_at": h.get("decided_at", ""), "overridden": True})
                tri["decided_by"] = h.get("decided_by", "unknown")
            elif confirmed and hc == "PRODUCT_BUG":
                # CI 无人值守时 `_auto_default_decision` 会预写 PRODUCT_BUG 建议，属未经人确认，
                # 必须与 LLM 同权降级，否则「机器自己批准自己定性」这条铁律形同虚设。
                tri.update({"category": "PRODUCT_BUG", "source": "human", "confidence": 1.0,
                            "rationale": h.get("note", "") or tri.get("rationale", ""),
                            # 严重程度也只能由人给：不接住，Bug 草稿那一栏永远回落「待定」。
                            "severity": h.get("severity", "") or tri.get("severity", ""),
                            "decided_by": h.get("decided_by", "unknown"),
                            "decided_at": h.get("decided_at", ""), "overridden": True})
                rec["bug_draft"] = h.get("bug_draft") or rec.get("bug_draft")
            else:
                # 未经人确认的「裁决」不当结论用，但也不能反过来擦掉规则/LLM 已有的判定：
                # CI 只要预写一条就会把整批 LLM 结论打回 NEEDS_HUMAN，信息净损失。
                low.append(f"human 结论 {hc or '空'} 未经人确认（confirmed_by_human!=true），未采纳")
        if not simple and tri.get("category") == "PRODUCT_BUG" and tri.get("source") != "human":
            low.append(f"{tri.get('source')} 层拒绝定性 PRODUCT_BUG（分流铁律）")
            tri.update({"category": "NEEDS_HUMAN", "confidence": 0.0})
        if tri.get("category") in BLOCKED_CATEGORIES and not (tri.get("unblock_hint") or "").strip():
            low.append(f"{tri['category']} 缺 unblock_hint")
            tri.update({"category": "NEEDS_HUMAN", "confidence": 0.0})
        if low:
            tri["rationale"] = "；".join(low + [tri.get("rationale", "")]).strip("；")
        rec["triage"] = tri
        rec["needs_reconfirm"] = tri.get("source") != "human"
        merged[cid] = rec
    return merged


def derived_status(rec: dict) -> str:
    """分流层派生状态：`blocked` 不回写 `records.jsonl`，仅在合并后派生。"""
    cat, st = rec["triage"].get("category", ""), rec.get("status", "")
    if cat in BLOCKED_CATEGORIES:
        return "blocked"
    if cat in _STATUS_BY_CATEGORY:
        return _STATUS_BY_CATEGORY[cat]
    return st


def compute_summary(merged: dict) -> dict:
    """8 段摘要 + 两个通过率。`总用例` == 各桶之和（依赖 `OK` 哨兵使此不变量成立）。"""
    buckets = {"通过": 0, "真实缺陷": 0, "环境阻塞": 0, "数据前置未满足": 0,
               "用例问题": 0, "执行未到位": 0, "待人工裁决": 0, "其他异常": 0}
    cat2bucket = {"OK": "通过", "PRODUCT_BUG": "真实缺陷", "ENV_BLOCK": "环境阻塞",
                  "DATA_PRECOND": "数据前置未满足", "CASE_DEFECT": "用例问题",
                  "EXEC_INCOMPLETE": "执行未到位", "NEEDS_HUMAN": "待人工裁决"}
    for rec in merged.values():
        cat = rec["triage"].get("category", "")
        if cat in cat2bucket:
            buckets[cat2bucket[cat]] += 1
        else:
            # 含 category 为空（未跑过规则层）与非法值：不静默丢弃，单开一桶供自检
            buckets["其他异常"] += 1
    total = max(len(merged), 1)
    moved = buckets["环境阻塞"] + buckets["数据前置未满足"]
    denom = total - moved
    passed = buckets["通过"]
    return {**buckets, "总用例": len(merged),
            "通过率": round(passed / total * 100, 1),
            "有效通过率": round(passed / denom * 100, 1) if denom else 0.0,
            "移出分母": moved}


def evaluate_gate(merged: dict, mode: str = "strict") -> dict:
    """收尾门禁。`strict`=人在场，未裁决即卡发版建议；`report_only`=CI，结论 N/A 且不影响退出码。

    设计理由：人不在场时不存在发版决策，把「未定论」伪装成「否决」只会让人整个绕过分流层。
    """
    pending = [c for c, r in merged.items() if r["triage"].get("category") == "NEEDS_HUMAN"]
    no_hint = [c for c, r in merged.items()
               if r["triage"].get("category") in BLOCKED_CATEGORIES
               and not (r["triage"].get("unblock_hint") or "").strip()]
    bugs = [c for c, r in merged.items() if r["triage"].get("category") == "PRODUCT_BUG"]
    if mode != "strict":
        return {"verdict": "na", "pending": len(pending), "no_hint": len(no_hint), "bugs": bugs,
                "note": "CI 浅分流：未做缺陷定性，发版建议为 N/A，不影响退出码", "blocks_exit_code": False}
    if pending or no_hint:
        return {"verdict": "reject", "pending": len(pending), "no_hint": len(no_hint), "bugs": bugs,
                "note": "存在未裁决项或 BLOCKED 未说明解除路径，不具备出结论条件", "blocks_exit_code": True}
    return {"verdict": "allow", "pending": 0, "no_hint": 0, "bugs": bugs,
            "note": "人工核没通过才是真不过", "blocks_exit_code": False}


def collect_quarantine(rid: str, merged: dict) -> list:
    """线 2 被人推翻过的用例单独记账（本期只记录不重跑），作二期 FLAKY 判定数据基础。"""
    return [{"case_id": cid, "executor": r.get("executor"), "module": r.get("module"),
             "rule_or_llm": r["triage"].get("rationale", ""), "decided_by": r["triage"].get("decided_by", "")}
            for cid, r in merged.items()
            if r.get("executor") == "qoder_mcp" and r["triage"].get("overridden")]


def write_quarantine(rid: str, merged: dict) -> Path:
    rows = collect_quarantine(rid, merged)
    p = run_dir(rid) / "quarantine.md"
    lines = [f"# Quarantine（Qoder MCP 线被人工推翻过的用例）", "",
             f"run_id: {rid} | 条目: {len(rows)}", "",
             "| Case ID | 模块 | 机器结论依据 | 裁决人 |", "|---|---|---|---|"]
    lines += [f"| {r['case_id']} | {r['module']} | {r['rule_or_llm']} | {r['decided_by']} |" for r in rows]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ── 反向映射：契约记录 → 旧报告层所需 result 行 ────────────────
_RESULT_STATUS_FOR_REPORT = {"pass": "pass", "fail": "fail", "error": "error",
                             "manual": "manual", "blocked": "blocked", "skipped": "skipped"}


def to_result_rows(records: list) -> list:
    """契约记录 → 旧 `build_and_save()` 所需 result 行（键名与 `tester_agent` 产物对齐）。

    存在的意义：分流结论要同时进 MD/HTML/Excel 三份报告，而旧报告路径按
    `id/name/status/duration/steps/expected/assertions` 取值。反向映射使 `records.jsonl`
    成为唯一事实源，无需改执行线已有产物。
    """
    rows = []
    for r in records:
        tri = r.get("triage", {})
        rows.append({
            "id": r.get("case_id", ""), "name": r.get("name", ""),
            "module": r.get("module", ""), "case_type": r.get("case_type", ""),
            "priority": r.get("priority", ""),
            "status": _RESULT_STATUS_FOR_REPORT.get(r.get("status", ""), "error"),
            "duration": float(r.get("duration_sec", 0) or 0),
            "precondition": r.get("precondition", ""),
            "steps": "\n".join(f'{s.get("order")}.\u3000{s.get("action")} → {s.get("outcome")}'
                               for s in r.get("steps", [])),
            "expected": "\n".join(f'{i + 1}.\u3000{a.get("text")} → {a.get("verdict")}'
                                 for i, a in enumerate(r.get("assertions", []))),
            "expected_results": [{"expect": a.get("text", ""), "verdict": a.get("verdict", "")}
                                 for a in r.get("assertions", [])],
            "test_data": r.get("test_data", ""),
            "precondition_met": r.get("precondition_met", None),
            "actual": r.get("error", ""),
            "assertions": [{"text": a.get("text", ""),
                            "passed": a.get("verdict") == "pass",
                            "verifiable": a.get("verdict") != "unverifiable",
                            "reason": a.get("reason", "")} for a in r.get("assertions", [])],
            "screenshot": r.get("screenshots", []), "log": r.get("log_path", ""),
            "req_source": r.get("req_source", ""), "test_point_ref": r.get("test_point_ref", ""),
            "triage_category": tri.get("category", ""), "triage_source": tri.get("source", ""),
            "triage_confidence": tri.get("confidence", 0.0),
            "triage_decided_by": tri.get("decided_by", ""),
            "triage_rationale": tri.get("rationale", ""),
            "triage_action": tri.get("suggested_action", ""),
            "unblock_hint": tri.get("unblock_hint", ""),
        })
    return rows


# ── LLM 复判输入包 ────────────────────────────────────────────
# 只认「首列是需求 ID」的表格行，如 `| CAT-01 | 仅文档知识库下支持新建分类 | … |`；
# 前缀至少两个大写字母，避免把 `| F-CAT-01 |`（功能 ID）误当成需求 ID。
_REQ_ROW_RE = re.compile(r"^\|\s*([A-Z]{2,6}-[A-Z]?\d+)\s*\|\s*(.+?)\s*\|")


def _req_files_for(module: str) -> list:
    """优先只扫 02_split_requirements 下路径含模块名的文件，避免跨模块需求 ID 碰撞。"""
    base = _cfg.SPLIT_REQUIREMENTS_DIR
    if not base.exists():
        return []
    all_md = sorted(base.rglob("*.md"))
    hits = [p for p in all_md if module and module in str(p)]
    return hits or all_md


def find_req_snippets(module: str, req_source: str, max_len: int = 400) -> dict:
    """按需求 ID（如 `CAT-01,CAT-04`）从拆分需求文档里抽出原文行。

    这是「把人工清单喂给 AI」的具体实现：Testing Frontier 实测同一模型无人工清单时
    F1 < 30%，给出清单后 49.2%。抽不到时返回 {}，由提示词层要求「拿不准则回落 NEEDS_HUMAN」。
    """
    wanted = {t.strip().upper() for t in re.split(r"[,，;；/\s]+", req_source or "") if t.strip()}
    if not wanted:
        return {}
    hits = {}
    for p in _req_files_for(module):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line in lines:
            m = _REQ_ROW_RE.match(line.strip())
            if m and m.group(1).upper() in wanted:
                hits.setdefault(m.group(1).upper(), m.group(2)[:max_len])
        if len(hits) == len(wanted):
            break
    return hits


def build_triage_payload(rid: str, records: list, threshold: float = None,
                         simple: bool = None) -> list:
    """打包待 LLM 判定的用例。

    simple=False（默认）：只打包规则层未定论（NEEDS_HUMAN）的用例。
    simple=True：打包所有非 OK 的用例（规则层只负责确认通过，其余全交 LLM）。
    """
    if threshold is None:
        from core.config import TRIAGE_CONF_THRESHOLD
        threshold = TRIAGE_CONF_THRESHOLD
    if simple is None:
        from core.config import TRIAGE_SIMPLE
        simple = TRIAGE_SIMPLE
    payload = []
    for rec in records:
        tri = rec.get("triage", {})
        if simple:
            # 简化模式：只有规则层确认 OK 的才跳过，其余全送 LLM
            if tri.get("category") == "OK":
                continue
        else:
            if tri.get("category") != "NEEDS_HUMAN":
                continue
        payload.append({
            "case_id": rec.get("case_id"), "name": rec.get("name"),
            "module": rec.get("module"), "priority": rec.get("priority"),
            "status": rec.get("status"), "derived_status": derived_status(rec),
            "precondition": rec.get("precondition"), "precondition_met": rec.get("precondition_met"),
            "test_data": rec.get("test_data"), "error": rec.get("error"),
            "steps": rec.get("steps", []), "assertions": rec.get("assertions", []),
            "url_at_failure": rec.get("url_at_failure"), "screenshots": rec.get("screenshots", []),
            "console_errors": rec.get("console_errors", [])[:5],
            "requirement": find_req_snippets(rec.get("module", ""), rec.get("req_source", "")),
            "rule_layer_excluded": tri.get("rationale", ""),
            "existing_bug_draft": rec.get("bug_draft"),
            "confidence_threshold": threshold,
        })
    return payload


# ── 分流产物（文件即状态：下一阶段只读文件，不怕中断）───────────────
def md_escape(v) -> str:
    """表格单元格里不能出现 `|` 与真换行，否则整张 Markdown 报告都会错位。

    名字不带下划线：报告层（`exporters/report_exporter.py`）也要用，跨模块不外泄私有。
    """
    return str(v if v is not None else "").replace("|", "\\|").replace("\n", " ")


def write_pending_review(rid: str, merged: dict) -> Path:
    """待人工裁决清单。人在这里勾选，或直接跑 `python run.py triage {rid}` 交互裁决。"""
    rows = [r for r in merged.values() if r["triage"].get("category") == "NEEDS_HUMAN"]
    lines = [f"# 待人工裁决清单（{rid}）", "",
             f"共 {len(rows)} 项。未清零前收尾门禁不得给出「建议发版」（strict 模式）。", "",
             "| Case ID | 用例名称 | 模块 | 状态 | 机器结论依据 | LLM 提案 | 建议 | 你的裁决 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: x.get("case_id", "")):
        tri = r["triage"]
        prop = r.get("llm_proposal") or {}
        prop_txt = f"{prop.get('rationale', '')}（置信 {prop.get('confidence', '')}）" if prop else "—"
        lines.append(f"| {md_escape(r.get('case_id'))} | {md_escape(r.get('name'))} "
                     f"| {md_escape(r.get('module'))} | {md_escape(r.get('status'))} "
                     f"| {md_escape(tri.get('rationale'))[:160]} | {md_escape(prop_txt)[:160]} "
                     f"| {md_escape(tri.get('suggested_action'))} "
                     f"| ☐bug ☐case ☐env ☐data ☐exec ☐skip |")
    lines += ["", "> 裁决为 `env`/`data` 时**必须**填 `unblock_hint`（如何解除阻塞），否则会被回落。",
              "> 铁律：`PRODUCT_BUG` 只能由人定性，`[q]` 批量接受也不包括它与环境/数据阻塞。",
              f"> 交互裁决：`python run.py triage {rid}`（逐条选项，结论写入 `decisions.yaml`）。", ""]
    p = run_dir(rid) / "pending_review.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def collect_fix_list(merged: dict) -> dict:
    """按「谁该改」分组：用例作者（CASE_DEFECT）、执行层（EXEC_INCOMPLETE）、运维（ENV/DATA）。"""
    groups = {"用例问题": [], "执行未到位": [], "环境阻塞": [], "数据前置未满足": []}
    cat2group = {"CASE_DEFECT": "用例问题", "EXEC_INCOMPLETE": "执行未到位",
                 "ENV_BLOCK": "环境阻塞", "DATA_PRECOND": "数据前置未满足"}
    for cid, r in merged.items():
        cat = r["triage"].get("category", "")
        if cat in cat2group:
            groups[cat2group[cat]].append(r)
    return groups


def write_fix_list(rid: str, merged: dict) -> Path:
    """回灌 design 阶段的清单（只出清单，不改设计代码，避免范围膨胀）。

    只写 `CASE_DEFECT` / `EXEC_INCOMPLETE` 两组：环境/数据前置不归用例作者管，
    混进「用例修复清单」只会让人对着环境问题改用例；那两类在报告的 BLOCKED 表里。
    """
    groups = collect_fix_list(merged)
    lines = [f"# 用例与执行修复清单（{rid}）", "",
             "分流结论为 `CASE_DEFECT` / `EXEC_INCOMPLETE` 的用例**不提 Bug**，在此回灌修复。", ""]
    for gname in ("用例问题", "执行未到位"):
        rows = groups[gname]
        lines += [f"## {gname}（{len(rows)}）", ""]
        if not rows:
            lines += ["_无_", ""]
            continue
        lines += ["| Case ID | 用例名称 | 现象/依据 | 修复建议 |", "|---|---|---|---|"]
        for r in sorted(rows, key=lambda x: x.get("case_id", "")):
            tri = r["triage"]
            hint = tri.get("unblock_hint", "")
            fix = (tri.get("suggested_action") or "") + (f"；解除方式：{hint}" if hint else "")
            lines.append(f"| {md_escape(r.get('case_id'))} | {md_escape(r.get('name'))} "
                         f"| {md_escape(tri.get('rationale'))[:160]} | {md_escape(fix)} |")
        lines.append("")
    blocked = len(groups["环境阻塞"]) + len(groups["数据前置未满足"])
    lines += [f"> 另有 {blocked} 条属环境/数据前置（不计入本清单），见报告 BLOCKED 表与"
              f" `gate.json` 摘要。", ""]
    p = run_dir(rid) / "triage_用例修复清单.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def _first_fail_text(rec: dict) -> str:
    for a in rec.get("assertions", []):
        if a.get("verdict") == "fail":
            return f"{a.get('text')}（{a.get('reason', '')}）"
    return ""


def _bug_draft_of(rec: dict) -> dict:
    """人确认定性后，草稿正文优先用人/执行层留下的 `bug_draft`，其次才用 LLM 提案里的草稿。

    铁律约束的是「谁来定性」，不是「谁来打草稿」：拒收 LLM 定性 ≠ 连它写的草稿也扔进垃圾桶。
    """
    return rec.get("bug_draft") or (rec.get("llm_proposal") or {}).get("bug_draft") or {}


def write_bug_drafts(rid: str, merged: dict, simple: bool = None) -> list:
    """为已确认的 PRODUCT_BUG 出草稿；不同步 Jira/GitHub，只出 Markdown。

    simple=False（默认）：仅为人工确认的 PRODUCT_BUG 出草稿（铁律）。
    simple=True：LLM 确认的 PRODUCT_BUG 也出草稿。
    """
    if simple is None:
        from core.config import TRIAGE_SIMPLE
        simple = TRIAGE_SIMPLE
    paths = []
    out_dir = run_dir(rid) / "bug_drafts"
    for cid, r in sorted(merged.items()):
        tri = r["triage"]
        if tri.get("category") != "PRODUCT_BUG":
            continue
        if not simple and tri.get("source") != "human":
            continue
        draft = _bug_draft_of(r)
        module = r.get("module") or "UNKNOWN"
        abbr = "".join(w[0] for w in re.findall(r"[A-Za-z]+", module)) or "GEN"
        n = len(paths) + 1          # 只给真正出了的草稿编号，否则出现 BUG-GEN-03 是孤立文件
        p = out_dir / f"BUG-{abbr}-{n:02d}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        repro = draft.get("reproduce") or [s.get("action", "") for s in r.get("steps", [])]
        if isinstance(repro, str):
            repro = [repro]
        steps = "\n".join(f"{i}. {t}" for i, t in enumerate(repro, 1) if t) or "（待补）"
        p.write_text("\n".join([
            f"### BUG-{abbr}-{n:02d} {draft.get('title') or r.get('name', '')}", "",
            "| 字段 | 值 |", "|---|---|",
            f"| Bug ID | BUG-{abbr}-{n:02d} |",
            f"| 关联用例 | {cid} |",
            f"| 严重程度 | {tri.get('severity') or draft.get('severity') or '待定（需人归类）'} |",
            f"| 分流结论 | PRODUCT_BUG（{'人工' if tri.get('source') == 'human' else 'AI'}确认："
            f"{tri.get('decided_by', '') or tri.get('source', '')} {tri.get('decided_at', '')}）|",
            f"| 环境 | {r.get('url_at_failure', '')} |",
            f"| 前置条件 | {r.get('precondition', '')} |",
            f"| 测试数据 | {r.get('test_data', '')} |",
            "| 复现步骤 | " + "<br>".join(steps.splitlines()) + " |",
            f"| 预期结果 | {draft.get('expected') or _first_fail_text(r)} |",
            f"| 实际结果 | {draft.get('actual') or r.get('error', '')} |",
            f"| 需求来源 | {draft.get('req_source') or r.get('req_source', '')} |",
            f"| 证据 | {', '.join(r.get('screenshots', [])) or '（无截图）'} |",
            f"| 裁决备注 | {tri.get('rationale', '')} |", "",
            "> 本文件由分流层生成，**未自动同步到任何缺陷系统**（只出草稿，提交由人决定）。", "",
        ]), encoding="utf-8")
        paths.append(p)
    return paths


def write_artifacts(rid: str, merged: dict, summary: dict, duplicates: int = 0,
                    malformed: int = 0, mode: str = "strict") -> dict:
    """一次写齐全部分流产物，返回文件名→路径。非致命异常在上层（`run.py triage`）被兜住。"""
    if duplicates or malformed:
        append_error_log(rid, f"records.jsonl 质量：duplicates={duplicates} malformed={malformed}")
    out = {
        "pending_review": write_pending_review(rid, merged),
        "fix_list": write_fix_list(rid, merged),
        "quarantine": write_quarantine(rid, merged),
    }
    drafts = write_bug_drafts(rid, merged)
    gate = evaluate_gate(merged, mode=mode)
    gp = run_dir(rid) / "gate.json"
    gp.write_text(
        json.dumps({"run_id": rid, "mode": mode, "gate": gate, "summary": summary,
                    "duplicates": duplicates, "malformed": malformed,
                    "generated_at": datetime.now().isoformat(timespec="seconds")},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    out["gate"] = gp
    out["bug_drafts"] = drafts
    return out
