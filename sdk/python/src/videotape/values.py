"""The built-in value types of the vocabulary (design 05 §6.1, guide 06 §4).

Each type says what the engine derives from it: `Secret` is written and never drawn; `Text` is
written over several lines; `Money` carries its currency; `Image`, `Video`, `Audio`, `RichText`,
and `Series` are facts, shown exactly. Every one of them marks its JSON Schema with
`"x-vt": {"type": ...}` so the intent says what each field is without naming Python classes.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import core_schema as cs

VT = "x-vt"
"""The JSON Schema extension key that carries Videotape's options."""


# ── strings ──────────────────────────────────────────────────────────────────


class Secret(str):
    """A value the user types once: it reaches the handler and is never stored, logged, or drawn.

    It is a `str`, so a handler can pass it on; its repr is masked, so it stays out of logs.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "Secret('••••••')"

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: Any) -> cs.CoreSchema:
        return cs.no_info_after_validator_function(cls, cs.str_schema())

    @classmethod
    def __get_pydantic_json_schema__(cls, schema: cs.CoreSchema, handler: Any) -> dict[str, Any]:
        out = handler(schema)
        out.update(format="password", writeOnly=True)
        out[VT] = {"type": "secret"}
        return out


class Text(str):
    """Text written over several lines: one to six, unless `vt.Field(lines=(3, 12))` says otherwise.

    A type used bare, as an annotation (`notes: vt.Text`); its values are plain strings.
    """

    LINES = (1, 6)

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: Any) -> cs.CoreSchema:
        return cs.str_schema()

    @classmethod
    def __get_pydantic_json_schema__(cls, schema: cs.CoreSchema, handler: Any) -> dict[str, Any]:
        out = handler(schema)
        out[VT] = {"type": "text"}
        return out


class Id(str):
    """A document's identity (05 §6.1): never shown, and not required until the app saves the record.

    The engine holds a document, syncs it, and keys list items by it. A record has at most one.
    """

    __slots__ = ()

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: Any) -> cs.CoreSchema:
        return cs.no_info_after_validator_function(
            lambda v: cls(str(v)), cs.union_schema([cs.str_schema(), cs.int_schema(strict=True)])
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, schema: cs.CoreSchema, handler: Any) -> dict[str, Any]:
        return {"type": "string", VT: {"type": "id"}}


class Phrase(str):
    """Copy with parameters, from `vt.t(...)`; its string value is the key. Copy lives in intent, so a
    record refuses it: a document holds data (05 §6.1)."""

    key: str
    params: dict[str, Any]

    def __new__(cls, key: str, params: dict[str, Any]) -> Phrase:
        phrase = super().__new__(cls, key)
        phrase.key = key
        phrase.params = params
        return phrase

    def __repr__(self) -> str:
        args = "".join(f", {k}={v!r}" for k, v in self.params.items())
        return f"vt.t({self.key!r}{args})"


def t(key: str, **params: Any) -> Phrase:
    """Copy with parameters, looked up in the catalogue: `vt.t("dashboard.hello", name=Dashboard.first_name)`.

    A parameter may be a field reference, which the engine fills in the user's locale.
    """
    if not re.fullmatch(r"[A-Za-z][\w-]*(\.[A-Za-z0-9][\w-]*)*", key):
        raise ValueError(f"vt.t({key!r}): a message key is dotted words, such as 'dashboard.hello'")
    return Phrase(key, params)


# ── money ────────────────────────────────────────────────────────────────────


class Money:
    """An amount with its currency. It compares with numbers by amount, so `vt.Field(ge=0)` works."""

    __slots__ = ("amount", "currency")

    amount: Decimal
    currency: str

    def __init__(self, amount: Decimal | int | float | str, currency: str) -> None:
        try:
            value = Decimal(str(amount))
        except InvalidOperation:
            raise ValueError(f"not an amount: {amount!r}") from None
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError(f"not an ISO 4217 currency code: {currency!r}")
        object.__setattr__(self, "amount", value)
        object.__setattr__(self, "currency", currency)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("Money is immutable")

    def __repr__(self) -> str:
        return f"Money('{self.amount}', '{self.currency}')"

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Money):
            return (self.amount, self.currency) == (other.amount, other.currency)
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.amount, self.currency))

    def _other(self, other: object) -> Decimal:
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise TypeError(f"cannot compare {self.currency} with {other.currency}")
            return other.amount
        if isinstance(other, (int, float, Decimal)):
            return Decimal(str(other))
        raise TypeError(f"cannot compare Money with {type(other).__name__}")

    def __lt__(self, other: object) -> bool:
        return self.amount < self._other(other)

    def __le__(self, other: object) -> bool:
        return self.amount <= self._other(other)

    def __gt__(self, other: object) -> bool:
        return self.amount > self._other(other)

    def __ge__(self, other: object) -> bool:
        return self.amount >= self._other(other)

    def to_json(self) -> dict[str, str]:
        return {"amount": str(self.amount), "currency": self.currency}

    @classmethod
    def _parse(cls, value: Any) -> Money:
        if isinstance(value, Money):
            return value
        if isinstance(value, dict) and set(value) == {"amount", "currency"}:
            return cls(value["amount"], value["currency"])
        if isinstance(value, str) and (m := re.fullmatch(r"\s*(-?[\d.]+)\s+([A-Z]{3})\s*", value)):
            return cls(m[1], m[2])
        raise ValueError("expected Money, {'amount': ..., 'currency': ...}, or '12.50 EUR'")

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: Any) -> cs.CoreSchema:
        return cs.no_info_plain_validator_function(
            cls._parse, serialization=cs.plain_serializer_function_ser_schema(lambda m: m.to_json())
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, schema: cs.CoreSchema, handler: Any) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "amount": {"type": "string", "pattern": r"^-?\d+(\.\d+)?$"},
                "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
            },
            "required": ["amount", "currency"],
            "additionalProperties": False,
            VT: {"type": "money"},
        }


# ── facts ────────────────────────────────────────────────────────────────────


class Value(BaseModel):
    """A built-in value: immutable, closed, and marked in JSON Schema with its Videotape type."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Image(Value):
    """A picture from data, drawn exactly; it carries its own alt text."""

    model_config = ConfigDict(json_schema_extra={VT: {"type": "image"}})

    src: str
    alt: str
    width: int | None = None
    height: int | None = None


class Video(Value):
    """A clip, played by the platform's own player on a screen in the world."""

    model_config = ConfigDict(json_schema_extra={VT: {"type": "video"}})

    src: str
    title: str | None = None
    poster: str | None = None
    captions: str | None = None


class Audio(Value):
    """A sound, played by the platform's own player."""

    model_config = ConfigDict(json_schema_extra={VT: {"type": "audio"}})

    src: str
    title: str | None = None
    transcript: str | None = None


class Span(Value):
    """A run of text in `RichText`: plain, emphasised, code, a link, or a mention."""

    model_config = ConfigDict(json_schema_extra={VT: {"part": "richtext"}})

    text: str
    emphasis: Literal["em", "strong"] | None = None
    code: bool = False
    link: str | None = None
    mention: str | None = None


class Paragraph(Value):
    model_config = ConfigDict(json_schema_extra={VT: {"part": "richtext"}})

    kind: Literal["paragraph"] = "paragraph"
    spans: list[Span]


class ListBlock(Value):
    model_config = ConfigDict(json_schema_extra={VT: {"part": "richtext"}})

    kind: Literal["list"] = "list"
    ordered: bool = False
    items: list[list[Span]]


class CodeBlock(Value):
    model_config = ConfigDict(json_schema_extra={VT: {"part": "richtext"}})

    kind: Literal["code"] = "code"
    text: str
    language: str | None = None


Block = Annotated[Paragraph | ListBlock | CodeBlock, Field(discriminator="kind")]

_INLINE = re.compile(
    r"`(?P<code>[^`]+)`"
    r"|\*\*(?P<strong>[^*]+)\*\*"
    r"|(?<!\w)[*_](?P<em>[^*_]+)[*_](?!\w)"
    r"|\[(?P<label>[^\]]+)\]\((?P<href>[^)\s]+)\)"
    r"|(?<![\w@])@(?P<mention>[A-Za-z0-9_][\w.-]*\w|[A-Za-z0-9_])"
)


def _spans(text: str) -> list[Span]:
    out: list[Span] = []
    at = 0
    for m in _INLINE.finditer(text):
        if m.start() > at:
            out.append(Span(text=text[at : m.start()]))
        if m["code"] is not None:
            out.append(Span(text=m["code"], code=True))
        elif m["strong"] is not None:
            out.append(Span(text=m["strong"], emphasis="strong"))
        elif m["em"] is not None:
            out.append(Span(text=m["em"], emphasis="em"))
        elif m["label"] is not None:
            out.append(Span(text=m["label"], link=m["href"]))
        else:
            out.append(Span(text="@" + m["mention"], mention=m["mention"]))
        at = m.end()
    if at < len(text):
        out.append(Span(text=text[at:]))
    return out


class RichText(Value):
    """Formatted text in a closed model: paragraphs, emphasis, links, lists, code, and mentions.

    The text engine draws it; links are actions that open. A plain `str` is accepted and becomes
    paragraphs, so `Message(text=draft.text)` works.
    """

    model_config = ConfigDict(json_schema_extra={VT: {"type": "richtext"}})

    blocks: list[Block]

    @model_validator(mode="before")
    @classmethod
    def _from_str(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"blocks": [{"kind": "paragraph", "spans": [{"text": p}]} for p in _paragraphs(value)]}
        return value

    @classmethod
    def from_text(cls, text: str) -> RichText:
        return cls.model_validate(text)

    @classmethod
    def from_markdown(cls, markdown: str) -> RichText:
        """Reads the part of Markdown the model can hold; headings become strong paragraphs."""
        blocks: list[Paragraph | ListBlock | CodeBlock] = []
        lines = markdown.replace("\r\n", "\n").split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("```"):
                language = line[3:].strip() or None
                body: list[str] = []
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    body.append(lines[i])
                    i += 1
                blocks.append(CodeBlock(text="\n".join(body), language=language))
                i += 1
            elif m := re.match(r"\s*(?:([-*])|(\d+)[.)])\s+", line):
                ordered = m[2] is not None
                items: list[list[Span]] = []
                while i < len(lines) and (m := re.match(r"\s*(?:[-*]|\d+[.)])\s+", lines[i])):
                    items.append(_spans(lines[i][m.end() :]))
                    i += 1
                blocks.append(ListBlock(ordered=ordered, items=items))
            elif line.strip():
                para: list[str] = []
                while i < len(lines) and lines[i].strip() and not lines[i].startswith("```") \
                        and not re.match(r"\s*(?:[-*]|\d+[.)])\s+", lines[i]):
                    para.append(lines[i].strip())
                    i += 1
                if para[0].startswith("#"):
                    blocks.append(Paragraph(spans=[Span(text=" ".join(para).lstrip("# "), emphasis="strong")]))
                else:
                    blocks.append(Paragraph(spans=_spans(" ".join(para))))
            else:
                i += 1
        return cls(blocks=blocks)

    @property
    def plain(self) -> str:
        """The text without formatting, paragraphs separated by blank lines."""
        parts: list[str] = []
        for b in self.blocks:
            if isinstance(b, Paragraph):
                parts.append("".join(s.text for s in b.spans))
            elif isinstance(b, ListBlock):
                parts.append("\n".join("".join(s.text for s in item) for item in b.items))
            else:
                parts.append(b.text)
        return "\n\n".join(parts)


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()] or [""]


class Series(Value):
    """A chart drawn from data, with a table as its accessible form: `vt.Series(rows, x="week", y="events")`."""

    model_config = ConfigDict(json_schema_extra={VT: {"type": "series"}})

    rows: list[dict[str, Any]]
    x: str
    y: str | list[str]

    def __init__(self, rows: list[dict[str, Any]] | None = None, /, **data: Any) -> None:
        if rows is not None:
            data["rows"] = rows
        super().__init__(**data)

    @model_validator(mode="after")
    def _columns_exist(self) -> Series:
        wanted = [self.x, *([self.y] if isinstance(self.y, str) else self.y)]
        for n, row in enumerate(self.rows):
            missing = [k for k in wanted if k not in row]
            if missing:
                raise ValueError(f"row {n} has no {', '.join(missing)}")
        return self


ItemT = TypeVar("ItemT")


class Page(BaseModel, Generic[ItemT]):
    """One page of a long list, from an `@vt.pages` loader: `vt.Page(posts, next_cursor)`."""

    items: list[ItemT]
    next: str | None = None

    def __init__(self, items: list[ItemT] | None = None, next: str | None = None, /, **data: Any) -> None:  # noqa: A002
        if items is not None:
            data["items"] = items
        if next is not None:
            data["next"] = next
        super().__init__(**data)


BUILTIN_TYPES: dict[type, str] = {
    Id: "id",
    Text: "text",
    Secret: "secret",
    Money: "money",
    Image: "image",
    Video: "video",
    Audio: "audio",
    RichText: "richtext",
    Series: "series",
}
"""Python class → its Videotape type, for the built-ins that are classes."""
