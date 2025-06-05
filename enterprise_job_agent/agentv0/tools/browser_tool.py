import logging
import os
import json
from typing import Dict, Any, Optional, List, Tuple, Union
import asyncio
from playwright.async_api import async_playwright, Page, Browser, Playwright
import time

from agentv0.tools.base import BaseTool
from agentv0.page_analyzer import analyze_page_structure

class BrowserTool(BaseTool):
    """Tool for interacting with a web browser using Playwright.
    
    This tool provides a unified interface for all browser-related operations,
    including navigation, element interaction, and page analysis.
    """
    
    def __init__(self, headless: bool = True):
        """Initialize the browser tool.
        
        Args:
            headless: Whether to run the browser in headless mode
        """
        super().__init__(
            name="browser",
            description="Interacts with web pages through a browser"
        )
        self.headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._initialized = False
    
    async def _ensure_initialized(self) -> None:
        """Ensure the browser is initialized before use.
        
        This lazy initialization allows the browser to be created only when needed.
        """
        if not self._initialized:
            self.logger.info("Initializing browser...")
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                ]
            )
            
            context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            # Stealth mode - avoid detection
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {} };
            """)
            
            self._page = await context.new_page()
            self._initialized = True
            self.logger.info("Browser initialized successfully")
    
    async def close(self) -> Dict[str, Any]:
        """Close the browser and clean up resources.
        
        Returns:
            A dictionary with status information
        """
        if self._browser:
            await self._browser.close()
            self._browser = None
            
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
            
        self._page = None
        self._initialized = False
        self.logger.info("Browser closed")
        
        return {
            "success": True,
            "observation": "Browser closed successfully"
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute a browser operation based on the provided parameters.
        
        This is a dispatcher method that routes to the appropriate specialized method
        based on the 'action' parameter.
        
        Args:
            **kwargs: Must include 'action' key and action-specific parameters
            
        Returns:
            Result dictionary with 'success' and 'observation' keys
            
        Raises:
            ValueError: If 'action' is missing or invalid
        """
        if 'action' not in kwargs:
            raise ValueError("Missing required 'action' parameter")
            
        action = kwargs.pop('action')
        
        # Map action names to methods
        action_map = {
            'navigate': self.navigate,
            'find_element': self.find_element,
            'click_element': self.click_element,
            'fill_text_field': self.fill_text_field,
            'select_dropdown_option': self.select_dropdown_option,
            'upload_file': self.upload_file,
            'get_text': self.get_text,
            'get_html': self.get_html,
            'analyze_page_structure': self.analyze_page_structure,
            'check_element_state': self.check_element_state,
            'wait_for_navigation': self.wait_for_navigation,
            'close': self.close
        }
        
        if action not in action_map:
            raise ValueError(f"Invalid action: {action}. Valid actions are: {', '.join(action_map.keys())}")
            
        # Dispatch to the appropriate method
        return await action_map[action](**kwargs)
    
    async def navigate(self, url: str, timeout: int = 30000) -> Dict[str, Any]:
        """Navigate the browser to a URL.
        
        Args:
            url: The URL to navigate to
            timeout: Maximum time to wait for navigation in milliseconds
            
        Returns:
            Result dictionary with success status and current URL
        """
        await self._ensure_initialized()
        
        try:
            self.logger.info(f"Navigating to {url}")
            response = await self._page.goto(url, timeout=timeout, wait_until="networkidle")
            
            # Check for navigation errors
            if response and response.status >= 400:
                self.logger.warning(f"Navigation resulted in error status: {response.status}")
                return {
                    "success": False,
                    "observation": f"Navigation failed with status {response.status}",
                    "url": self._page.url,
                    "status": response.status
                }
                
            current_url = self._page.url
            self.logger.info(f"Successfully navigated to {current_url}")
            
            return {
                "success": True,
                "observation": f"Successfully navigated to page",
                "url": current_url
            }
            
        except Exception as e:
            self.logger.error(f"Navigation failed: {str(e)}")
            return {
                "success": False,
                "observation": f"Navigation failed: {str(e)}",
                "error": str(e)
            }
    
    async def find_element(self, selector: str, timeout: int = 10000) -> Dict[str, Any]:
        """Find an element on the page.
        
        Args:
            selector: CSS selector for the element
            timeout: Maximum time to wait for the element in milliseconds
            
        Returns:
            Result dictionary with success status and element info if found
        """
        await self._ensure_initialized()
        
        try:
            self.logger.debug(f"Searching for element: {selector}")
            element = await self._page.wait_for_selector(selector, timeout=timeout)
            
            if element:
                # Get basic element properties
                tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
                is_visible = await element.is_visible()
                is_enabled = await element.is_enabled() if tag_name in ['button', 'input', 'select', 'textarea'] else True
                
                self.logger.info(f"Found element: {selector} (tag: {tag_name}, visible: {is_visible}, enabled: {is_enabled})")
                
                return {
                    "success": True,
                    "observation": f"Element found: {selector}",
                    "tag_name": tag_name,
                    "is_visible": is_visible,
                    "is_enabled": is_enabled
                }
            else:
                # This branch is unlikely to execute due to the wait_for_selector behavior
                return {
                    "success": False,
                    "observation": f"Element not found: {selector}"
                }
                
        except Exception as e:
            self.logger.error(f"Failed to find element {selector}: {str(e)}")
            return {
                "success": False,
                "observation": f"Failed to find element: {str(e)}",
                "error": str(e)
            }
    
    async def click_element(self, selector: str, timeout: int = 10000, force: bool = False) -> Dict[str, Any]:
        """Click an element on the page.
        
        Args:
            selector: CSS selector for the element to click
            timeout: Maximum time to wait for the element in milliseconds
            force: Whether to force the click, bypassing actionability checks
            
        Returns:
            Result dictionary with success status
        """
        await self._ensure_initialized()
        
        try:
            self.logger.info(f"Attempting to click element: {selector}")
            
            # Wait for the element to be visible
            element = await self._page.wait_for_selector(selector, timeout=timeout, state="visible")
            
            if not element:
                return {
                    "success": False,
                    "observation": f"Element not found or not visible: {selector}"
                }
            
            # Check if element is actionable (unless force=True)
            if not force:
                is_enabled = await element.is_enabled()
                if not is_enabled:
                    return {
                        "success": False,
                        "observation": f"Element is disabled: {selector}"
                    }
            
            # Attempt to click
            await element.click(force=force, timeout=timeout)
            
            # Small delay to allow potential page interactions to start
            await asyncio.sleep(0.5)
            
            self.logger.info(f"Successfully clicked element: {selector}")
            return {
                "success": True,
                "observation": f"Successfully clicked element: {selector}"
            }
            
        except Exception as e:
            self.logger.error(f"Failed to click element {selector}: {str(e)}")
            return {
                "success": False,
                "observation": f"Failed to click element: {str(e)}",
                "error": str(e)
            }
    
    async def fill_text_field(self, selector: str, text: str, timeout: int = 10000) -> Dict[str, Any]:
        """Fill a text field with the provided text.
        
        Args:
            selector: CSS selector for the text field
            text: The text to enter
            timeout: Maximum time to wait for the element in milliseconds
            
        Returns:
            Result dictionary with success status
        """
        await self._ensure_initialized()
        
        try:
            self.logger.info(f"Attempting to fill text in element: {selector}")
            
            # Wait for the element to be visible
            element = await self._page.wait_for_selector(selector, timeout=timeout, state="visible")
            
            if not element:
                return {
                    "success": False,
                    "observation": f"Element not found or not visible: {selector}"
                }
            
            # Clear the field first
            await element.click(timeout=timeout)
            await element.focus()
            await self._page.keyboard.press("Control+A")
            await self._page.keyboard.press("Delete")
            
            # Type the new text
            await element.type(text, timeout=timeout)
            
            self.logger.info(f"Successfully filled text in element: {selector}")
            return {
                "success": True,
                "observation": f"Successfully filled text in element: {selector}"
            }
            
        except Exception as e:
            self.logger.error(f"Failed to fill text in element {selector}: {str(e)}")
            return {
                "success": False,
                "observation": f"Failed to fill text in element: {str(e)}",
                "error": str(e)
            }
    
    async def select_dropdown_option(self, selector: str, option_text: str, timeout: int = 10000) -> Dict[str, Any]:
        """Select an option from a dropdown by visible text.
        
        Args:
            selector: CSS selector for the select element
            option_text: The visible text of the option to select
            timeout: Maximum time to wait for the element in milliseconds
            
        Returns:
            Result dictionary with success status
        """
        await self._ensure_initialized()
        
        try:
            self.logger.info(f"Attempting to select option '{option_text}' from dropdown: {selector}")
            
            # Wait for the select element to be visible
            select_element = await self._page.wait_for_selector(selector, timeout=timeout, state="visible")
            
            if not select_element:
                return {
                    "success": False,
                    "observation": f"Select element not found or not visible: {selector}"
                }
            
            # Get all options to find a match
            options = await self._page.evaluate(f"""
                () => {{
                    const select = document.querySelector('{selector}');
                    if (!select) return [];
                    return Array.from(select.options).map(option => {{
                        return {{
                            value: option.value,
                            text: option.text,
                            selected: option.selected
                        }};
                    }});
                }}
            """)
            
            # Find option by text (case-insensitive)
            option_found = False
            option_value = None
            
            for option in options:
                if option['text'].lower() == option_text.lower():
                    option_found = True
                    option_value = option['value']
                    break
            
            if not option_found:
                return {
                    "success": False,
                    "observation": f"Option '{option_text}' not found in dropdown",
                    "available_options": [option['text'] for option in options]
                }
            
            # Select the option by value
            await self._page.select_option(selector, value=option_value)
            
            self.logger.info(f"Successfully selected option '{option_text}' from dropdown: {selector}")
            return {
                "success": True,
                "observation": f"Successfully selected option '{option_text}' from dropdown"
            }
            
        except Exception as e:
            self.logger.error(f"Failed to select option from dropdown {selector}: {str(e)}")
            return {
                "success": False,
                "observation": f"Failed to select option from dropdown: {str(e)}",
                "error": str(e)
            }
    
    async def upload_file(self, selector: str, file_path: str, timeout: int = 10000) -> Dict[str, Any]:
        """Upload a file using a file input element.
        
        Args:
            selector: CSS selector for the file input element
            file_path: Path to the file to upload
            timeout: Maximum time to wait for the element in milliseconds
            
        Returns:
            Result dictionary with success status
        """
        await self._ensure_initialized()
        
        try:
            self.logger.info(f"Attempting to upload file '{file_path}' to input: {selector}")
            
            # Verify file exists
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "observation": f"File not found: {file_path}"
                }
            
            # Wait for the file input to be present (note: file inputs are often hidden)
            element = await self._page.wait_for_selector(selector, timeout=timeout)
            
            if not element:
                return {
                    "success": False,
                    "observation": f"File input element not found: {selector}"
                }
            
            # Upload the file
            await element.set_input_files(file_path)
            
            self.logger.info(f"Successfully uploaded file to: {selector}")
            return {
                "success": True,
                "observation": f"Successfully uploaded file: {os.path.basename(file_path)}"
            }
            
        except Exception as e:
            self.logger.error(f"Failed to upload file to {selector}: {str(e)}")
            return {
                "success": False,
                "observation": f"Failed to upload file: {str(e)}",
                "error": str(e)
            }
    
    async def get_text(self, selector: str, timeout: int = 10000) -> Dict[str, Any]:
        """Get the text content of an element.
        
        Args:
            selector: CSS selector for the element
            timeout: Maximum time to wait for the element in milliseconds
            
        Returns:
            Result dictionary with success status and text content if found
        """
        await self._ensure_initialized()
        
        try:
            self.logger.debug(f"Getting text from element: {selector}")
            
            # Wait for the element to be present
            element = await self._page.wait_for_selector(selector, timeout=timeout)
            
            if not element:
                return {
                    "success": False,
                    "observation": f"Element not found: {selector}"
                }
            
            # Get the text content
            text = await element.text_content()
            text = text.strip() if text else ""
            
            self.logger.debug(f"Got text from {selector}: {text[:50]}...")
            return {
                "success": True,
                "observation": f"Successfully retrieved text from element",
                "text": text
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get text from {selector}: {str(e)}")
            return {
                "success": False,
                "observation": f"Failed to get text: {str(e)}",
                "error": str(e)
            }
    
    async def get_html(self, selector: Optional[str] = None, timeout: int = 10000) -> Dict[str, Any]:
        """Get the HTML content of an element or the entire page.
        
        Args:
            selector: CSS selector for the element (None for entire page)
            timeout: Maximum time to wait for the element in milliseconds
            
        Returns:
            Result dictionary with success status and HTML content
        """
        await self._ensure_initialized()
        
        try:
            if selector:
                self.logger.debug(f"Getting HTML from element: {selector}")
                
                # Wait for the element to be present
                element = await self._page.wait_for_selector(selector, timeout=timeout)
                
                if not element:
                    return {
                        "success": False,
                        "observation": f"Element not found: {selector}"
                    }
                
                # Get the outer HTML
                html = await element.evaluate("el => el.outerHTML")
            else:
                self.logger.debug("Getting HTML for entire page")
                html = await self._page.content()
            
            self.logger.debug(f"Successfully retrieved HTML content")
            return {
                "success": True,
                "observation": f"Successfully retrieved HTML content",
                "html": html
            }
            
        except Exception as e:
            context = f"from {selector}" if selector else "of page"
            self.logger.error(f"Failed to get HTML {context}: {str(e)}")
            return {
                "success": False,
                "observation": f"Failed to get HTML: {str(e)}",
                "error": str(e)
            }
    
    async def analyze_page_structure(self) -> Dict[str, Any]:
        """Analyze the current page structure to identify forms, fields, and other interactive elements.
        
        Returns:
            Result dictionary with success status and structured page analysis
        """
        await self._ensure_initialized()
        
        try:
            self.logger.info("Analyzing page structure")
            
            # Get the page HTML
            html_result = await self.get_html()
            if not html_result["success"]:
                return {
                    "success": False,
                    "observation": "Failed to get page HTML for analysis",
                    "error": html_result.get("error", "Unknown error")
                }
            
            # Get the current URL
            current_url = self._page.url
            
            # Use the page analyzer to analyze the structure
            analysis = await analyze_page_structure(html_result["html"], current_url)
            
            self.logger.info(f"Successfully analyzed page structure: found {len(analysis['elements'])} elements")
            return {
                "success": True,
                "observation": f"Successfully analyzed page structure",
                "elements": analysis["elements"],
                "url": current_url
            }
            
        except Exception as e:
            self.logger.error(f"Failed to analyze page structure: {str(e)}")
            return {
                "success": False,
                "observation": f"Failed to analyze page structure: {str(e)}",
                "error": str(e)
            }
    
    async def check_element_state(self, selector: str, state: str, timeout: int = 10000) -> Dict[str, Any]:
        """Check the state of an element (visible, enabled, checked).
        
        Args:
            selector: CSS selector for the element
            state: The state to check ('visible', 'enabled', 'checked')
            timeout: Maximum time to wait for the element in milliseconds
            
        Returns:
            Result dictionary with success status and state check result
        """
        await self._ensure_initialized()
        
        valid_states = ['visible', 'enabled', 'checked']
        if state not in valid_states:
            return {
                "success": False,
                "observation": f"Invalid state: {state}. Valid states are: {', '.join(valid_states)}"
            }
        
        try:
            self.logger.debug(f"Checking if element {selector} is {state}")
            
            # Wait for the element to be present
            element = await self._page.wait_for_selector(selector, timeout=timeout)
            
            if not element:
                return {
                    "success": False,
                    "observation": f"Element not found: {selector}"
                }
            
            # Check the requested state
            if state == 'visible':
                result = await element.is_visible()
            elif state == 'enabled':
                result = await element.is_enabled()
            elif state == 'checked':
                result = await element.is_checked()
            
            self.logger.debug(f"Element {selector} is{' ' if result else ' not '}{state}")
            return {
                "success": True,
                "observation": f"Element is{' ' if result else ' not '}{state}",
                "result": result
            }
            
        except Exception as e:
            self.logger.error(f"Failed to check element state: {str(e)}")
            return {
                "success": False,
                "observation": f"Failed to check element state: {str(e)}",
                "error": str(e)
            }
    
    async def wait_for_navigation(self, timeout: int = 30000) -> Dict[str, Any]:
        """Wait for navigation to complete.
        
        Args:
            timeout: Maximum time to wait for navigation in milliseconds
            
        Returns:
            Result dictionary with success status and new URL
        """
        await self._ensure_initialized()
        
        try:
            self.logger.info("Waiting for navigation to complete")
            
            # Wait for network to be idle
            await self._page.wait_for_load_state("networkidle", timeout=timeout)
            
            current_url = self._page.url
            self.logger.info(f"Navigation complete, current URL: {current_url}")
            
            return {
                "success": True,
                "observation": "Navigation complete",
                "url": current_url
            }
            
        except Exception as e:
            self.logger.error(f"Failed while waiting for navigation: {str(e)}")
            return {
                "success": False,
                "observation": f"Failed while waiting for navigation: {str(e)}",
                "error": str(e)
            }
    
    def _get_parameter_schema(self) -> Dict[str, Any]:
        """Define the schema for the parameters this tool accepts.
        
        Returns:
            A dictionary representing a JSONSchema for the parameters.
        """
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "navigate", "find_element", "click_element", "fill_text_field",
                        "select_dropdown_option", "upload_file", "get_text", "get_html",
                        "analyze_page_structure",
                        "check_element_state", "wait_for_navigation",
                        "close"
                    ],
                    "description": "The browser action to perform"
                },
                "url": {
                    "type": "string",
                    "description": "The URL to navigate to (for 'navigate' action)"
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for the target element"
                },
                "text": {
                    "type": "string",
                    "description": "Text to enter (for 'fill_text_field' action)"
                },
                "option_text": {
                    "type": "string",
                    "description": "Option text to select (for 'select_dropdown_option' action)"
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to upload (for 'upload_file' action)"
                },
                "state": {
                    "type": "string",
                    "enum": ["visible", "enabled", "checked"],
                    "description": "Element state to check (for 'check_element_state' action)"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Maximum time to wait in milliseconds",
                    "default": 10000
                },
                "force": {
                    "type": "boolean",
                    "description": "Whether to force the action, bypassing actionability checks",
                    "default": False
                }
            },
            "required": ["action"],
            "additionalProperties": False
        } 