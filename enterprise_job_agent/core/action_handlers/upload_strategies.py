"""Defines strategies for handling file uploads in different contexts (e.g., specific platforms)."""
import logging
import asyncio
from abc import ABC, abstractmethod
from playwright.async_api import Page, Frame

# Assuming ActionContext might be needed later, though not directly used now
# from enterprise_job_agent.core.models import ActionContext 

logger = logging.getLogger(__name__)

class FileUploadStrategy(ABC):
    """Abstract base class for file upload strategies."""

    @abstractmethod
    async def can_handle(self, frame: Frame) -> bool:
        """Determines if this strategy can handle the upload in the given frame context."""
        pass

    @abstractmethod
    async def upload(self, page: Page, frame: Frame, input_selector: str, file_path: str) -> bool:
        """Executes the file upload using this strategy's logic."""
        pass

class GreenhouseFileUploadStrategy(FileUploadStrategy):
    """Handles file uploads specifically for Greenhouse forms."""
    
    async def can_handle(self, frame: Frame) -> bool:
        """Checks if the current frame seems to be part of a Greenhouse form."""
        try:
            # Logic moved from FileUploadHandler._check_if_greenhouse
            is_greenhouse = await frame.evaluate("""() => {
                    return window.location.href.includes('greenhouse.io') || 
                           document.querySelector('meta[name="greenhouse-form"]') !== null ||
                           document.querySelector('form[action*="greenhouse"]') !== null ||
                           document.querySelector('[data-greenhouse-job-id]') !== null;
                }""")
            if is_greenhouse:
                logger.debug("Detected Greenhouse context.")
            return bool(is_greenhouse)
        except Exception as e:
            logger.debug(f"Error checking for Greenhouse context: {e}")
            return False

    async def upload(self, page: Page, frame: Frame, input_selector: str, file_path: str) -> bool:
        """Attempts file upload using common Greenhouse patterns (finding associated visible button)."""
        logger.debug(f"Attempting Greenhouse-specific upload for {input_selector}")
        try:
            # Logic moved from FileUploadHandler._handle_greenhouse_upload
            selector_id_part = input_selector.replace('#', '')
            # Common patterns for visible buttons linked to hidden file inputs in Greenhouse
            upload_button_selectors = [
                f"label[for='{selector_id_part}']",
                f"button[data-qa='attach-button']", # Common data-qa attribute
                f"button:has-text('Attach')",
                f"button:has-text('Upload')",
                f"{input_selector} ~ label.upload-button",
                f"{input_selector} ~ .upload-file-button",
                f"{input_selector} ~ button.btn-file",
                f"div[data-input='{selector_id_part}'] button" # Another common pattern
            ]
            
            for btn_selector in upload_button_selectors:
                try:
                    # Use locator for better waiting and interaction
                    upload_locator = frame.locator(btn_selector).first # Take first match
                    
                    # Check if the button is visible before attempting interaction
                    await upload_locator.wait_for(state='visible', timeout=2000) 
                    
                    logger.info(f"Found visible Greenhouse upload button: {btn_selector}")
                    # Use page.expect_file_chooser with the click action
                    async with page.expect_file_chooser(timeout=5000) as fc_info:
                        await upload_locator.click()
                        logger.info(f"Clicked Greenhouse upload button: {btn_selector}")
                    
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(file_path)
                    logger.info(f"Set file path '{file_path}' via Greenhouse button strategy.")
                    await asyncio.sleep(2) # Longer wait for Greenhouse uploads
                    return True
                except Exception as e:
                    logger.debug(f"Greenhouse button selector {btn_selector} check/interaction failed: {e}")
                    continue # Try next selector
            
            logger.warning(f"Greenhouse strategy: Could not find or interact with a suitable upload button for {input_selector}")
            return False
        except Exception as e:
            logger.error(f"Error during Greenhouse upload strategy execution for {input_selector}: {e}")
            return False

class StandardFileUploadStrategy(FileUploadStrategy):
    """Handles standard file uploads for visible or hidden inputs."""
    
    async def can_handle(self, frame: Frame) -> bool:
        """This is the default strategy, so it can always handle."""
        return True # Default strategy

    async def upload(self, page: Page, frame: Frame, input_selector: str, file_path: str) -> bool:
        """Executes standard file upload logic."""
        logger.debug(f"Attempting standard upload strategy for {input_selector}")
        # Logic moved from FileUploadHandler.execute
        
        # Check visibility first
        is_hidden = await self._is_element_hidden(frame, input_selector)
        
        # Strategy 2 (from original handler): Standard visible file input
        if not is_hidden:
            try:
                logger.debug(f"Standard strategy: Attempting upload for visible input {input_selector}")
                # Some inputs might need an activation click
                try:
                    await frame.locator(input_selector).click(timeout=2000)
                    logger.debug(f"Standard strategy: Clicked visible file input {input_selector}")
                except Exception:
                    logger.debug(f"Standard strategy: Could not click visible input {input_selector} (might be normal). Proceeding.")
                
                await frame.locator(input_selector).set_input_files(file_path, timeout=10000)
                logger.info(f"Standard strategy: Successfully set file for visible input {input_selector}")
                await asyncio.sleep(1) # Allow time for potential UI updates
                return True
            except Exception as e:
                logger.warning(f"Standard strategy: Visible upload failed for {input_selector}: {e}. Trying hidden input approach.")
                # Fall through to hidden input logic if visible fails
        
        # Strategy 3 (from original handler): Direct hidden file input
        # This also catches the case where the visible check failed above
        try:
            logger.debug(f"Standard strategy: Attempting direct upload for hidden/unclickable input {input_selector}")
            await frame.locator(input_selector).set_input_files(file_path, timeout=10000)
            logger.info(f"Standard strategy: Successfully set file directly for {input_selector}")
            await asyncio.sleep(1)
            return True
        except Exception as e:
            logger.warning(f"Standard strategy: Direct upload failed for {input_selector}: {e}. Trying visibility toggle.")

        # Strategy 4 (from original handler): Make hidden input visible temporarily
        restore_func_name = f"__restore_{input_selector.replace('#', '').replace('-', '')}"
        try:
            logger.info(f"Standard strategy: Attempting to make hidden file input {input_selector} visible temporarily")
            # Javascript to make element visible
            await frame.evaluate(f"""(selector) => {{
                const el = document.querySelector(selector);
                if (el) {{
                    const originalStyles = {{
                        display: el.style.display,
                        visibility: el.style.visibility,
                        position: el.style.position,
                        top: el.style.top,
                        left: el.style.left,
                        zIndex: el.style.zIndex
                    }};
                    el.style.display = 'block';
                    el.style.visibility = 'visible';
                    el.style.position = 'fixed'; // Bring to front if needed
                    el.style.top = '0';
                    el.style.left = '0';
                    el.style.zIndex = '9999'; // High z-index
                    window['{restore_func_name}'] = () => {{
                        el.style.display = originalStyles.display;
                        el.style.visibility = originalStyles.visibility;
                        el.style.position = originalStyles.position;
                        el.style.top = originalStyles.top;
                        el.style.left = originalStyles.left;
                        el.style.zIndex = originalStyles.zIndex;
                        delete window['{restore_func_name}']; // Clean up
                    }};
                }}
            }}""", input_selector)
            
            # Try set_input_files again on the now-visible element
            await frame.locator(input_selector).set_input_files(file_path, timeout=10000)
            logger.info(f"Standard strategy: Successfully set file for temporarily visible input {input_selector}")
            await asyncio.sleep(1)
            # Restore original styles
            await self._restore_styles(frame, restore_func_name)
            return True
        except Exception as e2:
            logger.error(f"Standard strategy: Failed to set file for {input_selector} even after making it visible: {e2}")
            # Attempt restore anyway if function exists
            await self._restore_styles(frame, restore_func_name)
            return False # Failed
            
    async def _is_element_hidden(self, frame: Frame, selector: str) -> bool:
         """Checks if an element is hidden via CSS or lack of offsetParent."""
         # Logic moved from FileUploadHandler._is_element_hidden
         try:
            is_hidden = await frame.evaluate("""(selector) => {
                const el = document.querySelector(selector);
                // Check for display:none, visibility:hidden, or type=file without offsetParent (common hidden pattern)
                if (!el) return true;
                const style = getComputedStyle(el);
                return style.display === 'none' || style.visibility === 'hidden' || (el.type === 'file' && !el.offsetParent);
            }""", selector)
            if is_hidden:
                logger.debug(f"Element {selector} determined to be hidden.")
            else:
                 logger.debug(f"Element {selector} determined to be visible.")
            return bool(is_hidden)
         except Exception as e:
             logger.warning(f"Error checking visibility for {selector}: {e}. Assuming hidden.")
             return True # Assume hidden if check fails
             
    async def _restore_styles(self, frame: Frame, restore_func_name: str):
        """Calls the JS function to restore original element styles."""
        try:
            await frame.evaluate(f"typeof window['{restore_func_name}'] === 'function' && window['{restore_func_name}']()")
            logger.debug(f"Restored original styles using {restore_func_name}")
        except Exception as e:
             logger.warning(f"Could not restore styles using {restore_func_name}: {e}")
             # Ignore errors during cleanup

# Standard strategy will be added next. 