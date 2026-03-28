from utu.tracing.langfuse_utils import LangfuseUtils

langfuse_utils = LangfuseUtils()


def test_get_otlp_endpoint():
    """Test that the OTLP endpoint is correctly formatted."""
    endpoint = langfuse_utils.get_otlp_endpoint()
    print(f"OTLP Endpoint: {endpoint}")
    assert endpoint.endswith("/api/public/otel/v1/traces"), f"Unexpected endpoint: {endpoint}"


def test_get_otlp_headers():
    """Test that the OTLP headers contain Authorization."""
    headers = langfuse_utils.get_otlp_headers()
    print(f"OTLP Headers: {headers}")
    assert "Authorization" in headers, "Authorization header is missing"
    assert headers["Authorization"].startswith("Basic "), "Authorization should use Basic auth"


def test_get_trace_url():
    """Test that the trace URL is correctly formatted."""
    trace_id = "test-trace-id-12345"
    url = langfuse_utils.get_trace_url(trace_id)
    print(f"Trace URL: {url}")
    assert url is not None, "Trace URL should not be None"
    assert trace_id in url, f"Trace ID should be in URL: {url}"
    assert "/trace/" in url, f"URL should contain '/trace/': {url}"


def test_create_span_exporter():
    """Test that the span exporter is created correctly."""
    exporter = langfuse_utils.create_span_exporter()
    print(f"Span Exporter: {exporter}")
    assert exporter is not None, "Span exporter should not be None"
    assert hasattr(exporter, "_endpoint"), "Exporter should have _endpoint attribute"
    assert exporter._endpoint.endswith("/api/public/otel/v1/traces"), (
        f"Unexpected exporter endpoint: {exporter._endpoint}"
    )


if __name__ == "__main__":
    print("Testing LangfuseUtils...")
    print("-" * 50)

    test_get_otlp_endpoint()
    print("✓ test_get_otlp_endpoint passed")
    print("-" * 50)

    test_get_otlp_headers()
    print("✓ test_get_otlp_headers passed")
    print("-" * 50)

    test_get_trace_url()
    print("✓ test_get_trace_url passed")
    print("-" * 50)

    test_create_span_exporter()
    print("✓ test_create_span_exporter passed")
    print("-" * 50)

    print("\nAll tests passed!")
