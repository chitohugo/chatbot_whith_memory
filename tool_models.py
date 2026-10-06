from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ListFilesArguments(ToolArguments):
    directory: str = Field(default=".", min_length=1, max_length=4096)


class ReadFileArguments(ToolArguments):
    file_path: str = Field(min_length=1, max_length=4096)


class EditFileArguments(ReadFileArguments):
    prev_text: str | None = Field(default=None, max_length=100_000)
    new_text: str = Field(default="", max_length=100_000)


class DeleteFileArguments(ReadFileArguments):
    recursive: StrictBool = False


class SaveMemoryArguments(ToolArguments):
    fact: str = Field(min_length=1, max_length=4000)

    @field_validator("fact")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("El recuerdo no puede estar vacío")
        return value.strip()


TOOL_ARGUMENT_MODELS = {
    "list_files": ListFilesArguments, "read_file": ReadFileArguments,
    "edit_file": EditFileArguments, "delete_file": DeleteFileArguments,
    "save_memory": SaveMemoryArguments,
}
