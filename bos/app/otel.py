"""
OpenTelemetry instrumentation (opt-in).

When BOS_OTEL_EXPORTER_OTLP_ENDPOINT is set, instruments:
  - FastAPI requests (auto via opentelemetry-instrumentation-fastapi)
  - SQLAlchemy DB calls (auto via opentelemetry-instrumentation-sqlalchemy)
  - Every LangGraph node (manual spans via tracer)
  - Token / cost metrics (manual counters + histograms)

If the env var is not set, this module is a no-op.

Usage in main.py:
    from .otel import setup_otel, get_tracer
    setup_otel(app)
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("my_node"):
        ...
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Optional

log = logging.getLogger("bos.otel")

_tracer = None
_meter = None
_counters: dict = {}
_histograms: dict = {}


def is_enabled() -> bool:
    return bool(os.environ.get("BOS_OTEL_EXPORTER_OTLP_ENDPOINT"))


def setup_otel(app=None) -> None:
    """Initialize OTel SDK and instrument FastAPI / SQLAlchemy if enabled.

    Idempotent: safe to call multiple times.
    """
    global _tracer, _meter
    if not is_enabled():
        log.info("OpenTelemetry disabled (set BOS_OTEL_EXPORTER_OTLP_ENDPOINT to enable)")
        return
    if _tracer is not None:
        return  # already initialized

    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    except ImportError:
        log.warning(
            "OpenTelemetry enabled but packages not installed. "
            "Run: pip install opentelemetry-sdk opentelemetry-exporter-otlp "
            "opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy"
        )
        return

    resource = Resource.create({
        "service.name": os.environ.get("BOS_OTEL_SERVICE_NAME", "brokerage-os"),
        "service.version": "1.0.0",
        "deployment.environment": os.environ.get("BOS_ENV", "dev"),
    })

    # Traces
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=os.environ["BOS_OTEL_EXPORTER_OTLP_ENDPOINT"]))
    )
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("bos")

    # Metrics
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=os.environ["BOS_OTEL_EXPORTER_OTLP_ENDPOINT"]),
        export_interval_millis=30000,
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))
    _meter = metrics.get_meter("bos")

    # Pre-register metrics
    _register_default_metrics()

    # Auto-instrument FastAPI
    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(app)
            log.info("FastAPI instrumented for OTel")
        except ImportError:
            log.warning("FastAPI OTel instrumentation skipped (package not installed)")

    # Auto-instrument SQLAlchemy
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from .db import get_engine
        SQLAlchemyInstrumentor().instrument(engine=get_engine())
        log.info("SQLAlchemy instrumented for OTel")
    except (ImportError, Exception) as e:
        log.warning("SQLAlchemy OTel instrumentation skipped: %s", e)

    log.info("OpenTelemetry initialized (endpoint=%s)",
             os.environ["BOS_OTEL_EXPORTER_OTLP_ENDPOINT"])


def _register_default_metrics() -> None:
    """Create the canonical BOS metric instruments."""
    global _meter
    if _meter is None:
        return
    _counters["llm_calls"] = _meter.create_counter(
        "bos.llm.calls", unit="1", description="Number of LLM calls"
    )
    _histograms["llm_latency_ms"] = _meter.create_histogram(
        "bos.llm.latency_ms", unit="ms", description="LLM call latency"
    )
    _histograms["llm_tokens"] = _meter.create_histogram(
        "bos.llm.tokens", unit="1", description="Tokens per LLM call"
    )
    _histograms["llm_cost_usd"] = _meter.create_histogram(
        "bos.llm.cost_usd", unit="USD", description="Estimated cost per LLM call"
    )
    _counters["workflow_completions"] = _meter.create_counter(
        "bos.workflow.completions", unit="1", description="Workflows completed"
    )
    _counters["workflow_errors"] = _meter.create_counter(
        "bos.workflow.errors", unit="1", description="Workflow errors"
    )
    _counters["approval_decisions"] = _meter.create_counter(
        "bos.approval.decisions", unit="1", description="Approval decisions made"
    )


def get_tracer(name: str = "bos"):
    """Return the OTel tracer (or a no-op if OTel disabled)."""
    if not is_enabled() or _tracer is None:
        return _NoOpTracer()
    return _tracer


def record_llm_call(node: str, model: str, latency_ms: int,
                    tokens: int, cost_usd: float, success: bool) -> None:
    """Push LLM metrics to OTel (no-op if disabled)."""
    if not is_enabled() or _meter is None:
        return
    attrs = {"node": node, "model": model, "success": str(success)}
    if success:
        _counters["llm_calls"].add(1, attrs)
    else:
        _counters["workflow_errors"].add(1, attrs)
    _histograms["llm_latency_ms"].record(latency_ms, attrs)
    _histograms["llm_tokens"].record(tokens, attrs)
    _histograms["llm_cost_usd"].record(cost_usd, attrs)


def record_workflow_completion(success: bool, intent: str = "") -> None:
    if not is_enabled() or _meter is None:
        return
    attrs = {"intent": intent, "success": str(success)}
    if success:
        _counters["workflow_completions"].add(1, attrs)
    else:
        _counters["workflow_errors"].add(1, attrs)


def record_approval_decision(decision: str, intent: str = "") -> None:
    if not is_enabled() or _meter is None:
        return
    _counters["approval_decisions"].add(1, {"decision": decision, "intent": intent})


class _NoOpTracer:
    """Fallback tracer when OTel is disabled. Methods are no-ops."""
    @contextmanager
    def start_as_current_span(self, name: str, **kw):
        class _Span:
            def set_attribute(self, *a, **kw): pass
            def set_status(self, *a, **kw): pass
            def record_exception(self, *a, **kw): pass
            def add_event(self, *a, **kw): pass
        yield _Span()

    def start_span(self, name: str, **kw):
        class _Span:
            def set_attribute(self, *a, **kw): pass
            def end(self): pass
        return _Span()
