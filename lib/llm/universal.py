import json
from typing import Literal

from iafisher_foundation.prelude import *


Role = Literal["user", "assistant"]


# TODO(2026-02): Something that's a little inelegant about this representation is that messages
# can have impossible roles, e.g., `ThinkingMessage` can have `role="user"` which should be
# impossible.


@dataclass
class Message:
    role: Role


@dataclass
class Citation:
    title: str
    url: str


@dataclass
class TextMessage(Message):
    text: str
    citations: List[Citation] = dataclasses.field(default_factory=list)

    @override
    def __str__(self) -> str:
        return self.text

    def merge_in_place(self, other: "TextMessage") -> None:
        self.text += other.text
        self.citations.extend(other.citations)


@dataclass
class ThinkingMessage(Message):
    thinking: str

    @override
    def __str__(self) -> str:
        return f"<thinking>{self.thinking}</thinking>"


@dataclass
class ToolUseRequest(Message):
    tool_use_id: str
    tool_name: str
    tool_input: Any


@dataclass
class ToolUseResponse(Message):
    tool_output: str


@dataclass
class UnknownMessage(Message):
    raw_json: Any

    @override
    def __str__(self) -> str:
        return "unknown message type: " + json.dumps(self.raw_json)
