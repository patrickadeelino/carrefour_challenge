from __future__ import annotations

import pytest

from carrefour_ocr_mcp.services.pii_guard.presidio_analyzer import (
    PresidioPiiAnalyzer,
)


@pytest.fixture(scope="module")
def pii_analyzer() -> PresidioPiiAnalyzer:
    return PresidioPiiAnalyzer()


@pytest.mark.parametrize(
    "text",
    [
        "Paciente Ana Clara da Silva",
        "CPF 529.982.247-25",
        "CPF 529.982.247-24",
        "CNPJ 11.222.333/0001-81",
        "CNPJ 11.222.333/0001-80",
        "CNPJ 00.000.000/E08G-12",
        "CNPJ 00.000.000/e08g-12",
        "RG 12.345.678-9",
        "CNS 123456789012345",
        "Telefone (41) 99999-0000",
        "Contato ana@example.com",
    ],
)
def test_detects_configured_personal_data_categories(
    pii_analyzer: PresidioPiiAnalyzer,
    text: str,
) -> None:
    assert pii_analyzer.contains_pii(text)


@pytest.mark.parametrize(
    "exam_name",
    [
        "Hemograma completo",
        "Glicemia de jejum",
        "Hemoglobina glicada (HbA1c)",
        "Colesterol total e frações",
        "TSH (hormônio tireoestimulante)",
        "TSH",
        "Colesterol LDL",
        "Vitamina D (25-OH)",
        "Vitamina D, T3 Reverso e PSA Total",
    ],
)
def test_does_not_classify_supported_exam_names_as_pii(
    pii_analyzer: PresidioPiiAnalyzer,
    exam_name: str,
) -> None:
    assert not pii_analyzer.contains_pii(exam_name)


def test_detects_person_name_alongside_known_numeric_exam_term(
    pii_analyzer: PresidioPiiAnalyzer,
) -> None:
    assert pii_analyzer.contains_pii("T3 Reverso e Ana Clara da Silva")
