# 手动执行流水线 Checklist（探索 → 执行）

> 用法：在 Qoder 对话框按顺序触发 skill；每完成一步把 `[ ]` 改成 `[x]`。
> 模块名 = `<MODULE>`（替换为实际模块名）。
> 阶段 02、03 有"标准 / 加深"两档，二选一触发即可（加深为可选，独立选择互不影响）。
> 一步一停：每步完成停下出【阶段确认卡】等确认再进下一步；⏸=停点，⛔=需先清未拍板 ⬜；「继续到 Gx」可连放行到指定关；状态文件 qoder_workspace/pipeline_gate/<MODULE>.json。

```
模块流水线进度（<MODULE>）：
- [ ] 0  准备：确认 inputs/requirements、inputs/online_prototypes.yaml、.env 齐全
```

## 主线（每模块一轮）

```
- [ ] 1  00 探索        → explore-web-system ⏸G1
        触发："用 explore-web-system 探索 <MODULE>"
        产物：output/00_explore/（功能地图 + 探索记录，只记事实）

- [ ] 2  01 业务梳理    → business-analysis ⏸G2
        触发："用 business-analysis 梳理 <MODULE> 业务"
        产物：output/01_business/（业务全景图）

- [ ] 3  02 需求拆分    → analyze-requirements【标准】 ⏸G3⛔
        或（加深）      → comprehensive-requirements-analysis
        触发："用 analyze-requirements 拆分 <MODULE> 需求"
        产物：output/02_split_requirements/<MODULE>/（+加深版多产歧义/缺口/边界/质量报告）

- [ ] 4  02_5 双验鲜门禁 → module-deep-dive ＋ 02_5b 视觉验鲜二选一（插入需求理解之前；默认必做，豁免须记理由） ⏸G4⛔（深探后）→ ⏸G5⛔（对比后）
        4a 深探核对：module-deep-dive ⏸G4⛔
           触发："对 <MODULE> 做 module-deep-dive 深探核对"
           产物：output/00_explore/modules/<MODULE>-深探核对.md
           跳过条件：模块极简 / 纯回归 / 距全站探索极短且无发版 → 记录"跳过+理由"
        4b 视觉验鲜（**二选一，选择权在人**，4a 后执行） ⏸G5⛔
           4b-1 全自动：prototype-ui-compare（AI 双源采集对比）
              触发："用 prototype-ui-compare 对比 <MODULE> 原型与真实系统"
              产物：output/02_5_prototype_diff/<MODULE>/（元素对比报告 + 双源截图）
              豁免条件：无原型入口（记 N/A）/ 已有报告且无变更（只做增量）
              拍板闭环：需拍板项汇入 02 风险汇总 → python -X utf8 scripts/_backfill_confirmations.py gen <MODULE> --format xlsx
              下游：03 三子步须显式引用报告（design-test-cases「存在时必引」）
           4b-2 人工轻量：prototype-ui-manual-compare（AI 只出页面清单，人工自行对比）
              触发："用 prototype-ui-manual-compare 给 <MODULE> 出人工对比页面清单"
              产物：output/02_5_prototype_diff/<MODULE>/页面清单.md（仅此一件，无差异报告）
              边界：零浏览器操作/零 MCP token；**产物不向下游流转**，人工差异记录（Excel/MD）自处理；需拍板/需 03 断言的差异由人工自行录入对应载体
              升级：后续需 AI 报告时直接再跑 4b-1（增量豁免口径不变）

- [ ] 5  03 用例设计    → design-test-cases【标准】（含 需求理解→测试点→用例 三子步）
        或（加深）      → comprehensive-test-case-design
        触发："用 design-test-cases 设计 <MODULE> 用例"
        产物：output/03_design/（需求理解.md + 测试点.md + 用例.md）
        门禁：⏸G6⛔（需求理解后停）→ ⏸G7⛔（测试点后停）→ ⏸G8⛔（用例后停）

- [ ] 6  04 评审        → 无独立 skill：跑 run_review 脚本，或对话人工评审 ⏸G9
        触发："评审 <MODULE> 用例" / `'' | python scripts/run_review.py <MODULE>`
        产物：output/04_review/（缺陷分级 P0/P1/P2）

- [ ] 7  05 导出        → export-test-docs（Excel 样式遵循 test-doc-format） ⏸G10
        触发："用 export-test-docs 导出 <MODULE>"
        产物：output/05_export/（test_cases + test_points 两个 xlsx）

- [ ] 8  06 执行        → 非 skill：先生成计划，再用 browser MCP 真实执行 ⏸G11（执行前必停）→ ⏸G12（执行后停）
        计划：`python run.py qoder-plan <MODULE>` → qoder_workspace/test_plan_<MODULE>.md（头部「前置样本准备」清单：执行前逐项清零 ⬜→✅，缺样本用例直接判 BLOCKED 不盲试）
        触发："读取 qoder_workspace/test_plan_<MODULE>.md 并用浏览器执行"
        执行顺序参考：requirement-testing-flow 阶段四（从左到右/从上到下/从外到里）
        产物：截图 + 执行结果（PASS/FAIL/manual/BLOCKED）

- [ ] 9  06 报告        → test-report-format ⏸G13（报告后停）
        触发："用 test-report-format 生成 <MODULE> 报告"
        产物：output/06_reports/（md / html / excel）

- [ ] 10 清理 ⏸G14（确认后执行）：删除执行期间创建的测试数据；还原移动/状态变更；共享数据只"确认→取消"
```

## 加深档何时选

- **02 加深（comprehensive-requirements-analysis）**：需求歧义/缺口不明、全新模块、多来源冲突、需风险驱动分析报告。
- **03 加深（comprehensive-test-case-design）**：逻辑/状态流转复杂、需系统化测试设计技术（EP/BVA/DT/ST/Pairwise）、存量用例质量差。
- 日常回归或需求清晰的模块用标准档即可；两档产出兼容，下游（深探/导出/报告）不受影响。

## 备注

- 00 探索为**全站一次性**；1~10 为**按模块循环**。
- 每轮开跑前清理该模块旧的 02、02_5~06 产物（全新一轮含旧 02_5 报告；仅增量补验时保留并在 4b 记录范围），统一时间戳，避免旧文件污染。
- 一步一停：每关（⏸）出【阶段确认卡】；跨会话恢复先读 qoder_workspace/pipeline_gate/<MODULE>.json；⛔ 关卡解除走拍板回填（gen → 业务填 → backfill → lint），门禁不设旁路；「继续到 Gx」可连放行到指定关。
- 浏览器执行技巧（toast 捕获 / EP 输入 / 弹窗可见性 / 副作用用例）见 module-e2e-test-pipeline 的 browser-execution.md。
