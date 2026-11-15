import hashlib
import json
import re
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

from videotape.checks import ChecksError, Spot
from videotape.frames import Box, Frame
from videotape.publish import publish

MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"
PROMPT = ('Find every piece of text in this image. Answer with a JSON array and nothing else. '
          'Each element is {"text": "...", "bbox_2d": [x1, y1, x2, y2], "button": true or false}. '
          'Copy each text exactly, keeping its case and punctuation. Give each separate line or label its own element. '
          'For a button, bbox_2d covers the whole button, not only its text.')
MAX_NEW_TOKENS = 1024


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
    name = "qwen3-vl-8b"

    def __init__(self, tape: Path):
        if find_spec("torch") is None or find_spec("transformers") is None:
            raise ChecksError("qwen3-vl-8b checks this model's keys and needs videotape's qwen extra, which is not "
                              "installed here; install videotape[qwen]")
        self.looks = tape / "looks"
        self.qwen: _Qwen | None = None

    def see(self, frame: Frame) -> tuple[Spot, ...]:
        fields = [MODEL_ID, PROMPT, MAX_NEW_TOKENS, frame.width, frame.height, hashlib.sha256(frame.rgb).hexdigest()]
        path = self.looks / f"{hashlib.sha256(json.dumps(fields).encode()).hexdigest()}.json"
        if not path.exists():
            self.qwen = self.qwen or _Qwen()
            reply = self.qwen.ask(frame)
            self.looks.mkdir(parents=True, exist_ok=True)
            publish(path, lambda partial: partial.write_text(json.dumps({"model": MODEL_ID, "reply": reply}, indent=2) + "\n"))
        return spots(json.loads(path.read_text())["reply"], frame.width, frame.height)


class _Qwen:
    def __init__(self):
        import torch
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            device = "mps"
        else:
            raise ChecksError("qwen3-vl-8b needs a CUDA GPU or Apple silicon (MPS), and this machine has neither")
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
