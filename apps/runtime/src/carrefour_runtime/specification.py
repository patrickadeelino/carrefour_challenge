from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .tool_registry import REQUIRED_TOOL_IDS, ToolId


class StrictSpecificationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ModelSpecification(StrictSpecificationModel):
    provider: Literal["gemini", "zai"]
    name: Literal["gemini-3.1-flash-lite", "glm-5.3"]

    @model_validator(mode="after")
    def validate_provider_model_pair(self) -> Self:
        allowed_models = {
            "gemini": "gemini-3.1-flash-lite",
            "zai": "glm-5.3",
        }
        if allowed_models[self.provider] != self.name:
            raise ValueError("o modelo não pertence ao provedor declarado")

        return self


class AgentSpecification(StrictSpecificationModel):
    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")]
    type: Literal["exam_scheduler"]
    model: ModelSpecification
    tools: list[ToolId]

    @field_validator("tools")
    @classmethod
    def validate_tools(cls, tools: list[ToolId]) -> list[ToolId]:
        if len(tools) != len(set(tools)):
            raise ValueError("IDs duplicados não são permitidos")

        missing_tools = sorted(REQUIRED_TOOL_IDS - set(tools))
        if missing_tools:
            raise ValueError("tools obrigatórias ausentes: " + ", ".join(missing_tools))

        return tools


class Specification(StrictSpecificationModel):
    agent: AgentSpecification
