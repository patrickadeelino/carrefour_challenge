from pathlib import Path

import pytest

from carrefour_runtime.services.process.input_reader import (
    ProcessInputError,
    resolve_input_image,
)


def test_resolve_input_image_accepts_only_a_file_name_in_the_allowed_directory(
    tmp_path: Path,
) -> None:
    images = tmp_path / "images"
    images.mkdir()
    image = images / "request.png"
    image.write_bytes(b"image")

    assert resolve_input_image("request.png", images) == image


@pytest.mark.parametrize(
    "filename",
    ["../secret.png", "/tmp/secret.png", "nested/request.png", r"nested\request.png"],
)
def test_resolve_input_image_rejects_paths_outside_the_allowed_directory(
    tmp_path: Path, filename: str
) -> None:
    images = tmp_path / "images"
    images.mkdir()

    with pytest.raises(ProcessInputError, match="nome de arquivo"):
        resolve_input_image(filename, images)


def test_resolve_input_image_rejects_missing_files_and_symlinks(tmp_path: Path) -> None:
    images = tmp_path / "images"
    images.mkdir()
    outside_image = tmp_path / "outside.png"
    outside_image.write_bytes(b"image")
    (images / "linked.png").symlink_to(outside_image)

    with pytest.raises(ProcessInputError, match="não encontrado"):
        resolve_input_image("missing.png", images)
    with pytest.raises(ProcessInputError, match="não encontrado"):
        resolve_input_image("linked.png", images)
