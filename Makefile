# ═══════════════════════════════════════════════════════════════════════════
# ai-learning-loop —— 常用操作快捷方式（uv 驱动）
# ═══════════════════════════════════════════════════════════════════════════
# 开发:
#   make install      开发安装（uv sync --all-extras）
#   make test         运行测试
#   make lint         静态检查
#   make check        测试 + 静态检查
#
# 构建:
#   make build        构建 wheel + sdist
#   make clean        清理构建产物
#
# 发布:
#   make publish-test 发布到 TestPyPI
#   make publish      发布到 PyPI
#
# Docker:
#   make docker-build 构建 Docker 镜像
#   make docker-run   运行 Docker 容器
# ═══════════════════════════════════════════════════════════════════════════

.PHONY: help install test test-quick lint lint-fix format type-check check \
        clean build publish-test publish \
        docker-build docker-run docker-stop docker-logs run export-graph lock

# ── 默认目标 ──────────────────────────────────────────────────────────────
help: ## 显示帮助信息
	@echo "ai-learning-loop —— 可用命令:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "示例: make install"

# ── 安装 ──────────────────────────────────────────────────────────────────
install: ## 开发安装（含所有 extras + dev 依赖）
	uv sync --all-extras

lock: ## 更新 uv.lock
	uv lock

# ── 测试 ──────────────────────────────────────────────────────────────────
test: ## 运行测试套件
	uv run python -m pytest tests/ -v

test-quick: ## 快速测试（无详细输出）
	uv run python -m pytest tests/ -q

# ── 静态检查 ──────────────────────────────────────────────────────────────
lint: ## Ruff 检查
	uv run ruff check .

lint-fix: ## Ruff 自动修复
	uv run ruff check --fix .

format: ## Ruff 格式化
	uv run ruff format .

type-check: ## 类型检查（pyright + mypy）
	uv run pyright .
	uv run mypy socratic_loop/core/ socratic_loop/infra/ socratic_loop/agents/ socratic_loop/workflow/ --ignore-missing-imports

check: lint type-check test ## 完整检查（lint + type + test）

# ── 构建 ──────────────────────────────────────────────────────────────────
clean: ## 清理构建产物
	rm -rf build/ dist/ *.egg-info .eggs/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov/

build: clean ## 构建 wheel + sdist
	uv build
	uv twine check dist/*

# ── 发布 ──────────────────────────────────────────────────────────────────
publish-test: build ## 发布到 TestPyPI
	uv twine upload --repository testpypi dist/*

publish: build ## 发布到 PyPI
	uv twine upload dist/*

# ── Docker ────────────────────────────────────────────────────────────────
docker-build: ## 构建 Docker 镜像
	docker compose build

docker-run: ## 运行 Docker 容器
	docker compose up -d

docker-stop: ## 停止 Docker 容器
	docker compose down

docker-logs: ## 查看 Docker 日志
	docker compose logs -f

# ── 开发服务器 ────────────────────────────────────────────────────────────
run: ## 启动开发服务器
	uv run ai-learning-loop

export-graph: ## 导出 LangGraph 架构图
	uv run debate-graph
