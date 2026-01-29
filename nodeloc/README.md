# NodeLoc Auto-Check-in

> 基于 Selenium + undetected-chromedriver 的 NodeLoc 自动签到脚本  
> 适用于 **青龙（QingLong） / Linux Server / 本地 Python 环境**
---
在原作者的代码上修改增加支持github action运行
## ✨ 项目简介

本项目是一个 **NodeLoc 论坛自动签到脚本**，  
通过模拟真实浏览器行为完成每日签到操作，支持：

- ✅ 多账号顺序签到  
- ✅ 无头 Chrome（Headless）  
- ✅ Cookie 登录（无需账号密码）  
- ✅ 适配青龙面板（QingLong）  
- ✅ 自动规避常见 Selenium 特征检测  

项目结构清晰，代码已模块化拆分，  
同时也适合作为 **Selenium 自动化学习示例**。

---

## 📁 项目结构

```text
.
├── browser.py   # 浏览器创建 & Cookie 注入
├── checkin.py   # 登录检测 & 签到逻辑
├── main.py      # 程序入口 & 多账号调度
├── requirements.txt
├── README.md
└── LICENSE
```

## 🚀 github action运行使用方式

### 1️⃣ 安装依赖
fork到本账号

### 2️⃣ 获取 Cookie
使用浏览器登录：https://www.nodeloc.com
打开开发者工具（F12）
在 Network / 请求头 / Application → Cookies 中获取完整 Cookie

### 3️⃣ 设置环境变量（支持多账号）
```bash
在仓库 Settings → Secrets & variables → Actions 中添加名为 NL_COOKIE 的 secret，值为你从浏览器获取的 Cookie（支持多账号，多行）。
```
### 4️⃣ 运行脚本
点击action运行工作流即可
## 📜 License
本项目采用 MIT License 开源协议。

## ⭐ Star
如果这个项目对你有帮助，欢迎点个 ⭐
你的支持是我继续维护和优化的动力 ❤️
