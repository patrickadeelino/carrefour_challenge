"""Armazenamento temporário de imagens para o fluxo de atendimento."""

from __future__ import annotations

import os
import stat
import tempfile
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from carrefour_runtime.value_objects.image_id import ImageId


class ImageStorageError(ValueError):
    """Imagem não suportada ou operação de armazenamento inválida."""


class TemporaryImageStore:
    """Armazena PNG/JPG temporariamente e resolve arquivos por UUID interno."""

    DEFAULT_ROOT = Path("/var/run/carrefour/images")
    DEFAULT_MAX_IMAGE_SIZE_BYTES = 10_000_000
    DEFAULT_ORPHAN_TTL = timedelta(minutes=30)
    _SUPPORTED_FORMATS = frozenset({"PNG", "JPEG"})

    def __init__(
        self,
        root: Path | None = None,
        max_image_size_bytes: int = DEFAULT_MAX_IMAGE_SIZE_BYTES,
        orphan_ttl: timedelta = DEFAULT_ORPHAN_TTL,
    ) -> None:
        if max_image_size_bytes <= 0:
            raise ValueError("max_image_size_bytes deve ser positivo")
        if orphan_ttl <= timedelta(0):
            raise ValueError("orphan_ttl deve ser positivo")

        configured_root = os.environ.get("CARREFOUR_IMAGE_STORAGE_PATH")
        self.root = (
            root
            if root is not None
            else Path(configured_root or str(self.DEFAULT_ROOT))
        )
        self.max_image_size_bytes = max_image_size_bytes
        self.orphan_ttl = orphan_ttl
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ImageStorageError(
                "não foi possível preparar o armazenamento"
            ) from error

    def store(self, image_bytes: bytes) -> ImageId:
        """Valida e grava os bytes sob um UUID, promovendo o arquivo atomicamente."""
        self._validate_image(image_bytes)
        self.cleanup_orphans()
        image_id = ImageId.new()
        destination = self.root / str(image_id)
        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".upload-", dir=self.root, delete=False
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(image_bytes)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, destination)
        except OSError as error:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.unlink(missing_ok=True)
            raise ImageStorageError("não foi possível armazenar imagem") from error

        return image_id

    def resolve(self, image_id: ImageId) -> Path:
        """Resolve um UUID canônico para um arquivo existente no diretório permitido."""
        image_path = self._path_for(image_id)
        if not image_path.is_file() or image_path.is_symlink():
            raise ImageStorageError("imagem não encontrada")
        return image_path

    def delete(self, image_id: ImageId) -> bool:
        """Apaga uma imagem pelo UUID; retorna False se ela já não existir."""
        image_path = self._path_for(image_id)
        try:
            image_path.unlink()
        except FileNotFoundError:
            return False
        except OSError as error:
            raise ImageStorageError("não foi possível remover imagem") from error
        return True

    def cleanup_orphans(self, now: datetime | None = None) -> int:
        """Remove imagens UUID expiradas e arquivos regulares do armazenamento."""
        current_time = now or datetime.now(UTC)
        if current_time.tzinfo is None:
            raise ValueError("now deve conter fuso horário")
        expiration_timestamp = (
            current_time.timestamp() - self.orphan_ttl.total_seconds()
        )

        try:
            candidates = tuple(self.root.iterdir())
        except OSError as error:
            raise ImageStorageError(
                "não foi possível listar o armazenamento"
            ) from error

        return sum(
            self._remove_if_expired(candidate, expiration_timestamp)
            for candidate in candidates
        )

    def _remove_if_expired(self, candidate: Path, expiration_timestamp: float) -> int:
        if candidate.is_symlink() or not _is_canonical_uuid(candidate.name):
            return 0

        try:
            candidate_stat = candidate.stat(follow_symlinks=False)
            if not stat.S_ISREG(candidate_stat.st_mode):
                return 0
            if candidate_stat.st_mtime >= expiration_timestamp:
                return 0
            candidate.unlink()
        except FileNotFoundError:
            return 0
        except OSError as error:
            raise ImageStorageError("não foi possível limpar imagem órfã") from error

        return 1

    def _validate_image(self, image_bytes: bytes) -> None:
        if not image_bytes:
            raise ImageStorageError("imagem vazia")
        if len(image_bytes) > self.max_image_size_bytes:
            raise ImageStorageError("imagem excede o limite de tamanho de 10 MB")

        try:
            with Image.open(BytesIO(image_bytes)) as image:
                image_format = image.format
                image.verify()
        except (Image.DecompressionBombError, OSError, UnidentifiedImageError) as error:
            raise ImageStorageError("imagem inválida ou corrompida") from error

        if image_format not in self._SUPPORTED_FORMATS:
            raise ImageStorageError("formato não suportado; use PNG e JPG")

    def _path_for(self, image_id: ImageId) -> Path:
        return self.root / str(image_id)


def _is_canonical_uuid(value: str) -> bool:
    try:
        ImageId.parse(value)
    except ValueError:
        return False
    return True
