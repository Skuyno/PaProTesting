"""Domain exceptions for the service."""


class OperationAlreadyExistsError(Exception):
    """Raised when an operation with the same id already exists."""

class OperationNotFoundError(Exception):
    """Raised when the requested operation does not exist."""

class ProviderUnavailableError(Exception):
    """Raised if it was not possible to receive a response from the provider."""

class ReceiptConflictError(Exception):
    """Raised when a receipt contradicts the stored provider payment id."""
