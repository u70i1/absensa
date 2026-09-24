"""Shared Jinja environment and presentation-only helpers."""

import re
from pathlib import Path

from fastapi.templating import Jinja2Templates

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=APP_DIR / "templates")


def student_initials(name: str | None) -> str:
    words = re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", name or "", flags=re.UNICODE)
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].capitalize()
    return "".join(word[0].upper() for word in words[:2])


templates.env.filters["initials"] = student_initials
