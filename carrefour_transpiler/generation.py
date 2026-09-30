from textwrap import dedent

from .specification import Specification
from .tool_registry import TOOL_REGISTRY_ORDER

AGENT_INSTRUCTIONS = {
    "exam_scheduler": (
        "Você é um agente de agendamento de exames. Use somente as ferramentas "
        "fornecidas para ler o pedido, localizar os exames no catálogo e solicitar "
        "o agendamento. Não invente exames, códigos, disponibilidade ou horários. "
        "Confirme os detalhes com a pessoa antes de enviar uma solicitação de "
        "agendamento."
    )
}


def generate_agent_source(specification: Specification) -> str:
    """Renderiza uma factory Python determinística para um agente Google ADK."""
    agent = specification.agent
    selected_tools = set(agent.tools)
    ordered_tools = tuple(
        tool_id for tool_id in TOOL_REGISTRY_ORDER if tool_id in selected_tools
    )
    instruction = AGENT_INSTRUCTIONS[agent.type]

    source = f"""
        from typing import Any

        from google.adk.agents import Agent


        AGENT_NAME = {agent.name!r}
        MODEL_NAME = {agent.model.name!r}
        TOOL_IDS = {ordered_tools!r}
        INSTRUCTION = {instruction!r}


        def create_agent(registered_tools: dict[str, Any]) -> Agent:
            expected_tool_ids = set(TOOL_IDS)
            registered_tool_ids = set(registered_tools)
            if registered_tool_ids == expected_tool_ids:
                return Agent(
                    name=AGENT_NAME,
                    model=MODEL_NAME,
                    instruction=INSTRUCTION,
                    tools=[registered_tools[tool_id] for tool_id in TOOL_IDS],
                )

            missing_tool_ids = sorted(expected_tool_ids - registered_tool_ids)
            extra_tool_ids = sorted(registered_tool_ids - expected_tool_ids)
            details = []
            if missing_tool_ids:
                details.append("IDs ausentes: " + ", ".join(missing_tool_ids))
            if extra_tool_ids:
                details.append("IDs extras: " + ", ".join(extra_tool_ids))
            raise ValueError(
                "registered_tools deve corresponder às tools declaradas; "
                + "; ".join(details)
            )
    """
    return dedent(source).lstrip().rstrip() + "\n"
