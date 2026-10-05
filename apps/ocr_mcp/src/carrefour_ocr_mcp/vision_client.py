from __future__ import annotations

import base64
import logging
import os
from time import monotonic
from typing import cast

import httpx

VISION_ANNOTATE_URL = "https://vision.googleapis.com/v1/images:annotate"
DOCUMENT_TEXT_DETECTION = "DOCUMENT_TEXT_DETECTION"
DEFAULT_TIMEOUT_SECONDS = 60.0
logger = logging.getLogger(__name__)


class VisionClientError(Exception):
    """Base class for sanitized Cloud Vision client failures."""

    error_code = "vision_client_failed"
    component = "vision_client"


class VisionConfigurationError(VisionClientError):
    """Raised when the runtime does not provide a usable API key."""

    error_code = "vision_configuration_invalid"


class VisionTimeoutError(VisionClientError):
    """Raised when Cloud Vision does not respond before the timeout."""

    error_code = "vision_timeout"


class VisionConnectionError(VisionClientError):
    """Raised when the client cannot connect to Cloud Vision."""

    error_code = "vision_connection_failed"


class VisionApiError(VisionClientError):
    """Raised when Cloud Vision rejects the OCR request."""

    error_code = "vision_api_rejected"


class VisionResponseError(VisionClientError):
    """Raised when Cloud Vision returns an invalid response."""

    error_code = "vision_invalid_response"


class GoogleCloudVisionClient:
    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not api_key.strip():
            raise VisionConfigurationError(
                "GOOGLE_CLOUD_VISION_API_KEY não configurada."
            )

        self._api_key = api_key
        self._http_client = http_client
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(
        cls,
        http_client: httpx.AsyncClient,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> GoogleCloudVisionClient:
        api_key = os.environ.get("GOOGLE_CLOUD_VISION_API_KEY", "")
        if not api_key.strip():
            raise VisionConfigurationError(
                "GOOGLE_CLOUD_VISION_API_KEY não configurada."
            )
        return cls(api_key.strip(), http_client, timeout_seconds)

    async def detect_document_text(self, image: bytes) -> dict[str, object]:
        started_at = monotonic()
        logger.info(
            "vision.request.started",
            extra={
                "event_name": "vision.request.started",
                "component": "vision_client",
            },
        )
        try:
            annotation = await self._request_document_text(image)
        except Exception as error:
            logger.error(
                "vision.request.failed",
                extra={
                    "event_name": "vision.request.failed",
                    "component": getattr(error, "component", "vision_client"),
                    "duration_ms": _duration_ms(started_at),
                    "error_code": getattr(
                        error, "error_code", "vision_unexpected_failure"
                    ),
                    "error_type": type(error).__name__,
                },
            )
            raise

        logger.info(
            "vision.request.completed",
            extra={
                "event_name": "vision.request.completed",
                "component": "vision_client",
                "duration_ms": _duration_ms(started_at),
                "outcome": "success",
            },
        )
        return annotation

    async def _request_document_text(self, image: bytes) -> dict[str, object]:
        request_body = {
            "requests": [
                {
                    "image": {"content": base64.b64encode(image).decode("ascii")},
                    "features": [{"type": DOCUMENT_TEXT_DETECTION}],
                }
            ]
        }
        try:
            response = await self._http_client.post(
                VISION_ANNOTATE_URL,
                headers={"X-Goog-Api-Key": self._api_key},
                json=request_body,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            raise VisionTimeoutError(
                "Cloud Vision excedeu o limite de tempo."
            ) from None
        except httpx.HTTPStatusError as error:
            raise VisionApiError(
                f"Cloud Vision retornou HTTP {error.response.status_code}."
            ) from None
        except httpx.RequestError:
            raise VisionConnectionError(
                "Não foi possível conectar ao Cloud Vision."
            ) from None

        try:
            payload = response.json()
        except ValueError:
            raise VisionResponseError("Cloud Vision retornou JSON inválido.") from None

        if not isinstance(payload, dict):
            raise VisionResponseError("Cloud Vision retornou uma resposta inválida.")

        responses = payload.get("responses")
        if (
            not isinstance(responses, list)
            or len(responses) != 1
            or not isinstance(responses[0], dict)
        ):
            raise VisionResponseError("Cloud Vision retornou uma resposta inválida.")

        annotation = cast(dict[str, object], responses[0])
        if "error" in annotation:
            raise VisionApiError("Cloud Vision rejeitou a solicitação de OCR.")
        return annotation


def _duration_ms(started_at: float) -> int:
    return round((monotonic() - started_at) * 1000)
