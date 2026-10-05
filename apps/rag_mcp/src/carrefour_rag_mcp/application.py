"""Composition root for the RAG MCP application."""

from __future__ import annotations

import logging
from collections.abc import Callable
from time import monotonic

from carrefour_observability.logging_config import configure_json_logging
from mcp.server import MCPServer

from carrefour_rag_mcp.catalog.errors import CatalogLoadError
from carrefour_rag_mcp.catalog.loader import CatalogLoader
from carrefour_rag_mcp.catalog.models import CatalogDocument
from carrefour_rag_mcp.server import create_server
from carrefour_rag_mcp.services.exam_search import ExamSearchService

logger = logging.getLogger(__name__)
CatalogLoaderFunction = Callable[[], CatalogDocument]


def create_application(
    catalog_loader: CatalogLoaderFunction = CatalogLoader.load_bundled,
) -> MCPServer:
    """Load the bundled catalog, log readiness, and build an MCP server."""
    configure_json_logging("carrefour_rag_mcp", "rag-mcp")
    started_at = monotonic()
    try:
        search_service = ExamSearchService(catalog_loader())
    except CatalogLoadError as error:
        _log_catalog_failure(error.error_code, type(error).__name__, started_at)
        raise
    except Exception as error:
        _log_catalog_failure("catalog_unavailable", type(error).__name__, started_at)
        raise CatalogLoadError("catalog_unavailable") from None

    logger.info(
        "rag.catalog.ready",
        extra={
            "event_name": "rag.catalog.ready",
            "component": "catalog_index",
            "duration_ms": _duration_ms(started_at),
            "outcome": "success",
        },
    )
    return create_server(search_service)


def _log_catalog_failure(
    error_code: str,
    error_type: str,
    started_at: float,
) -> None:
    logger.error(
        "rag.catalog.failed",
        extra={
            "event_name": "rag.catalog.failed",
            "component": "catalog_loader",
            "duration_ms": _duration_ms(started_at),
            "error_code": error_code,
            "error_type": error_type,
            "outcome": "failed",
        },
    )


def _duration_ms(started_at: float) -> int:
    return round((monotonic() - started_at) * 1000)
