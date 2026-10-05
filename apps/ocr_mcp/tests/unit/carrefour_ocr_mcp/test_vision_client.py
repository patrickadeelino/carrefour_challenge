import base64
import json

import httpx
import pytest

from carrefour_ocr_mcp.vision_client import (
    GoogleCloudVisionClient,
    VisionApiError,
    VisionConfigurationError,
    VisionResponseError,
    VisionTimeoutError,
)


@pytest.mark.anyio
async def test_document_text_detection_sends_image_and_returns_annotation(
    json_log_capture,
) -> None:
    image = b"test image bytes"
    annotation = {"fullTextAnnotation": {"text": "Texto OCR de teste"}}
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"responses": [annotation]})

    with json_log_capture("carrefour_ocr_mcp.vision_client", "ocr-mcp") as log_stream:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond)
        ) as http_client:
            vision_client = GoogleCloudVisionClient("test-api-key", http_client)

            result = await vision_client.detect_document_text(image)

    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://vision.googleapis.com/v1/images:annotate"
    assert request.headers["x-goog-api-key"] == "test-api-key"
    assert "test-api-key" not in str(request.url)
    assert request.extensions["timeout"]["read"] == 60.0
    assert json.loads(request.content) == {
        "requests": [
            {
                "image": {"content": base64.b64encode(image).decode("ascii")},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            }
        ]
    }
    assert result == annotation
    records = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    assert [record["event"] for record in records] == [
        "vision.request.started",
        "vision.request.completed",
    ]
    assert records[-1]["component"] == "vision_client"
    assert records[-1]["outcome"] == "success"
    assert "Texto OCR de teste" not in log_stream.getvalue()
    assert "test-api-key" not in log_stream.getvalue()


@pytest.mark.anyio
async def test_timeout_is_reported_without_exposing_transport_details(
    json_log_capture,
) -> None:
    async def timeout(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("internal transport details")

    with json_log_capture("carrefour_ocr_mcp.vision_client", "ocr-mcp") as log_stream:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(timeout)
        ) as http_client:
            vision_client = GoogleCloudVisionClient("test-api-key", http_client)

            with pytest.raises(VisionTimeoutError) as error:
                await vision_client.detect_document_text(b"image")

    assert "internal transport details" not in str(error.value)
    record = json.loads(log_stream.getvalue().splitlines()[-1])
    assert record["event"] == "vision.request.failed"
    assert record["level"] == "ERROR"
    assert record["error_code"] == "vision_timeout"
    assert record["error_type"] == "VisionTimeoutError"
    assert record["duration_ms"] >= 0
    assert "internal transport details" not in log_stream.getvalue()
    assert "test-api-key" not in log_stream.getvalue()


@pytest.mark.anyio
async def test_http_error_is_sanitized_and_not_retried() -> None:
    requests: list[httpx.Request] = []

    async def reject(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(403, text="provider response contains private data")

    async with httpx.AsyncClient(transport=httpx.MockTransport(reject)) as http_client:
        vision_client = GoogleCloudVisionClient("test-api-key", http_client)

        with pytest.raises(VisionApiError) as error:
            await vision_client.detect_document_text(b"image")

    assert "403" in str(error.value)
    assert "private data" not in str(error.value)
    assert "test-api-key" not in str(error.value)
    assert len(requests) == 1


@pytest.mark.anyio
async def test_invalid_json_response_is_reported_as_a_response_error() -> None:
    async def invalid_json(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(invalid_json)
    ) as http_client:
        vision_client = GoogleCloudVisionClient("test-api-key", http_client)

        with pytest.raises(VisionResponseError):
            await vision_client.detect_document_text(b"image")


@pytest.mark.anyio
async def test_unexpected_response_shape_is_rejected() -> None:
    async def invalid_shape(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"responses": []})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(invalid_shape)
    ) as http_client:
        vision_client = GoogleCloudVisionClient("test-api-key", http_client)

        with pytest.raises(VisionResponseError):
            await vision_client.detect_document_text(b"image")


@pytest.mark.anyio
async def test_provider_error_inside_successful_http_response_is_rejected() -> None:
    async def provider_error(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"responses": [{"error": {"message": "internal provider detail"}}]},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(provider_error)
    ) as http_client:
        vision_client = GoogleCloudVisionClient("test-api-key", http_client)

        with pytest.raises(VisionApiError) as error:
            await vision_client.detect_document_text(b"image")

    assert "internal provider detail" not in str(error.value)


@pytest.mark.anyio
async def test_client_loads_api_key_from_runtime_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_VISION_API_KEY", "runtime-key")
    seen_headers: list[httpx.Headers] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers)
        return httpx.Response(200, json={"responses": [{}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        vision_client = GoogleCloudVisionClient.from_environment(http_client)
        await vision_client.detect_document_text(b"image")

    assert seen_headers[0]["x-goog-api-key"] == "runtime-key"


@pytest.mark.anyio
async def test_client_requires_api_key_in_runtime_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_VISION_API_KEY", raising=False)

    async with httpx.AsyncClient() as http_client:
        with pytest.raises(VisionConfigurationError):
            GoogleCloudVisionClient.from_environment(http_client)
