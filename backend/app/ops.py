"""运维支撑：速率限制 / 登录失败锁定 / 请求指标 / 追踪上下文。

面向企业交付的内建硬化层，全部内存实现、零外部依赖：
- 登录端点按「IP+用户名」滑动窗口限流，超阈值直接 429
- 全局 API 按 IP 宽松限流，防单点滥用
- 请求指标计数器，供 /api/metrics 输出 Prometheus 文本
- trace_id 走 contextvars，日志/响应头可关联贯穿
"""
import logging
import threading
import time
import uuid
from collections import deque
from contextvars import ContextVar
from functools import lru_cache

logger = logging.getLogger("medconsult")

_trace_id: ContextVar[str] = ContextVar("trace_id", default="-")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


def current_trace_id() -> str:
    return _trace_id.get()


def set_trace_id(tid: str) -> None:
    _trace_id.set(tid)


class SlidingWindowLimiter:
    """滑动窗口限流：window_secs 内最多 max_hits 次。线程安全。"""

    def __init__(self, max_hits: int, window_secs: int):
        self.max_hits = max_hits
        self.window_secs = window_secs
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            dq = self._hits.setdefault(key, deque())
            while dq and now - dq[0] > self.window_secs:
                dq.popleft()
            if len(dq) >= self.max_hits:
                return False
            dq.append(now)
            return True

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


class LoginLock:
    """登录失败锁定：同一账户/IP 失败达阈值后锁定，也可主动清零。"""

    def __init__(self, threshold: int, lock_secs: int):
        self.threshold = threshold
        self.lock_secs = lock_secs
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def fail(self, key: str) -> int:
        """记录一次失败，返回当前失败次数（达到阈值视为锁定）。"""
        now = time.monotonic()
        with self._lock:
            buf = [t for t in self._fails.get(key, []) if now - t <= self.lock_secs]
            buf.append(now)
            self._fails[key] = buf
            return len(buf)

    def is_locked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            buf = [t for t in self._fails.get(key, []) if now - t <= self.lock_secs]
            # 若已过期但长于阈值，视为锁定窗口期内不可再试
            return len(buf) >= self.threshold and (now - buf[0]) <= self.lock_secs

    def clear(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)


class Metrics:
    """轻量请求指标（Prometheus 文本格式，无外部依赖）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._total = 0
        self._status: dict[int, int] = {}
        self._latency_sum_ms = 0.0
        self._latency_count = 0
        self._start = time.time()

    def observe(self, status_code: int, latency_ms: float) -> None:
        with self._lock:
            self._total += 1
            self._status[status_code] = self._status.get(status_code, 0) + 1
            self._latency_sum_ms += latency_ms
            self._latency_count += 1

    def render(self) -> str:
        with self._lock:
            total = self._total
            status = dict(self._status)
            latency_sum = self._latency_sum_ms
            latency_count = self._latency_count
            uptime = time.time() - self._start
        lines = [
            "# HELP medconsult_http_requests_total 已处理请求总数",
            "# TYPE medconsult_http_requests_total counter",
            f"medconsult_http_requests_total {total}",
            "# HELP medconsult_http_request_duration_ms_avg 平均请求耗时(ms)",
            "# TYPE medconsult_http_request_duration_ms_avg gauge",
            f"medconsult_http_request_duration_ms_avg {(latency_sum / latency_count) if latency_count else 0:.2f}",
            "# HELP medconsult_http_requests_by_status 按状态码请求数",
            "# TYPE medconsult_http_requests_by_status counter",
        ]
        for code in sorted(status):
            lines.append(f"medconsult_http_requests_by_status{{status=\"{code}\"}} {status[code]}")
        lines.append("# HELP medconsult_uptime_seconds 进程运行时长(秒)")
        lines.append("# TYPE medconsult_uptime_seconds gauge")
        lines.append(f"medconsult_uptime_seconds {uptime:.0f}")
        return "\n".join(lines)


metrics = Metrics()


@lru_cache
def get_login_lock() -> LoginLock:
    """按配置构建全局登录锁定器（单一实例，供 main/auth 共用）。"""
    from .config import get_settings
    s = get_settings()
    return LoginLock(s.login_fail_threshold, s.login_lock_seconds)