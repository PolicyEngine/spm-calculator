"""Stable validation errors shared by SPM consumer adapters."""


class SPMInputError(ValueError):
    """An actionable input error suitable for an API validation response."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)

    def to_dict(self):
        return {"code": self.code, "message": str(self)}
