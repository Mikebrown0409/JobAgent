"""Handles click actions on elements like buttons or links."""

import logging
from typing import Dict, Any, Optional

from enterprise_job_agent.core.action_handlers.base_handler import BaseActionHandler
from enterprise_job_agent.core.browser_interface import BrowserInterface
from enterprise_job_agent.tools.form_interaction import FormInteraction
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.core.exceptions import ActionExecutionError
from enterprise_job_agent.tools.element_selector import ElementSelector

logger = logging.getLogger(__name__)

class ClickHandler(BaseActionHandler):
    """Handles clicking actionable elements."""

    def __init__(
        self,
        browser_interface: BrowserInterface,
        form_interaction: FormInteraction,
        element_selector: ElementSelector,
        diagnostics_manager: Optional[DiagnosticsManager] = None
    ):
        super().__init__(browser_interface, element_selector, diagnostics_manager)
        self.form_interaction = form_interaction
        self.logger = logging.getLogger(__name__)

    async def execute(self, action_context: Dict[str, Any]) -> bool:
        """Executes a click action on the specified element."""
        if not action_context:
            self.logger.error("ClickHandler received None action_context")
            return False

        selector = action_context.field_id
        fallback_text = action_context.fallback_text
        frame_id = action_context.frame_id
        element_data = action_context.options.get('element_data', {}) if action_context.options else {}

        if not selector and not fallback_text:
            self.logger.error("Click action requires either a selector or fallback text.")
            return False

        self.logger.info(f"Executing click action for '{fallback_text or selector}'")

        try:
            success = await self.form_interaction.click_element(selector, frame_id)
            if success:
                self.logger.info(f"Click successful for '{fallback_text or selector}'")
                return True
            else:
                self.logger.error(f"Click failed for '{fallback_text or selector}' using selector '{selector}'")
                return False
        except Exception as e:
            self.logger.error(f"Error executing click action for '{fallback_text or selector}': {e}", exc_info=True)
            raise ActionExecutionError(f"Click failed for {selector}", selector=selector, details=str(e)) from e 