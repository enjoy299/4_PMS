---
name: test-report-format
description: 测试报告标准格式规范。生成 Excel/Markdown/HTML 测试报告时使用，确保包含完整的14个字段（Case ID、Name、Module、Type、Priority、Status、Duration、Precondition、Steps、Expected、Test Data、Req Source、Test Point、Assertion Details）。当提到测试报告、导出报告、生成报告、Excel报告、Markdown报告时使用此 skill。
---

# 测试报告标准格式

## 适用范围

所有测试报告（Excel / Markdown / HTML）必须遵循此格式，确保字段完整、可追溯。

参考样例：
- Excel: `output/06_reports/excel/20260903_125350_知识管理.xlsx`
- Markdown: `output/06_reports/markdown/20260903_125350_知识管理.md`

---

## Excel 报告格式

### 文件命名

```
{时间戳}_{模块名}.xlsx
```
- 时间戳格式: `YYYYMMDD_HHMMSS`
- 示例: `20260903_125350_知识管理.xlsx`

### 存放目录

```
output/06_reports/excel/
```
直接放在 excel 目录下，**不创建模块子目录**。

### Sheet 结构

**Sheet 名**: `Test Results`

**第1行（标题）**: 合并 A1:N1，内容为 `{模块名} - Test Report`，字体加粗 14号

**第2行（概要）**: 合并 A2:N2，内容为 `Time: {时间}  Pass Rate: {通过率}  Duration: {总耗时}`

**第4行（表头）**: 14个字段列头，白字蓝底(#2E75B6)，加粗

**第5行起（数据）**: 每行一个测试用例

### 完整14个字段

| 列 | 字段名 | 说明 | 示例 |
|----|--------|------|------|
| A | Case ID | 用例编号 | TC-知识管理-分类管理-001 |
| B | Name | 用例名称 | 文档知识库下新建一级分类 |
| C | Module | 所属子模块 | 分类管理 |
| D | Type | 用例类型 | 正向 / 异常 / 状态 |
| E | Priority | 优先级 | P0 / P1 / P2 |
| F | Status | 执行状态 | pass / fail / error |
| G | Duration | 执行耗时 | 12.5s |
| H | Precondition | 前置条件 | 已登录系统，进入知识管理页面 |
| I | Steps | 操作步骤 | 1. 点击新建 2. 输入名称 3. 保存 |
| J | Expected | 预期结果 | 1. 弹窗关闭 2. 分类树中出现新分类 |
| K | Test Data | 测试数据 | 分类名称：测试分类A |
| L | Req Source | 需求来源编号 | CAT-01,CAT-02 |
| M | Test Point | 测试点ID | TP-知识管理-分类管理-001 |
| N | Assertion Details | 断言详情 | PASS: 弹窗关闭; FAIL: 状态未变 |

### 样式要求

- **表头**: 白字(#FFFFFF) + 蓝底(#2E75B6) + 加粗 + 细边框
- **pass 行**: Status 列绿底(#E2EFDA)
- **fail 行**: Status 列红底(#FCE4EC)
- **error 行**: Status 列橙底(#FFF3E0)
- **列宽**: A=14, B=30, C=10, D=8, E=8, F=8, G=10, H=30, I=35, J=30, K=20, L=12, M=12, N=40

### Assertion Details 格式

```
PASS: 断言描述1; PASS: 断言描述2; FAIL: 断言描述3
```

失败用例追加错误信息：
```
FAIL: 断言描述 [Error: 【缺陷】具体缺陷描述]
```

---

## Markdown 报告格式

### 文件命名

```
{时间戳}_{模块名}.md
```

### 存放目录

```
output/06_reports/markdown/
```

### 模板

```markdown
# {模块名} - Test Report

**Time**: {YYYY-MM-DD HH:MM}
**Pass Rate**: {通过率}% ({通过数}/{总数})
**Duration**: {总耗时}s

| Status | Count |
|---|---|
| Passed | {通过数} |
| Failed | {失败数} |
| Errors | {错误数} |

## Details

### [{STATUS}] [{Case ID}] {Name}
- Priority: {Priority} | Type: {Type} | Module: {Module}
- Test Point: {Test Point} | Req Source: {Req Source}
- Precondition: {Precondition}
- Steps: {操作步骤}（如有）
- Expected: {预期结果}（如有）
- Test Data: {Test Data}（如有）
- [{STATUS}] {断言1}
- [{STATUS}] {断言2}

- **Error**: {缺陷描述}（仅 fail 时）

```
{观察项/问题说明}（可选，用代码块包裹）
```

### 每个用例包含

1. 标题行: `[PASS/FAIL] [TC-模块名-子模块名-NNN] 用例名称`
2. 基础信息行: `Priority | Type | Module`
3. 追溯信息行: `Test Point | Req Source`
4. 前置条件（有则写）
5. 操作步骤（有则写）
6. 预期结果（有则写）
7. 测试数据（有则写）
8. 每条断言单独一行 `[PASS/FAIL] 描述`
9. 失败用例追加 `**Error**: 缺陷描述`
10. 观察项用代码块包裹

---

## HTML 报告格式

### 文件命名与目录

```
output/06_reports/html/{时间戳}_{模块名}.html
```

### 关键要素

- 统计卡片: Passed(绿) / Failed(红) / Errors(橙) / Pass Rate(蓝)
- 详细表格包含完整14列
- Status 列用颜色区分: `.status-pass`(绿) / `.status-fail`(红) / `.status-error`(橙)
- 断言详情用彩色标签: `.assert-pass`(绿底) / `.assert-fail`(红底)

---

## 代码实现

使用 `exporters/report_exporter.py` 中的 `ReportExporter.build_and_save()` 方法生成报告。

调用方式：

```python
from exporters.report_exporter import ReportExporter

exporter = ReportExporter()
report = exporter.build_and_save(
    suite_name="知识管理",
    results=[
        {
            "id": "TC-知识管理-分类管理-001",
            "name": "文档知识库下新建一级分类",
            "module": "分类管理",
            "case_type": "正向",       # 正向/异常/状态
            "priority": "P0",
            "status": "pass",          # pass/fail/error
            "duration": 12.5,
            "precondition": "已登录系统",
            "steps": "1. 点击新建分类 2. 输入名称 3. 保存",
            "expected": "1. 弹窗关闭 2. 分类树中出现新分类",
            "test_data": "分类名称：测试分类A",
            "req_source": "CAT-01,CAT-02",
            "test_point_ref": "TP-知识管理-分类管理-001",
            "assertions": [
                {"text": "弹窗关闭", "passed": True},
                {"text": "分类树中出现'测试分类A'", "passed": True},
            ],
            "output": "",              # 可选，控制台输出
            "error": "",               # 可选，错误信息
        },
        # ... 更多用例
    ]
)
```

---

## 检查清单

生成报告前确认：

- [ ] 包含完整14个字段（不可省略任何字段）
- [ ] 文件直接放在格式目录下，不创建模块子目录
- [ ] 文件名使用时间戳+模块名格式
- [ ] Assertion Details 包含每条断言的 PASS/FAIL 状态
- [ ] 失败用例包含 Error 缺陷描述
- [ ] Excel 样式符合颜色和列宽要求
