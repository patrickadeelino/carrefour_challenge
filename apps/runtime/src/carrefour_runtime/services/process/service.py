"""Orquestra a imagem temporária e a execução do fluxo completo do agente."""

from __future__ import annotations

import logging
from pathlib import Path
from time import monotonic
from typing import Protocol

from opentelemetry import trace

from carrefour_runtime.services.image_storage.temporary_store import ImageStorageError
from carrefour_runtime.services.process.errors import ProcessExecutionError
from carrefour_runtime.services.process.input_reader import (
    ProcessInputError,
    read_input_image,
    resolve_input_image,
)
from carrefour_runtime.services.process.processing_lock import (
    ProcessingInProgress,
    ProcessingLock,
)
from carrefour_runtime.value_objects.image_id import ImageId
from carrefour_runtime.value_objects.process_result import ProcessResult

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class ProcessWorkflowExecutor(Protocol):
    async def execute(self, image_id: ImageId) -> object: ...


class ImageStore(Protocol):
    max_image_size_bytes: int

    def store(self, image_bytes: bytes) -> ImageId: ...

    def delete(self, image_id: ImageId) -> bool: ...


class ProcessService:
    """Executa o fluxo completo por vez e apaga a cópia ao finalizar."""

    def __init__(
        self,
        image_directory: Path,
        image_store: ImageStore,
        executor: ProcessWorkflowExecutor,
        lock_path: Path,
    ) -> None:
        self.image_directory = image_directory
        self.image_store = image_store
        self.executor = executor
        self.lock_path = lock_path

    async def process(self, filename: str) -> ProcessResult:
        with tracer.start_as_current_span(
            "process", record_exception=False, set_status_on_exception=False
        ) as span:
            try:
                result = await self._process(filename)
            except ProcessExecutionError as error:
                span.set_attribute("process.outcome", "failed")
                span.set_attribute("error.code", error.error_code)
                span.set_status(trace.StatusCode.ERROR)
                raise
            span.set_attribute(
                "process.outcome",
                "review_required" if result.requires_review else "success",
            )
            return result

    async def _process(self, filename: str) -> ProcessResult:
        started_at = monotonic()
        logger.info(
            "process.started",
            extra={
                "event_name": "process.started",
                "component": "process_service",
            },
        )
        try:
            with ProcessingLock(self.lock_path):
                result = await self._process_locked(filename)
        except ProcessingInProgress as error:
            logger.warning(
                "process.lock.rejected",
                extra={
                    "event_name": "process.lock.rejected",
                    "component": "processing_lock",
                    "error_code": "process_already_running",
                    "error_type": type(error).__name__,
                },
            )
            failure = ProcessExecutionError(
                str(error),
                error_code="process_already_running",
                component="processing_lock",
                error_type=type(error).__name__,
            )
            self._log_failure(failure, started_at)
            raise failure from error
        except Exception as error:
            failure = _safe_process_error(error)
            self._log_failure(failure, started_at)
            if failure is error:
                raise
            raise failure from error

        log_completion = logger.warning if result.requires_review else logger.info
        log_completion(
            "process.completed",
            extra={
                "event_name": "process.completed",
                "component": "process_service",
                "duration_ms": _duration_ms(started_at),
                "outcome": "review_required" if result.requires_review else "success",
            },
        )
        return result

    async def _process_locked(self, filename: str) -> ProcessResult:
        image_id: ImageId | None = None
        result: ProcessResult | None = None
        failure: ProcessExecutionError | None = None
        cleanup_failure: ImageStorageError | None = None
        try:
            image_started_at = monotonic()
            with tracer.start_as_current_span(
                "process.image.store",
                record_exception=False,
                set_status_on_exception=False,
            ) as span:
                try:
                    image_id = self._store_image(filename)
                except Exception:
                    span.set_attribute("process.image.store.outcome", "failed")
                    span.set_status(trace.StatusCode.ERROR)
                    raise
                span.set_attribute("process.image.store.outcome", "success")
            logger.info(
                "process.image.stored",
                extra={
                    "event_name": "process.image.stored",
                    "component": "temporary_image_store",
                    "duration_ms": _duration_ms(image_started_at),
                },
            )
            workflow_started_at = monotonic()
            logger.info(
                "process.workflow.started",
                extra={
                    "event_name": "process.workflow.started",
                    "component": "workflow_executor",
                },
            )
            with tracer.start_as_current_span(
                "process.workflow.execute",
                record_exception=False,
                set_status_on_exception=False,
            ) as span:
                try:
                    raw_result = await self.executor.execute(image_id)
                except Exception:
                    span.set_attribute("process.workflow.outcome", "failed")
                    span.set_status(trace.StatusCode.ERROR)
                    raise
                span.set_attribute("process.workflow.outcome", "response_received")
            result = self._validate_workflow_result(raw_result)
            log_workflow_completion = (
                logger.warning if result.requires_review else logger.info
            )
            log_workflow_completion(
                "process.workflow.completed",
                extra={
                    "event_name": "process.workflow.completed",
                    "component": "workflow_executor",
                    "duration_ms": _duration_ms(workflow_started_at),
                    "outcome": "review_required"
                    if result.requires_review
                    else "success",
                },
            )
        except Exception as error:
            failure = _safe_process_error(error)
        finally:
            with tracer.start_as_current_span(
                "process.image.cleanup",
                record_exception=False,
                set_status_on_exception=False,
            ) as span:
                cleanup_failure = self.delete_image(image_id)
                span.set_attribute(
                    "process.image.cleanup.outcome",
                    "failed" if cleanup_failure else "completed",
                )
                if cleanup_failure is not None:
                    span.set_status(trace.StatusCode.ERROR)

        self._raise_failures(failure, cleanup_failure)
        if result is None:
            raise ProcessExecutionError(
                "fluxo do agente não retornou um resultado válido",
                error_code="workflow_result_missing",
                component="workflow_executor",
            )
        return result

    def _store_image(self, filename: str) -> ImageId:
        image_path = resolve_input_image(filename, self.image_directory)
        image_bytes = read_input_image(
            image_path, self.image_store.max_image_size_bytes
        )
        return self.image_store.store(image_bytes)

    @staticmethod
    def _validate_workflow_result(value: object) -> ProcessResult:
        if isinstance(value, ProcessResult):
            return value
        raise ProcessExecutionError(
            "fluxo do agente retornou um resultado inválido",
            error_code="workflow_result_invalid",
            component="workflow_executor",
            error_type=type(value).__name__,
        )

    @staticmethod
    def _raise_failures(
        failure: ProcessExecutionError | None,
        cleanup_failure: ImageStorageError | None,
    ) -> None:
        if failure is not None and cleanup_failure is not None:
            combined = ExceptionGroup(
                "Falharam o processamento e a limpeza da imagem temporária",
                [failure, cleanup_failure],
            )
            raise ProcessExecutionError(
                "falha técnica durante o processamento e a limpeza da imagem "
                "temporária",
                error_code="processing_and_cleanup_failed",
                component="temporary_image_store",
                error_type="ExceptionGroup",
            ) from combined
        if failure is not None:
            raise failure
        if cleanup_failure is not None:
            raise ProcessExecutionError(
                "falha técnica ao remover a imagem temporária",
                error_code="temporary_image_delete_failed",
                component="temporary_image_store",
                error_type="ImageStorageError",
            ) from cleanup_failure

    @staticmethod
    def _log_failure(error: ProcessExecutionError, started_at: float) -> None:
        expected_rejection_codes = {
            "process_already_running",
            "input_filename_invalid",
            "input_image_unavailable",
            "input_image_too_large",
        }
        log_failure = (
            logger.warning
            if error.error_code in expected_rejection_codes
            else logger.error
        )
        log_failure(
            "process.failed",
            extra={
                "event_name": "process.failed",
                "component": error.component,
                "duration_ms": _duration_ms(started_at),
                "error_code": error.error_code,
                "error_type": error.error_type or type(error).__name__,
            },
        )

    def delete_image(self, image_id: ImageId | None) -> ImageStorageError | None:
        """Remove a imagem criada pelo atendimento, sem lógica no bloco finally."""
        if image_id is None:
            return None
        try:
            deleted = self.image_store.delete(image_id)
        except ImageStorageError as error:
            logger.error(
                "process.image_cleanup.failed",
                extra={
                    "event_name": "process.image_cleanup.failed",
                    "component": "temporary_image_store",
                    "error_code": "temporary_image_delete_failed",
                    "error_type": type(error).__name__,
                },
            )
            return error

        logger.info(
            "process.image_cleanup.completed",
            extra={
                "event_name": "process.image_cleanup.completed",
                "component": "temporary_image_store",
                "outcome": "deleted" if deleted else "already_absent",
            },
        )
        return None


def _safe_process_error(error: Exception) -> ProcessExecutionError:
    if isinstance(error, ProcessExecutionError):
        return error
    if isinstance(error, ProcessInputError):
        return ProcessExecutionError(
            str(error),
            error_code=error.error_code,
            component="input_reader",
            error_type=type(error).__name__,
        )
    if isinstance(error, ImageStorageError):
        return ProcessExecutionError(
            str(error),
            error_code="image_storage_failed",
            component="temporary_image_store",
            error_type=type(error).__name__,
        )
    return ProcessExecutionError(
        "falha técnica durante o processamento",
        error_code="workflow_execution_failed",
        component="workflow_executor",
        error_type=type(error).__name__,
    )


def _duration_ms(started_at: float) -> int:
    return round((monotonic() - started_at) * 1000)
