"""E2E manual do CLI com MCP/Cloud Vision reais e modelo ADK determinístico."""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import sys
import time
from pathlib import Path

import pytest

from carrefour_runtime import cli
from carrefour_runtime.services.image_storage.temporary_store import (
    TemporaryImageStore,
)
from carrefour_runtime.services.process.adk_executor import AdkOcrExecutor
from carrefour_runtime.value_objects.image_id import ImageId
from support.adk_models import DeterministicOcrModel

EXPECTED_EXAMS_BY_IMAGE = {
    "exam_request_pt_br.png": [
        "Hemograma completo",
        "Glicemia de jejum",
        "Hemoglobina glicada (HbA1c)",
        "Colesterol total e frações",
        "TSH (hormônio tireoestimulante)",
    ],
    "exam_request_pt_br_simplified.png": [
        "Hemograma completo",
        "Glicemia de jejum",
        "Hemoglobina glicada (HbA1c)",
        "TSH",
        "Colesterol LDL",
        "Vitamina D (25-OH)",
    ],
}
PATIENT_MARKERS = ("PACIENTE TESTE", "CPF FICTÍCIO")

pytestmark = pytest.mark.e2e


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_VISION_E2E") != "1",
    reason="E2E com Cloud Vision real exige opt-in explícito",
)
def test_processes_one_reference_image_with_live_vision(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _log_progress(capsys, "Iniciando E2E com Cloud Vision real.")
    image_name = os.environ.get("E2E_IMAGE_NAME", "")
    if image_name not in EXPECTED_EXAMS_BY_IMAGE:
        pytest.fail("E2E_IMAGE_NAME deve selecionar uma das duas fixtures previstas")
    _log_progress(capsys, f"Imagem selecionada: {image_name}.")

    image_directory = Path(
        os.environ.get(
            "CARREFOUR_INPUT_IMAGES_DIRECTORY",
            "/workspace/tests/fixtures/images",
        )
    )
    image_path = image_directory / image_name
    generated_agent_path = Path(
        os.environ.get(
            "CARREFOUR_GENERATED_AGENT_PATH", "/workspace/generated/agent.py"
        )
    )
    assert image_path.is_file(), f"fixture não encontrada: {image_path}"
    assert generated_agent_path.is_file(), (
        "Agente gerado ausente; execute o comando generate antes do E2E."
    )
    _log_progress(capsys, "Fixture e agente gerado encontrados.")

    original_digest = _sha256(image_path)
    image_store = TemporaryImageStore()
    test_model = DeterministicOcrModel()
    created_executors: list[AdkOcrExecutor] = []

    def create_deterministic_executor(agent_path: Path) -> AdkOcrExecutor:
        executor = AdkOcrExecutor(agent_path, model_override=test_model)
        created_executors.append(executor)
        return executor

    monkeypatch.setenv("GOOGLE_API_KEY", "deterministic-e2e-model-not-used")
    monkeypatch.setenv("GOOGLE_API_USE_CLIENT_CERTIFICATE", "false")
    monkeypatch.setattr(cli, "_create_ocr_executor", create_deterministic_executor)
    monkeypatch.setattr(
        sys,
        "argv",
        ["carrefour-runtime", "process", "--path", image_name],
    )

    _log_progress(
        capsys,
        "Executando `process`: o OCR chamará o Vision real via MCP/SSE; "
        "o modelo Gemini está substituído pelo modelo determinístico do teste.",
    )
    started_at = time.perf_counter()
    with pytest.raises(SystemExit) as exit_result:
        runpy.run_module("carrefour_runtime", run_name="__main__")
    elapsed_seconds = time.perf_counter() - started_at
    captured = capsys.readouterr()

    _log_progress(
        capsys,
        f"Comando encerrado em {elapsed_seconds:.2f}s; validando o resultado.",
    )
    assert exit_result.value.code == 0, captured.err or captured.out
    assert json.loads(captured.out) == {"exams": EXPECTED_EXAMS_BY_IMAGE[image_name]}
    _log_progress(capsys, "Código de saída e lista de exames conferem.")
    assert test_model.request_count == 1
    assert test_model.image_id is not None
    assert test_model.user_text == f"image_id: {test_model.image_id}"
    assert set(test_model.available_tool_names) == {
        "appointment_booking",
        "exam_catalog_search",
        "extract_exams",
    }
    assert created_executors[0].model_override is test_model
    assert str(ImageId.parse(test_model.image_id)) == test_model.image_id
    _log_progress(capsys, "Agente ADK chamou extract_exams com um image_id UUID.")
    assert not (image_store.root / test_model.image_id).exists()
    assert _sha256(image_path) == original_digest
    _log_progress(capsys, "Cópia temporária removida; imagem original preservada.")

    output_and_errors = f"{captured.out}\n{captured.err}".upper()
    assert all(marker not in output_and_errors for marker in PATIENT_MARKERS)

    with capsys.disabled():
        print(f"Resultado validado: {captured.out.strip()}", flush=True)
        print(f"E2E concluído em {elapsed_seconds:.2f}s.", flush=True)


def _log_progress(capsys: pytest.CaptureFixture[str], message: str) -> None:
    with capsys.disabled():
        print(f"[e2e] {message}", file=sys.stderr, flush=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
