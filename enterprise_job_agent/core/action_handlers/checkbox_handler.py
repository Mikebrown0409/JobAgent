"""Handles checkbox and radio button actions."""
import logging
from typing import Optional, Dict, Any

from .base_handler import BaseActionHandler
from enterprise_job_agent.core.exceptions import ActionExecutionError
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager

class CheckboxHandler(BaseActionHandler):
    """Handles checkbox and radio button actions."""

    def __init__(
        self,
        browser_interface,
        element_selector,
        form_interaction,
        diagnostics_manager: Optional[DiagnosticsManager] = None
    ):
        super().__init__(browser_interface, element_selector, diagnostics_manager)
        self.form_interaction = form_interaction
        # self.logger = diagnostics_manager.get_logger(__name__) if diagnostics_manager else logging.getLogger(__name__)
        self.logger = logging.getLogger(__name__) # Use standard logger

    async def execute(self, context) -> bool:
        """Execute a checkbox or radio button action."""
        try:
            field_id = context.field_id
            field_value = context.field_value
            frame_id = context.frame_id
            field_type = context.field_type # Should be 'checkbox' or 'radio'
            
            # Determine the target state
            target_state = False
            if field_type == 'radio':
                # Radio buttons are always set to True (checked) when interacted with
                target_state = True
                self.logger.debug(f"Executing radio action for {field_id}")
            elif field_type == 'checkbox':
                # Determine target state for checkbox based on value
                if field_value is None:
                    target_state = True # Default to checking if value is None
                elif isinstance(field_value, str):
                    target_state = field_value.lower() in ('true', 'yes', '1', 'on', 'checked')
                else:
                    target_state = bool(field_value)
                self.logger.debug(f"Executing checkbox action for {field_id} with target state: {target_state}")
            else:
                self.logger.warning(f"CheckboxHandler received unexpected field type: {field_type} for {field_id}. Assuming checkbox.")
                target_state = True # Default to checking

            frame = await self._get_frame(frame_id)
            safe_selector = await self._sanitize_selector(field_id)
            
            # Ensure element is visible before interacting
            if not await self._ensure_element_visibility(frame, safe_selector):
                 self.logger.error(f"Element {safe_selector} not visible for {field_type} action.")
                 return False
                 
            # Use FormInteraction tool for the actual interaction
            await self.form_interaction.set_checkbox(safe_selector, target_state)
            self.logger.info(f"Successfully set {field_type} {safe_selector} to {target_state}")
            return True

        except ActionExecutionError as ae:
             self.logger.error(f"ActionExecutionError during {field_type} action for {context.field_id}: {ae}")
             raise
        except Exception as e:
            field_type_log = context.field_type or "unknown"
            self.logger.error(f"Unexpected error executing {field_type_log} action for {context.field_id}: {e}")
            raise ActionExecutionError(f"Failed to execute {field_type_log} action for '{context.field_id}'") from e 