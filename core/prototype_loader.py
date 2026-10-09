"""
在线原型加载器 —— 打开在线原型网站并截图。

改造说明：
  原版本使用 browser-use 的 Agent 让 AI 操控浏览器截图。
  改造后使用 Playwright 纯脚本直接访问网站并截图，无需 AI 参与。

配置文件：inputs/online_prototypes.yaml
"""
import re
import yaml
from pathlib import Path
from datetime import datetime
from core.config import ONLINE_PROTOTYPES_FILE, SCREENSHOTS_DIR, HEADLESS
from utils.logger import get_logger

logger = get_logger("prototype")


class PrototypeLoader:
    """
    原型加载器类 —— 使用 Playwright 直接打开在线原型页面并截图。
    """

    def __init__(self):
        """初始化：加载原型配置。"""
        self.prototypes = self._load_config()

    def _load_config(self) -> list[dict]:
        """从 YAML 配置文件中加载原型信息。"""
        if not ONLINE_PROTOTYPES_FILE.exists():
            return []
        with open(ONLINE_PROTOTYPES_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("prototypes", []) if data else []

    @staticmethod
    def _clean_module_name(name: str) -> str:
        """清洗模块名，去除数字前缀（如 '7、知识管理' -> '知识管理'）。"""
        return re.sub(r"^\d+[、_.\-\s]+", "", name).strip()

    def get_prototype(self, module_name: str) -> dict | None:
        """根据模块名称查找对应的原型配置（支持清洗后的名称匹配）。"""
        clean_name = self._clean_module_name(module_name)
        for p in self.prototypes:
            proto_module = p.get("module", "")
            if proto_module == module_name or proto_module == clean_name:
                return p
        return None

    def capture_prototype(self, module_name: str) -> list[Path]:
        """
        截取指定模块的在线原型页面。

        使用 Playwright 直接访问网站、登录（如需要）、逐个页面截图。

        参数：
            module_name: 模块名称

        返回：
            截图文件路径列表
        """
        proto = self.get_prototype(module_name)
        if not proto:
            logger.info(f"  {module_name}: 未配置在线原型")
            return []

        url = proto["url"]
        username = proto.get("username", "")
        password = proto.get("password", "")
        pages = proto.get("pages", [])

        logger.info(f"  打开在线原型：{proto['name']} ({url})")

        screenshots = []
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=HEADLESS)
                page = browser.new_page(viewport={"width": 1920, "height": 1080})

                # 访问原型网站
                page.goto(url, wait_until="networkidle", timeout=30000)

                # 如果需要登录，尝试自动填写
                if username and password:
                    try:
                        page.fill('input:not([type="password"])', username, timeout=5000)
                        page.fill('input[type="password"]', password, timeout=5000)
                        page.click('button[type="submit"]', timeout=5000)
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        logger.warning("  自动登录失败，可能需要手动登录")

                # 截取首页截图
                img_path = SCREENSHOTS_DIR / f"proto_{module_name}_{ts}_home.png"
                page.screenshot(path=str(img_path), full_page=True)
                screenshots.append(img_path)
                logger.info(f"    -> {img_path.name}")

                # 逐个导航到配置的页面并截图
                for page_info in pages:
                    page_name = page_info.get("name", "")
                    page_path = page_info.get("path", "")
                    if page_path and page_path != "/":
                        full_url = f"{url.rstrip('/')}{page_path}"
                        try:
                            page.goto(full_url, wait_until="networkidle", timeout=15000)
                        except Exception:
                            pass
                    img_path = SCREENSHOTS_DIR / f"proto_{module_name}_{ts}_{page_name}.png"
                    page.screenshot(path=str(img_path), full_page=True)
                    screenshots.append(img_path)
                    logger.info(f"    -> {img_path.name}")

                browser.close()
        except Exception as e:
            logger.error(f"  原型截图失败：{e}")

        return screenshots

    def capture_all(self) -> dict[str, list[Path]]:
        """截取所有已配置的原型页面。"""
        results = {}
        for proto in self.prototypes:
            module = proto.get("module", "")
            if module:
                paths = self.capture_prototype(module)
                results[module] = paths
        return results
