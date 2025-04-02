"""Advanced frame management for multi-frame job application pages."""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from playwright.async_api import Page, Frame, Locator

logger = logging.getLogger(__name__)

class AdvancedFrameManager:
    """Advanced frame manager for handling complex web applications with multiple frames."""
    
    def __init__(self, page: Page):
        """
        Initialize the frame manager.
        
        Args:
            page: The Playwright page object
        """
        self.page = page
        self.frames = {}  # Frame identifier to frame object
        self.frame_metadata = {}  # Additional metadata about frames
        self.navigation_paths = {}  # Paths between frames/states
        self.cached_selectors = {}  # Cache for selector lookup results
        logger.info("Advanced Frame Manager initialized")
    
    async def map_all_frames(self) -> Dict[str, Frame]:
        """
        Map all frames in the page and provide identifiable references.
        
        Returns:
            Dictionary of frame identifiers to frame objects
        """
        # Start with the main page frame
        self.frames = {"main": self.page.main_frame}
        self.frame_metadata = {
            "main": {
                "url": await self.page.main_frame.evaluate("window.location.href"),
                "title": await self.page.title(),
                "depth": 0,
                "parent": None
            }
        }
        
        # Wait for page to stabilize and iframes to load
        try:
            await self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as e:
            logger.warning(f"Wait for networkidle timed out, continuing with frame mapping: {e}")
        
        # Before mapping, check for common application patterns
        try:
            # Check for Greenhouse Application iframe - common pattern
            greenhouse_iframe = self.page.frame_locator('iframe[id="grnhse_iframe"]').first
            if await greenhouse_iframe.count() > 0:
                logger.info("Detected Greenhouse application iframe")
        except Exception as e:
            logger.debug(f"Error checking for Greenhouse iframe: {e}")
        
        # Map all child frames recursively
        await self._map_child_frames(self.page.main_frame, "main", 1)
        
        # Log mapped frames
        logger.info(f"Mapped {len(self.frames)} frames")
        for identifier, metadata in self.frame_metadata.items():
            logger.debug(f"Frame: {identifier} - URL: {metadata.get('url')}, Title: {metadata.get('title')}")
            
        return self.frames
    
    async def _map_child_frames(self, parent_frame: Frame, parent_id: str, depth: int) -> None:
        """
        Recursively map child frames.
        
        Args:
            parent_frame: The parent frame
            parent_id: The identifier of the parent frame
            depth: The current depth level
        """
        # Enhanced: Wait briefly to ensure all frames are loaded
        try:
            await asyncio.sleep(0.2 * depth)  # Progressive sleep based on depth
        except Exception:
            pass
        
        child_frames = parent_frame.child_frames
        logger.debug(f"Found {len(child_frames)} child frames in parent '{parent_id}'")
        
        for i, frame in enumerate(child_frames):
            try:
                # Get frame information with robust error handling
                frame_url = "about:blank"
                try:
                    frame_url = await frame.evaluate("window.location.href", timeout=2000)
                except Exception:
                    logger.debug(f"Could not get URL for frame at index {i}, using default")
                
                # Enhanced: More detailed frame inspection
                frame_attributes = {}
                try:
                    # Try to get iframe element attributes from parent
                    iframe_selector = f"iframe:nth-child({i+1})"
                    iframe_element = parent_frame.locator(iframe_selector)
                    
                    if await iframe_element.count() > 0:
                        for attr in ["id", "name", "src", "title", "class"]:
                            attr_value = await iframe_element.get_attribute(attr)
                            if attr_value:
                                frame_attributes[attr] = attr_value
                except Exception as e:
                    logger.debug(f"Error getting iframe attributes: {e}")
                
                # Get frame name with fallback
                frame_name = frame.name or frame_attributes.get("name") or f"frame_{len(self.frames)}"
                
                # Create a unique identifier that's stable across page reloads
                # Priority: explicit name/id > URL-based identifier > parent-based fallback
                if frame.name and frame.name != "":
                    identifier = frame.name
                elif frame_attributes.get("id"):
                    identifier = frame_attributes.get("id")
                elif frame_attributes.get("name"):
                    identifier = frame_attributes.get("name")
                elif "iframe" in frame_url:
                    # Extract a stable part of the URL if possible
                    url_parts = frame_url.split("/")
                    if len(url_parts) > 3:
                        identifier = f"{url_parts[2]}_{i}"
                    else:
                        identifier = f"{parent_id}_frame_{i}"
                else:
                    identifier = f"{parent_id}_frame_{i}"
                
                # Make sure identifier is unique by appending index if needed
                base_identifier = identifier
                counter = 1
                while identifier in self.frames:
                    identifier = f"{base_identifier}_{counter}"
                    counter += 1
                
                # Add to frames dict
                self.frames[identifier] = frame
                
                # Add metadata, including discovered attributes
                self.frame_metadata[identifier] = {
                    "url": frame_url,
                    "name": frame_name,
                    "depth": depth,
                    "parent": parent_id,
                    "index": i,
                    "attributes": frame_attributes
                }
                
                # Enhanced: Log more details about identified frame
                logger.debug(f"Mapped frame '{identifier}' at depth {depth} with attributes: {frame_attributes}")
                
                # Recursively map child frames
                await self._map_child_frames(frame, identifier, depth + 1)
                
            except Exception as e:
                logger.warning(f"Error mapping child frame at index {i} in parent '{parent_id}': {e}")
    
    async def find_frame_for_selector(self, selector: str) -> Optional[Tuple[str, Frame]]:
        """
        Find the frame that contains an element matching the selector.
        
        Args:
            selector: CSS selector to search for
            
        Returns:
            Tuple of (frame_identifier, frame) or None if not found
        """
        logger.debug(f"Searching for selector '{selector}' across all frames")
        
        # Check cache first
        if selector in self.cached_selectors:
            cached_identifier = self.cached_selectors[selector]
            if cached_identifier in self.frames:
                logger.debug(f"Using cached frame '{cached_identifier}' for selector '{selector}'")
                return (cached_identifier, self.frames[cached_identifier])
        
        # Sort frames by depth to search more efficiently (parent frames first)
        frame_items = sorted(
            self.frames.items(), 
            key=lambda x: self.frame_metadata.get(x[0], {}).get("depth", 0)
        )
        
        # Enhanced: First check frames that match known patterns
        for pattern, frame_identifiers in self._get_prioritized_frames().items():
            if pattern in selector.lower():
                logger.debug(f"Selector '{selector}' matches pattern '{pattern}', checking prioritized frames first")
                # Check prioritized frames first
                for identifier in frame_identifiers:
                    if identifier in self.frames:
                        frame = self.frames[identifier]
                        try:
                            # Check if the selector exists in this frame
                            count = await frame.locator(selector).count()
                            if count > 0:
                                logger.debug(f"Found selector '{selector}' in prioritized frame '{identifier}'")
                                # Cache the result for future lookups
                                self.cached_selectors[selector] = identifier
                                return (identifier, frame)
                        except Exception as e:
                            logger.debug(f"Error checking selector in prioritized frame '{identifier}': {e}")
        
        # Check all frames
        for identifier, frame in frame_items:
            try:
                # Add retry with better error handling
                for attempt in range(2):  # 2 attempts
                    try:
                        # Check if the selector exists in this frame
                        count = await frame.locator(selector).count()
                        if count > 0:
                            logger.debug(f"Found selector '{selector}' in frame '{identifier}'")
                            # Cache the result for future lookups
                            self.cached_selectors[selector] = identifier
                            return (identifier, frame)
                    except Error as e:
                        if "detached" in str(e).lower() and attempt == 0:
                            # Frame may be temporarily detached, retry once
                            logger.debug(f"Frame '{identifier}' might be detached, retrying")
                            await asyncio.sleep(0.5)
                        else:
                            raise
            except Exception as e:
                logger.warning(f"Error checking selector '{selector}' in frame '{identifier}': {e}")
        
        logger.warning(f"Selector '{selector}' not found in any frame")
        return None
    
    def _get_prioritized_frames(self) -> Dict[str, List[str]]:
        """
        Get prioritized frames based on common patterns.
        
        Returns:
            Dictionary mapping selector patterns to frame identifiers
        """
        # Map common element patterns to likely frame identifiers
        prioritized = {
            "first_name": ["application", "grnhse_iframe", "application_form"],
            "last_name": ["application", "grnhse_iframe", "application_form"],
            "email": ["application", "grnhse_iframe", "application_form"],
            "phone": ["application", "grnhse_iframe", "application_form"],
            "location": ["application", "grnhse_iframe", "application_form"],
            "resume": ["application", "grnhse_iframe", "application_form"],
            "education": ["application", "grnhse_iframe", "education_form"],
            "experience": ["application", "grnhse_iframe", "experience_form"]
        }
        
        # Ensure all identifiers exist, filtering out non-existent ones
        result = {}
        for pattern, identifiers in prioritized.items():
            result[pattern] = [i for i in identifiers if i in self.frames]
        
        return result
    
    async def reset_cached_selectors(self) -> None:
        """Clear the selector cache after navigation or major DOM changes."""
        logger.debug("Resetting cached selectors")
        self.cached_selectors = {}
    
    async def find_frame_by_content(self, content_text: str) -> Optional[Tuple[str, Frame]]:
        """
        Find a frame that contains specific text content.
        
        Args:
            content_text: Text to search for
            
        Returns:
            Tuple of (frame_identifier, frame) or None if not found
        """
        logger.debug(f"Searching for text '{content_text}' across all frames")
        
        for identifier, frame in self.frames.items():
            try:
                # Use text content locator to search
                text_locator = frame.get_by_text(content_text, exact=False)
                count = await text_locator.count()
                if count > 0:
                    logger.debug(f"Found text '{content_text}' in frame '{identifier}'")
                    return (identifier, frame)
            except Exception as e:
                logger.warning(f"Error checking for text '{content_text}' in frame '{identifier}': {e}")
        
        logger.warning(f"Text '{content_text}' not found in any frame")
        return None
    
    async def find_element(self, selector: str, text: Optional[str] = None) -> Optional[Tuple[str, Frame, Locator]]:
        """
        Find an element across all frames using selector and optional text content.
        
        Args:
            selector: CSS selector to search for
            text: Optional text content the element should contain
            
        Returns:
            Tuple of (frame_identifier, frame, locator) or None if not found
        """
        logger.debug(f"Searching for element with selector '{selector}' and text '{text}'")
        
        # Try to use cached frame information first
        if selector in self.cached_selectors:
            frame_id = self.cached_selectors[selector]
            if frame_id in self.frames:
                frame = self.frames[frame_id]
                try:
                    base_locator = frame.locator(selector)
                    count = await base_locator.count()
                    
                    if count > 0:
                        if text is not None:
                            text_locator = base_locator.filter(has_text=text)
                            text_count = await text_locator.count()
                            
                            if text_count > 0:
                                return (frame_id, frame, text_locator.first)
                        else:
                            return (frame_id, frame, base_locator.first)
                except Exception:
                    # Cache miss, continue with full search
                    pass
        
        # Full search across all frames
        frame_items = sorted(
            self.frames.items(), 
            key=lambda x: self.frame_metadata.get(x[0], {}).get("depth", 0)
        )
        
        for identifier, frame in frame_items:
            try:
                # First check if selector exists in this frame
                base_locator = frame.locator(selector)
                count = await base_locator.count()
                
                if count > 0:
                    # Update cache
                    self.cached_selectors[selector] = identifier
                    
                    # If text is specified, filter by text content
                    if text is not None:
                        text_locator = base_locator.filter(has_text=text)
                        text_count = await text_locator.count()
                        
                        if text_count > 0:
                            logger.debug(f"Found element with selector '{selector}' and text '{text}' in frame '{identifier}'")
                            return (identifier, frame, text_locator.first)
                    else:
                        logger.debug(f"Found element with selector '{selector}' in frame '{identifier}'")
                        return (identifier, frame, base_locator.first)
            except Exception as e:
                logger.warning(f"Error checking for element in frame '{identifier}': {e}")
        
        logger.warning(f"Element with selector '{selector}' and text '{text}' not found in any frame")
        return None
    
    async def wait_for_navigation_complete(self) -> None:
        """Wait for all frames to complete navigation and become stable."""
        logger.debug("Waiting for navigation to complete in all frames")
        
        # Wait for main frame first
        await self.page.wait_for_load_state("networkidle")
        
        # Then check all frames
        for identifier, frame in self.frames.items():
            try:
                await frame.wait_for_load_state("networkidle", timeout=5000)
            except Exception as e:
                logger.warning(f"Error waiting for frame '{identifier}' to load: {e}")
        
        # Add a small delay to ensure everything is really loaded
        await asyncio.sleep(1)
        
        logger.debug("Navigation completed for all frames")
    
    async def detect_new_frames(self) -> Dict[str, Frame]:
        """
        Detect any new frames that have appeared since the last mapping.
        
        Returns:
            Dictionary of new frame identifiers to frame objects
        """
        old_frame_count = len(self.frames)
        await self.map_all_frames()
        new_frame_count = len(self.frames)
        
        if new_frame_count > old_frame_count:
            logger.info(f"Detected {new_frame_count - old_frame_count} new frames")
            
        return self.frames
    
    async def analyze_frame_relationships(self) -> Dict[str, Any]:
        """
        Analyze relationships between frames to understand the application structure.
        
        Returns:
            Dictionary of frame relationship data
        """
        relationships = {}
        
        for identifier, metadata in self.frame_metadata.items():
            parent_id = metadata.get("parent")
            
            if parent_id:
                if parent_id not in relationships:
                    relationships[parent_id] = []
                    
                relationships[parent_id].append({
                    "id": identifier,
                    "url": metadata.get("url"),
                    "name": metadata.get("name"),
                    "depth": metadata.get("depth")
                })
        
        logger.debug(f"Analyzed frame relationships: {len(relationships)} parent frames with children")
        return relationships
    
    async def dismiss_dropdown(self, retry_attempts: int = 3) -> bool:
        """
        Dismiss any active dropdowns by clicking on the body element.
        
        Args:
            retry_attempts: Number of retry attempts if first try fails
            
        Returns:
            True if successful, False otherwise
        """
        logger.debug("Attempting to dismiss any active dropdowns")
        
        # Try in main frame first, then in all frames
        frames_to_try = ["main"] + [f for f in self.frames.keys() if f != "main"]
        
        for frame_id in frames_to_try:
            if frame_id not in self.frames:
                continue
                
            frame = self.frames[frame_id]
            for attempt in range(retry_attempts):
                try:
                    # Try to click on the body element
                    await frame.locator("body").click(position={'x': 0, 'y': 0}, timeout=1000)
                    logger.debug(f"Clicked body in frame '{frame_id}' to dismiss dropdown")
                    return True
                except Exception as e:
                    logger.debug(f"Attempt {attempt+1} to dismiss dropdown in frame '{frame_id}' failed: {e}")
                    
                    # Alternative approach - try pressing Escape key
                    if attempt == retry_attempts - 1:
                        try:
                            await self.page.keyboard.press("Escape")
                            logger.debug("Pressed Escape key to dismiss dropdown")
                            return True
                        except Exception as esc_e:
                            logger.debug(f"Failed to press Escape key: {esc_e}")
        
        logger.warning("Failed to dismiss dropdown after all attempts")
        return False 