"""Orquestra o armazenamento temporário e a chamada da tool de OCR."""

from __future__ import annotations

import logging
from pathlib import Path
from time import monotonic
from typing import Protocol

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
from carrefour_runtime.value_objects.exam_result import ExamResult
from carrefour_runtime.value_objects.image_id import ImageId

logger = logging.getLogger(__name__)


class OCRExecutor(Protocol):
    async def extract_exams(self, image_id: ImageId) -> object: ...


class ImageStore(Protocol):
    max_image_size_bytes: int

    def store(self, image_bytes: bytes) -> ImageId: ...

    def delete(self, image_id: ImageId) -> bool: ...


class ProcessService:
    """Executa um pedido por vez e apaga a cópia temporária ao finalizar."""

    def __init__(
        self,
        image_directory: Path,
        image_store: ImageStore,
        executor: OCRExecutor,
        lock_path: Path,
    ) -> None:
        self.image_directory = image_directory
        self.image_store = image_store
        self.executor = executor
        self.lock_path = lock_path

    async def process(self, filename: str) -> ExamResult:
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

    async def _process_locked(self, filename: str) -> ExamResult:
        image_id: ImageId | None = None
        result: ExamResult | None = None
        failure: ProcessExecutionError | None = None
        cleanup_failure: ImageStorageError | None = None
        try:
            image_started_at = monotonic()
            image_id = self._store_image(filename)
            logger.info(
                "process.image.stored",
                extra={
                    "event_name": "process.image.stored",
                    "component": "temporary_image_store",
                    "duration_ms": _duration_ms(image_started_at),
                },
            )
            ocr_started_at = monotonic()
            logger.info(
                "process.ocr.started",
                extra={
                    "event_name": "process.ocr.started",
                    "component": "ocr_executor",
                },
            )
            raw_result = await self.executor.extract_exams(image_id)
            result = self._validate_result(raw_result)
            log_ocr_completion = (
                logger.warning if result.requires_review else logger.info
            )
            log_ocr_completion(
                "process.ocr.completed",
                extra={
                    "event_name": "process.ocr.completed",
                    "component": "ocr_executor",
                    "duration_ms": _duration_ms(ocr_started_at),
                    "outcome": "review_required"
                    if result.requires_review
                    else "success",
                },
            )
        except Exception as error:
            failure = _safe_process_error(error)
        finally:
            cleanup_failure = self.delete_image(image_id)

        self._raise_failures(failure, cleanup_failure)
        if result is None:
            raise ProcessExecutionError(
                "OCR não retornou um resultado estruturado válido",
                error_code="ocr_result_invalid",
                component="ocr_result",
                error_type="InvalidExamResult",
            )
        return result

    def _store_image(self, filename: str) -> ImageId:
        image_path = resolve_input_image(filename, self.image_directory)
        image_bytes = read_input_image(
            image_path, self.image_store.max_image_size_bytes
        )
        return self.image_store.store(image_bytes)

    @staticmethod
    def _validate_result(value: object) -> ExamResult:
        try:
            return ExamResult.from_mapping(value)
        except ValueError as error:
            raise ProcessExecutionError(
                "OCR não retornou um resultado estruturado válido",
                error_code="ocr_result_invalid",
                component="ocr_result",
                error_type=type(error).__name__,
            ) from error

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
        error_code="ocr_execution_failed",
        component="ocr_executor",
        error_type=type(error).__name__,
    )


def _duration_ms(started_at: float) -> int:
    return round((monotonic() - started_at) * 1000)
