"""Issue short-lived local demo JWTs; this is not an identity provider."""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import jwt

from carrefour_schedule_api.config import ScheduleApiSettings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emite JWT local de demonstração")
    parser.add_argument("--user", required=True, help="Identificador local do usuário")
    arguments = parser.parse_args(argv)

    try:
        settings = ScheduleApiSettings.from_environment()
    except (RuntimeError, ValueError):
        print("Configuração da API inválida.", file=sys.stderr)
        return 2

    if not settings.enable_demo_token_issuer:
        print("Emissor de demonstração desabilitado neste ambiente.", file=sys.stderr)
        return 2

    issued_at = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": arguments.user,
            "iat": issued_at,
            "exp": issued_at + timedelta(minutes=30),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
