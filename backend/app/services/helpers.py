def check_missing_fields(required: set, input: dict) -> set:
    provided = {field for field, value in input.items() if value is not None}
    return required - provided
