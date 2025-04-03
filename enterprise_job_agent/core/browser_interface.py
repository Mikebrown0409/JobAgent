"""Base interface for browser interactions."""

from typing import Optional, Protocol
from playwright.async_api import Frame, Page

class BrowserInterface(Protocol):
    """Protocol defining the interface for browser interactions."""
    
    page: Page
    
    async def get_frame(self, frame_identifier: Optional[str] = None) -> Frame:
        """Get a frame by identifier."""
        ...
    
    async def navigate(self, url: str) -> bool:
        """Navigate to a URL."""
        ... 