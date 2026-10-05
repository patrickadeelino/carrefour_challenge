import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from carrefour_observability.telemetry import (
    configure_telemetry,
    shutdown_telemetry,
)

from .services.generate.service import (
    InvalidAgentSpecification,
    generate_agent_file,
)
from .services.image_storage.temporary_store import ImageStorageError
from .services.process.composition import (
    ProcessConfigurationError,
    create_process_service,
)
from .services.process.errors import ProcessExecutionError
from .services.process.message_formatter import (
    ProcessMessageFormatError,
    format_process_message,
)
from .validation import validate_specification
from .value_objects.process_result import ProcessResult
from .value_objects.user_id import UserId

logger = logging.getLogger(__name__)


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
    process_command = commands.add_parser(
        "process", help="processa uma imagem de pedido de exames"
    )
    process_command.add_argument("--path", required=True, help="nome do arquivo")
    process_command.add_argument(
        "--user", required=True, help="identificador local do usuário"
    )
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


def _run_generation(output_path: Path, specification: Any) -> int:
    try:
        generate_agent_file(specification, output_path)
    except InvalidAgentSpecification as error:
        for message in error.messages:
            print(f"Erro de validação: {message}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"Erro ao gravar {output_path}: {error}", file=sys.stderr)
        return 1

    print(f"Agente gerado: {output_path}")
    return 0


def print_process_result(result: ProcessResult) -> int:
    try:
        message = format_process_message(result)
    except ProcessMessageFormatError:
        logger.error(
            "process.output.failed",
            extra={
                "event_name": "process.output.failed",
                "component": "cli",
                "error_code": "process_result_not_presentable",
                "error_type": "ProcessMessageFormatError",
            },
        )
        print("não foi possível apresentar o resultado com segurança", file=sys.stderr)
        return 1

    print(message)
    return result.exit_code


def _run_processing(filename: str, user_id_value: str) -> int:
    try:
        user_id = UserId(user_id_value)
    except ValueError:
        print("identificador de usuário inválido", file=sys.stderr)
        return 1

    try:
        service = create_process_service(user_id)
    except ProcessConfigurationError as error:
        logger.error(
            "process.configuration_failed",
            extra={
                "event_name": "process.configuration_failed",
                "component": "cli",
                "error_code": error.error_code,
            },
        )
        print(error.public_message, file=sys.stderr)
        return 1
    except ImageStorageError:
        logger.error(
            "process.failed",
            extra={
                "event_name": "process.failed",
                "component": "temporary_image_store",
                "error_code": "image_storage_unavailable",
                "error_type": "ImageStorageError",
            },
        )
        print("não foi possível preparar o armazenamento temporário", file=sys.stderr)
        return 1
    except Exception as error:
        logger.error(
            "process.failed",
            extra={
                "event_name": "process.failed",
                "component": "cli",
                "error_code": "unexpected_runtime_failure",
                "error_type": type(error).__name__,
            },
        )
        print("falha técnica durante o processamento", file=sys.stderr)
        return 1

    try:
        result = asyncio.run(service.process(filename))
    except ProcessExecutionError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception as error:
        logger.error(
            "process.failed",
            extra={
                "event_name": "process.failed",
                "component": "cli",
                "error_code": "unexpected_runtime_failure",
                "error_type": type(error).__name__,
            },
        )
        print("falha técnica durante o processamento", file=sys.stderr)
        return 1

    return print_process_result(result)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "process":
        configure_telemetry("assistant-runtime", "carrefour_runtime")
        try:
            return _run_processing(args.path, args.user)
        finally:
            shutdown_telemetry()

    try:
        specification = _read_specification(args.specification)
    except SpecificationFileError as read_error:
        print(read_error, file=sys.stderr)
        return 1

    if args.command == "validate":
        return _run_validation(args.specification, specification)

    return _run_generation(args.output, specification)
