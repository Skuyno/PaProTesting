"""Prometheus metrics for the payment service."""

from prometheus_client import Counter, Gauge

operations_by_status = Gauge(
    "payment_operations",
    "Number of operations by current status.",
    ["status"],
)

dispatch_attempts = Counter(
    "payment_dispatch_attempts_total",
    "Dispatch attempts to the provider by result.",
    ["result"],
)
