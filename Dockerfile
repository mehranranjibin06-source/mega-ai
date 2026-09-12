FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# ffmpeg برای ویدیو/صدا، فونت‌ها برای متن فارسی در تصویر و نمودار
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-dejavu fonts-noto-core git curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
VOLUME ["/app/workspace", "/app/data"]

# سلامت واقعی: خود سرور باید جواب بدهد
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://localhost:${PORT:-8000}/api/health" || exit 1

# محیط داکر: همان پایتون سیستم، بدون ساخت venv
ENV MEGA_NO_VENV=1 MEGA_HOST=0.0.0.0 MEGA_PORT=8000
CMD ["python", "server.py"]
