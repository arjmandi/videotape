import hashlib
import json
import re
import threading
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, distribution, requires
from pathlib import Path

from videotape.checks import Free, Purse, Read, Spot
from videotape.errors import ScreenplayError
from videotape.frames import Box, Frame
from videotape.atomic import write_atomically

MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"
PROMPT = ('Find every piece of text in this image. Answer with a JSON array and nothing else. '
          'Each element is {"text": "...", "bbox_2d": [x1, y1, x2, y2], "button": true or false}. '
          'Copy each text exactly, keeping its case and punctuation. Give each separate line or label its own element. '
          'For a button, bbox_2d covers the whole button, not only its text.'
          ' Read text on signs seen at an angle too. Never add a character that is not drawn, such as a period at the '
          'end of a line.')
MAX_NEW_TOKENS = 4096
ADD_EXTRA = ('in pyproject.toml, put [qwen] right after videotape in dependencies, as in "videotape[qwen] @ '
             'file:///Users/me/videotape" or "videotape[qwen]==0.1.0", then run uv sync')
"""How a project adds videotape's qwen extra, whichever source its videotape dependency names: a folder, a git
commit, or a version on an index."""


def installed() -> bool:
    """Whether videotape's qwen extra is installed: every distribution the extra names in videotape's own metadata,
    since Qwen3-VL-8B needs all of them, accelerate for its device_map among them."""
    try:
        named = [re.match(r"[A-Za-z0-9._-]+", line)[0] for line in requires("videotape") or []
                 if re.search(r"""extra\s*==\s*["']qwen["']""", line)]
        for name in named:
            distribution(name)
    except PackageNotFoundError:
        return False
    return bool(named)


def spots(reply: str, width: int, height: int) -> tuple[Spot, ...]:
    """What Qwen saw, as spots. An element it called a button is a control."""
    found = []
    for element in _elements(reply):
        try:
            text, (x1, y1, x2, y2) = element["text"], element["bbox_2d"]
            # Qwen3-VL grounds in coordinates relative to the image, from 0 to 1000 on each axis.
            box = Box(round(x1 * width / 1000), round(y1 * height / 1000),
                      round((x2 - x1) * width / 1000), round((y2 - y1) * height / 1000))
        except (KeyError, TypeError, ValueError):
            continue
        if isinstance(text, str) and text.strip():
            found.append(Spot(text.strip(), box, element.get("button") is True))
    return tuple(found)


def _elements(reply: str) -> list:
    """The objects of the reply's JSON array, in order. On garbled lettering Qwen can repeat one element until it runs
    out of tokens, so a cut-off array still yields every element that was complete before the cut."""
    fenced = re.search(r"```(?:json)?\s*(.*?)(?:```|$)", reply, re.S)
    body = (fenced.group(1) if fenced else reply).lstrip()
    if not body.startswith("["):
        return []
    decoder, at, elements = json.JSONDecoder(), 1, []
    while True:
        while at < len(body) and body[at] in " \t\r\n,":
            at += 1
        if at >= len(body) or body[at] == "]":
            return elements
        try:
            element, at = decoder.raw_decode(body, at)
        except json.JSONDecodeError:
            return elements
        elements.append(element)


class QwenEye:
    """Qwen3-VL-8B, run here, which reads every piece of text on a picture and says which sit in a button. It
    reports no marks and no charts, and caches each reply in the tape's looks/, by the picture's hash."""

    name = "qwen3-vl-8b"
    key = None
    paid = False

    @staticmethod
    def most(width: int, height: int) -> float:
        return 0.0

    def __init__(self, tape: Path):
        if not installed():
            raise ScreenplayError("VT105", self.name, "is a reader of this model's eye and runs through videotape's "
                                  "qwen extra, which is not installed here", ADD_EXTRA)
        self.looks = tape / "looks"

    def see(self, frame: Frame, purse: Purse = Free()) -> Read:
        fields = [MODEL_ID, PROMPT, MAX_NEW_TOKENS, frame.width, frame.height, hashlib.sha256(frame.rgb).hexdigest()]
        path = self.looks / f"{hashlib.sha256(json.dumps(fields).encode()).hexdigest()}.json"
        if not path.exists():
            reply = _ask(frame)
            self.looks.mkdir(parents=True, exist_ok=True)
            write_atomically(path, lambda partial: partial.write_text(json.dumps({"model": MODEL_ID, "reply": reply}, indent=2) + "\n"))
        return Read(self.name, spots(json.loads(path.read_text())["reply"], frame.width, frame.height))


_LOADED: list["_Qwen"] = []
_ONE_AT_A_TIME = threading.Lock()


def _ask(frame: Frame) -> str:
    """Qwen3-VL-8B's reply about the picture. A render reads the takes of two shots at once, and a screen test reads
    with an eye for each of its tapes, so they share one model, loaded on the first read, and ask it one picture at a
    time: transformers' first import is not safe from two threads, and each model holds the weights in memory."""
    with _ONE_AT_A_TIME:
        if not _LOADED:
            _LOADED.append(_Qwen())
        return _LOADED[0].ask(frame)


class _Qwen:
    def __init__(self):
        import torch
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            device = "mps"
        else:
            raise ScreenplayError("VT105", QwenEye.name, "needs a CUDA GPU or Apple silicon (MPS), and this machine has "
                                  "neither", "render on a Mac with Apple silicon or a machine with a CUDA GPU, or with "
                                  "the stand-in, as in videotape render --story starter --model stand-in")
        self.model = Qwen3VLForConditionalGeneration.from_pretrained(MODEL_ID, dtype=torch.bfloat16, device_map=device)
        self.processor = AutoProcessor.from_pretrained(MODEL_ID)

    def ask(self, frame: Frame) -> str:
        from PIL import Image

        image = Image.frombytes("RGB", (frame.width, frame.height), frame.rgb)
        messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": PROMPT}]}]
        inputs = self.processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=True,
                                                    return_tensors="pt").to(self.model.device)
        out = self.model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False,
                                  temperature=None, top_p=None, top_k=None)
        return self.processor.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
