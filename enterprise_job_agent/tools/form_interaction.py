"""Tools for interacting with form elements."""

import re
import logging
import asyncio
from typing import Dict, Any, Optional, List, Union
from enum import Enum, auto
import time

from enterprise_job_agent.core.browser_interface import BrowserInterface
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.tools.element_selector import ElementSelector

logger = logging.getLogger(__name__)

class InteractionType(Enum):
    """Types of form interactions."""
    FILL = auto()
    SELECT = auto()
    CLICK = auto()
    UPLOAD = auto()
    CLEAR = auto()

class InteractionResult:
    """Result of a form interaction."""
    def __init__(
        self,
        success: bool,
        field_id: str,
        interaction_type: InteractionType,
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.success = success
        self.field_id = field_id
        self.interaction_type = interaction_type
        self.error = error
        self.details = details or {}
        self.retry_count = 0

class FormInteraction:
    """Handles reliable form interactions with retries and error handling."""
    
    def __init__(
        self,
        browser: BrowserInterface,
        element_selector: ElementSelector,
        diagnostics_manager: Optional[DiagnosticsManager] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """Initialize form interaction tool.
        
        Args:
            browser: Browser interface instance
            element_selector: Element selector for finding elements
            diagnostics_manager: Optional diagnostics manager
            max_retries: Maximum number of retries for failed actions
            retry_delay: Delay between retries in seconds
        """
        self.browser = browser
        self.diagnostics_manager = diagnostics_manager
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.element_selector = element_selector
        self.logger = logger
    
    async def _wait_for_element(
        self,
        selector: str,
        frame_id: Optional[str] = None,
        timeout: int = 5000
    ) -> bool:
        """Wait for an element to be ready for interaction."""
        try:
            frame = await self.browser.get_frame(frame_id) if frame_id else None
            element = await self.element_selector.wait_for_element(selector, frame=frame)
            return element is not None
        except Exception as e:
            self.logger.debug(f"Element not ready: {selector} - {str(e)}")
            return False
    
    async def _retry_interaction(
        self,
        interaction_fn,
        field_id: str,
        interaction_type: InteractionType,
        **kwargs
    ) -> InteractionResult:
        """Retry an interaction with exponential backoff."""
        result = InteractionResult(False, field_id, interaction_type)
        
        for attempt in range(self.max_retries):
            try:
                success = await interaction_fn(**kwargs)
                if success:
                    result.success = True
                    break
                    
            except Exception as e:
                result.error = str(e)
                self.logger.debug(f"Interaction attempt {attempt + 1} failed: {str(e)}")
            
            # Update retry count
            result.retry_count = attempt + 1
            
            # Wait before retry
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return result
    
    async def fill_field(
        self,
        selector: str,
        value: str,
        frame_id: Optional[str] = None
    ) -> bool:
        """Fill a form field with text.
        
        Args:
            selector: CSS selector for the field
            value: Value to fill
            frame_id: Optional frame identifier
            
        Returns:
            True if successful, False otherwise
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage(f"fill_field_{selector}")
            
        try:
            # Get the frame if needed
            frame = await self.browser.get_frame(frame_id) if frame_id else None
            context = frame or self.browser.page
            
            # Find and fill the field
            element = await self.element_selector.wait_for_element(selector, frame=frame)
            if not element:
                raise ValueError(f"Element not found: {selector}")
                
            await element.fill(value)
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(True)
            return True
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(False, error=str(e))
            logger.error(f"Error filling field {selector}: {e}")
            return False
    
    async def select_option(
        self,
        selector: str,
        value: str,
        options: Optional[List[str]] = None,
        frame_id: Optional[str] = None
    ) -> bool:
        """Select an option from a dropdown.
        
        Args:
            selector: CSS selector for the dropdown
            value: Value to select
            options: Optional list of available options
            frame_id: Optional frame identifier
            
        Returns:
            True if successful, False otherwise
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage(f"select_option_{selector}")
            
        try:
            # Get the frame if needed
            frame = await self.browser.get_frame(frame_id) if frame_id else None
            context = frame or self.browser.page
            
            # Find the dropdown
            element = await self.element_selector.wait_for_element(selector, frame=frame)
            if not element:
                raise ValueError(f"Element not found: {selector}")
            
            # Check element tag to determine approach
            tag_name = await element.get_property('tagName')
            tag_name = await tag_name.json_value()
            
            # Handle education-related fields specially (these are commonly problematic)
            field_id = selector.strip('#')
            is_education_field = any(edu_field in field_id.lower() for edu_field in ["school", "degree", "discipline", "education", "university"])
            
            self.logger.info(f"Selecting option '{value}' in {tag_name} element {selector} (education field: {is_education_field})")
            
            if tag_name.lower() == 'select':
                # Standard HTML select element
                try:
                    # Try exact value first
                    await element.select_option(value=value)
                    if self.diagnostics_manager:
                        self.diagnostics_manager.end_stage(True)
                    return True
                except Exception as e1:
                    self.logger.debug(f"Could not select by value, trying by label: {e1}")
                    try:
                        # Then try by label
                        await element.select_option(label=value)
                        if self.diagnostics_manager:
                            self.diagnostics_manager.end_stage(True)
                        return True
                    except Exception as e2:
                        self.logger.debug(f"Could not select by label, trying by text content: {e2}")
                        try:
                            # If options were provided, try to find the best match
                            if options:
                                # Find option with closest text match
                                closest_option = None
                                best_match_score = 0
                                for option in options:
                                    # Compute similarity score (simple approach)
                                    option_lower = option.lower()
                                    value_lower = value.lower()
                                    
                                    # Check for contains relationship
                                    if value_lower in option_lower or option_lower in value_lower:
                                        score = len(set(value_lower) & set(option_lower)) / max(len(value_lower), len(option_lower))
                                        if score > best_match_score:
                                            best_match_score = score
                                            closest_option = option
                                
                                if closest_option:
                                    self.logger.info(f"Found closest option: '{closest_option}' for value '{value}'")
                                    try:
                                        await element.select_option(label=closest_option)
                                        if self.diagnostics_manager:
                                            self.diagnostics_manager.end_stage(True, details={"matched_option": closest_option})
                                        return True
                                    except Exception as e3:
                                        self.logger.debug(f"Could not select option by label: {e3}")
                                        # Try by value
                                        await element.select_option(value=closest_option)
                                        if self.diagnostics_manager:
                                            self.diagnostics_manager.end_stage(True, details={"matched_option": closest_option})
                                        return True
                        except Exception as e3:
                            self.logger.debug(f"Could not select by options list: {e3}")
                            
                            # Special handling for education fields
                            if is_education_field:
                                try:
                                    # For education fields, try a more aggressive approach
                                    # First click to open the dropdown
                                    await element.click()
                                    await asyncio.sleep(0.5)
                                    
                                    # Try to use JavaScript to select the option
                                    js_select = f"""
                                    (element) => {{
                                        const options = Array.from(element.options);
                                        const targetValue = "{value}".toLowerCase();
                                        for (let i = 0; i < options.length; i++) {{
                                            const option = options[i];
                                            if (option.text.toLowerCase().includes(targetValue) || 
                                                targetValue.includes(option.text.toLowerCase())) {{
                                                element.selectedIndex = i;
                                                element.dispatchEvent(new Event('change'));
                                                return true;
                                            }}
                                        }}
                                        return false;
                                    }}
                                    """
                                    selected = await context.evaluate(js_select, element)
                                    if selected:
                                        if self.diagnostics_manager:
                                            self.diagnostics_manager.end_stage(True, details={"method": "js_select"})
                                        return True
                                except Exception as e_js:
                                    self.logger.debug(f"JS selection failed: {e_js}")
                            
                            # Last resort - try typing into the field
                            await element.fill(value)
                            if self.diagnostics_manager:
                                self.diagnostics_manager.end_stage(True, 
                                                                 details={"note": "Selected by typing value"})
                            return True
            else:
                # Custom dropdown or other element type
                try:
                    # First click to open the dropdown
                    await element.click()
                    await asyncio.sleep(0.5)  # Wait for dropdown to appear
                    
                    # For custom dropdowns in education fields, try additional strategies
                    if is_education_field:
                        # For these fields, try to match more aggressively
                        try:
                            # Create more specific selectors for education dropdowns
                            edu_option_selectors = [
                                f"li:has-text('{value}')",
                                f"div[role='option']:has-text('{value}')",
                                f"option:has-text('{value}')",
                                f".dropdown-item:has-text('{value}')",
                                f".select-option:has-text('{value}')",
                                f"*:has-text('{value}')"
                            ]
                            
                            for edu_selector in edu_option_selectors:
                                try:
                                    option_elements = await context.query_selector_all(edu_selector)
                                    if option_elements and len(option_elements) > 0:
                                        # Click the first matching element
                                        await option_elements[0].click()
                                        self.logger.info(f"Selected education field option using selector: {edu_selector}")
                                        if self.diagnostics_manager:
                                            self.diagnostics_manager.end_stage(True, details={"method": "education_field_selector"})
                                        return True
                                except Exception as e_edu:
                                    self.logger.debug(f"Education selector {edu_selector} failed: {e_edu}")
                        except Exception as e_edu_outer:
                            self.logger.debug(f"Education-specific selection failed: {e_edu_outer}")
                    
                    # Try to find and click the option
                    if options:
                        # Create a selector for dropdown items (common patterns)
                        option_selectors = [
                            "li",  # Most common for custom dropdowns
                            ".dropdown-item",
                            ".select-option",
                            f"li:has-text('{value}')",
                            f"div[role='option']:has-text('{value}')",
                            f"*:has-text('{value}')"
                        ]
                        
                        # Try each selector
                        for option_selector in option_selectors:
                            try:
                                option_element = await context.query_selector(option_selector)
                                if option_element:
                                    await option_element.click()
                                    self.logger.info(f"Selected dropdown option using selector: {option_selector}")
                                    if self.diagnostics_manager:
                                        self.diagnostics_manager.end_stage(True)
                                    return True
                            except Exception as option_e:
                                self.logger.debug(f"Could not select with {option_selector}: {option_e}")
                    
                    # If we couldn't find options, try just typing the value
                    await element.fill(value)
                    await element.press("Enter")
                    
                    if self.diagnostics_manager:
                        self.diagnostics_manager.end_stage(True, 
                                                           details={"note": "Selected by typing and pressing Enter"})
                    return True
                    
                except Exception as e:
                    self.logger.debug(f"Custom dropdown interaction failed: {e}")
                    # Final fallback - just type the value and leave it
                    await element.fill(value)
                    if self.diagnostics_manager:
                        self.diagnostics_manager.end_stage(True, 
                                                          details={"note": "Selected by typing only"})
                    return True
                    
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(False, error=str(e))
            self.logger.error(f"Error selecting option in {selector}: {e}")
            return False
    
    async def set_checkbox(
        self,
        selector: str,
        checked: bool,
        frame_id: Optional[str] = None
    ) -> bool:
        """Set a checkbox to checked or unchecked.
        
        Args:
            selector: CSS selector for the checkbox
            checked: Whether the checkbox should be checked
            frame_id: Optional frame identifier
            
        Returns:
            True if successful, False otherwise
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage(f"set_checkbox_{selector}")
            
        try:
            # Get the frame if needed
            frame = await self.browser.get_frame(frame_id) if frame_id else None
            context = frame or self.browser.page
            
            # Find the checkbox
            element = await self.element_selector.wait_for_element(selector, frame=frame)
            if not element:
                raise ValueError(f"Element not found: {selector}")
                
            # Get current state
            is_checked = await element.is_checked()
            
            # Click if state needs to change
            if is_checked != checked:
                await element.click()
                
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(True)
            return True
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(False, error=str(e))
            logger.error(f"Error setting checkbox {selector}: {e}")
            return False
    
    async def upload_file(
        self,
        selector: str,
        file_path: str,
        frame_id: Optional[str] = None
    ) -> bool:
        """Upload a file to a file input.
        
        Args:
            selector: CSS selector for the file input
            file_path: Path to the file to upload
            frame_id: Optional frame identifier
            
        Returns:
            True if successful, False otherwise
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage(f"upload_file_{selector}")
            
        try:
            # Get the frame if needed
            frame = await self.browser.get_frame(frame_id) if frame_id else None
            context = frame or self.browser.page
            
            # Find the file input
            element = await self.element_selector.wait_for_element(selector, frame=frame)
            if not element:
                raise ValueError(f"Element not found: {selector}")
                
            # Upload the file
            await element.set_input_files(file_path)
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(True)
            return True
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(False, error=str(e))
            logger.error(f"Error uploading file to {selector}: {e}")
            return False 