class SafeError(Exception):
    """Only pre-authored messages cross CLI/MCP boundaries; never upstream exception text."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
