import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from carrefour_observability.logging_config import JsonEventFormatter

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def json_log_capture():
    @contextmanager
    def capture(logger_namespace: str, service_name: str) -> Iterator[StringIO]:
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonEventFormatter(service_name))
        logger = logging.getLogger(logger_namespace)
        previous_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            yield stream
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)
            handler.close()

    return capture


class FakeVisionClient:
    def __init__(self, annotation: dict[str, object]) -> None:
        self.annotation = annotation
        self.received_image: bytes | None = None

    async def detect_document_text(self, image: bytes) -> dict[str, object]:
        self.received_image = image
        return self.annotation


@pytest.fixture
def vision_client_factory() -> type[FakeVisionClient]:
    return FakeVisionClient


@pytest.fixture
def numbered_vision_annotation() -> dict[str, Any]:
    contents = (FIXTURES / "vision" / "numbered_list.json").read_text(encoding="utf-8")
    return json.loads(contents)


@pytest.fixture
def checkbox_vision_annotation() -> dict[str, Any]:
    contents = (FIXTURES / "vision" / "checkboxes.json").read_text(encoding="utf-8")
    return json.loads(contents)


@pytest.fixture
def numbered_request_image() -> bytes:
    return (FIXTURES / "images" / "exam_request_pt_br.png").read_bytes()


@pytest.fixture
def checkbox_request_image() -> bytes:
    return (FIXTURES / "images" / "exam_request_pt_br_simplified.png").read_bytes()


@pytest.fixture
def partial_mark_request_image() -> bytes:
    return (FIXTURES / "images" / "exam_request_pt_br_partial_mark.png").read_bytes()
