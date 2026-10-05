import json

import pytest

from carrefour_ocr_mcp.services.exam_extractor import (
    ExamImageError,
    VisionExamExtractor,
)


@pytest.mark.anyio
async def test_vision_service_delegates_to_factory_and_returns_only_exams(
    caplog: pytest.LogCaptureFixture,
    numbered_vision_annotation: dict[str, object],
    numbered_request_image: bytes,
    vision_client_factory,
) -> None:
    full_text_annotation = numbered_vision_annotation["fullTextAnnotation"]
    assert isinstance(full_text_annotation, dict)
    full_text = full_text_annotation["text"]
    assert isinstance(full_text, str)
    full_text_annotation["text"] = (
        "PACIENTE TESTE 001\nCPF 000.000.000-00\n"
        + full_text
        + "\nTELEFONE (00) 00000-0000"
    )
    vision_client = vision_client_factory(numbered_vision_annotation)

    result = await VisionExamExtractor(vision_client).extract_exams(
        numbered_request_image
    )

    assert result["exams"][0] == "Hemograma completo"
    assert vision_client.received_image == numbered_request_image
    assert "PACIENTE TESTE" not in json.dumps(result)
    assert "000.000.000-00" not in json.dumps(result)
    assert "PACIENTE TESTE" not in caplog.text
    assert "000.000.000-00" not in caplog.text


@pytest.mark.anyio
async def test_invalid_image_is_rejected_before_calling_vision(
    vision_client_factory,
) -> None:
    vision_client = vision_client_factory({})

    with pytest.raises(ExamImageError):
        await VisionExamExtractor(vision_client).extract_exams(b"invalid image")

    assert vision_client.received_image is None
