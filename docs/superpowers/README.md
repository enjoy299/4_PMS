# docs/superpowers —— 设计与实施计划的落盘目录

本目录存放 **Qoder `superpowers` skill 三段式工作流**（`brainstorming` → `writing-plans` → `executing-plans`）产出的两类文档：设计契约与实施计划。它们是特性开发的**权威输入**，被 skill 直接读取，请勿随意改名或挪动位置。

## 两个子目录的分工

| 子目录 | 角色 | 权威顺序 |
|--------|------|----------|
| `specs/` | **设计契约**（是什么/为什么）：背景与缺陷、范围、分类法、数据契约、关键决策记录、配置项 | **冲突时以 specs 为准** |
| `plans/` | **实施计划**（怎么做）：Task 拆分、Files 清单、`- [ ]` checkbox 逐步落地、单测用例、每步 commit 消息模板 | 派生自 specs，实施期间回填 checkbox |

Plans 顶部固定写有一行「设计文档（权威，勿再质疑范围）：`docs/superpowers/specs/…`」——两者是一对一配套关系，一个特性一份 spec、一份 plan。

## 命名规范

```
{YYYY-MM-DD}-{slug}.md
```

- **日期**：设计定稿日（spec 首次批准日；plan 若因 spec 修订而重排，用重排日）
- **slug**：kebab-case 特性名，例如 `result-triage`、`result-triage-design`（spec 加 `-design` 后缀以区分）
- **同日多稿**：追加 `-v2`、`-v3`；老稿保留不删，作为决策轨迹存档
- spec 与 plan 的 slug 保持一致，只是 spec 尾部多 `-design`，方便一眼配对

## 当前索引

| 特性 | Spec | Plan | 状态 | 最新动作 |
|------|------|------|------|----------|
| Result Triage（测试结果分流） | [`specs/2026-09-14-result-triage-design.md`](specs/2026-09-14-result-triage-design.md) | [`plans/2026-09-14-result-triage.md`](plans/2026-09-14-result-triage.md) | 设计中 → 实施进行中（14 Task，本期 MCP 单线） | `9ca6e35` 规则层 R1-R8 已落地 |

**配对提交锚点**：

- Spec 首版：`d65d699 docs(spec): 新增测试结果分流（Result Triage）设计 v1`
- Spec 最新修订：`a14aaa8 docs(triage): 范围改为 MCP 单线（Task 5 延后）+ Task 6 加固（run_id/缺口清单/凭据不落盘）`
- Plan 首版：`a14aaa8`（同上，spec 修订后同步产出的 14 Task 计划）
- Plan 最新触及：`9ca6e35`（实施回填 checkbox）

## 如何新增一份 spec / plan

1. **Brainstorm** —— 触发 `superpowers:brainstorming` skill，与用户逐节确认设计要点、拒绝面、铁律；产出的 markdown 落到 `specs/YYYY-MM-DD-{slug}-design.md`。
2. **拍板** —— 用户对 spec 每个决策节签字（对话里说"确认"或复述要点）。**未拍板前不要动 plans/**。
3. **Write Plan** —— 触发 `superpowers:writing-plans` skill，把 spec 拆成 N 个可独立提交的 Task，落到 `plans/YYYY-MM-DD-{slug}.md`，每步 checkbox 语法严格（`- [ ]` / `- [x]`）。
4. **Index 更新** —— 回到本 README 的「当前索引」表加一行；记录 spec/plan 首次落盘的 git commit hash。
5. **Execute** —— 触发 `superpowers:executing-plans` skill，逐 Task 实施；实施中每完成一个 step 就回填 plan 的 checkbox，同一个 Task 结束 commit 一次。

## 与 skill 的耦合（不要随意改名）

- `superpowers:writing-plans` 默认把新 plan 写到 `docs/superpowers/plans/`
- `superpowers:executing-plans` 会从当前工作目录向上定位 `docs/superpowers/plans/`，按 checkbox 追踪进度
- 若把文件挪到别的位置或改了文件名，上述两个 skill 会**找不到**，导致进度追踪失效、决策依据丢失

## 与其他目录的关系

- `output/` —— 框架运行时的实际产物（探索记录、需求拆分、用例、报告、分流结果）。specs/plans 是**施工图纸**，output 是**施工结果**，不重叠。
- `ai_workspace/` —— AI 一次性对话产生的 prompt/response 中间文件，非正式记录，会被反复覆盖。specs/plans 是**长期权威**。
- `agents/*_prompt.md` —— 各 Agent 的角色提示词，是运行期配置，不是设计文档。

## 变更本目录的规则

- **不要改写已经拍板的历史 spec**：设计有变时新增 `-v2` 版本，老版本保留，方便回溯"当时为什么这么做"
- **不要在 plan 里塞实施细节之外的内容**：如临时调试日志、废弃方案对比——那些写到 `ai_workspace/` 或直接 commit message 里
- **不要动 skill 契约段落**：plan 顶部的 `> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans …` 是 `executing-plans` skill 的定位锚点，删了会跑不起来
