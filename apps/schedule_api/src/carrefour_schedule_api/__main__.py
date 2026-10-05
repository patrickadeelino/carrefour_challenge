"""Run the local API server with HTTP access logs disabled."""

import uvicorn

from carrefour_schedule_api.app import create_app


def main() -> None:
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=8000,
        access_log=False,
    )


if __name__ == "__main__":
    main()
