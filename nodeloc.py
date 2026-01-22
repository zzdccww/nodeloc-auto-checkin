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

BASE_URL = os.environ.get("NODELOC_BASE_URL", "https://www.nodeloc.com").rstrip("/")
LOGIN_URL = f"{BASE_URL}/login"
SESSION_URL = f"{BASE_URL}/session"
CSRF_URL = f"{BASE_URL}/session/csrf"

USERNAME = os.environ.get("NODELOC_USERNAME") or os.environ.get("USERNAME")
PASSWORD = os.environ.get("NODELOC_PASSWORD") or os.environ.get("PASSWORD")
NL_COOKIE = os.environ.get("NL_COOKIE", "").strip()

BROWSE_ENABLED = os.environ.get("BROWSE_ENABLED", "true").strip().lower() not in ["false","0","off"]
HEADLESS = os.environ.get("HEADLESS", "true").strip().lower() not in ["false","0","off"]
LIKE_PROB = float(os.environ.get("LIKE_PROB", "0.3"))
CLICK_COUNT = int(os.environ.get("CLICK_COUNT", "10"))

# 默认签到按钮选择器（优先未签到按钮，再兜底任意签到按钮）
DEFAULT_CHECKIN_SELECTORS = "button.checkin-button:not(.checked-in),button.checkin-button"
CHECKIN_SELECTOR = os.environ.get("CHECKIN_SELECTOR", DEFAULT_CHECKIN_SELECTORS).strip()



GOTIFY_URL = os.environ.get("GOTIFY_URL")
GOTIFY_TOKEN = os.environ.get("GOTIFY_TOKEN")
SC3_PUSH_KEY = os.environ.get("SC3_PUSH_KEY")

class NodeLocBrowser:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/118.0.0.0 Safari/537.36"),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        co = (ChromiumOptions()
              .headless(HEADLESS)
              .incognito(True)
              .set_argument("--no-sandbox")
              .set_argument("--disable-dev-shm-usage"))
        self.browser = Chromium(co)
        self.page = self.browser.new_tab()

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
                logger.error(f"登录失败，状态码: {resp_login.status_code}，响应: {resp_login.text[:200]}")
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
        if "avatar" in (self.page.html or "") or "/u/" in (self.page.html or ""):
            logger.info("登录验证成功（avatar / /u/）")
            return True
        logger.error("登录验证失败")
        return False

    
    def try_checkin(self) -> bool:
        logger.info("尝试执行签到...")
        # 打开首页（或签到入口页）
        self.page.get(BASE_URL + "/")
        time.sleep(2.0)
    
        # 规范化候选选择器：
        # 1) 优先使用环境变量/默认值（已经在顶部设为：button.checkin-button...）
        # 2) 再追加兜底选择器（尽量不要依赖 :has-text，部分环境兼容性不稳定）
        selectors: List[str] = []
        if CHECKIN_SELECTOR:
            selectors.extend([s.strip() for s in CHECKIN_SELECTOR.split(",") if s.strip()])
    
        # 兜底候选（从“更精确”到“一般”）
        fallback_selectors = [
            # 你的真实按钮类名（再次兜底一次，防止用户覆盖后仍失败）
            "button.checkin-button:not(.checked-in)",
            "button.checkin-button",
    
            # 兼容一些主题的常见按钮位置
            ".d-header .btn.checkin-button",
            ".d-header button.btn",
    
            # 最后再试基于文本的选择器（某些引擎不支持 :has-text，放在最后）
            'button:has-text("签到")', 'a:has-text("签到")',
            'button:has-text("打卡")', 'a:has-text("打卡")',
        ]
        for css in fallback_selectors:
            if css not in selectors:
                selectors.append(css)
    
        logger.debug(f"签到按钮候选选择器：{selectors}")
    
        # 工具函数：若命中的是 <svg>，则向上找到最近的 <button>/<a>
        def _promote_to_clickable(ele):
            try:
                tag = (getattr(ele, "tag", "") or "").lower()
            except Exception:
                tag = ""
            if tag == "svg":
                parent = ele.parent()
                # 向上找可点击的 button / a
                while parent and getattr(parent, "tag", None) and getattr(parent, "tag").lower() not in ("button", "a"):
                    parent = parent.parent()
                return parent or ele
            return ele
    
        # 工具函数：判断是否“已签到”
        def _is_checked_in(ele):
            try:
                cls = (ele.attr("class") or "") if hasattr(ele, "attr") else (getattr(ele, "attrs", {}).get("class", "") if hasattr(ele, "attrs") else "")
                # DrissionPage 的 .attr("class") 通常返回字符串；有些实现可能返回列表，做个兜底处理
                if isinstance(cls, list):
                    classes = " ".join(cls)
                else:
                    classes = str(cls)
                return "checked-in" in classes
            except Exception:
                return False
    
        for css in selectors:
            try:
                ele = self.page.ele(css)
                if not ele:
                    continue
    
                # 如果元素就是“已签到”按钮，直接判定成功并返回
                if _is_checked_in(ele):
                    logger.success(f"已检测到签到完成（元素含 .checked-in）：{css}")
                    return True
    
                # 命中 svg 时提升到可点击的父级
                ele = _promote_to_clickable(ele)
    
                # 再次检测（父级可能带有 .checked-in）
                if _is_checked_in(ele):
                    logger.success(f"已检测到签到完成（父级含 .checked-in）：{css}")
                    return True
    
                # 再做一次文本判定（如果引擎支持 .text）
                text = ""
                try:
                    text = (ele.text or "").strip()
                except Exception:
                    text = ""
                if text and any(k in text for k in ("签到", "打卡", "签 到", "Check-in", "check in")):
                    logger.info(f"发现疑似签到按钮：{css} / 文本：{text}，准备点击")
    
                # 点击
                ele.click()
                time.sleep(random.uniform(1.2, 2.2))
    
                # 点击后再检查一次是否已变成“已签到”状态
                try:
                    # 页面可能动态变更，重新拿一次元素或其父级
                    confirm_ele = self.page.ele("button.checkin-button") or ele
                    if _is_checked_in(confirm_ele):
                        logger.success("签到成功（点击后检测到已签到状态）")
                        return True
                except Exception:
                    pass
    
                # 有些站点会弹出提示或需要刷新状态，再给一次机会
                time.sleep(0.8)
                self.page.refresh()
                time.sleep(1.0)
    
                # 刷新后再检测一次“已签到”状态
                try:
                    confirm_ele2 = self.page.ele("button.checkin-button")
                    if confirm_ele2 and _is_checked_in(confirm_ele2):
                        logger.success("签到成功（刷新后检测到已签到状态）")
                        return True
                except Exception:
                    pass
    
                logger.info(f"已点击可能的签到按钮：{css}，但未确认到已签到状态，将继续尝试其他候选")
                # 不 return，继续试下一个候选
            except Exception as e:
                logger.debug(f"签到点击失败，尝试下一个：{css} | {e}")
    
        logger.warning("未找到‘签到/打卡’按钮，请设置 CHECKIN_SELECTOR 精确匹配或检查页面结构")
        return False



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

class NodeLocRunner:
    def run(self) -> bool:
        b = NodeLocBrowser()
        return b.run()



