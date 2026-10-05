class ProcessExecutionError(RuntimeError):
    """Falha segura e apresentável durante o fluxo de atendimento."""

    def __init__(
        self,
        message: str,
        error_code: str = "processing_failed",
        component: str = "process_service",
        error_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.component = component
        self.error_type = error_type
