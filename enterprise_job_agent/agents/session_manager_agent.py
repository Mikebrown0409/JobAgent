"""Session Manager Agent for handling application session state and navigation."""

import logging
import asyncio
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from crewai import Agent

from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.tools.element_selector import ElementSelector

logger = logging.getLogger(__name__)

@dataclass
class SessionState:
    """Current state of the application session."""
    current_page: str
    form_state: Dict[str, Any]
    navigation_history: List[str]
    last_interaction: float
    is_authenticated: bool
    errors: List[Dict[str, Any]]
    active_frame: Optional[str] = None
    recovery_attempts: int = 0
    max_recovery_attempts: int = 3

SYSTEM_PROMPT = """You are an expert Session Management Specialist focusing on job applications.

TASK:
Manage application session state, navigation, and form persistence with high reliability.

YOUR EXPERTISE:
- Maintaining stable application sessions
- Handling multi-page navigation flows
- Preventing session timeouts
- Managing authentication states
- Recovering from navigation errors

APPROACH:
1. Track session state continuously
2. Detect and prevent timeouts proactively
3. Handle page transitions smoothly
4. Maintain form state across pages
5. Recover from navigation errors gracefully

TECHNICAL CAPABILITIES:
- Session state monitoring
- Navigation management
- Form state persistence
- Authentication handling
- Error recovery strategies

ALWAYS STRUCTURE YOUR RESPONSES AS JSON following the exact schema provided in the task.
"""

class SessionManagerAgent:
    """Agent for managing application session state and navigation."""
    
    def __init__(
        self,
        llm: Any,
        browser_manager: BrowserManager,
        diagnostics_manager: Optional[DiagnosticsManager] = None,
        tools: List[Any] = None,
        verbose: bool = False,
        session_timeout: int = 1800  # 30 minutes
    ):
        """Initialize the session manager agent.
        
        Args:
            llm: Language model to use
            browser_manager: Browser manager instance
            diagnostics_manager: Optional diagnostics manager
            tools: List of tools the agent can use
            verbose: Whether to enable verbose output
            session_timeout: Session timeout in seconds
        """
        self.llm = llm
        self.browser_manager = browser_manager
        self.diagnostics_manager = diagnostics_manager
        self.verbose = verbose
        self.session_timeout = session_timeout
        
        self.element_selector = ElementSelector(browser_manager)
        self.agent = self.create(llm, tools, verbose)
        self.session_state = SessionState(
            current_page="",
            form_state={},
            navigation_history=[],
            last_interaction=time.time(),
            is_authenticated=False,
            errors=[],
            active_frame=None,
            recovery_attempts=0
        )
    
    @staticmethod
    def create(
        llm: Any,
        tools: List[Any] = None,
        verbose: bool = False
    ) -> Agent:
        """Create a Session Manager Agent."""
        return Agent(
            role="Session Management Specialist",
            goal="Maintain stable application sessions and handle navigation reliably",
            backstory="""You are an expert in managing web application sessions and navigation.
            You understand the complexities of maintaining state across multi-page forms.
            Your expertise ensures applications remain stable and recoverable from errors.""",
            verbose=verbose,
            allow_delegation=False,
            tools=tools or [],
            llm=llm,
            system_prompt=SYSTEM_PROMPT
        )
    
    async def navigate_to_page(
        self,
        target_url: str,
        expected_elements: List[str] = None,
        timeout: int = 10000,
        retry_on_timeout: bool = True
    ) -> bool:
        """Navigate to a specific page and verify arrival.
        
        Args:
            target_url: URL to navigate to
            expected_elements: List of selectors that should be present
            timeout: Timeout in milliseconds
            retry_on_timeout: Whether to retry navigation if a timeout occurs
            
        Returns:
            True if navigation succeeded, False otherwise
        """
        try:
            # Check if we're already on the target page
            current_url = self.browser_manager.page.url if self.browser_manager.page else None
            if current_url == target_url:
                logger.info("Already on target page")
                return True
            
            # Navigate to the page
            if not await self.browser_manager.navigate(target_url):
                return False
            
            # Update session state
            self.session_state.current_page = target_url
            self.session_state.navigation_history.append(target_url)
            self.session_state.last_interaction = time.time()
            self.session_state.active_frame = None  # Reset active frame on navigation
            
            # Wait for network idle
            try:
                await self.browser_manager.page.wait_for_load_state("networkidle", timeout=timeout)
            except Exception as e:
                logger.warning(f"Network idle timeout: {e}")
            
            # Verify expected elements if provided
            if expected_elements:
                for selector in expected_elements:
                    try:
                        element = await self.element_selector.wait_for_element(
                            selector,
                            timeout=timeout
                        )
                        if not element and retry_on_timeout:
                            # Attempt recovery
                            if self.session_state.recovery_attempts < self.session_state.max_recovery_attempts:
                                self.session_state.recovery_attempts += 1
                                logger.info(f"Retrying navigation to {target_url} (attempt {self.session_state.recovery_attempts})")
                                return await self.navigate_to_page(
                                    target_url,
                                    expected_elements,
                                    timeout,
                                    retry_on_timeout=False  # Prevent infinite recursion
                                )
                            else:
                                raise ValueError(f"Expected element not found after {self.session_state.max_recovery_attempts} attempts: {selector}")
                    except Exception as e:
                        raise
            
            # Reset recovery attempts on successful navigation
            self.session_state.recovery_attempts = 0
            return True
            
        except Exception as e:
            logger.error(f"Error during navigation: {e}")
            return False
    
    async def check_session_health(self) -> bool:
        """Check if the current session is healthy."""
        try:
            # Check if browser is initialized
            if not self.browser_manager or not self.browser_manager.page:
                logger.error("Browser not initialized")
                return False
            
            # Check if page is responsive
            try:
                await self.browser_manager.page.evaluate("1")
            except Exception as e:
                logger.error(f"Page not responsive: {e}")
                return False
            
            # Check session timeout
            if time.time() - self.session_state.last_interaction > self.session_timeout:
                logger.error("Session timed out")
                return False
            
            # Update last interaction time
            self.session_state.last_interaction = time.time()
            return True
            
        except Exception as e:
            logger.error(f"Error checking session health: {e}")
            return False
    
    async def initialize_session(self) -> bool:
        """Initialize a new application session."""
        try:
            # Reset session state
            self.session_state = SessionState(
                current_page="",
                form_state={},
                navigation_history=[],
                last_interaction=time.time(),
                is_authenticated=False,
                errors=[],
                active_frame=None,
                recovery_attempts=0
            )
            
            # Check if browser is ready
            if not await self.check_session_health():
                logger.error("Browser not healthy during session initialization")
                return False
            
            # Initialize browser state
            await self.browser_manager.page.evaluate("""
                // Clear localStorage
                window.localStorage.clear();
                // Clear sessionStorage
                window.sessionStorage.clear();
                // Clear cookies
                document.cookie.split(";").forEach(function(c) { 
                    document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/"); 
                });
            """)
            
            return True
            
        except Exception as e:
            logger.error(f"Error initializing session: {e}")
            return False
    
    async def save_form_state(self) -> Dict[str, Any]:
        """Save the current state of form fields.
        
        Returns:
            Dictionary of field values
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage("save_form_state")
            
        try:
            page = self.browser_manager.page
            if not page:
                raise ValueError("No active page")
                
            # Get all form fields
            form_state = {}
            input_selectors = [
                "input:not([type='submit'])",
                "select",
                "textarea"
            ]
            
            for selector in input_selectors:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    field_id = await element.get_attribute("id") or await element.get_attribute("name")
                    if field_id:
                        if await element.get_attribute("type") == "checkbox":
                            value = await element.is_checked()
                        else:
                            value = await element.input_value()
                        form_state[field_id] = value
            
            self.session_state.form_state = form_state
            self.session_state.last_interaction = time.time()
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(success=True, details={"fields_saved": len(form_state)})
            return form_state
            
        except Exception as e:
            error_msg = f"Failed to save form state: {str(e)}"
            logger.error(error_msg)
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(success=False, error=error_msg)
            return {}
    
    async def restore_form_state(self) -> bool:
        """Restore previously saved form state.
        
        Returns:
            True if state was restored successfully, False otherwise
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage("restore_form_state")
            
        try:
            page = self.browser_manager.page
            if not page:
                raise ValueError("No active page")
                
            restored_fields = 0
            failed_fields = []
            
            for field_id, value in self.session_state.form_state.items():
                try:
                    # Find the element
                    element = await page.query_selector(f"#{field_id}, [name='{field_id}']")
                    if not element:
                        failed_fields.append({"field": field_id, "reason": "Element not found"})
                        continue
                        
                    # Restore value based on field type
                    field_type = await element.get_attribute("type")
                    if field_type == "checkbox":
                        if value:
                            await element.check()
                        else:
                            await element.uncheck()
                    else:
                        await element.fill(str(value))
                        
                    restored_fields += 1
                    
                except Exception as e:
                    failed_fields.append({"field": field_id, "reason": str(e)})
            
            self.session_state.last_interaction = time.time()
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    success=len(failed_fields) == 0,
                    details={
                        "restored_fields": restored_fields,
                        "failed_fields": failed_fields
                    }
                )
            
            return len(failed_fields) == 0
            
        except Exception as e:
            error_msg = f"Failed to restore form state: {str(e)}"
            logger.error(error_msg)
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(success=False, error=error_msg)
            return False 