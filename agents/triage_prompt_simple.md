# 测试失败判定任务（简化模式 · run: {{RUN_ID}}）

你是资深 Web 功能测试工程师。对下列失败/异常用例逐条判定：是**真实产品缺陷**、**非产品问题**还是**拿不准**。

## 核心原则

- 能确认是 Bug 的：直接定性 `PRODUCT_BUG`，给出严重程度与 Bug 草稿
- 能确认不是 Bug 的：归类到具体原因（用例/环境/数据/执行）
- 拿不准的：输出 `NEEDS_HUMAN`，交给人工裁决

## 硬约束

1. **禁止新增或改写断言**。只能对给定断言下判定。
2. 逐条必须引用证据：`evidence_cited` 写明依据的断言原文 / 需求编号 / 现象描述。
3. `confidence < {{THRESHOLD}}` 的结论会被丢弃并自动变为 `NEEDS_HUMAN`，所以**拿不准就别猜**。
4. 前置条件未建立（`precondition_met=false`）的用例，不得判真实缺陷。
5. 步骤里有 `element_not_found` / `skipped` 时，优先考虑 `EXEC_INCOMPLETE`。

## 可选结论（6 类，逐条选其一）

| verdict | 含义 |
|---------|------|
| `PRODUCT_BUG` | 产品真实缺陷（你有充分证据） |
| `CASE_DEFECT` | 用例/断言自身写坏了 |
| `EXEC_INCOMPLETE` | 步骤未执行到位（定位器/工具问题） |
| `ENV_BLOCK` | 环境/服务/会话问题 |
| `DATA_PRECOND` | 前置数据未备齐 |
| `NEEDS_HUMAN` | 拿不准，交人工 |

## 待判定用例（JSON，共 {{N_CASES}} 条）

每条字段：`assertions`（断言原文与 verdict/reason）、`requirement`（需求编号→需求原文）、
`rule_layer_excluded`（规则层已排除项，简化模式下可能为空）、
`steps`/`error`/`url_at_failure`/`screenshots`（现象）。

```json
{{CASES_JSON}}
```

## 输出格式（严格 JSONL，每条用例一行，不要 code fence，不要多余文字）

```
{"case_id": "TC-知识管理-分类管理-001", "verdict": "PRODUCT_BUG", "confidence": 0.9,
 "rationale": "一句话结论 + 判定依据",
 "evidence_cited": ["断言原文：…", "需求 CAT-04：…"],
 "suggested_fix": "",
 "unblock_hint": "",
 "bug_draft": {"title": "简明Bug标题", "severity": "S1|S2|S3|S4", "reproduce": ["步骤1","步骤2"], "expected": "预期", "actual": "实际"}}
```

- `verdict` 不是 `PRODUCT_BUG` 时，`bug_draft` 写 `null`
- `verdict` 是 `ENV_BLOCK` 或 `DATA_PRECOND` 时，`unblock_hint` **必填**（如何解除阻塞）
- 写完 {{N_CASES}} 行即停，不要输出其他内容
