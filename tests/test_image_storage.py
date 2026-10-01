import os
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from carrefour_transpiler.image_storage import ImageStorageError, TemporaryImageStore
from PIL import Image


def image_bytes(image_format: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(output, format=image_format)
    return output.getvalue()


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
def test_store_accepts_supported_images_and_uses_uuid_filename(tmp_path, image_format):
    content = image_bytes(image_format)
    store = TemporaryImageStore(tmp_path)

    image_id = store.store(content)

    assert str(UUID(image_id)) == image_id
    stored_file = tmp_path / image_id
    assert stored_file.read_bytes() == content
    with Image.open(stored_file) as stored_image:
        assert stored_image.format == image_format


def test_store_rejects_empty_or_invalid_image_without_leaving_files(tmp_path):
    store = TemporaryImageStore(tmp_path)

    with pytest.raises(ImageStorageError, match="imagem vazia"):
        store.store(b"")
    with pytest.raises(ImageStorageError, match="imagem inválida"):
        store.store(b"not an image")

    assert list(tmp_path.iterdir()) == []


def test_store_rejects_unsupported_image_format(tmp_path):
    store = TemporaryImageStore(tmp_path)

    with pytest.raises(ImageStorageError, match="PNG e JPG"):
        store.store(image_bytes("GIF"))

    assert list(tmp_path.iterdir()) == []


def test_store_rejects_images_over_configured_size_limit(tmp_path):
    content = image_bytes("PNG")
    store = TemporaryImageStore(tmp_path, max_image_size_bytes=len(content) - 1)

    with pytest.raises(ImageStorageError, match="limite de tamanho"):
        store.store(content)

    assert list(tmp_path.iterdir()) == []


def test_default_image_size_limit_is_10_megabytes(tmp_path):
    store = TemporaryImageStore(tmp_path)

    assert store.max_image_size_bytes == 10_000_000


def test_failed_atomic_promotion_does_not_leave_partial_artifacts(
    tmp_path, monkeypatch
):
    store = TemporaryImageStore(tmp_path)

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated filesystem failure")

    monkeypatch.setattr("carrefour_transpiler.image_storage.os.replace", fail_replace)

    with pytest.raises(ImageStorageError, match="armazenar imagem"):
        store.store(image_bytes("PNG"))

    assert list(tmp_path.iterdir()) == []


def test_resolve_returns_only_the_file_referenced_by_a_valid_uuid(tmp_path):
    content = image_bytes("PNG")
    store = TemporaryImageStore(tmp_path)
    image_id = store.store(content)

    assert store.resolve(image_id) == tmp_path / image_id
    assert store.resolve(image_id).read_bytes() == content


def test_delete_removes_an_image_by_its_internal_id(tmp_path):
    store = TemporaryImageStore(tmp_path)
    image_id = store.store(image_bytes("PNG"))

    assert store.delete(image_id) is True
    assert store.delete(image_id) is False
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("invalid_id", ["../../outside", "not-a-uuid"])
def test_storage_rejects_non_uuid_ids(tmp_path, invalid_id):
    store = TemporaryImageStore(tmp_path)

    with pytest.raises(ImageStorageError, match="image_id inválido"):
        store.resolve(invalid_id)
    with pytest.raises(ImageStorageError, match="image_id inválido"):
        store.delete(invalid_id)

    assert list(tmp_path.iterdir()) == []


def test_cleanup_removes_only_uuid_images_older_than_30_minutes(tmp_path):
    store = TemporaryImageStore(tmp_path)
    old_id = store.store(image_bytes("PNG"))
    recent_id = store.store(image_bytes("JPEG"))
    unrelated_file = tmp_path / "keep.txt"
    unrelated_file.write_text("keep", encoding="utf-8")
    now = datetime.now(UTC)
    old_time = (now - timedelta(minutes=31)).timestamp()
    recent_time = (now - timedelta(minutes=29)).timestamp()
    os.utime(tmp_path / old_id, (old_time, old_time))
    os.utime(tmp_path / recent_id, (recent_time, recent_time))

    removed_count = store.cleanup_orphans(now=now)

    assert removed_count == 1
    assert not (tmp_path / old_id).exists()
    assert (tmp_path / recent_id).exists()
    assert unrelated_file.read_text(encoding="utf-8") == "keep"


def test_cleanup_rejects_naive_datetime(tmp_path):
    store = TemporaryImageStore(tmp_path)

    with pytest.raises(ValueError, match="fuso horário"):
        store.cleanup_orphans(now=datetime.now())


def test_new_store_cleans_expired_orphans_before_saving(tmp_path):
    image_id = "2d9e3044-1313-49df-81cc-8b18e3a0ad67"
    expired_file = tmp_path / image_id
    expired_file.write_bytes(image_bytes("PNG"))
    old_time = (datetime.now(UTC) - timedelta(minutes=31)).timestamp()
    os.utime(expired_file, (old_time, old_time))
    store = TemporaryImageStore(tmp_path)

    stored_id = store.store(image_bytes("JPEG"))

    assert not expired_file.exists()
    assert (tmp_path / stored_id).is_file()
