"""快速诊断：登录一次后运行固化脚本前3条用例，输出每条的结果。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from playwright.sync_api import sync_playwright
from test_actions import ALL_SKILLS
import importlib.util

spec = importlib.util.spec_from_file_location(
    "solidified", os.path.join(os.path.dirname(__file__), "工业APP_solidified.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={"width": 1920, "height": 1080})

    # 登录一次（用较长的超时）
    print("正在登录...")
    login_result = ALL_SKILLS["login"](page)
    print(f"登录结果: {login_result}")

    # 跑前5条
    for case in mod.CASES[:5]:
        print(f"\n{'='*60}")
        print(f"执行: {case['id']} - {case['name']}")
        try:
            result = case["fn"](page)
            print(f"结果: {result}")
        except Exception as e:
            print(f"异常: {type(e).__name__}: {e}")

    browser.close()
