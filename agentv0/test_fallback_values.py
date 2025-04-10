import unittest
from strategies.adaptive_strategy import AdaptiveStrategy
from strategies.lever_strategy import LeverStrategy
from strategies.greenhouse_strategy import GreenhouseStrategy
from strategies.base_strategy import BaseApplicationStrategy
import logging
from typing import Dict, List, Any, Tuple
from playwright.sync_api import Page

# Configure logging for tests
logging.basicConfig(level=logging.INFO)

# Test mock that implements the abstract methods
class MockBaseStrategy(BaseApplicationStrategy):
    """Mock implementation of BaseApplicationStrategy for testing."""
    
    def find_fields(self, page: Page) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Mock implementation."""
        return [], {}
    
    def handle_field(self, page: Page, profile_key: str, selector: str, value: Any, probe_elements_map: Dict[str, Any] = None) -> bool:
        """Mock implementation."""
        return False
    
    def get_submit_selectors(self) -> List[str]:
        """Mock implementation."""
        return ["button[type=submit]"]
        
    def perform_pre_upload_steps(self, page: Page):
        """Mock implementation."""
        pass
        
    def perform_pre_submit_steps(self, page: Page):
        """Mock implementation."""
        pass

class TestFallbackValues(unittest.TestCase):
    """Test the fallback value generation across different strategies."""
    
    def setUp(self):
        """Set up test cases."""
        self.lever_strategy = LeverStrategy()
        self.greenhouse_strategy = GreenhouseStrategy()
        self.adaptive_strategy = AdaptiveStrategy()
        self.base_strategy = MockBaseStrategy()  # Use the mock implementation
        
        # Test field contexts
        self.empty_context = {}
        
        self.eeo_context_no_options = {
            'label': 'What is your gender?',
            'section': 'Equal Employment Opportunity',
            'tag': 'select'
        }
        
        self.eeo_context_with_options = {
            'label': 'What is your ethnicity?',
            'section': 'Equal Employment Opportunity',
            'tag': 'select',
            'options': [
                {'text': 'Hispanic or Latino', 'value': 'hispanic'},
                {'text': 'White (Not Hispanic or Latino)', 'value': 'white'},
                {'text': 'Black or African American', 'value': 'black'},
                {'text': 'Asian', 'value': 'asian'},
                {'text': 'Decline to self-identify', 'value': 'decline'}
            ]
        }
        
    def test_common_fallbacks_in_base_strategy(self):
        """Test that base strategy provides fallbacks for common fields."""
        common_fields = [
            "salary_expectation",
            "notice_period",
            "how_did_you_hear",
            "website",
            "references",
            "availability",
            "work_authorization_us",
            "require_sponsorship",
            "relocate",
            "remote_work"
        ]
        
        for field in common_fields:
            with self.subTest(field=field):
                fallback = self.base_strategy.generate_fallback_value(field, {})
                self.assertIsNotNone(fallback, f"No fallback provided for {field}")
                self.assertNotEqual(fallback, "", f"Empty fallback provided for {field}")
    
    def test_eeo_field_detection_and_fallbacks(self):
        """Test that EEO fields are detected and given appropriate fallbacks."""
        # Test EEO field with no options
        fallback = self.lever_strategy.generate_fallback_value("gender", self.eeo_context_no_options)
        self.assertEqual(fallback, "Prefer not to say")
        
        # Test EEO field with options including a decline option
        fallback = self.lever_strategy.generate_fallback_value("ethnicity", self.eeo_context_with_options)
        self.assertEqual(fallback, "decline")  # Should use the value from the decline option
    
    def test_adaptive_strategy_fallbacks(self):
        """Test fallbacks in the adaptive strategy."""
        # Adaptive strategy uses the mapper for fallbacks
        fallback = self.adaptive_strategy.mapper.generate_fallback_value("salary_expectation", {})
        self.assertEqual(fallback, "Competitive / Market rate")
        
        # Test that it handles EEO fields properly
        fallback = self.adaptive_strategy.mapper.generate_fallback_value("gender", self.eeo_context_no_options)
        self.assertEqual(fallback, "Prefer not to say")
    
    def test_nonexistent_field_fallbacks(self):
        """Test fallbacks for fields that don't have predefined fallbacks."""
        # Fields without predefined fallbacks should return None
        fallback = self.lever_strategy.generate_fallback_value("some_random_field", {})
        self.assertIsNone(fallback)
        
        # Custom fields with no EEO context should return None
        fallback = self.lever_strategy.generate_fallback_value("custom_question", {'label': 'What is your favorite color?'})
        self.assertIsNone(fallback)

if __name__ == '__main__':
    unittest.main() 