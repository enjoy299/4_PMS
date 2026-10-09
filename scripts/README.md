# scripts/ — 流水线执行脚本与导出工具

这个文件夹包含两类脚本：**流水线各阶段的独立执行脚本**（`run_*.py`，对应 `run.py` 里的命令，可单独跑某一阶段或指定模块），以及**一次性的 Excel 导出 / 报告生成工具**（`export_*.py`、`gen_*.py`、`_*.py`）。所有脚本均从**项目根目录**运行。

## 一、流水线阶段脚本（`run_*.py`，按 7 阶段顺序）

| 阶段 | 文件 | 对应命令 | 用途 |
|:----:|------|----------|------|
| 1 | `run_business.py` | `run.py business` | 业务梳理：探索产物 + 需求交叉比对 → 业务全景图 |
| 2 | `run_analyze.py` | `run.py analyze` | 需求分析：读取需求文档 → 拆分模块化需求 |
| 3 | `run_understand.py` | `run.py understand` | 需求理解：拆分需求 → 需求理解文档 |
| 3 | `run_design.py` | `run.py design` | 用例设计：基于需求 → 生成测试用例 |
| 4 | `run_review.py` | `run.py review` | 用例评审：检查测试用例质量 |
| 6 | `run_test.py` | `run.py test` | 测试执行：调用测试智能体用 Playwright 跑用例 |
| 辅助 | `run_explore.py` | `run.py explore` | 探索测试：遍历系统页面寻找潜在 bug |
| 准备 | `run_prototype.py` | `run.py prototype` | 原型截图：截取在线原型页面 |

```bash
python scripts/run_business.py 首页       # 指定模块（可带数字前缀，如 1、首页）
python scripts/run_analyze.py 知识管理
python scripts/run_test.py 知识管理
python scripts/run_explore.py             # 无参数，遍历全站
```

## 二、Excel 导出脚本（`export_*.py`）

把测试点 / 用例 / 报告的 Markdown 解析为标准格式 Excel。

| 文件 | 用途 |
|------|------|
| `export_module_excel.py` | **通用**「测试点 + 用例」合并双 Sheet Excel 导出（推荐）。用法：`python scripts/export_module_excel.py <模块名> [需求编号]` |
| `export_km_excel.py` | 知识管理「测试点 + 用例」导出（**已弃用**，保留为向后兼容入口，推荐改用 `export_module_excel.py 知识管理`） |
| `export_home_cases_excel.py` | 首页「测试点 + 用例」Markdown → test-doc-format 标准双 Sheet Excel |
| `export_home_analysis_excel.py` | 首页 `output/06_reports/首页/` 下多份 Markdown 分析报告 → 多 Sheet Excel 工作簿 |
| `export_home_test_report.py` | 首页标准 Excel 测试报告（test-report-format 14 字段 / Test Results Sheet） |

## 三、报告 / 模板生成脚本（`gen_*.py`）

| 文件 | 用途 |
|------|------|
| `gen_case_template.py` | 生成 `templates/test_case_template.xlsx` 用例模板（13 列，P0/P1/P2 优先级带色） |
| `gen_excel_report.py` | 生成符合完整字段要求的 Excel 测试报告（通用样式模板） |
| `gen_report.py` | 项目详情管理测试报告生成（内置示例执行结果，走 `ReportExporter`） |
| `gen_p0_report.py` | 知识管理模块 P0 用例 Excel 测试报告 |
| `gen_p2_report.py` | 知识管理模块 P2 用例 Excel 测试报告 |
| `gen_pm_export.py` | 项目管理「测试点 + 用例」合并双 Sheet Excel 导出 |

## 四、确认列桥接工具（`confirmation_bridge.py`）

业务拍板的 Excel 双向桥：**md 产物永远是确认列的唯一事实源**，xlsx 只是给业务的填写视图。

| 命令 | 用途 |
|------|------|
| `python scripts/confirmation_bridge.py export [模块...]` | 扫描 L1~L4 确认列的 ⬜ 项 → `output/05_export/待拍板清单_*.xlsx`（附「填写说明」sheet，业务只填 F 列） |
| `python scripts/confirmation_bridge.py apply [xlsx] [--dry-run]` | 读业务填好的清单，把结论原位回写源 md（⬜ → ✅，与手工就地拍板等效）；行号+原问句双重校验，行漂移/已拍板的行跳过并报「过期冲突」（退出码 1） |

## 五、一次性 / 辅助脚本（`_*.py`，下划线开头）

针对特定数据集或用于校验的临时脚本，非常规流水线环节。

| 文件 | 用途 |
|------|------|
| `_gen_p0_km_report.py` | 一次性：基于 `qoder_workspace/test_result_P0_km_*.json` + 知识管理 P0 用例计划，生成 Excel/Markdown/HTML 三格式报告 |
| `_verify_p0_report.py` | 校验上面生成的 P0 报告结构是否正确（读回 Excel 检查字段） |
