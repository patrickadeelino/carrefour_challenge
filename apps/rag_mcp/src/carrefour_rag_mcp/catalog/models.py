"""Strict schema and integrity checks for the bundled exam catalog."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictCatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CatalogExam(StrictCatalogModel):
    code: str = Field(pattern=r"^CAT-\d{3}$")
    name: str = Field(min_length=1, max_length=160)
    aliases: tuple[str, ...] = Field(max_length=20)

    @field_validator("name", "code")
    @classmethod
    def reject_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("valor com espaços externos")
        return value

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, aliases: tuple[str, ...]) -> tuple[str, ...]:
        if any(not alias.strip() or alias != alias.strip() for alias in aliases):
            raise ValueError("alias vazio ou com espaços externos")
        return aliases

    @model_validator(mode="after")
    def validate_alias_integrity(self) -> "CatalogExam":
        normalized_name = _basic_key(self.name)
        normalized_aliases = [_basic_key(alias) for alias in self.aliases]
        if len(normalized_aliases) != len(set(normalized_aliases)):
            raise ValueError("aliases duplicados no mesmo exame")
        if normalized_name in normalized_aliases:
            raise ValueError("alias repete o nome canônico")
        return self


class CatalogDocument(StrictCatalogModel):
    exams: tuple[CatalogExam, ...] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_catalog_integrity(self) -> "CatalogDocument":
        codes = [exam.code for exam in self.exams]
        if len(codes) != len(set(codes)):
            raise ValueError("códigos duplicados")

        canonical_names = [_basic_key(exam.name) for exam in self.exams]
        if len(canonical_names) != len(set(canonical_names)):
            raise ValueError("nomes canônicos duplicados")
        return self


def _basic_key(value: str) -> str:
    return " ".join(value.casefold().split())
