"""Helper functions"""


def make_student_payload(class_=None, **overrides):
    payload =  {
        "name": "Shaun",
        "nisn": "9876543210",
        "class_id": class_.class_id if class_ else None,
        "current": True,
    }
    payload.update(overrides)
    return payload


def make_class_payload(**overrides):
    """A baseline valid POST body. Override individual fields per test."""
    payload = {"class_name": "XI-B"}
    payload.update(overrides)
    return payload

