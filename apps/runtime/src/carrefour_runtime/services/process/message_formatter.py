"""Human-readable, privacy-conscious messages for terminal process results."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from carrefour_runtime.services.process.schedule_api_client import (
    ScheduleApiResponse,
)
from carrefour_runtime.value_objects.process_result import ProcessResult

DISPLAY_TIMEZONE = ZoneInfo("America/Sao_Paulo")
REVIEW_MESSAGE = (
    "Não foi possível confirmar os exames automaticamente. "
    "Revise o pedido antes de continuar."
)
NO_EXAMS_MESSAGE = "Não identifiquei exames para processar nesta imagem."


class _AppointmentGroup(Protocol):
    scheduled_at: datetime
    exam_codes: list[str]


class ProcessMessageFormatError(ValueError):
    """A terminal result cannot be presented without exposing internal data."""


def format_process_message(result: ProcessResult) -> str:
    """Render a terminal workflow result without IDs or catalog codes."""
    if result.requires_review:
        return REVIEW_MESSAGE

    if result.schedule_response is not None:
        return _format_schedule_response(
            result.schedule_response,
            result.canonical_names_by_code,
        )

    if result.to_dict() == {"exams": []}:
        return NO_EXAMS_MESSAGE

    raise ProcessMessageFormatError("resultado final de processamento ausente")


def _format_schedule_response(
    response: ScheduleApiResponse,
    canonical_names_by_code: dict[str, str],
) -> str:
    already = _format_appointment_groups(
        response.already_scheduled,
        canonical_names_by_code,
    )
    newly = _format_appointment_groups(
        response.newly_scheduled,
        canonical_names_by_code,
    )
    unavailable = _format_unavailable_exams(response, canonical_names_by_code)

    if unavailable and (already or newly):
        sections = ["Agendamento parcial."]
        _append_section(sections, "Já estavam agendados", already)
        _append_section(sections, "Novos agendamentos", newly)
        sections.append("Sem disponibilidade de horário:\n" + unavailable)
        return "\n\n".join(sections)

    if unavailable:
        return "Não foi possível encontrar horários disponíveis para:\n" + unavailable

    if already and newly:
        sections = ["Agendamento atualizado."]
        _append_section(sections, "Já estavam agendados", already)
        _append_section(sections, "Novos agendamentos", newly)
        return "\n\n".join(sections)

    if newly:
        return "Novos agendamentos confirmados:\n" + newly

    if already:
        return "Estes exames já estavam agendados:\n" + already

    return "Não há agendamentos pendentes para estes exames."


def _format_appointment_groups(
    groups: Sequence[_AppointmentGroup],
    canonical_names_by_code: dict[str, str],
) -> str:
    lines: list[str] = []
    for group in groups:
        scheduled_at = group.scheduled_at
        exam_codes = group.exam_codes
        if not exam_codes:
            raise ProcessMessageFormatError("grupo de agendamento sem exames")
        exam_names = [
            _canonical_name(code, canonical_names_by_code) for code in exam_codes
        ]
        lines.append(f"- {_format_datetime(scheduled_at)} — {_join_names(exam_names)}")
    return "\n".join(lines)


def _format_unavailable_exams(
    response: ScheduleApiResponse,
    canonical_names_by_code: dict[str, str],
) -> str:
    names = [
        _canonical_name(exam.exam_code, canonical_names_by_code)
        for exam in response.not_scheduled
    ]
    return "\n".join(f"- {name}" for name in names)


def _canonical_name(code: str, canonical_names_by_code: dict[str, str]) -> str:
    try:
        return canonical_names_by_code[code]
    except KeyError:
        raise ProcessMessageFormatError(
            "código de agendamento sem nome canônico resolvido"
        ) from None


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=DISPLAY_TIMEZONE)
    else:
        value = value.astimezone(DISPLAY_TIMEZONE)
    return value.strftime("%d/%m/%Y às %H:%M")


def _join_names(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} e {names[-1]}"


def _append_section(sections: list[str], title: str, content: str) -> None:
    if content:
        sections.append(f"{title}:\n{content}")
