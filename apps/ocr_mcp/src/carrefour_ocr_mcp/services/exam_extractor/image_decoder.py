from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from carrefour_ocr_mcp.services.exam_extractor.errors import ExamImageError


def decode_image(image_bytes: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            return ImageOps.exif_transpose(source).convert("RGB")
    except (
        Image.DecompressionBombError,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ):
        raise ExamImageError(
            "Não foi possível decodificar a imagem para análise."
        ) from None
