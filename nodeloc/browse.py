# -*- coding: utf-8 -*-
"""
浏览点赞模块
模拟真人浏览行为，随机点击帖子、滚动页面、点赞
"""
import os
import random
import time
import logging
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

log = logging.getLogger(__name__)

# ================== 浏览配置（从环境变量读取）==================
# 是否启用浏览功能
BROWSE_ENABLED = os.environ.get("BROWSE_ENABLED", "true").lower() == "true"
# 点赞概率（0~1）
LIKE_PROB = float(os.environ.get("LIKE_PROB", "0.3"))
# 随机浏览帖子数量
CLICK_COUNT = int(os.environ.get("CLICK_COUNT", "10"))
# ==============================================================


def browse_topics(driver, base_url: str) -> bool:
    """
    随机浏览首页帖子
    :param driver: Selenium WebDriver 实例
    :param base_url: 网站基础地址
    :return: 是否浏览成功
    """
    if not BROWSE_ENABLED:
        log.info("📖 浏览功能已禁用，跳过")
        return False

    log.info("📖 开始随机浏览首页主题...")
    
    try:
        # 1. 访问首页
        driver.get(base_url + "/")
        time.sleep(4)

        # 2. 获取所有帖子链接
        # 使用 CSS 选择器查找帖子标题链接
        topic_elements = driver.find_elements(By.CSS_SELECTOR, "#list-area a.title")
        topic_links = [el.get_attribute("href") for el in topic_elements if el.get_attribute("href")]

        if not topic_links:
            log.warning("⚠️ 未找到主题链接")
            return False

        # 3. 随机选择要浏览的帖子
        picks = random.sample(topic_links, min(CLICK_COUNT, len(topic_links)))
        log.info(f"🔍 发现 {len(topic_links)} 个主题，随机浏览 {len(picks)} 个")

        # 4. 逐个浏览每个帖子
        for url in picks:
            full_url = url if url.startswith("http") else (base_url + url)
            _browse_one_topic(driver, full_url, base_url)

        log.info("✅ 浏览任务完成")
        return True

    except Exception as e:
        log.error(f"❌ 浏览任务失败: {e}")
        return False


def _browse_one_topic(driver, url: str, base_url: str) -> None:
    """
    浏览单个帖子
    :param driver: Selenium WebDriver 实例
    :param url: 帖子 URL
    :param base_url: 网站基础地址
    """
    original_window = driver.current_window_handle
    
    try:
        # 1. 新开一个标签页访问帖子
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(url)
        time.sleep(random.uniform(1.2, 2.2))

        # 2. 根据概率决定是否点赞
        if random.random() < LIKE_PROB:
            _try_like(driver)

        # 3. 模拟滚动阅读
        _auto_scroll(driver)

    except Exception as e:
        log.debug(f"浏览帖子出错: {e}")
    finally:
        # 4. 关闭当前标签页，回到原来的窗口
        try:
            if len(driver.window_handles) > 1:
                driver.close()
                driver.switch_to.window(original_window)
        except Exception:
            pass


def _auto_scroll(driver) -> None:
    """
    模拟真人滚动页面
    :param driver: Selenium WebDriver 实例
    """
    prev_url = None
    
    # 随机滚动 6~10 次
    for _ in range(random.randint(6, 10)):
        # 每次滚动 520~700 像素
        distance = random.randint(520, 700)
        driver.execute_script(f"window.scrollBy(0, {distance})")
        
        # 随机停顿 1.8~3.5 秒，模拟阅读
        time.sleep(random.uniform(1.8, 3.5))

        # 检查是否到达页面底部
        at_bottom = driver.execute_script(
            "return window.scrollY + window.innerHeight >= document.body.scrollHeight;"
        )
        cur_url = driver.current_url

        if cur_url != prev_url:
            prev_url = cur_url
        elif at_bottom and prev_url == cur_url:
            # 已到底部，停止滚动
            break

        # 7% 概率提前结束（模拟真人随机行为）
        if random.random() < 0.07:
            break


def _try_like(driver) -> None:
    """
    尝试点赞帖子
    :param driver: Selenium WebDriver 实例
    """
    # 点赞按钮的候选 CSS 选择器（不同版本的 Discourse 可能不同）
    candidates = [
        ".discourse-reactions-reaction-button",
        "button.toggle-like",
        "button.btn-like",
    ]

    try:
        for selector in candidates:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, selector)
                if btn and btn.is_displayed():
                    btn.click()
                    log.info("👍 点赞成功")
                    time.sleep(random.uniform(0.8, 1.6))
                    return
            except NoSuchElementException:
                continue
    except Exception:
        pass
