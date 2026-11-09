class WhatIfError(Exception):
    """Expected, user-facing production error."""


class ValidationError(WhatIfError):
    """Episode or configuration validation failed."""


class ExternalToolError(WhatIfError):
    """An external executable or media operation failed."""
