"""Handles file upload actions using a strategy pattern."""
import logging
import asyncio
from playwright.async_api import Page, Frame
from typing import Optional, Dict, Any

from .base_handler import BaseActionHandler
from .upload_strategies import GreenhouseFileUploadStrategy, StandardFileUploadStrategy
from enterprise_job_agent.core.exceptions import ActionExecutionError
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager

class FileUploadHandler(BaseActionHandler):
    """Handles file input actions by delegating to appropriate strategies."""
    
    def __init__(self, browser_manager, form_interaction, element_selector, diagnostics_manager):
        # Pass correct arguments to BaseActionHandler
        super().__init__(browser_manager, form_interaction, element_selector)
        self.diagnostics_manager = diagnostics_manager # Store locally
        # Order matters: more specific strategies first
        self.strategies = [
            GreenhouseFileUploadStrategy(),
            StandardFileUploadStrategy() 
        ]
        self.logger = logging.getLogger(__name__) # Use standard logger

    async def execute(self, context) -> bool:
        """Executes a file upload action using the first applicable strategy."""
        selector = context.field_id
        file_path = context.field_value
        frame_id = context.frame_id
        page = self.browser_manager.get_page() # Needed by strategies

        if not page:
             self.logger.error("Page object not available for file upload.")
             return False
             
        # Check if file_path is empty or None - If so, skip gracefully
        if not file_path:
            self.logger.warning(f"No file path provided for selector '{selector}'. Skipping file upload.")
            return True # Treat as success (nothing to upload)

        if not selector:
            self.logger.error(f"Missing selector ('{selector}') for file upload.")
            return False

        self.logger.info(f"Attempting file upload for {selector} with file path: {file_path}")
        
        try:
            frame = await self._get_frame(frame_id)
            safe_selector = await self._sanitize_selector(selector)
            
            # Iterate through strategies
            for strategy in self.strategies:
                strategy_name = strategy.__class__.__name__
                self.logger.debug(f"Checking applicability of strategy: {strategy_name}")
                
                try:
                    if await strategy.can_handle(frame):
                        self.logger.info(f"Executing file upload using strategy: {strategy_name}")
                        # Pass necessary arguments to the strategy's upload method
                        success = await strategy.upload(page, frame, safe_selector, file_path)
                        if success:
                            self.logger.info(f"File upload successful using strategy: {strategy_name} for {safe_selector}")
                            return True
                        else:
                            self.logger.warning(f"Strategy {strategy_name} handled context but failed to upload for {safe_selector}. Trying next strategy.")
                    else:
                         self.logger.debug(f"Strategy {strategy_name} cannot handle the current context.")
                except Exception as strat_ex:
                    # Catch errors within a strategy's execution to allow fallback
                    self.logger.error(f"Error executing strategy {strategy_name} for {safe_selector}: {strat_ex}", exc_info=True)
                    self.logger.warning(f"Strategy {strategy_name} failed with an error. Trying next strategy.")
                    continue # Move to the next strategy

            # If loop completes without success
            self.logger.error(f"All file upload strategies failed for {safe_selector}")
            return False
            
        except ActionExecutionError as ae:
             # Handle errors from _get_frame or _sanitize_selector
             self.logger.error(f"ActionExecutionError during file upload setup for {selector}: {ae}")
             raise
        except Exception as e:
            # Catch any other unexpected errors during the setup or loop iteration logic
            self.logger.error(f"Unexpected error executing file upload for {selector}: {e}", exc_info=True)
            raise ActionExecutionError(f"Failed to execute file upload for '{selector}'") from e

    # Removed _check_if_greenhouse
    # Removed _is_element_hidden (moved to StandardFileUploadStrategy)
    # Removed _handle_greenhouse_upload 