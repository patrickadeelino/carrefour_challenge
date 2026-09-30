from typing import Any

from pydantic import ValidationError

from .specification import Specification


def _format_error_location(location: tuple[str | int, ...]) -> str:
    if not location:
        return "$"
    path = ".".join(str(part) for part in location)
    return f"$.{path}" if location[0] != "agent" else path


def parse_specification(specification: Any) -> Specification:
    return Specification.model_validate(specification)


def format_validation_errors(error: ValidationError) -> list[str]:
    return [
        f"{_format_error_location(detail['loc'])}: {detail['msg']}"
        for detail in error.errors(include_input=False)
    ]


def validate_specification(specification: Any) -> list[str]:
    """Retorna erros de validação da especificação sem propagar exceções do Pydantic."""
    try:
        parse_specification(specification)
    except ValidationError as error:
        return format_validation_errors(error)
    return []
