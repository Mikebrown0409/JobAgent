"""Action executor for job application system."""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass

from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.tools.form_interaction import FormInteraction
from enterprise_job_agent.tools.element_selector import ElementSelector

logger = logging.getLogger(__name__)

@dataclass
class ActionContext:
    """Context for an action execution."""
    field_id: str
    field_type: str
    field_value: Any
    frame_id: Optional[str] = None
    options: Optional[Dict[str, Any]] = None

class ActionExecutor:
    """Executes actions on forms."""
    
    def __init__(
        self,
        browser_manager: BrowserManager,
        form_interaction: FormInteraction,
        element_selector: ElementSelector,
        diagnostics_manager: Optional[DiagnosticsManager] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """Initialize the action executor.
        
        Args:
            browser_manager: Browser manager for browser automation
            form_interaction: Form interaction utility
            element_selector: Element selector utility
            diagnostics_manager: Optional diagnostics manager
            max_retries: Maximum number of retries for failed actions
            retry_delay: Delay between retries in seconds
        """
        self.browser_manager = browser_manager
        self.form_interaction = form_interaction
        self.element_selector = element_selector
        self.diagnostics_manager = diagnostics_manager
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logging.getLogger(__name__)

    async def execute_form_actions(
        self,
        actions: List[ActionContext],
        stop_on_error: bool = True
    ) -> Dict[str, Tuple[bool, Optional[str]]]:
        """Execute a list of form actions with retries and error handling.
        
        Args:
            actions: List of actions to execute
            stop_on_error: Whether to stop on first error
            
        Returns:
            Dictionary mapping field IDs to (success, error_message) tuples
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage("execute_form_actions")
            
        results = {}
        
        for action in actions:
            if self.diagnostics_manager:
                self.diagnostics_manager.start_stage(f"action_{action.field_id}")
                
            success = False
            error_msg = None
            
            for attempt in range(self.max_retries):
                try:
                    # Switch to correct frame if needed
                    if action.frame_id:
                        frame = await self.browser_manager.get_frame(action.frame_id)
                        if not frame:
                            raise ValueError(f"Frame not found: {action.frame_id}")
                    
                    # Get selector for the field
                    selector = f"#{action.field_id}"  # Default selector
                    
                    # Execute action based on field type
                    if action.field_type == "select":
                        success = await self.form_interaction.select_option(
                            selector,
                            action.field_value,
                            action.options.get("dropdown_options") if action.options else None
                        )
                    elif action.field_type == "checkbox":
                        success = await self.form_interaction.set_checkbox(
                            selector,
                            bool(action.field_value)
                        )
                    elif action.field_type == "file":
                        success = await self.form_interaction.upload_file(
                            selector,
                            str(action.field_value)
                        )
                    else:  # Default to fill
                        success = await self.form_interaction.fill_field(
                            selector,
                            str(action.field_value)
                        )
                        
                    if success:
                        break
                    else:
                        error_msg = "Action failed without exception"
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
                    
                except Exception as e:
                    error_msg = str(e)
                    self.logger.warning(
                        f"Action failed for field {action.field_id} "
                        f"(attempt {attempt + 1}/{self.max_retries}): {error_msg}"
                    )
                    
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
                    
            results[action.field_id] = (success, error_msg)
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    success,
                    error=error_msg if not success else None
                )
                
            if not success and stop_on_error:
                break
                
        if self.diagnostics_manager:
            self.diagnostics_manager.end_stage(
                all(success for success, _ in results.values()),
                details={"results": results}
            )
            
        return results 