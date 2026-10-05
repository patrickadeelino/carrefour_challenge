from pathlib import Path
from typing import Any

from pydantic import ValidationError

from carrefour_runtime.services.generate.source_generator import generate_agent_source
from carrefour_runtime.validation import (
    format_validation_errors,
    parse_specification,
)


class InvalidAgentSpecification(ValueError):
    def __init__(self, messages: list[str]) -> None:
        super().__init__("A especificação do agente é inválida")
        self.messages = tuple(messages)


def generate_agent_file(specification_data: Any, output_path: Path) -> None:
    """Valida a especificação e grava o código gerado no caminho solicitado."""
    try:
        specification = parse_specification(specification_data)
    except ValidationError as error:
        raise InvalidAgentSpecification(format_validation_errors(error)) from error

    generated_source = generate_agent_source(specification)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(generated_source, encoding="utf-8", newline="\n")
