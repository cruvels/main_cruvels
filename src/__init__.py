"""
Cruvels Legal AI Package Initialization.
Ensures system compatibility and telemetry safeguards for Windows Application Control policies.
"""
import sys
import types

# Disable Chroma telemetry by environment
import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"

# If grpc DLL is blocked by OS Application Control policy, mock OpenTelemetry OTLP exporter
try:
    import grpc  # noqa: F401
except Exception:
    if "opentelemetry.exporter.otlp.proto.grpc.trace_exporter" not in sys.modules:
        trace_mock = types.ModuleType("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")

        class MockOTLPSpanExporter:
            def __init__(self, *args, **kwargs):
                pass

        trace_mock.OTLPSpanExporter = MockOTLPSpanExporter
        sys.modules["opentelemetry.exporter.otlp.proto.grpc.trace_exporter"] = trace_mock
