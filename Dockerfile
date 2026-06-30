# ═══════════════════════════════════════════════════════════════════════════
# ai-learning-loop —— 多阶段构建 Docker 镜像
# ═══════════════════════════════════════════════════════════════════════════
# 构建: docker build -t ai-learning-loop .
# 运行: docker run -p 3003:3003 -p 8003:8003 --env-file .env ai-learning-loop
# ═══════════════════════════════════════════════════════════════════════════

# ── Stage 1: 依赖安装 ─────────────────────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖定义
COPY pyproject.toml MANIFEST.in ./

# 安装 Python 依赖（利用 Docker 缓存层）
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir .

# ── Stage 2: 最终镜像 ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# 创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 从 deps 阶段复制已安装的包
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# 复制应用代码
COPY socratic_loop/ ./socratic_loop/
COPY web/ ./web/
COPY ai_learning_loop_cli.py ./
COPY rxconfig.py ./

# 设置权限
RUN chown -R appuser:appuser /app

# 切换到非 root 用户
USER appuser

# 环境变量
ENV PYTHONUTF8=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 3003 8003

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health', timeout=5)" || exit 1

# 启动命令
ENTRYPOINT ["python", "ai_learning_loop_cli.py"]
