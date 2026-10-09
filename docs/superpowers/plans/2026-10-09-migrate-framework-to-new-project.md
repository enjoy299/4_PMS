# 框架迁移到 4_PMS 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 AI Web 自动化测试框架从 `E:\Qodertest\air2_sys_test_10` 复制到 `E:\Qodertest\4_PMS`，清理旧项目数据/产物，起新 git 历史并推送 `https://github.com/enjoy299/4_PMS`。

**Architecture:** 三步走：① robocopy 模式排除复制（不带 .git/.venv/.env/缓存）→ ② 新目录内按精确清单清理旧产物与需求数据、写入新项目初始化文件 → ③ 静态/动态验证全绿后 git init 首次提交并推送远端。依据 spec：`docs/superpowers/specs/2026-10-09-migrate-framework-to-new-project-design.md`。

**Tech Stack:** Windows PowerShell（robocopy / Remove-Item）、Python 3.11 venv + pip、pytest、Playwright、git 2.55。

**执行注意（重要）：**
- 本计划所有写操作目标都是 `E:\Qodertest\4_PMS`，在 Qoder 工作区（air2_sys_test_10）**之外**——Bash 调用需申请越出沙箱的权限（用户会收到确认弹窗），属预期行为。
- 旧目录 `E:\Qodertest\air2_sys_test_10` 全程只读，唯一的写动作是计划/文档的 git 提交（在旧仓库）。
- 用户的 PowerShell 不支持 `&&`，多条命令用 `;` 分隔。
- 涉及中文模式串的扫描一律走 UTF-8 临时 python 脚本文件（tmp_ 前缀，已被 .gitignore 忽略），不走内联命令行。

**回滚总纲：** push 之前，删除 `E:\Qodertest\4_PMS` 全部内容后重跑 robocopy 即可完全重来；push 之后如需重来，删除远端 main 分支后重新 push。旧目录与旧远端零影响。

---

### Task 1: robocopy 排除式复制

**Files:**
- Create: `E:\Qodertest\4_PMS\`（整个目录树，除排除项外全量复制）

- [ ] **Step 1: 前置核验（只读）**

```powershell
Test-Path E:\Qodertest\4_PMS; (Get-ChildItem E:\Qodertest\4_PMS -Force -ErrorAction SilentlyContinue | Measure-Object).Count; git -C E:\Qodertest\air2_sys_test_10 status --short
```

Expected: `True`、`0`（目录存在且为空——2026-10-09 已探测确认）、git status 无输出（旧仓库干净）。若目录非空，**停止并询问用户**。

- [ ] **Step 2: robocopy 执行（含退出码归一）**

```powershell
robocopy E:\Qodertest\air2_sys_test_10 E:\Qodertest\4_PMS /E /XD .git .venv __pycache__ .pytest_cache repowiki better-harness-runs /XF .env *.log *.pyc tmp_* /NFL /NDL /NP /R:1 /W:1; if ($LASTEXITCODE -ge 8) { throw "robocopy 失败，退出码 $LASTEXITCODE" } else { Write-Output "robocopy 成功，退出码 $LASTEXITCODE（0-7 均为成功）"; $global:LASTEXITCODE = 0 }
```

Expected: 输出 robocopy 汇总（目录/文件计数）+ `robocopy 成功，退出码 1`。robocopy 退出码 0-7 都是成功（1=有文件复制），≥8 才失败；末尾把 `$LASTEXITCODE` 归零避免工具误报。

- [ ] **Step 3: 排除生效抽查**

```powershell
Test-Path E:\Qodertest\4_PMS\.git; Test-Path E:\Qodertest\4_PMS\.venv; Test-Path E:\Qodertest\4_PMS\.env; Test-Path E:\Qodertest\4_PMS\agents\tester_agent.py; Test-Path E:\Qodertest\4_PMS\.qoder\skills; (Get-ChildItem E:\Qodertest\4_PMS -Recurse -File | Measure-Object).Count
```

Expected: `False`、`False`、`False`、`True`、`True`、文件总数约 620±150（283 个 git 跟踪文件 + ai_workspace 54 + qoder_workspace 约 14 + output/04-06 共 289 + 其他未跟踪零散文件；.git/.venv/日志已排除）。若前三项出现 `True`，立即停止排查。

### Task 2: 新目录内清理旧产物与需求数据

**Files:**
- Delete: `E:\Qodertest\4_PMS\output\`（除 README.md 外全部）
- Delete: `E:\Qodertest\4_PMS\inputs\requirements\`（除 example.md 外全部）
- Delete: `E:\Qodertest\4_PMS\inputs\prototypes\`（除 .gitkeep 外全部）
- Delete: `E:\Qodertest\4_PMS\qoder_workspace\`（除 manual_pipeline_checklist.md 外全部）
- Delete: `E:\Qodertest\4_PMS\ai_workspace\`（除 README.md 外全部）
- Delete: `E:\Qodertest\4_PMS\logs\`（除 README.md 外全部）

所有删除命令都用「遍历 + 白名单过滤」模式，不写中文字面量路径，天然规避编码问题；作用域严格限定在 `E:\Qodertest\4_PMS` 之内。

- [ ] **Step 1: 清理 output/、ai_workspace/、logs/（各保留 README.md）**

```powershell
foreach ($rel in @('output','ai_workspace','logs')) { $p = "E:\Qodertest\4_PMS\$rel"; Get-ChildItem -LiteralPath $p | Where-Object { $_.Name -ne 'README.md' } | Remove-Item -Recurse -Force; Write-Output "$rel -> " ((Get-ChildItem -LiteralPath $p | ForEach-Object Name) -join ',') }
```

Expected: 三行输出均为 `... -> README.md`。

- [ ] **Step 2: 清理 inputs/requirements/（保留 example.md）与 inputs/prototypes/（保留 .gitkeep）**

```powershell
Get-ChildItem -LiteralPath 'E:\Qodertest\4_PMS\inputs\requirements' -File | Where-Object { $_.Name -ne 'example.md' } | Remove-Item -Force; Get-ChildItem -LiteralPath 'E:\Qodertest\4_PMS\inputs\prototypes' | Where-Object { $_.Name -ne '.gitkeep' } | Remove-Item -Recurse -Force; Write-Output "requirements -> " ((Get-ChildItem -LiteralPath 'E:\Qodertest\4_PMS\inputs\requirements' | ForEach-Object Name) -join ','); Write-Output "prototypes -> " ((Get-ChildItem -LiteralPath 'E:\Qodertest\4_PMS\inputs\prototypes' -Force | ForEach-Object Name) -join ',')
```

Expected: `requirements -> example.md`、`prototypes -> .gitkeep`。

- [ ] **Step 3: 清理 qoder_workspace/（保留 manual_pipeline_checklist.md）**

```powershell
Get-ChildItem -LiteralPath 'E:\Qodertest\4_PMS\qoder_workspace' | Where-Object { $_.Name -ne 'manual_pipeline_checklist.md' } | Remove-Item -Recurse -Force; Write-Output "qoder_workspace -> " ((Get-ChildItem -LiteralPath 'E:\Qodertest\4_PMS\qoder_workspace' | ForEach-Object Name) -join ',')
```

Expected: `qoder_workspace -> manual_pipeline_checklist.md`。

- [ ] **Step 4: 清理结果总核验**

```powershell
foreach ($rel in @('output','ai_workspace','logs','qoder_workspace')) { Write-Output "$rel : " ((Get-ChildItem -LiteralPath "E:\Qodertest\4_PMS\$rel" -Recurse -Force | ForEach-Object FullName) -join ';') }
```

Expected: 四个目录各自只剩白名单文件一行输出，无任何子目录残留。

### Task 3: 新项目初始化文件

**Files:**
- Create: `E:\Qodertest\4_PMS\.env.example`
- Overwrite: `E:\Qodertest\4_PMS\inputs\online_prototypes.yaml`

- [ ] **Step 1: 写入 .env.example（20 个配置项模板，无真实值）**

用 Write 工具创建 `E:\Qodertest\4_PMS\.env.example`，内容如下（键清单与 `core/config.py` 的 getenv 完全对齐）：

```dotenv
# ==========================================================
# AI Web 自动化测试框架 —— 环境配置模板（4_PMS）
# 使用：复制本文件为 .env（PowerShell: Copy-Item .env.example .env），
#       填入新项目实际值。.env 已被 .gitignore 忽略，不会入库。
# 必填仅 3 项：APP_URL、TEST_USERNAME、TEST_PASSWORD；其余均有默认值。
# ==========================================================

# ---------- 被测系统 ----------
APP_URL=http://localhost:3000            # 被测系统的网址
LOGIN_URL=                               # 登录页地址（可选，默认用 APP_URL/login）
TEST_USERNAME=admin                      # 登录用的测试用户名
TEST_PASSWORD=admin123                   # 登录用的测试密码
TEST_USERNAME_2=                         # 第二测试账号用户名（可选，权限对比场景）
TEST_PASSWORD_2=                         # 第二测试账号密码（可选）

# ---------- 在线原型（可选，python run.py prototype 抓取用）----------
PROTOTYPE_URL=                           # 在线原型的地址
PROTOTYPE_USERNAME=                      # 原型的登录用户名
PROTOTYPE_PASSWORD=                      # 原型的登录密码

# ---------- 执行行为 ----------
HEADLESS=true                            # 是否无头模式运行浏览器（true/false）
MAX_STEPS=30                             # 每条用例的最大步骤数
HUMAN_CONFIRM=true                       # 人工确认门禁（true/false）

# ---------- 环境预检（06 执行阶段，可选）----------
TARGET_SERVERS=                          # 本地服务启动命令，格式 command::port，多个用逗号分隔
TARGET_READY_TIMEOUT=30                  # 端口就绪探测超时（秒）
TARGET_READY_INTERVAL=2                  # 端口就绪探测间隔（秒）

# ---------- 导出格式（逗号分隔）----------
TESTPOINT_FORMAT=md,excel                # 测试点导出格式
TESTCASE_FORMAT=md,excel                 # 测试用例导出格式
REPORT_FORMAT=md,html,excel              # 测试报告导出格式

# ---------- 分流（triage）----------
TRIAGE_ENABLED=false                     # 是否启用 LLM 分流复判（true/false）
TRIAGE_SIMPLE=false                      # 使用简化版分流提示词（true/false）
```

- [ ] **Step 2: 重置 online_prototypes.yaml 为空模板**

用 Write 工具覆盖 `E:\Qodertest\4_PMS\inputs\online_prototypes.yaml`，内容：

```yaml
# ==========================================================
# 在线原型配置清单（4_PMS）
# 供 core/prototype_loader.py 登录原型站点并逐页截图，作为需求分析的 UI 参考。
# 每个模块的字段：
#   module:   业务模块名（与 inputs/requirements/ 拆分后的模块名一致）
#   name:     原型名称（展示用）
#   url:      原型站点地址
#   username: 原型登录用户名
#   password: 原型登录密码
#   pages:    待截图页面路径列表
# ==========================================================
prototypes: []
```

- [ ] **Step 3: 核验两个文件**

```powershell
(Get-Content E:\Qodertest\4_PMS\.env.example -Encoding UTF8 | Measure-Object -Line).Lines; Get-Content E:\Qodertest\4_PMS\inputs\online_prototypes.yaml -Encoding UTF8 | Select-Object -Last 1
```

Expected: 约 40 行；最后一行 `prototypes: []`。再抽查 `.env.example` 中无旧系统真实值（肉眼确认 APP_URL 是 localhost 默认值）。

### Task 4: 静态验证（残留扫描 + 敏感扫描）

**Files:**
- Create: `E:\Qodertest\air2_sys_test_10\tmp_scan_migration.py`（一次性扫描脚本，tmp_ 前缀不入库）

- [ ] **Step 1: 写扫描脚本（UTF-8 文件，规避中文内联传参问题）**

用 Write 工具在旧仓库根创建 `tmp_scan_migration.py`：

```python
# -*- coding: utf-8 -*-
"""迁移静态验证：残留扫描（旧模块名）+ 敏感扫描（旧 .env 值反查新目录）。"""
import os
import sys

OLD = r"E:\Qodertest\air2_sys_test_10"
NEW = r"E:\Qodertest\4_PMS"

MODULE_NAMES = ["工业APP", "知识管理", "项目管理", "基础数据管理", "首页", "个人空间"]
SCAN_DIRS = ["inputs", "output", "qoder_workspace", "ai_workspace", "logs"]

def iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".venv", "__pycache__", ".git", ".pytest_cache")]
        for name in filenames:
            yield os.path.join(dirpath, name)

print("== 残留扫描（旧模块名，inputs/output/qoder_workspace/ai_workspace/logs）==")
hits = 0
for rel in SCAN_DIRS:
    root = os.path.join(NEW, rel)
    if not os.path.isdir(root):
        continue
    for path in iter_files(root):
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if any(m in line for m in MODULE_NAMES):
                hits += 1
                print(f"[残留] {path}:{i}: {line.strip()[:80]}")
print(f"残留命中合计: {hits}（预期 1：manual_pipeline_checklist.md 提示行）")

print("== 敏感扫描（旧 .env 的 URL/凭据值反查新目录全树）==")
sensitive = []
for line in open(os.path.join(OLD, ".env"), encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, val = line.split("=", 1)
    val = val.strip()
    if len(val) >= 6 and key in ("APP_URL", "LOGIN_URL", "TEST_USERNAME", "TEST_PASSWORD",
                                 "PROTOTYPE_URL", "PROTOTYPE_USERNAME", "PROTOTYPE_PASSWORD"):
        sensitive.append((key, val))

cred_leaks, url_hits_docs, url_hits_other = 0, 0, 0
URL_KEYS = ("APP_URL", "LOGIN_URL", "PROTOTYPE_URL")
for path in iter_files(NEW):
    if path.endswith((".pyc", ".png", ".jpg", ".xlsx", ".docx", ".gitignore")):
        continue
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        continue
    for key, val in sensitive:
        if val and val in text:
            in_docs = os.sep + "docs" + os.sep in path
            if key in URL_KEYS:
                if in_docs:
                    url_hits_docs += 1
                else:
                    url_hits_other += 1
                print(f"[URL] {path}: 含 {key} 的值")
            else:
                cred_leaks += 1
                print(f"[凭据] {path}: 含 {key} 的值")
print(f"凭据命中: {cred_leaks}（预期 0，任何位置都不允许）")
print(f"URL命中: docs/内 {url_hits_docs}（允许，历史spec文字），docs/外 {url_hits_other}（预期 0）")
ok = hits <= 1 and cred_leaks == 0 and url_hits_other == 0
print("静态验证:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
```

- [ ] **Step 2: 执行扫描**

```powershell
python E:\Qodertest\air2_sys_test_10\tmp_scan_migration.py
```

Expected: `残留命中合计: 1`（manual_pipeline_checklist.md 的提示行）；`凭据命中: 0`；`docs/外 0`（docs/ 内若有 URL 命中属历史 spec 文字，可接受）；末行 `静态验证: PASS`，退出码 0。
若 `凭据命中 > 0` 或 `docs/外 URL > 0` 或残留超出 1 处：**停止，逐条评估命中文件**（删除该文件或脱敏后重扫），不得盲目放行。

- [ ] **Step 3: 删除扫描脚本（保持旧仓库干净）**

用 DeleteFile 工具删除 `E:\Qodertest\air2_sys_test_10\tmp_scan_migration.py`。

### Task 5: 环境重建 + 动态验证

**Files:**
- Create: `E:\Qodertest\4_PMS\.venv\`（虚拟环境）

- [ ] **Step 1: 旧仓库跑 pytest 建立基线（区分迁移问题 vs 存量问题）**

```powershell
Set-Location E:\Qodertest\air2_sys_test_10; .venv\Scripts\python.exe -m pytest -q
```

Expected: 全绿（16 个测试文件）。若有失败：记录失败项为**存量问题**，继续迁移（新仓库预期与基线一致），但在最终汇报中如实列出。

- [ ] **Step 2: 新目录建 venv + 装依赖**

```powershell
python -m venv E:\Qodertest\4_PMS\.venv; E:\Qodertest\4_PMS\.venv\Scripts\python.exe -m pip install -r E:\Qodertest\4_PMS\requirements.txt --quiet
```

Expected: pip 正常完成（首次约 2-5 分钟，超时则放后台跑）。注意 requirements.txt 含 playwright、pytest、openpyxl、python-dotenv、rich、pyyaml 等。

- [ ] **Step 3: 安装 Playwright 浏览器**

```powershell
E:\Qodertest\4_PMS\.venv\Scripts\python.exe -m playwright install chromium
```

Expected: Chromium 下载完成（约 150MB，2-10 分钟视网络，超时放后台）。若网络受限下载失败：设置镜像环境变量重试一次（PowerShell：`$env:PLAYWRIGHT_DOWNLOAD_HOST='https://npmmirror.com/mirrors/playwright'; E:\Qodertest\4_PMS\.venv\Scripts\python.exe -m playwright install chromium`），仍失败则汇报并询问用户代理配置。

- [ ] **Step 4: 新目录跑 pytest（对照基线）**

```powershell
Set-Location E:\Qodertest\4_PMS; .venv\Scripts\python.exe -m pytest -q
```

Expected: 与 Step 1 基线一致（理想为全绿）。若因缺 .env 报错：先 `Copy-Item .env.example .env` 再跑（全默认值）。新出现的失败（基线没有的）必须排查后才可继续。

- [ ] **Step 5: CLI 冒烟**

```powershell
Set-Location E:\Qodertest\4_PMS; .venv\Scripts\python.exe run.py help
```

Expected: 正常输出命令帮助（pipeline/business/analyze/testpoints/testcases/review/export/test/qoder-plan/solidify/triage/explore/prototype 等子命令列表），无 import 报错。

### Task 6: git 全新历史 + 远端对接

**Files:**
- Create: `E:\Qodertest\4_PMS\.git\`（全新仓库）

- [ ] **Step 1: 初始化仓库**

```powershell
Set-Location E:\Qodertest\4_PMS; git init -b main
```

Expected: `Initialized empty Git repository in E:/Qodertest/4_PMS/.git/`（git 2.55 支持 -b）。

- [ ] **Step 2: 暂存并核验忽略规则生效**

```powershell
Set-Location E:\Qodertest\4_PMS; git add -A; (git status --porcelain | Measure-Object -Line).Lines; git status --porcelain | Select-String -Pattern '\.env|\.venv|output/0|\.log' | ForEach-Object { $_.Line }
```

Expected: 暂存约 **163±10** 行；第二条 Select-String 仅应输出 `.env.example` 一行（A 状态），不得出现 `.env`、`.venv`、`output/00~06` 子目录内容、任何 `.log`。若出现违规项：停下核查 .gitignore 是否被破坏。

- [ ] **Step 3: 首次提交**

```powershell
Set-Location E:\Qodertest\4_PMS; git commit -m "init: AI Web 自动化测试框架（迁移自 air_sys_test_05）"; git log --oneline
```

Expected: 恰好 1 个提交，输出该提交哈希。

- [ ] **Step 4: 配置远端并探测仓库存在性（spec 门禁：确认仓库已创建才 push）**

```powershell
Set-Location E:\Qodertest\4_PMS; git remote add origin https://github.com/enjoy299/4_PMS; git ls-remote origin
```

Expected: 列出远端引用（空仓库显示空输出、退出码 0 即存在）。
若报 `Repository not found` 或 `could not read from remote repository`：**停止并请用户在 GitHub 上创建 enjoy299/4_PMS 仓库（不要勾选初始化 README）**，创建后重跑 `git ls-remote origin` 再继续。若因网络超时：改用代理地址 `git remote set-url origin https://gh-proxy.com/https://github.com/enjoy299/4_PMS` 后重试。

- [ ] **Step 5: 推送**

```powershell
Set-Location E:\Qodertest\4_PMS; git push -u origin main
```

Expected: 推送成功，`main -> main` 且设置上游跟踪。若网络超时：`git remote set-url origin https://gh-proxy.com/https://github.com/enjoy299/4_PMS` 后重试一次（与旧项目同策略）。

- [ ] **Step 6: 终态核验**

```powershell
Set-Location E:\Qodertest\4_PMS; git log --oneline; git status --short; git branch -vv
```

Expected: 恰好 1 个提交；工作区干净；`main...origin/main` 已跟踪。

---

## 完成后交付汇报要点

按用户约定，最终汇报须包含：① 各 Task 执行结果与验证证据（pytest 基线对比、扫描 PASS、git 状态）；② 透明说明采纳项（robocopy 排除清单、gh-proxy 回退是否触发）；③ 回滚方式（push 前删目录重来 / push 后删远端分支）；④ 已知残留清单（tester_agent.py L389-392 知识管理硬编码、README/skill 文档示例文字、模块特定报告脚本——均记录在 spec 第 5 节，新项目首跑前调整）。
