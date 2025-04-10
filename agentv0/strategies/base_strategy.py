from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Any, TypeVar, Union
from playwright.sync_api import Page

# Type alias for field definitions and maps
Fields = List[Dict[str, Any]]
ElementMap = Dict[str, Dict[str, Any]]
ReturnType = Tuple[Fields, ElementMap]  # Ensure abstract method aligns with implementations


class BaseApplicationStrategy(ABC):
    """Abstract base class for platform-specific application strategies."""

    @abstractmethod
    def find_fields(self, page: Page) -> ReturnType:
        """Platform-specific method to find form fields.
        
        Args:
            page: The Playwright page object
            
        Returns:
            A tuple containing:
                1. List of dictionaries, each representing a form field with at least 'key', 'selector', 'label', and 'type'
                2. Dictionary mapping selectors to element context data (for AI-driven interaction)
        """
        pass

    @abstractmethod
    def handle_field(self, page: Page, profile_key: str, selector: str, value: Any, probe_elements_map: Dict[str, Any] = None) -> bool:
        """Platform-specific handling for a field. Return True if handled, False otherwise.
        
        Args:
            page: The Playwright page object
            profile_key: The profile key being processed (e.g., 'full_name', 'email')
            selector: CSS selector for the target field
            value: Value to enter/select (string or list for multi-select fields)
            probe_elements_map: Optional map of element context data from probe for AI-driven interaction
            
        Returns:
            True if handled by the strategy, False to use default fallback
        """
        # Default implementation indicates not handled by strategy
        return False
        
    @abstractmethod
    def get_submit_selectors(self) -> List[str]:
        """Return a list of potential submit button selectors/texts for this platform."""
        pass
    
    @abstractmethod
    def perform_pre_upload_steps(self, page: Page):
        """Perform any actions needed BEFORE file uploads (e.g., clicking reveal buttons)."""
        pass

    @abstractmethod
    def perform_pre_submit_steps(self, page: Page):
        """Perform any actions needed just BEFORE clicking the final submit button."""
        pass

    def generate_fallback_value(self, profile_key: str, field_context: Dict[str, Any]) -> Any:
        """Generate intelligent fallback values for common fields not in the profile.
        
        Args:
            profile_key: The field key (e.g., 'salary_expectation')
            field_context: The field's context information
            
        Returns:
            A reasonable fallback value or None if no fallback is appropriate
        """
        # Common field fallbacks based on field key
        fallbacks = {
            "salary_expectation": "Competitive / Market rate",
            "notice_period": "2 weeks",
            "how_did_you_hear": "LinkedIn",
            "website": "https://linkedin.com/in/myprofile",
            "references": "Available upon request",
            "availability": "Immediate",
            "work_authorization_us": "Yes",
            "require_sponsorship": "No",
            "relocate": "Yes",
            "remote_work": "Yes",
        }
        
        # Check for direct match in fallbacks
        if profile_key in fallbacks:
            return fallbacks[profile_key]
        
        # Use context to determine if this is an EEO field (Equal Employment Opportunity)
        label = field_context.get('label', '').lower() if field_context else ''
        section = field_context.get('section', '').lower() if field_context else ''
        
        # Check for EEO fields by context
        is_eeo_field = any(word in section for word in ['equal', 'opportunity', 'eeo', 'diversity']) or \
                       any(word in label for word in ['gender', 'race', 'ethnicity', 'veteran', 'disability'])
        
        if is_eeo_field:
            # For EEO fields, prefer "Decline to answer" if available
            if field_context and field_context.get('options'):
                for option in field_context['options']:
                    option_text = option.get('text', '').lower()
                    if any(phrase in option_text for phrase in ['decline', 'prefer not', 'do not wish']):
                        return option.get('value') or option.get('text')
            
            # Default EEO fallback if no decline option found
            return "Prefer not to say"
        
        # Default implementation returns None - no fallback
        return None

    # Add more common methods as needed, e.g., handle_login, navigate_to_form, etc.
