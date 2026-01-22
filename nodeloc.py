
# -*- coding: utf-8 -*-
import os
import re
import time
import random
from typing import List

from loguru import logger
from curl_cffi import requests
from bs4 import BeautifulSoup
from DrissionPage import ChromiumOptions, Chromium
from tabulate import tabulate

from utils import retry

# ------------------ 基础配置 ------------------
BASE_URL = os.environ.get("NODELOC_BASE_URL", "https://www.nodeloc.com").rstrip("/")
LOGIN_URL = f"{BASE_URL}/login"
SESSION_URL = f"{BASE_URL}/session"
CSRF_URL = f"{BASE_URL}/session/csrf"

USERNAME = os.environ.get("NODELOC_USERNAME") or os.environ.get("USERNAME")
PASSWORD = os.environ.get("NODELOC_PASSWORD") or os.environ.get("PASSWORD")
NL_COOKIE = os.environ.get("NL_COOKIE", "").strip()

BROWSE_ENABLED = os.environ.get("BROWSE_ENABLED", "true").strip().lower() not in ["false", "0", "off"]
HEADLESS = os.environ.get("HEADLESS", "true").strip().lower() not in ["false", "0", "off"]
LIKE_PROB = float(os.environ.get("LIKE_PROB", "0.3"))
CLICK_COUNT = int(os.environ.get("CLICK_COUNT", "10"))

# 默认签到按钮选择器：优先使用你给出的精准选择器
DEFAULT_CHECKIN_SELECTORS = (
    "li.header-dropdown-toggle.checkin-icon button.checkin-button,"
    "button.checkin-button:not(.checked-in),"
    "button.checkin-button"
)
CHECKIN_SELECTOR = os.environ.get("CHECKIN_SELECTOR", DEFAULT_CHECKIN_SELECTORS).strip()

GOTIFY_URL = os.environ.get("GOTIFY_URL")
GOTIFY_TOKEN = os.environ.get("GOTIFY_TOKEN")
SC3_PUSH_KEY = os.environ.get("SC3_PUSH_KEY")
# ----------------------------------------------------


class NodeLocBrowser:
    def __init__(self) -> None:
        # HTTP 会话（curl_cffi）
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/118.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

        # ---------------- 正式修复 Desktop 渲染关键配置 ----------------
        co = ChromiumOptions()

        # 强制 Desktop 用户环境
        co.set_argument("--disable-blink-features=AutomationControlled")
        co.set_argument("--disable-features=IsolateOrigins,site-per-process")
        co.set_argument("--disable-extensions")
        co.set_argument("--window-size=1400,900")

        # headless 视图在 mobile 模式下渲染不全，此模式必须保持 false 才能看到签到按钮
        co.headless(HEADLESS)

        # 常规配置
        co.incognito(True)
        co.set_argument("--no-sandbox")
        co.set_argument("--disable-dev-shm-usage")

        # --------------------------------------------------------------

        self.browser = Chromium(co)
        self.page = self.browser.new_tab()

    # ------------------ Cookie/Login ------------------
    def set_cookies_to_both(self, cookie_dict: dict):
        for k, v in cookie_dict.items():
            self.session.cookies.set(k, v, domain=self._cookie_domain())
        dp_cookies = [{"name": k, "value": v, "domain": self._cookie_domain(), "path": "/"}
                      for k, v in cookie_dict.items()]
        self.page.set.cookies(dp_cookies)

    def _cookie_domain(self) -> str:
        host = BASE_URL.split("://", 1)[-1].split("/", 1)[0]
        if host.startswith("www."):
            host = host[4:]
        return f".{host}"

    def _parse_cookie_str(self, cookie_str: str) -> dict:
        pairs = [kv.strip() for kv in cookie_str.split(";") if "=" in kv]
        return {kv.split("=", 1)[0].strip(): kv.split("=", 1)[1].strip() for kv in pairs}

    def login_via_cookie(self) -> bool:
        logger.info("尝试使用 NL_COOKIE 登录...")
        try:
            cookie_dict = self._parse_cookie_str(NL_COOKIE)
            if not cookie_dict:
                logger.warning("NL_COOKIE 为空或格式不正确")
                return False
            self.set_cookies_to_both(cookie_dict)
            self.page.get(BASE_URL + "/")
            time.sleep(3)
            return self._verify_logged_in()
        except Exception as e:
            logger.error(f"Cookie 登录异常: {e}")
            return False

    def login_via_password(self) -> bool:
        logger.info("尝试使用 用户名/密码 登录...")
        if not USERNAME or not PASSWORD:
            logger.error("未提供用户名或密码，无法使用密码登录")
            return False
        try:
            headers = {
                "User-Agent": self.session.headers["User-Agent"],
                "Accept": self.session.headers["Accept"],
                "Accept-Language": self.session.headers["Accept-Language"],
                "X-Requested-With": "XMLHttpRequest",
                "Referer": LOGIN_URL,
            }
            resp_csrf = self.session.get(CSRF_URL, headers=headers, impersonate="chrome136")
            csrf = resp_csrf.json().get("csrf")
            if not csrf:
                logger.error("未获取到 CSRF")
                return False
            logger.info(f"CSRF: {csrf[:10]}...")

            headers.update({
                "X-CSRF-Token": csrf,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": BASE_URL,
            })
            data = {"login": USERNAME, "password": PASSWORD}
            resp_login = self.session.post(SESSION_URL, data=data, headers=headers, impersonate="chrome136")
            if resp_login.status_code != 200:
                logger.error(f"登录失败，状态码: {resp_login.status_code}")
                return False
            j = resp_login.json()
            if j.get("error"):
                logger.error(f"登录失败: {j.get('error')}")
                return False

            self.set_cookies_to_both(self.session.cookies.get_dict())
            self.page.get(BASE_URL + "/")
            time.sleep(4)
            return self._verify_logged_in()
        except Exception as e:
            logger.error(f"密码登录异常: {e}")
            return False

    def _verify_logged_in(self) -> bool:
        user_ele = self.page.ele("@id=current-user")
        if user_ele:
            logger.info("登录验证成功（current-user）")
            return True
        html = self.page.html or ""
        if "avatar" in html or "/u/" in html:
            logger.info("登录验证成功（avatar / /u/）")
            return True
        logger.error("登录验证失败")
        return False
    # ----------------------------------------------------

    # ------------------ 签到（最终 Desktop 版） ------------------
    def try_checkin(self) -> bool:
        logger.info("尝试执行签到...")

        self.page.get(BASE_URL + "/")
        time.sleep(3)

        # 等待 Desktop 顶部导航栏渲染完成
        try:
            self.page.wait.ele_displayed("css=ul.icons.d-header-icons", timeout=8)
        except:
            logger.warning("顶部导航栏未完全渲染，可能导致找不到签到按钮")

        # 签到按钮选择器
        selectors = [s.strip() for s in CHECKIN_SELECTOR.split(",") if s.strip()]
        precise = "li.header-dropdown-toggle.checkin-icon button.checkin-button"
        if precise not in selectors:
            selectors.insert(0, precise)

        logger.debug(f"签到按钮候选：{selectors}")

        def _checked(ele):
            try:
                cls = ele.attr("class") or ""
                return "checked-in" in cls or bool(ele.attr("disabled"))
            except:
                return False

        for sel in selectors:
            btn = self.page.ele(sel)
            if not btn:
                logger.debug(f"未找到：{sel}")
                continue

            if _checked(btn):
                logger.success("今日已签到（checked-in）")
                return True

            # 点击签到
            try:
                btn.click()
            except:
                try:
                    self.page.run_js("arguments[0].click();", btn)
                except Exception as e:
                    logger.error(f"点击失败：{e}")
                    continue

            time.sleep(2)

            # 确认签到
            btn2 = self.page.ele(sel)
            if btn2 and _checked(btn2):
                logger.success("签到成功（checked-in）")
                return True

        logger.warning("未找到签到按钮或未确认到成功")
        return False
    # ----------------------------------------------------

    # ------------------ 浏览/点赞 ------------------
    def click_topics_and_browse(self) -> bool:
        logger.info("开始随机浏览首页主题...")
        self.page.get(BASE_URL + "/")
        time.sleep(4)

        topic_links = [a.attr("href") for a in self.page.eles("css=#list-area a.title") if a.attr("href")]
        if not topic_links:
            logger.error("未找到主题链接")
            return False

        picks = random.sample(topic_links, min(CLICK_COUNT, len(topic_links)))
        logger.info(f"发现 {len(topic_links)} 个主题，随机浏览 {len(picks)} 个")

        for url in picks:
            full = url if url.startswith("http") else (BASE_URL + url)
            self._browse_one_topic(full)

        return True

    @retry(3, sleep_seconds=1.0)
    def _browse_one_topic(self, url: str):
        tab = self.browser.new_tab()
        tab.get(url)
        time.sleep(random.uniform(1.2, 2.2))

        if random.random() < LIKE_PROB:
            self._try_like(tab)

        self._auto_scroll(tab)
        tab.close()

    def _auto_scroll(self, page):
        prev_url = None
        for _ in range(random.randint(6, 10)):
            dist = random.randint(520, 700)
            page.run_js(f"window.scrollBy(0, {dist})")
            time.sleep(random.uniform(1.8, 3.5))

            at_bottom = page.run_js("window.scrollY + window.innerHeight >= document.body.scrollHeight")
            cur = page.url

            if cur != prev_url:
                prev_url = cur
            elif at_bottom and prev_url == cur:
                break

            if random.random() < 0.07:
                break

    def _try_like(self, page) -> None:
        try:
            cand = [
                ".discourse-reactions-reaction-button",
                "button.toggle-like",
                "button.btn-like",
            ]
            for sel in cand:
                btn = page.ele(f"css={sel}")
                if btn:
                    btn.click()
                    time.sleep(random.uniform(0.8, 1.6))
                    return
        except Exception:
            pass
    # ----------------------------------------------------

    # ------------------ 信息与推送 ------------------
    def print_basic_info(self):
        try:
            resp = self.session.get(f"{BASE_URL}/badges", impersonate="chrome136")
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table tr")
            info = []
            for r in rows:
                cols = [c.text.strip() for c in r.select("td")]
                if len(cols) >= 2:
                    info.append(cols[:3])
            if info:
                print("------------- Badges / Info -------------")
                print(tabulate(info, headers=["列1", "列2", "列3"], tablefmt="pretty"))
        except Exception:
            pass

    def send_notifications(self, ok: bool, did_checkin: bool, browsed: bool):
        status = ("✅ 登录成功" if ok else "❌ 登录失败")
        if did_checkin:
            status += " + 签到完成"
        if browsed and BROWSE_ENABLED:
            status += " + 浏览任务完成"

        # Gotify
        if GOTIFY_URL and GOTIFY_TOKEN:
            try:
                r = requests.post(
                    f"{GOTIFY_URL}/message",
                    params={"token": GOTIFY_TOKEN},
                    json={"title": "NODELOC", "message": status, "priority": 1},
                    timeout=10,
                )
                r.raise_for_status()
            except Exception:
                pass

        # Server酱³
        if SC3_PUSH_KEY:
            m = re.match(r"sct(\d+)t", SC3_PUSH_KEY, re.I)
            if m:
                uid = m.group(1)
                url = f"https://{uid}.push.ft07.com/send/{SC3_PUSH_KEY}"
                params = {"title": "NODELOC", "desp": status}
                for _ in range(3):
                    try:
                        r = requests.get(url, params=params, timeout=10)
                        r.raise_for_status()
                        break
                    except Exception:
                        time.sleep(random.randint(120, 240))
    # ----------------------------------------------------

    # ------------------ 入口 ------------------
    def run(self) -> bool:
        ok = False
        did_checkin = False
        browsed = False

        try:
            if NL_COOKIE:
                ok = self.login_via_cookie()
                if not ok and USERNAME and PASSWORD:
                    ok = self.login_via_password()
            else:
                ok = self.login_via_password()

            if not ok:
                self.send_notifications(False, False, False)
                return False

            self.print_basic_info()

            did_checkin = self.try_checkin()

            if BROWSE_ENABLED:
                browsed = self.click_topics_and_browse()

            self.send_notifications(True, did_checkin, browsed)
            return True
        finally:
            try:
                self.page.close()
                self.browser.quit()
            except Exception:
                pass
    # ----------------------------------------------------


class NodeLocRunner:
    def run(self) -> bool:
        b = NodeLocBrowser()
        return b.run()
