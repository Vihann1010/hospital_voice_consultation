"""Lightweight in-process metrics, exported in Prometheus text format.

A full client library would be heavier than this deployment needs: a handful of
counters and latency buckets answer the questions that actually get asked —
is it up, is it slow, is it erroring, is anything being rate limited.
"""
import threading
import time
from collections import defaultdict
from typing import Dict, List

_LATENCY_BUCKETS_MS = (25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)


def _normalise(path: str) -> str:
    """Collapse ids so cardinality stays bounded."""
    parts = []
    for segment in path.strip("/").split("/"):
        if len(segment) >= 16 and any(character.isdigit() for character in segment):
            parts.append("{id}")
        elif segment.count("-") >= 4:
            parts.append("{id}")
        else:
            parts.append(segment)
    return "/" + "/".join(parts)


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.requests: Dict[tuple, int] = defaultdict(int)
        self.latency: Dict[str, List[int]] = defaultdict(
            lambda: [0] * (len(_LATENCY_BUCKETS_MS) + 1)
        )
        self.latency_sum: Dict[str, float] = defaultdict(float)
        self.rate_limited: Dict[str, int] = defaultdict(int)
        self.errors: Dict[str, int] = defaultdict(int)

    def record_request(self, path: str, status: int, duration_ms: float) -> None:
        route = _normalise(path)
        with self._lock:
            self.requests[(route, status)] += 1
            self.latency_sum[route] += duration_ms
            buckets = self.latency[route]
            for index, edge in enumerate(_LATENCY_BUCKETS_MS):
                if duration_ms <= edge:
                    buckets[index] += 1
                    break
            else:
                buckets[-1] += 1
            if status >= 500:
                self.errors[route] += 1

    def record_rate_limited(self, scope: str) -> None:
        with self._lock:
            self.rate_limited[scope] += 1

    def snapshot(self) -> dict:
        with self._lock:
            total = sum(self.requests.values())
            errors = sum(self.errors.values())
            return {
                "uptime_seconds": round(time.time() - self.started_at, 1),
                "requests_total": total,
                "errors_total": errors,
                "error_rate": round(errors / total, 4) if total else 0.0,
                "rate_limited_total": sum(self.rate_limited.values()),
            }

    def prometheus(self) -> str:
        lines: List[str] = []
        with self._lock:
            lines.append("# HELP satya_uptime_seconds Process uptime.")
            lines.append("# TYPE satya_uptime_seconds gauge")
            lines.append(f"satya_uptime_seconds {time.time() - self.started_at:.1f}")

            lines.append("# HELP satya_http_requests_total HTTP requests by route and status.")
            lines.append("# TYPE satya_http_requests_total counter")
            for (route, status), count in sorted(self.requests.items()):
                lines.append(
                    f'satya_http_requests_total{{route="{route}",status="{status}"}} {count}'
                )

            lines.append("# HELP satya_http_request_duration_ms Request latency histogram.")
            lines.append("# TYPE satya_http_request_duration_ms histogram")
            for route, buckets in sorted(self.latency.items()):
                cumulative = 0
                for index, edge in enumerate(_LATENCY_BUCKETS_MS):
                    cumulative += buckets[index]
                    lines.append(
                        f'satya_http_request_duration_ms_bucket{{route="{route}",le="{edge}"}} {cumulative}'
                    )
                cumulative += buckets[-1]
                lines.append(
                    f'satya_http_request_duration_ms_bucket{{route="{route}",le="+Inf"}} {cumulative}'
                )
                lines.append(
                    f'satya_http_request_duration_ms_sum{{route="{route}"}} {self.latency_sum[route]:.1f}'
                )
                lines.append(
                    f'satya_http_request_duration_ms_count{{route="{route}"}} {cumulative}'
                )

            lines.append("# HELP satya_rate_limited_total Requests rejected by the rate limiter.")
            lines.append("# TYPE satya_rate_limited_total counter")
            for scope, count in sorted(self.rate_limited.items()):
                lines.append(f'satya_rate_limited_total{{scope="{scope}"}} {count}')
        return "\n".join(lines) + "\n"


metrics = Metrics()
