from functools import wraps
from typing import Callable, Any
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from app.config import settings


_tracer_provider: TracerProvider | None = None


def setup_tracing():
    global _tracer_provider

    if not settings.otel_enabled:
        return

    resource = Resource.create({"service.name": settings.otel_service_name})
    _tracer_provider = TracerProvider(resource=resource)

    if settings.otel_exporter == "otlp":
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
        except ImportError:
            # Fallback to console if OTLP exporter is not installed
            exporter = ConsoleSpanExporter()
    else:
        exporter = ConsoleSpanExporter()

    _tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(_tracer_provider)


def get_tracer(name: str) -> trace.Tracer:
    if _tracer_provider is None:
        setup_tracing()
    return trace.get_tracer(name)


def trace_workflow(workflow_name: str):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer("autoloop.workflow")
            with tracer.start_as_current_span(workflow_name) as span:
                span.set_attribute("workflow.name", workflow_name)
                result = await func(*args, **kwargs)
                return result

        return wrapper

    return decorator


def trace_activity(activity_name: str):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer("autoloop.activity")
            with tracer.start_as_current_span(activity_name) as span:
                span.set_attribute("activity.name", activity_name)
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("activity.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("activity.status", "failed")
                    span.record_exception(e)
                    raise

        return wrapper

    return decorator
