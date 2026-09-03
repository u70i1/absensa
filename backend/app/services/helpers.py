def check_missing_fields(required: set, input: dict) -> set:
    provided = {field for field, value in input.items() if value is not None}
    return required - provided


def fail(index: int, error: str, item) -> dict:
    """Build one failure entry in the shape both endpoints already return.
    error is exc.detail from an AppException, kept as a plain string here
    the service layer never raises out of the batch loop, so callers never
    see AppException instances, only this dict shape."""
    return {"index": index, "error": error, "item": item}


def bulk_response_or_422(succeeded: list, failed: list) -> dict:
    """Both bulk operations return the same envelope. The router decides
    whether 'failed present, succeeded empty' means a 422 status this
    function just returns the plain dict; no JSONResponse/status-code
    concerns belong at this layer."""
    return {"succeeded": succeeded, "failed": failed}
