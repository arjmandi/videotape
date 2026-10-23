"""The intent document's own JSON Schema (05 §6: "intent serialises to JSON with a published schema").

The models below describe what `videotape.serialize` writes; they are not used to build it.
`intent_schema()` is the published schema, kept in `intent.schema.json` beside this module; a test
holds the two together and validates every sample app's intent against it.

    python -m videotape.spec > src/videotape/intent.schema.json
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .derive import AFFORDANCES
from .serialize import FORMAT

Name = Annotated[str, Field(pattern=r"^[A-Za-z][\w-]*$")]
FieldName = Annotated[str, Field(pattern=r"^[A-Za-z_]\w*\.[A-Za-z_]\w*$", description="A field reference: Record.field")]
Affordance = Literal[AFFORDANCES]  # type: ignore[valid-type]


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldRef(_Spec):
    """A field reference, `Deal.amount`; in an action's arguments it means this item's value."""

    field: FieldName


class Phrase(_Spec):
    """A message key with parameters, from `vt.t(...)`."""

    t: str
    params: dict[str, Any] | None = None


Label = str | Phrase | FieldRef


class HandlerRef(_Spec):
    """A decision: the engine calls the app's handler of this name over the app protocol."""

    handler: str


class LoaderRef(_Spec):
    loader: str


class _Identity(_Spec):
    sign_in: Any = None
    sign_out: Literal[True] | None = None


class Jump(_Identity):
    type: Literal["jump"]
    tape: Name
    args: dict[str, Any] | None = None


class Goto(_Identity):
    type: Literal["goto"]
    frame: Name


class Back(_Identity):
    type: Literal["back"]


class Stay(_Identity):
    type: Literal["stay"]


class Call(_Spec):
    type: Literal["call"]
    tape: Name
    then: HandlerRef | None = Field(None, description="The handler that receives done()'s result as `result`.")
    args: dict[str, Any] | None = None


class Done(_Spec):
    type: Literal["done"]
    result: Any = None


class Open(_Spec):
    type: Literal["open"]
    url: Any


class Download(_Spec):
    type: Literal["download"]
    name: str
    data: str
    encoding: Literal["base64"] | None = None


class Copy(_Spec):
    type: Literal["copy"]
    field: FieldName | None = None
    text: str | None = None


Outcome = Annotated[Jump | Goto | Back | Stay | Call | Done | Open | Download | Copy, Field(discriminator="type")]
Target = Outcome | HandlerRef


class Kind(_Spec):
    """What a type is to Videotape (the `x-vt` of a field, without its options)."""

    type: str
    record: str | None = None
    enum: str | None = None
    choices: list[Any] | None = None
    lines: list[int] | None = None
    item: Item | None = None
    nullable: Literal[True] | None = None


class Item(Kind):
    """A collection's item: its kind, and for records the components each item derives."""

    components: list[Component] | None = None
    states: list[FieldName] | None = None


class Component(_Spec):
    """A component: a field of a record the frame shows or edits, or a string the frame adds.

    Derived components nest: a record field's `components` are its fields, and a collection's
    `item` holds the components of each item. Only top-level derived components carry `from`.
    """

    model_config = ConfigDict(populate_by_name=True)

    field: FieldName | None = None
    text: str | Phrase | None = None
    from_: Literal["shows", "edit"] | None = Field(None, alias="from")
    type: str | None = None
    record: str | None = None
    enum: str | None = None
    choices: list[Any] | None = None
    lines: list[int] | None = None
    item: Item | None = None
    nullable: Literal[True] | None = None
    role: Literal["heading", "primary", "secondary", "navigation", "status", "supporting"] | None = None
    importance: Literal["required", "normal", "optional"] | None = None
    group: str | None = None
    order: int | None = None
    format: str | None = None
    kind: str | None = None
    commit: Literal["submit", "blur", "change"] | None = None
    options: Any = None
    select: Target | None = None
    pages: LoaderRef | None = None
    anchor: Literal["start", "end"] | None = None
    min_items: int | None = None
    max_items: int | None = None
    group_by: FieldRef | None = None
    surface: bool | None = None
    visible: FieldRef | None = None
    hidden: FieldRef | None = None
    press: Target | None = None
    label: Label | None = None
    pick: Name | None = None
    gt: Any = None
    ge: Any = None
    lt: Any = None
    le: Any = None
    affordances: list[Affordance]
    many: Literal[True] | None = Field(None, description="choose is choose(many): an edited list of choices.")
    components: list[Component] | None = None
    states: list[FieldName] | None = None
    events: dict[Literal["change", "play", "progress", "ended", "error"], Target] | None = None
    override: Literal[True] | None = None


class Action(_Spec):
    """A named action; `on` makes it an action on each item of that record (or of the items a field
    holds, where the frame holds the record more than once), `to` a move."""

    label: Label
    target: Target
    affordance: Literal["press", "move"]
    on: str | FieldRef | None = None
    to: str | None = None
    gesture: str | None = None
    key: str | None = None
    role: Literal["heading", "primary", "secondary", "navigation", "status", "supporting"] | None = None
    importance: Literal["required", "normal", "optional"] | None = None
    hidden: FieldRef | None = None
    visible: FieldRef | None = None


class Shows(_Spec):
    record: str | None = None
    collection: str | None = None


class Edits(_Spec):
    record: str


class Submit(_Spec):
    label: Label
    handler: str


class Change(_Spec):
    field: FieldName
    handler: str


class After(_Spec):
    seconds: float
    then: Target


class Frame(_Spec):
    """A place: its tape, and its `id` in a tape of several. Graph nodes are `tape` or `tape/id`."""

    id: Name | None = None
    purpose: str
    title: Label | None = None
    address: str | None = None
    public: Literal[True] | None = None
    shows: Shows | None = None
    edit: Edits | None = None
    enter: LoaderRef | None = None
    submit: Submit | None = None
    components: list[Component]
    states: list[FieldName] | None = None
    actions: list[Action] | None = None
    on_change: list[Change] | None = None
    after: After | None = None
    back: Literal[False] | None = Field(None, description="back=False: no platform back here.")
    hub: Literal[False] | None = Field(None, description="hub=False: the hub never shows here.")
    root: Literal[True] | None = Field(
        None, description="A history root: the entry, a hub destination's first frame, or where a sign-in or sign-out lands."
    )


class Tape(_Spec):
    """A journey; its first frame is where it starts."""

    id: Name
    frames: list[Frame] = Field(min_length=1)


class Destination(_Spec):
    tape: Name
    label: Label
    symbol: str | None = None


class Param(Kind):
    """A parameter after ctx: a document by record type, a move's target, or a loader's argument."""

    name: str
    required: bool
    default: Any = None


class Declared(_Spec):
    """An outcome a handler returns, read from its body or its @vt.outcomes; `implied` marks the Stay
    every handler has because it may Reject."""

    type: Literal["goto", "jump", "back", "stay", "call", "done", "open", "download"]
    tape: Name | None = None
    frame: Name | None = None
    args: list[str] | None = Field(None, description="The names of its keyword arguments.")
    args_open: Literal[True] | None = Field(None, description="It passes **kwargs, so not every name is known.")
    resets_history: Literal[True] | None = Field(None, description="It signs in or out: history starts again.")
    then: HandlerRef | None = None
    implied: Literal[True] | None = None


class Handler(_Spec):
    """A decision: its documents by record type, and the outcomes it returns, read from its body."""

    params: list[Param]
    outcomes: list[Declared]
    unreadable: str | None = Field(None, description="Which returns cannot be read; its edges are not all known.")


class Loader(_Spec):
    """A loader: what a frame shows (`enter=`), the next page of a list (`@vt.pages`), or a choice's options."""

    params: list[Param]
    returns: Kind | None = None
    unreadable: str | None = None


class Edge(_Spec):
    """A declared edge of the journey graph. `to` is absent for back and done, and for names that do not
    exist. The platform's back (from every frame with history that is not a root and has no
    back=False) and the hub's doors are implied, not listed."""

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str | None = None
    type: Literal["goto", "jump", "back", "call", "done"]
    tape: Name | None = None
    frame: Name | None = None
    resets_history: Literal[True] | None = None
    via: dict[str, Any]


class Intent(_Spec):
    """A Videotape app's intent: records, tapes, frames, components, actions, handlers, and edges."""

    format: Literal[FORMAT]  # type: ignore[valid-type]
    app: Name
    entry: str
    world: str | None = None
    hub: list[Destination] | None = None
    tapes: list[Tape]
    records: dict[str, dict[str, Any]] = Field(
        description="Each record's JSON Schema, with Videotape's options under x-vt; enums too. "
        "References point at #/records/Name and #/types/vt.Name."
    )
    types: dict[str, dict[str, Any]] = Field(description="The built-in types the records use, as vt.Name.")
    handlers: dict[str, Handler]
    loaders: dict[str, Loader]
    edges: list[Edge]


def _tidy(node: Any) -> Any:
    """Optional properties are absent, never null, in intent JSON; say so in the schema."""
    if isinstance(node, list):
        return [_tidy(n) for n in node]
    if not isinstance(node, dict):
        return node
    out = {k: _tidy(v) for k, v in node.items()}
    any_of = out.get("anyOf")
    if out.get("default", ...) is None and isinstance(any_of, list) and {"type": "null"} in any_of:
        rest = [b for b in any_of if b != {"type": "null"}]
        del out["default"], out["anyOf"]
        out.update(rest[0] if len(rest) == 1 else {"anyOf": rest})
    elif out.get("default", ...) is None and not any_of:
        del out["default"]
    return out


def intent_schema() -> dict[str, Any]:
    schema = _tidy(Intent.model_json_schema(by_alias=True))
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "Videotape intent", **schema}


if __name__ == "__main__":
    print(json.dumps(intent_schema(), indent=2, ensure_ascii=False))
