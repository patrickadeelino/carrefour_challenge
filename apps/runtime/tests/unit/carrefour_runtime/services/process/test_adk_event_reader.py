import pytest

from carrefour_runtime.services.process.adk_event_reader import (
    extract_structured_content,
)
from carrefour_runtime.services.process.errors import ProcessExecutionError


def test_structured_content_is_read_from_the_adk_tool_response() -> None:
    result = {"exams": ["Hemograma completo"]}

    assert extract_structured_content({"structuredContent": result}) == result


@pytest.mark.parametrize(
    "response",
    [
        {"isError": True, "structuredContent": {"exams": []}},
        {"is_error": True, "structuredContent": {"exams": []}},
        {"content": [{"text": "ok"}]},
        None,
    ],
)
def test_tool_error_or_missing_structured_content_is_rejected(response: object) -> None:
    with pytest.raises(ProcessExecutionError, match="resultado estruturado"):
        extract_structured_content(response)
