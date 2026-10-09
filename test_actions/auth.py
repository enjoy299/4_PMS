"""
技能：登录/登出 —— 使用 Playwright 自动登录和登出系统。

改造说明：
  原版本使用 browser-use 的 Tools 装饰器。
  改造后改为普通的 Playwright 函数。
"""
from core.config import APP_URL, TEST_USERNAME, TEST_PASSWORD
try:
    from core.config import LOGIN_URL
except ImportError:
    LOGIN_URL = None
try:
    from core.config import TEST_USERNAME_2, TEST_PASSWORD_2
except ImportError:
    TEST_USERNAME_2 = TEST_PASSWORD_2 = ""
from utils.logger import get_logger

logger = get_logger("skill_auth")


def login(page, username: str | None = None, password: str | None = None) -> str:
    """
    自动登录系统：打开登录页，填写用户名和密码，点击登录。
    如果已登录（session 有效）且未指定账号，直接返回成功。

    参数：
        page: Playwright 的 Page 对象
        username: 指定登录账号（为空则用 .env 的 TEST_USERNAME）；
                  传入第二账号即可切换身份，用于权限/跨账号可见性测试
        password: 指定登录密码（为空则用 .env 的 TEST_PASSWORD）

    返回：
        操作结果描述
    """
    try:
        user = username or TEST_USERNAME
        pwd = password or TEST_PASSWORD
        # 使用 LOGIN_URL 或构造登录地址
        login_url = LOGIN_URL if LOGIN_URL else (APP_URL if "/login" in APP_URL else f"{APP_URL}/login")
        logger.info(f"正在访问登录页：{login_url}")
        # 远程 SPA 系统加载慢，用 "commit" 尽早返回（收到首个字节即继续），
        # 再手动等待页面可交互，避免 domcontentloaded 超时。
        page.goto(login_url, wait_until="commit", timeout=60000)

        # 等待 SPA 框架加载并渲染登录表单
        logger.info("等待登录表单渲染...")
        try:
            page.wait_for_selector(
                'input[placeholder*="用户名"], input[placeholder*="用户"], input[name*="user"], input[name*="username"]',
                timeout=60000
            )
        except Exception:
            # 可能已登录（session 有效）或页面结构不同
            page.wait_for_timeout(5000)

        # 检查是否已登录（URL 不再包含 /login，说明已自动跳转）
        current_url = page.url
        if "/login" not in current_url and username is None:
            logger.info(f"检测到已登录状态，当前 URL: {current_url}")
            return f"已登录（session 有效）：{user}"

        # 查找输入框 - 使用更精确的选择器
        username_input = (
            page.query_selector('input[placeholder*="用户名"]') or
            page.query_selector('input[placeholder*="用户"]') or
            page.query_selector('input[name*="user"], input[name*="username"]') or
            page.query_selector('input[type="text"]:first-of-type')
        )

        password_input = (
            page.query_selector('input[type="password"]') or
            page.query_selector('input[placeholder*="密码"]')
        )

        if not username_input or not password_input:
            logger.warning("未找到登录输入框")
            return "登录失败：未找到登录表单"

        # 填写用户名和密码
        # 注意：SPA 框架（Vue/React）的受控输入框不响应 ElementHandle.fill()，
        # 需要用 click + type 逐字输入来触发 input 事件。
        logger.info(f"填写用户名：{user}")
        username_input.click()
        username_input.type(user, delay=80)
        logger.info("填写密码")
        password_input.click()
        password_input.type(pwd, delay=80)

        # 查找并点击登录按钮 - 使用更精确的选择器
        login_button = (
            page.query_selector('button:has-text("登录")') or
            page.query_selector('button:has-text("登 录")') or
            page.query_selector('button[type="submit"]') or
            page.query_selector('input[type="submit"]') or
            page.query_selector('button:has-text("Login")')
        )

        if not login_button:
            logger.warning("未找到登录按钮")
            return "登录失败：未找到登录按钮"

        logger.info("点击登录按钮...")
        login_button.click()

        # 等待页面跳转（登录成功后 URL 会改变）
        logger.info("等待登录完成...")
        try:
            page.wait_for_url("**/*", timeout=10000)  # 等待 URL 变化
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as e:
            logger.warning(f"等待页面加载超时：{e}")

        # 验证登录是否成功
        final_url = page.url
        if "/login" not in final_url:
            logger.info(f"登录成功，当前 URL: {final_url}")
            return f"已登录：{user}"
        else:
            logger.warning(f"登录可能失败，仍在登录页：{final_url}")
            # 检查是否有错误提示
            error_msg = page.query_selector('.error-message, .ant-message-error, [class*="error"]')
            if error_msg:
                error_text = error_msg.text_content()
                return f"登录失败：{error_text}"
            return "登录失败：登录后仍停留在登录页"

    except Exception as e:
        logger.error(f"登录异常：{e}")
        return f"登录异常：{e}"


def check_session(page) -> bool:
    """
    检查当前登录会话是否仍然有效。

    通过访问系统首页并检测是否被重定向到登录页来判断。

    参数：
        page: Playwright 的 Page 对象

    返回：
        True 表示会话有效，False 表示已过期
    """
    try:
        current_url = page.url
        # 如果当前已经在登录页，会话已过期
        if "/login" in current_url:
            return False
        # 尝试访问系统页面，检查是否被重定向到登录页
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(1500)
        if "/login" in page.url:
            logger.warning("会话已过期（被重定向到登录页）")
            return False
        logger.info(f"会话有效，当前 URL: {page.url}")
        return True
    except Exception as e:
        logger.warning(f"会话检测异常：{e}")
        return False


def logout(page) -> str:
    """
    登出系统：导航到登录页（相当于退出当前会话）。

    参数：
        page: Playwright 的 Page 对象

    返回：
        操作结果描述
    """
    try:
        page.goto(f"{APP_URL}/login", wait_until="networkidle", timeout=15000)
        return "已登出"
    except Exception as e:
        return f"登出异常：{e}"


def switch_account(page, username: str | None = None, password: str | None = None) -> str:
    """
    切换登录账号：先登出并清理前端会话（cookie / localStorage / sessionStorage），
    再以目标账号登录。默认切换到 .env 的第二账号（TEST_USERNAME_2 / TEST_PASSWORD_2）。

    用于权限测试、跨账号可见性验证（如“编辑中”APP 对他人不可见）等双账号场景。

    参数：
        page: Playwright 的 Page 对象
        username: 目标账号（为空则用 TEST_USERNAME_2）
        password: 目标密码（为空则用 TEST_PASSWORD_2）

    返回：
        操作结果描述
    """
    user = username or TEST_USERNAME_2
    pwd = password or TEST_PASSWORD_2
    if not user:
        return "未配置第二账号（.env 的 TEST_USERNAME_2 为空），无法切换"

    logger.info(f"切换账号 -> {user}")
    logout(page)
    # 清理前端会话，避免访问 /login 时被原账号 session 自动登录
    try:
        page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch (e) {} }")
        page.context.clear_cookies()
    except Exception as e:
        logger.warning(f"清理会话异常（继续尝试登录）：{e}")

    return login(page, username=user, password=pwd)
