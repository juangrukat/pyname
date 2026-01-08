class AIRenamerError(Exception):
    """Base exception for Pynamer."""
    pass


class LLMError(AIRenamerError):
    """Error communicating with LLM."""
    pass


class LLMConnectionError(LLMError):
    """Could not connect to LLM provider."""
    pass


class LLMResponseError(LLMError):
    """Invalid response from LLM."""
    pass


class MetadataError(AIRenamerError):
    """Error extracting metadata."""
    pass


class RenameError(AIRenamerError):
    """Error during rename operation."""
    pass


class ConfigError(AIRenamerError):
    """Configuration error."""
    pass
