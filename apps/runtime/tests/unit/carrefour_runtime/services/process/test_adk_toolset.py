from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from carrefour_runtime.services.process.adk_toolset import build_registered_tools


def test_registered_tools_expose_ocr_and_controlled_not_implemented_stubs() -> None:
    tools = build_registered_tools("http://ocr-mcp:8000/sse")

    assert set(tools) == {
        "medical_order_ocr",
        "exam_catalog_search",
        "appointment_booking",
    }
    assert isinstance(tools["medical_order_ocr"], McpToolset)
    assert tools["exam_catalog_search"]("hemograma") == {
        "status": "not_implemented",
        "message": "A busca no catálogo ainda não está implementada.",
    }
    assert tools["appointment_booking"]("exam-123") == {
        "status": "not_implemented",
        "message": "O agendamento ainda não está implementado.",
    }
