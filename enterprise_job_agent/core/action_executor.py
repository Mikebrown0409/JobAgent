"""Action executor for job application system - Refactored Dispatcher."""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple, Union
import os
import difflib
import re
import random
import time
import traceback
from dataclasses import dataclass

from playwright.async_api import Page, Frame, Locator, Error

# Import the exception from the new location
from enterprise_job_agent.core.exceptions import ActionExecutionError, FrameNotFoundError
from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.tools.form_interaction import FormInteraction
from enterprise_job_agent.tools.element_selector import ElementSelector
from enterprise_job_agent.core.action_strategy_selector import ActionStrategySelector

# Action Handlers
# Assuming imports will work once base_handler issue resolved
from .action_handlers.base_handler import BaseActionHandler
from .action_handlers.text_handler import TextActionHandler
from .action_handlers.select_handler import SelectActionHandler
from .action_handlers.click_handler import ClickHandler
from .action_handlers.checkbox_handler import CheckboxHandler
from .action_handlers.fileupload_handler import FileUploadHandler
from .action_handlers.typeahead_handler import TypeaheadActionHandler

logger = logging.getLogger(__name__)

@dataclass
class TypeaheadAction:
    """Data structure for typeahead actions with AI support."""
    field_name: str  # Name of the field for logging
    value: str  # Value to set
    selector: Optional[str] = None  # CSS selector (can be determined later)
    field_type: Optional[str] = None  # Type of field (school, degree, etc.)
    profile_data: Optional[Dict[str, Any]] = None  # User profile data for context
    frame_id: Optional[str] = None  # Frame ID if not in main frame

@dataclass
class ActionContext:
    """Context for an action execution."""
    field_id: str  # Can be a selector, or a conceptual ID if type is 'click' and using fallback_text
    field_type: str # e.g., "text", "select", "click", "checkbox", "file"
    field_value: Any # Value to fill/select, or None for click
    frame_id: Optional[str] = None
    options: Optional[Dict[str, Any]] = None # Additional options if needed (e.g., field_purpose, name)
    fallback_text: Optional[str] = None # Text content to use as fallback (e.g., button text)
    field_name: Optional[str] = None # Original field name for context
    profile_data: Optional[Dict[str, Any]] = None # User profile data (less likely needed here)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the ActionContext object to a dictionary for serialization."""
        # Use dataclasses.asdict for robust conversion if available and suitable
        # Otherwise, manually construct the dictionary
        return {
            "field_id": self.field_id,
            "field_type": self.field_type,
            "field_value": self.field_value,
            "frame_id": self.frame_id,
            "options": self.options,
            "fallback_text": self.fallback_text,
            "field_name": self.field_name,
            "profile_data": self.profile_data,
        }

class ActionExecutor:
    """Refactored Action Executor - Dispatches actions to specialized handlers."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        form_interaction: FormInteraction,
        element_selector: ElementSelector,
        strategy_selector: ActionStrategySelector,
        diagnostics_manager: DiagnosticsManager,
        llm: Any, # Added llm dependency for strategy selector if needed internally
        test_mode: bool = False,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize the action executor and its handlers."""
        self.browser_manager = browser_manager
        self.form_interaction = form_interaction # Pass to handlers
        self.element_selector = element_selector # Pass to handlers
        self.strategy_selector = strategy_selector
        self.diagnostics_manager = diagnostics_manager
        self.logger = logger or logging.getLogger(__name__)
        self.test_mode = test_mode # Track test mode if needed at executor level
        self.llm = llm # Store LLM instance

        # Instantiate handlers, passing necessary dependencies
        common_handler_args = {
            'browser_manager': self.browser_manager,
            'form_interaction': self.form_interaction,
            'element_selector': self.element_selector,
        }
        
        # Separate instantiation for handlers requiring strategy_selector
        strategy_handler_args = {
            **common_handler_args,
            'strategy_selector': self.strategy_selector,
            'diagnostics_manager': self.diagnostics_manager
        }
        
        # Base handlers (no strategy selector needed)
        file_handler = FileUploadHandler(
            browser_manager=self.browser_manager,
            form_interaction=self.form_interaction,
            element_selector=self.element_selector,
            diagnostics_manager=self.diagnostics_manager
        )
        click_handler = ClickHandler(
            browser_interface=self.browser_manager,
            form_interaction=self.form_interaction,
            element_selector=self.element_selector,
            diagnostics_manager=self.diagnostics_manager
        )
        checkbox_handler = CheckboxHandler(
            browser_interface=self.browser_manager,
            element_selector=self.element_selector,
            form_interaction=self.form_interaction,
            diagnostics_manager=self.diagnostics_manager
        )
        
        # Strategy-aware handlers
        text_handler = TextActionHandler(**strategy_handler_args)
        select_handler = SelectActionHandler(**strategy_handler_args)
        typeahead_handler = TypeaheadActionHandler(**strategy_handler_args)

        # Primary handler mapping based on expected base field types
        self.handlers: Dict[str, BaseActionHandler] = {
            'text': text_handler,
            'email': text_handler,
            'textarea': text_handler,
            'phone': text_handler,
            'url': text_handler,
            'password': text_handler,
            'number': text_handler,
            'date': text_handler,
            'select': select_handler,
            'click': click_handler,
            'checkbox': checkbox_handler,
            'radio': checkbox_handler,
            'typeahead': typeahead_handler,
            'autocomplete': typeahead_handler,
            'combobox': typeahead_handler,
            'file': file_handler,
            'upload': file_handler,
            'resume': file_handler, # Explicitly map resume/cover_letter to file handler
            'cover_letter': file_handler,
            # Add mappings for semantic types identified by ProfileAdapterAgent
            'school': typeahead_handler, # Schools often use typeahead/autocomplete
            'location': typeahead_handler, # Locations usually use typeahead
            'degree': select_handler, # Degrees are often standard dropdowns
            'discipline': select_handler, # Disciplines are often standard dropdowns
            'gender': select_handler, # Demographics are usually dropdowns or radio groups
            'hispanic': select_handler, 
            'race': select_handler,
            'ethnicity': select_handler,
            'veteran': select_handler,
            'disability': select_handler,
            # Add other potential semantic types here if needed
            'demographic': select_handler,
            'button': click_handler, # Use ClickHandler for buttons
        }
        
        self.logger.info(f"ActionExecutor initialized with handlers. Test mode: {self.test_mode}")
        # Remove test_mode setting from FormInteraction if it exists
        # if self.form_interaction and hasattr(self.form_interaction, 'set_test_mode'):
        #      self.form_interaction.set_test_mode(self.test_mode)

    def set_test_mode(self, test_mode: bool):
        """Set test mode (might affect underlying interaction tool)."""
        self.test_mode = test_mode
        self.logger.info(f"ActionExecutor test mode set to: {self.test_mode}")
        # Propagate test mode to FormInteraction if needed
        # if self.form_interaction and hasattr(self.form_interaction, 'set_test_mode'):
        #      self.form_interaction.set_test_mode(self.test_mode)
        
    def _get_handler(self, field_type: str) -> Optional[BaseActionHandler]:
        """Get the appropriate handler for a given field type."""
        # Normalize field_type to lowercase for robust matching
        normalized_type = field_type.lower() if field_type else 'text' 
        handler = self.handlers.get(normalized_type)
        
        if not handler:
             # Fallback to text handler for unknown types
             self.logger.warning(f"No specific handler for field type '{normalized_type}' (original: '{field_type}'). Falling back to TextActionHandler.")
             handler = self.handlers.get('text') # Ensure 'text' handler exists
        return handler

    async def execute_action(self, context: ActionContext) -> bool:
        """Dispatch the action execution to the appropriate specialized handler."""
        if not context:
            self.logger.error("Cannot execute action: Context is None")
            return False

        field_type = context.field_type or "unknown"
        log_target = f"selector '{context.field_id}'" if context.field_id else f"text '{context.fallback_text}'"
        self.logger.info(f"Attempting action type '{field_type}' for {log_target}")
        
        handler = self._get_handler(field_type)
        if not handler:
             # This case should be rare due to the fallback in _get_handler
             self.logger.error(f"Could not find any handler (including fallback) for field type '{field_type}'")
             return False
             
        try:
            # Log start with diagnostics manager if available
            if self.diagnostics_manager:
                # Use context.__dict__ for logging to avoid issues if context has complex types
                self.diagnostics_manager.start_action(context.field_type, context.__dict__) # Log context details
                
            self.logger.debug(f"EXECUTOR_CONTEXT_PASS: Passing context object id={id(context)} with field_id='{context.field_id}' to handler {type(handler).__name__}")

            # Execute the action using the chosen handler
            success = await handler.execute(context)
            
            # Log end result with diagnostics manager
            if self.diagnostics_manager:
                self.diagnostics_manager.end_action(success)
                
            if success:
                 self.logger.info(f"Action '{field_type}' for {log_target} SUCCEEDED")
            else:
                 # Errors should ideally be raised by handlers, but log failure if bool is returned
                 self.logger.error(f"Action '{field_type}' for {log_target} FAILED (Handler returned False)")
                 
            return success

        except ActionExecutionError as ae:
             # Log known action errors raised by handlers
             error_message = f"Action '{field_type}' for {log_target} FAILED: {ae}"
             self.logger.error(error_message)
             if self.diagnostics_manager:
                 self.diagnostics_manager.end_action(False, error=str(ae))
             # Re-raise for potential handling by CrewManager/ErrorRecoveryAgent
             raise
        except Exception as e:
            # Log unexpected errors
            error_message = f"Unexpected error during action '{field_type}' for {log_target}: {e}"
            self.logger.error(error_message)
            self.logger.error(traceback.format_exc())
            if self.diagnostics_manager:
                self.diagnostics_manager.end_action(False, error=error_message)
            # Wrap in ActionExecutionError before re-raising
            raise ActionExecutionError(error_message) from e

    async def execute_form_actions(self, actions: List[Union[Dict[str, Any], ActionContext]], stop_on_error: bool = False) -> Dict[str, Any]:
        """Execute a list of form actions using the dispatcher.
        
        Args:
            actions: List of action dictionaries or ActionContext objects.
            stop_on_error: Whether to stop execution on the first error.
            
        Returns:
            Dict with execution statistics.
        """
        self.logger.info(f"Executing {len(actions)} form actions using handler dispatch.")
        success_count = 0
        failure_count = 0
        total_actions = len(actions)
        start_time = time.time() # Import time needed

        # Diagnostics for the overall form execution
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage("execute_form_actions")

        for i, action_data in enumerate(actions):
            context: Optional[ActionContext] = None
            try:
                # Create ActionContext if input is a dict
                if isinstance(action_data, dict):
                     # Basic validation/creation
                     context = ActionContext(
                         field_id=action_data.get("field_id", ""),
                         field_type=action_data.get("field_type", "text"), # Default to text?
                         field_value=action_data.get("value"),
                         frame_id=action_data.get("frame_id"),
                         options=action_data.get("options", {}),
                         fallback_text=action_data.get("fallback_text"),
                         field_name=action_data.get("field_name")
                     )
                elif isinstance(action_data, ActionContext):
                     context = action_data
                else:
                     raise TypeError(f"Invalid action data type: {type(action_data)}")

                log_target = f"selector '{context.field_id}'" if context.field_id else f"text '{context.fallback_text}'"
                self.logger.info(f"Executing action {i+1}/{total_actions}: Type '{context.field_type}' for {log_target}")

                # Execute single action via the dispatcher
                success = await self.execute_action(context)
                
                if success:
                    success_count += 1
                else:
                    # execute_action should raise ActionExecutionError on failure
                    # This path might not be hit if handlers always raise
                    failure_count += 1
                    self.logger.warning(f"Action {i+1} reported failure (returned False) for {log_target}")
                    if stop_on_error:
                        self.logger.warning(f"Stopping execution due to failure (stop_on_error=True)")
                        break

            except ActionExecutionError as ae:
                 # Handle errors raised by execute_action or handlers
                 failure_count += 1
                 log_target_err = f"'{context.field_id if context else 'N/A'}'" 
                 self.logger.error(f"Action {i+1} failed for {log_target_err} with error: {ae}")
                 if stop_on_error:
                     self.logger.warning(f"Stopping execution due to error (stop_on_error=True)")
                     break
            except Exception as e:
                 # Catch unexpected errors during context creation or execution
                 failure_count += 1
                 log_target_err = f"'{context.field_id if context else 'N/A'}'" 
                 self.logger.error(f"Unexpected exception during action {i+1} for {log_target_err}: {e}", exc_info=True)
                 if stop_on_error:
                     self.logger.warning(f"Stopping execution due to unexpected error (stop_on_error=True)")
                     break
                     
            # Small delay between actions (optional)
            await asyncio.sleep(0.1)
        
        # Calculate execution stats
        execution_time = time.time() - start_time
        success_rate = (success_count / total_actions * 100) if total_actions > 0 else 0

        results = {
            "success_count": success_count,
            "failure_count": failure_count,
            "total_actions": total_actions,
            "success_rate": success_rate,
            "execution_time_seconds": execution_time
        }

        self.logger.info(f"Form execution completed in {execution_time:.2f}s: {success_count}/{total_actions} actions succeeded ({success_rate:.1f}%). Failures: {failure_count}")

        # Diagnostics for the overall stage
        if self.diagnostics_manager:
            stage_success = failure_count == 0
            error_msg = f"{failure_count} action(s) failed." if failure_count > 0 else None
            self.diagnostics_manager.end_stage(success=stage_success, error=error_msg, details=results)

        return results
