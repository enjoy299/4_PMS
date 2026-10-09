"""
测试执行智能体 —— 流水线第 5 步：使用 Playwright 执行测试用例。

改造说明：
  原版本使用 browser-use 的 Agent 让 AI 操控浏览器。
  改造后，生成 Playwright 纯脚本并直接执行，
  使用 test_actions/ 中的函数进行操作，无需 AI 参与浏览器控制。

支持两种用例格式：
  - YAML 格式（旧版，output/03_design/test_cases/ 目录）
  - Markdown 表格格式（新版，output/03_design/ 目录）

输出文件：output/06_reports/ 目录下的测试报告
"""
import re
import json
import yaml as yaml_lib
from pathlib import Path
from datetime import datetime
from core.config import (
    CASES_DIR, DESIGN_WORKSPACE_DIR, APP_URL, TEST_USERNAME, TEST_PASSWORD,
    HEADLESS, MAX_STEPS, LOGS_DIR, TEST_SCRIPTS_DIR,
    REPORTS_DIR, MD_REPORTS_DIR, HTML_REPORTS_DIR, EXCEL_REPORTS_DIR,
    TARGET_READY_TIMEOUT, TARGET_READY_INTERVAL, TARGET_SERVERS,
    find_module_file, get_module_dir,
)
from core.env_ready import (
    wait_for_url_ready, start_configured_servers, stop_servers, TargetNotReadyError,
)
from core.hooks import reset_run, take_screenshot
from test_actions import ALL_SKILLS
from exporters.report_exporter import ReportExporter
from utils.logger import get_logger

logger = get_logger("tester")


# ===== 断言作用域与语义常量（供 _check_assertion 使用） =====
# 结果/内容容器候选：断言优先在这些区域内验证，避免整页 body 误判（假通过）
RESULT_SCOPE_SELECTORS = [
    ".el-table", ".ant-table", "table",
    "[class*='result']", "[class*='list']", "[class*='table']",
    "main", "[role='main']",
]

# 结果行/列表项选择器：用于统计结果数量（判断“为空/无数据”）
RESULT_ROW_SELECTORS = [
    ".el-table__body tbody tr", ".ant-table-tbody tr",
    "table tbody tr", "[role='row']", "[class*='list'] [class*='item']",
]

# 否定语义短语：命中即视为负向断言（期望“不出现/没有/为空”）
NEGATION_PHRASES = [
    "不包含", "不出现", "不显示", "不返回", "不可见", "不存在", "不应", "不能",
    "没有", "未出现", "未显示", "未找到", "为空", "无结果", "无数据", "无匹配",
    "看不到", "消失", "无报错", "没有错误", "无异常",
]


class TesterAgent:
    """
    测试执行智能体类 —— 使用 Playwright 直接执行测试用例。
    """
    role = "tester"

    def __init__(self):
        self.reporter = ReportExporter()
        self._active_servers = []

    def _env_preflight(self) -> bool:
        """06 执行阶段环境预检：（可选）启动本地服务 + 探测 APP_URL 可达。

        返回 True 表示环境就绪可开跑；False 表示不可达，调用方应清晰中止。
        """
        try:
            self._active_servers = start_configured_servers(TARGET_SERVERS)
        except TargetNotReadyError as e:
            logger.error(f"环境预检失败：{e}")
            self._env_cleanup()
            return False
        if not wait_for_url_ready(APP_URL, timeout=TARGET_READY_TIMEOUT,
                                  interval=TARGET_READY_INTERVAL):
            logger.error(f"中止执行：被测系统在 {TARGET_READY_TIMEOUT}s 内不可达，请检查 .env 的 APP_URL 与网络/服务状态：{APP_URL}")
            self._env_cleanup()
            return False
        return True

    def _env_cleanup(self):
        """回收预检阶段启动的本地服务（未启动时为空操作）。"""
        stop_servers(self._active_servers)
        self._active_servers = []

    def _try_load_solidified_script(self, module_name: str) -> list | None:
        """尝试加载固化脚本。
        
        查找 test_scripts/{模块名}_solidified.py，存在则动态导入并返回 CASES 列表。
        不存在则返回 None（调用方回退到现有自然语言解析执行）。
        """
        # 清洗模块名
        clean_name = re.sub(r"^\d+[、_.\-\s]+", "", module_name).strip()
        script_path = TEST_SCRIPTS_DIR / f"{clean_name}_solidified.py"
        
        if not script_path.exists():
            logger.debug(f"无固化脚本：{script_path}")
            return None
        
        logger.info(f"发现固化脚本：{script_path}")
        
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                f"solidified_{clean_name}", script_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            cases = getattr(module, "CASES", None)
            if not cases:
                logger.warning(f"固化脚本无 CASES 注册表：{script_path}")
                return None
            
            logger.info(f"加载固化脚本成功：{len(cases)} 条用例")
            return cases
        except Exception as e:
            logger.error(f"加载固化脚本失败：{e}")
            return None

    def _run_solidified_cases(self, page, cases: list, module_name: str) -> list:
        """执行固化脚本中的用例。
        
        每个用例调用其 fn(page) 函数，捕获返回值作为结果。
        """
        results = []
        clean_name = re.sub(r"^\d+[、_.\-\s]+", "", module_name).strip()
        
        for case_info in cases:
            case_id = case_info.get("id", "TC-???")
            case_fn = case_info.get("fn")
            case_name = case_info.get("name", "")
            priority = case_info.get("priority", "P1")
            module = case_info.get("module", clean_name)
            
            if not case_fn:
                logger.warning(f"用例 {case_id} 无 fn 函数，跳过")
                continue
            
            reset_run(clean_name, case_id)
            start_time = datetime.now()
            
            try:
                result = case_fn(page)
                status = result.get("status", "error") if isinstance(result, dict) else "error"
                error = result.get("error", "") if isinstance(result, dict) else ""
            except Exception as e:
                status = "error"
                error = str(e)[:300]
                logger.error(f"  用例 {case_id} 执行出错：{e}")
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            results.append({
                "id": case_id,
                "name": case_name,
                "priority": priority,
                "module": module,
                "status": status,
                "duration": elapsed,
                "error": error,
                "assertions": [],
                "output": f"固化脚本执行：{status}",
            })
            
            logger.info(f"  {case_id} => {status.upper()} ({elapsed:.1f}秒)")
        
        return results

    def run_suite(self, module_name: str) -> dict | None:
        """执行一个模块的所有测试用例。"""
        case_file = find_module_file(CASES_DIR, module_name, [".yaml"])
        if not case_file:
            logger.error(f"用例文件未找到：{CASES_DIR}/{module_name}")
            return None

        actual_module = case_file.stem
        with open(case_file, "r", encoding="utf-8") as f:
            suite = yaml_lib.safe_load(f)

        if not suite or not isinstance(suite, dict):
            logger.error(f"{actual_module} 用例文件格式错误")
            return None

        cases = suite.get("cases", [])
        if not cases:
            logger.error(f"{actual_module} 中没有测试用例")
            return None

        logger.info(f"测试执行：{actual_module} - {len(cases)} 个用例")
        logger.info("模式：连续执行（失败后继续）")
        results = []

        # [已停用] 空壳 Playwright 脚本生成（仅产出注释、不可执行，易误导）
        # 如需恢复脚本模式产物，请让设计阶段产出结构化步骤后重写此函数
        # self._generate_playwright_script(actual_module, cases)

        # 环境预检（06）：不可达则清晰中止，避免刷全量 error 假失败
        if not self._env_preflight():
            return None

        # 使用 Playwright 执行
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=HEADLESS)
                context = browser.new_context(viewport={"width": 1920, "height": 1080})
                page = context.new_page()

                # 一次性登录
                logger.info("正在登录...")
                login_result = ALL_SKILLS["login"](page)
                logger.info(f"登录结果：{login_result}")

                # 一次性导航到模块
                logger.info(f"正在导航到模块：{actual_module}")
                nav_result = self._navigate_to_module_menu(page, actual_module)
                logger.info(f"导航结果：{nav_result}")

                # 连续执行所有用例
                for i, case in enumerate(cases, 1):
                    logger.info(f"\n  [{i}/{len(cases)}] {case.get('id', '')} - {case.get('name', '')}")

                    # 检查 session 是否有效
                    current_url = page.url
                    if "/login" in current_url:
                        logger.warning("Session 已过期，重新登录...")
                        login_result = ALL_SKILLS["login"](page)
                        nav_result = self._navigate_to_module_menu(page, actual_module)

                    # 执行用例（不登录不导航）
                    result = self._run_case(page, case, actual_module, skip_login_nav=True)
                    results.append(result)

                    # 用例执行后返回模块首页（重置状态）
                    if i < len(cases):
                        logger.info("  返回模块首页...")
                        self._navigate_to_module_menu(page, actual_module)
                        page.wait_for_timeout(1000)

                browser.close()
        except ImportError:
            logger.error("Playwright 未安装，请运行：playwright install chromium")
        except Exception as e:
            logger.error(f"Playwright 执行出错：{e}")
        finally:
            self._env_cleanup()

        if results:
            report = self.reporter.build_and_save(actual_module, results)
            return report
        return None

    def _run_case(self, page, case: dict, module_name: str = "", skip_login_nav: bool = False) -> dict:
        """执行单个测试用例。
    
        参数：
            page: Playwright Page 对象
            case: 用例字典
            module_name: 模块名称
            skip_login_nav: 是否跳过登录和导航（连续执行模式）
        """
        case_id = case.get("id", "TC-???")
        case_name = case.get("name", "未命名")
        
        # 重置计数器（传入模块和用例信息，用于日志文件命名）
        reset_run(module_name, case_id)
        priority = case.get("priority", "P2")
        steps = case.get("steps", [])
        assertions = case.get("assertions", [])
        test_point_ref = case.get("test_point_ref", "")
        module = case.get("module", "")
        case_type = case.get("case_type", "")
        precondition = case.get("precondition", "")
        test_data = case.get("test_data", "")
        req_source = case.get("req_source", "")
        cleanup = case.get("cleanup", "")
        remark = case.get("remark", "")
    
        start_time = datetime.now()
        result = {
            "id": case_id, "name": case_name, "priority": priority,
            "test_point_ref": test_point_ref, "status": "error",
            "duration": 0, "assertions": [{"text": a, "passed": False, "verifiable": True, "reason": ""} for a in assertions],
            "output": "", "error": "",
            # 额外字段：用于报告展示，方便用户定位
            "module": module,
            "case_type": case_type,
            "precondition": precondition,
            "test_data": test_data,
            "req_source": req_source,
            "cleanup": cleanup,
            "remark": remark,
        }
    
        try:
            outputs = []
    
            # 根据模式决定是否登录和导航
            if not skip_login_nav:
                # 独立执行模式：每个用例都登录
                login_result = ALL_SKILLS["login"](page)
                outputs.append(f"登录：{login_result}")
    
                nav_result = self._navigate_to_module_menu(page, module_name)
                outputs.append(f"导航：{nav_result}")
            else:
                outputs.append("（连续执行模式：跳过登录和导航）")

            # 按步骤执行
            for s in sorted(steps, key=lambda x: x.get("order", 0)):
                action = s.get("action", "")
                output = self._execute_action(page, action)
                outputs.append(f"步骤 {s.get('order', '')}: {output}")

                # 检查是否遇到找不到的元素，自动跳过
                if "未找到" in output or "找不到" in output:
                    logger.warning(f"  [!] 步骤 {s.get('order', '')} 未找到元素，自动跳过：{output}")
                    continue

            # 检查断言（三态：通过 PASS / 失败 FAIL / 不可自动验证 MANUAL）
            for i, a_text in enumerate(assertions):
                check_result = self._check_assertion(page, a_text)
                passed = check_result["passed"]
                verifiable = check_result.get("verifiable", True)
                reason = check_result.get("reason", "")
                result["assertions"][i]["passed"] = passed
                result["assertions"][i]["verifiable"] = verifiable
                result["assertions"][i]["reason"] = reason
                if passed:
                    tag = "PASS"
                elif verifiable:
                    tag = "FAIL"
                else:
                    tag = "MANUAL"  # 无法自动验证，需人工确认（不再假装通过）
                suffix = f"（{reason}）" if reason else ""
                outputs.append(f"断言 [{a_text}]: {tag}{suffix}")

            result["output"] = "\n".join(outputs)

            # 汇总用例状态：有明确失败 -> fail；无失败但有不可验证 -> manual；否则 pass
            has_fail = any((not a["passed"]) and a.get("verifiable", True)
                           for a in result["assertions"])
            has_manual = any((not a["passed"]) and (not a.get("verifiable", True))
                             for a in result["assertions"])
            if has_fail:
                result["status"] = "fail"
            elif has_manual:
                result["status"] = "manual"
            else:
                result["status"] = "pass"

            # 失败或需人工确认时截图
            if result["status"] in ("fail", "manual"):
                take_screenshot(page, f"{result['status'].upper()}_{case_id}")

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:300]
            logger.error(f"  用例 {case_id} 执行出错：{e}")
            # 出错时也截图
            try:
                take_screenshot(page, f"ERROR_{case_id}")
            except Exception:
                pass

        elapsed = (datetime.now() - start_time).total_seconds()
        result["duration"] = elapsed
        logger.info(f"  {case_id} => {result['status'].upper()} ({elapsed:.1f}秒)")
        return result

    def _execute_action(self, page, action: str) -> str:
        """根据动作描述执行对应的 Playwright 操作。"""
        action_lower = action.lower()

        # 简单的动作解析（根据关键词匹配技能函数）
        if "登录" in action or "login" in action_lower:
            return ALL_SKILLS["login"](page)
        elif "登出" in action or "logout" in action_lower:
            return ALL_SKILLS["logout"](page)
        elif "导航" in action or "打开" in action or "navigate" in action_lower:
            # 检查是否是导航到特定模块页面（如"导航到知识管理页面"）
            if "知识管理" in action:
                # 已经在登录后导航到知识管理菜单，此步骤可跳过
                return "已跳过：已在知识管理页面"
            # 尝试提取路径
            for word in action.replace("打开", " ").replace("导航到", " ").replace("访问", " ").split():
                if word.startswith("/") or word.startswith("http"):
                    return ALL_SKILLS["go_to_page"](page, word)
            # 如果没有找到 URL，返回提示而不是导航到首页
            return f"已跳过：{action}（无需导航）"
        # 增强：处理更多中文动作（必须在"点击"之前）
        elif "选中" in action or "选择" in action:
            # 选中某个元素/分类/条目 - 优先尝试树节点，再尝试菜单
            text = action.replace("点击", "").replace("选中", "").replace("选择", "").replace("分类", "").replace("条目", "").strip()
            # 去除引号
            text = text.strip('"').strip("'").strip('"').strip("'")
            if text:
                # 先尝试点击树节点（更精确）
                result = self._click_tree_item(page, text)
                if "未找到" not in result:
                    return result
                # 再尝试点击菜单
                result = ALL_SKILLS["click_menu"](page, text)
                return result if "未找到" not in result else f"未找到：{text}"
        elif "点击" in action or "click" in action_lower:
            # 提取按钮/菜单文字
            text = action.replace("点击", "").replace("按钮", "").strip()
            # 去除位置描述词（左侧、右侧、工具栏、顶部、底部等）
            for pos_word in ["左侧", "右侧", "工具栏", "顶部", "底部", "上方", "下方", "中间", "左边", "右边"]:
                text = text.replace(pos_word, "")
            # 优先提取引号内的文字（如 点击"文档知识库" -> 文档知识库）
            import re
            quote_match = re.search(r'["\u201c\u201d\'\u2018\u2019]([^"\u201c\u201d\'\u2018\u2019]+)["\u201c\u201d\'\u2018\u2019]', text)
            if quote_match:
                text = quote_match.group(1).strip()
            else:
                text = text.strip()
            if text:
                # 特殊处理：树形工具栏图标按钮
                if "新建分类" in text:
                    return ALL_SKILLS["click_new_category"](page)
                if "编辑分类" in text:
                    return ALL_SKILLS["click_edit_category"](page)
                if "删除分类" in text:
                    return ALL_SKILLS["click_delete_category"](page)
                if "上移" in text and "分类" not in text:
                    return ALL_SKILLS["click_move_up"](page)
                if "下移" in text and "分类" not in text:
                    return ALL_SKILLS["click_move_down"](page)
                # 先尝试点击树节点（对于分类等树形结构）
                result = self._click_tree_item(page, text)
                if "未找到" not in result:
                    return result
                # 再尝试按钮
                result = ALL_SKILLS["click_button"](page, text)
                if "未找到" not in result:
                    return result
                # 最后尝试菜单
                result = ALL_SKILLS["click_menu"](page, text)
                return result
        elif "填写" in action or "输入" in action or "fill" in action_lower:
            # 尝试多种格式解析
            # 格式 1: "输入 XXX: YYY" (冒号分隔)
            # 格式 2: "输入 XXX"YYY"" (引号分隔)
            import re
            
            # 先去除动作词
            clean_action = action.replace("填写", "").replace("输入", "").replace("在弹窗中", "").strip()
            
            # 尝试引号格式：输入分类名称"测试分类A"
            quote_match = re.search(r'([^"\u201c\u201d]+)["\u201c\u201d]([^"\u201c\u201d]+)["\u201c\u201d]', clean_action)
            if quote_match:
                label = quote_match.group(1).strip()
                value = quote_match.group(2).strip()
                return ALL_SKILLS["fill_input"](page, label, value)
            
            # 尝试冒号格式：输入 XXX: YYY
            parts = clean_action.split(":", 1)
            if len(parts) == 2:
                return ALL_SKILLS["fill_input"](page, parts[0].strip(), parts[1].strip())
            
            return f"已跳过：{action}（无法解析输入格式）"
        elif "截图" in action or "screenshot" in action_lower:
            return ALL_SKILLS["take_screenshot"](page, action[:15])
        elif "查看" in action or "检查" in action or "观察" in action:
            # 查看/检查某个元素 - 不再中间截图，只在失败时截图
            return f"已查看：{action}"
        elif "找到" in action or "查找" in action or "搜索" in action:
            # 搜索/查找某个元素
            text = action.replace("找到", "").replace("查找", "").replace("搜索", "").strip()
            if "搜索框" in action or "输入框" in action:
                return f"已找到搜索框"
            return f"已查找：{text}"
        elif "取消" in action:
            result = ALL_SKILLS["click_button"](page, "取消")
            if "未找到" in result:
                result = ALL_SKILLS["click_button"](page, "Cancel")
            return result
        elif "确认" in action or "确定" in action:
            result = ALL_SKILLS["click_button"](page, "确认")
            if "未找到" in result:
                result = ALL_SKILLS["click_button"](page, "确定")
            if "未找到" in result:
                result = ALL_SKILLS["click_button"](page, "OK")
            return result
        elif "保存" in action or "提交" in action:
            result = ALL_SKILLS["click_button"](page, "保存")
            if "未找到" in result:
                result = ALL_SKILLS["click_button"](page, "提交")
            if "未找到" in result:
                result = ALL_SKILLS["click_button"](page, "Save")
            return result
        elif "删除" in action:
            result = ALL_SKILLS["click_button"](page, "删除")
            if "未找到" in result:
                result = ALL_SKILLS["click_button"](page, "Delete")
            return result
        elif "新建" in action or "创建" in action or "新增" in action:
            # 知识管理模块的"新建分类"是图标按钮（第一个工具栏按钮）
            if "分类" in action:
                try:
                    # 尝试多种图标按钮选择器
                    icon_selectors = [
                        '.category-toolbar button:first-child',
                        '.toolbar button:first-child',
                        '.tool-bar button:first-child',
                        'div[class*="toolbar"] button:first-child',
                        'button:has(.icon-folder-add)',
                        'button:has(.el-icon-folder-add)',
                        'button:has(.anticon-plus)',
                    ]
                    for sel in icon_selectors:
                        el = page.query_selector(sel)
                        if el:
                            el.click()
                            page.wait_for_timeout(1500)
                            return "已点击：新建分类（图标按钮）"
                    # 如果图标选择器都失败，尝试点击第一个可见的按钮
                    first_btn = page.query_selector('button:visible')
                    if first_btn:
                        first_btn.click()
                        page.wait_for_timeout(1500)
                        return "已点击：新建分类（第一个按钮）"
                except Exception as e:
                    logger.debug(f"图标按钮点击失败：{e}")
            result = ALL_SKILLS["click_button"](page, "新建")
            if "未找到" in result:
                result = ALL_SKILLS["click_button"](page, "新建分类")
            if "未找到" in result:
                result = ALL_SKILLS["click_button"](page, "新建知识")
            if "未找到" in result:
                result = ALL_SKILLS["click_button"](page, "Create")
            return result
        elif "勾选" in action or "复选" in action:
            # 勾选复选框
            text = action.replace("勾选", "").replace("复选", "").strip()
            try:
                checkbox = page.query_selector(f'input[type="checkbox"][title="{text}"]')
                if not checkbox:
                    checkbox = page.query_selector(f'label:has-text("{text}") input[type="checkbox"]')
                if checkbox:
                    checkbox.check()
                    return f"已勾选：{text}"
                return f"未找到复选框：{text}"
            except Exception as e:
                return f"勾选异常：{e}"
        elif "重置" in action:
            result = ALL_SKILLS["click_button"](page, "重置")
            if "未找到" in result:
                result = ALL_SKILLS["click_button"](page, "Reset")
            return result
        elif "入库" in action:
            result = ALL_SKILLS["click_button"](page, "入库")
            return result
        elif "移动" in action:
            result = ALL_SKILLS["click_button"](page, "移动")
            return result

        # 默认：不再中间截图，只在失败时截图
        return f"已执行（通用）：{action}"

    def _click_tree_item(self, page, item_name: str) -> str:
        """
        点击树节点（如分类树中的"文档知识库"、"集成知识库"）。
        使用 Element Plus el-tree 组件选择器。

        参数：
            page: Playwright Page 对象
            item_name: 树节点名称

        返回：
            操作结果描述
        """
        try:
            # 等待页面加载
            page.wait_for_load_state("networkidle", timeout=5000)
            page.wait_for_timeout(1500)

            # 策略 1：使用 get_by_text 精确匹配（最可靠）
            try:
                element = page.get_by_text(item_name, exact=True).first
                if element.count() > 0:
                    element.click()
                    page.wait_for_timeout(1000)
                    return f"已点击树节点：{item_name}"
            except Exception as e:
                logger.debug(f"get_by_text 失败：{e}")

            # 策略 2：Element Plus el-tree 选择器
            el_tree_selectors = [
                f'span.tree-node-label:has-text("{item_name}")',
                f'span.custom-tree-node:has-text("{item_name}")',
                f'.el-tree-node__content:has-text("{item_name}")',
                f'[role="treeitem"]:has-text("{item_name}")',
            ]
            for selector in el_tree_selectors:
                try:
                    element = page.locator(selector).first
                    if element.count() > 0:
                        element.click()
                        page.wait_for_timeout(1000)
                        return f"已点击树节点（el-tree）：{item_name}"
                except Exception:
                    continue

            # 策略 3：Ant Design 树选择器（兼容其他系统）
            ant_selectors = [
                f'.ant-tree-title:has-text("{item_name}")',
                f'span.tree-node-label:has-text("{item_name}")',
                f'[title="{item_name}"]',
            ]
            for selector in ant_selectors:
                try:
                    element = page.locator(selector).first
                    if element.count() > 0:
                        element.click()
                        page.wait_for_timeout(1000)
                        return f"已点击树节点（ant-tree）：{item_name}"
                except Exception:
                    continue

            # 策略 4：JavaScript 遍历所有 span 查找精确文本
            try:
                body_text = page.text_content("body") or ""
                if item_name in body_text:
                    result = page.evaluate(f"""
                        () => {{
                            const spans = document.querySelectorAll('span.tree-node-label, span.custom-tree-node, .el-tree-node__content span, [role="treeitem"] span, span');
                            for (const el of spans) {{
                                if (el.textContent.trim() === '{item_name}') {{
                                    el.click();
                                    return 'exact';
                                }}
                            }}
                            // 模糊匹配
                            for (const el of spans) {{
                                if (el.textContent.trim().includes('{item_name}')) {{
                                    el.click();
                                    return 'fuzzy';
                                }}
                            }}
                            return null;
                        }}
                    """)
                    if result:
                        page.wait_for_timeout(1000)
                        return f"已通过 JS 点击树节点：{item_name}"
            except Exception:
                pass

            return f"未找到树节点：{item_name}"
        except Exception as e:
            return f"点击树节点异常：{e}"

    def _ask_user_for_help(self, page, original_action: str, error_output: str) -> str:
        """
        当找不到元素时，暂停执行并询问用户如何继续。

        参数：
            page: Playwright Page 对象
            original_action: 原始动作描述
            error_output: 错误输出信息

        返回：
            用户输入的指令
        """
        from rich.console import Console
        from rich.prompt import Prompt

        console = Console()

        console.print(f"\n[yellow]️ 执行遇到问题[/yellow]")
        console.print(f"  原始动作：[cyan]{original_action}[/cyan]")
        console.print(f"  问题描述：[red]{error_output}[/red]")
        console.print(f"\n[yellow]请选择操作：[/yellow]")
        console.print(f"  1. 输入新的操作指令（如：点击'XX'按钮）")
        console.print(f"  2. 输入'跳过'或'skip'跳过此步骤")
        console.print(f"  3. 输入'终止'或'stop'终止当前用例")

        try:
            user_input = Prompt.ask("\n[bold]请输入指令[/bold]", default="跳过")
            if user_input.lower() in ["终止", "stop", "exit"]:
                raise KeyboardInterrupt("用户选择终止用例")
            return user_input
        except (EOFError, KeyboardInterrupt) as e:
            if isinstance(e, KeyboardInterrupt):
                raise
            console.print("[dim]（非交互环境，自动跳过）[/dim]")
            return "跳过"

    def _navigate_to_module_menu(self, page, module_name: str) -> str:
        """
        登录后在左侧菜单中找到并点击模块对应的菜单项。
    
        参数：
            page: Playwright Page 对象
            module_name: 模块名称（如'7、知识管理'）
    
        返回：
            导航结果描述
        """
        # 清洗模块名，去除数字前缀（如'7、知识管理' -> '知识管理'）
        import re
        clean_name = re.sub(r"^\d+[、_.\-\s]+", "", module_name).strip()
        logger.info(f"正在导航到模块菜单：{clean_name}")

        # 快速检查：如果已经在目标页面，跳过导航但仍需等待页面加载
        current_url = page.url
        if "knowledgeManger" in current_url and "知识管理" in clean_name:
            logger.info(f"已在知识管理页面，跳过导航")
            # 确保页面内容已加载
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(1000)
            return f"已在页面：{clean_name}"
        if "项目管理" in clean_name and "projectList" in current_url:
            logger.info(f"已在项目管理页面，跳过导航")
            return f"已在页面：{clean_name}"
    
        try:
            # 等待页面基本加载完成（使用 domcontentloaded 而不是 networkidle，避免超时）
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            logger.info(f"当前页面 URL: {page.url}")

            # 构建候选名称列表：精确名 + 逐步缩短的候选名
            # 例如 "知识管理概述" -> ["知识管理概述", "知识管理"]
            candidate_names = [clean_name]
            # 尝试去掉常见后缀（概述、管理、模块等）
            for suffix in ["概述", "管理", "模块", "功能", "设计"]:
                if clean_name.endswith(suffix) and clean_name[:-len(suffix)] not in candidate_names:
                    candidate_names.append(clean_name[:-len(suffix)])
            # 也尝试取前 N 个字符（N 从长到短）
            for length in range(len(clean_name) - 1, max(2, len(clean_name) // 2), -1):
                short = clean_name[:length]
                if short not in candidate_names:
                    candidate_names.append(short)

            logger.info(f"候选菜单名称：{candidate_names}")
    
            # 对每个候选名称尝试精确匹配（找到第一个就返回）
            for name in candidate_names:
                menu_selectors = [
                    f'text="{name}"',
                    f'a:has-text("{name}")',
                    f'li:has-text("{name}")',
                ]
    
                for selector in menu_selectors:
                    try:
                        element = page.query_selector(selector)
                        if element:
                            logger.info(f"找到菜单元素（{name}）：{selector}")
                            url_before = page.url
                            element.click()
                            # 等待 URL 变化或页面加载
                            try:
                                page.wait_for_url(lambda url: url != url_before, timeout=5000)
                            except Exception:
                                pass
                            # 等待页面基本加载
                            try:
                                page.wait_for_load_state("domcontentloaded", timeout=5000)
                            except Exception:
                                pass
                            logger.info(f"已点击菜单（{name}），当前 URL: {page.url}")
                            # 额外等待确保内容渲染
                            page.wait_for_timeout(2000)
                            return f"已点击菜单：{name}"
                    except Exception as e:
                        logger.debug(f"选择器 {selector} 失败：{e}")
                        continue
                # 当前候选名没有匹配，继续尝试下一个候选名
    
            # 如果精确匹配全部失败，尝试模糊匹配（使用最短候选名）
            short_name = candidate_names[-1]
            try:
                body_text = page.text_content("body") or ""
                if short_name in body_text:
                    page.evaluate(f"""
                        () => {{
                            const elements = document.querySelectorAll('a, li, span, div');
                            for (const el of elements) {{
                                if (el.textContent.trim() === '{short_name}' ||
                                    el.textContent.trim().includes('{short_name}')) {{
                                    el.click();
                                    return true;
                                }}
                            }}
                            return false;
                        }}
                    """)
                    page.wait_for_load_state("networkidle", timeout=10000)
                    return f"已通过 JS 点击菜单：{short_name}"
            except Exception:
                pass
    
            logger.warning(f"未找到菜单：{clean_name}")
            return f"未找到菜单：{clean_name}"
        except Exception as e:
            logger.error(f"导航异常：{e}")
            return f"导航异常：{e}"

    # ========== 断言检查（三态：pass / fail / 不可自动验证 manual） ==========
    # 设计原则（消除“假通过”）：
    #   1. 不再用“整页 body 任意子串命中”判通过；
    #   2. 优先在结果容器（表格/列表/主区域）内验证，收窄作用域；
    #   3. 区分正向 / 负向（否定）语义；
    #   4. 无法可靠定位验证目标时，标记 verifiable=False（归为 manual），
    #      绝不默认通过——交人工确认，避免谎报绿色。

    def _check_assertion(self, page, assertion_text: str) -> dict:
        """检查单个断言。返回 {"passed": bool, "verifiable": bool, "reason": str}。"""
        text = (assertion_text or "").strip()
        if not text:
            return {"passed": True, "verifiable": True, "reason": "空断言，视为通过"}

        negative = self._is_negative_assertion(text)

        # 1) URL / 跳转断言
        if ("网址" in text) or ("url" in text.lower()) or ("跳转" in text):
            return self._assert_url(page, text, negative)

        # 2) 页面报错 / 异常 / 注入断言
        if any(k in text for k in ["报错", "错误", "异常", "注入"]) or "error" in text.lower():
            return self._assert_page_errors(page, text, negative)

        # 3) 空结果 / 无数据断言
        if any(k in text for k in ["为空", "无结果", "无数据", "无匹配", "没有数据",
                                   "列表为空", "结果为空", "暂无", "空空"]):
            return self._assert_empty_result(page, text, negative)

        # 4) 文本 / 元素存在性断言：必须有引号内的明确目标
        targets = [t for t in self._extract_quoted(text) if t]
        if targets:
            return self._assert_text_in_scope(page, text, targets, negative)

        # 5) 无法可靠验证（主观描述、缺少可定位目标）
        return {"passed": False, "verifiable": False,
                "reason": "无法自动验证：缺少可定位目标（建议用引号标注期望文本，或改为 URL/报错/数量断言）"}

    def _is_negative_assertion(self, text: str) -> bool:
        """判断是否为负向断言（期望“不出现/没有/为空”等）。"""
        return any(p in text for p in NEGATION_PHRASES)

    def _extract_quoted(self, text: str) -> list[str]:
        """提取断言文本中引号内的目标内容（支持中英文引号）。"""
        import re
        return re.findall(
            r'["\u201c\u2018\'\u300c]([^"\u201d\u2019\'\u300d]+)["\u201d\u2019\'\u300d]',
            text,
        )

    def _get_scope_text(self, page) -> tuple[str, bool]:
        """在结果容器（表格/列表/主区域）内取文本，避免整页误判。

        返回 (文本, 是否成功定位到容器)。
        """
        for sel in RESULT_SCOPE_SELECTORS:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    txt = loc.first.text_content() or ""
                    if txt.strip():
                        return txt, True
            except Exception:
                continue
        return "", False

    def _count_result_rows(self, page) -> int:
        """统计结果行数（表格行 / 列表项）。找不到返回 0。"""
        for sel in RESULT_ROW_SELECTORS:
            try:
                c = page.locator(sel).count()
                if c > 0:
                    return c
            except Exception:
                continue
        return 0

    def _assert_url(self, page, text: str, negative: bool) -> dict:
        """URL 断言：期望当前 URL 包含（或不包含）某片段。"""
        import re
        url = page.url or ""
        quoted = self._extract_quoted(text)
        expect = quoted[0] if quoted else ""
        if not expect:
            m = re.search(r'(/[A-Za-z0-9_\-/]+|https?://\S+)', text)
            expect = m.group(1) if m else ""
        if not expect:
            return {"passed": False, "verifiable": False, "reason": "URL 断言缺少期望片段"}
        hit = expect in url
        passed = (not hit) if negative else hit
        return {"passed": passed, "verifiable": True,
                "reason": f"URL 期望{'不含' if negative else '包含'} '{expect}'；实际 {url}"}

    def _assert_page_errors(self, page, text: str, negative: bool) -> dict:
        """页面报错断言：默认期望“无报错”。"""
        result = ALL_SKILLS["check_page_errors"](page)
        has_error = result.startswith("发现错误")
        expect_no_error = negative or any(k in text for k in
                                          ["无报错", "没有错误", "无异常", "不报错", "无 JS", "无注入", "正常"])
        passed = (not has_error) if expect_no_error else has_error
        return {"passed": passed, "verifiable": True, "reason": result}

    def _assert_empty_result(self, page, text: str, negative: bool) -> dict:
        """空结果断言：结果列表为空 / 无数据。"""
        scope_text, scope_found = self._get_scope_text(page)
        rows = self._count_result_rows(page)
        if not scope_found and rows == 0:
            return {"passed": False, "verifiable": False,
                    "reason": "未定位到结果容器，无法确认是否为空"}
        empty_marks = ["暂无数据", "无数据", "没有找到", "未找到", "无结果",
                       "暂无", "空空如也", "No Data", "no data"]
        mark_hit = any(m in scope_text for m in empty_marks)
        is_empty = (rows == 0) or mark_hit
        passed = (not is_empty) if negative else is_empty
        return {"passed": passed, "verifiable": True,
                "reason": f"结果行数={rows}；空态提示命中={mark_hit}"}

    def _assert_text_in_scope(self, page, text: str, targets: list[str], negative: bool) -> dict:
        """文本存在性断言：在结果容器内验证目标文本出现/不出现。"""
        scope_text, scope_found = self._get_scope_text(page)
        if not scope_found:
            return {"passed": False, "verifiable": False,
                    "reason": "未定位到结果容器（表格/列表/主区域），无法在正确作用域验证文本"}
        hits = [t for t in targets if t in scope_text]
        if negative:
            passed = len(hits) == 0
            reason = f"结果区域{'未出现' if passed else '出现了'}目标 {targets}"
        else:
            passed = len(hits) == len(targets)  # 正向要求全部命中（比“任意命中”更严格）
            reason = f"结果区域命中 {hits} / 期望 {targets}"
        return {"passed": passed, "verifiable": True, "reason": reason}

    def _generate_playwright_script(self, module_name: str, cases: list):
        """[已停用 · DEPRECATED] 生成 Playwright 测试脚本文件。

        注意：本函数产出的脚本仅包含步骤注释、并无实际可执行代码（空壳），
        容易让人误以为“框架能生成可运行脚本”。已从主执行链路摘除，
        保留定义仅为可回退。如需真正可执行的脚本模式，应让设计阶段产出
        结构化步骤（locator + action + value）后再重写本函数。
        """
        lines = [
            '"""',
            f'自动生成的 Playwright 测试脚本：{module_name}',
            f'生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}',
            '"""',
            'from playwright.sync_api import sync_playwright',
            f'APP_URL = "{APP_URL}"',
            f'USERNAME = "{TEST_USERNAME}"',
            f'PASSWORD = "{TEST_PASSWORD}"',
            '',
            'with sync_playwright() as p:',
            f'    browser = p.chromium.launch(headless={HEADLESS})',
            '    page = browser.new_page()',
            '',
        ]

        for case in cases:
            case_id = case.get("id", "TC")
            case_name = case.get("name", "")
            lines.append(f'    # === {case_id}: {case_name} ===')
            for s in sorted(case.get("steps", []), key=lambda x: x.get("order", 0)):
                lines.append(f'    # 步骤 {s.get("order", "")}: {s.get("action", "")}')
            lines.append('')

        lines.append('    browser.close()')

        script_path = TEST_SCRIPTS_DIR / f"test_{module_name}.py"
        script_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"  Playwright 脚本已生成：{script_path}")

    def run_all_suites(self):
        """执行所有模块的测试用例（共享浏览器会话，登录一次，跨模块复用）。"""
        # 收集所有用例文件
        md_files = self._collect_case_files()
        if not md_files:
            # 回退到旧版 YAML 格式
            files = sorted(CASES_DIR.glob("*.yaml"))
            if not files:
                logger.error("未找到测试用例文件")
                return
            logger.info(f"测试执行（YAML 格式）：{len(files)} 个套件")
            for f in files:
                logger.info(f"  执行套件：{f.stem}")
                self.run_suite(f.stem)
            return

        logger.info(f"测试执行：{len(md_files)} 个模块（共享会话模式）")

        # 环境预检（06）：不可达则清晰中止
        if not self._env_preflight():
            return

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=HEADLESS)
                context = browser.new_context(viewport={"width": 1920, "height": 1080})
                page = context.new_page()

                # 一次性登录
                logger.info("正在登录...")
                login_result = ALL_SKILLS["login"](page)
                logger.info(f"登录结果：{login_result}")

                # 逐模块执行
                for idx, md_file in enumerate(md_files, 1):
                    module_name = md_file.stem.replace("-用例", "").split("-", 1)[-1] if "-" in md_file.stem else md_file.stem
                    logger.info(f"\n{'='*50}")
                    logger.info(f"[{idx}/{len(md_files)}] 模块：{module_name}")
                    logger.info(f"{'='*50}")

                    # 检测会话是否过期，过期则重新登录
                    if not ALL_SKILLS["check_session"](page):
                        logger.warning("会话已过期，重新登录...")
                        login_result = ALL_SKILLS["login"](page)
                        logger.info(f"重新登录结果：{login_result}")

                    # 执行该模块的用例
                    self._execute_suite_with_page(page, md_file)

                browser.close()
                logger.info("\n所有模块执行完成，浏览器已关闭")

        except ImportError:
            logger.error("Playwright 未安装，请运行：playwright install chromium")
        except Exception as e:
            logger.error(f"Playwright 执行出错：{e}")
        finally:
            self._env_cleanup()

    def _collect_case_files(self) -> list[Path]:
        """收集所有 Markdown 用例文件（兼容不带与带时间戳后缀两种命名）。"""
        md_files: list[Path] = []
        # 新目录约定：DESIGN_WORKSPACE_DIR/test_cases/{模块名}/*-用例*.md
        if CASES_DIR.exists():
            md_files.extend(CASES_DIR.rglob("*-用例.md"))
            md_files.extend(CASES_DIR.rglob("*-用例_*.md"))
        # 兼容旧目录：直接放在 DESIGN_WORKSPACE_DIR 或子目录下一层
        md_files.extend(DESIGN_WORKSPACE_DIR.rglob("*-用例.md"))
        md_files.extend(DESIGN_WORKSPACE_DIR.rglob("*-用例_*.md"))
        return sorted(set(md_files))

    def _execute_suite_with_page(self, page, md_file: Path) -> dict | None:
        """
        使用已有的浏览器页面执行单个模块的测试用例。

        不创建浏览器、不登录——复用调用方提供的 page。
        执行完成后自动生成该模块的报告。

        参数：
            page: 已登录的 Playwright Page 对象
            md_file: Markdown 用例文件路径
        """
        module_name = md_file.stem.replace("-用例", "").split("-", 1)[-1] if "-" in md_file.stem else md_file.stem
        
        # 优先尝试加载固化脚本
        solidified = self._try_load_solidified_script(module_name)
        if solidified:
            logger.info(f"执行（固化脚本）：{module_name} - {len(solidified)} 条用例")
            results = []
            try:
                logger.info(f"导航到模块：{module_name}")
                nav_result = self._navigate_to_module_menu(page, module_name)
                page.wait_for_timeout(2000)
                
                results = self._run_solidified_cases(page, solidified, module_name)
            except Exception as e:
                logger.error(f"固化脚本执行出错：{e}")
            
            if results:
                report = self.reporter.build_and_save(module_name, results)
                return report
            return None
        
        # 无固化脚本，回退到自然语言解析模式
        cases = self.parse_markdown_cases(md_file)
        if not cases:
            logger.error(f"未解析到用例：{md_file}")
            return None

        logger.info(f"执行：{module_name} - {len(cases)} 个用例")
        results = []

        # [已停用] 空壳 Playwright 脚本生成（仅产出注释、不可执行，易误导）
        # self._generate_playwright_script(module_name, cases)

        try:
            # 导航到模块
            logger.info(f"导航到模块：{module_name}")
            nav_result = self._navigate_to_module_menu(page, module_name)
            logger.info(f"导航结果：{nav_result}")

            # 等待模块页面内容加载（如树形结构）
            logger.info("等待页面内容加载...")
            page.wait_for_timeout(3000)

            # 连续执行所有用例
            for i, case in enumerate(cases, 1):
                logger.info(f"  [{i}/{len(cases)}] {case.get('id', '')} - {case.get('name', '')}")

                # 检查 session 是否有效
                current_url = page.url
                if "/login" in current_url:
                    logger.warning("  Session 已过期，重新登录...")
                    ALL_SKILLS["login"](page)
                    self._navigate_to_module_menu(page, module_name)

                result = self._run_case(page, case, module_name, skip_login_nav=True)
                results.append(result)

                # 返回模块首页
                if i < len(cases):
                    logger.info("  返回模块首页...")
                    self._navigate_to_module_menu(page, module_name)
                    page.wait_for_timeout(1000)

        except Exception as e:
            logger.error(f"模块 {module_name} 执行出错：{e}")

        if results:
            report = self.reporter.build_and_save(module_name, results)
            return report
        return None

    # ========== Markdown 用例解析与执行 ==========

    def parse_markdown_cases(self, md_file: Path) -> list[dict]:
        """
        解析 Markdown 表格格式的测试用例文件。

        支持两种格式：
        1. 横排表格：所有用例在一个大表格中（列：用例 ID、用例标题、操作步骤等）
        2. 竖排表格：每个用例一个小表格（行：用例 ID、模块、测试步骤等）

        参数：
            md_file: Markdown 用例文件路径

        返回：
            用例字典列表
        """
        content = md_file.read_text(encoding="utf-8")
        
        # 检测格式：包含以下任一分隔行即为竖排小表格格式
        # 旧约定：“| 项目 | 内容 |”；新约定：“| 字段 | 值 |”（design-test-cases skill）
        vertical_markers = (
            "| 项目 | 内容 |", "|项目|内容|",
            "| 字段 | 值 |", "|字段|值|",
        )
        if any(m in content for m in vertical_markers) or "| 用例ID |" in content or "| 用例 ID |" in content:
            return self._parse_vertical_table_cases(content)
        
        # 否则使用横排表格解析
        return self._parse_horizontal_table_cases(content, md_file)

    def _parse_horizontal_table_cases(self, content: str, md_file: Path) -> list[dict]:
        """解析横排表格格式的用例文件（所有用例在一个大表格中）。"""
        lines = content.strip().split("\n")

        # 找到表格头部（包含 "用例 ID" 的行）
        header_idx = -1
        for i, line in enumerate(lines):
            if "用例 ID" in line and "|" in line:
                header_idx = i
                break

        if header_idx < 0:
            logger.error(f"未找到用例表格：{md_file}")
            return []

        # 解析表头
        raw_header = lines[header_idx].strip()
        if raw_header.startswith("|"):
            raw_header = raw_header[1:]
        if raw_header.endswith("|"):
            raw_header = raw_header[:-1]
        headers = [h.strip() for h in raw_header.split("|")]
        col_map = {h: idx for idx, h in enumerate(headers)}

        # 跳过分隔行
        data_start = header_idx + 1
        if data_start < len(lines) and "---" in lines[data_start]:
            data_start += 1

        # 解析数据行
        cases = []
        for line in lines[data_start:]:
            if not line.strip() or "---" in line:
                continue
            stripped = line.strip()
            if stripped.startswith("|"):
                stripped = stripped[1:]
            if stripped.endswith("|"):
                stripped = stripped[:-1]
            cells = [c.strip() for c in stripped.split("|")]
            if len(cells) < 3:
                continue

            case = {
                "id": self._get_cell(cells, col_map, "用例 ID"),
                "name": self._get_cell(cells, col_map, "用例标题"),
                "module": self._get_cell(cells, col_map, "模块"),
                "priority": self._get_cell(cells, col_map, "优先级") or "P1",
                "case_type": self._get_cell(cells, col_map, "用例类型"),
                "precondition": self._get_cell(cells, col_map, "前置条件"),
                "test_data": self._get_cell(cells, col_map, "测试数据"),
                "raw_steps": self._get_cell(cells, col_map, "操作步骤"),
                "raw_expected": self._get_cell(cells, col_map, "预期结果"),
                "cleanup": self._get_cell(cells, col_map, "清理动作"),
                "remark": self._get_cell(cells, col_map, "备注"),
                "req_source": self._get_cell(cells, col_map, "需求来源"),
                "test_point_ref": self._get_cell(cells, col_map, "测试点 ID"),
            }
            case["steps"] = self._parse_numbered_steps(case["raw_steps"])
            case["assertions"] = self._parse_numbered_items(case["raw_expected"])

            if case["id"]:
                cases.append(case)

        return cases

    def _parse_vertical_table_cases(self, content: str) -> list[dict]:
        """解析竖排表格格式的用例文件（每个用例一个小表格）。"""
        import re
        cases = []
        
        # 按 ### 标题分割用例
        # 匹配格式: ### TC-<模块名>-<子模块名>-<三位序号> 用例标题（如 TC-知识管理-分类管理-001）
        # 兼容：旧 TC-<模块缩写>-<NNN>；未拆分子模块时为 TC-<模块名>-<NNN>（如 TC-首页-001）——均以 TC- 开头可命中
        case_blocks = re.split(r'###\s+(TC-[^\n]+)', content)
        
        i = 1
        while i < len(case_blocks):
            case_header = case_blocks[i].strip()
            case_content = case_blocks[i + 1] if i + 1 < len(case_blocks) else ""
            i += 2
            
            # 提取用例 ID 和标题
            header_parts = case_header.split(None, 1)
            case_id = header_parts[0]
            case_name = header_parts[1] if len(header_parts) > 1 else ""
            
            # 解析表格中的键值对
            case_data = {"id": case_id, "name": case_name}
            for line in case_content.split("\n"):
                line = line.strip()
                if line.startswith("|") and "|" in line[1:]:
                    # 去掉首尾的 |
                    if line.startswith("|"):
                        line = line[1:]
                    if line.endswith("|"):
                        line = line[:-1]
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 2:
                        key = parts[0]
                        value = parts[1]
                        # 归一化 key（去除内部空格），同时匹配 “用例 ID / 用例ID” 两种写法
                        key_norm = key.replace(" ", "")
                        # 映射字段名
                        if key_norm in ("用例ID", "字段", "内容", "值"):
                            if key_norm == "用例ID":
                                case_data["id"] = value
                        elif key_norm == "模块":
                            case_data["module"] = value
                        elif key_norm == "子模块":
                            case_data["submodule"] = value
                        elif key_norm == "优先级":
                            case_data["priority"] = value
                        elif key_norm == "前置条件":
                            case_data["precondition"] = value
                        elif key_norm in ("测试步骤", "操作步骤"):
                            case_data["raw_steps"] = value
                        elif key_norm in ("预期结果", "预期结果"):
                            case_data["raw_expected"] = value
                        elif key_norm == "测试数据":
                            case_data["test_data"] = value
                        elif key_norm == "清理动作":
                            case_data["cleanup"] = value
                        elif key_norm == "备注":
                            case_data["remark"] = value
                        elif key_norm == "需求来源":
                            case_data["req_source"] = value
                        elif key_norm == "测试点ID":
                            case_data["test_point_ref"] = value
                        elif key_norm == "用例标题":
                            if not case_data.get("name"):
                                case_data["name"] = value
                        elif key_norm == "用例类型":
                            case_data["case_type"] = value
            
            # 解析步骤和断言
            case_data["steps"] = self._parse_numbered_steps(case_data.get("raw_steps", ""))
            case_data["assertions"] = self._parse_numbered_items(case_data.get("raw_expected", ""))
            
            if case_data.get("id"):
                cases.append(case_data)
        
        return cases

    def _get_cell(self, cells: list, col_map: dict, col_name: str) -> str:
        """安全获取表格单元格值。"""
        idx = col_map.get(col_name)
        if idx is None or idx >= len(cells):
            return ""
        val = cells[idx].strip()
        return val if val != "-" else ""

    def _parse_numbered_steps(self, text: str) -> list[dict]:
        """
        解析编号步骤文本为结构化步骤列表。

        支持格式：
          - "1. 点击按钮 2. 输入文本"
          - "1. 进入知识管理页面"
        """
        if not text:
            return []
        # 匹配 "数字. 内容" 模式
        parts = re.split(r'(\d+)\.\s*', text)
        steps = []
        i = 1
        while i < len(parts):
            if i + 1 < len(parts):
                order = int(parts[i])
                action = parts[i + 1].strip()
                if action:
                    steps.append({"order": order, "action": action})
                i += 2
            else:
                break
        return steps

    def _parse_numbered_items(self, text: str) -> list[str]:
        """
        解析编号项目文本为列表。

        支持格式：
          - "1. 页面包含XX 2. 系统显示YY"
        """
        if not text:
            return []
        parts = re.split(r'\d+\.\s*', text)
        return [p.strip() for p in parts if p.strip()]

    def run_suite_from_md(self, md_file: Path) -> dict | None:
        """
        从 Markdown 用例文件执行测试。

        参数：
            md_file: Markdown 用例文件路径
        """
        cases = self.parse_markdown_cases(md_file)
        if not cases:
            logger.error(f"未解析到用例：{md_file}")
            return None

        module_name = md_file.stem.replace("-用例", "").split("-", 1)[-1] if "-" in md_file.stem else md_file.stem
        logger.info(f"测试执行：{module_name} - {len(cases)} 个用例")
        logger.info("模式：连续执行（失败后继续）")
        results = []

        # [已停用] 空壳 Playwright 脚本生成（仅产出注释、不可执行，易误导）
        # self._generate_playwright_script(module_name, cases)

        # 环境预检（06）：不可达则清晰中止
        if not self._env_preflight():
            return None

        # 使用 Playwright 执行
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=HEADLESS)
                context = browser.new_context(viewport={"width": 1920, "height": 1080})
                page = context.new_page()

                # 登录
                logger.info("正在登录...")
                login_result = ALL_SKILLS["login"](page)
                logger.info(f"登录结果：{login_result}")

                # 导航到模块
                logger.info(f"正在导航到模块：{module_name}")
                nav_result = self._navigate_to_module_menu(page, module_name)
                logger.info(f"导航结果：{nav_result}")

                # 连续执行所有用例
                for i, case in enumerate(cases, 1):
                    logger.info(f"\n  [{i}/{len(cases)}] {case.get('id', '')} - {case.get('name', '')}")

                    # 检查 session 是否有效
                    current_url = page.url
                    if "/login" in current_url:
                        logger.warning("Session 已过期，重新登录...")
                        ALL_SKILLS["login"](page)
                        self._navigate_to_module_menu(page, module_name)

                    result = self._run_case(page, case, module_name, skip_login_nav=True)
                    results.append(result)

                    # 返回模块首页
                    if i < len(cases):
                        logger.info("  返回模块首页...")
                        self._navigate_to_module_menu(page, module_name)
                        page.wait_for_timeout(1000)

                browser.close()
        except ImportError:
            logger.error("Playwright 未安装，请运行：playwright install chromium")
            return None
        except Exception as e:
            logger.error(f"Playwright 执行出错：{e}")
        finally:
            self._env_cleanup()

        if results:
            report = self.reporter.build_and_save(module_name, results)
            return report
        return None
