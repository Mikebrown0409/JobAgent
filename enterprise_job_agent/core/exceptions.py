"""Custom exceptions for the enterprise job agent system."""

class ActionExecutionError(Exception):
    """Custom exception for action execution failures."""
    pass


class FrameNotFoundError(Exception):
    """Custom exception for when a required frame is not found."""
    pass


class ElementNotFoundError(Exception):
    """Custom exception for when a required element is not found."""
    pass

# Add other custom exceptions here as needed 