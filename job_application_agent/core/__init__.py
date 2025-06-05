"""Core components for the Job Application Agent."""

try:
    from .agent import JobApplicationAgent
    from .config import Config
    
    __all__ = ["JobApplicationAgent", "Config"]
except ImportError:
    __all__ = [] 