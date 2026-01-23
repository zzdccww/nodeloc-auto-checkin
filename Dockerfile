
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=1 \
    CHROME_PATH=/usr/bin/chromium \
    LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8

# 安装 Chromium 及运行依赖（Debian Bookworm）
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    ca-certificates \
    fonts-noto \
    fonts-noto-cjk \
    libnss3 \
    libxss1 \
    libasound2 \
    libxshmfence1 \
    libxi6 \
    libgbm1 \
    libgtk-3-0 \
    tzdata \
    locales \
 && sed -i 's/# zh_CN.UTF-8 UTF-8/zh_CN.UTF-8 UTF-8/' /etc/locale.gen && locale-gen \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app

# 为 DrissionPage 预置临时目录（与代码里的 co.set_tmp_path('/tmp/DrissionPage') 对应）
RUN mkdir -p /tmp/DrissionPage && chmod -R 777 /tmp/DrissionPage

# 缺省用无头模式（可被运行时覆盖）
ENV HEADLESS=true

CMD ["python", "main.py"]
