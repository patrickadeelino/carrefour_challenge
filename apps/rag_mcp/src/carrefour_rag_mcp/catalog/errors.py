"""Stable, content-free catalog loading failures."""

from typing import Literal

CatalogErrorCode = Literal["catalog_invalid", "catalog_unavailable"]


class CatalogLoadError(RuntimeError):
    """Raised when the bundled catalog cannot be loaded safely."""

    def __init__(self, error_code: CatalogErrorCode) -> None:
        super().__init__(error_code)
        self.error_code = error_code
