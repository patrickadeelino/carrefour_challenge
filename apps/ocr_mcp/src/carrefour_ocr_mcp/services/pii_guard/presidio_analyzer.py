from __future__ import annotations

from presidio_analyzer import (
    AnalyzerEngine,
    PatternRecognizer,
    RecognizerRegistry,
    RecognizerResult,
)
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.pattern import Pattern
from presidio_analyzer.predefined_recognizers import EmailRecognizer, PhoneRecognizer

_LANGUAGE = "pt"
_MINIMUM_SCORE = 0.35
# spaCy classifies this supported exam name as a person in the reference form.
_KNOWN_MEDICAL_PERSON_FALSE_POSITIVES = {"t3 reverso"}
_PII_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "BR_CPF",
    "BR_CNPJ",
    "BR_RG",
    "BR_CNS",
]


class PresidioPiiAnalyzer:
    """Detect configured Brazilian PII categories with a local Presidio engine."""

    def __init__(self) -> None:
        self._engine = _create_analyzer_engine()

    def contains_pii(self, text: str) -> bool:
        matches = self._engine.analyze(
            text=text,
            language=_LANGUAGE,
            entities=_PII_ENTITIES,
            score_threshold=_MINIMUM_SCORE,
        )
        return any(_is_personal_match(text, match) for match in matches)


def _is_personal_match(text: str, match: RecognizerResult) -> bool:
    if match.entity_type != "PERSON":
        return True

    recognized_text = text[match.start : match.end]
    return recognized_text.casefold() not in _KNOWN_MEDICAL_PERSON_FALSE_POSITIVES


def _create_analyzer_engine() -> AnalyzerEngine:
    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": _LANGUAGE, "model_name": "pt_core_news_sm"}],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=configuration).create_engine()
    registry = RecognizerRegistry(supported_languages=[_LANGUAGE])
    registry.load_predefined_recognizers(
        nlp_engine=nlp_engine,
        languages=[_LANGUAGE],
    )
    registry.add_recognizer(EmailRecognizer(supported_language=_LANGUAGE))
    registry.add_recognizer(
        PhoneRecognizer(
            supported_language=_LANGUAGE,
            supported_regions=["BR"],
        )
    )
    registry.add_recognizer(_BrazilianCpfRecognizer())
    registry.add_recognizer(_BrazilianCnpjRecognizer())
    registry.add_recognizer(_BrazilianRgRecognizer())
    registry.add_recognizer(_BrazilianCnsRecognizer())
    return AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=[_LANGUAGE],
        log_decision_process=False,
    )


class _BrazilianCpfRecognizer(PatternRecognizer):
    """Match the identifier shape even if OCR damages its check digits."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity="BR_CPF",
            supported_language=_LANGUAGE,
            patterns=[
                Pattern(
                    name="Brazilian CPF",
                    regex=r"\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}\b",
                    score=0.85,
                )
            ],
            context=["cpf"],
        )


class _BrazilianCnpjRecognizer(PatternRecognizer):
    """Match numeric or alphanumeric CNPJ shape without relying on its checksum."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity="BR_CNPJ",
            supported_language=_LANGUAGE,
            patterns=[
                Pattern(
                    name="Brazilian CNPJ",
                    regex=(
                        r"\b[A-Za-z0-9]{2}[.\s]?[A-Za-z0-9]{3}"
                        r"[.\s]?[A-Za-z0-9]{3}\s*/?\s*[A-Za-z0-9]{4}"
                        r"\s*-?\s*\d{2}\b"
                    ),
                    score=0.85,
                )
            ],
            context=["cnpj"],
        )


class _BrazilianRgRecognizer(PatternRecognizer):
    def __init__(self) -> None:
        super().__init__(
            supported_entity="BR_RG",
            supported_language=_LANGUAGE,
            patterns=[
                Pattern(
                    name="Brazilian RG",
                    regex=r"\b\d{1,2}[.]?\d{3}[.]?\d{3}[-]?[\dX]\b",
                    score=0.85,
                )
            ],
            context=["rg", "registro geral", "identidade"],
        )


class _BrazilianCnsRecognizer(PatternRecognizer):
    def __init__(self) -> None:
        super().__init__(
            supported_entity="BR_CNS",
            supported_language=_LANGUAGE,
            patterns=[
                Pattern(
                    name="Brazilian CNS",
                    regex=r"\b\d{15}\b",
                    score=0.85,
                )
            ],
            context=["cns", "cartão nacional de saúde", "cartao sus"],
        )
