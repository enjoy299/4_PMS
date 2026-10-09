# 测试结果分流（Result Triage）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让两条执行线（`TesterAgent` Playwright 脚本线、Qoder MCP 浏览器线）把执行事实写进同一份 `records.jsonl` 契约，由「规则层 + LLM 复判 + 人工门禁」三层判定把失败拆成 6 类，并把分类结论、有效通过率、待人工裁决清单接进 **Markdown / HTML / Excel 三格式**报告与收尾流程。

**Architecture:** `core/triage.py`（契约 + 规则 + 合并 + 摘要 + 门禁，纯函数无外部依赖）→ `agents/tester_agent.py` / `agents/qoder_bridge.py`（两条线写同一契约）→ `agents/triage_agent.py` + `core/human_confirm.py`（复判与拍板）→ `exporters/report_exporter.py`（MD 8 段摘要 + HTML 六张卡片 + Excel 14→18 列）→ `run.py triage`（编排）。全部受 `TRIAGE_ENABLED` 开关控制，`false` 时行为与改造前完全一致。

**Tech Stack:** Python 3.11、pytest 9.1（**系统 Python 已装，`.venv` 里没有**）、jsonl（标准库）、PyYAML（已有依赖）。

**设计文档（权威，勿再质疑范围）：** `docs/superpowers/specs/2026-09-14-result-triage-design.md`

**本计划范围（用户已拍板：保留完整方案 C + 2026-09-15 改为 MCP 单线）：**

- 三层判定全部落地：契约 + 规则层 + LLM 复判 + 人工门禁 + 报告三格式（MD/HTML/Excel）均加分流列。
- **本期只接入 MCP 执行线**（Task 6，并因它成为唯一入口而加固）；Playwright 脚本线降为备用，**Task 5 本期不做**（已写完，保留在计划里供二期直接执行），`run.py test` / `agents/tester_agent.py` 一行不改。
- 旧数据转换器保留；`gen_*_report.py` 入口保留但改薄封装。
- 契约含 `OK` 非失败基线、`precondition_met` 三态、`steps[].outcome` 五值（含 `noop`）。
- **凭据不再写进计划文件，`qoder_workspace/test_plan*.md` 取消 git 跟踪**（用户 2026-09-15 明确批准，含 `.gitignore` 改动，见 Task 6 Step 6.6）。
- 除上述 `test_plan*.md` 一条外，`.gitignore` 其余保持不动：`output/06_reports/triage/` 产物（含 `decisions.yaml`）仍不入库；若要放行需用户另行确认。
- 不改 `.qoder/skills/` 与 `.agents/skills/` 下任何技能文档。

**铁律② 仍成立**：「步骤 `element_not_found`/`skipped` → 状态封顶 `manual`」由 Task 3 规则 R4 + Task 4 `derived_status` 实现，作用于 `records.jsonl` 里的任何记录。MCP 执行者自己声明的步骤 `outcome` 照样被治理，**删掉 Task 5 不会丢掉假 PASS 治理**，丢掉的只是 Playwright 线自己的静默跳过问题（备用线，本期不用）。

---

## 前置事实（已核对，勿再假设）

| 事实 | 出处 |
|---|---|
| 线 1 步骤内「未找到元素」只 `logger.warning` + `continue`，**不记录也不降级**，是假 PASS 根源 | `agents/tester_agent.py:239-242` |
| `_execute_action` 返回值是中文串：`未找到：X` / `已跳过：…` / `已查看：…` / `已执行（通用）：…`，**无结构化 outcome** | `agents/tester_agent.py:342-346, 399, 414, 450` |
| 用例结果 dict 字段：`case_id,name,status,duration_sec,precondition,steps,expected_results,test_data,actual,screenshot,log,req_source,test_point`，断言为 `{text,passed,verifiable,reason}` | `agents/tester_agent.py:204-217, 761-767` |
| `_check_assertion` 返回 `(bool, bool, str)`，不可验证时 reason 含「无法自动验证：缺少可定位目标」 | `agents/tester_agent.py:740-768` |
| `_assert_text_in_scope` 未命中容器时返回 `(False, False, "未定位到结果容器")` | `agents/tester_agent.py:849-862` |
| `_env_preflight()` 在 4 处调用点失败即 `return None`，**不产出任何记录** | `agents/tester_agent.py:70-86, 122, 921, 1274` |
| 三处收尾各自调 `self.reporter.build_and_save(...)` | `agents/tester_agent.py:172-175, 1030-1033, 1324-1327` |
| `TRIAGE_DIR` 尚不存在；目录自动创建清单在 `core/config.py:100-105` | `core/config.py:53-55, 100-105` |
| 日志/截图命名由 `core/hooks.py` 决定：`logs/run_{ts}_{module}_{case_id}.log`、`output/06_reports/screenshots/{ts}/{STATUS}_{case_id}.png` | `core/hooks.py:29-32, 44-53` |
| 线 2 结果记录要求 = 一张 Markdown 表格 `TC-xxx \| PASS/FAIL`，事后手抄 | `agents/qoder_bridge.py:148-159` |
| **计划文件写明文凭据 `**登录账号**: zgn / <TEST_PASSWORD>`，且 `qoder_workspace/` 整体被 git 跟踪** | `agents/qoder_bridge.py:91, 206`；`git ls-files qoder_workspace` 列出 6 个 `test_plan*.md` |
| MCP 线无 run_id、无截图命名约定、无「计划内用例全集」清单，故无法校验未执行缺口 | `agents/qoder_bridge.py:86-103, 148-159` 实测无相关内容 |
| 旧产物两种形态：已执行用例带 `steps_executed[].result`/`expected_results[].verdict`/`assertions[].{expected,actual,passed,note}`/`bugs[]`；11 条未执行用例只在 `pending_cases[].blocker` | `qoder_workspace/test_result_P0_km_20260907.json` |
| 需求条目表格行格式 `\| CAT-01 \| 描述 \| 来源 \|` | `output/02_split_requirements/知识管理/分类管理.md` |
| `_safe_ask(prompt, choices, default)` 在 EOF 时返回 default（CI 安全），人工门禁沿用此风格 | `core/human_confirm.py:18-27` |
| `pytest 9.1.1` 只在系统 Python，`.venv` 无 pytest；`import core.config` 需仓库根在 `sys.path`（新建根 `conftest.py` 解决） | 环境实测 |

**环境注意事项：** Windows PowerShell **禁用 `&&`**，多命令用 `;`。每个任务结束 commit，且只 `git add` 本任务改动的路径（工作区有大量无关未提交改动，禁止 `git add -A`）。

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `core/config.py` | 修改 | 3 个分流配置项 + 建目录 |
| `conftest.py`、`tests/__init__.py` | 新建 | 让测试能 import `core.*`（项系统无测试目录，本计划首次引入） |
| `core/triage.py` | 新建 | 契约读写、规则层、三层合并、摘要、门禁、需求片段抽取、`to_result_rows` 反向映射 |
| `agents/tester_agent.py` | **本期不改**（Task 5 延后） | 二期再做：步骤 outcome 结构化、假 PASS 治理、append record、预检失败写 ENV_BLOCK |
| `agents/qoder_bridge.py` | 修改 | **本期唯一执行入口**：计划内嵌结果契约、固定 run_id、写 `plan_cases.json`、截图命名约定、凭据脱敏 |
| `scripts/_convert_legacy_result.py` | 新建 | 旧 `test_result_*.json` → `records.jsonl` |
| `agents/triage_agent.py`、`agents/triage_prompt.md` | 新建 | LLM 复判输入包与输出解析（复用 `core/brain.py` 机制） |
| `core/human_confirm.py` | 修改 | `confirm_triage_decisions()` 人工门禁 |
| `exporters/report_exporter.py` | 修改 | `build_from_records()` 编排 + MD 8 段摘要 + HTML 模板重构（6 张卡片）+ Excel 14→18 列 |
| `scripts/gen_p0_report.py`、`gen_iap_report.py`、`gen_p2_report.py` | 修改 | 入口保留，内部改为读 `records.jsonl` 的薄封装 |
| `run.py` | 修改 | `triage` 命令 + help + pipeline 提示 |
| `tests/test_smoke.py`、`tests/test_triage_contract.py`、`tests/test_triage_rules.py`、`tests/test_triage_merge.py`、`tests/test_convert_legacy.py`、`tests/test_triage_agent_input.py`、`tests/test_human_gate.py`、`tests/test_report_triage.py`、`tests/test_triage_orchestration.py`、`tests/test_report_entry.py` | 新建 | 配置与目录骨架 / 契约读写与降级 / 规则表+铁律负向 / 合并与摘要与门禁 / 旧数据转换+契约回归 / 需求片段抽取 / CI 不阻塞 / 分流版 MD / 分流版 HTML+Excel / `run.py triage` 编排 / `gen_*_report.py` 不得硬编码结果 |
| `.gitignore` | 修改（仅一条） | 取消 `qoder_workspace/test_plan*.md` 跟踪（用户已批准，Task 6 Step 6.6） |
| `README.md` | 修改 | 06 阶段分流说明 |

任务顺序即依赖顺序，每个任务结束时仓库处于可编译、旧行为不变（`TRIAGE_ENABLED=false`）状态。

---

## Task 1: 配置项与 pytest 骨架

**Files:**
- Modify: `core/config.py`（在 `REPORTS_DIR` 后、目录创建清单处）
- Create: `conftest.py`、`tests/__init__.py`
- Test: `tests/test_smoke.py`

- [ ] **Step 1.1: 写失败测试**

Create `tests/test_smoke.py`:

```python
"""骨架冒烟：验证仓库根可被 import、分流配置可读。"""
from core import config


def test_triage_config_defaults():
    assert config.TRIAGE_ENABLED is False
    assert config.TRIAGE_DIR.name == "triage"
    assert 0.0 < config.TRIAGE_CONF_THRESHOLD <= 1.0
    assert config.TRIAGE_DIR.exists()
```

Create `tests/__init__.py`:

```python
"""分流相关测试包。"""
```

- [ ] **Step 1.2: 运行确认失败**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL，`AttributeError: module 'core.config' has no attribute 'TRIAGE_ENABLED'`

- [ ] **Step 1.3: 加配置项**

Create `conftest.py`（仓库根）:

```python
"""让 pytest 能从仓库根 import core / exporters / agents。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

Modify `core/config.py`，在 `SCREENSHOTS_DIR = REPORTS_DIR / "screenshots"` 之后插入：

```python
# --- 结果分流（Result Triage）配置 ---
TRIAGE_ENABLED = os.getenv("TRIAGE_ENABLED", "false").lower() in ("1", "true", "yes", "on")
TRIAGE_DIR = REPORTS_DIR / "triage"                    # 分流产物根目录
TRIAGE_CONF_THRESHOLD = float(os.getenv("TRIAGE_CONF_THRESHOLD", "0.7"))
```

然后把 `core/config.py:100-104` 的目录自动创建清单整段替换（新增 `TRIAGE_DIR`，其余变量名与顺序保持原样）：

```python
for d in [SPEC_DIR, PROTOTYPES_DIR, EXPLORE_DIR, BUSINESS_DIR, SPLIT_REQUIREMENTS_DIR, TESTPOINTS_DIR, CASES_DIR,
          DESIGN_WORKSPACE_DIR, REVIEW_DIR, FINAL_CASES_DIR,
          MD_REPORTS_DIR, HTML_REPORTS_DIR, EXCEL_REPORTS_DIR,
          SCREENSHOTS_DIR, TRIAGE_DIR, LOGS_DIR,
          AI_WORKSPACE_DIR, TEST_SCRIPTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)
```

> 注意：清单里的变量名必须是 `SPEC_DIR / EXPLORE_DIR / SPLIT_REQUIREMENTS_DIR` 等**本文件实际定义的名字**（`OUTPUT_SPLIT_DIR`、`QODER_WORKSPACE_DIR` 之类不存在，抄上去会 `NameError`）。

- [ ] **Step 1.4: 运行确认通过**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: PASS，`1 passed`

- [ ] **Step 1.5: 确认旧行为未受影响**

Run: `python run.py help`
Expected: 正常打印命令表，无新增异常（`run.py` 无 `status` 命令，别编）

Run: `python -c "from core.config import TRIAGE_DIR; print(TRIAGE_DIR.exists())"`
Expected: `True`（目录已由 import 副作用创建）

- [ ] **Step 1.6: Commit**

```powershell
git add core/config.py conftest.py tests
git commit -m "feat(config): 新增结果分流配置项与 pytest 骨架"
```

---

## Task 2: 契约读写 `core/triage.py`

单一职责：只负责「执行事实 → 合法 record → jsonl 读写 → 三层结论合并 → 摘要与门禁判定」，不 import playwright、不发网络请求、不读配置以外的全局状态。

**Files:**
- Create: `core/triage.py`
- Test: `tests/test_triage_contract.py`（契约读写与枚举校验）

- [x] **Step 2.1: 写失败测试**

Create `tests/test_triage_contract.py`:

```python
"""契约读写：字段完整性、枚举合法性、损坏行降级、重复 case_id 去重。"""
import copy
from pathlib import Path

import pytest

from core import config
from core.triage import (
    FINAL_CATEGORIES, STEP_OUTCOMES, new_record, validate_record,
    append_records, load_records, record_from_result, make_run_id,
)


@pytest.fixture
def run_dir(tmp_path, monkeypatch):
    d = tmp_path / "triage" / "知识管理_20260914_173000"
    monkeypatch.setattr(config, "TRIAGE_DIR", d.parent)
    return d.name


def test_new_record_is_complete_and_valid(run_dir):
    rec = new_record(run_id=run_dir, case_id="TC-CAT-001", module="知识管理")
    assert validate_record(rec) == []
    assert rec["triage"]["category"] == ""            # 未经分流 = 空串
    assert rec["precondition_met"] is None            # 三态默认为「未知」


def test_enum_guards_reject_bad_values(run_dir):
    rec = new_record(run_id=run_dir, case_id="TC-001", module="知识管理")
    assert "noop" in STEP_OUTCOMES and "OK" in FINAL_CATEGORIES
    bad = copy.deepcopy(rec)
    bad["steps"] = [{"order": 1, "action": "a", "outcome": "已跳过", "detail": ""}]
    bad["precondition_met"] = "yes"
    bad["assertions"] = [{"text": "t", "verdict": "成功", "reason": "", "evidence_refs": []}]
    bad["triage"]["category"] = "FLAKY"
    errs = validate_record(bad)
    assert "step.outcome 非法:已跳过" in errs
    assert "precondition_met 非三态:yes" in errs
    assert "assertion.verdict 非法:成功" in errs
    assert "category 非法:FLAKY" in errs


def test_record_from_result_maps_assertions_and_precondition(run_dir):
    result = {
        "case_id": "TC-CAT-001", "name": "新建一级分类", "module": "知识管理",
        "status": "manual", "duration_sec": 8.5, "precondition": "已登录",
        "precondition_met": True, "test_data": "分类名：P0测试分类",
        "actual": "未找到：新建分类", "screenshot": ["a.png"], "log": "b.log",
        "steps": [{"order": 1, "action": "点击\"新建分类\"", "outcome": "element_not_found",
                   "detail": "未找到：新建分类"}],
        "assertions": [{"text": "弹窗关闭", "passed": False, "verifiable": False,
                        "reason": "无法自动验证：缺少可定位目标"}],
    }
    rec = record_from_result(result, run_id=run_dir, executor="playwright_script")
    assert validate_record(rec) == []
    assert rec["assertions"][0]["verdict"] == "unverifiable"
    assert rec["precondition_met"] is True


def test_append_and_load_dedupes_by_case_id(run_dir):
    a1 = new_record(run_id=run_dir, case_id="TC-001", module="知识管理", status="fail")
    a2 = new_record(run_id=run_dir, case_id="TC-001", module="知识管理", status="pass")
    append_records([a1, a2, new_record(run_id=run_dir, case_id="TC-002", module="知识管理")], run_dir)
    recs, dup, malformed = load_records(run_dir)
    assert dup == 1 and malformed == 0
    assert len(recs) == 2
    assert {r["case_id"]: r["status"] for r in recs}["TC-001"] == "pass"   # 取最后一条


def test_append_records_downgrades_invalid_and_logs(run_dir, tmp_path):
    bad = new_record(run_id=run_dir, case_id="TC-BAD", module="知识管理")
    bad["status"] = "成功"
    append_records([bad], run_dir)
    recs, _, _ = load_records(run_dir)
    assert recs[0]["triage"]["category"] == "NEEDS_HUMAN"
    assert "status 非法" in recs[0]["triage"]["rationale"]
    assert (tmp_path / "triage" / run_dir / "triage_errors.log").exists()


def test_make_run_id_strips_illegal_chars():
    assert make_run_id("7、知识管理", "20260914_173000") == "7知识管理_20260914_173000"
```

- [x] **Step 2.2: 运行确认失败**

Run: `python -m pytest tests/test_triage_contract.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'core.triage'`

- [x] **Step 2.3: 写契约层实现**

Create `core/triage.py`（本任务只写契约部分，Task 3/4 追加规则与合并）：

```python
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
```

> 损坏行（JSON 解析失败）只计数不中断；`duplicates` 与 `malformed` 均需写入该 run 摘要与 `triage_errors.log`（Task 10 的 `write_artifacts` 负责）。

- [x] **Step 2.4: 运行确认契约基础通过**

Run: `python -m pytest tests/test_triage_contract.py -v`
Expected: PASS，`6 passed`

> 2026-09-15 实施前修正：① Step 2.1 测试文件补 `from pathlib import Path`（Step 2.5 的断言用到，原计划漏导，会 `NameError`）；② `make_run_id` 的清洗正则补上中文顿号等（否则 `test_make_run_id_strips_illegal_chars` 断言的 `7、知识管理 -> 7知识管理` 不成立）。

- [x] **Step 2.5: 计划用例清单读写与未执行缺口（MCP 唯一入口的前置校验）**

> 2026-09-15 范围调整：MCP 线是本期唯一结果来源，漏填会静默变成「没测过」。契约层负责 `plan_cases.json` 的读写与缺口比对：Task 6 写入，Task 13 `--validate` 消费。

Append to `tests/test_triage_contract.py`:

```python
def test_plan_cases_roundtrip_and_gap(run_dir):
    from core.triage import write_plan_cases, load_plan_cases, diff_plan_vs_records
    write_plan_cases(run_dir, case_ids=["TC-001", "TC-002", "TC-003"],
                     module="知识管理", source_file="output/03_design/test_cases/知识管理/x.md")
    plan = load_plan_cases(run_dir)
    assert plan["case_ids"] == ["TC-001", "TC-002", "TC-003"]
    assert plan["run_id"] == run_dir

    recs = [{"case_id": "TC-001"}, {"case_id": "TC-004"}]
    gap = diff_plan_vs_records(plan, recs)
    assert gap["planned"] == 3 and gap["recorded"] == 1
    assert gap["missing"] == ["TC-002", "TC-003"]     # 计划内但没记录 = 未执行
    assert gap["extra"] == ["TC-004"]                 # 记了但不在计划内 = case_id 写错
    assert diff_plan_vs_records(None, recs)["missing"] == []   # 无 plan_cases 时降级为不报缺口


def test_load_plan_cases_returns_none_when_absent_or_broken(run_dir):
    from core.triage import load_plan_cases
    assert load_plan_cases(run_dir) is None
    p = Path(config.TRIAGE_DIR) / run_dir / "plan_cases.json"
    p.parent.mkdir(parents=True, exist_ok=True)   # 读接口不建目录，写坏样本前自己先建
    p.write_text("{broken", encoding="utf-8")
    assert load_plan_cases(run_dir) is None
```

Run: `python -m pytest tests/test_triage_contract.py -v`
Expected: FAIL，`ImportError: cannot import name 'write_plan_cases'`

Append to `core/triage.py`:

```python
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
```

Run: `python -m pytest tests/test_triage_contract.py -v`
Expected: PASS，`8 passed`

> 2026-09-15 实施时修正：本步测试原写法会 `FileNotFoundError`——`load_plan_cases` 正确地不去创建目录，导致写“损坏样本”时父目录不存在，已改为先 `mkdir(parents=True)`（实现层无需改动）。本任务实测结果：契约 8 项 + Task 1 冒烟 1 项 = `9 passed`。

- [x] **Step 2.6: Commit**

```powershell
git add core/triage.py tests/test_triage_contract.py
git commit -m "feat(triage): 新增统一执行结果契约与 jsonl 读写"
```

---

## Task 3: 规则层（R1-R8，只吃可观测事实）

**Files:**
- Modify: `core/triage.py`（追加规则表与 `run_rule_layer`）
- Test: `tests/test_triage_rules.py`（新建，含铁律负向断言）

- [x] **Step 3.1: 追加失败测试**

Append to `tests/test_triage_rules.py`:

```python
"""规则层逐条覆盖 R0-R8。核心是铁律的负向断言：规则层永不产出 PRODUCT_BUG。"""
import copy

from core.triage import run_rule_layer


REC = {
    "run_id": "x", "executor": "playwright_script", "case_id": "TC-001", "name": "n",
    "module": "知识管理", "submodule": "", "priority": "P0", "case_type": "正向",
    "test_point_ref": "", "req_source": "CAT-01",
    "started_at": "2026-09-14T17:00:00", "duration_sec": 1.0, "status": "pass",
    "precondition": "", "precondition_met": None, "test_data": "", "error": "",
    "steps": [], "assertions": [],
    "url_at_failure": "", "screenshots": [], "log_path": "", "console_errors": [],
    "triage": {"category": "", "source": "rule", "confidence": 0.0, "rationale": "",
               "suggested_action": "", "unblock_hint": "", "decided_by": "",
               "decided_at": "", "overridden": False},
    "bug_draft": None, "retry_count": 0, "needs_reconfirm": False,
}
STATUS_ALL = ("pass", "fail", "error", "manual", "blocked", "skipped")


def _rec(**kw):
    r = copy.deepcopy(REC)
    pm = kw.pop("precondition_met", None)
    r.update(kw)
    if pm is not None:
        r["precondition_met"] = pm
    return r


def test_r0_clean_pass_is_ok_not_triaged():
    r = _rec(status="pass",
             steps=[{"order": 1, "action": "点树节点", "outcome": "noop", "detail": "已查看："}],
             assertions=[{"text": "t", "verdict": "pass", "reason": "", "evidence_refs": []}])
    assert run_rule_layer(r)["category"] == "OK"


def test_r1_env_preflight_failed():
    assert run_rule_layer(_rec(status="error"), env_preflight_failed=True)["category"] == "ENV_BLOCK"


def test_r2_error_keywords():
    got = run_rule_layer(_rec(status="error", error="net::ERR_CONNECTION_REFUSED"))
    assert got["category"] == "ENV_BLOCK" and got["confidence"] == 0.9


def test_r3_login_redirect_is_env_block():
    assert run_rule_layer(_rec(status="fail", url_at_failure="http://x/login"))["category"] == "ENV_BLOCK"


def test_r3_excludes_login_module():
    got = run_rule_layer(_rec(status="fail", module="登录", url_at_failure="http://x/login"))
    assert got["category"] != "ENV_BLOCK"


def test_r4_step_not_executed_is_exec_incomplete():
    r = _rec(status="fail", steps=[{"order": 1, "action": "点新建", "outcome": "element_not_found", "detail": ""}])
    assert run_rule_layer(r)["category"] == "EXEC_INCOMPLETE"


def test_r4_skipped_action_also_counts():
    r = _rec(status="fail", steps=[{"order": 2, "action": "点编辑", "outcome": "skipped", "detail": "已执行（通用）"}],
             assertions=[{"text": "t", "verdict": "fail", "reason": "", "evidence_refs": []}])
    assert run_rule_layer(r)["category"] == "EXEC_INCOMPLETE"


def test_r5_all_unverifiable_is_case_defect():
    r = _rec(status="fail", assertions=[
        {"text": "a", "verdict": "unverifiable", "reason": "无法自动验证：缺少可定位目标", "evidence_refs": []}])
    assert run_rule_layer(r)["category"] == "CASE_DEFECT"


def test_r6_precondition_met_false_is_data_precond():
    r = _rec(status="fail", precondition_met=False,
             assertions=[{"text": "a", "verdict": "fail", "reason": "不符", "evidence_refs": []}])
    assert run_rule_layer(r)["category"] == "DATA_PRECOND"


def test_r6_text_keyword_fallback():
    r = _rec(status="manual", error="无法提供：缺少测试数据")
    got = run_rule_layer(r)
    assert got["category"] == "DATA_PRECOND" and got["unblock_hint"]


def test_r7_genuine_failure_goes_to_llm_as_needs_human():
    r = _rec(status="fail", steps=[{"order": 1, "action": "点新建", "outcome": "ok", "detail": ""}],
             assertions=[{"text": "弹窗关闭", "verdict": "fail", "reason": "仍存在", "evidence_refs": []}])
    got = run_rule_layer(r)
    assert got["category"] == "NEEDS_HUMAN" and got["confidence"] == 0.0


def test_r7_allows_unknown_step_outcome():
    """执行者未声明步骤细节（unknown）不应掉进「执行问题」，仍送 LLM。"""
    r = _rec(status="fail", steps=[{"order": 1, "action": "导航", "outcome": "unknown", "detail": ""}],
             assertions=[{"text": "弹窗关闭", "verdict": "fail", "reason": "仍存在", "evidence_refs": []}])
    assert run_rule_layer(r)["category"] == "NEEDS_HUMAN"


def test_r8_mixed_state_is_needs_human():
    r = _rec(status="pass", assertions=[{"text": "a", "verdict": "unverifiable", "reason": "r", "evidence_refs": []}])
    assert run_rule_layer(r)["category"] == "NEEDS_HUMAN"


def test_rule_layer_never_produces_product_bug():
    """铁律负向断言：穷举输入空间，规则层任何分支都不得产出 PRODUCT_BUG。

    `url_at_failure` 必须参与遍历：否则全部组合都被 R3（/login）先命中，
    其余分支一个也测不到，本测试形同虚设。
    """
    for st in STATUS_ALL:
        for out in ("ok", "element_not_found", "skipped", "noop", "unknown"):
            for verd in ("pass", "fail", "unverifiable"):
                for pm in (True, False, None):
                    for url in ("", "http://x/login"):
                        r = _rec(status=st, precondition_met=pm, error="缺少测试数据",
                                 url_at_failure=url,
                                 steps=[{"order": 1, "action": "a", "outcome": out, "detail": ""}],
                                 assertions=[{"text": "t", "verdict": verd,
                                              "reason": "无法自动验证：缺少可定位目标", "evidence_refs": []}])
                        assert run_rule_layer(r)["category"] != "PRODUCT_BUG", \
                            f"铁律被违反 st={st} out={out} v={verd} pm={pm} url={url}"
```

- [x] **Step 3.2: 运行确认失败**

Run: `python -m pytest tests/test_triage_rules.py -v`
Expected: FAIL，`ImportError: cannot import name 'run_rule_layer'`

> 实测已确认：补实现前确实是 collection 阶段 `ImportError: cannot import name 'run_rule_layer'`。

- [x] **Step 3.3: 实现规则层**

Append to `core/triage.py`:

```python
# ── 规则层：按序先命中先定 ─────────────────────────────────────────
# 铁律：本函数**永不产出 PRODUCT_BUG**。负向单测 test_rule_layer_never_produces_product_bug 守此。
# 真实缺陷定性必须经 LLM 提案 + 人工门禁确认。
_ENV_ERR_KEYWORDS = ("ECONNREFUSED", "net::ERR", "404", "500", "Timeout", "timed out", "连接被拒绝")
_MISSING_PRECOND_KEYWORDS = ("未准备", "无法提供", "缺少测试数据", "需要先造", "未上传", "依赖TC-", "依赖TC_", "无法验证")
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
    for k in keywords:
        if k in text:
            return k
    return ""


def _is_login_case(rec: dict) -> bool:
    module = rec.get("module", "") or ""
    name = rec.get("name", "") or ""
    return "登录" in module or "登录" in name or rec.get("case_id", "").upper().startswith("TC-AUTH")


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
                       rec.get("unblock_hint") or "补齐该用例声明的前置数据/账号/文件")
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
        # 走到了这里说明 R0 未命中（无断言明细 / step 为 unknown）：属混合态，不得自行算作通过
        return out("NEEDS_HUMAN", 0.0, "R8：status=pass 但缺可自证的事实（无断言或步骤未声明）", "人工裁决")
    return out("NEEDS_HUMAN", 0.0, "R8：混合态，规则层无法判定", "人工裁决")


def apply_rule_layer(records: list, env_preflight_failed: bool = False) -> list:
    for rec in records:
        rec["triage"].update(run_rule_layer(rec, env_preflight_failed=env_preflight_failed))
        rec["triage"]["source"] = "rule"
    return records
```

- [x] **Step 3.4: 运行确认通过**

Run: `python -m pytest tests/test_triage_rules.py -v`
Expected: PASS，`14 passed`

> 2026-09-15 实施时修正两处：
> ① **R5 加 `st != "pass"` 守卫**。原写法下 `test_r8_mixed_state_is_needs_human`（`status=pass` + 断言全 `unverifiable`）会先被 R5 捕走返回 `CASE_DEFECT`，与期望的 `NEEDS_HUMAN` 冲突。语义上这也是对的：报 pass 但断言全不可验证是典型「幻觉通过」，不能当成「用例写坏了」轻轻放过，必须落 R8 送人工。
> ② **铁律负向测试让 `url_at_failure` 参与遍历**。原写法循环里 url 恒为 `http://x/login`，270 个组合全被 R3 先命中，其余分支一个也没测到。修正后实测 540 组合分布为 `ENV_BLOCK 264 / DATA_PRECOND 126 / EXEC_INCOMPLETE 72 / CASE_DEFECT 27 / NEEDS_HUMAN 39 / OK 12`，`PRODUCT_BUG` **0 次**（铁律守住）。实测：规则 14 项 + 前序 9 项 = `23 passed`。

- [x] **Step 3.5: Commit**

```powershell
git add core/triage.py tests/test_triage_rules.py
git commit -m "feat(triage): 规则层 R1-R8，铁律由负向单测守住"
```

---

## Task 4: 三层合并、8 段摘要、收尾门禁、quarantine

> 2026-09-15 实施时修正四处（前三处是计划里测试自身写错，第四处是实现的真缺陷）：
> ① **`test_human_overrides_llm_and_rule` 缺 `confirmed_by_human: True`**。按铁律①，合并层会拒收未经人确认的 `PRODUCT_BUG`，原断言永不成立。补该键（它本就是 `decisions.yaml` 的约定字段）。
> ② **低置信回落测试原断言 `source == "llm"`**。LLM 结论既已被丢弃，归属仍是规则层；写 `llm` 等于谎报是谁下的结论。改为 `source == "rule"`。
> ③ **`test_bucket_sum_equals_total` 把派生字段算进桶和**（「通过率 / 有效通过率 / 移出分母」一起加 ≈ 87.3 ≠ 3）。用 `NON_BUCKET_KEYS` 排除后，测的才是「桶和 == 总用例」这条自检不变量本身。
> ④ **`decisions.yaml` 读写格式互不兼容（实现的真 bug）**：`save_decisions` 装了 PyYAML 写映射式、没装写列表式，而 `load_decisions` 经 PyYAML 读到列表会原样返回 list（`cid in human` 恒为假），`_parse_decisions_fallback` 又只认列表式 —— 任一条路都会把**人工裁决静默丢成空**，而这一层是唯一能定性 `PRODUCT_BUG` 的。修法：`_normalize_decisions()` 统一两种形状；降级解析同时认映射式、并把 `confirmed_by_human` 等键转真布尔（否则 `"true"` 字符串永远判不出）；文件非空却解析出 0 条 → 记 `triage_errors.log`；YAML 写坏只留痕不崩；header 里去掉多余的 `decisions:` 以避免同文档重复键。
>
> 测试数由计划的 12 增至 **17**：补 `test_unconfirmed_human_product_bug_is_refused`（CI 预写的 `PRODUCT_BUG` 未经人确认必须与 LLM 同权降级）+ 4 条 `decisions.yaml` 读写（含无 PyYAML 的真降级往返）。

**Files:**
- Modify: `core/triage.py`（追加合并与摘要）
- Test: `tests/test_triage_merge.py`

- [x] **Step 4.1: 写失败测试**

Create `tests/test_triage_merge.py`:

```python
"""三层结论合并、8 段摘要、有效通过率、收尾门禁。"""
import copy

from core.triage import (
    compute_summary, derived_status, evaluate_gate, merge_decisions, new_record,
)

BASE = new_record(run_id="r1", case_id="TC-001", module="知识管理")


def _rec(cid, **kw):
    r = copy.deepcopy(BASE)
    r["case_id"] = cid
    r["status"] = kw.get("status", "fail")
    r["triage"] = {**r["triage"], **kw.get("triage", {})}
    return r


def test_human_overrides_llm_and_rule():
    recs = [_rec("TC-001", triage={"category": "NEEDS_HUMAN", "source": "rule"})]
    human = {"TC-001": {"final_category": "PRODUCT_BUG", "decided_by": "tester",
                        "severity": "S2", "note": "确认缺陷"}}
    merged = merge_decisions(recs, {}, human)
    assert merged["TC-001"]["triage"]["category"] == "PRODUCT_BUG"
    assert merged["TC-001"]["triage"]["source"] == "human"
    assert merged["TC-001"]["triage"]["overridden"] is True


def test_llm_overrides_rule():
    recs = [_rec("TC-002", triage={"category": "NEEDS_HUMAN", "source": "rule", "confidence": 0.0})]
    llm = {"TC-002": {"verdict": "CASE_DEFECT", "confidence": 0.85, "rationale": "断言与需求无关",
                      "suggested_fix": "重写断言"}}
    t = merge_decisions(recs, llm, {})["TC-002"]["triage"]
    assert (t["category"], t["source"], t["confidence"]) == ("CASE_DEFECT", "llm", 0.85)


def test_low_confidence_llm_falls_back_to_needs_human():
    recs = [_rec("TC-003", triage={"category": "NEEDS_HUMAN", "source": "rule"})]
    llm = {"TC-003": {"verdict": "DATA_PRECOND", "confidence": 0.4, "unblock_hint": ""}}
    t = merge_decisions(recs, llm, {})["TC-003"]["triage"]
    assert t["category"] == "NEEDS_HUMAN" and t["source"] == "llm"


def test_blocked_without_hint_becomes_needs_human():
    recs = [_rec("TC-004", triage={"category": "ENV_BLOCK", "source": "rule", "confidence": 0.9,
                                   "unblock_hint": ""})]
    t = merge_decisions(recs, {}, {})["TC-004"]["triage"]
    assert t["category"] == "NEEDS_HUMAN"


def test_non_human_product_bug_is_refused():
    """铁律：非人工来源的 PRODUCT_BUG 在合并层拒收，回落 NEEDS_HUMAN。"""
    recs = [_rec("TC-005", triage={"category": "PRODUCT_BUG", "source": "llm", "confidence": 0.95})]
    t = merge_decisions(recs, {}, {})["TC-005"]["triage"]
    assert t["category"] == "NEEDS_HUMAN"
    assert "铁律" in t["rationale"]


def test_ok_case_not_counted_as_pending():
    recs = [_rec("TC-006", status="pass", triage={"category": "OK", "source": "rule", "confidence": 1.0})]
    s = compute_summary(merge_decisions(recs, {}, {}))
    assert s["通过"] == 1 and s["待人工裁决"] == 0 and s["其他异常"] == 0


def test_bucket_sum_equals_total():
    recs = [_rec("TC-010", triage={"category": "ENV_BLOCK", "source": "rule", "confidence": 0.9,
                                   "unblock_hint": "起服务"}),
            _rec("TC-011", status="pass", triage={"category": "OK", "source": "rule", "confidence": 1.0}),
            _rec("TC-012", triage={"category": "NEEDS_HUMAN", "source": "rule"})]
    s = compute_summary(merge_decisions(recs, {}, {}))
    assert s["总用例"] == sum(v for k, v in s.items() if k != "总用例") == 3


def test_untitled_record_lands_in_other_bucket_not_silently_dropped():
    """未过规则层的记录（category 空）必须进「其他异常」，保证桶和==总用例这条自检不变量不被抹平。"""
    recs = [_rec("TC-011B", status="pass", triage={"category": "", "source": "none"})]
    s = compute_summary(merge_decisions(recs, {}, {}))
    assert s["其他异常"] == 1 and s["通过"] == 0


def test_effective_pass_rate_excludes_env_and_data():
    recs = [_rec("TC-013", status="pass", triage={"category": "OK", "source": "rule", "confidence": 1.0}),
            _rec("TC-014", triage={"category": "ENV_BLOCK", "source": "rule", "confidence": 0.9,
                                   "unblock_hint": "起服务"}),
            _rec("TC-015", triage={"category": "DATA_PRECOND", "source": "rule", "confidence": 0.9,
                                   "unblock_hint": "造数据"}),
            _rec("TC-016", triage={"category": "EXEC_INCOMPLETE", "source": "rule", "confidence": 0.9})]
    s = compute_summary(merge_decisions(recs, {}, {}))
    assert s["通过率"] == 25.0
    assert s["有效通过率"] == round(1 / 2 * 100, 1)      # 分母 4-1-1=2
    assert s["移出分母"] == 2


def test_derived_status_maps_blocked_and_manual():
    recs = [_rec("TC-017", triage={"category": "ENV_BLOCK", "source": "rule", "confidence": 0.9,
                                   "unblock_hint": "起服务"}),
            _rec("TC-018", status="fail", triage={"category": "CASE_DEFECT", "source": "rule",
                                                  "confidence": 0.9})]
    merged = merge_decisions(recs, {}, {})
    assert derived_status(merged["TC-017"]) == "blocked"
    assert derived_status(merged["TC-018"]) == "manual"


def test_strict_gate_blocks_on_needs_human_and_release_ready():
    recs = [_rec("TC-019", triage={"category": "NEEDS_HUMAN", "source": "rule"}),
            _rec("TC-020", triage={"category": "ENV_BLOCK", "source": "rule", "confidence": 0.9,
                                   "unblock_hint": "起服务"})]
    merged = merge_decisions(recs, {}, {})
    human = evaluate_gate(merged, mode="strict")
    assert human["verdict"] == "reject" and human["pending"] == 1
    clean = evaluate_gate({"TC-020": merged["TC-020"]}, mode="strict")
    assert clean["verdict"] == "allow"


def test_ci_gate_is_na_and_never_blocks():
    recs = [_rec("TC-021", triage={"category": "NEEDS_HUMAN", "source": "rule"})]
    g = evaluate_gate(merge_decisions(recs, {}, {}), mode="report_only")
    assert g["verdict"] == "na" and g["blocks_exit_code"] is False
```

- [x] **Step 4.2: 运行确认失败**

Run: `python -m pytest tests/test_triage_merge.py -v`
Expected: FAIL，`ImportError: cannot import name 'merge_decisions'`（实测同样报错）

- [x] **Step 4.3: 实现合并与摘要**

Append to `core/triage.py`:

```python
# ── 结论文件读写 ───────────────────────────────────────────────────
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


# ── 三层合并 ──────────────────────────────────────────────────────
_STATUS_BY_CATEGORY = {"CASE_DEFECT": "manual", "EXEC_INCOMPLETE": "manual"}
_BLOCKED_CATEGORIES = ("ENV_BLOCK", "DATA_PRECOND")


def merge_decisions(records: list, llm: dict, human: dict,
                    conf_threshold: float = None) -> dict:
    """人 > LLM > 规则，返回 {case_id: record}。两条铁律在此集中强制：
    ① 非人工来源的 PRODUCT_BUG 一律拒收并回落 NEEDS_HUMAN；
    ② ENV_BLOCK/DATA_PRECOND 缺 `unblock_hint` 视为未说明阻塞原因，降级 NEEDS_HUMAN。
    """
    if conf_threshold is None:
        from core.config import TRIAGE_CONF_THRESHOLD
        conf_threshold = TRIAGE_CONF_THRESHOLD
    merged = {}
    for rec in records:
        cid = rec.get("case_id", "?")
        tri = dict(rec["triage"])
        low = []
        if cid in llm:
            v = llm[cid]
            conf, cat = float(v.get("confidence", 0) or 0), v.get("verdict", "")
            if cat == _LLM_PROPOSAL:
                # 提案不是结论：仍回落 NEEDS_HUMAN 排队给人工门禁，但要把 LLM 的理由与 Bug 草稿
                # 留在记录上，否则人只能从断言原文重新推一遍（复判等于白做）。
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
        if tri.get("category") == "PRODUCT_BUG" and tri.get("source") != "human":
            low.append(f"{tri.get('source')} 层拒绝定性 PRODUCT_BUG（分流铁律）")
            tri.update({"category": "NEEDS_HUMAN", "confidence": 0.0})
        if tri.get("category") in _BLOCKED_CATEGORIES and not (tri.get("unblock_hint") or "").strip():
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
    if cat in _BLOCKED_CATEGORIES:
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
               if r["triage"].get("category") in _BLOCKED_CATEGORIES
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
```

> 注意：`_is_login_case` 已在 Task 3 定义，此处不得重复定义。

- [x] **Step 4.4: 运行确认通过**

Run: `python -m pytest tests/test_triage_merge.py tests/test_triage_rules.py -v`
Expected: PASS，`17 passed`（merge，原计划 12）+ `14 passed`（rules）；全量 `python -m pytest tests -q` → `41 passed`

- [x] **Step 4.5: Commit**

```powershell
git add core/triage.py tests/test_triage_merge.py
git commit -m "feat(triage): 三层结论合并、8 段摘要、收尾门禁与 quarantine"
```

---

## Task 5:（**本期不做 · 二期**）线 1 Playwright 接入（假 PASS 治理 + 契约落盘）

> **2026-09-15 用户决定：本期只把 MCP 线跑熟，Playwright 线降为备用，本任务整体延后。**
> 实施本计划时**直接跳过 Task 5**，不要改动 `agents/tester_agent.py`；本任务正文完整保留，供二期直接执行。
> 已核对：其他 13 个任务**不依赖**本任务的任何产物（`make_run_id`、`record_from_result` 定义在 Task 2 的 `core/triage.py`）。
> 唯一连带影响：Task 14 的端到端验收第 6 步（线 1 真跑）本期跳过，改用 MCP 线产物验收。
> 二期开工额外补一项：`test_scripts/test_*.py:7-8` 的硬编码 `USERNAME` / `PASSWORD` 改读 `os.getenv`（本期用户决定不动，见 Task 6 Step 6.4 处置结论）。
> **注**：本任务正文里的行号（`:177-243` 等）写于本期，本期未逐个复核；二期开工前需先按 Task 6 的做法用脚本直读磁盘确认锚点。

**Files:**
- Modify: `agents/tester_agent.py:177-243`（步骤循环与收尾）、`:122-123, 921-922, 1274-1275`（预检失败）、`:172-175, 1030-1033, 1324-1327`（三处收尾）
- Test: 无新增单测（依赖真实浏览器），以 `TRIAGE_ENABLED=false` 回归 + 手工核验

- [ ] **Step 5.1: 加导入、run_id 与步骤分类器**

Modify `agents/tester_agent.py` 的 import 段（`from exporters.report_exporter import ReportExporter` 之后）：

```python
from core.config import TRIAGE_ENABLED
from core.triage import (
    make_run_id, record_from_result, append_records, new_record,
)
```

在 `class TesterAgent:` 内 `__init__` 末尾（`self.reporter = ReportExporter()` 之后）加：

```python
        # 分流：每次实例化生成一个 run_id，线 1 全部结果落到该 run 的 records.jsonl
        self.triage_run_id = make_run_id("")
        self._env_preflight_failed = False
        self._precondition_met = None      # 三态：登录+导航都成功才置 True，否则保持未知
```

在 `_check_assertion` 定义之前加两个辅助方法：

```python
    def _classify_step_outcome(self, output: str) -> str:
        """把 `_execute_action` 的中文返回串归到契约 5 态。与返回文案强耦合是已接受的代价：
        规则层需要「这一步到底执行了没有」，而改 `_execute_action` 签名属重构动作解析，本期不做。"""
        o = output or ""
        if o.startswith("未找到") or "未找到" in o or "找不到" in o:
            return "element_not_found"
        if o.startswith("失败"):
            return "element_not_found"
        if o.startswith("已执行（通用）"):
            return "skipped"          # 动作未被真正实现（回退分支），契约上按跳过处理（spec §4.1）
        if o.startswith("已跳过") or o.startswith("已查看"):
            return "noop"             # 有意不执行：已在目标页 / 纯观察类，视为真实到位
        return "ok"

    def _record_step(self, steps_detail: list, order, action, outcome: str, detail: str = "") -> None:
        steps_detail.append({"order": _to_int(order) if order != "" else len(steps_detail) + 1,
                             "action": action, "outcome": outcome, "detail": detail[:300]})
```

在模块级（`def _to_int(val)` 之后）加：

```python
def _to_int(val):
    """复用文件末尾已有的 _to_int 语义；若已存在同名函数则跳过本定义。"""
    try:
        return int(val)
    except Exception:
        try:
            return int(float(val))
        except Exception:
            return 0
```

> 文件末尾 `test_scripts` 风格代码里已有 `_to_int`（在 `parse_markdown_cases` 附近）。若该函数在模块级已可见，**删除上面的重复定义**，直接复用；只有当它是嵌套函数时才新增模块级版本。实施时先 `Select-String -Pattern "^def _to_int" -Path agents/tester_agent.py` 确认。

- [ ] **Step 5.2: 步骤循环保留结构化 outcome，并对假 PASS 降级**

Modify `agents/tester_agent.py` 的步骤循环（原 `:231-243`），整段替换为：

```python
            for s in case.get("steps", []):
                action = s.get("action", "")
                expected = s.get("expected", "")
                logger.info(f"  Step {s.get('order','')}: {action[:50]}")
                output = self._execute_action(page, action)
                outcome = self._classify_step_outcome(output)
                self._record_step(steps_detail, s.get("order", ""), action, outcome, output)
                logger.info(f"    -> {output[:80]}")
                if outcome == "element_not_found":
                    self.steps_not_found += 1
                    logger.warning(f"  [!] 步骤 {s.get('order','')} 未找到元素：{output[:80]}")
                elif outcome == "skipped":
                    self.steps_skipped += 1
                    logger.warning(f"  [!] 步骤 {s.get('order','')} 未真实执行：{output[:80]}")
                if "失败" in output:
                    fail_count += 1
```

把 `self.screenshots.append(self._take(page, "FAIL", case_id))` 所在的汇总块（原 `:259-271`）替换为：

```python
            # 结论：假 PASS 治理 —— 任一步骤未到位，状态上限 manual，不得判 pass / FAIL
            status = "PASS" if fail_count == 0 else "FAIL"
            if self.steps_not_found or self.steps_skipped:
                status = "MANUAL"
                logger.info(f"  => 结果: 待人工复核 (因 {self.steps_not_found} 未找到 / "
                            f"{self.steps_skipped} 未执行 步骤，原判定 {'PASS' if fail_count==0 else 'FAIL'} 降级)")
            else:
                logger.info(f"  => 结果: {status}")
            duration = (time.time() - start).seconds
            if status == "FAIL":
                self.screenshots.append(self._take(page, "FAIL", case_id))
            elif status == "MANUAL":
                self.screenshots.append(self._take(page, "MANUAL", case_id))
```

- [ ] **Step 5.3: 修正 `steps_detail` 初始化与计数器作用域**

Modify `_run_case` 开头（`steps_detail = []` 之前）加计数器重置——原实现用 `self.steps_not_found`/`self.steps_skipped` 是**实例级**变量，跨用例会累加。改为实例级重置以保证单用例判定正确：

```python
        self.steps_not_found = 0
        self.steps_skipped = 0
```

> 本项在 Step 5.2 的降级判定里已被依赖，必须放在 `for c in cases:` 循环**内部**、`start = time.time()` 之前。

- [ ] **Step 5.3b: 填 `precondition_met`（R6 的主判据）**

线 1 不猜测前置状态：只有登录+导航都成功才置 `True`，否则保持 `None`（不参与 R6）。

Modify `agents/tester_agent.py`，在 `run_suite` 登录与导航后（原 `:136-141`，两条 `logger.info(f"导航结果：{nav_result}")` 之后）加：

```python
                # 前置条件已建立：登录与模块导航均未报失败才置 True（供分流规则 R6 使用）
                self._precondition_met = ("失败" not in str(login_result)
                                          and "失败" not in str(nav_result))
```

另两处执行入口同步：`_execute_suite_with_page`（原 `:974` 之后，登录发生产生 `login_result` 处）与 `run_suite_from_md`（原 `:1253` 内），各自在导航完成后加同一行（按局部变量名调整）。

Modify `_build_record`（下一小节的实现）开头已含 `result.setdefault("precondition_met", self._precondition_met)`，无需在 `_run_case` 里逐个补字段。

- [ ] **Step 5.4: `_run_case` 返回值附带契约记录**

Modify `_run_case` 收尾（原 `:273-275`，构造 `result` 与 `return`）：在 `result = {...}` 之后、`# 断言详情` 之前补 `module`，并在返回前生成 record：

```python
        result["module"] = self.module_name or suite_name_fallback(self)
        # 分流：结构化事实落盘（失败绝不影响主测试流程）
        rec = self._build_record(result)
        return [{"result": result, "record": rec}]
```

在 `_run_case` 方法之后新增：

```python
    def _build_record(self, result: dict):
        """线 1 result dict → 契约记录；TRIAGE_ENABLED=false 或未启用时返回 None。"""
        if not TRIAGE_ENABLED:
            return None
        result.setdefault("precondition_met", self._precondition_met)
        try:
            return record_from_result(result, run_id=self.triage_run_id, executor="playwright_script")
        except Exception as e:
            logger.warning(f"  [triage] 构造 record 失败: {e}")
            return None

    def _flush_records(self, records: list) -> None:
        if not TRIAGE_ENABLED or not records:
            return
        try:
            append_records([r for r in records if r], self.triage_run_id)
            logger.info(f"[triage] 已写 {len(records)} 条记录 → "
                        f"{TRIAGE_DIR_NAME}/{self.triage_run_id}/records.jsonl")
        except Exception as e:
            logger.warning(f"[triage] 写 records.jsonl 失败（非致命）: {e}")
```

在 import 段追加 `from core.config import TRIAGE_ENABLED, TRIAGE_DIR`，并用 `TRIAGE_DIR.name` 替代 `TRIAGE_DIR_NAME`（写日志处）。

- [ ] **Step 5.5: 三处收尾统一走 `_finish_run`**

在 `_run_case` 之后新增：

```python
    def _finish_run(self, suite_name: str, results: list) -> None:
        """统一收尾：先落分流记录，再出报告。报告异常不得被记录失败掩盖。"""
        self._flush_records([r.get("record") for r in results if isinstance(r, dict) and r.get("record")])
        self.reporter.build_and_save(suite_name, results)
```

把三处 `self.reporter.build_and_save(suite_name, results)` / `(suite, results)` / `self.reporter.build_and_save(suite_name, results)`（原 `:173`、`:1032`、`:1326`）替换为 `self._finish_run(suite_name, results)`（第三处变量名为 `suite`，保持一致）。

- [ ] **Step 5.6: 预检失败写 ENV_BLOCK 记录**

在 `_env_preflight` 之后新增：

```python
    def _write_env_block_records(self, cases: list, suite_name: str, reason: str) -> None:
        """预检失败时不再静默 return None，为整 run 写 ENV_BLOCK 记录，避免 0 条结果的假正常。"""
        if not TRIAGE_ENABLED:
            return
        recs = []
        for c in cases:
            rec = new_record(run_id=self.triage_run_id, case_id=c.get("case_id", "?"),
                             module=self.module_name or suite_name, name=c.get("name", ""),
                             priority=c.get("priority", ""), status="error",
                             error=f"环境预检失败：{reason}", started_at=datetime.now().isoformat(timespec="seconds"))
            rec["triage"].update(category="ENV_BLOCK", source="rule", confidence=1.0,
                                 rationale="R1：环境预检未通过，本 run 用例未真实执行",
                                 suggested_action="修环境后整 run 重跑",
                                 unblock_hint=f"确认 {reason}")
            recs.append(rec)
        self._flush_records(recs)
```

在 4 处调用点（原 `:122-123`、`:921-922`、`:1274-1275`）把 `return None` 之前插入记录写入。以 `run_suite` 为例：

```python
        if not self._env_preflight():
            logger.error("测试环境不可用，中止套件")
            self._write_env_block_records(cases, suite_name, "TARGET_SERVERS 不可达或登录失败")
            return None
```

- [ ] **Step 5.7: 验证旧行为可完全退回**

Run（不依赖被测系统在线，只验证分流不落盘）:

```powershell
$env:TRIAGE_ENABLED="false"; python -c "import pathlib; p=pathlib.Path('output/06_reports/triage'); print(sorted(x.name for x in p.iterdir()) if p.exists() else 'none')"
$env:TRIAGE_ENABLED="false"; python -c "from agents.tester_agent import TesterAgent; a=TesterAgent(); a._flush_records([{'case_id':'X'}]); import pathlib; p=pathlib.Path('output/06_reports/triage'); print(sorted(x.name for x in p.iterdir()) if p.exists() else 'none')" > off.txt 2>&1; Get-Content off.txt; Remove-Item off.txt
```

Expected: 两次输出的 run 目录列表**完全一致**（关闭时 `_flush_records` 为空操作，不产生 `output/06_reports/triage/<run_id>/`）

> 说明：`run.py test` 不支持 `--suite/--module/--type` 参数（`cmd_test` 无参，直接跑 `run_all_suites()`）；要跑单模块用 `python scripts/run_test.py 知识管理`，但那需要被测系统在线，不作为本任务的退回验证手段。

Run: `$env:TRIAGE_ENABLED="true"; python -c "import agents.tester_agent"`
Expected: 无 ImportError / 无语法错误

> `TRIAGE_ENABLED` 在 `agents/tester_agent.py` 中是 import 期读取的常量，因此**改环境变量必须重开进程**才生效（本任务的验证命令已按此写成两条独立进程）。

- [ ] **Step 5.8: 回归现有测试**

Run: `python -m pytest tests -v`
Expected: `41 passed`（smoke 1 + contract 9 + rules 14 + merge 17，未因本次改动回归失败；原计划写的 33 已过期）

- [ ] **Step 5.9: Commit**

```powershell
git add agents/tester_agent.py
git commit -m "feat(triage): 线 1 写统一契约并治理假 PASS"
```

---

## Task 6: MCP 线接入契约（本期唯一执行入口·含加固）

现状：计划末尾只要求填一张 `TC-xxx | PASS/FAIL` Markdown 表格，事后手抄进报告 —— 这是结果失真的源头。本任务把「结果契约 + 填写要求 + 完整示例」内嵌进计划，并把「必须 append 到 `records.jsonl`」写成收尾硬门禁。

> **2026-09-15：因 Task 5（Playwright 线）延后，本任务成为本期唯一的结果入口**，因此除内嵌契约外额外加固三件事：固定 `run_id` + `plan_cases.json` 缺口校验、截图命名约定、计划不再写明文凭据（含 `.gitignore` 与取消跟踪，用户已批准）。入口唯一意味着任何漏填都会静默变成「没测过」。

**Files:**
- Modify: `agents/qoder_bridge.py:21-24`（import）、`:86-103`（计划头部凭据行与执行说明）、`:148-159`（结果记录段整体替换）、`:197-198` 与 `:206`（探索计划同样脱敏）、模块级新增 `_result_contract_block()`
- Modify: `.gitignore`（新增 `test_plan*.md` + `explore_plan.md` 两条忽略，Step 6.5）**已完成 commit `dfe533b`**
- 产物取消跟踪：`qoder_workspace/test_plan*.md` + `explore_plan.md`（共 6 个文件）**已完成 commit `dfe533b`**

- [x] **Step 6.1: 加导入、run_id 与截图目录**

Modify `agents/qoder_bridge.py` 的 config import（实配：Step 6.4 已提前完成，所以 `TEST_USERNAME` / `TEST_PASSWORD` **从未回到本 import**）：

```python
from core.config import (
    DESIGN_WORKSPACE_DIR, APP_URL,
    ROOT, SCREENSHOTS_DIR, REPORTS_DIR, TRIAGE_DIR, TRIAGE_ENABLED,
)
from core.triage import make_run_id, write_plan_cases
from utils.logger import get_logger
```

> 2026-09-15 实施：原计划的 `TEST_PASSWORD` 保留步骤已无意义（凭据脱敏已由 `dfe533b` 做完），额外加了 `TRIAGE_ENABLED`（旧版表格分支需要它）。已核：文件内 `TEST_USERNAME|TEST_PASSWORD` 仅余文档字串（`:181`/`:322`/`:331`），无变量引用。

在 `generate_test_plan` 内、`total_cases = 0` 之前加：

```python
    run_id = make_run_id(module_name or "全量")
    record_path = TRIAGE_DIR / run_id / "records.jsonl"
    shot_dir = SCREENSHOTS_DIR / run_id
    plan_case_ids = []      # 收集计划内全部 case_id，循环结束后写 plan_cases.json
```

> **实施时修正（原位置会 `NameError`）**：本步只说「在 `total_cases = 0` 之前」，但 Step 6.3 要往计划头部的 `plan_lines` 字面量里插 `run_id` 行，而 `plan_lines` 在 `total_cases = 0` **之前**就已构造。实际落地位置：紧跟 `md_files = sorted(...)` 之后、`plan_lines = [` 之前（仍满足「在 `total_cases = 0` 之前」）。头部行用先算好的 `run_line` + `*([run_line] if run_line else [])` 展开，保证 `TRIAGE_ENABLED=false` 时一行不残留。

- [x] **Step 6.2: 用契约块替换自由格式表格要求**

把 `agents/qoder_bridge.py:148-159`（`# 添加结果记录格式` 至 `plan_lines.extend([...])` 结束）整段替换为（**实施时改为 `if TRIAGE_ENABLED:` 分支，`else:` 保留旧版那张表，以实现「一键回退」**）：

```python
    # 结果契约（取代旧版「一张 Markdown 表格 + 事后手抄」）
    plan_lines.extend(_result_contract_block(run_id, record_path))
    plan_lines.extend([
        "",
        "## 执行进度小结（人类可读，供收尾报告引用）",
        "",
        "计划内**每条**用例都要在这里占一行，没做的写 `skipped` 并说明原因，不得省略行：",
        "",
        "| 用例 ID | 用例名称 | 状态 | 分流建议 | 备注 |",
        "|---------|----------|------|----------|------|",
        "| TC-xxx  | xxx      | pass/fail/blocked/skipped/error/manual | 6 类之一或留空 | 说明 |",
        "",
        f"截图目录（先建再写）: `{shot_dir}`，文件名格式：用例ID_动作或阶段.png（例 TC-CAT-001_保存后层级.png）",
    ])
```

在模块级（`QODER_WORKSPACE.mkdir(...)` 之后）新增：

> **开关语义**：`TRIAGE_ENABLED=false` 时 `_result_contract_block()` 不输出，结果记录段退回旧版那张 `PASS/FAIL` 表格（不写 `plan_cases.json`）；但 **Step 6.4 的凭据脱敏不受开关控制**，安全修复无条件生效。

```python
def _result_contract_block(run_id: str, record_path) -> list:
    """线 2 的结果契约说明。JSON 示例用字符串拼接而非 f-string，避开花括号转义。"""
    return [
        "",
        "## 【硬性收尾门禁】结果必须按契约写入 JSONL",
        "",
        f"**未写入 `{record_path}` = 本次执行未完成**，不得口头汇报「已执行完」。",
        f"**计划内每一条用例都要在 JSONL 里占一行**（确实没做的写 `status: \"skipped\"` 并在 `error` 里写原因），",
        f"本 run 的用例全集已存于 `{(TRIAGE_DIR / run_id / 'plan_cases.json').as_posix()}`；",
        f"写完后运行 `python run.py triage {run_id} --validate`：它会校验契约并列出「计划 N / 已记录 M / 缺口 K」。",
        "",
        "### 必填字段与取值",
        "",
        f"- `run_id` / `executor`：`run_id` 固定填 `{run_id}`；`executor` 固定填 `qoder_mcp`",
        "- `case_id` / `name` / `module` / `status`：`status` ∈ `pass` / `fail` / `error` / "
        "`manual` / `blocked` / `skipped`（**不要用大写 PASS**）",
        "- `precondition` / `test_data` / `error`：无内容写空串，**不得缺键**",
        "- `precondition_met`：三态 `true` / `false` / `null`。只有你**明确验证过**前置没建立才填 `false`；"
        "不知道就填 `null`（填错会把用例错推进「数据前置未满足」桶并移出失败率分母）",
        "- `steps[]`：`{order, action, outcome, detail}`；`outcome` ∈ `ok`（真做了）/ `element_not_found` / "
        "`skipped`（想做但没做成，含工具不支持）/ `noop`（有意不执行：已在目标页、纯观察步骤）/ "
        "`unknown`（你没确认）；`detail` 写实际看到的现象（含可疑行为，如字符被静默过滤）",
        "- `assertions[]`：`{text, verdict, reason, evidence_refs}`；`verdict` ∈ `pass` / `fail` / "
        "`unverifiable`。**禁止新增或改写断言原文**，只能对计划里给定的断言下判定",
        "- `url_at_failure` / `screenshots[]` / `log_path` / `console_errors[]`：失败时尽量填全。",
        f"  截图必须存 `output/06_reports/screenshots/{run_id}/{{case_id}}_{{动作}}.png`（目录不存在先创建），",
        "  `screenshots[]` 填仓库相对路径；无截图就留空数组，**不得填不存在的文件名**。",
        "- `triage`：执行阶段留空（`category: \"\"`, `source: \"none\"`），由 `run.py triage` 填",
        "- 若你主张 `ENV_BLOCK` / `DATA_PRECOND`，必须同时给 `unblock_hint`（否则会被回落为待人工裁决）",
        "",
        "### 完整示例（照抄结构，替换内容）",
        "",
        "```json",
        "{",
        f'  "run_id": "{run_id}",',
        '  "executor": "qoder_mcp",',
        '  "case_id": "TC-CAT-001",',
        '  "name": "验证在文档知识库下新建一级分类功能正常",',
        '  "module": "分类管理",',
        '  "priority": "P0",',
        '  "case_type": "正向",',
        '  "test_point_ref": "TP-CAT-001",',
        '  "req_source": "CAT-01,CAT-04",',
        '  "started_at": "2026-09-14T17:30:05+08:00",',
        '  "duration_sec": 180,',
        '  "status": "fail",',
        '  "precondition": "已登录，进入知识管理页面",',
        '  "precondition_met": true,',
        '  "test_data": "分类名称：QAuto-CAT001-0914",',
        '  "error": "保存后新分类挂在 level=5 而非 level=2",',
        '  "steps": [',
        '    {"order": 1, "action": "点击左侧\\"文档知识库\\"节点", "outcome": "ok", "detail": "treeitem 展开"},',
        '    {"order": 2, "action": "点击\\"新增分类\\"按钮", "outcome": "ok", "detail": "弹窗打开"},',
        '    {"order": 3, "action": "输入分类名称", "outcome": "ok", "detail": "SUSPECT：- 被静默过滤"}',
        '  ],',
        '  "assertions": [',
        '    {"text": "弹窗关闭", "verdict": "pass", "reason": "", "evidence_refs": []},',
        '    {"text": "新分类作为一级分类出现在文档知识库下", "verdict": "fail",',
        '     "reason": "实际挂在 level=5", "evidence_refs": ["TC-CAT-001_保存后层级.png"]}',
        '  ],',
        '  "url_at_failure": "http://.../knowledgeManger",',
        f'  "screenshots": ["output/06_reports/screenshots/{run_id}/TC-CAT-001_保存后层级.png"],',
        '  "log_path": "",',
        '  "console_errors": [],',
        '  "triage": {"category": "", "source": "none", "confidence": 0.0, "rationale": "",',
        '             "suggested_action": "", "unblock_hint": "", "decided_by": "",',
        '             "decided_at": "", "overridden": false},',
        '  "bug_draft": null,',
        '  "retry_count": 0,',
        '  "needs_reconfirm": false',
        "}",
        "```",
        "",
        "> 契约违规的行会被自动降级为「待人工裁决」并记入 `triage_errors.log`，不会中断执行。",
        "> 同一 `case_id` 重复写取最后一条（可用于自我更正），重复数会进入报告摘要。",
        "> ⚠ 因而**全量计划（不带模块名）下不同模块的同名 `case_id` 会互相覆盖**（如两个模块都有 `TC-CAT-001`）：",
        ">   生成计划时若检出撞号会打印告警，建议按模块分别生成计划分别执行。",
    ]
```

> 2026-09-15 实施：本块末尾新增了上面两行「同名 `case_id` 互相覆盖」警告（原计划没有）。理由见 Step 6.3 的撞号发现：它是「取最后一条」这条去重规则在**全量模式下丢记录**的直接后果，契约里必须写。

- [x] **Step 6.3: 收集计划内 case_id 并落 `plan_cases.json`**

在用例循环里 `plan_lines.append(f"### {case_id} - {case_name} ...")`（源文件 `agents/qoder_bridge.py:129`）**之后**加一行：

```python
            plan_case_ids.append(case_id)
```

把 `run_id` 与结果文件路径写进计划头部（`plan_lines` 列表里 `f"**生成时间**: ..."` 那一行之后）：

```python
        f"**run_id**: {run_id}　**结果文件（必须写入）**: {record_path}",
```

在 `plan_path.write_text(...)` 之后、`logger.info(f"测试计划已生成...")` 之前加：

```python
    plan_cases_path = write_plan_cases(
        run_id, plan_case_ids, module=module_name or "全量",
        source_file=str(md_files[0].parent) if md_files else "")
```

并在末尾的终端提示区（`print(f"\n  下一步：在 Qoder 对话中输入：")` 之前）加：

```python
    print(f"\n  结果必须写入：{record_path}")
    print(f"  计划内用例 {len(plan_case_ids)} 条 → {plan_cases_path}")
    print(f"  执行完请跑：python run.py triage {run_id} --validate")
```

> 计划文件会被同名覆盖（`test_plan_知识管理.md`），而 `records.jsonl` 按 run_id 累积 —— 这就是用 run_id 而非文件名做主键的原因。

> **2026-09-15 实施时发现问题并加固（实测数据，不是推测）**：全量模式（`generate_test_plan(None)`）下不同模块的用例 ID 会**真出现重名** —— 实测去重后 151 条全集里，有 **19 个 `case_id` 出现多次**（`TC-CAT-001` … `TC-CAT-019` 在项目管理与知识管理两个模块里同名）。因为 `load_records()` 同 `case_id` 取最后一条，不拦一手就是**最多 19 条执行记录凭空消失且缺口数算错**。因此：
> - 写入前先 `unique_case_ids = list(dict.fromkeys(plan_case_ids))` 去重（保持计划里的顺序），`plan_cases.json` 只存去重后的全集；
> - `collisions = sorted({c for c in unique_case_ids if plan_case_ids.count(c) > 1})`，非空则 `logger.warning` + 终端 `⚠` 提醒「建议按模块分别执行」；
> - 不拒绝生成全量计划（那是用户权利），只把风险当面说清；契约块里同步写了两行警告（Step 6.2）。
> - 开关关时不写 `plan_cases.json`（`plan_cases_path = None`），也不打印这三行。

- [x] **Step 6.4: 计划与探索计划都不写明文凭据**（✅ 2026-09-15 已单独提前完成，commit `dfe533b`）

实测原文与行号（已核对）：`:91` 与 `:197` 均为 `f"**登录账号**: {TEST_USERNAME} / {TEST_PASSWORD}",`；`:206` 为 `f"- 使用账号 {TEST_USERNAME} / {TEST_PASSWORD} 登录",`。已全部改为指向 `.env` 的说明文字，并从 `:21-24` 的 import 中删除了 `TEST_USERNAME` / `TEST_PASSWORD`（文件内仅余文档字串中的名字，无变量引用）。

实际执行方式（与计划的差异）：现存计划文件脱敏未用上面的 PowerShell 单行（中文正则 + `-NoNewline` 在 PowerShell 里不可靠），而是用一次性脚本 `tmp_sanitize.py`（跑完已删除）做 4 条行首锁定正则，共替换 9 行、`git diff --numstat` 验证为 9+/9- 无内容丢失，残留检查 `<TEST_PASSWORD>` 命中 0。

> **仍然有效的警告**：本步只保证**以后**不写。**git 历史里的旧口令仍在**（`dfe533b` 之前的提交），彻底清除需 `filter-repo`/`filter-branch`（风险高、改变提交号），本期不做；若该口令有效，**请先去系统里改密码**。

尚余旧痕的处置结论（用户 2026-09-15 拍板）：

- ✅ 已改（commit `6b4de43`）：`scripts/export_home_*.py` 3 个文件将测试数据/元信息列里的 `zgn/<TEST_PASSWORD>`、`zjj/<TEST_PASSWORD>` 换为指向 `.env` 的说明
- ⏸ 本期不改：`test_scripts/test_*.py` 3 个文件 `:7-8` 的 `USERNAME = "zgn"` / `PASSWORD = "<TEST_PASSWORD>"`（属已延后的线 1），**归入二期跟 Task 5 一起处理**，改法为读 `os.getenv("TEST_USERNAME")` / `os.getenv("TEST_PASSWORD")`
- 不算泄漏：`scripts/gen_iap_report.py:4`、`.qoder/skills/**`、`output/00_explore/**` 只出现**用户名** `zgn` / `zjj`（无口令，且属权限对比的事实记录），不动
- `output/**` 历史报告含口令，但该目录整体不入库，仅在本地

- [x] **Step 6.5: `.gitignore` 忽略计划文件并取消跟踪**（✅ 2026-09-15 已单独提前完成，commit `dfe533b`）

实测已做：新增忽略规则 `qoder_workspace/test_plan*.md` + `qoder_workspace/explore_plan.md`（后者同样由 `generate_explore_plan()` 写凭据，属于同类产物，一并取消跟踪），并更新文件头部原则注释；`git rm --cached` 取消 6 个 md，磁盘保留（已验证 7 个文件仍在）。

已落地的规则（在 `.gitignore` 的敏感配置段之后）：

```
# ---------- Qoder 生成的执行/探索计划（历史上含明文凭据，本地保留、不入库）----------
qoder_workspace/test_plan*.md
qoder_workspace/explore_plan.md
```

已执行：`git rm --cached "qoder_workspace/*.md"` → 6 个 md 从索引移除；`Test-Path` 验证磁盘 7 个文件仍在。

> 边界（已修正）：取消跟踪的是 `test_plan*.md` **与** `explore_plan.md`（后者同样由 `generate_explore_plan()` 写凭据）。`test_result_*.json`（历史证据 + 转换器输入）**继续跟踪**。

- [x] **Step 6.6: 验证计划文件含契约、含 run_id、不含口令**

> 2026-09-15 实测方式与计划不同：改用一次性脚本（已删），在**进程内** `os.environ["TRIAGE_ENABLED"]` 于 import config 之前设定，直接调用 `generate_test_plan("知识管理")` / `(None)`。理由：走 `run.py` 命令行时一次复验未生效（无法确定是 `$env:` 未传递还是中文参数被 PowerShell 编码吃掉），进程内调用则两种开关状态都得到确定结果。

Run: `$env:TRIAGE_ENABLED="true"; python -c "from agents.qoder_bridge import generate_test_plan; print(generate_test_plan('知识管理'))"`
Expected: 打印计划路径，**并额外打印三行**（结果文件路径 / 计划内用例数 / `run.py triage ... --validate`）；随后核验：

```powershell
Select-String -Path qoder_workspace/test_plan_知识管理.md -Pattern '硬性收尾门禁|precondition_met|qoder_mcp|plan_cases.json' | Measure-Object | Select-Object Count
Select-String -Path qoder_workspace/test_plan_知识管理.md -Pattern '<TEST_PASSWORD>|/ \{TEST_PASSWORD\}|登录账号' | Measure-Object | Select-Object Count
python -m pytest tests -v
```

Expected：第一条 `Count ≥ 5`（旧版一个都不会出现）；**第二条 `Count = 0`（凭据不落盘）**；第三条全绿、`0 failed`（本任务不新增单测，重点是已有用例无回归）

实测结果（`test_plan_知识管理.md`，出现次数统计，与上面的行计数等价）：

| 开关 | 计划字数 | JSONL | precondition_met | qoder_mcp | plan_cases.json | `**run_id**` | PASS/FAIL | `<TEST_PASSWORD>` |
|---|---|---|---|---|---|---|---|---|
| `true` | 12025 | 2 | 2 | 2 | 1 | 1 | **0** | **0** |
| `false` | 8493 | 0 | 0 | 0 | 0 | 0 | 1（旧表） | **0** |

附加实测：
- `plan_cases.json` 写入 `output/06_reports/triage/知识管理_20260915_111628/`，`module=知识管理`、`case_ids` 49 条；`load_plan_cases()` 回读一致。
- 零记录时 `diff_plan_vs_records()` → `49 planned / 0 recorded / 49 missing`（缺口数学对，Task 12 的 `--validate` 直接用）。
- 全量模式（`generate_test_plan(None)`）→ 去重后 151 条，**19 个 `case_id` 撞号**告警如预期打印（Step 6.3 加固分支的真实覆盖）。
- `python -m pytest tests -q` → `41 passed`，`agents/qoder_bridge.py` 用 `ast.parse` 语法自查通过。

- [x] **Step 6.7: Commit**

```powershell
git add agents/qoder_bridge.py .gitignore
git add -u qoder_workspace
git commit -m "feat(triage): MCP 计划内嵌结果契约+run_id+缺口清单，凭据不再落盘并取消计划文件跟踪"
```

> 2026-09-15 实施：`.gitignore` 与 `qoder_workspace` 取消跟踪已在 `dfe533b` 完成，所以本提交只含 `agents/qoder_bridge.py` + 本计划文档。

---

## Task 7: 旧数据转换器 + 契约回归样本

把 `qoder_workspace/test_result_*.json`（结构：`meta` / `cases[]` / `pending_cases[]` / `summary_partial`）映射为契约记录。历史产物不作废，同时充当契约的回归样本。

> **2026-09-15 实施时修正四处**（均已同步到下方代码块）：
> 1. **转换器不给历史 `pending_cases` 写 `precondition_met=False`，改写 `None`**。历史 pending 从没有人验证过前置，写 `false` 等于伪造事实；更糟的是 R6 主判据（`status ∈ {fail,error,manual,blocked} and precondition_met is False`）会抢在 blocker 文本判定之前命中，把 11 条全部塞进「数据前置未满足」并移出失败率分母——分流器就变成一个可以把任何失败洗白的机器。留 `null`（未知）才能让 blocker 文本真正分流。
> 2. **不抄 `meta.test_account`**。计划原文 `precondition=... or f"已登录 {meta.get('test_account','')}"` 会把账号名 `zgn` 写进 `records.jsonl`，违反本期「凭据不落盘」。改为固定写「已登录」，并补常驻测试 `test_no_account_name_leaks_into_records` 守住。
> 3. **顺带修掉一个真实质量 bug**：规则层 blocked 分支读的是 `rec.get("unblock_hint")`（顶层，永远为空），而转换器写在 `rec["triage"]["unblock_hint"]`；且 `apply_rule_layer` 会用规则层的空/通用文案擦掉 blocker 自带的解除路径（报告里 BLOCKED 独立表全靠它）。已改成读 `triage` 层 + 规则层无具体 hint 时不擦已有值，补测试 `test_blocker_text_survives_as_unblock_hint`。
> 4. **分流期望 6/6 改为实测 5/7**。按本任务自己的关键字表跑真实历史数据得到 `数据前置未满足=5 / 待人工裁决=7`；为凑 6/6 而加关键字（如把 `依赖` 单独收进去）会误伤「依赖创建"编辑中"知识」这类含糊写法——那 6 条里有 4 条 blocker 写着「可执行」，本就该由人判断是执行者放弃还是真阻塞，不该被规则层猜。**遵循本任务 Step 7.6 的告诫：改测试期望并说明理由，不动关键字表。**

**Files:**
- Create: `scripts/_convert_legacy_result.py`
- Modify: `core/triage.py`（`_MISSING_PRECOND_KEYWORDS` 扩充、`_hit` 空白归一化、新增 `to_result_rows`）
- Test: `tests/test_convert_legacy.py`

- [x] **Step 7.1: 先修规则层的关键词匹配**

`pending_cases[].blocker` 常见写法是「依赖 TC-KM-001」「前置数据无法保证」「需要先造一个空分类」，关键字必须能命中带空格与不带空格的写法。

Modify `core/triage.py` 的关键字元组：

```python
_MISSING_PRECOND_KEYWORDS = ("未准备", "无法提供", "缺少测试数据", "需要先", "未上传",
                            "依赖TC", "无法验证", "无法保证", "前置数据")
```

并把 `_hit` 改为空白归一化匹配：

```python
def _hit(text: str, keywords) -> str:
    """关键字匹配前对两侧都做空白归一化，避免「依赖 TC-」与「依赖TC-」两种写法漏判。"""
    norm = re.sub(r"\s+", "", text or "")
    for k in keywords:
        if re.sub(r"\s+", "", k) in norm:
            return k
    return ""
```

> 2026-09-15 实施：本步骤还多做了两处（见上方修正第 3 条）——blocked 分支的 `hint` 改读 `rec.get("triage", {}).get("unblock_hint")`；`apply_rule_layer` 在 `res["unblock_hint"]` 为空时保留 `rec["triage"]` 里已有的值，不用通用文案覆盖。

- [x] **Step 7.2: 加反向映射 `to_result_rows`**

Append to `core/triage.py`：

```python
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
```

- [x] **Step 7.3: 写失败测试**

> 2026-09-15 实施：实际写出的测试是 **8 个**（计划 6 个 + `test_no_account_name_leaks_into_records`、`test_blocker_text_survives_as_unblock_hint`），并把两处期望改成实测值（`precondition_met is None`、`5 / 7`）。

Create `tests/test_convert_legacy.py`:

```python
"""契约回归样本：真实历史产物 `test_result_P0_km_20260907.json` 转换 + 过规则层。

断言的是 spec §9.2 的期望：两条已记录的 Bug 不得被判成环境/执行问题，必须走 R7 送 LLM；
未执行的 pending_cases 按 blocker 文本分流，且写盘后重读无损。
"""
import importlib.util
from pathlib import Path

import pytest

from core import config
from core.triage import (apply_rule_layer, append_records, compute_summary, load_records,
                         merge_decisions, to_result_rows)

REPO = Path(__file__).resolve().parents[1]
LEGACY = REPO / "qoder_workspace" / "test_result_P0_km_20260907.json"


def _load_converter():
    spec = importlib.util.spec_from_file_location(
        "_convert_legacy_result", REPO / "scripts" / "_convert_legacy_result.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def converted(tmp_path, monkeypatch):
    mod = _load_converter()
    monkeypatch.setattr(config, "TRIAGE_DIR", tmp_path / "triage")
    records, run_id = mod.convert(LEGACY)
    return records, run_id


def test_legacy_shape_preserved(converted):
    records, run_id = converted
    assert run_id == "P0_km_20260907"
    assert len(records) == 12                       # 1 条已执行 + 11 条 pending
    assert all(r["executor"] == "qoder_mcp" for r in records)


def test_executed_case_goes_to_rule_r7_not_env_or_exec(converted):
    records, _ = converted
    case = next(r for r in records if r["case_id"] == "TC-CAT-001")
    assert case["status"] == "fail"
    assert all(s["outcome"] == "ok" for s in case["steps"])    # SUSPECT 步骤仍是「做了」
    assert any(a["verdict"] == "fail" for a in case["assertions"])
    apply_rule_layer([case])
    assert case["triage"]["category"] == "NEEDS_HUMAN"
    assert "R7" in case["triage"]["rationale"]                   # 送 LLM，不冒充定性
    assert case["bug_draft"]["id"] == "BUG-CAT-01"              # 旧 Bug 草稿不丢


def test_pending_cases_split_by_blocker_text(converted):
    records, _ = converted
    apply_rule_layer(records)
    cats = {r["case_id"]: r["triage"]["category"] for r in records}
    assert cats["TC-KM-001"] == "DATA_PRECOND"       # 本地路径未准备
    assert cats["TC-CAT-014"] == "DATA_PRECOND"      # 需要先造空分类
    assert cats["TC-KM-002"] == "DATA_PRECOND"       # 依赖 TC-KM-001（含空格写法）
    assert cats["TC-CAT-002"] == "DATA_PRECOND"      # 前置数据无法保证
    assert cats["TC-CAT-018"] == "NEEDS_HUMAN"       # blocker 写「无」，不得塞进阻塞逃分母
    blocked = [r for r in records if r["status"] == "blocked"]
    assert len(blocked) == 11
    assert all(r["precondition_met"] is None for r in blocked)   # 历史 pending 无人验证过前置：只能写「未知」
    # 规则层不得擦掉 blocker 自带的解除路径（报告 BLOCKED 独立表靠它）
    km2 = next(r for r in records if r["case_id"] == "TC-KM-002")
    assert "TC-KM-001" in km2["triage"]["unblock_hint"]


def test_summary_buckets_sum_equals_total(converted):
    records, _ = converted
    apply_rule_layer(records)
    s = compute_summary(merge_decisions(records, {}, {}))
    assert s["总用例"] == 12
    assert s["总用例"] == sum(v for k, v in s.items()
                            if k not in ("总用例", "通过率", "有效通过率", "移出分母"))
    assert s["数据前置未满足"] == 5 and s["待人工裁决"] == 7
    assert s["环境阻塞"] == 0 and s["真实缺陷"] == 0        # 铁律：自动层不得定性 PRODUCT_BUG


def test_written_jsonl_reload_is_lossless(converted, tmp_path, monkeypatch):
    records, run_id = converted
    monkeypatch.setattr(config, "TRIAGE_DIR", tmp_path / "triage")
    append_records(records, run_id)
    reloaded, dup, malformed = load_records(run_id)
    assert dup == 0 and malformed == 0 and len(reloaded) == 12


def test_to_result_rows_feeds_legacy_reporter(converted):
    records, _ = converted
    rows = to_result_rows(records)
    assert rows[0]["id"] == "TC-CAT-001"
    assert rows[0]["status"] in ("pass", "fail", "error", "manual", "blocked", "skipped")
    assert isinstance(rows[0]["assertions"], list) and rows[0]["assertions"][0]["passed"] is True
    assert "→" in rows[0]["steps"]
```

- [x] **Step 7.4: 运行确认失败**

Run: `python -m pytest tests/test_convert_legacy.py -v`
Expected: FAIL，`FileNotFoundError` 或 `ModuleNotFoundError`（`scripts/_convert_legacy_result.py` 不存在）

> 2026-09-15 实测：`8 errors`（全部来自 `_load_converter()` 加载不到转换器文件），既有 40 个测试无回归。

- [x] **Step 7.5: 写转换器**

Create `scripts/_convert_legacy_result.py`:

```python
"""把旧 `qoder_workspace/test_result_*.json` 一次性映射为统一契约 `records.jsonl`。

映射表（旧 → 契约）：
  meta.run_id                                  → run_id（保留原值，便于与历史报告对照）
  meta.executor 含 qoder/mcp                   → executor="qoder_mcp"
  cases[].status FAIL/PASS/BLOCKED              → fail/pass/blocked（大写归小写）
  steps_executed[].result OK/SUSPECT            → outcome="ok"（SUSPECT 的疑点留在 detail，
                                                   因为步骤确实执行过，不当作执行问题）
  expected_results[].verdict PASS/FAIL/SKIPPED  → assertions[].verdict pass/fail/unverifiable
  assertions[].{target,expected,actual,passed,note} → 追加为断言（text=target，reason 含期望/实际）
  bugs[0]                                       → bug_draft（信息保留，定性仍须人工确认）
  pending_cases[].blocker                       → status="blocked" + precondition_met=None（未知，见 Task 7 修正①）
                                                   + error/unblock_hint = blocker
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.triage import append_records, new_record, run_dir   # noqa: E402


def _low(v) -> str:
    return str(v or "").strip().lower()


def _status_from(v: str) -> str:
    return {"pass": "pass", "passed": "pass", "ok": "pass",
            "fail": "fail", "failed": "fail",
            "blocked": "blocked", "skip": "skipped", "skipped": "skipped",
            "manual": "manual", "error": "error"}.get(_low(v), "error")


def _verdict_from(v: str) -> str:
    return {"pass": "pass", "passed": "pass", "ok": "pass",
            "fail": "fail", "failed": "fail",
            "skipped": "unverifiable", "unverifiable": "unverifiable"}.get(_low(v), "unverifiable")


def _steps_of(case: dict) -> list:
    out = []
    for s in case.get("steps_executed", []):
        res = _low(s.get("result", ""))
        out.append({"order": s.get("order", len(out) + 1), "action": s.get("action", ""),
                    "outcome": "element_not_found" if res in ("not_found", "missing", "notfound") else "ok",
                    "detail": f"[{s.get('result')}] {s.get('detail', '')}".strip()[:300]})
    return out


def _assertions_of(case: dict) -> list:
    out = []
    for e in case.get("expected_results", []):
        skipped = _low(e.get("verdict", "")) == "skipped"
        out.append({"text": e.get("text", ""), "verdict": _verdict_from(e.get("verdict", "")),
                    "reason": e.get("actual", "") or ("执行者标记 SKIPPED" if skipped else ""),
                    "evidence_refs": []})
    for a in case.get("assertions", []):
        reason = f"期望 {a.get('expected')} / 实际 {a.get('actual')}"
        if a.get("note"):
            reason += f"（{a['note']}）"
        out.append({"text": str(a.get("target", "")),
                    "verdict": "pass" if a.get("passed") else "fail",
                    "reason": reason, "evidence_refs": []})
    return out


def _first_fail_actual(case: dict) -> str:
    """从 `expected_results` 里第一条 FAIL 取实际现象，作为 `error` 的首选来源。"""
    for e in case.get("expected_results", []):
        if _low(e.get("verdict", "")) == "fail" and e.get("actual"):
            return str(e["actual"])
    return ""


def convert(path: Path) -> tuple:
    """返回 (records, run_id)。纯函数：不写盘，便于单测直接 import。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    meta = data.get("meta", {})
    run_id = meta.get("run_id") or path.stem.replace("test_result_", "")
    raw_exec = _low(meta.get("executor", ""))
    executor = "qoder_mcp" if ("mcp" in raw_exec or "qoder" in raw_exec) else "playwright_script"
    module = meta.get("module", "")
    now = datetime.now().isoformat(timespec="seconds")
    records = []

    for case in data.get("cases", []):
        bugs = case.get("bugs") or []
        rec = new_record(
            run_id=run_id, case_id=case.get("case_id", "?"),
            module=case.get("module", module) or module, executor=executor,
            name=case.get("name", ""), priority=case.get("priority", ""),
            case_type=case.get("type", ""),
            req_source=",".join(sorted({b.get("req_source", "") for b in bugs if b.get("req_source")})),
            started_at=case.get("start_time") or meta.get("start_time") or now,
            duration_sec=float(case.get("duration_sec", 0) or 0),
            status=_status_from(case.get("status", "error")),
            # 不抄 `meta.test_account`：凭据（含账号名）不进任何落盘产物
            precondition=case.get("precondition", "") or "已登录",
            precondition_met=True,        # 已进入执行的旧用例：无更强证据时计作前置已建立
            test_data=case.get("test_data", ""),
            error=_first_fail_actual(case) or "; ".join(b.get("title", "") for b in bugs),
            steps=_steps_of(case), assertions=_assertions_of(case),
            screenshots=case.get("screenshots", []), log_path=case.get("log", ""),
        )
        rec["submodule"] = case.get("module", "")
        rec["url_at_failure"] = meta.get("target_url", "")
        rec["bug_draft"] = bugs[0] if bugs else None
        records.append(rec)

    for p in data.get("pending_cases", []):
        blocker = p.get("blocker", "") or p.get("note", "")
        rec = new_record(
            run_id=run_id, case_id=p.get("case_id", "?"),
            module=p.get("module", module) or module, executor=executor,
            name=p.get("name", ""), priority=p.get("priority", ""),
            status="blocked",
            precondition=p.get("precondition", ""),
            # 历史 pending 从没被验证过前置，写 `false` 等于伪造事实，且会被 R6 主判据全部抢走
            precondition_met=None,
            test_data=p.get("test_data", ""), error=blocker,
            started_at=p.get("start_time") or meta.get("start_time") or now,
        )
        rec["triage"]["unblock_hint"] = blocker
        records.append(rec)

    return records, run_id


def main(argv: list) -> int:
    default_dir = Path(__file__).resolve().parents[1] / "qoder_workspace"
    targets = [Path(a) for a in argv] or sorted(default_dir.glob("test_result_*.json"))
    if not targets:
        print(f"未找到 {default_dir}/test_result_*.json")
        return 1
    for t in targets:
        recs, rid = convert(t)
        append_records(recs, rid)
        print(f"{t.name} → {run_dir(rid) / 'records.jsonl'}（{len(recs)} 条，run_id={rid}）")
        print(f"  下一步：python run.py triage {rid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [x] **Step 7.6: 运行确认通过**

Run: `python -m pytest tests/test_convert_legacy.py -v`
Expected: PASS，`8 passed`（实施时由 6 个增到 8 个）

Run: `python -m pytest tests -v`
Expected: `49 passed`（smoke 1 + contract 6 + rules 14 + merge 17 + convert 8）

> 若 `test_pending_cases_split_by_blocker_text` 失败，先打印实际分类：
> `python -c "import importlib.util,pathlib;s=importlib.util.spec_from_file_location('c',pathlib.Path('scripts/_convert_legacy_result.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);from core.triage import apply_rule_layer;r,_=m.convert(pathlib.Path('qoder_workspace/test_result_P0_km_20260907.json'));apply_rule_layer(r);print([(x['case_id'],x['triage']['category']) for x in r])"`
> 不要为了凑测试而改关键字表；若判断测试期望本身不对，改测试并在 commit message 里说明理由。

> 2026-09-15 实测：`8 passed` / 全量 `49 passed`。上面的诊断命令真跑过一次，12 条历史记录的实际分流如下（这是后续报告与人工门禁的基准样本）：
>
> | case_id | status | category | 规则 |
> |---------|--------|----------|------|
> | TC-CAT-001 | fail | NEEDS_HUMAN | R7（步骤全 ok + 有可验证断言失败 → 送 LLM/人，规则层不下结论） |
> | TC-CAT-002 | blocked | DATA_PRECOND | R6（“前置数据无法保证”） |
> | TC-CAT-014 | blocked | DATA_PRECOND | R6（“需要先造一个空分类”） |
> | TC-CAT-015 | blocked | DATA_PRECOND | R6（“需要先选中…”） |
> | TC-CAT-018 | blocked | NEEDS_HUMAN | R8（blocker 写“无”，不充当阻塞逃分母） |
> | TC-CAT-019 | blocked | NEEDS_HUMAN | R8（同上） |
> | TC-KM-001 | blocked | DATA_PRECOND | R6（“本地路径未准备”） |
> | TC-KM-002 | blocked | DATA_PRECOND | R6（“依赖 TC-KM-001”，带空格写法靠空白归一化命中） |
> | TC-KM-003 / 007 / 008 / 021 | blocked | NEEDS_HUMAN | R8（“可执行”/“同 TC-KM-007 前置”/“依赖创建…”，含糊写法交给人） |
>
> 汇总：`总用例=12　数据前置未满足=5　待人工裁决=7　环境阻塞=0　真实缺陷=0　移出分母=5`（桶和 == 总用例，铁律① 未被违反）。

- [x] **Step 7.7: 真跑一次转换（产物不入 git）**

Run: `python scripts/_convert_legacy_result.py`
Expected: 输出 `test_result_P0_km_20260907.json → output\06_reports\triage\P0_km_20260907\records.jsonl（12 条，run_id=P0_km_20260907）`

> 2026-09-15 实测：输出与期望一致，`load_records("P0_km_20260907")` 重读得 `12 条 / dup=0 / malformed=0`（写盘无损）。
> 已知行为：转换器是 `append_records`（追加写），重复跑会留下同 `case_id` 的多条记录；`load_records` 按后写覆盖取唯一值，但 `duplicates` 计数会报出来。重跑前先删目录。

- [x] **Step 7.8: Commit**

```powershell
git add scripts/_convert_legacy_result.py core/triage.py tests/test_convert_legacy.py
git commit -m "feat(triage): 旧结果 JSON 转统一契约，并以历史产物做契约回归"
```

> 2026-09-15 提交时额外说明：commit message 带上了改测试期望的理由（见 Step 7.6 注与 Task 7 顶部四处修正）；本提交含 `core/triage.py`、`scripts/_convert_legacy_result.py`、`tests/test_convert_legacy.py`、本计划文档四个路径（仓库根临时探测文件已删，不入库）。


---

## Task 8: LLM 复判层（`agents/triage_agent.py`）

只处理规则层拿不准的语义判断（R7），并且**把人工清单喂给它**：`req_source` 指向的需求原文片段逐条附进输入包。沿用 `core/brain.py` 的 prompt/response 文件机制，不需 API Key。

> **2026-09-15 实施时修正五处**：
> 1. **补一个设计缺口：`PRODUCT_BUG_PROPOSAL` 原本会被丢弃**。本任务前的 `merge_decisions` 只看 `cat in CATEGORIES`，提案属「非 6 类」→ 连理由和 Bug 草稿一起被当噪声忽略，而提示词却向模型承诺「会被强制回落 NEEDS_HUMAN 并排队给人工门禁」。现新增 `rec["llm_proposal"]`（confidence/rationale/evidence_cited/bug_draft）保留提案，**仍强制回落 `NEEDS_HUMAN`**（铁律① 不破，只是不再白看一场），并补 2 个合并层测试。（该改动落在 Task 4 的 `merge_decisions`，Task 4 代码块不再同步，以本条为准。）
> 2. **`parse_llm_jsonl` 重写**。计划代码定义了 `_OBJ_RE` 并在注释里说「失败则用平衡括号再扫一次」，实际**根本没实现**（死代码）；按行 `json.loads` 遇 Qoder 常见形态（code fence 包裹 + 对象缩进成多行）会把整批结论读成 0 条，而「0 条」与「没有待复判用例」在日志里长得一模一样。现用带字符串/转义状态机的括号平衡扫描，`failed` 再用「问了几条 vs 解析出几条」反推截断。
> 3. **测试从 5 个增到 11 个**（新增 5 个 `parse_llm_jsonl` + 1 个需求 ID 混合场景）；计划里 `assert find_req_snippets("不存在的模块", "CAT-01") == {} or True` 是恒真断言（永不失败），改成有内容的断言。
> 4. **`review()` 两处留痕**：输入不干净（`dup`/`malformed` 非 0）写 `triage_errors.log`；LLM 漏答的 `case_id` 也记日志，否则人以为「AI 看过了、没问题」。
> 5. **实测 `reviewed=7`（计划写 6）**，因为 Task 7 已确认历史 pending 分流是 5/7；计划里的 `Select-String ... | Measure-Object` 核验改用进程内字符计数（PowerShell 中文控制台输出乱码，看不清匹配内容）。

**Files:**
- Create: `agents/triage_agent.py`、`agents/triage_prompt.md`
- Modify: `core/triage.py`（新增 `find_req_snippets`、`build_triage_payload`）
- Test: `tests/test_triage_agent_input.py`

- [x] **Step 8.1: 写失败测试**

Create `tests/test_triage_agent_input.py`:

```python
"""LLM 输入包质量：需求原文必须被引用进去（“把清单喂给 AI”），断言原文与现象齐备。"""
import json
from pathlib import Path

import pytest

from core import config
from core.triage import (apply_rule_layer, build_triage_payload, find_req_snippets,
                         load_records)

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def km_run(tmp_path, monkeypatch):
    """用旧数据转换器产出一个真 run（不用假数据测提示词）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_c", REPO / "scripts" / "_convert_legacy_result.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(config, "TRIAGE_DIR", tmp_path / "triage")
    records, rid = mod.convert(REPO / "qoder_workspace" / "test_result_P0_km_20260907.json")
    apply_rule_layer(records)
    return records, rid


def test_find_req_snippets_extracts_by_id():
    hits = find_req_snippets("知识管理", "CAT-01,CAT-04")
    assert set(hits) >= {"CAT-01", "CAT-04"}
    assert hits["CAT-01"].strip() and not hits["CAT-01"].startswith("|")


def test_find_req_snippets_survives_unknown_id():
    assert find_req_snippets("知识管理", "NOPE-99") == {}
    assert find_req_snippets("不存在的模块", "CAT-01") == {} or True   # 不抛异常


def test_payload_only_includes_rule_uncertain_cases(km_run):
    records, rid = km_run
    need = [r for r in records if r["triage"]["category"] == "NEEDS_HUMAN"]
    payload = build_triage_payload(rid, records)
    ids = {p["case_id"] for p in payload}
    assert ids == {r["case_id"] for r in need}          # 已定论的不送 LLM
    assert "TC-CAT-001" in ids


def test_payload_carries_assertion_text_and_requirement(km_run):
    records, rid = km_run
    payload = build_triage_payload(rid, records)
    one = next(p for p in payload if p["case_id"] == "TC-CAT-001")
    assert any(a["verdict"] == "fail" for a in one["assertions"])
    assert one["requirement"].get("CAT-01") or one["requirement"].get("CAT-04")
    assert one["rule_layer_excluded"]           # 已排除项必须告知，避免重复推理
    assert one["screenshots"]                    # 旧产物里本就带截图路径


def test_payload_is_json_serialisable(km_run):
    records, rid = km_run
    text = json.dumps(build_triage_payload(rid, records), ensure_ascii=False)
    assert "PRODUCT_BUG" not in text or True        # 允许出现在候选枚举说明里，不得出现在结论里
    assert len(text) < 200_000                      # 防止一条带大量 detail 的 case 撞爆上下文
```

- [x] **Step 8.2: 运行确认失败**

Run: `python -m pytest tests/test_triage_agent_input.py -v`
Expected: FAIL，`ImportError: cannot import name 'find_req_snippets'`

> 2026-09-15 实测：`ImportError: cannot import name 'build_triage_payload'`（收集阶段就失败，与计划同类）；实现输入层后 `6 passed / 5 failed`（失败项均为 `agents/triage_agent.py` 不存在）。

- [x] **Step 8.3: 实现需求抽取与输入包**

`core/triage.py` 顶部**无需再改 import**（Task 2 已统一用 `from core import config as _cfg`），本任务直接引用 `_cfg.SPLIT_REQUIREMENTS_DIR`。append 前先用 `Select-String -Pattern "SPLIT_REQUIREMENTS_DIR|find_module_file" -Path core/config.py` 确认这两个名字确实存在于 `core/config.py`。

Append to `core/triage.py`：

```python
# ── LLM 复判输入包 ────────────────────────────────────────
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


def build_triage_payload(rid: str, records: list, threshold: float = None) -> list:
    """只打包规则层未定论（NEEDS_HUMAN）的用例，逐条给出断言原文/现象/需求原文/已排除项。"""
    if threshold is None:
        from core.config import TRIAGE_CONF_THRESHOLD
        threshold = TRIAGE_CONF_THRESHOLD
    payload = []
    for rec in records:
        tri = rec.get("triage", {})
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
```

> `derived_status` 在 Task 4 已定义，本处直接复用，**不要重复定义**。

- [x] **Step 8.4: 运行确认通过**

Run: `python -m pytest tests/test_triage_agent_input.py -v`
Expected: PASS，`11 passed`（实施时由 5 个增到 11 个；输出解析部分需 Step 8.6 完成后才绿）

- [x] **Step 8.5: 写提示词模板**

Create `agents/triage_prompt.md`（用 `{{...}}` 占位符 + `str.replace`，**不走 `agent_loader.load_prompt`**：模板里含 JSON 字面花括号，`.format()` 会抛错）：

```markdown
# 测试失败复判任务（run: {{RUN_ID}}）

你是资深 Web 功能测试工程师。你的任务**不是**判断“测试能不能过”，而是对下列**规则层无法定论**的用例，
逐条判定失败归属于哪一类。规则层已经用可观测事实排除了一批选项，不得重复推理。

## 硬约束（违反即为错误输出）

1. **禁止新增或改写断言**。只能对给定断言下判定，不得自行发明“应该还要验证 X”。
2. 逐条必须引用证据：`evidence_cited` 里写明你依据的具体断言原文 / 需求编号 / 现象描述，不能只写“根据情势判断”。
3. 拿不准一律输出 `NEEDS_HUMAN`，**不准猜一个分类交差**；`confidence < {{THRESHOLD}}` 会被自动丢弃。
4. 你**不得**输出 `PRODUCT_BUG` 作为最终定性。即使你认为是真缺陷，也只能输出
   `verdict=PRODUCT_BUG_PROPOSAL`（提案），它会被强制回落 `NEEDS_HUMAN` 并排队给人工门禁。
   你的提案理由与 Bug 草稿会原样呈给人，因此 `rationale`、`evidence_cited`、`bug_draft` 必须写实。
   依据：无人工清单时各模型 F1 均 < 30%，有清单 49.2%。
5. 前置条件未建立（`precondition_met=false`）的用例，不得判真实缺陷，也不得判用例问题。
6. 步骤里有 `element_not_found` / `skipped` 时，优先考虑 `EXEC_INCOMPLETE`，不得归因于产品。
7. `requirement` 字段是需求原文片段，**只有它为空时才允许承认“无依据”**并输出 `NEEDS_HUMAN`；
   有原文而在文字上与之矛盾，请按第 4 条走提案，不要自己下最终结论。

## 可选结论（6 类，逐条选其一）

`CASE_DEFECT`（用例/断言自身问题，含幻觉断言）、`EXEC_INCOMPLETE`（步骤未执行到位）、
`ENV_BLOCK`（环境/服务/会话）、`DATA_PRECOND`（前置数据未备齐）、`NEEDS_HUMAN`（拿不准）、
`PRODUCT_BUG_PROPOSAL`（仅提案，需人拍板）。

## 待复判用例（JSON，共 {{N_CASES}} 条）

每条字段：`assertions`（断言原文与 verdict/reason）、`requirement`（需求编号→需求原文）、
`rule_layer_excluded`（规则层已排除项）、`steps`/`error`/`url_at_failure`/`screenshots`（现象）、
`existing_bug_draft`（执行者已留下的 Bug 草稿，可能为 null）。

```json
{{CASES_JSON}}
```

## 输出格式（严格 JSONL，每条用例一行，不要 code fence，不要多余文字）

```
{"case_id": "TC-XXX-000", "verdict": "CASE_DEFECT", "confidence": 0.85,
 "rationale": "一句话结论 + 为何不是其他类",
 "evidence_cited": ["断言原文：…", "需求 CAT-04：…"],
 "suggested_fix": "给用例作者的具体修改建议",
 "unblock_hint": "仅 ENV_BLOCK/DATA_PRECOND 必填：如何解除阻塞",
 "bug_draft": {"title": "", "severity": "S1|S2|S3|S4", "reproduce": [], "expected": "", "actual": ""}}
```

`verdict` 不是 `PRODUCT_BUG_PROPOSAL` 时，`bug_draft` 写 `null`。写完 {{N_CASES}} 行即停。
```

- [x] **Step 8.6: 写复判智能体**

Create `agents/triage_agent.py`：

```python
"""LLM 复判智能体 —— 把规则层拿不准的用例打包成清单，交给 Qoder 对话复判。

与同类智能体的差异：不走 `agent_loader.load_prompt`（模板含 JSON 字面花括号，`.format()`
会报错），而是直接读 `triage_prompt.md` 并用 `{{MARKER}}` 替换。AI 能力仍由 Qoder 对话提供，
本模块不需要 API Key。
"""
import json
import re
from datetime import datetime
from pathlib import Path

from core.brain import save_prompt, read_response
from core.config import TRIAGE_CONF_THRESHOLD
from core.triage import (append_error_log, append_llm_review, build_triage_payload,
                         load_records, run_dir)
from utils.logger import get_logger

logger = get_logger("triage_agent")
PROMPT_FILE = Path(__file__).parent / "triage_prompt.md"


class TriageAgent:
    """复判层：只处理规则层未定论的项，输出 `llm_review.jsonl`。"""

    def review(self, rid: str, dry_run: bool = False) -> dict:
        """返回 `{reviewed, parsed, raw_failed, prompt_path}`。`dry_run=True` 只出提示词不交互。"""
        records, dup, malformed = load_records(rid)
        payload = build_triage_payload(rid, records)
        if not payload:
            logger.info("[triage] 无规则层未定论用例，LLM 复判跳过")
            return {"reviewed": 0, "parsed": 0, "raw_failed": 0, "prompt_path": ""}
        prompt = self._render(rid, payload)
        task_name = f"triage_{rid}"
        prompt_path = save_prompt(task_name, prompt)
        if dry_run:
            logger.info(f"[triage] dry-run：仅生成提示词 {prompt_path}")
            return {"reviewed": len(payload), "parsed": 0, "raw_failed": 0,
                    "prompt_path": str(prompt_path)}
        response = read_response(task_name)
        items, failed_lines = parse_llm_jsonl(response)
        append_llm_review(rid, items)
        if failed_lines:
            (run_dir(rid) / "llm_raw").mkdir(parents=True, exist_ok=True)
            raw = run_dir(rid) / "llm_raw" / f"{datetime.now():%Y%m%d_%H%M%S}.md"
            raw.write_text(response, encoding="utf-8")
            append_error_log(rid, f"LLM 回复有 {failed_lines} 行无法解析，原文存：{raw}")
        return {"reviewed": len(payload), "parsed": len(items), "raw_failed": failed_lines,
                "prompt_path": str(prompt_path)}

    def _render(self, rid: str, payload: list) -> str:
        template = PROMPT_FILE.read_text(encoding="utf-8")
        cases_json = json.dumps(payload, ensure_ascii=False, indent=2)
        return (template.replace("{{RUN_ID}}", rid)
                .replace("{{THRESHOLD}}", str(TRIAGE_CONF_THRESHOLD))
                .replace("{{N_CASES}}", str(len(payload)))
                .replace("{{CASES_JSON}}", cases_json))


_CASE_ID_RE = re.compile(r'"case_id"\s*:')


def _iter_json_objects(text: str):
    """扫出括号平衡的顶层 JSON 对象（字符串内的花括号与转义不计入）。

    不能按行 `json.loads`：Qoder 常把 JSONL 包进 code fence，并把一个对象缩进成多行，
    逐行解析会把整批复判结论读成 0 条 —— 而 0 条看起来和「没有待复判用例」一模一样。
    """
    depth, start, in_str, esc = 0, None, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start:i + 1]
                start = None


def parse_llm_jsonl(text: str) -> tuple:
    """解析复判回复，返回 `(items, failed)`。`failed` 含截断对象与缺 `case_id` 的对象。"""
    text = text or ""
    items, broken = [], 0
    for chunk in _iter_json_objects(text):
        try:
            d = json.loads(chunk)
        except json.JSONDecodeError:
            broken += 1
            continue
        if isinstance(d, dict) and d.get("case_id"):
            items.append(d)
        else:
            broken += 1
    # 被截断的对象永远平衡不了、扫不出来，用「问了几条」反推漏了几条
    expected = len(_CASE_ID_RE.findall(text))
    return items, max(broken, expected - len(items))
```

> 2026-09-15 实施：本步代码块已同步为真实实现（原计划的按行解析 + 未被使用的 `_OBJ_RE` 已换为上述括号平衡扫描）；`TriageAgent.review()` 另加两处留痕（见上方修正④）。

- [x] **Step 8.7: 用真 run 验一遍提示词（不进入交互）**

Run: `python scripts/_convert_legacy_result.py`
Expected: 产出 `output/06_reports/triage/P0_km_20260907/records.jsonl`（若 Task 7 已跑则幂等，只追加）

> 2026-09-15 实测修正：**不幂等**。转换器走 `append_records`（追加写），重跑会留下同 `case_id` 的两份记录（`load_records` 取后写的，但 `duplicates` 会报 12）——重跑前先删 `records.jsonl`。本步骤验证时误跑了两次追加，恰好仍验证了 `review()` 的脏输入告警会落 `triage_errors.log`。

Run: `python -c "from core.triage import load_records, apply_rule_layer; r,_,_=load_records('P0_km_20260907'); apply_rule_layer(r); from core.triage import append_records; append_records(r,'P0_km_20260907'); from agents.triage_agent import TriageAgent; print(TriageAgent().review('P0_km_20260907', dry_run=True))"`
Expected: 打印 `{'reviewed': 7, 'parsed': 0, 'raw_failed': 0, 'prompt_path': 'ai_workspace\triage_P0_km_20260907_prompt.md'}`（计划原文写 6，因为 Task 7 已把 pending 分流定为 5/7）

> 2026-09-15 实测：用一次性脚本（已删）在进程内跑完「转换 → 规则层落盘 → dry-run」，得 `{'reviewed': 7, 'parsed': 0, 'raw_failed': 0, ...}`；提示词 8000 字符，`"requirement"` 出现 7 次（每条待复判用例都带上了需求字段），`PRODUCT_BUG_PROPOSAL` 3 次，`{{RUN_ID}}/{{THRESHOLD}}/{{N_CASES}}/{{CASES_JSON}}` 残留 0 个。
> 另：`save_prompt` 会把提示词复制到系统剪贴板（`core/brain.py` 既有行为，所有智能体共用），验证时会覆盖用户的剪贴板。

Run: `Select-String -Path ai_workspace/triage_P0_km_20260907_prompt.md -Pattern 'requirement|PRODUCT_BUG_PROPOSAL|禁止新增或改写断言' | Measure-Object | Select-Object Count`
Expected: `Count ≥ 6`

> 2026-09-15 实测：改用进程内 `text.count(...)` 统计（PowerShell 中文控制台输出乱码，看不清匹配内容），结论同上。

Run: `python -m pytest tests -v`
Expected: `62 passed`（Task 7 后 49 + 复判输入/解析 11 + 提案合并 2）

- [x] **Step 8.8: Commit**

```powershell
git add agents/triage_agent.py agents/triage_prompt.md core/triage.py tests/test_triage_agent_input.py
git commit -m "feat(triage): LLM 复判层，携需求原文清单只处理规则未定论项"
```

> 2026-09-15 提交：除上述四个路径，还含 `tests/test_triage_merge.py`（提案保留的 2 个测试）与本计划文档。`ai_workspace/triage_P0_km_20260907_prompt.md` 与 `output/06_reports/triage/**` 均为验证产物，不入库。

---

## Task 9: 人工门禁（`core/human_confirm.confirm_triage_decisions`）

分流铁律的落脚点：`PRODUCT_BUG` 定性与任何改判为 `BLOCKED` 必须由人拍板。沿用本文件已有的 `_safe_ask` 风格（EOF 安返默认值，CI 不崩）。

**Files:**
- Modify: `core/human_confirm.py`（顶部补 import、末尾新增门禁函数）
- Modify: `core/triage.py`（`merge_decisions` 收紧人工归属，见下方修正 ②③④）
- Test: `tests/test_human_gate.py`、`tests/test_triage_merge.py`（合并层 4 个回归测试）

> **实施时修正五处（2026-09-15）**：
> 1. **`pending` 口径太窄**：原计划只取 `category == "NEEDS_HUMAN"`，于是 `_q_eligible()`（要求 `source == "llm"`）、`overridden`、quarantine（专收被人工推翻的 LLM 结论）三条链路永远拿不到数据 —— LLM 高置信改判的项既不进门禁也不被批量接受，等于静默放行。改为抽 `_needs_human()`：`NEEDS_HUMAN` **或** `source == "llm"`。
> 2. **CI 伪人证**：CI 预写的 `decisions.yaml` 会被 `merge_decisions` 当成人工裁决（`source=human`、`needs_reconfirm=False`），`confirmed_by_human: False` 形同虚设。合并层收紧为：**所有**人工归属都必须 `confirmed_by_human is True`。
> 3. **收紧的反噬**：只在 `PRODUCT_BUG` 分支要求确认、其余落到 `else` 强行 `tri.update(NEEDS_HUMAN)`，则 CI 预写一条就把整批 LLM 结论打回待裁决（信息净损失）。`else` 改为「只标注未采纳，不改类别」。
> 4. **人工 `unblock_hint` 未被接住**：门禁要求 `[skip]`/`[env]`/`[data]` 必填解除路径，但合并层原来不读它 → 人刚标的阻塞被「BLOCKED 缺 hint 降级」那一判退回自己的结论。human 分支带下 `unblock_hint`。
> 5. **计划自带测试有两处必败缺陷**（是计划的问题，不是实现的）：`return "q" if not calls else default` 因先 `append` 恒为 `False`，永不返回 `q` → 改 `len(calls) == 1`；`TC-004` 沿用默认 rationale「R7：疑似真实缺陷」会被 `_suggest_category` 判成 `PRODUCT_BUG` 而永远 `_q_eligible` 不通过 → 换成 LLM 风格 rationale。

- [x] **Step 9.1: 写失败测试**

Create `tests/test_human_gate.py`:

```python
"""人工门禁：定性必须出自人、`[q]` 不得成为逃分母的后门、CI 不得阻塞流水线。"""
import copy

import pytest

from core import config
from core.human_confirm import confirm_triage_decisions
from core.triage import evaluate_gate, load_decisions, merge_decisions, new_record, save_decisions


BASE = new_record(run_id="r", case_id="TC-0", module="知识管理")


def _rec(cid, **tri):
    r = copy.deepcopy(BASE)
    r["case_id"] = cid
    r["name"] = f"用例 {cid}"
    r["status"] = "fail"
    r["triage"] = {**r["triage"], **{"category": "NEEDS_HUMAN", "source": "rule",
                                     "confidence": 0.0, "rationale": "R7：疑似真实缺陷",
                                     "suggested_action": "", "unblock_hint": ""}, **tri}
    return r


@pytest.fixture(autouse=True)
def _triage_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRIAGE_DIR", tmp_path / "triage")


def _answers(seq):
    """按顺序弹出预设回答（同时覆盖选项题与自由输入题）。"""
    it = iter(seq)
    return lambda *a, **kw: next(it)


def test_human_can_confirm_product_bug(monkeypatch):
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    monkeypatch.setattr("core.human_confirm._safe_ask", _answers(["bug"]))
    monkeypatch.setattr("core.human_confirm._safe_ask_text", _answers(["S2", "名称被静默过滤"]))
    merged = {"TC-001": _rec("TC-001")}
    decisions = confirm_triage_decisions("r1", merged)
    assert decisions["TC-001"]["final_category"] == "PRODUCT_BUG"
    assert decisions["TC-001"]["confirmed_by_human"] is True
    remerged = merge_decisions(list(merged.values()), {}, decisions)
    assert remerged["TC-001"]["triage"]["category"] == "PRODUCT_BUG"   # 人拍板后铁律放行
    assert remerged["TC-001"]["triage"]["decided_by"]


def test_human_decisions_are_persisted(monkeypatch):
    """返回值不算证据：人工裁决必须落 `decisions.yaml`，否则重跑一次就丢了。"""
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    monkeypatch.setattr("core.human_confirm._safe_ask", _answers(["case"]))
    monkeypatch.setattr("core.human_confirm._safe_ask_text", _answers([""]))
    confirm_triage_decisions("r6", {"TC-006": _rec("TC-006")})
    back = load_decisions("r6")
    assert back["TC-006"]["final_category"] == "CASE_DEFECT"
    assert back["TC-006"]["confirmed_by_human"] is True


def test_ci_mode_never_blocks_but_marks_unconfirmed(monkeypatch):
    monkeypatch.setattr(config, "HUMAN_CONFIRM", False)
    merged = {"TC-002": _rec("TC-002")}
    decisions = confirm_triage_decisions("r2", merged)     # 不得调用任何 input
    assert decisions["TC-002"]["confirmed_by_human"] is False
    remerged = merge_decisions(list(merged.values()), {}, decisions)
    assert remerged["TC-002"]["triage"]["category"] == "NEEDS_HUMAN"
    assert remerged["TC-002"]["needs_reconfirm"] is True
    gate = evaluate_gate(remerged, mode="report_only")
    assert gate["verdict"] == "na" and gate["blocks_exit_code"] is False


def test_quick_accept_cannot_qualify_bug_or_block(monkeypatch):
    """`[q]` 只批量接受 LLM 高置信且非 PRODUCT_BUG/BLOCKED 的项。"""
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    calls = []

    def ask(prompt_text, choices, default):
        calls.append(default)
        return "q" if len(calls) == 1 else default       # 首轮走 [q]，剩余项按默认值逐条走

    monkeypatch.setattr("core.human_confirm._safe_ask", ask)
    monkeypatch.setattr("core.human_confirm._safe_ask_text", lambda *a, **k: "")
    merged = {
        "TC-003": _rec("TC-003", category="CASE_DEFECT", source="llm", confidence=0.9,
                       rationale="铁律：llm 层拒绝定性 PRODUCT_BUG（分流铁律）"),   # 含铁律字样
        "TC-004": _rec("TC-004", category="CASE_DEFECT", source="llm", confidence=0.9,
                       rationale="断言与需求无关，建议重写"),
    }
    decisions = confirm_triage_decisions("r3", merged)
    assert decisions["TC-004"]["final_category"] == "CASE_DEFECT"
    assert "TC-003" not in decisions                      # 铁律拒绝项不得被 q 扫掉，得继续挂待裁决


def test_blocked_choice_requires_hint(monkeypatch):
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    monkeypatch.setattr("core.human_confirm._safe_ask", _answers(["skip"]))
    monkeypatch.setattr("core.human_confirm._safe_ask_text", _answers([""]))   # 空 hint
    merged = {"TC-005": _rec("TC-005")}
    decisions = confirm_triage_decisions("r4", merged)
    assert "TC-005" not in decisions                      # 未说明解除路径 → 不收，继续挂待裁决


def test_llm_conclusion_is_reconfirmed_and_overridable(monkeypatch):
    """LLM 改判过的项必须进门禁；人推翻后 `overridden` 才会为 quarantine 提供数据。"""
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    monkeypatch.setattr("core.human_confirm._safe_ask", _answers(["env"]))
    monkeypatch.setattr("core.human_confirm._safe_ask_text", _answers(["重启网关后重跑"]))
    merged = {"TC-009": _rec("TC-009", category="CASE_DEFECT", source="llm", confidence=0.9,
                             rationale="断言与需求无关")}
    decisions = confirm_triage_decisions("r9", merged)
    assert decisions["TC-009"]["final_category"] == "ENV_BLOCK"
    remerged = merge_decisions(list(merged.values()), {}, decisions)["TC-009"]
    assert remerged["triage"]["category"] == "ENV_BLOCK"
    assert remerged["triage"]["overridden"] is True
    assert remerged["triage"]["unblock_hint"] == "重启网关后重跑"


def test_edit_with_illegal_category_is_not_recorded(monkeypatch):
    """自写结论拼错类别时不得静默当成某一类收下。"""
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    monkeypatch.setattr("core.human_confirm._safe_ask", _answers(["edit"]))
    monkeypatch.setattr("core.human_confirm._safe_ask_text", _answers(["PRODUCT-PENDING"]))
    decisions = confirm_triage_decisions("r7", {"TC-007": _rec("TC-007")})
    assert decisions == {}


def test_no_pending_case_returns_empty(monkeypatch):
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    merged = {"TC-008": _rec("TC-008", category="OK", source="rule", confidence=1.0,
                             rationale="R0：确认通过")}
    assert confirm_triage_decisions("r8", merged) == {}
```

> 原计划的 `test_decisions_roundtrip_via_yaml`（纯 `save_decisions`/`load_decisions` 往返）不依赖门禁，已由 `test_human_decisions_are_persisted` 与 `tests/test_triage_merge.py` 的 YAML 回读测试覆盖，此处以门禁行为测试替换。

- [x] **Step 9.2: 运行确认失败**

Run: `python -m pytest tests/test_human_gate.py -v`
Expected: FAIL，`ImportError: cannot import name 'confirm_triage_decisions'`（实测如此）

- [x] **Step 9.3: 实现门禁**

Modify `core/human_confirm.py` 顶部（`console = Console()` 之后）加：

```python
from datetime import datetime

from core import config as _cfg          # 取属性而非导入值：保证测试可 monkeypatch、运行时读最新值
from core.triage import CATEGORIES, save_decisions

_CATEGORY_BY_CHOICE = {"bug": "PRODUCT_BUG", "case": "CASE_DEFECT", "env": "ENV_BLOCK",
                       "data": "DATA_PRECOND", "exec": "EXEC_INCOMPLETE"}
```

在文件末尾新增：

```python
def _safe_ask_text(prompt_text, default=""):
    """自由文本输入的安全版（`_safe_ask` 只管选项题）。EOF 时返回 default。"""
    try:
        return Prompt.ask(prompt_text, default=default).strip()
    except EOFError:
        console.print("  [dim]（非交互环境，自动填入默认值）[/dim]")   # 无占位符，不加 f 前缀
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
            save_decisions(run_id, decisions)   # 空集不写盘：不留下一个空 YAML 让人误以为「已裁决过」
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
```

- [x] **Step 9.4: 运行确认通过**

Run: `python -m pytest tests/test_human_gate.py -v`
Expected: PASS，`8 passed`（计划原写 `5 passed`；实施时删 1 个不依赖门禁的往返测试、加 4 个门禁行为测试）

> 若 `test_quick_accept_cannot_qualify_bug_or_block` 失败，检查 `_q_eligible` 是否错误地把「含铁律字样的 rationale」归为可批量接受 —— 这正是本测试要守的门禁。**不要为了让测试通过而放宽 `_q_eligible`。**

Run: `python -m pytest tests -v`
Expected: `74 passed`（Task 8 后 62 + 门禁 8 + 合并层新增 4）

真 run 冒烟（`P0_km_20260907`，`HUMAN_CONFIRM=False`，验证后已删临时脚本与 `decisions.yaml`）：

| 项 | 实测 |
| --- | --- |
| 输入 | `records=12 dup=0 malformed=0` |
| pending / CI 落库 | `decisions=7`（全部 `source=rule` 的 NEEDS_HUMAN；无 LLM 复判产物可加，故 0 条被 `continue` 跳过） |
| 8 段摘要 before / after | 完全一致（`数据前置未满足=5 / 待人工裁决=7 / 移出分母=5`）——证明 CI 预写的建议确实未改变任何结论 |
| `decisions.yaml` 回读 | `confirmed_by_human: False` 为**布尔**而非字符串，`final_category` 仅 `NEEDS_HUMAN`（R7 建议被降级，未写 PRODUCT_BUG） |

- [x] **Step 9.5: Commit**

```powershell
git add core/human_confirm.py core/triage.py tests/test_human_gate.py tests/test_triage_merge.py \
        docs/superpowers/plans/2026-09-14-result-triage.md
git commit -m "feat(triage): 人工裁决门禁，[q] 限定 LLM 高置信且不定性"
```

> 2026-09-15 提交：除 `core/human_confirm.py`、`tests/test_human_gate.py`，还必须带 `core/triage.py`（修正 ②③④ 均在此）与 `tests/test_triage_merge.py`（这 3 个修正各有一个回归测试），否则单提门禁文件会得到一个「测试全红」的提交。

---

## Task 10: 分流产物（待裁决清单 / 修复清单 / Bug 草稿 / quarantine）

把三层结论落成可交接的文件：人能勾的清单、回灌设计阶段的修复清单、Bug 草稿、线 2 隔离名单。

**Files:**
- Modify: `core/triage.py`（新增 `md_escape` / `write_pending_review` / `collect_fix_list` / `write_fix_list` / `write_bug_drafts` / `write_artifacts`；`write_quarantine` 已在 Task 6 存在）
- Modify: `core/triage.py:merge_decisions`（人工 `severity` 接住，供 Bug 草稿栏使用）
- Test: `tests/test_triage_merge.py`（追加 4 个产物测试）

> **实施时修正五处（2026-09-15）**：
> 1. **计划自相矛盾：`write_fix_list` 与它的测试打架**。计划代码把四组（含环境阻塞/数据前置）全写进 `triage_用例修复清单.md`，而测试断言 `"TC-103" not in fix`。按测试的意图实现：修复清单只写 `用例问题` + `执行未到位` 两组，环境/数据前置在清单末尾以一行计数指引到报告 BLOCKED 表。**理由**：把阻塞项混进「用例修复清单」会诱导人对着环境问题改用例。
> 2. **人给的严重程度会被丢在 `decisions.yaml` 里**：门禁为 `[bug]` 收了 `severity`，但 `merge_decisions` 不往下传 → Bug 草稿的严重程度永远是「待定」。合并层 human/PRODUCT_BUG 分支补 `severity`。
> 3. **`bug_draft` 只读一个位置会掉草稿**：人确认的 PRODUCT_BUG 往往没有 `rec["bug_draft"]`（Task 8 把 LLM 的草稿存在 `rec["llm_proposal"]["bug_draft"]`）→ 抽 `_bug_draft_of()` 回落到 LLM 提案草稿。铁律约束的是「谁来定性」，不是「谁来打草稿」。
> 4. **草稿编号会跳号**：计划用 `enumerate(sorted(merged.items()))`，被 `continue` 跳过的项也占号（出现孤立的 `BUG-GEN-03`）→ 改为只给真正写出的草稿计数。
> 5. **测试写法统一**：计划测试里逐个重建 `tmp_path + monkeypatch`，本文件已有 `rid` fixture（作用相同）→ 四个测试均直接用 `rid`；`write_artifacts` 放到文件顶部的统一 import 块里，不在函数内局部导入。
> 6. **（Task 11 回头改的）`_md_escape` 改名为公开的 `md_escape`**：报告层要拿它转义表格单元，跨模块 `import` 一个下划线开头的名字等于把私有实现当 API 用；现在两侧都读同一个函数，表格转义只有一份口径。

- [x] **Step 10.1: 追加失败测试**

Append to `tests/test_triage_merge.py`（并把顶部 import 块加上 `json` 与 `write_artifacts`）:

```python
# ── 分流产物：文件即状态，下一阶段只读文件，中断了也不丢 ──────────────
def test_write_artifacts_produces_handoff_files(rid):
    """待裁决清单/修复清单/quarantine 三件套必须落盘；环境阻塞不进「用例修复清单」。"""
    recs = [_rec("TC-100", triage={"category": "NEEDS_HUMAN", "source": "rule"}),
            _rec("TC-101", triage={"category": "CASE_DEFECT", "source": "rule", "confidence": 0.9,
                                   "suggested_action": "重写断言"}),
            _rec("TC-102", triage={"category": "EXEC_INCOMPLETE", "source": "llm", "confidence": 0.8,
                                   "suggested_action": "补图标定位器"}),
            _rec("TC-103", triage={"category": "ENV_BLOCK", "source": "rule", "confidence": 0.9,
                                   "unblock_hint": "起服务"})]
    merged = merge_decisions(recs, {}, {})
    out = write_artifacts(rid, merged, compute_summary(merged), duplicates=1, malformed=0,
                          mode="report_only")
    for name in ("pending_review", "fix_list", "quarantine"):
        assert out[name].exists() and out[name].read_text(encoding="utf-8").strip()
    text = out["pending_review"].read_text(encoding="utf-8")
    assert "TC-100" in text and "unblock_hint" in text
    fix = out["fix_list"].read_text(encoding="utf-8")
    assert "TC-101" in fix and "TC-102" in fix          # 用例问题与执行未到位都进修复清单
    assert "TC-103" not in fix                          # 环境阻塞不是「用例该修」的东西，进报告 BLOCKED 表
    assert json.loads(out["gate"].read_text(encoding="utf-8"))["mode"] == "report_only"


def test_bug_draft_needs_human_confirm_but_reuses_llm_draft(rid):
    """人只负责拍板定性（含严重程度），草稿正文允许沿用 LLM 写的，否则人还得重打一遍。"""
    recs = [_rec("TC-110", triage={"category": "NEEDS_HUMAN", "source": "rule"}),
            _rec("TC-111", triage={"category": "PRODUCT_BUG", "source": "llm", "confidence": 0.95})]
    recs[0]["module"] = recs[1]["module"] = "分类管理"
    llm = {"TC-110": {"verdict": "PRODUCT_BUG_PROPOSAL", "confidence": 0.9,
                      "rationale": "断言 2 与需求冲突",
                      "bug_draft": {"title": "名称被静默过滤", "expected": "提示不合规",
                                    "req_source": "CAT-04"}}}
    human = {"TC-110": {"final_category": "PRODUCT_BUG", "confirmed_by_human": True,
                        "decided_by": "tester", "severity": "S1", "note": "复现稳定"}}
    merged = merge_decisions(recs, llm, human)
    out = write_artifacts(rid, merged, compute_summary(merged), 0, 0, "strict")
    drafts = sorted((run_dir(rid) / "bug_drafts").glob("*.md"))
    assert len(drafts) == 1                             # TC-111 被铁律拒收 → 不出草稿
    body = drafts[0].read_text(encoding="utf-8")
    assert "名称被静默过滤" in body and "S1" in body and "TC-110" in body and "CAT-04" in body
    assert "人工确认" in body
    assert out["bug_drafts"] == drafts


def test_quarantine_lists_only_overridden_mcp_cases(rid):
    a = _rec("TC-120", triage={"category": "CASE_DEFECT", "source": "human", "confidence": 1.0,
                               "overridden": True, "decided_by": "tester"})
    a["executor"] = "qoder_mcp"
    b = _rec("TC-121", triage={"category": "CASE_DEFECT", "source": "human", "confidence": 1.0,
                               "overridden": True})
    b["executor"] = "playwright_script"
    merged = merge_decisions([a, b], {}, {})
    out = write_artifacts(rid, merged, compute_summary(merged), 0, 0, "strict")
    text = out["quarantine"].read_text(encoding="utf-8")
    assert "TC-120" in text and "TC-121" not in text


def test_write_artifacts_on_clean_run_still_leaves_files(rid):
    """全通过的 run 也要有一整套产物：下游按固定文件名取用，不该判断「这次有没有」。"""
    recs = [_rec("TC-130", status="pass",
                 triage={"category": "OK", "source": "rule", "confidence": 1.0})]
    out = write_artifacts(rid, merge_decisions(recs, {}, {}),
                          compute_summary({"x": recs[0]}), 0, 0, "strict")
    assert out["bug_drafts"] == []
    text = out["pending_review"].read_text(encoding="utf-8")
    assert "TC-130" not in text and "0 项" in text
    assert json.loads(out["gate"].read_text(encoding="utf-8"))["gate"]["verdict"] == "allow"
```

> 与计划的差异：原 `test_bug_draft_only_written_for_human_confirmed_bug` 直接手工造一个 `source=human` 的记录，只能证明「产物写得出」；换上来的版本走 `merge_decisions(recs, llm, human)` 全链路，同时守住三件事：铁律拒收的 LLM 定性不出草稿、人工 `severity` 能进草稿、LLM 提案草稿不被丢。另加一个空跑（clean run）守「文件名固定」约定。

- [x] **Step 10.2: 运行确认失败**

Run: `python -m pytest tests/test_triage_merge.py -v -k artifacts`
Expected: FAIL，`ImportError: cannot import name 'write_artifacts'`（实测：因为导入在文件顶部，整个文件 collection error，比计划预期更红）

- [x] **Step 10.3: 实现产物输出**

Append to `core/triage.py`：

```python
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


def write_bug_drafts(rid: str, merged: dict) -> list:
    """只为**已经人工确认**的 `PRODUCT_BUG` 出草稿（铁律）；不同步 Jira/GitHub，只出 Markdown。"""
    paths = []
    out_dir = run_dir(rid) / "bug_drafts"
    for cid, r in sorted(merged.items()):
        tri = r["triage"]
        if tri.get("category") != "PRODUCT_BUG" or tri.get("source") != "human":
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
            f"| 分流结论 | PRODUCT_BUG（人工确认：{tri.get('decided_by', '')} "
            f"{tri.get('decided_at', '')}）|",
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
```

> 键名约定：`write_artifacts` 返回的是**不带后缀的逻辑键**（`pending_review` / `fix_list` / `quarantine` / `gate` / `bug_drafts`），值是 `Path`。文件名带不带 `.md`、是中文还是英文属实现细节，调用方（`run.py triage`、报告层）只按逻辑键取用，日后改名不波及下游。

- [x] **Step 10.4: 运行确认通过**

Run: `python -m pytest tests/test_triage_merge.py -v`
Expected: PASS，`28 passed`（计划原写 `15 passed`，那是 Task 8/9 已先后追加合并层测试前的基数）

Run: `python -m pytest tests -v`
Expected: `78 passed`

真 run 产物核验（用 Task 7 的 `P0_km_20260907/records.jsonl`，12 条；验证后产物与临时脚本已删，以免与 Task 11 的真实产物混淆）：

| 产物 | 实测 |
| --- | --- |
| `pending_review.md` | 7 行待裁决（R7×1 + R8×6），含「LLM 提案」列（无复判产物时为 `—`）与 `☐exec` 选项 |
| `triage_用例修复清单.md` | 用例问题 0 / 执行未到位 0，尾行「另有 5 条属环境/数据前置…」与摘要 `移出分母=5` 对得上 |
| `quarantine.md` | 条目 0（CI 未裁决 → 无人工推翻） |
| `gate.json` | `mode=report_only`、`verdict=na`、`pending=7`、`bugs=[]`，`summary` 与 Task 7 基线逐项一致 |
| `bug_drafts/` | 未创建（无人工确认的 PRODUCT_BUG），`out["bug_drafts"] == []` |

> 旧数据里的 6 条 R8 记录 **用例名称为空**（`P0_km_20260907.json` 本身就没存 name），清单里只能靠 Case ID 追溯 —— 属数据源限制，不改分流层。

- [x] **Step 10.5: Commit**

```powershell
git add core/triage.py tests/test_triage_merge.py
git commit -m "feat(triage): 分流产物（待裁决清单/修复清单/Bug 草稿/quarantine/gate）"
```

> 2026-09-15 提交：本任务不动 `core/human_confirm.py`；但 `core/triage.py` 里带了 Task 9 漏下的一条 `severity` 传递（属本任务产物才能观测到，改在此、测也在此）。

---

## Task 11: 报告层接入Ⅰ——`build_from_records()` 与分流版 Markdown

报告层**只呈现结论、不二次判定**：全部判定逻辑在 `core/triage.py`，避免两套口径。本任务只让 **Markdown** 吃到分流；HTML / Excel 在 Task 12 接入，`run.py triage` 在 Task 13 才 wired，所以中间态不影响任何现有命令。

**Files:**
- Modify: `exporters/report_exporter.py:15`（import 改运行时取属性）、`:83-97`（`build_and_save` 目录/格式改读 `_cfg`）、新增 `build_from_records()` / `_save_md_triage()` / `_print_summary_triage()`
- Modify: `core/triage.py`（`_md_escape` → `md_escape`、`_BLOCKED_CATEGORIES` → `BLOCKED_CATEGORIES`，都是为了给报告层复用，不改判定逻辑）
- Test: `tests/test_report_triage.py`

- [x] **Step 11.1: 写失败测试**

Create `tests/test_report_triage.py`：

```python
"""分流结论进报告：8 段摘要、有效通过率、BLOCKED 独立表、发版建议、旧路径不变。"""
import json

import pytest

from core import config
from core.triage import append_records, new_record
from exporters.report_exporter import ReportExporter


def _rec(rid, cid, **kw):
    r = new_record(run_id=rid, case_id=cid, module="知识管理")
    r["name"] = kw.pop("name", f"用例{cid}")
    r["status"] = kw.pop("status", "fail")
    tri = kw.pop("triage", None)
    if tri is not None:
        r["triage"].update(tri)
    r.update(kw)
    return r


@pytest.fixture
def env(tmp_path, monkeypatch):
    """隔离目录与格式：不依赖真实 `output/`。"""
    monkeypatch.setattr(config, "TRIAGE_DIR", tmp_path / "triage")
    monkeypatch.setattr(config, "MD_REPORTS_DIR", tmp_path / "md")
    monkeypatch.setattr(config, "HTML_REPORTS_DIR", tmp_path / "html")
    monkeypatch.setattr(config, "EXCEL_REPORTS_DIR", tmp_path / "xlsx")
    monkeypatch.setattr(config, "REPORT_FORMAT", ["md"])
    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    return tmp_path


def _seed(rid="R1"):
    """4 条覆盖四类终态：OK / ENV_BLOCK / DATA_PRECOND / R7→NEEDS_HUMAN。"""
    append_records([
        _rec(rid, "TC-001", status="pass",
             steps=[{"order": 1, "action": "点击新建", "outcome": "ok", "detail": ""}],
             assertions=[{"text": "弹窗关闭", "verdict": "pass", "reason": "", "evidence_refs": []}]),
        _rec(rid, "TC-002", status="error", error="net::ERR_CONNECTION_REFUSED",
             triage={"category": "ENV_BLOCK", "source": "rule", "confidence": 0.9,
                     "unblock_hint": "起本地服务后整 run 重跑"}),
        _rec(rid, "TC-003", status="fail", precondition_met=False,
             test_data="上传文件：test.doc",
             triage={"category": "DATA_PRECOND", "source": "rule", "confidence": 0.9,
                     "unblock_hint": "准备 test.doc 后重跑"}),
        _rec(rid, "TC-004", status="fail",
             assertions=[{"text": "分类树出现新分类", "verdict": "fail", "reason": "",
                          "evidence_refs": []}]),
    ], rid)
    return rid


def _read_md(tmp_path):
    files = sorted((tmp_path / "md").glob("*.md"))
    assert files, "未生成 Markdown 报告"
    return files[-1].read_text(encoding="utf-8")


def test_summary_counts_and_effective_rate(env):
    report = ReportExporter().build_from_records(_seed(), mode="strict")
    s = report["summary"]
    assert (s["总用例"], s["通过"], s["环境阻塞"], s["数据前置未满足"], s["待人工裁决"]) == (4, 1, 1, 1, 1)
    assert s["移出分母"] == 2 and s["其他异常"] == 0
    assert s["有效通过率"] == round(1 / 2 * 100, 1)      # 1 / (4 - 1 - 1)
    assert s["通过率"] == round(1 / 4 * 100, 1)          # 旧口径仍保留、并列展示
    buckets = ("通过", "真实缺陷", "环境阻塞", "数据前置未满足", "用例问题",
               "执行未到位", "待人工裁决", "其他异常")
    assert sum(s[k] for k in buckets) == s["总用例"]      # 自检不变量


def test_md_has_effective_rate_blocked_table_and_triage_columns(env):
    _seed()
    ReportExporter().build_from_records("R1", mode="strict")
    md = _read_md(env)
    assert "## 摘要（8 段）" in md and "**有效通过率**" in md
    assert "| 分流类别 | 判定来源 | 置信度 | 裁决人 |" in md
    assert "## BLOCKED" in md and "起本地服务后整 run 重跑" in md    # 解除方式逐条列明
    assert "待人工裁决" in md and "TC-004" in md
    assert "分类树出现新分类" in md                                  # 断言原文仍可查


def test_strict_gate_rejects_release_advice_when_pending(env):
    _seed()
    report = ReportExporter().build_from_records("R1", mode="strict")
    assert report["gate"]["verdict"] == "reject" and report["gate"]["blocks_exit_code"]
    assert "不具备出结论条件" in _read_md(env)


def test_report_only_mode_writes_na_not_reject(env):
    _seed()
    report = ReportExporter().build_from_records("R1", mode="report_only")
    assert report["gate"]["verdict"] == "na" and not report["gate"]["blocks_exit_code"]
    md = _read_md(env)
    assert "N/A" in md and "浅分流" in md and "❌" not in md


def test_mode_defaults_from_human_confirm(env, monkeypatch):
    _seed()
    exporter = ReportExporter()
    assert exporter.build_from_records("R1")["mode"] == "strict"      # HUMAN_CONFIRM=True
    monkeypatch.setattr(config, "HUMAN_CONFIRM", False)
    assert exporter.build_from_records("R1")["mode"] == "report_only"  # CI 语义自动推得


def test_unknown_category_lands_in_other_bucket_not_dropped(env):
    """非法类别直写 jsonl（绕过 `append_records` 校验）时必须现形，不能静默消失。"""
    d = config.TRIAGE_DIR / "R9"
    d.mkdir(parents=True)
    rec = _rec("R9", "TC-901", status="fail", triage={"category": "WEIRD", "source": "rule"})
    (d / "records.jsonl").write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
    s = ReportExporter().build_from_records("R9", mode="strict")["summary"]
    assert s["总用例"] == 1 and s["其他异常"] == 1
    assert "⚠️" in _read_md(env)


def test_blocked_table_follows_triage_category_not_raw_status(env):
    """BLOCKED 表必须与摘要的类别桶同一口径（真跑历史 run 时踩到的）。

    历史数据里原始 `status=blocked` 的用例远多于真正判为阻塞的：它们因未说明阻塞原因
    落入 NEEDS_HUMAN。若表按原始 status 取数，就会出现「摘要 5 条阻塞、表里 11 行」，
    读者不知道哪些才是真的逃出了有效分母。
    """
    append_records([
        _rec("RB", "TC-B1", status="blocked",
             triage={"category": "ENV_BLOCK", "source": "rule", "confidence": 0.9,
                     "unblock_hint": "起本地服务后重跑"}),
        _rec("RB", "TC-B2", status="blocked"),      # 只写了 blocked、未说明原因 → R8 送人工
    ], "RB")
    report = ReportExporter().build_from_records("RB", mode="strict")
    assert report["summary"]["环境阻塞"] == 1 and report["summary"]["待人工裁决"] == 1
    assert [d["id"] for d in report["blocked"]] == ["TC-B1"]
    md = _read_md(env)
    table = md.split("## BLOCKED")[1].split("## 待人工裁决")[0]
    assert "TC-B1" in table and "TC-B2" not in table
    # 结论列也不能自相矛盾：一条同时写 BLOCKED 与 待人工裁决 的行，人不知道先处理哪个
    assert "### [待人工裁决] [TC-B2]" in md


def test_suite_name_is_majority_module_not_first(env):
    """报告标题取多数模块（真跑历史 run 时踩到的）。

    `P0_km_20260907` 的 12 条里 11 条属知识管理、1 条属分类管理，而分类管理那条恰好
    Case ID 排序靠首。取首条会让整份报告改名，人拿文件时会误以为拿错了模块。
    """
    append_records([
        _rec("RM", "TC-CAT-001", module="分类管理"),
        _rec("RM", "TC-KM-001", module="知识管理"),
        _rec("RM", "TC-KM-002", module="知识管理"),
    ], "RM")
    report = ReportExporter().build_from_records("RM", mode="report_only")
    assert report["suite_name"] == "知识管理"


def test_blank_case_name_is_marked_not_left_empty(env):
    """历史 JSON 的 `pending_cases` 只存 case_id + blocker，名称必为空。

    空单元格会让人以为是报告渲染坏了（或直接误读成「这条用例没名字」），必须显式标出来。
    """
    append_records([_rec("RN", "TC-N01", name="", status="blocked")], "RN")
    ReportExporter().build_from_records("RN", mode="strict")
    assert "（名称未记录" in _read_md(env)


def test_missing_run_raises_clearly(env):
    with pytest.raises(FileNotFoundError) as e:
        ReportExporter().build_from_records("nope")
    assert "records.jsonl" in str(e.value)


def test_legacy_build_and_save_still_four_state(env):
    """旧路径一行结论不得变：`TRIAGE_ENABLED=false` 时走的就是它。"""
    rows = [{"id": "TC-001", "name": "n", "module": "m", "case_type": "正向", "priority": "P0",
             "status": "pass", "duration": 1.0, "steps": "1. a", "expected": "1. b",
             "assertions": [{"text": "t", "passed": True}]}]
    ReportExporter().build_and_save("知识管理", rows)
    md = _read_md(env)
    assert "| Passed | 1 |" in md and "分流类别" not in md and "摘要（8 段）" not in md
```

- [x] **Step 11.2: 运行确认失败**

Run: `python -m pytest tests/test_report_triage.py -v`
Expected: FAIL，`AttributeError: 'ReportExporter' object has no attribute 'build_from_records'`（部分用例会是 `monkeypatching attribute TRIAGE_DIR / MD_REPORTS_DIR 无效`，Step 11.3 修的就是这个）

实测：`7 failed, 1 passed`。7 个全为 `AttributeError`；`test_legacy_build_and_save_still_four_state` 也失败，原因正是预期中的那一条——旧 `build_and_save` 用模块级常量，`monkeypatch` 不生效，**于是它把真实 MD/Excel 写进了 `output/06_reports/`**（事后手工删了 `20260915_121916_知识管理.xlsx`）。该残留从 Step 11.3 起消失。

- [x] **Step 11.3: 目录常量改为运行时取属性（旧行为不变）**

`exporters/report_exporter.py:15` 整行替换：

```python
from core import config as _cfg   # 取属性而非导入值：运行时读最新配置，测试可 monkeypatch 隔离目录
from core.triage import BLOCKED_CATEGORIES   # BLOCKED 只按分流类别认定，与摘要同一口径
```

（原行：`from core.config import MD_REPORTS_DIR, HTML_REPORTS_DIR, EXCEL_REPORTS_DIR, REPORT_FORMAT`）

> `BLOCKED_CATEGORIES` 本步就引入：报告层需要与 `merge_decisions` / `evaluate_gate` 同一套「什么算阻塞」的定义，不能让报告自己再列一份元组。

把 `build_and_save` 内 `:83-97` 的目录与格式引用换为运行时局部变量（其余逻辑一字不改）：

```python
        # 报告直接放到对应格式目录下，不创建模块子目录
        # 确保目录存在（配置在运行时读，便于测试隔离与改配置后不重启生效）
        md_dir, html_dir, excel_dir = _cfg.MD_REPORTS_DIR, _cfg.HTML_REPORTS_DIR, _cfg.EXCEL_REPORTS_DIR
        for d in (md_dir, html_dir, excel_dir):
            d.mkdir(parents=True, exist_ok=True)
```

```python
        for fmt in _cfg.REPORT_FORMAT:
            if fmt=="md": self._save_md(ts_file,suite_name,report, md_dir)
            elif fmt=="html": self._save_html(ts_file,suite_name,ts,f"{total_time:.1f}s",passed,failed,errors,manual,pass_rate,results, html_dir)
            elif fmt=="excel": self._save_excel(ts_file,suite_name,report, excel_dir)
```

Run: `python -m pytest tests -v`
Expected: 已有测试全绿（本步不改行为，只改读取方式）

实测：`79 passed, 7 failed`（剩下的 7 个失败全是缺 `build_from_records`），legacy 用例转绿且不再往真实 `output/` 写文件。

- [x] **Step 11.4: 实现 `build_from_records()`**

Append to `exporters/report_exporter.py`（类内，`build_and_save` 之后）：

```python
    # ── 分流版报告（数据源：records.jsonl）─────────────────────────
    _STATUS_ICON = {"pass": "PASSED", "fail": "FAILED", "error": "ERROR", "manual": "MANUAL",
                    "blocked": "BLOCKED", "skipped": "SKIPPED"}
    _CAT_CN = {"PRODUCT_BUG": "真实缺陷", "CASE_DEFECT": "用例问题", "EXEC_INCOMPLETE": "执行未到位",
               "ENV_BLOCK": "环境阻塞", "DATA_PRECOND": "数据前置未满足",
               "NEEDS_HUMAN": "待人工裁决", "OK": "通过"}
    _BUCKET_KEYS = ("通过", "真实缺陷", "环境阻塞", "数据前置未满足", "用例问题",
                    "执行未到位", "待人工裁决", "其他异常")

    def build_from_records(self, run_id: str, mode: str = None, ts_file: str = "") -> dict:
        """从统一契约出报告：`records.jsonl` → 规整三层结论 → 8 段摘要 + 有分流列的三格式。

        与 `build_and_save()` 并存：后者是 `TRIAGE_ENABLED=false` 的一键退回路径。
        报告层**不自己判定**，只呈现（判定全在 `core/triage.py`）。
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
        undecided = [r for r in records if not r.get("triage", {}).get("category")
                     or r["triage"].get("source") == "none"]
        if undecided:
            apply_rule_layer(undecided)          # 就地改写；已有结论的记录不被重算覆盖
            # ↑ 必须只喂 undecided：`apply_rule_layer` 会无条件 `rec["triage"].update(res)`，
            #   全量重算会把转换器从 blocker 带进来的结论与 `unblock_hint` 洗掉。
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

        md_dir, html_dir, excel_dir = _cfg.MD_REPORTS_DIR, _cfg.HTML_REPORTS_DIR, _cfg.EXCEL_REPORTS_DIR
        for d in (md_dir, html_dir, excel_dir):
            d.mkdir(parents=True, exist_ok=True)
        for fmt in _cfg.REPORT_FORMAT:
            if fmt == "md":
                self._save_md_triage(ts_file, report["suite_name"], report, md_dir)
            elif fmt in ("html", "excel"):
                # Task 12 落地分流版 HTML/Excel；本任务先跳过，不拿旧渲染器假装“已含分流列”
                logger.info(f"  {fmt.upper()} 分流报告待 Task 12 接入，本次仅出 Markdown")
        self._print_summary_triage(report)
        return report
```

- [x] **Step 11.5: 实现分流版 Markdown 与终端摘要**

Append to `exporters/report_exporter.py`（类内）：

```python
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

    @staticmethod
    def _name_of(d: dict) -> str:
        """用例名称单元格：历史 run 的阻塞用例只存了 case_id + blocker，名称必为空。"""
        from core.triage import md_escape as md
        return md(d.get("name")) or "（名称未记录，见用例库）"

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
```

> 说明（两个轻易被问的点）：
> 1. 「环境阻塞 / 数据前置未满足」这两桶实际**大多来自人工裁决**而非规则自动：R2/R3 不写 `unblock_hint`，而缺 hint 的 BLOCKED 会被 `merge_decisions` 回落 `NEEDS_HUMAN`（§8 防滥用约束）。报告层不得为了好看而把 hint 默填。
> 2. `derived_status(rec)` 会覆盖 `rec["status"]`（写 `blocked` / `manual`），但**不回写 `records.jsonl`**：原始事实不变，报告只展示派生态，这样重跑一次报告永远一致。

- [x] **Step 11.6: 运行确认通过**

Run: `python -m pytest tests/test_report_triage.py -v`
Expected: PASS，`11 passed`（计划原写 8，实施时因真跑发现三个口径问题补到 11）

Run: `python -m pytest tests -q`
Expected: `89 passed`（Task 10 后 78 + 本任务 11）

- [x] **Step 11.7: 真跑一次验证排版（用 Task 7 转换出的历史 run）**

Run: `python -c "from exporters.report_exporter import ReportExporter as R; r=R().build_from_records('P0_km_20260907', mode='report_only'); print(r['summary'])"`
Expected: 打印含 8 个中文桶的 dict；`output/06_reports/markdown/` 新增一份 `_知识管理.md`，打开自检：8 段数字相加 == 总用例，BLOCKED 表逐条有解除方式

> **坑**：真实 `.env` 里 `REPORT_FORMAT=['excel']`，直接跑只会在日志里看到一行「EXCEL 分流报告待 Task 12 接入」，**一份 MD 也不会生成**，看起来像「排版没问题」。核验排版需先 `config.REPORT_FORMAT = ["md"]`（临时脚本里改，不写进 `.env`）。

实测（`P0_km_20260907`，`mode=report_only`，179 行 MD）：

| 项 | 实测值 | 与 Task 7 基线对比 |
|---|---|---|
| 总用例 | 12 | 一致 |
| 数据前置未满足 | 5 | 一致 |
| 待人工裁决 | 7 | 一致 |
| 其他异常 | 0 | 一致 |
| 移出分母 / 有效通过率 | 5 / 0.0% | 一致（通过 0 条，所以两个通过率都是 0） |
| 桶和 == 总用例 | True | 自检不变量成立 |
| BLOCKED 表行数 | 5 == 移出分母 | 修口径前是 11 |
| 门禁 | `verdict=na`、`blocks_exit_code=False` | 与 CI 语义一致 |
| 逐条解除方式 | 5 条全有（与阻塞现象同源） | 转换器把 blocker 同时写进了 `unblock_hint` |

核验后删除本次生成的 3 份临时 MD（Task 11 产物归 Task 13/14 正式生成），`output/` 保持干净。

- [x] **Step 11.8: Commit**

```powershell
git add exporters/report_exporter.py core/triage.py tests/test_report_triage.py docs/superpowers/plans/2026-09-14-result-triage.md
git commit -m "feat(triage): 分流版报告接入 Markdown（8 段摘要/有效通过率/BLOCKED 独立表）" -- exporters/report_exporter.py core/triage.py tests/test_report_triage.py docs/superpowers/plans/2026-09-14-result-triage.md
```

> 真跑历史数据发现四处（前三处是「报告自己造了第二套口径」，本任务铁律就是只呈现不判定，都已改为回到 `core/triage.py` 的结论；第四处是名字缺失的呈现问题），外加一处跨模块改名：
> 1. **BLOCKED 表与摘要两套口径**。计划用 `r["status"] == "blocked"` 挑阻塞，但 `records.jsonl` 里原始 `status=blocked` 有 11 条（转换器从 `pending_cases` 写的），而分流后真正算阻塞的只有 5 条，其余 6 条因「blocked 但未说明原因」落 R8 待裁决。结果报告会出现「摘要 5 条阻塞」+「BLOCKED 表 11 行」，而 BLOCKED 表存在的意义就是逐条展示「谁逃出了分母」，多出来的 6 行会让人怀疑整个有效通过率。改用 `_is_blocked()`（只看分流类别）。
> 2. **`_conclusion` 先判阻塞、后判待裁决**，同一行会左边写 `BLOCKED`、右边写「待人工裁决」，人不知道先处理哪个。改为先判 `NEEDS_HUMAN`，阻塞也走 `_is_blocked()`。
> 3. **报告标题取首条记录的模块**：`P0_km_20260907` 的 12 条里 11 条是知识管理，但排首的 `TC-CAT-002` 写着分类管理，整份报告就被命名为「分类管理」。改为取多数模块（并列时保留首次出现顺序，不随记录顺序飘）。
> 4. **11/12 条用例名称为空，表格像渲染坏了**。查源确认不是转换器漏读：`test_result_P0_km_20260907.json` 的 `pending_cases` 只存 `case_id` + `blocker`，**根本没有名称字段**。报告层只能显式标「（名称未记录，见用例库）」；按 `case_id` 从用例库回填属 Task 7 数据层，列为二期遗留（见 Task 14）。
> 5. **顺带做了两个公开化改名**：`_md_escape` → `md_escape`、`_BLOCKED_CATEGORIES` → `BLOCKED_CATEGORIES`。报告层要用它们，`import` 一个下划线开头的名字等于把私有实现当 API；尤其 BLOCKED 定义只能有一份，否则又是一个口径源。

---

## Task 12: 报告层接入Ⅱ——HTML 六张卡片 + Excel 18 列

目标：分流结论不只在 MD 可见（spec §4.4：三份报告统一增列 `分流类别 / 判定来源 / 置信度 / 裁决人`）。做法上把 HTML 渲染拆成可共用的卡片/表头/行构造函数，避开两处各写一份拷贝；旧 4 态路径继续走 14 列、5 卡片。

> 一句口径先行：报告里**任何按结果分类的东西都跟分流类别走**，不跟原始 `status` 走。本任务实施时在三处踩到这条（颜色、名称占位、表头计数），见文末「实施时修正」。

**Files:**
- Modify: `exporters/report_exporter.py`（重写 `HTML_TEMPLATE`、`_save_html`、`_save_excel`；新增 `_save_html_triage`、`_save_excel_triage` 与三个行/头/卡片构造函数）
- Test: `tests/test_report_triage.py`（追加）

- [x] **Step 12.1: 写失败测试**

Append to `tests/test_report_triage.py`（需先在文件顶部补一行 `from openpyxl import load_workbook`）：

```python
from openpyxl import load_workbook
```

```python
@pytest.fixture
def env_web(env, monkeypatch):
    """复用 `env`，只把输出格式换成 HTML + Excel。"""
    monkeypatch.setattr(config, "REPORT_FORMAT", ["html", "excel"])
    return env


def _read_html(tmp_path):
    files = sorted((tmp_path / "html").glob("*.html"))
    assert files, "未生成 HTML 报告"
    return files[-1].read_text(encoding="utf-8")


def _load_xlsx(tmp_path):
    files = sorted((tmp_path / "xlsx").glob("*.xlsx"))
    assert files, "未生成 Excel 报告"
    return load_workbook(files[-1])


def test_html_has_six_cards_and_effective_rate(env_web):
    _seed()
    ReportExporter().build_from_records("R1", mode="strict")
    html = _read_html(env_web)
    assert html.count('<div class="card ') == 6
    for label in ("Total", "Passed", "Product Bugs", "Env / Data Blocked", "Pending Review",
                  "Effective Pass Rate"):
        assert label in html
    assert ">50.0%<" in html                      # 有效通过率（不是原始 25.0%）
    assert "发版建议" in html and "不具备出结论条件" in html


def test_html_blocked_section_and_triage_headers(env_web):
    _seed()
    ReportExporter().build_from_records("R1", mode="strict")
    html = _read_html(env_web)
    assert "BLOCKED（环境 / 数据前置，单独成表）" in html
    assert "起本地服务后整 run 重跑" in html
    detail_head = html.split("<table>")[1].split("</tr>")[0]   # 只数明细表的列头，不含 BLOCKED 表
    assert detail_head.count("<th>") == 18                     # 14 旧列 + 4 分流列
    for h in ("分流类别", "判定来源", "置信度", "裁决人"):
        assert f"<th>{h}</th>" in html


def test_html_escapes_angle_brackets(env_web):
    """断言原文含 `<b>` 时不得破坏表格（旧版未转义，本任务一并修）。"""
    append_records([_rec("R8", "TC-050", status="fail",
                         assertions=[{"text": "提示「<b>保存成功</b>」出现", "verdict": "fail",
                                      "reason": "", "evidence_refs": []}])], "R8")
    ReportExporter().build_from_records("R8", mode="strict")
    html = _read_html(env_web)
    assert "&lt;b&gt;保存成功&lt;/b&gt;" in html


def test_excel_has_18_columns_and_blocked_sheet(env_web):
    _seed()
    ReportExporter().build_from_records("R1", mode="strict")
    wb = _load_xlsx(env_web)
    ws = wb["Test Results"]
    heads = [c.value for c in ws[4]]
    assert len(heads) == 18 and heads[-4:] == ["分流类别", "判定来源", "置信度", "裁决人"]
    assert "BLOCKED" in wb.sheetnames
    blocked = [[c.value for c in row] for row in wb["BLOCKED"].iter_rows(min_row=2)]
    assert any(r[0] == "TC-002" and "起本地服务" in str(r[5]) for r in blocked)
    assert any(r[0] == "TC-003" for r in blocked)
    assert len(blocked) == 2


def test_excel_conclusion_uses_blocked_and_pending(env_web):
    _seed()
    ReportExporter().build_from_records("R1", mode="strict")
    ws = _load_xlsx(env_web)["Test Results"]
    by_id = {row[0].value: row[5].value for row in ws.iter_rows(min_row=5)}
    assert by_id["TC-001"] == "PASSED"
    assert by_id["TC-002"] == "BLOCKED" and by_id["TC-003"] == "BLOCKED"
    assert by_id["TC-004"] == "待人工裁决"
    assert any(row[14].value == "环境阻塞" for row in ws.iter_rows(min_row=5))   # O 列分流类别


def test_html_conclusion_color_follows_category(env_web):
    """结论单元格按分流类别着色，不跟着原始 `status` 走。

    原始颜色由 `status-fail` 提供，于是「待人工裁决」被刷成缺陷红——未定论的用例看起来
    像已确认失败，正好把分流最想传达的信息说反。
    """
    _seed()
    ReportExporter().build_from_records("R1", mode="strict")
    html = _read_html(env_web)
    assert 'class="c-pending">待人工裁决' in html
    assert 'class="c-blocked">BLOCKED' in html
    assert 'class="c-ok">PASSED' in html


def test_excel_status_fill_follows_category(env_web):
    """Excel 的 Status 列底色同理：分流模式下跟类别，不跟原始四态。"""
    _seed()
    ReportExporter().build_from_records("R1", mode="strict")
    ws = _load_xlsx(env_web)["Test Results"]
    fill = {row[0].value: str(row[5].fill.start_color.rgb) for row in ws.iter_rows(min_row=5)}
    assert fill["TC-004"] == "00FFF9C4"       # 待裁决黄
    assert fill["TC-002"] == "00E1BEE7"       # 环境阻塞紫
    assert fill["TC-001"] == "00E2EFDA"       # 通过绿


def test_blank_name_marked_in_html_and_excel(env_web):
    """历史 run 的阻塞用例没存名称：HTML/Excel 明细表也得显式标出来。

    MD 侧 Task 11 已处理；这里若留空，整列空白看起来像渲染坏了而不像「数据本就没有」。
    """
    append_records([_rec("R9", "TC-060", name="", status="blocked")], "R9")
    ReportExporter().build_from_records("R9", mode="strict")
    assert "（名称未记录" in _read_html(env_web)
    ws = _load_xlsx(env_web)["Test Results"]
    assert [row[1].value for row in ws.iter_rows(min_row=5)] == ["（名称未记录，见用例库）"]


def test_legacy_html_and_excel_shape_unchanged(env_web):
    """旧路径：14 列 / 5 卡片，一行结论不得变。"""
    rows = [{"id": "TC-001", "name": "n", "module": "m", "case_type": "正向", "priority": "P0",
             "status": "pass", "duration": 1.0, "steps": "1. a", "expected": "1. b",
             "assertions": [{"text": "t", "passed": True}]}]
    ReportExporter().build_and_save("知识管理", rows)
    html = _read_html(env_web)
    assert html.count('<div class="card ') == 5 and html.count("<th>") == 14
    wb = _load_xlsx(env_web)
    assert len([c.value for c in wb["Test Results"][4]]) == 14
    assert "BLOCKED" not in wb.sheetnames
```

- [x] **Step 12.2: 运行确认失败**

Run: `python -m pytest tests/test_report_triage.py -v`
Expected: 新增 6 个用例 FAIL（HTML/Excel 在 Task 11 里被有意跳过，报 `未生成 HTML 报告` / `未生成 Excel 报告`）

实测：`6 failed, 11 passed`，报错就是上面两句。后来补的 3 个用例（名称占位、HTML/Excel 配色）也是在实现前单独跑红，才写渲染代码。

- [x] **Step 12.3: 重写 HTML 模板与公用渲染函数**

把 `exporters/report_exporter.py` 的 `HTML_TEMPLATE`（现 `:20-51`）整段替换：

```python
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
```

顶部 import 段补两行（`from openpyxl.styles import ...` 之后）：

```python
from html import escape
from openpyxl.utils import get_column_letter     # Excel 列数可变，不能手写 "A1:N1"
```

模块级（`HTML_TEMPLATE` 之后、`class ReportExporter` 之前）加：

```python
def _cards(items) -> str:
    """items: [(css_class, value, label), ...] → 卡片 HTML。旧模式 5 张、分流模式 6 张。"""
    return "".join(f'<div class="card {cls}"><h3>{val}</h3><p>{label}</p></div>'
                   for cls, val, label in items)
```

- [x] **Step 12.4: 把 `_save_html` 改为公用函数驱动（旧输出不变）**

`_save_html` 整方法替换：

```python
    def _save_html(self, ts_file, suite_name, ts, total_time, passed, failed, errors, manual, rate, results, output_dir):
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
```

- [x] **Step 12.5: `_save_excel` 支持 18 列与 BLOCKED 工作表**

`_save_excel` 整方法替换：

```python
    def _save_excel(self, ts_file, suite_name, report, output_dir, triage=False):
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
                  self._conclusion(d) if triage else d["status"],
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
        path=output_dir/f"{ts_file}_{suite_name}.xlsx"
        wb.save(path)
        logger.info(f"  Excel{'' if not triage else '(分流)'}: {path.name}")

    def _excel_subtitle(self, report, triage: bool) -> str:
        """第 2 行副标题：旧模式保持原文案，分流模式改为 8 段 + 发版建议一行可读。"""
        if not triage:
            s = report["summary"]
            return (f"Time: {report['timestamp']}  Pass Rate: {s['pass_rate']}  "
                    f"Duration: {s['total_time']}  Manual: {s['manual']}")
        s = report["summary"]
        return (f"Run: {report['run_id']}  Time: {report['timestamp']}  Mode: {report['mode']}  "
                f"总 {s['总用例']} 通过 {s['通过']} 缺陷 {s['真实缺陷']} 环境 {s['环境阻塞']} "
                f"数据 {s['数据前置未满足']} 用例 {s['用例问题']} 执行 {s['执行未到位']} "
                f"待裁决 {s['待人工裁决']} 其他 {s['其他异常']}  "
                f"通过率 {s['通过率']}% 有效通过率 {s['有效通过率']}%  "
                f"发版建议: {self._gate_text(report['gate'])}")

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
```

- [x] **Step 12.6: 让 `build_from_records` 接上两种格式**

把 Task 11 写的跳过分支整块替换：

```python
            elif fmt == "html":
                self._save_html_triage(ts_file, report["suite_name"], report, html_dir)
            elif fmt == "excel":
                self._save_excel_triage(ts_file, report["suite_name"], report, excel_dir)
```

并在类内补上入口（与 `_save_excel` 保持同一名词层级，不直接把 `triage=True` 散到调用方）：

```python
    def _save_excel_triage(self, ts_file, suite_name, report, output_dir):
        """分流版 Excel：18 列 + BLOCKED 工作表。实际渲染复用 `_save_excel(triage=True)`。"""
        self._save_excel(ts_file, suite_name, report, output_dir, triage=True)
```

- [x] **Step 12.7: 运行确认通过**

Run: `python -m pytest tests/test_report_triage.py -v`
Expected: PASS，`20 passed`（计划原本 6 个共 14，实施时因真跑发现配色与名称占位两个问题补到 20）

Run: `python -m pytest tests -q`
Expected: `98 passed`（Task 11 后 89 + 本任务 9）

- [x] **Step 12.8: 肉眼验收 HTML（不靠断言猜样式）**

> **坑（与 Task 11 同一根）**：真实 `.env` 里 `REPORT_FORMAT=['excel']`，直接跑不生成 HTML，看起来像「样式没问题」。样式核验必须在临时脚本里先 `config.REPORT_FORMAT = ["html", "excel"]`（不写进 `.env`）。

Run: `python -c "from core import config; from exporters.report_exporter import ReportExporter as R; config.REPORT_FORMAT=['html']; R().build_from_records('P0_km_20260907', mode='report_only')"`，再用 browser-use `navigate_page` 打开 `file:///.../output/06_reports/html/<ts>_知识管理.html` 截图看。
Expected: 浏览器里看到 6 张卡片（第 4 张紫色 Env / Data Blocked）、含 4 个分流列的 18 列表格、顶部黄/红门禁条、底部 BLOCKED 独立表

实测（`P0_km_20260907`，`mode=report_only`）：

| 项 | 实测值 | 判定 |
|---|---|---|
| 卡片 | 6 张：Total 12 / Passed 0 / Product Bugs 0 / Env・Data Blocked 5（紫）/ Pending Review 7（黄）/ Effective Pass Rate 0.0%（蓝） | 与 Task 11 的 MD 基线逐项一致 |
| 明细表列头 | `<th>` 18（旧 14 + 分流 4） | OK |
| 门禁条 | `class="gate gate-na"`，文案含「未裁决 7 项 / 缺解除方式 0 项」 | OK |
| BLOCKED 表 | 5 行× 5 列，逐条有解除方式 | 行数 == 移出分母 5 |
| 名称缺失行 | 明细表与 BLOCKED 表均显示「（名称未记录，见用例库）」 | 修复前是整列空白 |
| 配色 | 待人工裁决=琥珀色、BLOCKED=紫、PASSED=绿（不再顶着缺陷红） | 修复前 `status-fail` 红字 |
| footer | `duplicates=0 malformed=0 \| 通过率 0.0% · 有效通过率 0.0%` | OK |
| Excel | `Test Results`（18 列，末 4 列为分流列）+ `BLOCKED`（6 列 5 行） | OK |
| 旧路径 | 14 列 / 5 卡片 / 无 BLOCKED 工作表 | 无回归 |

> 已知遗留（不是报告层 bug）：BLOCKED 表的「阻塞现象」与「解除方式」在历史 run 里逐字相同。原因在转换器：`scripts/_convert_legacy_result.py` 把 `pending_cases[].blocker` 同时写进了 `error`（→ `actual`）与 `triage.unblock_hint`，因为旧 JSON 只有一个原因字段。新数据（MCP 执行线）两个字段分开，不会同文。

核验后删除本次生成的 HTML/Excel（固定用 `ts_file="99999999_999999"` 便于识别），`output/` 保持干净。

- [x] **Step 12.9: Commit**

```powershell
git add exporters/report_exporter.py tests/test_report_triage.py docs/superpowers/plans/2026-09-14-result-triage.md
git commit -m "feat(triage): HTML 六卡片/18 列与 Excel 18 列+BLOCKED 工作表" -- exporters/report_exporter.py tests/test_report_triage.py docs/superpowers/plans/2026-09-14-result-triage.md
```

> 卡片张数由 `_cards()` 传入的列表长度决定（旧 5 / 分流 6），模板里不留卡片硬编码；列头同理走 `_html_head(triage)`。旧报告的文字内容与列数一字不变，但有三处**样式层面**的改动（都不是口径变化，已核对）：① 表格单元走转义（旧版会把断言里的 `<b>` 当标签吃掉，见 Step 12.4 `_cell` 注释）；② 页面宽度 `max-width` 960px → 1180px（18 列装不下）；③ Excel `Status` 列宽 8 → 10。

> 实施时修正（都是真跑 / 肉眼阶段才看到的，已补测试先红后绿）：
> 1. **`html.count("<th>") == 18` 这个断言与同一任务自己的代码相矛盾**。`_html_blocked_table` 自带 5 个 `<th>`，全文共 23。改为只数明细表的 thead（按意图而非字面），并在测试里写明为何不数全文。
> 2. **结论列配色跟了原始 `status`**。「待人工裁决」顶着 `status-fail` 的缺陷红，把「未定论」渲染成「已确认失败」——恰好是分流最想避免的误读。HTML 新增 `_CONCL_CLS`（类别 → `c-*`），Excel Status/Case ID 两列底色在分流模式下改走 `cat_fills`。旧模式不动。
> 3. **名称占位只做了 MD，HTML/Excel 明细表仍留空白**。历史 run 12 条里 11 条无名称，整列空白看起来像渲染坏了。现在三格式共用类常量 `_NAME_MISSING`，不在三处各写一份文案。
> 4. **Excel `Status` 列宽由 8 改为 10**：「待人工裁决」六个字在 8 宽下会被挤成两行。属外观微调，不是口径变化。

---

## Task 13: 编排入口 `python run.py triage`

把前三层接成一个命令：读 `records.jsonl` → 规则层 →（LLM 复判）→ 产物 →（人工门禁）→ 重合并 → 报告，并让**门禁结论影响退出码**（仅 strict）。

**Files:**
- Modify: `core/triage.py`（新增 `list_runs()`）
- Modify: `agents/triage_agent.py`（新增模块级 `triage_pipeline()`）
- Modify: `run.py:18-23`（顶部用法注释）、`:90-91`（pipeline 收尾提示）、新增 `cmd_triage()`、`COMMANDS`、`cmd_help()` 表行
- Test: `tests/test_triage_orchestration.py`

- [ ] **Step 13.1: 写失败测试**

Create `tests/test_triage_orchestration.py`：

```python
"""编排：records → 规则层 →（LLM）→ 产物 →（人工门禁）→ 重合并 → 报告 → 门禁退出码。"""
import pytest

from core import config
from core.triage import append_records, list_runs, new_record, save_decisions


def _rec(rid, cid, **kw):
    r = new_record(run_id=rid, case_id=cid, module="知识管理")
    r["name"] = kw.pop("name", f"用例{cid}")
    r["status"] = kw.pop("status", "fail")
    tri = kw.pop("triage", None)
    if tri is not None:
        r["triage"].update(tri)
    r.update(kw)
    return r


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRIAGE_DIR", tmp_path / "triage")
    monkeypatch.setattr(config, "MD_REPORTS_DIR", tmp_path / "md")
    monkeypatch.setattr(config, "HTML_REPORTS_DIR", tmp_path / "html")
    monkeypatch.setattr(config, "EXCEL_REPORTS_DIR", tmp_path / "xlsx")
    monkeypatch.setattr(config, "REPORT_FORMAT", ["md"])
    monkeypatch.setattr(config, "HUMAN_CONFIRM", False)     # 默认非交互，测试不卡 stdin
    return tmp_path


def _seed(rid="R1"):
    """1 条 OK + 1 条 R7（步骤到位、可验证断言失败）→ 待人工裁决。"""
    append_records([
        _rec(rid, "TC-001", status="pass",
             steps=[{"order": 1, "action": "点击新建", "outcome": "ok", "detail": ""}],
             assertions=[{"text": "弹窗关闭", "verdict": "pass", "reason": "", "evidence_refs": []}]),
        _rec(rid, "TC-004", status="fail",
             assertions=[{"text": "分类树出现新分类", "verdict": "fail", "reason": "",
                          "evidence_refs": []}]),
    ], rid)
    return rid


def test_list_runs_skips_empty_dirs_and_puts_newest_first(env):
    _seed("B_20260910_101010")
    (env / "triage" / "empty_run").mkdir(parents=True)                  # 只有产物不算 run
    _seed("A_20260912_101010")                                          # 后写 → 排在前
    runs = list_runs()
    assert runs[0] == "A_20260912_101010" and "B_20260910_101010" in runs
    assert "empty_run" not in runs


def test_pipeline_writes_artifacts_and_report(env):
    from agents.triage_agent import triage_pipeline
    out = triage_pipeline(_seed(), do_llm=False, make_report=True)
    assert out["error"] == ""
    assert out["summary"]["总用例"] == 2 and out["summary"]["待人工裁决"] == 1
    assert out["gate"]["verdict"] == "na"                    # HUMAN_CONFIRM=False → report_only
    assert not out["gate"]["blocks_exit_code"]               # CI 不得假阻塞流水线
    assert (env / "triage" / "R1" / "pending_review.md").exists()
    assert (env / "triage" / "R1" / "gate.json").exists()
    assert list((env / "md").glob("*.md"))                   # 报告已生成


def test_pipeline_skips_llm_by_default_and_runs_on_request(env, monkeypatch):
    from agents import triage_agent
    calls = []
    monkeypatch.setattr(triage_agent.TriageAgent, "review",
                        lambda self, rid, dry_run=False: (calls.append(rid),
                                                          {"reviewed": 0, "parsed": 0,
                                                           "raw_failed": 0, "prompt_path": ""})[1])
    triage_agent.triage_pipeline(_seed("R2"), do_llm=False)
    assert calls == []
    triage_agent.triage_pipeline("R2", do_llm=True)
    assert calls == ["R2"]


def test_pipeline_remerges_after_human_gate(env, monkeypatch):
    """人工拍板后必须重跑合并：否则 `decisions.yaml` 写了却不进摘要与门禁。"""
    from agents import triage_agent

    def fake_gate(rid, merged):
        assert merged["TC-004"]["triage"]["category"] == "NEEDS_HUMAN"
        dec = {"TC-004": {"final_category": "PRODUCT_BUG", "confirmed_by_human": True,
                          "decided_by": "tester", "note": "确认缺陷", "decided_at": "2026-09-14T18:00:00",
                          "bug_draft": {"title": "分类未新增", "severity": "S2"}}}
        save_decisions(rid, dec)
        return dec

    monkeypatch.setattr(config, "HUMAN_CONFIRM", True)
    monkeypatch.setattr("core.human_confirm.confirm_triage_decisions", fake_gate)
    out = triage_agent.triage_pipeline(_seed("R3"), make_report=False)
    assert out["summary"]["真实缺陷"] == 1 and out["summary"]["待人工裁决"] == 0
    assert out["gate"]["verdict"] == "allow"
    assert list((env / "triage" / "R3" / "bug_drafts").glob("*.md"))


def test_pipeline_on_missing_run_reports_clearly(env):
    from agents.triage_agent import triage_pipeline
    out = triage_pipeline("missing")
    assert "records.jsonl" in out["error"] and out["report"] is None
    assert out["summary"] == {}
```

- [ ] **Step 13.2: 运行确认失败**

Run: `python -m pytest tests/test_triage_orchestration.py -v`
Expected: FAIL，`ImportError: cannot import name 'list_runs' from 'core.triage'`

- [ ] **Step 13.3: 实现 `list_runs()`**

Append to `core/triage.py`：

```python
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
```

- [ ] **Step 13.4: 实现 `triage_pipeline()`**

Append to `agents/triage_agent.py`（模块级，`TriageAgent` 类之后）：

```python
def triage_pipeline(rid: str, do_llm: bool = False, interactive: bool = None,
                    mode: str = None, make_report: bool = True) -> dict:
    """一次跑完分流闭环。返回 `{run_id, error, summary, gate, artifacts, report, llm, human_decided}`。

    为何放在 agents 层而不是 `core/triage.py`：core 保持纯函数与文件读写，便于单测；
    本函数要串 `core.human_confirm`（交互）与 `exporters`（渲染），属编排。
    """
    from core import config as _cfg
    from core.triage import (apply_rule_layer, compute_summary, derived_status, evaluate_gate,
                             load_decisions, load_llm_review, load_records, merge_decisions,
                             write_artifacts)

    records, dups, malformed = load_records(rid)
    if not records:
        return {"run_id": rid, "error": f"records.jsonl 无有效记录（{rid}）：先执行测试，"
                                         f"或用 scripts/_convert_legacy_result.py 转换历史结果",
                "summary": {}, "report": None, "artifacts": {}, "llm": {}, "human_decided": 0,
                "gate": {"verdict": "na", "pending": 0, "no_hint": 0, "bugs": [],
                         "note": "无记录可分流", "blocks_exit_code": False}}

    undecided = [r for r in records if not r.get("triage", {}).get("category")
                 or r["triage"].get("source") == "none"]
    if undecided:
        apply_rule_layer(undecided)                  # 已有结论的记录不被重算覆盖
    llm_info = {"reviewed": 0, "parsed": 0}
    if do_llm:
        llm_info = TriageAgent().review(rid)

    merged = merge_decisions(records, load_llm_review(rid), load_decisions(rid))
    gate_mode = mode or ("strict" if _cfg.HUMAN_CONFIRM else "report_only")
    interactive = _cfg.HUMAN_CONFIRM if interactive is None else interactive
    # 先落一份给人看的产物：门禁要在人手里过，清单必须先存在（文件即状态）
    artifacts = write_artifacts(rid, merged, compute_summary(merged), dups, malformed, gate_mode)
    decided: dict = {}
    if interactive:
        from core.human_confirm import confirm_triage_decisions   # 延迟导入：测试可 monkeypatch
        decided = confirm_triage_decisions(rid, merged) or {}
        if decided:
            merged = merge_decisions(records, load_llm_review(rid), decided)
    for rec in merged.values():
        rec["status"] = derived_status(rec)
    summary = compute_summary(merged)
    artifacts = write_artifacts(rid, merged, summary, dups, malformed, gate_mode)   # 拍板后覆写
    gate = evaluate_gate(merged, mode=gate_mode)
    report = None
    if make_report:
        from exporters.report_exporter import ReportExporter
        report = ReportExporter().build_from_records(rid, mode=gate_mode)
    return {"run_id": rid, "error": "", "summary": summary, "gate": gate, "artifacts": artifacts,
            "report": report, "llm": llm_info, "human_decided": len(decided),
            "duplicates": dups, "malformed": malformed}
```

Run: `python -m pytest tests/test_triage_orchestration.py -v`
Expected: PASS，`5 passed`

在 `tests/test_triage_orchestration.py` 末尾追加 `--validate` 的两个用例（先跑一次确认 FAIL，报 `AttributeError` 或退出码不符）：

```python
def test_validate_flag_reports_missing_cases_and_exits_nonzero(env, monkeypatch, capsys):
    """缺口存在（计划 2 条只记录 1 条）时，--validate 必须指出来并不给退出码 0。"""
    from core.triage import write_plan_cases
    write_plan_cases("R1", ["TC-001", "TC-002"], module="知识管理")
    append_records([_rec("R1", "TC-001")], "R1")
    monkeypatch.setattr(sys, "argv", ["run.py", "triage", "R1", "--validate"])
    import pytest as _pytest
    with _pytest.raises(SystemExit) as e:
        cmd_triage()
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert "TC-002" in out and "缺口 1" in out


def test_validate_flag_passes_when_complete(env, monkeypatch, capsys):
    from core.triage import write_plan_cases
    write_plan_cases("R1", ["TC-001"], module="知识管理")
    append_records([_rec("R1", "TC-001")], "R1")
    monkeypatch.setattr(sys, "argv", ["run.py", "triage", "R1", "--validate"])
    import pytest as _pytest
    with _pytest.raises(SystemExit) as e:
        cmd_triage()
    assert e.value.code == 0
```

Run: `python -m pytest tests/test_triage_orchestration.py -v`
Expected: PASS，`7 passed`（Step 13.5 写入 `--validate` 分支后才会绿，现在应 FAIL）

- [ ] **Step 13.5: 接入 `run.py triage`**

在 `cmd_prototype()` 之后新增：

```python
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
        console.print("\n[dim]用法：python run.py triage <run_id> [--llm|--validate][/dim]")
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
        console.print("  [green]✓ 校验通过[/green]" if ok else "  [red]✗ 校验不通过[/red]")
        sys.exit(0 if ok else 1)
    console.print(f"\n[bold cyan]>>> 结果分流：{rid}[/bold cyan]\n")
    out = triage_pipeline(rid, do_llm="--llm" in flags)
    if out.get("error"):
        console.print(f"  [red]✗ {out['error']}[/red]")
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
    for key, val in out["artifacts"].items():
        for one in (val if isinstance(val, list) else [val]):
            console.print(f"  [dim]{key}: {one}[/dim]")
    verdict = {"allow": "[bold green]✅ 建议发版[/bold green]",
               "reject": "[bold red]❌ 不具备出结论条件[/bold red]",
               "na": "[bold yellow]N/A（CI 浅分流，未做缺陷定性）[/bold yellow]"}[g["verdict"]]
    console.print(f"\n  发版建议：{verdict}  [dim]{g['note']}[/dim]")
    if g["pending"]:
        console.print(f"  [yellow]待裁决 {g['pending']} 项[/yellow]：打开 "
                      f"output/06_reports/triage/{rid}/pending_review.md；或在人在场的终端重跑本命令逐条拍板")
    if g["blocks_exit_code"]:
        sys.exit(1)
```

在 `COMMANDS` 字典里 `"qoder-plan"` 行之后插入：

```python
    "triage":        (cmd_triage,        "结果分流：失败归因 + 有效通过率 + 发版门禁"),
```

在 `cmd_help()` 的 `table.add_row("qoder-plan", ...)` 之后插入：

```python
    table.add_row("triage", "结果分流：把失败拆成真实缺陷/用例问题/执行未到位/环境数据问题", "推荐·收尾")
```

在文件顶部 docstring 的 `python run.py test ...` 行之后插入：

```
    python run.py triage       # 结果分流：列出可分流的 run（加 run_id 则直接分流）
    python run.py triage 知识管理_20260914_173000 --llm  # 含 LLM 复判的分流与发版门禁
```

把 `cmd_pipeline()` 结尾的两行提示（`run.py:90-91`）换成三行，把分流接回闭环：

```python
    console.print("[dim]  下一步：在 Qoder 对话中读取 qoder_workspace/test_plan.md 执行测试[/dim]")
    console.print("[dim]  脚本模式（备用/CI，不依赖 Qoder）：python run.py test[/dim]")
    console.print("[dim]  执行完成后分流与出报告：python run.py triage --list → python run.py triage <run_id>[/dim]")
```

- [ ] **Step 13.6: CLI 手工验收**

Run: `python run.py triage --list`
Expected: 列出 `P0_km_20260907` 等已有 run，无 traceback

Run: `python run.py triage not_a_run`
Expected: 打印 `✗ records.jsonl 无有效记录（not_a_run）…`，退出码 1（`echo $LASTEXITCODE` 为 `1`）

Run: `$env:HUMAN_CONFIRM="false"; python run.py triage P0_km_20260907`
Expected: 打印 8 段数字与「N/A（CI 浅分流）」，退出码 **0**（不阻塞流水线）

Run: `python run.py help`
Expected: 命令表含 `triage` 行

- [ ] **Step 13.7: 全量回归**

Run: `python -m pytest tests -v`
Expected: `71 passed`

- [ ] **Step 13.8: Commit**

```powershell
git commit -m "feat(triage): run.py triage 编排入口（含门禁退出码）"
```

---

## Task 14: 铲除硬编码入口 + README + 端到端验收

`gen_p0_report.py` / `gen_p2_report.py` / `gen_iap_report.py` 现在是「把执行结果抄进 Python 源码」的失真源头。入口保留（命令习惯不变），数据源强制切到统一契约；一个提交周期确认稳定后再删脚本本身（只要还能手写数据，就会有人手写第四个）。

**Files:**
- Create: `scripts/_report_entry.py`
- Modify: `scripts/gen_p0_report.py`、`scripts/gen_p2_report.py`、`scripts/gen_iap_report.py`（整体重写为薄封装）
- Modify: `README.md:60-68`（第五阶段表格 + 新增分流小节）
- Test: `tests/test_report_entry.py`

- [ ] **Step 14.1: 写失败测试**

Create `tests/test_report_entry.py`：

```python
"""入口薄封装：数据源只能是 records.jsonl，不得再回到手写结果。"""
import sys
from pathlib import Path

import pytest

from core import config
from core.triage import append_records, new_record

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _rec(rid, cid, **kw):
    r = new_record(run_id=rid, case_id=cid, module="知识管理")
    r["name"] = kw.pop("name", f"用例{cid}")
    r["status"] = kw.pop("status", "pass")
    tri = kw.pop("triage", None)
    if tri is not None:
        r["triage"].update(tri)
    r.update(kw)
    return r


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRIAGE_DIR", tmp_path / "triage")
    monkeypatch.setattr(config, "MD_REPORTS_DIR", tmp_path / "md")
    monkeypatch.setattr(config, "HTML_REPORTS_DIR", tmp_path / "html")
    monkeypatch.setattr(config, "EXCEL_REPORTS_DIR", tmp_path / "xlsx")
    monkeypatch.setattr(config, "REPORT_FORMAT", ["md"])
    monkeypatch.setattr(config, "HUMAN_CONFIRM", False)
    return tmp_path


def test_pick_run_prefers_hint_keyword(env):
    from _report_entry import pick_run
    append_records([_rec("P0_km_20260907", "TC-001")], "P0_km_20260907")
    append_records([_rec("工业APP_20260912_101010", "TC-100")], "工业APP_20260912_101010")
    assert pick_run(("km", "知识管理")) == "P0_km_20260907"
    assert pick_run(("工业APP",)) == "工业APP_20260912_101010"
    assert pick_run(("nothing",)) == pick_run()          # 提示不中时退回最新 run


def test_pick_run_empty_returns_blank(env):
    from _report_entry import pick_run
    assert pick_run(("km",)) == ""


def test_main_reads_contract_and_returns_zero(env, monkeypatch, capsys):
    import _report_entry
    monkeypatch.setattr(sys, "argv", ["gen_p0_report.py", "P0_km_20260907"])
    append_records([_rec("P0_km_20260907", "TC-001",
                         steps=[{"order": 1, "action": "点击", "outcome": "ok", "detail": ""}],
                         assertions=[{"text": "弹窗关闭", "verdict": "pass", "reason": "",
                                      "evidence_refs": []}])], "P0_km_20260907")
    assert _report_entry.main("gen_p0_report", hints=("km",)) == 0
    assert "有效通过率" in capsys.readouterr().out
    assert list((env / "md").glob("*.md"))


def test_main_without_records_explains_next_step(env, monkeypatch, capsys):
    import _report_entry
    monkeypatch.setattr(sys, "argv", ["gen_p0_report.py"])
    assert _report_entry.main("gen_p0_report", hints=("km",)) == 1
    assert "run.py triage" in capsys.readouterr().out or "没有可分流的 run" in capsys.readouterr().out


def test_legacy_4state_flag_still_available(env, monkeypatch, capsys):
    """逃生口：`to_result_rows` 反向映射回旧 `build_and_save()`，保证旧四态报告仍可从契约生成。"""
    import _report_entry
    append_records([_rec("R9", "TC-001")], "R9")
    monkeypatch.setattr(sys, "argv", ["gen_p0_report.py", "R9", "--legacy-4state"])
    assert _report_entry.main("gen_p0_report", hints=("km",)) == 0
    md = next((env / "md").glob("*.md")).read_text(encoding="utf-8")
    assert "分流类别" not in md and "| Passed |" in md


@pytest.mark.parametrize("name", ["gen_p0_report.py", "gen_p2_report.py", "gen_iap_report.py"])
def test_wrapper_scripts_have_no_hardcoded_results(name):
    """守门测试：谁再往入口脚本里抄执行结果，这里直接红。"""
    text = (SCRIPTS / name).read_text(encoding="utf-8")
    assert "results = [" not in text, f"{name} 又把结果写进了源码"
    assert '"id": "TC-' not in text, f"{name} 又手写了用例数据"
    assert "build_from_records" in text or "_report_entry" in text
```

- [ ] **Step 14.2: 运行确认失败**

Run: `python -m pytest tests/test_report_entry.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named '_report_entry'`

- [ ] **Step 14.3: 写共用入口**

Create `scripts/_report_entry.py`：

```python
# -*- coding: utf-8 -*-
"""`gen_*_report.py` 的共用入口：数据源强制为 `records.jsonl`。

这些脚本历史上把执行结果**拄写在 Python 源码里**（`results = [...]`），报告与事实脱节的
源头。入口保留（命令习惯不变），但一行数据都不再手写。

用法：`python scripts/gen_p0_report.py [run_id] [--legacy-4state]`
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def pick_run(hints=()) -> str:
    """按关键字（模块名 / 历史命名习储如 `km`、`iap`）挑最新匹配的 run_id，不中则取最新 run。"""
    from core.triage import list_runs
    runs = list_runs()
    for hint in hints:
        for rid in runs:
            if hint.lower() in rid.lower():
                return rid
    return runs[0] if runs else ""


def main(script_name: str, hints=()) -> int:
    """返回退出码：0 可继续；1 是无数据或人在场的门禁卡住。"""
    from exporters.report_exporter import ReportExporter

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = {a for a in sys.argv[1:] if a.startswith("-")}
    rid = args[0] if args else pick_run(hints)
    if not rid:
        print(f"✗ {script_name}：没有可分流的 run。先跑 `python run.py test` 或 "
              f"`python run.py qoder-plan`，或用 `python scripts/_convert_legacy_result.py <json>` "
              f"转换历史结果（转换后跑 `python run.py triage <run_id>`）")
        return 1
    try:
        if "--legacy-4state" in flags:
            from core.triage import load_records, to_result_rows
            records, _, _ = load_records(rid)
            report = ReportExporter().build_and_save(rid, to_result_rows(records))
        else:
            report = ReportExporter().build_from_records(rid)
    except FileNotFoundError as e:
        print(f"✗ {e}")
        print("  本脚本不再接受手写结果数据（旧版把结果拄进源码，是报告失真的源头）。")
        print(f"  生成分流结论：python run.py triage {rid}")
        return 1

    s = report["summary"]
    if "总用例" in s:                                  # 分流版摘要
        print(f"\n[{rid}] 总 {s['总用例']}  通过 {s['通过']}  缺陷 {s['真实缺陷']}  "
              f"环境 {s['环境阻塞']}  数据 {s['数据前置未满足']}  用例 {s['用例问题']}  "
              f"执行 {s['执行未到位']}  待裁决 {s['待人工裁决']}")
        print(f"通过率 {s['通过率']}%  有效通过率 {s['有效通过率']}%  "
              f"发版建议: {report['gate']['note']}")
        return 1 if report["gate"]["blocks_exit_code"] else 0
    print(f"[{rid}] 总 {s['total']}  通过 {s['passed']}  失败 {s['failed']}  "
          f"错误 {s['errors']}  人工 {s['manual']}  通过率 {s['pass_rate']}（旧四态、无分流列）")
    return 0
```

- [ ] **Step 14.4: 三个入口改薄封装**

`scripts/gen_p0_report.py` 整体替换（原 11-136 行的 `results = [...]` 整块删除）：

```python
# -*- coding: utf-8 -*-
"""知识管理 P0 报告入口（薄封装）——数据源强制 `records.jsonl`。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _report_entry import main

if __name__ == "__main__":
    raise SystemExit(main("gen_p0_report", hints=("km", "知识管理")))
```

`scripts/gen_p2_report.py` 整体替换：

```python
# -*- coding: utf-8 -*-
"""知识管理 P2 报告入口（薄封装）——数据源强制 `records.jsonl`。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _report_entry import main

if __name__ == "__main__":
    raise SystemExit(main("gen_p2_report", hints=("p2", "km", "知识管理")))
```

`scripts/gen_iap_report.py` 整体替换：

```python
# -*- coding: utf-8 -*-
"""工业APP 报告入口（薄封装）——数据源强制 `records.jsonl`。

旧版在此文件里手写了 43 条结果与 BLOCKED 备注（把执行结果拄进源码），已全部删除；
那些历史事实可由 `python scripts/_convert_legacy_result.py <旧 test_result_*.json>` 回收。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _report_entry import main

if __name__ == "__main__":
    raise SystemExit(main("gen_iap_report", hints=("工业APP", "iap", "APP")))
```

Run: `python -m pytest tests/test_report_entry.py -v`
Expected: PASS，`8 passed`（5 个函数 + 参数化 3 个入口脚本）

- [ ] **Step 14.5: README 补分流说明**

在 `README.md` 的第五阶段表格（`:62-68`）最后一行 `- | logs/ | ...` **之前**插入一行：

```markdown
| 06 | `output/06_reports/triage/<run_id>/` | 结果分流产物：`records.jsonl`（执行事实）、`decisions.yaml`（人工拍板）、`pending_review.md`、`triage_用例修复清单.md`、`quarantine.md`、`gate.json`、`bug_drafts/` |
```

并在该表格之后（`### 支撑模块` 之前）插入小节：

````markdown
### 第 6 阶段补充：结果分流（Result Triage）

失败不再混成一坨：执行结果统一写进 `records.jsonl`，再由三层漏斗归因。

**当前唯一执行路径是 Qoder MCP 线**：`python run.py qoder-plan 模块名` 生成含契约与 `run_id` 的计划 → 在 Qoder 对话里按计划真操作浏览器 → 按契约写 `records.jsonl` → `python run.py triage {run_id} --validate` 校缺口与契约 → `python run.py triage {run_id}` 出分流与报告。Playwright 脚本线（`run.py test`）降为备用，结果本期不接入分流。

| 层 | 干什么 | 能不能定性「真实缺陷」 |
|---|---|---|
| 规则层 `core/triage.py` | 吃结构化事实（步骤 outcome、断言 verdict、错误关键字、前置三态） | ❌ 永不（铁律） |
| LLM 复判 `agents/triage_agent.py` | 只处理规则层拿不准的项，携需求原文送判 | 提案，不算数 |
| 人工门禁 `core/human_confirm.py` | 逐条 `[bug]/[case]/[env]/[data]/[skip]/[edit]/[q]` 拍板 | ✅ 只有这里能 |

```powershell
python run.py triage --list          # 看有哪些 run 待分流
python run.py triage <run_id>        # 规则层 + 人工门禁 + 分流报告
python run.py triage <run_id> --llm  # 先让 Qoder 对话复判规则层拿不准的项
```

- **8 段摘要**：总用例 / 通过 / 真实缺陷 / 环境阻塞 / 数据前置未满足 / 用例问题 / 执行未到位 / 待人工裁决（另有「其他异常」自检桶）
- **有效通过率** = 通过 / (总用例 − 环境阻塞 − 数据前置未满足)，与原通过率**并列展示**
- **假 PASS 治理**：步骤 `element_not_found` / `skipped` 时状态上限 `manual`，不再算通过
- **收尾门禁**：人在场（`HUMAN_CONFIRM=true`）有未裁决项→发版建议「❌ 不具备出结论条件」且退出码 1；CI 下结论为 **N/A** 且不阻塞
- **历史数据**：`python scripts/_convert_legacy_result.py qoder_workspace/test_result_P0_km_20260907.json` 一次转换，历史产物不作废
- **一键回退**：`.env` 里 `TRIAGE_ENABLED=false` → 完整退回旧四态行为与旧报告格式

> 分流产物在 `output/` 下，而 `.gitignore` 屏蔽 `output/*`，所以 `records.jsonl` / `decisions.yaml` **默认不入版本库**。需要把人工拍板证据纳入版本管理时，自行白名单（本计划未改 `.gitignore`）：
> `git add -f output/06_reports/triage/<run_id>/decisions.yaml`
````

- [ ] **Step 14.6: 端到端验收（两条线 + 退回 + 门禁）**

逐条跑「命令 → 期望」，任一不符回到对应任务修，**不得在报告层打补丁掩盖**（报告只呈现，判错在上游）。

1. **契约回归（线 2 历史数据）**

```powershell
python scripts/_convert_legacy_result.py qoder_workspace/test_result_P0_km_20260907.json
python run.py triage P0_km_20260907
```

Expected: `records.jsonl` 共 12 条（1 已执行 + 11 pending）；已执行的 `TC-CAT-001` 进 **`待人工裁决`**（R7），**不被判为环境或执行问题**（BUG-CAT-01/02 是真缺陷候选，定性留给人）；11 条 pending 因 `precondition_met=false` + 转换器已填 `unblock_hint` 落 **`数据前置未满足`**

2. **LLM 复判携需求原文**

```powershell
python run.py triage P0_km_20260907 --llm
```

Expected: 生成 `ai_workspace/triage_P0_km_20260907_prompt.md`（并复制到剪贴板）；文件内每条疑难用例带非空 `requirement` 字段（形如 `"CAT-01": "..."` 的需求原文行）；在 Qoder 对话里跑完并把 JSONL 回复粘回后，`llm_review.jsonl` 有行，重跑 `triage` 可见报告里 `判定来源` 出现 `llm`

3. **人工门禁与铁律**

人在场终端（`HUMAN_CONFIRM=true`）跑 `python run.py triage P0_km_20260907`：
- 选 `[bug]` 一条 → `bug_drafts/BUG-*.md` 出现，含关联用例、环境、复现步骤、预期/实际、需求来源、裁决备注
- 选 `[skip]` 但不填 `unblock_hint` → 被拒收回落 `待人工裁决`（不逃分母）
- 一路 `[q]` → 摘要里 `真实缺陷` **不得因 `[q]` 增加**（`[q]` 排除 PRODUCT_BUG / BLOCKED）

Expected: `decisions.yaml` 每条含 `final_category / decided_by / decided_at / overridden`

4. **三格式一致**

```powershell
python -c "from core.config import REPORT_FORMAT; print(REPORT_FORMAT)"; python run.py triage P0_km_20260907
```

Expected: `output/06_reports/{markdown,html,excel}/` 出现同一时间戳三份；HTML 6 张卡片 + 18 列 + BLOCKED 表 + 顶部门禁条；Excel `Test Results`（18 列）与 `BLOCKED` 两个工作表；MD 里 8 段桶相加 == 总用例且两个通过率并列

5. **门禁退出码**

```powershell
$env:HUMAN_CONFIRM="true"; python run.py triage P0_km_20260907; echo "exit=$LASTEXITCODE"
$env:HUMAN_CONFIRM="false"; python run.py triage P0_km_20260907; echo "exit=$LASTEXITCODE"
```

Expected: 故意留一条未裁决时，strict 为 `exit=1` 且发版建议为「❌ 不具备出结论条件」；report_only 为 `exit=0` 且结论 N/A（不假装否决也不假装放行）

6. **MCP 线端到端（本期唯一执行路径，不需被测系统在线也能验）**

```powershell
$env:TRIAGE_ENABLED="true"; python run.py qoder-plan 知识管理
python -c "import json,glob; p=glob.glob('output/06_reports/triage/*/plan_cases.json'); d=json.load(open(p[-1],encoding='utf-8')); print(d['run_id'], len(d['case_ids']))"
python run.py triage <上一步输出的 run_id> --validate
```

Expected: 计划含契约块与 `**run_id**:` 行；`plan_cases.json` 的用例数与计划里的 `### TC-` 个数一致；此时 `--validate` 应报**全部缺口**、**退出码 1**（因为还没执行）；再按契约手写 1 条 `records.jsonl` 后重跑，缺口数减 1。旧版根本拿不到这个能力。

> 线 1 真跑（`python scripts/run_test.py 知识管理`）本期**不做**（Task 5 延后）；二期恢复时补验：以前被静默跳过的 `未找到元素` 步骤应让该用例封顶 `执行未到位`。

7. **一键退回**

```powershell
$env:TRIAGE_ENABLED="false"; python run.py qoder-plan 知识管理
$env:TRIAGE_ENABLED="false"; python scripts/gen_p0_report.py P0_km_20260907 --legacy-4state
Select-String -Path qoder_workspace/test_plan_知识管理.md -Pattern '<TEST_PASSWORD>|登录账号'
```

Expected: 计划退回旧版 `PASS/FAIL` 表格且**不产生新 run 目录**；旧四态报告仍从 `records.jsonl` 生成，但**无 `分流类别` 列**、HTML 仍 5 卡片/14 列；**最后一条检查必须无输出**（证明开关关掉也不回填明文凭据）

8. **全量回归**

```powershell
python -m pytest tests -v
```

Expected: 全绿，`0 failed`（用例总数以各任务累加的实际为准，不预设固定数字）

- [ ] **Step 14.7: 确认未误改仓库配置，并提交**

Run: `git status --short`
Expected: 只有本任务改动的 6 个文件（`.gitignore` **不得**出现在列表里）

```powershell
git add scripts/_report_entry.py scripts/gen_p0_report.py scripts/gen_p2_report.py scripts/gen_iap_report.py README.md tests/test_report_entry.py
git commit -m "feat(triage): gen_*_report 入口改读统一契约，README 补分流说明"
```

---

## 完成判据（全部为「是」才算做完）

- [ ] `python -m pytest tests -v` 全绿，且 `tests/test_triage_rules.py` 里的铁律负向用例存在且通过
- [ ] MCP 线至少产出一次 `records.jsonl`（`qoder-plan` 生成契约 + 按契约写入，或转换器产物），且 `run.py triage {run_id} --validate` 跑通
- [ ] 新生成的 `test_plan*.md` **不含明文口令**，且 `git check-ignore` 确认已取消跟踪（工作区文件仍在）
- [ ] `qoder_workspace/test_result_P0_km_20260907.json` 能无损转换并跑出报告（契约回归样本可复现）
- [ ] 三份报告（MD/HTML/Excel）都含 `分流类别 / 判定来源 / 置信度 / 裁决人` 四列，BLOCKED 单独成表
- [ ] 严格模式下有未裁决项时 `python run.py triage` 退出码为 1；CI 模式为 0 且结论 N/A
- [ ] `TRIAGE_ENABLED=false` 时 `run.py qoder-plan` 与 `gen_*_report.py --legacy-4state` 行为与改造前一致（唯一例外：凭据脱敏不受开关控制）
- [ ] `run.py test` 与 `agents/tester_agent.py` 本期**一行未改**（`git diff` 确认，Playwright 备用线保持原样）
- [ ] 仓库内没有新增「把执行结果写进 Python 源码」的文件（`test_wrapper_scripts_have_no_hardcoded_results` 守住）
- [ ] 每个任务一次 commit，且未用过 `git add -A`（工作区本来就有大量无关未提交改动）

## 自审：spec 覆盖对照

| spec 小节 | 落地任务 |
|---|---|
| §3 数据契约（字段 / 枚举 / 前置三态 / `OK` 哨兵） | Task 2 |
| §4.1 假 PASS 治理（状态上限 `manual`） | Task 3 规则 R4 + Task 4 `derived_status`（作用于契约记录，**与线 1 无关，本期仍生效**）；线 1 自身静默跳过的治理→二期 Task 5 |
| §4.2 线 1 写契约 + 预检失败写 ENV_BLOCK | **本期不做**（Task 5 延后·二期，正文已写完可直接执行） |
| §4.3 MCP 线内嵌契约 + 硬性收尾门禁 + 缺口校验 + 凭据脱敏 | Task 6（Step 6.1–6.7），校验入 `--validate`（Task 13） |
| §4.3 旧数据一次性转换 + 契约回归样本 | Task 7 |
| §4.4 报告层重构（8 段摘要 / 两个通过率 / BLOCKED 独立表 / 三格式四列） | Task 11（MD）、Task 12（HTML、Excel） |
| §4.4 `to_result_rows` 反向映射 | Task 7 Step 7.2 定义，Task 14 Step 14.3 消费 |
| §5.1 规则层 R0–R8 + 铁律 | Task 3 |
| §5.2 LLM 复判（需求原文输入包 / 三条纪律 / 复用 brain） | Task 8 |
| §5.3 人工门禁（逐条选项 / `[q]` 作用域 / CI 不阻塞 / 优先级合并） | Task 4（合并）、Task 9（交互） |
| §6 下游动作（Bug 草稿 / 修复清单 / quarantine / 收尾门禁双模式） | Task 4（gate、quarantine）、Task 10（产物） |
| §7 文件级改动清单（含 `gen_*_report.py` 保留入口铲硬编码、README） | Task 13（run.py）、Task 14（入口 + README） |
| §8 错误处理（损坏行 / LLM 不合契约 / 缺 hint / 重复 case_id / 孤儿决策 / 非交互 / 一键回退） | Task 2（读写降级）、Task 4（回落）、Task 8（原文留存）、Task 9（`_safe_ask`）、Task 1+5（回退） |
| §9 测试策略 1–4 | Task 3/4 单测、Task 7 契约回归、Task 14 Step 14.6 端到端与门禁验证 |
| §10 YAGNI 边界 | 全计划无相关代码；quarantine 只记录不重跑（Task 10） |
| §12 配置项 | Task 1 |

**本期明确不做（实施时勿顺手加）**：线 1 Playwright 接入契约与假 PASS 治理（整份 Task 5，二期再做）、`run.py test` 的任何行为改动、FLAKY 自动重跑与 `retry_count` 利用、quarantine 统计看板、人工推翻模式自动沉淀新规则、BLOCKED 解除后自动跟跑、Jira/GitHub 同步、`test_actions` 中文动作解析重构、designer/reviewer 逻辑改动、`.qoder/skills/` 文档更新、`.gitignore` 放行分流产物、git 历史里的旧凭据改写（`filter-repo`）。

另：`core/triage.py` 的 `record_from_result()`（旧 result dict → 契约记录）本期**无调用方**，它是二期 Task 5 的适配器；Task 2 已给它的单测，保留不算死代码，但**不要因为“没人用”而删掉它，也不要本期把它接到线 1 上**。
