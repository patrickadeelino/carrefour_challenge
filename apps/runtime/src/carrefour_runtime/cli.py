import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .generation import generate_agent_source
from .validation import (
    format_validation_errors,
    parse_specification,
    validate_specification,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="carrefour-runtime")
    commands = parser.add_subparsers(dest="command", required=True)
    validate_command = commands.add_parser(
        "validate", help="valida um arquivo de especificação JSON"
    )
    validate_command.add_argument("specification", type=Path)
    generate_command = commands.add_parser(
        "generate", help="gera o código Python do agente"
    )
    generate_command.add_argument("specification", type=Path)
    generate_command.add_argument("--output", type=Path, required=True)
    return parser


class SpecificationFileError(Exception):
    """Erro ao ler ou decodificar o arquivo JSON da especificação."""


def _read_specification(path: Path) -> Any:
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SpecificationFileError(f"Erro ao ler {path}: {error}") from error

    try:
        return json.loads(contents)
    except json.JSONDecodeError as error:
        raise SpecificationFileError(
            f"JSON inválido em {path}:{error.lineno}:{error.colno}: {error.msg}"
        ) from error


def _run_validation(specification_path: Path, specification: Any) -> int:
    errors = validate_specification(specification)
    if errors:
        for message in errors:
            print(f"Erro de validação: {message}", file=sys.stderr)
        return 1

    print(f"Especificação válida: {specification_path}")
    return 0


def _run_generation(
    specification_path: Path, output_path: Path, specification: Any
) -> int:
    try:
        validated_specification = parse_specification(specification)
    except ValidationError as error:
        for message in format_validation_errors(error):
            print(f"Erro de validação: {message}", file=sys.stderr)
        return 1

    generated_source = generate_agent_source(validated_specification)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(generated_source, encoding="utf-8", newline="\n")
    except OSError as error:
        print(f"Erro ao gravar {output_path}: {error}", file=sys.stderr)
        return 1

    print(f"Agente gerado: {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    try:
        specification = _read_specification(args.specification)
    except SpecificationFileError as read_error:
        print(read_error, file=sys.stderr)
        return 1

    if args.command == "validate":
        return _run_validation(args.specification, specification)

    return _run_generation(args.specification, args.output, specification)
