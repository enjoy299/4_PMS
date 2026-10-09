"""
配置中心 —— 读取 .env 文件中的所有配置项。

测试人员只需要修改项目根目录下的 .env 文件，
这里会自动加载这些配置，无需修改本文件。

AI 分析由 Qoder 对话完成，无需配置 API Key。

配置分为以下几类：
  1. 目标系统配置 —— 要测试哪个网站、用什么账号登录
  2. 在线原型配置 —— 原型设计稿的地址
  3. 运行控制 —— 是否隐藏浏览器、最多执行几步等
  4. 导出格式 —— 测试报告要生成哪些格式
  5. 目录配置 —— 各种文件存放在哪里
"""
import re                # 用于正则表达式匹配
import os               # 用于读取环境变量
from pathlib import Path # 用于处理文件路径
from dotenv import load_dotenv  # 用于加载 .env 文件中的配置

# 加载项目根目录下的 .env 文件，把里面的键值对变成环境变量
load_dotenv()

# 项目根目录（config.py 在 core/ 下，所以往上跳两级就是项目根目录）
ROOT = Path(__file__).parent.parent

# ===== 目标系统配置（你要测试的那个网站） =====
APP_URL = os.getenv("APP_URL", "http://localhost:3000")   # 被测系统的网址
LOGIN_URL = os.getenv("LOGIN_URL")                        # 登录页地址（可选，默认用 APP_URL/login）
TEST_USERNAME = os.getenv("TEST_USERNAME", "admin")        # 登录用的测试用户名
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "admin123")     # 登录用的测试密码
# 第二个测试账号（可选，用于权限/跨账号可见性测试；.env 未配置则为空字符串）
TEST_USERNAME_2 = os.getenv("TEST_USERNAME_2", "")         # 第二测试账号用户名
TEST_PASSWORD_2 = os.getenv("TEST_PASSWORD_2", "")         # 第二测试账号密码

# ===== 在线原型图配置（可选，用于让 AI 看到 UI 设计稿） =====
PROTOTYPE_URL = os.getenv("PROTOTYPE_URL", "")            # 在线原型的地址
PROTOTYPE_USERNAME = os.getenv("PROTOTYPE_USERNAME", "")   # 原型的登录用户名
PROTOTYPE_PASSWORD = os.getenv("PROTOTYPE_PASSWORD", "")   # 原型的登录密码

# ===== 运行时控制 =====
# HEADLESS：是否隐藏浏览器窗口（true=不显示浏览器，false=能看到浏览器操作过程）
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
# MAX_STEPS：AI 操控浏览器时，每个测试用例最多执行多少步（防止无限循环）
MAX_STEPS = int(os.getenv("MAX_STEPS", "30"))
# HUMAN_CONFIRM：是否在不确定的地方暂停，等待人工确认
HUMAN_CONFIRM = os.getenv("HUMAN_CONFIRM", "true").lower() == "true"

# ===== 执行阶段（06）环境预检配置（均可选，默认不影响远程系统测试） =====
# TARGET_READY_TIMEOUT：开跑前探测 APP_URL 可达的最长等待秒数（默认 30）
TARGET_READY_TIMEOUT = int(os.getenv("TARGET_READY_TIMEOUT", "30"))
# TARGET_READY_INTERVAL：可达性探测的重试间隔秒数（默认 2）
TARGET_READY_INTERVAL = float(os.getenv("TARGET_READY_INTERVAL", "2"))
# TARGET_SERVERS：可选，测试本地 dev server 时由框架自动起停。
#   格式：多个服务用 ';;' 分隔，每个服务为 '命令::端口'。
#   例："cd backend && python server.py::3000;;cd frontend && npm run dev::5173"
#   留空（默认）= 不启动任何本地服务，仅做 APP_URL 可达性探测。
TARGET_SERVERS = os.getenv("TARGET_SERVERS", "")

# ===== 导出格式配置（测试结果可以输出为多种格式） =====
# 测试点导出格式，默认 Markdown + Excel
TESTPOINT_FORMAT = [f.strip() for f in os.getenv("TESTPOINT_FORMAT", "md,excel").split(",")]
# 测试用例导出格式，默认 Markdown + Excel（方便人工阅读）
TESTCASE_FORMAT = [f.strip() for f in os.getenv("TESTCASE_FORMAT", "md,excel").split(",")]
# 测试报告导出格式，默认 Markdown + HTML + Excel
REPORT_FORMAT = [f.strip() for f in os.getenv("REPORT_FORMAT", "md,html,excel").split(",")]


# ===== 目录配置（定义各种文件的存放位置） =====
# 输入目录（保持不变）
INPUTS_DIR = ROOT / "inputs"                   # 输入文件夹（需求文档、原型图等）
SPEC_DIR = INPUTS_DIR / "requirements"         # 需求文档目录（放 .md 或 .txt 文件）
PROTOTYPES_DIR = INPUTS_DIR / "prototypes"     # 本地原型截图目录（放 .png 文件）
ONLINE_PROTOTYPES_FILE = INPUTS_DIR / "online_prototypes.yaml"  # 在线原型配置文件

# 输出目录（所有阶段产出统一放在 output/ 下，按流水线顺序编号）
OUTPUT_DIR = ROOT / "output"                            # 输出根目录
EXPLORE_DIR = OUTPUT_DIR / "00_explore"                 # 第 0 步：系统探索 → 功能地图、页面探索记录
BUSINESS_DIR = OUTPUT_DIR / "01_business"               # 第 1 步：业务梳理 → 业务全景图（角色/权限/实体/流程/术语）
SPLIT_REQUIREMENTS_DIR = OUTPUT_DIR / "02_split_requirements" # 第 2 步：需求分析 → 拆分后的模块化需求文件
DESIGN_WORKSPACE_DIR = OUTPUT_DIR / "03_design"         # 第 3 步：设计用例 → 需求理解、测试点、用例
REVIEW_DIR = OUTPUT_DIR / "04_review"                   # 第 4 步：评审用例 → 评审报告
FINAL_CASES_DIR = OUTPUT_DIR / "05_export"              # 第 5 步：导出 → 最终测试用例（Excel 导出）
TESTPOINTS_DIR = OUTPUT_DIR / "03_design" / "test_points"    # AI 分析出的测试点（兼容旧版）
CASES_DIR = OUTPUT_DIR / "03_design" / "test_cases"          # AI 设计的测试用例（兼容旧版）

# 报告目录
REPORTS_DIR = OUTPUT_DIR / "06_reports"          # 第 6 步：测试报告总目录
MD_REPORTS_DIR = REPORTS_DIR / "markdown"        # Markdown 格式报告目录
HTML_REPORTS_DIR = REPORTS_DIR / "html"          # HTML 网页格式报告目录
EXCEL_REPORTS_DIR = REPORTS_DIR / "excel"        # Excel 表格格式报告目录
SCREENSHOTS_DIR = REPORTS_DIR / "screenshots"    # 测试截图存放目录

# --- 结果分流（Result Triage）配置 ---
TRIAGE_ENABLED = os.getenv("TRIAGE_ENABLED", "false").lower() in ("1", "true", "yes", "on")
TRIAGE_DIR = REPORTS_DIR / "triage"                    # 分流产物根目录
TRIAGE_CONF_THRESHOLD = float(os.getenv("TRIAGE_CONF_THRESHOLD", "0.7"))
# 简化分流模式：开启后跳过规则层，LLM 可直接定性 PRODUCT_BUG（不经人工门禁），
# 拿不准的才回落 NEEDS_HUMAN 交人工裁决。关闭则恢复完整三层分流铁律。
TRIAGE_SIMPLE = os.getenv("TRIAGE_SIMPLE", "false").lower() in ("1", "true", "yes", "on")

# 其他目录（保持不变）
LOGS_DIR = ROOT / "logs"                       # 运行日志存放目录
AI_WORKSPACE_DIR = ROOT / "ai_workspace"        # AI 交互工作区（提示词和响应文件）
TEST_SCRIPTS_DIR = ROOT / "test_scripts"        # 生成的 Playwright 测试脚本目录

# 自动创建所有需要的文件夹（如果已存在则跳过）
for d in [SPEC_DIR, PROTOTYPES_DIR, EXPLORE_DIR, BUSINESS_DIR, SPLIT_REQUIREMENTS_DIR, TESTPOINTS_DIR, CASES_DIR,
          DESIGN_WORKSPACE_DIR, REVIEW_DIR, FINAL_CASES_DIR,
          MD_REPORTS_DIR, HTML_REPORTS_DIR, EXCEL_REPORTS_DIR,
          SCREENSHOTS_DIR, TRIAGE_DIR, LOGS_DIR,
          AI_WORKSPACE_DIR, TEST_SCRIPTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def get_module_dir(base_dir: Path, module_name: str) -> Path:
    """
    获取模块专属的子目录路径。

    例如：get_module_dir(DESIGN_WORKSPACE_DIR, "知识管理")
    返回：output/03_design/知识管理/

    参数：
        base_dir: 基础目录（如 DESIGN_WORKSPACE_DIR）
        module_name: 模块名称（如 "知识管理"）

    返回：
        模块子目录路径
    """
    # 清洗模块名：去除数字前缀
    clean_name = re.sub(r"^\d+[、_.\-\s]+", "", module_name).strip()
    module_dir = base_dir / clean_name
    module_dir.mkdir(parents=True, exist_ok=True)
    return module_dir


def find_module_file(directory: Path, module_name: str, extensions: list[str] | None = None) -> Path | None:
    """
    在指定目录中模糊查找模块对应的文件（默认递归子目录）。

    匹配策略（按优先级）：
      1. 精确匹配文件名（如 '知识管理.md'）
      2. 文件名包含关键词（如 '7、知识管理.md' 包含 '知识管理'）
      3. 清洗数字前缀后匹配（如传入 '7、知识管理' 也能匹配 '知识管理.md'）

    目录约定：03_design 下按业务模块归类子目录，因此默认递归。
    同一模块内优先返回与模块名完全前缀匹配的文件（如 "11-工业APP-用例"），
    避免误匹配到同目录下的 "01-工业APP-测试点" 之类文件。

    参数：
        directory: 搜索目录
        module_name: 模块名称（可以带数字前缀，也可以不带）
        extensions: 要匹配的文件扩展名列表，如 ['.md', '.yaml']；为 None 则匹配所有文件

    返回：
        匹配到的文件路径，未找到则返回 None
    """
    if not directory.exists():
        return None

    # 清洗模块名：去除数字前缀（如 '7、知识管理' -> '知识管理'）
    clean_name = re.sub(r"^\d+[、_.\-\s]+", "", module_name).strip()
    search_names = [module_name]
    if clean_name and clean_name != module_name:
        search_names.append(clean_name)

    # 构建文件列表（递归子目录）
    if extensions:
        files = []
        for ext in extensions:
            dot_ext = ext if ext.startswith(".") else f".{ext}"
            files.extend(directory.rglob(f"*{dot_ext}"))
    else:
        files = [p for p in directory.rglob("*") if p.is_file()]

    # 策略 1：精确匹配（文件名 == 模块名）
    for f in files:
        if f.stem in search_names:
            return f

    # 策略 2：包含匹配（文件名包含模块名，或模块名包含文件名）
    for f in files:
        for name in search_names:
            if name in f.stem or f.stem in name:
                return f

    return None


def find_latest_understanding(actual_module: str, parent_module: str = "") -> Path | None:
    """
    查找子模块已存在的需求理解文件：根级固定名 + 子目录批次，按 mtime 取最新。

    兼容 03_design 的两种命名世代（数字前缀可带可不带）：
      - 根级固定名：{actual_module}-需求理解.md（understand 步骤产物）；
      - 子目录批次：{NN}-{stem}-需求理解_{时间戳}.md（testpoints 步骤产物，
        存放在 03_design/test_points/{parent_module}/ 下）。

    参数：
        actual_module: 子模块名（如 '知识维护'，允许带数字前缀）
        parent_module: 父模块名（如 '知识管理'，对应 test_points 下的子目录名）

    返回：
        最新一份需求理解文件路径；未找到返回 None
    """
    cands: list[Path] = []
    fixed = TESTPOINTS_DIR / f"{actual_module}-需求理解.md"
    if fixed.exists() and fixed.stat().st_size > 0:
        cands.append(fixed)
    sub = TESTPOINTS_DIR / parent_module
    if parent_module and sub.is_dir():
        clean = re.sub(r"^\d+[、_.\-\s]+", "", actual_module).strip()
        for p in sub.glob("*需求理解*.md"):
            if "archive" in p.parts or p.stat().st_size == 0:
                continue
            if re.sub(r"^\d+[、_.\-\s]+", "", p.stem).startswith(f"{clean}-需求理解"):
                cands.append(p)
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)
