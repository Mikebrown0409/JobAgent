"""Error handling and recovery utilities for the enterprise job application system."""

import logging
import traceback
from typing import Dict, Any, Optional, Callable, List, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

class ErrorSeverity(Enum):
    """Severity levels for errors."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ErrorCategory(Enum):
    """Categories of errors that can occur during job applications."""
    NETWORK = "network"
    AUTHENTICATION = "authentication"
    FORM_VALIDATION = "form_validation"
    BROWSER = "browser"
    FILE_UPLOAD = "file_upload"
    CAPTCHA = "captcha"
    SERVER = "server"
    TIMEOUT = "timeout"
    UNEXPECTED_REDIRECT = "unexpected_redirect"
    ELEMENT_NOT_FOUND = "element_not_found"
    PERMISSION = "permission"
    DATA_MAPPING = "data_mapping"
    UNKNOWN = "unknown"

class ApplicationError(Exception):
    """
    Custom exception for application errors with additional context.
    """
    
    def __init__(
        self, 
        message: str, 
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
        recoverable: bool = True
    ):
        """
        Initialize an application error.
        
        Args:
            message: Error message
            category: Error category
            severity: Error severity
            context: Additional context information
            retry_count: Number of retries attempted
            recoverable: Whether the error is potentially recoverable
        """
        self.message = message
        self.category = category
        self.severity = severity
        self.context = context or {}
        self.retry_count = retry_count
        self.recoverable = recoverable
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the error to a dictionary.
        
        Returns:
            Dictionary representation of the error
        """
        return {
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "context": self.context,
            "retry_count": self.retry_count,
            "recoverable": self.recoverable,
            "traceback": traceback.format_exc()
        }

class ErrorRecoveryStrategy:
    """
    Base class for error recovery strategies.
    """
    
    def __init__(self, max_retries: int = 3, delay: float = 1.0):
        """
        Initialize the recovery strategy.
        
        Args:
            max_retries: Maximum number of retries
            delay: Delay between retries in seconds
        """
        self.max_retries = max_retries
        self.delay = delay
    
    async def recover(self, error: ApplicationError, context: Dict[str, Any]) -> bool:
        """
        Attempt to recover from the error.
        
        Args:
            error: The error to recover from
            context: Context information
            
        Returns:
            True if recovery was successful, False otherwise
        """
        raise NotImplementedError("Subclasses must implement recover()")

class RetryStrategy(ErrorRecoveryStrategy):
    """
    Simple retry strategy.
    """
    
    async def recover(self, error: ApplicationError, context: Dict[str, Any]) -> bool:
        """
        Recover by retrying the operation.
        
        Args:
            error: The error to recover from
            context: Context information including the operation to retry
            
        Returns:
            True if recovery was successful, False otherwise
        """
        if error.retry_count >= self.max_retries:
            logger.warning(f"Maximum retries ({self.max_retries}) exceeded for {error.category.value} error")
            return False
        
        operation = context.get("operation")
        if not operation or not callable(operation):
            logger.error("No operation provided for retry")
            return False
        
        import asyncio
        
        # Increase delay with each retry
        current_delay = self.delay * (error.retry_count + 1)
        logger.info(f"Retrying operation after {current_delay}s delay (attempt {error.retry_count + 1}/{self.max_retries})")
        
        try:
            # Wait before retrying
            await asyncio.sleep(current_delay)
            
            # Execute the operation
            result = await operation()
            
            logger.info("Retry successful")
            return True
        except Exception as e:
            logger.error(f"Retry failed: {e}")
            
            # Update retry count in the original error
            error.retry_count += 1
            return False

class AlternativePathStrategy(ErrorRecoveryStrategy):
    """
    Try an alternative path/approach.
    """
    
    async def recover(self, error: ApplicationError, context: Dict[str, Any]) -> bool:
        """
        Recover by trying an alternative approach.
        
        Args:
            error: The error to recover from
            context: Context information including alternative operations
            
        Returns:
            True if recovery was successful, False otherwise
        """
        alternatives = context.get("alternatives", [])
        if not alternatives:
            logger.error("No alternative paths provided for recovery")
            return False
        
        # Try each alternative in order
        for i, alternative in enumerate(alternatives):
            if not callable(alternative):
                logger.warning(f"Alternative {i} is not callable, skipping")
                continue
            
            logger.info(f"Trying alternative path {i+1}/{len(alternatives)}")
            
            try:
                # Execute the alternative
                result = await alternative()
                
                logger.info(f"Alternative path {i+1} successful")
                return True
            except Exception as e:
                logger.warning(f"Alternative path {i+1} failed: {e}")
        
        logger.error("All alternative paths failed")
        return False

class ElementSelectionStrategy(ErrorRecoveryStrategy):
    """
    Try alternative element selectors.
    """
    
    async def recover(self, error: ApplicationError, context: Dict[str, Any]) -> bool:
        """
        Recover by trying alternative selectors for an element.
        
        Args:
            error: The error to recover from
            context: Context information including the page and alternative selectors
            
        Returns:
            True if recovery was successful, False otherwise
        """
        from playwright.async_api import Page
        
        page = context.get("page")
        if not page or not isinstance(page, Page):
            logger.error("No page provided for element selection recovery")
            return False
        
        selectors = context.get("selectors", [])
        if not selectors:
            logger.error("No alternative selectors provided for recovery")
            return False
        
        action = context.get("action", "click")
        
        # Try each selector in order
        for i, selector in enumerate(selectors):
            logger.info(f"Trying alternative selector {i+1}/{len(selectors)}: {selector}")
            
            try:
                # Check if element exists
                element = await page.query_selector(selector)
                if not element:
                    logger.warning(f"Element not found with selector: {selector}")
                    continue
                
                # Perform the requested action
                if action == "click":
                    await element.click()
                elif action == "fill" and "value" in context:
                    await element.fill(context["value"])
                elif action == "select" and "value" in context:
                    await page.select_option(selector, context["value"])
                
                logger.info(f"Alternative selector {i+1} successful")
                return True
            except Exception as e:
                logger.warning(f"Alternative selector {i+1} failed: {e}")
        
        logger.error("All alternative selectors failed")
        return False

class CaptchaHandlingStrategy(ErrorRecoveryStrategy):
    """
    Handle CAPTCHA challenges.
    """
    
    async def recover(self, error: ApplicationError, context: Dict[str, Any]) -> bool:
        """
        Attempt to recover from CAPTCHA challenges.
        
        Args:
            error: The error to recover from
            context: Context information including the page
            
        Returns:
            True if recovery was successful, False otherwise
        """
        from playwright.async_api import Page
        
        page = context.get("page")
        if not page or not isinstance(page, Page):
            logger.error("No page provided for CAPTCHA handling")
            return False
        
        # Check for common CAPTCHA services
        captcha_selectors = [
            "iframe[src*='recaptcha']",
            "iframe[src*='captcha']",
            "iframe[src*='hcaptcha']",
            "div.g-recaptcha",
            "div.h-captcha",
            "#captcha"
        ]
        
        # Check if any CAPTCHA is present
        for selector in captcha_selectors:
            captcha_element = await page.query_selector(selector)
            if captcha_element:
                logger.info(f"CAPTCHA detected: {selector}")
                
                # Pause for human intervention if not headless
                if context.get("headless", True) is False:
                    # Take screenshot
                    await page.screenshot(path="captcha.png")
                    
                    logger.info("CAPTCHA requires human intervention. Screenshot saved as captcha.png")
                    logger.info("Waiting for manual CAPTCHA solution...")
                    
                    # Wait for navigation or timeout
                    try:
                        await page.wait_for_navigation(timeout=300000)  # 5 minutes timeout
                        logger.info("Navigation detected after CAPTCHA, assuming it was solved")
                        return True
                    except Exception:
                        logger.error("Timeout waiting for CAPTCHA solution")
                        return False
                else:
                    logger.error("CAPTCHA detected in headless mode, cannot proceed")
                    return False
        
        logger.warning("No recognized CAPTCHA found despite CAPTCHA error")
        return False

class BrowserRestartStrategy(ErrorRecoveryStrategy):
    """
    Restart the browser session.
    """
    
    async def recover(self, error: ApplicationError, context: Dict[str, Any]) -> bool:
        """
        Recover by restarting the browser session.
        
        Args:
            error: The error to recover from
            context: Context information including browser manager
            
        Returns:
            True if recovery was successful, False otherwise
        """
        from enterprise_job_agent.utils.browser_tools import BrowserManager
        
        browser_manager = context.get("browser_manager")
        if not browser_manager or not isinstance(browser_manager, BrowserManager):
            logger.error("No browser manager provided for session restart")
            return False
        
        url = context.get("url")
        if not url:
            logger.error("No URL provided for browser restart")
            return False
        
        logger.info("Attempting to restart browser session")
        
        try:
            # Close existing browser
            await browser_manager.close()
            
            # Start new browser
            success = await browser_manager.start()
            if not success:
                logger.error("Failed to restart browser")
                return False
            
            # Navigate to URL
            success = await browser_manager.navigate(url)
            if not success:
                logger.error(f"Failed to navigate to {url} after restart")
                return False
            
            logger.info("Browser restart successful")
            return True
        except Exception as e:
            logger.error(f"Error during browser restart: {e}")
            return False

class ErrorRecoveryManager:
    """
    Manager for error recovery strategies.
    """
    
    def __init__(self):
        """Initialize the error recovery manager."""
        self.strategies = {}
        self._register_default_strategies()
    
    def _register_default_strategies(self):
        """Register default recovery strategies."""
        # Register strategies by error category
        self.strategies[ErrorCategory.NETWORK] = [
            RetryStrategy(max_retries=5, delay=2.0),
            BrowserRestartStrategy()
        ]
        
        self.strategies[ErrorCategory.ELEMENT_NOT_FOUND] = [
            RetryStrategy(max_retries=3, delay=1.0),
            ElementSelectionStrategy()
        ]
        
        self.strategies[ErrorCategory.TIMEOUT] = [
            RetryStrategy(max_retries=3, delay=3.0),
            BrowserRestartStrategy()
        ]
        
        self.strategies[ErrorCategory.CAPTCHA] = [
            CaptchaHandlingStrategy()
        ]
        
        self.strategies[ErrorCategory.FORM_VALIDATION] = [
            RetryStrategy(max_retries=2, delay=1.0),
            AlternativePathStrategy()
        ]
        
        # Default fallback strategies for all other categories
        self.strategies[ErrorCategory.UNKNOWN] = [
            RetryStrategy(max_retries=3, delay=2.0),
            BrowserRestartStrategy()
        ]
    
    def register_strategy(self, category: ErrorCategory, strategy: ErrorRecoveryStrategy):
        """
        Register a recovery strategy for an error category.
        
        Args:
            category: Error category
            strategy: Recovery strategy
        """
        if category not in self.strategies:
            self.strategies[category] = []
        
        self.strategies[category].append(strategy)
    
    async def recover(self, error: ApplicationError, context: Dict[str, Any]) -> bool:
        """
        Attempt to recover from an error.
        
        Args:
            error: The error to recover from
            context: Context information
            
        Returns:
            True if recovery was successful, False otherwise
        """
        if not error.recoverable:
            logger.warning(f"Error marked as non-recoverable: {error.message}")
            return False
        
        # Get strategies for this error category
        strategies = self.strategies.get(error.category, self.strategies[ErrorCategory.UNKNOWN])
        
        # Try each strategy in order
        for i, strategy in enumerate(strategies):
            logger.info(f"Trying recovery strategy {i+1}/{len(strategies)} for {error.category.value} error")
            
            try:
                # Execute the strategy
                success = await strategy.recover(error, context)
                
                if success:
                    logger.info(f"Recovery strategy {i+1} successful")
                    return True
                else:
                    logger.warning(f"Recovery strategy {i+1} failed")
            except Exception as e:
                logger.error(f"Error in recovery strategy {i+1}: {e}")
        
        logger.error(f"All recovery strategies failed for {error.category.value} error")
        return False

# Create a singleton instance
recovery_manager = ErrorRecoveryManager() 