"""
探索智能体 —— 自由探索测试，寻找 bug。

改造说明：
  原版本使用 browser-use 的 Agent 让 AI 自由操控浏览器。
  改造后，使用 Playwright 纯脚本遍历所有页面：
    - 点击每个菜单、打开每个页面
    - 检查 404/500 错误、空白页、控制台报错
    - 记录每个页面的状态

输出文件：output/06_reports/ 目录下的探索报告
"""
from datetime import datetime
from pathlib import Path
from core.config import (
    APP_URL, TEST_USERNAME, TEST_PASSWORD,
    HEADLESS, SCREENSHOTS_DIR, LOGS_DIR, REPORTS_DIR,
)
from core.hooks import reset_run, take_screenshot
from test_actions import ALL_SKILLS
from utils.logger import get_logger

logger = get_logger("explorer")


class ExplorerAgent:
    """
    探索智能体类 —— 使用 Playwright 遍历系统所有页面，寻找潜在问题。
    不再依赖 AI 操控浏览器，而是按预定义策略系统性扫描。
    """
    role = "explorer"

    def __init__(self):
        self.findings = []  # 收集所有发现

    def run_all(self):
        """执行所有探索任务。"""
        self._explore_full_scan()
        self._explore_find_bugs()
        self._export_report()

    def _explore_full_scan(self):
        """
        全量扫描：遍历所有可达页面，检查是否有报错或空白页。
        """
        logger.info("  探索任务：全量扫描")
        reset_run()

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=HEADLESS)
                context = browser.new_context(viewport={"width": 1920, "height": 1080})
                page = context.new_page()

                # 收集控制台错误
                console_errors = []
                page.on("console", lambda msg: (
                    console_errors.append(f"[{msg.type}] {msg.text}")
                    if msg.type in ("error", "warning") else None
                ))

                # 第1步：登录
                login_result = ALL_SKILLS["login"](page)
                logger.info(f"    登录: {login_result}")
                take_screenshot(page, "explore_login")

                # 第2步：收集所有导航链接
                nav_links = self._collect_nav_links(page)
                logger.info(f"    发现 {len(nav_links)} 个导航链接")

                # 第3步：逐个访问每个页面
                for i, (link_text, link_url) in enumerate(nav_links, 1):
                    logger.info(f"    [{i}/{len(nav_links)}] {link_text}")
                    console_errors.clear()

                    try:
                        if link_url:
                            page.goto(link_url, wait_until="networkidle", timeout=15000)
                        else:
                            # 尝试点击菜单
                            ALL_SKILLS["click_menu"](page, link_text)
                            page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception as e:
                        self.findings.append({
                            "page": link_text,
                            "url": link_url or page.url,
                            "status": "error",
                            "detail": f"页面加载失败: {str(e)[:200]}",
                        })
                        continue

                    take_screenshot(page, f"scan_{link_text[:8]}")

                    # 检查页面状态
                    status = self._check_page_status(page, console_errors)
                    self.findings.append({
                        "page": link_text,
                        "url": page.url,
                        "status": status["status"],
                        "detail": status["detail"],
                    })

                browser.close()
        except ImportError:
            logger.error("Playwright 未安装，请运行：playwright install chromium")
        except Exception as e:
            logger.error(f"  全量扫描出错：{e}")

    def _explore_find_bugs(self):
        """
        寻找 bug：尝试页面上的按钮、表单等交互元素。
        """
        logger.info("  探索任务：寻找 bug")
        reset_run()

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=HEADLESS)
                context = browser.new_context(viewport={"width": 1920, "height": 1080})
                page = context.new_page()

                console_errors = []
                page.on("console", lambda msg: (
                    console_errors.append(msg.text)
                    if msg.type == "error" else None
                ))

                # 登录
                ALL_SKILLS["login"](page)

                # 在每个页面上尝试交互
                nav_links = self._collect_nav_links(page)
                for link_text, link_url in nav_links[:10]:  # 最多探索 10 个页面
                    try:
                        if link_url:
                            page.goto(link_url, wait_until="networkidle", timeout=15000)
                        else:
                            ALL_SKILLS["click_menu"](page, link_text)
                            page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        continue

                    # 检查页面上的按钮
                    buttons = page.query_selector_all("button, .btn, [role='button']")
                    for btn in buttons[:5]:  # 每个页面最多尝试 5 个按钮
                        try:
                            btn_text = btn.inner_text(timeout=2000).strip()
                            if not btn_text or len(btn_text) > 30:
                                continue
                            # 跳过危险按钮（删除、提交等）
                            dangerous = ["删除", "delete", "提交", "submit", "确认删除"]
                            if any(d in btn_text.lower() for d in dangerous):
                                continue
                            btn.click(timeout=3000)
                            page.wait_for_timeout(1000)
                        except Exception:
                            pass

                    # 记录控制台错误
                    if console_errors:
                        self.findings.append({
                            "page": link_text,
                            "url": page.url,
                            "status": "console_error",
                            "detail": f"控制台错误 ({len(console_errors)}): {'; '.join(console_errors[:3])}",
                        })
                        console_errors.clear()

                browser.close()
        except Exception as e:
            logger.error(f"  探索 bug 出错：{e}")

    def _collect_nav_links(self, page) -> list[tuple[str, str]]:
        """收集页面上的所有导航链接。"""
        links = []
        try:
            # 尝试常见的导航选择器
            selectors = [
                "nav a", ".sidebar a", ".menu a", ".nav-item a",
                "[class*='menu'] a", "[class*='nav'] a",
                ".ant-menu-item a", ".el-menu-item a",
            ]
            for selector in selectors:
                elements = page.query_selector_all(selector)
                for el in elements:
                    try:
                        text = el.inner_text(timeout=2000).strip()
                        href = el.get_attribute("href") or ""
                        if text and len(text) < 30:
                            full_url = ""
                            if href and href.startswith("/"):
                                from urllib.parse import urlparse
                                parsed = urlparse(page.url)
                                full_url = f"{parsed.scheme}://{parsed.netloc}{href}"
                            elif href and href.startswith("http"):
                                full_url = href
                            # 去重
                            if not any(t == text for t, _ in links):
                                links.append((text, full_url))
                    except Exception:
                        pass
                if links:
                    break  # 已找到导航链接，不再尝试其他选择器
        except Exception as e:
            logger.warning(f"  收集导航链接出错: {e}")
        return links

    def _check_page_status(self, page, console_errors: list) -> dict:
        """检查页面状态：是否正常、是否有错误。"""
        url = page.url
        title = page.title()

        # 检查 HTTP 错误（通过 URL 判断）
        if "/404" in url or "not-found" in url:
            return {"status": "404", "detail": "页面不存在"}

        # 检查空白页
        try:
            body_text = page.text_content("body", timeout=3000) or ""
            if len(body_text.strip()) < 10:
                return {"status": "empty", "detail": "页面内容为空或极少"}
        except Exception:
            return {"status": "error", "detail": "无法读取页面内容"}

        # 检查控制台错误
        if console_errors:
            return {
                "status": "console_error",
                "detail": f"控制台错误 ({len(console_errors)}): {'; '.join(console_errors[:3])[:200]}",
            }

        # 检查页面上是否有错误文本
        try:
            error_selectors = [".error", ".exception", "[class*='error']", "[class*='Error']"]
            for sel in error_selectors:
                el = page.query_selector(sel)
                if el:
                    text = el.inner_text(timeout=2000).strip()
                    if text and len(text) > 5:
                        return {"status": "page_error", "detail": f"页面显示错误: {text[:200]}"}
        except Exception:
            pass

        return {"status": "ok", "detail": f"正常 (标题: {title[:30]})"}

    def _export_report(self):
        """导出探索报告。"""
        if not self.findings:
            logger.info("  没有发现任何问题")
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_dir = REPORTS_DIR / "markdown"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"explore_report_{ts}.md"

        lines = [
            f"# 探索测试报告",
            f"",
            f"**时间**: {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"**目标**: {APP_URL}",
            f"**发现问题数**: {len(self.findings)}",
            f"",
            f"## 问题列表",
            f"",
        ]

        for i, f in enumerate(self.findings, 1):
            status_icon = {"ok": "✅", "error": "❌", "404": "🔍",
                          "empty": "⚠️", "console_error": "🐛",
                          "page_error": "⛔"}.get(f["status"], "❓")
            lines.append(f"### {i}. {status_icon} {f['page']}")
            lines.append(f"- **URL**: {f['url']}")
            lines.append(f"- **状态**: {f['status']}")
            lines.append(f"- **详情**: {f['detail']}")
            lines.append("")

        report_file.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"  探索报告已保存：{report_file}")

        # 在终端显示摘要
        print(f"\n{'=' * 50}")
        print(f"  探索测试完成：发现 {len(self.findings)} 个问题")
        print(f"  报告：{report_file}")
        print(f"{'=' * 50}")
        for f in self.findings[:10]:
            print(f"  [{f['status']}] {f['page']}: {f['detail'][:60]}")
