from typing import Literal, get_args

ToolId = Literal[
    "medical_order_ocr",
    "exam_catalog_search",
    "appointment_booking",
]

TOOL_REGISTRY_ORDER: tuple[ToolId, ...] = get_args(ToolId)
REQUIRED_TOOL_IDS: frozenset[ToolId] = frozenset(TOOL_REGISTRY_ORDER)
