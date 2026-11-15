"""Custom exceptions mapping to the error JSON shape in docs/api.md.
Never let a raw exception reach the client; main.py's handlers convert these
(and anything else) into { "error": { "code", "message", "details" } }.
"""


class AppError(Exception):
    code: str = "INTERNAL_ERROR"
    status_code: int = 500

    def __init__(self, message: str, details: dict | None = None, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class EmptyUploadError(AppError):
    code = "EMPTY_UPLOAD"
    status_code = 400


class InvalidRequestError(AppError):
    code = "INVALID_REQUEST"
    status_code = 400


class BatchFinalizedError(AppError):
    code = "BATCH_FINALIZED"
    status_code = 400


class TooManyFilesError(AppError):
    code = "TOO_MANY_FILES"
    status_code = 400


class BatchNotFoundError(AppError):
    code = "BATCH_NOT_FOUND"
    status_code = 404


class ImageNotFoundError(AppError):
    code = "IMAGE_NOT_FOUND"
    status_code = 404


class BatchNotReadyError(AppError):
    code = "BATCH_NOT_READY"
    status_code = 409


class RequestTooLargeError(AppError):
    code = "REQUEST_TOO_LARGE"
    status_code = 413


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    status_code = 422
