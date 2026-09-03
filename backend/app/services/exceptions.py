class AppException(Exception):
    detail = "unknown_error"
    status_code = 400

    def __init__(self, detail=None, status_code=None):
        self.detail = detail if detail is not None else self.detail
        self.status_code = status_code if status_code is not None else self.status_code
        super().__init__(self.detail)


class DuplicateNisn(AppException):
    detail = "duplicate_nisn"
    status_code = 409


class DuplicateScanLog(AppException):
    detail = "duplicate_scan"
    status_code = 409


class ScanLogNotFound(AppException):
    detail = "scan_log_not_found"
    status_code = 422


class ClassNotFound(AppException):
    detail = "class_not_found"
    status_code = 422


class StudentNotFound(AppException):
    detail = "student_not_found"
    status_code = 422
