"""
Job Application Agent - AI-Powered Automated Job Applications

A sophisticated AI agent system for automating job applications across various platforms.
Built with modern AI/LLM integration, robust error handling, and adaptive form filling.
"""

__version__ = "2.0.0"
__author__ = "Job Application Agent Team"
__description__ = "AI-powered automated job application system"

# Core imports for easy access
try:
    from .core.agent import JobApplicationAgent
    from .core.config import Config
    from .tools.browser_tool import BrowserTool
    
    __all__ = [
        "JobApplicationAgent",
        "Config", 
        "BrowserTool",
    ]
except ImportError:
    # Handle import errors during development
    __all__ = [] 