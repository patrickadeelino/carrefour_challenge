from pathlib import Path
from uuid import uuid4

import pytest

from carrefour_ocr_mcp.image_access import ImageAccessError, read_image


def test_read_image_rejects_symlink_without_disclosing_target(tmp_path: Path) -> None:
    image_directory = tmp_path / "images"
    image_directory.mkdir()
    outside_image = tmp_path / "private-image.png"
    outside_image.write_bytes(b"private patient image")
    image_id = str(uuid4())
    (image_directory / image_id).symlink_to(outside_image)

    with pytest.raises(ImageAccessError, match="Imagem indisponível") as error:
        read_image(image_directory, image_id)

    assert str(outside_image) not in str(error.value)
    assert "private patient image" not in str(error.value)


def test_read_image_rejects_resolved_path_outside_image_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_directory = tmp_path / "images"
    image_directory.mkdir()
    image_id = str(uuid4())
    image_path = image_directory / image_id
    image_path.write_bytes(b"image")
    outside_path = tmp_path / "outside" / image_id
    original_resolve = Path.resolve

    def resolve_with_outside_target(path: Path, strict: bool = False) -> Path:
        if path == image_path:
            return outside_path
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve_with_outside_target)

    with pytest.raises(ImageAccessError, match="Imagem indisponível"):
        read_image(image_directory, image_id)


def test_read_image_sanitizes_filesystem_read_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_directory = tmp_path / "images"
    image_directory.mkdir()
    image_id = str(uuid4())
    (image_directory / image_id).write_bytes(b"image")

    def fail_read(path: Path) -> bytes:
        raise PermissionError(f"private filesystem location: {path}")

    monkeypatch.setattr(Path, "read_bytes", fail_read)

    with pytest.raises(
        ImageAccessError, match="Não foi possível acessar a imagem"
    ) as error:
        read_image(image_directory, image_id)

    assert "private filesystem location" not in str(error.value)
