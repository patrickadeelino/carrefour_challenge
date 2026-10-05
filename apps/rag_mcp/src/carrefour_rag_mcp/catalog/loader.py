"""Load and validate the packaged catalog at application startup."""

from importlib.resources import files

from pydantic import ValidationError

from carrefour_rag_mcp.catalog.errors import CatalogLoadError
from carrefour_rag_mcp.catalog.models import CatalogDocument

MINIMUM_BUNDLED_EXAMS = 100


class CatalogLoader:
    """Reads the catalog as package data and exposes only safe failures."""

    @staticmethod
    def load_bundled() -> CatalogDocument:
        try:
            catalog_json = (
                files("carrefour_rag_mcp")
                .joinpath("data", "exams.json")
                .read_text(encoding="utf-8")
            )
        except (ModuleNotFoundError, OSError):
            raise CatalogLoadError("catalog_unavailable") from None
        catalog = CatalogLoader.from_json(catalog_json)
        if len(catalog.exams) < MINIMUM_BUNDLED_EXAMS:
            raise CatalogLoadError("catalog_invalid")
        return catalog

    @staticmethod
    def from_json(catalog_json: str) -> CatalogDocument:
        try:
            return CatalogDocument.model_validate_json(catalog_json)
        except ValidationError:
            raise CatalogLoadError("catalog_invalid") from None
