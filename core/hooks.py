"""
截图工具 —— Playwright 页面截图功能。

改造说明：
  原版本是 browser-use 的 on_step_end 钩子，每步自动截图。
  改造后改为普通的 Playwright 截图函数，供测试脚本调用。
"""
from pathlib import Path
from datetime import datetime
from core.config import SCREENSHOTS_DIR, LOGS_DIR
from utils.logger import get_logger

logger = get_logger("hooks")

# 全局计数器
_step_counter = 0
_run_id = ""
_module_name = ""
_case_id = ""


def reset_run(module_name: str = "", case_id: str = ""):
    """
    重置计数器 —— 每开始一个新的测试用例时调用。

    参数：
        module_name: 模块名称（如"知识管理"）
        case_id: 用例 ID（如"TC-知识管理-分类管理-001"；旧格式如"TC-CAT-001"）
    """
    global _step_counter, _run_id, _module_name, _case_id
    _step_counter = 0
    _run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    _module_name = module_name
    _case_id = case_id


def take_screenshot(page, description: str = "") -> Path | None:
    """
    对当前 Playwright 页面截图并保存。

    参数：
        page: Playwright 的 Page 对象
        description: 截图描述（用于文件名）

    返回：
        截图文件路径，失败时返回 None
    """
    global _step_counter
    _step_counter += 1

    try:
        url = page.url
        title = page.title()
    
        # 写日志（文件名包含日期、模块、用例 ID）
        case_part = f"_{_case_id}" if _case_id else ""
        module_part = f"_{_module_name}" if _module_name else ""
        log_file = LOGS_DIR / f"run_{_run_id}{module_part}{case_part}.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[第 {_step_counter} 步] {datetime.now():%H:%M:%S} | 网址：{url} | 标题：{title}\n")

        # 截图
        desc_part = f"_{description[:15]}" if description else ""
        img_path = SCREENSHOTS_DIR / f"run_{_run_id}_step{_step_counter:03d}{desc_part}.png"
        page.screenshot(path=str(img_path))
        logger.info(f"    截图：{img_path.name}")
        return img_path

    except Exception as e:
        logger.warning(f"    截图失败：{e}")
        return None
