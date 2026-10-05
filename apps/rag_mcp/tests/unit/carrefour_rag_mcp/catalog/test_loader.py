import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from carrefour_rag_mcp.catalog import CatalogLoader, CatalogLoadError


def test_bundled_catalog_loads_at_least_one_hundred_unique_exams() -> None:
    catalog = CatalogLoader.load_bundled()

    assert len(catalog.exams) >= 100
    assert len({exam.code for exam in catalog.exams}) == len(catalog.exams)


def test_bundled_catalog_contains_names_from_both_ocr_fixtures() -> None:
    catalog = CatalogLoader.load_bundled()
    names_and_aliases = {
        label for exam in catalog.exams for label in (exam.name, *exam.aliases)
    }

    assert "Hemograma completo" in names_and_aliases
    assert "Glicemia de jejum" in names_and_aliases
    assert "Hemoglobina glicada (HbA1c)" in names_and_aliases
    assert "Colesterol total e frações" in names_and_aliases
    assert "TSH (hormônio tireoestimulante)" in names_and_aliases
    assert "Creatinina" in names_and_aliases
    assert "CPK (Creatina quinase)" in names_and_aliases
    assert "Anticorpo anti-receptor de TSH" in names_and_aliases
    assert "Potássio" in names_and_aliases
    assert "Prolactina" in names_and_aliases
    assert "Colesterol HDL" in names_and_aliases
    assert "Colesterol LDL" in names_and_aliases
    assert "Vitamina D (25-OH)" in names_and_aliases


def test_catalog_allows_same_alias_for_multiple_exams(
    catalog_document_factory: Callable[..., str],
) -> None:
    exams = [
        {"code": f"CAT-{index:03d}", "name": f"Exame {index}", "aliases": []}
        for index in range(1, 101)
    ]
    exams[0]["aliases"] = ["Alias compartilhado"]
    exams[1]["aliases"] = ["Alias compartilhado"]

    loaded = CatalogLoader.from_json(catalog_document_factory(exams))

    assert loaded.exams[0].aliases == ("Alias compartilhado",)
    assert loaded.exams[1].aliases == ("Alias compartilhado",)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda exam: exam.pop("name"),
        lambda exam: exam.update(unknown="field"),
        lambda exam: exam.update(aliases=[""]),
        lambda exam: exam.update(aliases=["Repetido", "Repetido"]),
        lambda exam: exam.update(aliases=[exam["name"]]),
    ],
)
def test_catalog_rejects_invalid_exam_fields(
    catalog_document_factory: Callable[..., str],
    mutate: Callable[[dict[str, Any]], object],
) -> None:
    document = json.loads(catalog_document_factory())
    mutate(document["exams"][0])

    with pytest.raises(CatalogLoadError) as error:
        CatalogLoader.from_json(json.dumps(document))

    assert error.value.error_code == "catalog_invalid"


def test_catalog_rejects_duplicate_codes(
    catalog_document_factory: Callable[..., str],
) -> None:
    document = json.loads(catalog_document_factory())
    document["exams"][1]["code"] = document["exams"][0]["code"]

    with pytest.raises(CatalogLoadError, match="catalog_invalid"):
        CatalogLoader.from_json(json.dumps(document))


def test_catalog_rejects_duplicate_canonical_names(
    catalog_document_factory: Callable[..., str],
) -> None:
    document = json.loads(catalog_document_factory())
    document["exams"][1]["name"] = document["exams"][0]["name"].upper()

    with pytest.raises(CatalogLoadError, match="catalog_invalid"):
        CatalogLoader.from_json(json.dumps(document))


def test_catalog_structure_accepts_small_synthetic_fixture(
    catalog_document_factory: Callable[..., str],
) -> None:
    catalog = CatalogLoader.from_json(catalog_document_factory(count=2))

    assert len(catalog.exams) == 2


def test_bundled_catalog_rejects_fewer_than_one_hundred_exams(
    catalog_document_factory: Callable[..., str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog_json = catalog_document_factory(count=99)
    resource = SimpleNamespace(read_text=lambda encoding: catalog_json)
    package_data = SimpleNamespace(joinpath=lambda *_parts: resource)
    monkeypatch.setattr(
        "carrefour_rag_mcp.catalog.loader.files",
        lambda _package: package_data,
    )

    with pytest.raises(CatalogLoadError, match="catalog_invalid"):
        CatalogLoader.load_bundled()


def test_invalid_json_returns_sanitized_error() -> None:
    with pytest.raises(CatalogLoadError, match="catalog_invalid") as error:
        CatalogLoader.from_json('{"exams": [{"name": "CPF-123"}')

    assert "CPF-123" not in str(error.value)
