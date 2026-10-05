import asyncio
import logging
import os
from pathlib import Path

import httpx
import uvicorn
from carrefour_observability.logging_config import configure_json_logging

from carrefour_ocr_mcp.server import create_sse_app
from carrefour_ocr_mcp.services.exam_extractor.vision_exam_extractor import (
    VisionExamExtractor,
)
from carrefour_ocr_mcp.services.pii_guard import (
    PiiConfigurationError,
    PiiOutputGuard,
)
from carrefour_ocr_mcp.services.pii_guard.presidio_analyzer import (
    PresidioPiiAnalyzer,
)
from carrefour_ocr_mcp.vision_client import (
    GoogleCloudVisionClient,
    VisionConfigurationError,
)

IMAGE_STORAGE_PATH = "/var/run/carrefour/images"
OCR_HOST = "0.0.0.0"
OCR_PORT = 8000
# Mantém o namespace do pacote mesmo quando executado como `python -m`.
logger = logging.getLogger("carrefour_ocr_mcp.__main__")


def _create_pii_guard() -> PiiOutputGuard:
    try:
        return PiiOutputGuard(PresidioPiiAnalyzer())
    except Exception:
        raise PiiConfigurationError() from None


def _allowed_hosts_from_environment() -> list[str]:
    configured_hosts = os.environ.get("CARREFOUR_OCR_ALLOWED_HOSTS", "")
    allowed_hosts = [
        host.strip() for host in configured_hosts.split(",") if host.strip()
    ]
    if not allowed_hosts:
        logger.error(
            "ocr.configuration.failed",
            extra={
                "event_name": "ocr.configuration.failed",
                "component": "sse_server",
                "error_code": "allowed_hosts_missing",
                "error_type": "SystemExit",
            },
        )
        raise SystemExit("CARREFOUR_OCR_ALLOWED_HOSTS deve conter ao menos um host.")
    return allowed_hosts


async def _serve() -> None:
    image_directory = Path(
        os.environ.get("CARREFOUR_IMAGE_STORAGE_PATH", IMAGE_STORAGE_PATH)
    )
    allowed_hosts = _allowed_hosts_from_environment()
    pii_guard = _create_pii_guard()

    async with httpx.AsyncClient() as http_client:
        vision_client = GoogleCloudVisionClient.from_environment(http_client)
        extractor = VisionExamExtractor(vision_client)
        app = create_sse_app(
            image_directory,
            extractor,
            allowed_hosts,
            pii_guard,
        )
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=OCR_HOST,
                port=OCR_PORT,
                log_level="info",
                access_log=False,
            )
        )
        await server.serve()


def main() -> None:
    configure_json_logging("carrefour_ocr_mcp", "ocr-mcp")
    try:
        asyncio.run(_serve())
    except VisionConfigurationError as error:
        logger.error(
            "ocr.configuration.failed",
            extra={
                "event_name": "ocr.configuration.failed",
                "component": "vision_client",
                "error_code": error.error_code,
                "error_type": type(error).__name__,
            },
        )
        raise SystemExit(str(error)) from None
    except PiiConfigurationError as error:
        logger.error(
            "ocr.configuration.failed",
            extra={
                "event_name": "ocr.configuration.failed",
                "component": error.component,
                "error_code": error.error_code,
                "error_type": type(error).__name__,
            },
        )
        raise SystemExit(str(error)) from None
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
