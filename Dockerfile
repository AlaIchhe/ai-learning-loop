# ═══════════════════════════════════════════════════════════════════════════
# ai-learning-loop —— 多阶段构建 Docker 镜像（uv 驱动）
# ═══════════════════════════════════════════════════════════════════════════
# 构建: docker build -t ai-learning-loop .
# 运行: docker run -p 3003:3003 -p 8003:8003 --env-file .env ai-learning-loop
#
# 优势:
#   - uv 安装依赖比 pip 快 10-100x
#   - uv.lock 确保可重现构建
#   - 多阶段构建减小最终镜像体积
# ═══════════════════════════════════════════════════════════════════════════

# ── Stage 1: uv + 依赖安装 ────────────────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /app

# 安装 uv（官方静态二进制镜像）
COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /uvx /bin/

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖定义（利用 Docker 缓存层——仅当 pyproject.toml/uv.lock 变化时重建）
COPY pyproject.toml uv.lock MANIFEST.in ./

# 安装生产依赖 + 项目本身（--frozen 使用 uv.lock，不重新解析）
# --no-dev 跳过开发依赖（ruff, pytest 等）
RUN uv sync --frozen --no-dev

# ── Stage 2: 最终镜像 ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# 从 deps 阶段复制已安装的包 + console_scripts 入口
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# 复制应用代码
COPY socratic_loop/ ./socratic_loop/
COPY web/ ./web/
COPY rxconfig.py ./

# 创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app

# 切换到非 root 用户
USER appuser

# 环境变量
ENV PYTHONUTF8=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 暴露端口（默认值；运行时可通过 -e 覆盖）
EXPOSE 3003 8003

# 健康检查（端口可通过环境变量覆盖，默认 8003）
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; port='${BACKEND_PORT:-8003}'; urllib.request.urlopen(f'http://localhost:{port}/health', timeout=5)" || exit 1

# 启动命令（使用 console_scripts 入口）
ENTRYPOINT ["ai-learning-loop"]
