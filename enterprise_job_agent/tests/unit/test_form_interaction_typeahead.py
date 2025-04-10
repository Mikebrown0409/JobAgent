import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os
import asyncio
import json

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

# Import the necessary classes
from core.action_executor import TypeaheadAction, ActionExecutor
from tools.form_interaction import FormInteraction, InteractionType
from tools.dropdown_matcher import DropdownMatcher

class TestFormInteractionTypeahead(unittest.TestCase):
    """Test the handle_typeahead_with_ai method in FormInteraction."""

    def setUp(self):
        """Set up the test environment with necessary mocks."""
        # Create a mock browser interface
        self.mock_browser = MagicMock()
        self.mock_browser.page = MagicMock()
        
        # Create a mock element selector with async methods
        self.mock_element_selector = MagicMock()
        self.mock_element = MagicMock()
        self.mock_element_selector.get_element = AsyncMock(return_value=self.mock_element)
        self.mock_element.click = AsyncMock()
        self.mock_element.fill = AsyncMock()
        self.mock_element.press = AsyncMock()
        self.mock_element.input_value = AsyncMock(return_value="University of California, Berkeley")
        
        # Create a mock diagnostics manager
        self.mock_diagnostics = MagicMock()
        
        # Create a FormInteraction instance with mocks
        self.form_interaction = FormInteraction(
            browser=self.mock_browser,
            element_selector=self.mock_element_selector,
            diagnostics_manager=self.mock_diagnostics
        )
        
        # Create a logger mock
        self.form_interaction.logger = MagicMock()
        
        # Set up common test data
        self.test_selector = "#school-field"
        self.test_value = "University of California, Berkeley"
        self.test_profile = {
            "education": {
                "school": "University of California, Berkeley",
                "degree": "Bachelor of Science in Computer Science"
            },
            "personal": {
                "name": "Jane Doe",
                "location": "San Francisco, CA"
            }
        }
        
        # Mock the LLM client
        self.mock_llm_client = MagicMock()
        # Mock generate_text instead of chat method based on actual implementation
        self.mock_llm_client.generate_text = AsyncMock(return_value=json.dumps([
            "University of California, Berkeley", "UC Berkeley", "Cal", "Berkeley"
        ]))
        
        # Mock the methods used in handle_typeahead_with_ai
        self.form_interaction._generate_intelligent_variants = AsyncMock(
            return_value=["University of California, Berkeley", "UC Berkeley", "Cal", "Berkeley"]
        )
        self.form_interaction._try_fill_and_key = AsyncMock(return_value=True)
        self.form_interaction._get_visible_options_via_js = AsyncMock(return_value=[
            "University of California, Berkeley",
            "University of California, Los Angeles",
            "University of Southern California"
        ])
        self.form_interaction._try_click_option_text = AsyncMock(return_value=False)
        self.form_interaction._find_best_option_with_ai = AsyncMock(return_value="University of California, Berkeley")
        self.form_interaction._try_intelligent_typeahead_js = AsyncMock(return_value=False)
        
        # Add the dropdown matcher
        self.form_interaction.dropdown_matcher = MagicMock()
        self.form_interaction._generate_school_variants = MagicMock(
            return_value=["UC Berkeley", "Berkeley", "Cal"]
        )

    def test_handle_typeahead_with_ai(self):
        """Test the handle_typeahead_with_ai method."""
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(self._async_test_handle_typeahead_with_ai())
        self.assertTrue(result)
        
    async def _async_test_handle_typeahead_with_ai(self):
        """Asynchronous test for handle_typeahead_with_ai."""
        # Set _try_fill_and_key to return True for success
        self.form_interaction._try_fill_and_key = AsyncMock(return_value=True)
        
        # Call the method
        result = await self.form_interaction.handle_typeahead_with_ai(
            selector=self.test_selector,
            value=self.test_value,
            profile_data=self.test_profile,
            field_type="school",
            llm_client=self.mock_llm_client
        )
        
        # Verify methods were called in the correct order
        self.mock_element.click.assert_called_once()
        self.form_interaction._generate_intelligent_variants.assert_called_once()
        self.form_interaction._try_fill_and_key.assert_called_once()
        
        return result
        
    def test_handle_typeahead_with_complex_flow(self):
        """Test handle_typeahead_with_ai with the more complex flow."""
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(self._async_test_complex_flow())
        self.assertTrue(result)
        
    async def _async_test_complex_flow(self):
        """Test the more complex flow when initial strategies fail."""
        # Configure first fill_and_key to fail, but succeed on variant
        self.form_interaction._try_fill_and_key = AsyncMock(side_effect=[False, True, False])
        
        # Call the method
        result = await self.form_interaction.handle_typeahead_with_ai(
            selector=self.test_selector,
            value=self.test_value,
            profile_data=self.test_profile,
            field_type="school",
            llm_client=self.mock_llm_client
        )
        
        # Verify _try_fill_and_key was called multiple times
        self.assertEqual(self.form_interaction._try_fill_and_key.call_count, 2)
        
        return result

if __name__ == '__main__':
    unittest.main() 