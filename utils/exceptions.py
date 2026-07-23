"""
Custom application exceptions.
"""


class HrAiException(Exception):
    """Base exception for the application."""


class ConfigurationError(HrAiException):
    """Raised when configuration is invalid."""


class DatabaseConnectionError(HrAiException):
    """Raised when the database cannot be reached."""


class DatabaseQueryError(HrAiException):
    """Raised when a database query fails."""


class ValidationError(HrAiException):
    """Raised when input validation fails."""


class EmployeeNotFoundError(HrAiException):
    """Raised when an employee cannot be found."""


class DuplicateEmployeeError(HrAiException):
    """Raised when a duplicate employee is detected."""


class SqlGenerationError(HrAiException):
    """Raised when SQL generation fails."""


class SemanticSearchError(HrAiException):
    """Raised when semantic search fails."""


class LlmError(HrAiException):
    """Raised when the LLM request fails."""


class EmbeddingError(HrAiException):
    """Raised when embedding generation fails."""

class RepositoryError(HrAiException):
    """Raised when a repository operation fails."""


class ServiceError(HrAiException):
    """Raised when a service-layer operation fails."""


class HistoryError(HrAiException):
    """Raised when an employee-history operation fails."""


class ExplanationError(HrAiException):
    """Raised when building or validating an Explanation fails."""