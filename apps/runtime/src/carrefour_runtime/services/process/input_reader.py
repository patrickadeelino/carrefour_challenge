"""Resolução e leitura segura de imagens fornecidas ao comando process."""

from __future__ import annotations

import os
import stat
from pathlib import Path


class ProcessInputError(ValueError):
    """A imagem de entrada não está disponível na pasta permitida."""

    def __init__(self, message: str, error_code: str = "input_image_invalid") -> None:
        super().__init__(message)
        self.error_code = error_code


def resolve_input_image(filename: str, allowed_directory: Path) -> Path:
    """Resolve apenas nomes simples para arquivos regulares da pasta permitida."""
    if (
        not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or Path(filename).name != filename
    ):
        raise ProcessInputError(
            "informe somente o nome de arquivo da imagem",
            error_code="input_filename_invalid",
        )

    try:
        root = allowed_directory.resolve(strict=True)
        candidate = root / filename
        resolved_candidate = candidate.resolve(strict=True)
        resolved_candidate.relative_to(root)
        if candidate.is_symlink() or not stat.S_ISREG(candidate.stat().st_mode):
            raise ProcessInputError(
                "arquivo de imagem não encontrado ou inacessível",
                error_code="input_image_unavailable",
            )
    except (OSError, RuntimeError, ValueError) as error:
        if isinstance(error, ProcessInputError):
            raise
        raise ProcessInputError(
            "arquivo de imagem não encontrado ou inacessível",
            error_code="input_image_unavailable",
        ) from error

    return candidate


def read_input_image(image_path: Path, max_size_bytes: int) -> bytes:
    """Lê um arquivo regular sem seguir symlinks e limita bytes lidos."""
    if max_size_bytes <= 0:
        raise ValueError("max_size_bytes deve ser positivo")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(image_path, flags)
        with os.fdopen(descriptor, "rb") as image_file:
            if not stat.S_ISREG(os.fstat(image_file.fileno()).st_mode):
                raise ProcessInputError(
                    "arquivo de imagem não encontrado ou inacessível",
                    error_code="input_image_unavailable",
                )
            contents = image_file.read(max_size_bytes + 1)
    except (OSError, ValueError) as error:
        if isinstance(error, ProcessInputError):
            raise
        raise ProcessInputError(
            "arquivo de imagem não encontrado ou inacessível",
            error_code="input_image_unavailable",
        ) from error

    if len(contents) > max_size_bytes:
        raise ProcessInputError(
            "imagem excede o limite de tamanho permitido",
            error_code="input_image_too_large",
        )

    return contents
