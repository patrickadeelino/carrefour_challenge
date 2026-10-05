from __future__ import annotations

import json

from carrefour_runtime.services.process.message_formatter import (
    NO_EXAMS_MESSAGE,
    REVIEW_MESSAGE,
    ProcessMessageFormatError,
    format_process_message,
)
from carrefour_runtime.services.process.schedule_api_client import ScheduleApiResponse
from carrefour_runtime.value_objects.process_result import ProcessResult

FIRST_APPOINTMENT_ID = "75e39b6b-0ea7-4a4e-bbcc-20b137b1f70d"
SECOND_APPOINTMENT_ID = "00f5be9b-06a4-46a8-a5f9-970131403e45"


def scheduled_result(
    *,
    already: list[dict[str, object]] | None = None,
    newly: list[dict[str, object]] | None = None,
    unavailable: list[dict[str, str]] | None = None,
) -> ProcessResult:
    response = ScheduleApiResponse.model_validate_json(
        json.dumps(
            {
                "status": _status(already, newly, unavailable),
                "already_scheduled": already or [],
                "newly_scheduled": newly or [],
                "not_scheduled": unavailable or [],
            }
        )
    )
    return ProcessResult.scheduled(
        response,
        {
            "CAT-001": "Hemograma completo",
            "CAT-002": "Glicemia de jejum",
            "CAT-003": "TSH",
        },
    )


def appointment(
    appointment_id: str,
    scheduled_at: str,
    *exam_codes: str,
) -> dict[str, object]:
    return {
        "appointment_id": appointment_id,
        "scheduled_at": scheduled_at,
        "exam_codes": list(exam_codes),
    }


def _status(
    already: list[dict[str, object]] | None,
    newly: list[dict[str, object]] | None,
    unavailable: list[dict[str, str]] | None,
) -> str:
    if unavailable:
        return "partial" if already or newly else "no_availability"
    return "completed"


def test_formats_only_newly_scheduled_appointments_with_local_time() -> None:
    result = scheduled_result(
        newly=[
            appointment(
                FIRST_APPOINTMENT_ID,
                "2026-10-05T12:00:00+00:00",
                "CAT-001",
                "CAT-002",
            ),
            appointment(
                SECOND_APPOINTMENT_ID,
                "2026-10-06T15:30:00-03:00",
                "CAT-003",
            ),
        ]
    )

    message = format_process_message(result)

    assert message == (
        "Novos agendamentos confirmados:\n"
        "- 05/10/2026 às 09:00 — Hemograma completo e Glicemia de jejum\n"
        "- 06/10/2026 às 15:30 — TSH"
    )
    _assert_no_internal_identifiers(message)


def test_formats_only_already_scheduled_appointments() -> None:
    result = scheduled_result(
        already=[
            appointment(
                FIRST_APPOINTMENT_ID,
                "2026-10-05T09:00:00-03:00",
                "CAT-001",
            )
        ]
    )

    message = format_process_message(result)

    assert message == (
        "Estes exames já estavam agendados:\n- 05/10/2026 às 09:00 — Hemograma completo"
    )
    _assert_no_internal_identifiers(message)


def test_formats_existing_and_new_appointments_in_separate_sections() -> None:
    result = scheduled_result(
        already=[
            appointment(
                FIRST_APPOINTMENT_ID,
                "2026-10-05T09:00:00-03:00",
                "CAT-001",
            )
        ],
        newly=[
            appointment(
                SECOND_APPOINTMENT_ID,
                "2026-10-05T09:30:00-03:00",
                "CAT-002",
            )
        ],
    )

    message = format_process_message(result)

    assert message == (
        "Agendamento atualizado.\n\n"
        "Já estavam agendados:\n"
        "- 05/10/2026 às 09:00 — Hemograma completo\n\n"
        "Novos agendamentos:\n"
        "- 05/10/2026 às 09:30 — Glicemia de jejum"
    )
    _assert_no_internal_identifiers(message)


def test_formats_partial_booking_and_exams_without_availability() -> None:
    result = scheduled_result(
        already=[
            appointment(
                FIRST_APPOINTMENT_ID,
                "2026-10-05T09:00:00-03:00",
                "CAT-001",
            )
        ],
        newly=[
            appointment(
                SECOND_APPOINTMENT_ID,
                "2026-10-05T09:30:00-03:00",
                "CAT-002",
            )
        ],
        unavailable=[{"exam_code": "CAT-003", "reason": "no_availability"}],
    )

    message = format_process_message(result)

    assert "Agendamento parcial." in message
    assert "Já estavam agendados:" in message
    assert "Novos agendamentos:" in message
    assert "Sem disponibilidade de horário:\n- TSH" in message
    _assert_no_internal_identifiers(message)


def test_formats_no_availability_when_nothing_was_scheduled() -> None:
    result = scheduled_result(
        unavailable=[
            {"exam_code": "CAT-001", "reason": "no_availability"},
            {"exam_code": "CAT-002", "reason": "no_availability"},
        ]
    )

    message = format_process_message(result)

    assert message == (
        "Não foi possível encontrar horários disponíveis para:\n"
        "- Hemograma completo\n"
        "- Glicemia de jejum"
    )
    _assert_no_internal_identifiers(message)


def test_formats_empty_extraction_without_schedule_data() -> None:
    result = ProcessResult.from_ocr({"exams": []})

    assert format_process_message(result) == NO_EXAMS_MESSAGE


def test_review_message_never_repeats_exam_or_ambiguous_text() -> None:
    result = ProcessResult.from_ocr(
        {
            "status": "review_required",
            "exams": ["NOME-PACIENTE-SINTETICO"],
            "ambiguous_exams": ["CPF-PII-SINTETICO"],
        }
    )

    message = format_process_message(result)

    assert message == REVIEW_MESSAGE
    assert "NOME-PACIENTE-SINTETICO" not in message
    assert "CPF-PII-SINTETICO" not in message


def test_missing_canonical_name_fails_without_exposing_catalog_code() -> None:
    result = scheduled_result(
        newly=[
            appointment(
                FIRST_APPOINTMENT_ID,
                "2026-10-05T09:00:00-03:00",
                "CAT-999",
            )
        ]
    )

    try:
        format_process_message(result)
    except ProcessMessageFormatError as error:
        assert "CAT-999" not in str(error)
        return

    raise AssertionError("código sem nome canônico deveria ser rejeitado")


def _assert_no_internal_identifiers(message: str) -> None:
    assert "CAT-" not in message
    assert FIRST_APPOINTMENT_ID not in message
    assert SECOND_APPOINTMENT_ID not in message
