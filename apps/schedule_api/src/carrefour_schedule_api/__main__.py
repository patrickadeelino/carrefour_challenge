"""Run the local API server with HTTP access logs disabled."""

import atexit

import uvicorn
from carrefour_observability.telemetry import (
    configure_telemetry,
    instrument_asgi_app,
    shutdown_telemetry,
)

from carrefour_schedule_api.app import create_app


def main() -> None:
    app = create_app()
    configure_telemetry("schedule-api", "carrefour_schedule_api")
    atexit.register(shutdown_telemetry)
    app = instrument_asgi_app(app, "carrefour_schedule_api.__main__")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        access_log=False,
    )


if __name__ == "__main__":
    main()
