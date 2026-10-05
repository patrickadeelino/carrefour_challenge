import json
from collections.abc import Callable
from typing import Any

import pytest


@pytest.fixture
def catalog_document_factory() -> Callable[..., str]:
    def build_catalog(
        exams: list[dict[str, Any]] | None = None,
        *,
        count: int = 100,
    ) -> str:
        records = exams or [
            {
                "code": f"CAT-{index:03d}",
                "name": f"Exame sintético {index}",
                "aliases": [],
            }
            for index in range(1, count + 1)
        ]
        return json.dumps({"exams": records}, ensure_ascii=False)

    return build_catalog
