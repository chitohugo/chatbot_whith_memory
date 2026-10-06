"""Reglas administradas por el operador, independientes de las instrucciones del LLM."""
import os
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Operation = Literal["list", "read", "create", "edit", "delete"]


class PathRule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    allow: list[Operation] = Field(default_factory=list)
    deny: list[Operation] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def relative_path(cls, value):
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
            raise ValueError("Las reglas requieren rutas relativas con separadores /, sin .. ni unidades")
        return path.as_posix()


class FileAccessPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    default_allow: list[Operation] = Field(default_factory=lambda: ["list", "read"])
    rules: list[PathRule] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None):
        # Un archivo configurado ausente o inválido nunca habilita más permisos.
        return cls() if path is None else cls.model_validate_json(path.read_text(encoding="utf-8"))

    def allows(self, relative: str, operation: Operation):
        relative = os.path.normcase(relative).replace("\\", "/")
        allowed = operation in self.default_allow
        for rule in self.rules:
            prefix = os.path.normcase(rule.path).replace("\\", "/")
            if prefix != "." and relative != prefix and not relative.startswith(prefix + "/"):
                continue
            if operation in rule.deny:
                return False
            allowed = allowed or operation in rule.allow
        return allowed
