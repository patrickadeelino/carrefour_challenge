"""Lock entre processos para serializar atendimentos no container runtime."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from types import TracebackType
from typing import Self


class ProcessingInProgress(RuntimeError):
    """Já existe outro atendimento em execução neste runtime."""


class ProcessingLock:
    """Adquire um lock exclusivo não bloqueante em arquivo estável."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._descriptor: int | None = None

    def __enter__(self) -> Self:
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(
                self.lock_path,
                os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0),
                0o600,
            )
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                os.close(descriptor)
                raise ProcessingInProgress(
                    "já existe um processamento em andamento"
                ) from error
        except OSError as error:
            raise ProcessingInProgress(
                "não foi possível iniciar o processamento"
            ) from error

        self._descriptor = descriptor
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        if self._descriptor is None:
            return

        descriptor = self._descriptor
        self._descriptor = None
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
