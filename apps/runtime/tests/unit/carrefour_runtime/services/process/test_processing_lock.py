from pathlib import Path

import pytest

from carrefour_runtime.services.process.processing_lock import (
    ProcessingInProgress,
    ProcessingLock,
)


def test_processing_lock_rejects_a_second_active_processing(tmp_path: Path) -> None:
    lock = ProcessingLock(tmp_path / "runtime" / "process.lock")
    competing_lock = ProcessingLock(tmp_path / "runtime" / "process.lock")

    lock.__enter__()
    try:
        with pytest.raises(ProcessingInProgress, match="já existe"):
            competing_lock.__enter__()
    finally:
        lock.__exit__(None, None, None)

    with competing_lock:
        pass
