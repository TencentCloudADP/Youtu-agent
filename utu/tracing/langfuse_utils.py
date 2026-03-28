import os

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter


class LangfuseUtils:
    """Utilities for Langfuse tracing integration.

    Langfuse supports OpenTelemetry protocol for trace ingestion.
    Ref: https://langfuse.com/docs/opentelemetry/get-started
    """

    def __init__(
        self,
        base_url: str = None,
        public_key: str = None,
        secret_key: str = None,
        project_name: str = None,
    ):
        self.base_url = base_url or os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
        self.public_key = public_key or os.getenv("LANGFUSE_PUBLIC_KEY", "")
        self.secret_key = secret_key or os.getenv("LANGFUSE_SECRET_KEY", "")
        self.project_name = project_name or os.getenv("LANGFUSE_PROJECT_NAME", "")

        if not self.public_key or not self.secret_key:
            raise ValueError("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set")

        print(f"Using Langfuse base url: {self.base_url} with project name: {self.project_name}")

    def get_otlp_endpoint(self) -> str:
        """Get the OTLP endpoint for Langfuse.

        Returns:
            The OTLP HTTP endpoint URL for sending traces.
        """
        # Langfuse OTLP endpoint path: /api/public/otel/v1/traces
        # Ref: https://langfuse.com/docs/opentelemetry/get-started
        return f"{self.base_url.rstrip('/')}/api/public/otel/v1/traces"

    def get_otlp_headers(self) -> dict[str, str]:
        """Get the OTLP headers for authentication.

        Langfuse uses Basic authentication with public_key:secret_key.

        Returns:
            Dictionary containing the Authorization header.
        """
        import base64

        credentials = base64.b64encode(f"{self.public_key}:{self.secret_key}".encode()).decode()
        headers = {"Authorization": f"Basic {credentials}"}
        if self.project_name:
            headers["X-Langfuse-Project-Name"] = self.project_name
        return headers

    def create_span_exporter(self) -> OTLPSpanExporter:
        """Create an OTLP span exporter configured for Langfuse.

        Returns:
            Configured OTLPSpanExporter instance.
        """
        return OTLPSpanExporter(
            endpoint=self.get_otlp_endpoint(),
            headers=self.get_otlp_headers(),
        )

    def get_trace_url(self, trace_id: str) -> str | None:
        """Get the URL to view a trace in Langfuse UI.

        Args:
            trace_id: The trace ID to look up.

        Returns:
            URL to the trace in Langfuse UI, or None if not available.
        """
        if not trace_id:
            return None
        # Langfuse trace URL format
        return f"{self.base_url.rstrip('/')}/trace/{trace_id}"
