"""Helper functions for test files"""

from typing import Any, Optional

from app.models.class_ import Class


def make_student_payload(
    class_: Optional["Class"] = None, **overrides: Any
) -> dict[str, Any]:
    """Generate a valid student payload dictionary.

    Args:
        class_: The class/section the student belongs to. Defaults to None.
        **overrides: Common overrides include:
            - `name` (str): The student's full name. Default is `"Shaun"`.
            - `nisn` (str): The student's NISN, exactly 10 characters.
              Default is `"9876543210"`.
            - `current` (bool): Whether the student is currently enrolled.
              Default is `True`.

    Returns:
        A dictionary containing the student payload, guaranteed to have
        the keys `name`, `nisn`, `class_id`, and `current`.
    """
    payload = {
        "name": "Shaun",
        "nisn": "9876543210",
        "class_id": class_.class_id if class_ else None,
        "current": True,
    }
    payload.update(overrides)
    return payload


def make_class_payload(**overrides: Any) -> dict[str, Any]:
    """Generate a valid class payload dictionary.

    Args:
        **overrides: Override any payload field. The only intended use is
            `class_name` (str), which defaults to "XI-B".

    Returns:
        A dict with the key `class_name`.
    """
    payload = {"class_name": "XI-B"}
    payload.update(overrides)
    return payload
