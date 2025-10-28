# src/vention_communication/utils/errors.py

"""Custom exceptions for the Vention Communication library."""


class TypingError(Exception):
    """
    Raised when the library fails to infer or validate the types
    of an RPC action or stream, e.g., ambiguous parameters,
    missing annotations, unsupported type.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return f"TypingError: {self.message}"
