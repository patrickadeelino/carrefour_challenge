from datetime import UTC, datetime

import jwt

from carrefour_schedule_api.demo_token import main
from utils.schedule_api import JWT_SECRET


def test_demo_token_issuer_is_disabled_by_default(monkeypatch, capsys) -> None:
    monkeypatch.setenv("CARREFOUR_SCHEDULE_JWT_SECRET", JWT_SECRET)
    monkeypatch.delenv("CARREFOUR_SCHEDULE_ENABLE_DEMO_TOKEN_ISSUER", raising=False)

    result = main(["--user", "local-user"])

    captured = capsys.readouterr()
    assert result == 2
    assert captured.out == ""
    assert "desabilitado" in captured.err


def test_demo_token_issuer_creates_short_lived_local_jwt(monkeypatch, capsys) -> None:
    monkeypatch.setenv("CARREFOUR_SCHEDULE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("CARREFOUR_SCHEDULE_ENABLE_DEMO_TOKEN_ISSUER", "true")

    result = main(["--user", "local-user"])

    captured = capsys.readouterr()
    claims = jwt.decode(captured.out.strip(), JWT_SECRET, algorithms=["HS256"])
    assert result == 0
    assert captured.err == ""
    assert claims["sub"] == "local-user"
    assert 0 < claims["exp"] - int(datetime.now(UTC).timestamp()) <= 1800


def test_demo_token_issuer_fails_closed_without_valid_api_settings(monkeypatch, capsys):
    monkeypatch.setenv("CARREFOUR_SCHEDULE_JWT_SECRET", "short")

    assert main(["--user", "local-user"]) == 2
    assert "inválida" in capsys.readouterr().err
