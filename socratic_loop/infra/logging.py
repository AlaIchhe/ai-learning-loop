"""
结构化日志与可观测性基础设施。

提供：
1. 请求级 trace_id 生成与传播
2. LLM 调用计时与 token 统计
3. 结构化日志辅助（JSON 行格式，便于日志聚合）

用法：
    from socratic_loop.infra.logging import TraceLogger, trace_id_context

    with trace_id_context() as trace_id:
        tlog = TraceLogger(trace_id)
        tlog.llm_call_start(model="deepseek-chat", label="opponent")
        # ... LLM call ...
        tlog.llm_call_end(duration_ms=1234, success=True)
"""

import logging
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field

# =============================================================================
# Trace ID 管理
# =============================================================================

_trace_id_stack: list[str] = []


@contextmanager
def trace_id_context(trace_id: str | None = None) -> Generator[str]:
    """上下文管理器：为当前调用链注入 trace_id。

    用法：
        with trace_id_context() as tid:
            # tid 在整个 with 块内对 get_current_trace_id() 可见
            ...
    """
    tid = trace_id or str(uuid.uuid4())[:8]
    _trace_id_stack.append(tid)
    try:
        yield tid
    finally:
        _trace_id_stack.pop()


def get_current_trace_id() -> str | None:
    """获取当前活跃的 trace_id，若无则返回 None。"""
    return _trace_id_stack[-1] if _trace_id_stack else None


# =============================================================================
# 结构化日志格式
# =============================================================================


def _format_log(level: str, message: str, **fields: object) -> str:
    """构造单行 JSON 日志（便于 logfmt / jq 解析）。"""
    import json as _json

    parts: dict[str, object] = {"level": level, "msg": message}
    tid = get_current_trace_id()
    if tid:
        parts["trace_id"] = tid
    parts.update(fields)
    return _json.dumps(parts, ensure_ascii=False, default=str)


# =============================================================================
# TraceLogger —— 按请求的日志记录器
# =============================================================================


@dataclass
class LlmCallRecord:
    """单次 LLM 调用的结构化记录。"""

    label: str
    model_name: str
    start_ms: float = 0.0
    end_ms: float = 0.0
    duration_ms: float = 0.0
    success: bool = False
    retry_count: int = 0
    error: str | None = None


@dataclass
class TraceLogger:
    """请求级日志记录器 —— 汇总一次 graph.stream() 的所有观测数据。"""

    trace_id: str
    started_at: float = field(default_factory=time.monotonic)
    llm_calls: list[LlmCallRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # 内部状态
    _current_call: LlmCallRecord | None = None
    _logger: logging.Logger = field(default_factory=lambda: logging.getLogger("ai-learning-loop"))

    # ------------------------------------------------------------------
    # LLM 调用计时
    # ------------------------------------------------------------------

    def llm_call_start(self, *, model: str, label: str) -> None:
        """标记一次 LLM 调用的开始。"""
        self._current_call = LlmCallRecord(
            label=label,
            model_name=model,
            start_ms=time.monotonic() * 1000,
        )

    def llm_call_end(
        self,
        *,
        success: bool = True,
        retry_count: int = 0,
        error: str | None = None,
    ) -> None:
        """标记当前 LLM 调用结束并记录指标。"""
        if self._current_call is None:
            return
        self._current_call.end_ms = time.monotonic() * 1000
        self._current_call.duration_ms = round(self._current_call.end_ms - self._current_call.start_ms, 1)
        self._current_call.success = success
        self._current_call.retry_count = retry_count
        self._current_call.error = error

        record = self._current_call
        self.llm_calls.append(record)

        log_data = {
            "model": record.model_name,
            "label": record.label,
            "duration_ms": record.duration_ms,
            "success": record.success,
            "retries": record.retry_count,
        }
        if record.error:
            log_data["error"] = record.error

        self._logger.info(_format_log("INFO", "LLM call completed", **log_data))
        self._current_call = None

    # ------------------------------------------------------------------
    # 错误追踪
    # ------------------------------------------------------------------

    def record_error(self, error: str) -> None:
        """记录一次请求级错误。"""
        self.errors.append(error)
        self._logger.error(_format_log("ERROR", "Request error", error=error))

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """返回当前请求的汇总指标。"""
        total_duration = round((time.monotonic() - self.started_at) * 1000, 1)
        llm_duration = sum(c.duration_ms for c in self.llm_calls)
        success_count = sum(1 for c in self.llm_calls if c.success)
        total_retries = sum(c.retry_count for c in self.llm_calls)

        return {
            "trace_id": self.trace_id,
            "total_duration_ms": total_duration,
            "llm_duration_ms": round(llm_duration, 1),
            "llm_calls": len(self.llm_calls),
            "llm_successes": success_count,
            "llm_failures": len(self.llm_calls) - success_count,
            "total_retries": total_retries,
            "errors": len(self.errors),
        }


# =============================================================================
# 便捷函数
# =============================================================================


def create_trace_logger(trace_id: str | None = None) -> tuple[str, TraceLogger]:
    """创建一个 trace_id 和关联的 TraceLogger。

    便捷函数，等价于：
        with trace_id_context() as tid:
            tlog = TraceLogger(tid)
    """
    tid = trace_id or str(uuid.uuid4())[:8]
    return tid, TraceLogger(tid)
