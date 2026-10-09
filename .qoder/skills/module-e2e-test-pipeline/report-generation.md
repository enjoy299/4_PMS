# 报告生成手册（阶段 10）

用 `exporters/report_exporter.py` 的 `ReportExporter().build_and_save(suite_name, results)` 一次产出 **md / html / excel** 三格式（受 `core/config.py` 的 `REPORT_FORMAT` 控制，默认 `md,html,excel`），落盘到 `output/06_reports/{markdown,html,excel}/<时间戳>_<MODULE>.*`。范式参考 `scripts/gen_report.py`。

## results 每条用例的字段

```python
def A(text, passed, verifiable=True, reason=""):
    """一条断言：passed=三态之一；verifiable=False 表示无法自动验证（计入 manual）。"""
    return {"text": text, "passed": passed, "verifiable": verifiable, "reason": reason}

def R(cid, name, module, ctype, pri, status, dur, pre, steps, exp, tdata, tp, asserts, remark=""):
    return {
        "id": cid, "name": name, "module": module, "case_type": ctype, "priority": pri,
        "status": status, "duration": dur, "precondition": pre, "steps": steps,
        "expected": exp, "test_data": tdata, "req_source": REQ, "test_point_ref": tp,
        "assertions": asserts, "remark": remark,
    }
```

- `status`：`"pass"` / `"fail"` / `"manual"`（**三态**）。BLOCKED 一律记 `manual`。
- `case_type`：功能/边界/异常/权限…；`priority`：P0/P1/P2。
- `req_source`：需求追溯，如 `"11、工业APP.md / 02-分类管理"`。
- `test_point_ref`：对应测试点 ID（TP-…）。
- Excel 输出 **14 字段**：Case ID / Name / Module / Type / Priority / Status / Duration / Precondition / Steps / Expected / Test Data / Req Source / Test Point / Assertion Details（见 test-report-format skill）。

## BLOCKED → manual 映射

```python
# 阻塞用例：status=manual，断言 verifiable=False，reason 以 "BLOCKED:" 前缀写清根因
R("TC-知识管理-分类管理-002", "第二账号越权删除分类", CAT, "权限", "P0", "manual", 0,
  "需第二账号 zjj", "…", "…", "zjj 账号", "TP-知识管理-分类管理-002",
  [A("验证跨账号权限", None, False, "BLOCKED: 环境无第二账号 zjj，无法验证越权")],
  remark="待补样本复测")
```
> `passed=None` + `verifiable=False` 表示“未能自动判定”。真实 PASS 用 `passed=True`，真实 FAIL 用 `passed=False`（并在 reason 写实测 vs 预期）。

## 生成调用

```python
from exporters.report_exporter import ReportExporter
reporter = ReportExporter()
report = reporter.build_and_save(suite_name="<MODULE>", results=results)  # results 为上面构造的列表
print(report)  # 含各格式路径与汇总计数
```
把构造 `results` 的逻辑写成一个脚本（如 `scripts/gen_<module>_report.py`）便于复跑，运行时设 `PYTHONIOENCODING=utf-8` 避免 PowerShell GBK 乱码。

## 主报告（额外手写 md，放 output/06_reports/）

三格式报告是**机器产物**；另写一份**人读主报告** `<MODULE>_测试执行报告_<日期>.md`，结构：

```markdown
# <MODULE> 测试执行报告（<日期>）

## 一、执行汇总
| 指标 | 数值 |
|---|---|
| 用例总数 | N |
| PASS | n1 |
| FAIL | n2 |
| BLOCKED | n3 |
| 可执行通过率 | n1/(n1+n2) |

## 二、缺陷清单
| 编号 | 类型 | 严重度 | 现象 | 期望 | 定位 |
|---|---|---|---|---|---|
| BUG-01 | 缺陷 | 高 | 列表显示“已发布”，详情显示“编辑中” | 状态一致 | … |
| DIFF-01 | 需求偏差 | 中 | 实测“已发布” vs 需求“已入库” | 术语统一 | … |
| DEV-01 | 体验 | 低 | 编辑弹窗未全选原名称 | 便于修改 | … |

## 三、BLOCKED 专章（n3 条）
| 用例 | 阻塞根因 | 复测前置样本 |
|---|---|---|
| TC-知识管理-分类管理-002 | 无第二账号 | 预置 zjj 账号 |
| TC-工业APP-工业APP维护-007 | 无“编辑中”APP | 预置编辑中样本 |

## 四、关键实测行为
- 分类下有 APP → 删除被拦截：“当前分类下有工业APP，不允许删除！”
- 未产生版本才可删除；仅“编辑中”可入库；移动成功提示“已移动到临界节点”……

## 五、数据清理说明
- 自建 QD* 分类全部删除，残留校验为空；移动操作已还原；共享 APP 仅“确认→取消”未真删。

## 六、本轮框架能力发现
- HITL 全链路贯通；load_prompt 占位符 KeyError 缺陷；toast 捕获与 EP 原生 setter 两技巧可沉淀为通用能力。
```

## 截图

主报告引用 `output/06_reports/screenshots/<MODULE>_NN.png`（执行阶段存证）。核验三格式报告 + 主报告 + 截图均已落盘后，本阶段完成。
