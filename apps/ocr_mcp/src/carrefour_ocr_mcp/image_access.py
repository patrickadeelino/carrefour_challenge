from pathlib import Path

from mcp.server.mcpserver.exceptions import ToolError

from carrefour_ocr_mcp.value_objects.image_id import ImageId


class ImageAccessError(ToolError):
    """Sanitized tool error with a stable operational classification."""

    component = "image_access"

    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def read_image(image_directory: Path, image_id: str) -> bytes:
    try:
        parsed_id = ImageId.parse(image_id)
    except ValueError:
        raise ImageAccessError(
            "image_id deve ser um UUID válido.", "invalid_image_id"
        ) from None

    image_path = image_directory / str(parsed_id)
    if image_path.is_symlink():
        raise ImageAccessError("Imagem indisponível.", "image_unavailable")

    try:
        resolved_directory = image_directory.resolve(strict=True)
        resolved_image_path = image_path.resolve(strict=True)
        if resolved_image_path.parent != resolved_directory:
            raise ImageAccessError("Imagem indisponível.", "image_unavailable")
        return resolved_image_path.read_bytes()
    except FileNotFoundError:
        raise ImageAccessError("Imagem não encontrada.", "image_not_found") from None
    except OSError:
        raise ImageAccessError(
            "Não foi possível acessar a imagem.", "image_access_failed"
        ) from None
