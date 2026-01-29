# -*- coding: utf-8 -*-
# 👆 这一行指定了文件的编码格式为 UTF-8，防止中文乱码

# ================== 导入模块 ==================
# 导入操作系统模块，用于读取环境变量等
import os
# 导入时间模块，用于程序暂停（sleep）
import time
# 导入日志模块，用于输出运行日志
import logging

# 从 browser.py 文件中导入创建浏览器和注入 Cookie 的函数
from browser import create_browser, inject_cookies

# 从 checkin.py 文件中导入签到相关的配置和函数
from checkin import (
    BASE_URL,            # 网站的基础网址
    USER_PAGE,           # 用户个人中心页面地址
    COOKIE_DOMAIN,       # Cookie 的作用域（域名）
    wait_login_success,  # 等待并检查是否登录成功的函数
    get_username,        # 获取当前登录用户名的函数
    do_checkin,          # 执行核心签到动作的函数
)

# 从 browse.py 导入浏览点赞功能
from browse import browse_topics, BROWSE_ENABLED

# 从 notify.py 导入推送通知功能
from notify import send_notification, build_result_message
# ==============================================


# ================== 日志配置 ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)
# ==============================================


def process_account(cookie: str) -> dict:
    """
    处理单个账号的签到流程
    :param cookie: 账号的 Cookie 字符串
    :return: 包含签到结果和浏览结果的字典
    """
    result = {
        "checkin_msg": "",
        "login_ok": False,
        "browsed": False,
    }
    
    # 1. 启动浏览器
    driver = create_browser()
    if not driver:
        result["checkin_msg"] = "[❌] 浏览器启动失败"
        return result

    try:
        # 2. 注入 Cookie 并访问用户中心
        inject_cookies(driver, BASE_URL, cookie, COOKIE_DOMAIN)
        driver.get(USER_PAGE)

        # 3. 检查登录状态
        if not wait_login_success(driver):
            result["checkin_msg"] = "[❌] 登录失败，Cookie 可能失效"
            return result

        result["login_ok"] = True

        # 4. 获取用户名
        username = get_username(driver)
        log.info(f"👤 当前账号: {username}")

        # 5. 执行签到
        result["checkin_msg"] = do_checkin(driver, username)

        # 6. 执行浏览点赞任务（如果启用）
        if BROWSE_ENABLED:
            result["browsed"] = browse_topics(driver, BASE_URL)

        return result

    finally:
        # 无论成功失败，最后都关闭浏览器
        try:
            driver.quit()
        except Exception:
            pass


def main():
    """
    主程序入口
    """
    # 1. 检查环境变量
    if "NL_COOKIE" not in os.environ:
        print("❌ 未设置 NL_COOKIE 环境变量")
        return

    # 2. 解析 Cookie（支持多账号，每行一个）
    cookies = [
        line.strip().split("#", 1)[0]
        for line in os.environ["NL_COOKIE"].splitlines()
        if line.strip()
    ]

    log.info(f"✅ 共 {len(cookies)} 个账号，开始签到")
    if BROWSE_ENABLED:
        log.info("📖 浏览点赞功能已启用")

    results = []           # 签到结果消息列表
    any_login_ok = False   # 是否有任何账号登录成功
    any_browsed = False    # 是否有任何账号完成了浏览

    # 3. 遍历所有账号
    for cookie in cookies:
        result = process_account(cookie)
        
        log.info(result["checkin_msg"])
        results.append(result["checkin_msg"])
        
        if result["login_ok"]:
            any_login_ok = True
        if result["browsed"]:
            any_browsed = True
        
        # 账号间停顿 5 秒，防止风控
        time.sleep(5)

    # 4. 输出汇总结果
    print("\n".join(results))
    log.info("✅ 全部完成")

    # 5. 发送推送通知
    message = build_result_message(results, BROWSE_ENABLED, any_browsed)
    send_notification("NodeLoc 签到", message)


if __name__ == "__main__":
    main()
