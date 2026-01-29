# -*- coding: utf-8 -*-
"""
推送通知模块
支持 Telegram 和 Gotify 两种推送方式
"""
import os
import logging
import requests

log = logging.getLogger(__name__)

# ================== 推送配置（从环境变量读取）==================
# Telegram 配置
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_USER_ID = os.environ.get("TG_USER_ID", "")

# Gotify 配置
GOTIFY_URL = os.environ.get("GOTIFY_URL", "")
GOTIFY_TOKEN = os.environ.get("GOTIFY_TOKEN", "")
# ==============================================================


def send_telegram(title: str, message: str) -> bool:
    """
    发送 Telegram 消息
    :param title: 消息标题
    :param message: 消息内容
    :return: 是否发送成功
    """
    if not TG_BOT_TOKEN or not TG_USER_ID:
        log.debug("未配置 Telegram，跳过推送")
        return False

    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        params = {
            "chat_id": TG_USER_ID,
            "text": f"*{title}*\n\n{message}",
            "parse_mode": "Markdown"
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        log.info("✅ Telegram 推送成功")
        return True
    except Exception as e:
        log.warning(f"⚠️ Telegram 推送失败: {e}")
        return False


def send_gotify(title: str, message: str, priority: int = 5) -> bool:
    """
    发送 Gotify 消息
    :param title: 消息标题
    :param message: 消息内容
    :param priority: 消息优先级（1-10）
    :return: 是否发送成功
    """
    if not GOTIFY_URL or not GOTIFY_TOKEN:
        log.debug("未配置 Gotify，跳过推送")
        return False

    try:
        resp = requests.post(
            f"{GOTIFY_URL}/message",
            params={"token": GOTIFY_TOKEN},
            json={"title": title, "message": message, "priority": priority},
            timeout=10
        )
        resp.raise_for_status()
        log.info("✅ Gotify 推送成功")
        return True
    except Exception as e:
        log.warning(f"⚠️ Gotify 推送失败: {e}")
        return False


def send_notification(title: str, message: str) -> None:
    """
    统一推送接口：会尝试所有已配置的推送渠道
    :param title: 消息标题
    :param message: 消息内容
    """
    # 尝试所有已配置的推送方式
    send_telegram(title, message)
    send_gotify(title, message)


def build_result_message(results: list, browse_enabled: bool, browsed: bool) -> str:
    """
    构建推送消息内容
    :param results: 签到结果列表
    :param browse_enabled: 是否启用了浏览功能
    :param browsed: 浏览是否成功
    :return: 格式化的消息字符串
    """
    lines = ["📋 *签到结果*", ""]
    
    for result in results:
        lines.append(result)
    
    lines.append("")
    
    if browse_enabled:
        status = "✅ 完成" if browsed else "❌ 失败"
        lines.append(f"🔍 浏览任务: {status}")
    
    return "\n".join(lines)
