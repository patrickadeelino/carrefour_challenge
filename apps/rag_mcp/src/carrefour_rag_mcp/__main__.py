"""Process entrypoint for the RAG MCP SSE server."""

from __future__ import annotations

import asyncio
import atexit
import logging
import os

import uvicorn
from carrefour_observability.telemetry import (
    configure_telemetry,
    shutdown_telemetry,
)

from carrefour_rag_mcp.application import create_application
from carrefour_rag_mcp.catalog.errors import CatalogLoadError
from carrefour_rag_mcp.server import create_sse_app

RAG_HOST = "0.0.0.0"
RAG_PORT = 8000
ALLOWED_HOSTS_ENV = "CARREFOUR_RAG_ALLOWED_HOSTS"
logger = logging.getLogger("carrefour_rag_mcp.__main__")


def _allowed_hosts_from_environment() -> list[str]:
    configured_hosts = os.environ.get(ALLOWED_HOSTS_ENV, "")
    allowed_hosts = [
        host.strip() for host in configured_hosts.split(",") if host.strip()
    ]
    if allowed_hosts:
        return allowed_hosts

    logger.error(
        "rag.configuration.failed",
        extra={
            "event_name": "rag.configuration.failed",
            "component": "sse_server",
            "error_code": "allowed_hosts_missing",
            "error_type": "SystemExit",
        },
    )
    raise SystemExit(f"{ALLOWED_HOSTS_ENV} deve conter ao menos um host.")


async def _serve() -> None:
    allowed_hosts = _allowed_hosts_from_environment()
    mcp_server = create_application()
    app = create_sse_app(mcp_server, allowed_hosts)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=RAG_HOST,
            port=RAG_PORT,
            log_level="info",
            access_log=False,
        )
    )
    await server.serve()


def main() -> None:
    configure_telemetry("rag-mcp", "carrefour_rag_mcp")
    atexit.register(shutdown_telemetry)
    try:
        asyncio.run(_serve())
    except CatalogLoadError as error:
        raise SystemExit(str(error)) from None
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
