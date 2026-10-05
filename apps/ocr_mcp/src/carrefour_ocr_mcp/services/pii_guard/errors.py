class InvalidExamResultError(ValueError):
    """Sanitized rejection for extractor results outside the public contract."""

    error_code = "invalid_ocr_result"
    component = "pii_guard"

    def __init__(self) -> None:
        super().__init__("O OCR retornou um resultado fora do contrato permitido.")


class PiiAnalysisError(RuntimeError):
    """Sanitized failure raised when an output could not be checked for PII."""

    error_code = "pii_analysis_failed"
    component = "pii_guard"

    def __init__(self) -> None:
        super().__init__("Não foi possível verificar a privacidade do resultado.")


class PiiConfigurationError(RuntimeError):
    """Sanitized failure raised when the local PII detector cannot start."""

    error_code = "pii_configuration_failed"
    component = "pii_guard"

    def __init__(self) -> None:
        super().__init__("O detector local de privacidade não pôde ser iniciado.")
