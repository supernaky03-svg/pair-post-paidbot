class AppError(Exception):
    """Base application error."""

class ValidationError(AppError):
    """Raised when user input is invalid."""

class SourceResolveError(AppError):
    """Raised when a source cannot be resolved safely."""

