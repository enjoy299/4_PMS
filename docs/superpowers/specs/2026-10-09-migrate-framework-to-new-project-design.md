# 框架迁移设计：复制到新项目 + 全新 git 历史

> 日期：2026-10-09 状态：用户已确认设计方案
> 目标：把本框架从 air2_sys_test_10（air_system 项目）复制到新项目目录，旧项目原样保留，新项目起新 git 历史并指向新远端仓库

## 1. 背景与目标

### 1.1 背景

当前仓库 = 通用框架代码 + air_system 项目数据/产物 的混合体：

- **框架**：`agents/ core/ exporters/ utils/ test_actions/ scripts/ tests/ run.py .qoder/skills/ .gitignore templates/` 等，与新项目无绑定，可直接复用；
- **项目数据**：`inputs/requirements/` 16 个 air_system 需求文档、`inputs/online_prototypes.yaml`（air_system 原型地址）、`inputs/prototypes/知识管理/` 截图；
- **项目产物**（已被 git 跟踪约 95 个文件）：`output/00_explore ~ 03_design` 的探索事实/业务全景图/拆分需求/用例、`qoder_workspace/` 的执行计划与结果 JSON；
- **项目特定脚本**：`test_scripts/test_知识管理.py`、`test_项目管理.py`、`工业APP_solidified.py` 及 `scripts/` 内模块定制报告脚本；
- git 远端为 `https://gh-proxy.com/https://github.com/enjoy299/air_sys_test_05.git`，与本地目录名 air2_sys_test_10 不一致（本目录当初即携带旧历史复制而来）。

### 1.2 目标

1. 框架在新目录 `E:\Qodertest\4_PMS` 可完整运行（pytest 全绿、`run.py help` 正常）；
2. 新目录不含旧项目的需求数据、产物、日志、prompt 与任何凭据（`.env` 绝不带走）；
3. 新 git 仓库历史干净：首次提交即纯框架 + 新项目初始化文件；
4. 旧项目 air2_sys_test_10 全程零改动，作为可回滚兜底与历史存档。

## 2. 已确认决策

| # | 决策 | 用户选择 |
|---|------|---------|
| 1 | 迁移形态 | **复制出去，旧项目原样保留**（非原地切换、非抽模板） |
| 2 | git 历史 | **全新干净历史**：新目录不带 `.git`，重新 `git init`；框架演进史仍完整保留在旧仓库 |
| 3 | 复制范围 | **全量代码都带**（含模块特定脚本 export_km_*/gen_iap_report/test_scripts 固化脚本、prev_*.py 残留），只清产物与需求数据 |
| 4 | 复制方式 | **robocopy 排除式**：一条命令 + 集中排除清单，规则可审计可复用；中文业务文件名复制后在第二层按精确清单清理 |

## 3. 迁移设计

### 3.1 第一层：robocopy 模式排除（机器产物/环境/敏感文件）

```
robocopy E:\Qodertest\air2_sys_test_10 E:\Qodertest\4_PMS /E
  /XD .git .venv __pycache__ .pytest_cache repowiki better-harness-runs
  /XF .env *.log *.pyc tmp_*
```

| 排除项 | 原因 |
|--------|------|
| `.git` | 全新历史的先决条件 |
| `.venv` | 新项目重建虚拟环境，旧环境含绝对路径不可移植 |
| `__pycache__`、`.pytest_cache`、`*.pyc` | 纯缓存 |
| `repowiki`、`better-harness-runs` | Qoder IDE 生成缓存（`.qoder/` 下子目录，skills 子目录保留） |
| `.env` | 含旧系统 APP_URL 与测试账号密码，**绝不带走** |
| `*.log`、`tmp_*` | 可再生调试产物 |

说明：robocopy 只读源目录，旧项目零写入。

### 3.2 第二层：新目录内清理与重置（精确清单）

第一层无法用通配安全处理中文业务文件名，复制完成后在新目录内按下表逐项处理：

| 位置 | 动作 | 保留 |
|------|------|------|
| `output/` | 删除全部内容（00_explore/01_business/02_split_requirements/03_design 的 95 个被跟踪产物，及本地存在的 04/05/06 运行产物） | 仅 `output/README.md`（运行时自动重建 00~06 子目录） |
| `inputs/requirements/` | 删除 15 个 air_system 需求与全局说明文档（1、首页.md ~ 12、文件预览专题.md、系统术语解释.md、关于研发流程图的优化.md、系统预览支持格式.md） | 仅 `example.md`（框架通用示例） |
| `inputs/prototypes/` | 删除 `知识管理/` 目录（2 张旧截图） | 仅 `.gitkeep` |
| `inputs/online_prototypes.yaml` | **重置为空模板**（见 3.4） | — |
| `qoder_workspace/` | 删除 test_plan*.md、explore_plan.md、solidify_plan_*.md、test_result_*.json、test.docx、iap_tooltip_test.png、pipeline_gate/ 等全部旧计划与结果 | 仅 `manual_pipeline_checklist.md`（通用流水线清单） |
| `ai_workspace/` | 删除全部旧 prompt/response 文件 | 仅 `README.md` |
| `logs/` | 删除 136 个旧运行日志 | 仅 `README.md` |

### 3.3 全量保留清单（按决策 3）

- **框架代码**：`agents/ core/ exporters/ utils/ test_actions/ run.py conftest.py requirements.txt skills-lock.json .gitignore README.md templates/`
- **scripts/ 全部 38 个**：含 `run_*.py` 通用入口与 export_km_*/gen_iap_report/gen_pm_export/_build_full_*_json 等模块特定脚本（旧模块名仅作参考）
- **tests/ 全部 16 个**：已核实全部使用 tmp_path 自建夹具，不依赖真实旧产物，新项目 pytest 应全绿
- **test_scripts/**：`test_知识管理.py`、`test_项目管理.py`、`工业APP_solidified.py`、`_debug_run.py`（参考资产）
- **.qoder/skills/**（12 个定制 skill）、**.agents/skills/**（外部技能包）、**skills-lock.json**
- **docs/superpowers/**（既有 spec/plan 演进文档）、**prev_*.py ×7、review_diff.txt**（用户选择保留的历史残留）

### 3.4 新项目初始化

1. **新建 `.env.example`**（旧项目没有，正好补上 `.gitignore` 中已预留的 `!.env.example` 放行规则）：
   - 列出 `core/config.py` 实际读取的全部 **20 个**配置项，按用途分组并附填写说明，不填任何真实值：
     - 被测系统：APP_URL、LOGIN_URL、TEST_USERNAME、TEST_PASSWORD、TEST_USERNAME_2、TEST_PASSWORD_2（第二测试账号，可选）
     - 在线原型：PROTOTYPE_URL、PROTOTYPE_USERNAME、PROTOTYPE_PASSWORD
     - 执行行为：HEADLESS、MAX_STEPS、HUMAN_CONFIRM
     - 环境预检（06 执行阶段，可选）：TARGET_SERVERS、TARGET_READY_TIMEOUT、TARGET_READY_INTERVAL
     - 导出格式：TESTPOINT_FORMAT、TESTCASE_FORMAT、REPORT_FORMAT
     - 分流：TRIAGE_ENABLED、TRIAGE_SIMPLE
   - 用户复制为 `.env` 后填新项目值（必填仅 APP_URL + 测试账号，其余均有默认值）
2. **重置 `inputs/online_prototypes.yaml` 为空模板**：

   ```yaml
   # 在线原型配置清单（新项目填写）
   # schema：module（业务模块名）/ name / url / username / password / pages（待截图页面路径列表）
   prototypes: []
   ```

### 3.5 git 全新历史

```
cd E:\Qodertest\4_PMS
git init -b main
git add -A
git commit -m "init: AI Web 自动化测试框架（迁移自 air_sys_test_05）"
git remote add origin https://github.com/enjoy299/4_PMS
git push -u origin main     # 待用户确认远端仓库已创建后执行
```

- 远端：`https://github.com/enjoy299/4_PMS`（用户提供的地址，不带 gh-proxy 前缀；若直连 push 失败，改用 `https://gh-proxy.com/https://github.com/enjoy299/4_PMS`，与旧项目同策略）

## 4. 验证清单（新目录内依次执行）

1. **环境重建**：`python -m venv .venv` → 激活 → `pip install -r requirements.txt` → `playwright install`
2. **单元测试**：`pytest`——预期全绿（tests/ 不依赖真实旧产物）
3. **CLI 冒烟**：`python run.py help` 正常输出
4. **残留扫描**：`inputs/ output/ qoder_workspace/ ai_workspace/ logs/` 内 grep 旧模块名（工业APP|知识管理|项目管理|基础数据管理|首页|个人空间）应零命中；唯一例外：保留的 `qoder_workspace/manual_pipeline_checklist.md` 开头提示行（“如 知识管理 / 工业APP / 项目管理”）属举例文字，预期 1 处命中。代码目录（agents/core/scripts/test_scripts/tests/docs）中的旧模块名属示例文字/参考脚本，允许保留
5. **敏感扫描**：新目录全树反查旧 .env 的凭据值（用户名/密码）应零命中；旧系统 URL 值仅允许出现在 `docs/superpowers/` 历史演进文档的示例文字中（spec 第 3.3 节选择保留 docs），其余位置零命中；`.env` 未带入，`.env.example` 无真实值

## 5. 已知残留与后续调整项（不阻塞迁移）

| 项 | 位置 | 处理时机 |
|----|------|---------|
| 「知识管理」导航跳过硬编码 | `agents/tester_agent.py` L389-392（`if "知识管理" in action: return "已跳过..."`） | 新项目首跑执行阶段前，按新模块名调整 |
| 旧模块名示例文字 | README、agents/core 注释、.qoder/skills 文档、scripts 文档字符串 | 不影响运行，按需顺手改 |
| 模块特定报告脚本 | `scripts/export_km_*` `gen_iap_report` 等 | 新项目出报告时参照改造或弃用 |

## 6. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 清理清单漏删旧产物 | 验证第 4 步残留扫描兜底；清单遗漏项在新仓库首次提交前可随时补删 |
| robocopy 排除过宽误伤 | 排除清单全部是缓存/环境/敏感文件，与业务代码无交集；完成后对比 `git ls-files` 差集核验 |
| 新仓库推送后才发现问题 | 旧项目零改动可随时重新复制；push 前新目录可整体删除重来（零风险窗口）；push 后如需重来仅删远端分支即可 |

**回滚方式**：迁移全程旧目录零写入、远端零推送——任何时刻不满意，删除 `E:\Qodertest\4_PMS` 整个目录即完全回滚；已 push 时额外删远端分支。

## 7. 待填项（已于 2026-10-09 由用户提供）

| 占位符 | 实际值 |
|--------|--------|
| `<NEW_DIR>` | `E:\Qodertest\4_PMS` |
| `<NEW_REMOTE>` | `https://github.com/enjoy299/4_PMS`（不带 gh-proxy 前缀，直连失败时回退加前缀） |
