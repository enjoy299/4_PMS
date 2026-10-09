---
name: gen-full-report
description: 为指定模块生成全量测试报告Excel。基于用例Markdown定义和JSON执行结果，组装完整数据并调用ReportExporter生成含Test Results(14列)+Bugs两个sheet的标准Excel报告。当用户要求生成全量报告、测试报告Excel、全量Excel，或提到 全量报告、生成报告、测试报告Excel 时使用此skill。
---

# 生成全量测试报告

## 概述

将「用例定义 Markdown」+「执行结果」组装为标准 JSON，再调用 `ReportExporter` 生成含 Test Results + Bugs 两个 sheet 的 Excel 报告。

## 前置条件

1. 用例 Markdown 已存在于 `output/03_design/test_cases/{模块名}/` 目录
2. 执行结果已记录（可以是 JSON 字典、对话中逐条确认的结果、或脚本执行日志）
3. `exporters/report_exporter.py` 中的 `ReportExporter` 可用

## 两步流程

### Step 1: 组装全量 JSON

使用模板脚本 `scripts/_build_full_json_template.py`：

```bash
# 复制到 scripts/ 并按模块改名
cp .qoder/skills/gen-full-report/scripts/_build_full_json_template.py scripts/_build_full_{模块缩写}_json.py
```

需要修改的变量（脚本顶部 `# ── 配置 ──` 区域）：

| 变量 | 说明 | 示例 |
|------|------|------|
| `MODULE_NAME` | 模块中文名 | `"工业APP"` |
| `OUT_JSON_NAME` | 输出 JSON 文件名 | `"test_result_full_iap.json"` |
| `CASE_MD_PATH` | 用例 Markdown 相对路径 | `"output/03_design/test_cases/工业APP/工业APP-用例_20260910_1200.md"` |

需要填充的两部分数据：

1. **`ALL_CASES`**：从用例 Markdown 提取每条用例的 `case_id / name / module / priority / case_type / req_source / test_point_ref`
2. **`executed`**：每条用例的执行结果 `status / duration_sec / note`
3. **`bugs`**：发现的 BUG 列表（可选）

**状态取值**（5 种标准状态）：`PASS` / `FAIL` / `BLOCKED` / `NOT_RUN` / `MANUAL`

运行：
```bash
python scripts/_build_full_{模块缩写}_json.py
```

输出：`qoder_workspace/{OUT_JSON_NAME}`，打印统计摘要。

### Step 2: 生成 Excel 报告

使用模板脚本 `scripts/_gen_full_report_template.py`：

```bash
cp .qoder/skills/gen-full-report/scripts/_gen_full_report_template.py scripts/_gen_full_{模块缩写}_report.py
```

需要修改的变量：

| 变量 | 说明 | 示例 |
|------|------|------|
| `RESULT_JSON` | Step 1 输出的 JSON 路径 | `ROOT / "qoder_workspace" / "test_result_full_iap.json"` |
| `SUITE_NAME` | 报告标题中的套件名 | `"工业APP_全量"` |

运行：
```bash
python scripts/_gen_full_{模块缩写}_report.py
```

输出：`output/06_reports/excel/{SUITE_NAME}/{时间戳}_{SUITE_NAME}.xlsx`

## Excel 报告格式

### Sheet 1: Test Results（14 列）

| 列名 | 来源 |
|------|------|
| Case ID | ALL_CASES.case_id |
| Name | ALL_CASES.name |
| Module | ALL_CASES.module |
| Type | ALL_CASES.case_type |
| Priority | ALL_CASES.priority |
| Status | executed.status → pass/fail/blocked/skipped/manual |
| Duration | executed.duration_sec |
| Precondition | 从用例 MD 解析 |
| Steps | 从用例 MD 解析 |
| Expected | 从用例 MD 解析 |
| Test Data | 从用例 MD 解析 |
| Req Source | ALL_CASES.req_source |
| Test Point | ALL_CASES.test_point_ref |
| Assertion Details | executed.note（PASS 时）或阻塞/失败原因 |

### Sheet 2: Bugs

| 列名 | 说明 |
|------|------|
| Bug ID | 自定义编号如 BUG-IAP-001 |
| Title | BUG 标题 |
| Severity | 严重/一般/轻微 |
| Reproduce | 复现步骤 |
| Expected | 预期行为 |
| Actual | 实际行为 |
| Req Source | 需求来源 |
| Affected Cases | 关联用例 ID 列表 |

### 样式

- 表头：蓝底白字（#2E75B6）
- PASS 行：浅绿底（#E2EFDA）
- FAIL 行：浅红底（#FCE4EC）
- BLOCKED 行：浅紫底（#E1BEE7）
- 副标题行：显示时间、通过率、各状态计数

## 用例 Markdown 解析规则

脚本自动从 `### TC-XXX-NNN` 开始的块中提取 `| 字段 | 值 |` 表格，映射关系：

```python
field_map = {
    "前置条件": "precondition",
    "操作步骤": "steps",
    "预期结果": "expected",
    "测试数据": "test_data",
}
```

- `<br>` / `<br/>` → 换行符 `\n`
- Markdown 链接 `[text](url)` → 纯文本 `text`

# 核心原则：缺数据就造，不许 BLOCKED

**铁律：测试执行中遇到「缺少前置数据」时，必须主动构造测试数据并继续执行，禁止标记 BLOCKED。**

BLOCKED 只允许用于真正不可控的外部因素（如系统宕机、网络中断）。因缺少测试数据而 BLOCKED 是执行者的失职，不是系统的限制。

### 常见场景与造数据策略

| 场景 | 错误做法 | 正确做法 |
|------|----------|----------|
| 需要「编辑中」状态的样本 | 标记 BLOCKED「需要编辑中样本」 | 在系统中创建/操作出编辑中状态的数据，然后继续测试 |
| 需要多个同类样本 | 标记 BLOCKED「需要多个样本」 | 批量创建多个样本数据，验证批量操作 |
| 需要多版本数据 | 标记 BLOCKED「需要多版本」 | 对同一对象执行多次入库/版本升级操作，构造多版本 |
| 需要第二账号验证可见性 | 标记 BLOCKED「需要第二账号」 | 从 `.env` 读取 `TEST_USERNAME_2` / `TEST_PASSWORD_2`，切换账号测试 |
| 需要特定入口/页面 | 标记 BLOCKED「需要入口」 | 实际导航到该入口，进入页面测试 |
| 需要关联数据（如模板关联APP） | 标记 BLOCKED「需要关联数据」 | 实际执行关联操作，验证关联结果 |

### 造数据的注意事项

1. **优先利用已有数据**：先检查系统中是否已有满足条件的数据，有则直接用
2. **构造时注意可清理性**：用 `QD测试` / `QDauto` 前缀命名，便于测试后清理
3. **破坏性操作要谨慎**：入库/删除等不可逆操作，先验证行为再确认结果
4. **记录造数据过程**：在 `note` 中记录如何构造的数据（如「封装matlab V1(编辑中)→V2(已发布)」）
5. **`.env` 中的账号要用起来**：第二账号 `TEST_USERNAME_2` 就是为可见性/权限测试准备的

### 工业APP模块实战案例

```
TC-APP-007: 需要编辑中APP → 找到「封装matlab V1(编辑中)」→ 执行入库 → V2(已发布) → PASS
TC-APP-008: 需要多个编辑中APP → 找到「面积计算V8」+「V19」→ 批量入库 → V9+V20 → PASS  
TC-APP-016: 需要多版本APP → 「封装matlab」入库后产生V1/V2 → 详情页版本下拉验证 → PASS
TC-APP-001: 需要第二账号 → 从.env取zjj/<TEST_PASSWORD> → 清除session → 切换登录 → 验证不可见 → PASS
TC-APP-024: 需要研发模板入口 → 实际导航到活动模板详情页 → 点工业app标签 → 验证 → PASS
```

## 注意事项

1. **JSON 是中间产物**：先确保 JSON 数据正确，再以此生成 Excel
2. **增量更新**：执行完新用例后，只需更新 `executed` 字典中对应条目，重新运行两个脚本即可
3. **BLOCKED 用例**：不应长期存在，缺数据就造数据，造完继续测
4. **报告时间戳**：Excel 文件名使用 `YYYYMMDD_HHMMSS` 格式，每次生成新文件不覆盖旧文件
