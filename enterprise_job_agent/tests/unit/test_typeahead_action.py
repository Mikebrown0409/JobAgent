import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os
import asyncio

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from core.action_executor import ActionExecutor, TypeaheadAction

class TestTypeaheadAction(unittest.TestCase):
    """Test the TypeaheadAction and its execution."""

    def setUp(self):
        """Set up the test."""
        self.action_executor = ActionExecutor(test_mode=True)
        self.action_executor.logger = MagicMock()
        
        # Mock form_interaction and its methods
        self.mock_form_interaction = MagicMock()
        self.mock_form_interaction.handle_typeahead_with_ai = AsyncMock(return_value=True)
        self.action_executor.form_interaction = self.mock_form_interaction
        
        # Mock the element_selector for field finding
        self.mock_element_selector = MagicMock()
        self.mock_form_interaction.element_selector = self.mock_element_selector
        
        # Set up the _find_field_by_name method to return a mock element
        self.mock_element = MagicMock()
        self.mock_element.get_css_selector = AsyncMock(return_value="#university-field")
        self.action_executor._find_field_by_name = AsyncMock(return_value=self.mock_element)
        
        # Create a sample profile data
        self.profile_data = {
            "education": {
                "school": "University of California, Berkeley",
                "degree": "Bachelor of Science"
            },
            "personal": {
                "name": "John Doe",
                "location": "San Francisco, CA"
            }
        }

    def test_typeahead_action_with_selector(self):
        """Test typeahead action with provided selector."""
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(self._async_test_with_selector())
        self.assertTrue(result)

    async def _async_test_with_selector(self):
        """Test typeahead action with a provided selector."""
        # Create a TypeaheadAction with a selector
        action = TypeaheadAction(
            field_name="University",
            value="University of California, Berkeley",
            selector="#university-field",
            field_type="school",
            profile_data=self.profile_data
        )
        
        # Execute the action
        result = await self.action_executor._execute_typeahead_action(action)
        
        # Verify handle_typeahead_with_ai was called with right parameters (using kwargs)
        self.mock_form_interaction.handle_typeahead_with_ai.assert_called_once()
        
        call_kwargs = self.mock_form_interaction.handle_typeahead_with_ai.call_args.kwargs
        self.assertEqual(call_kwargs["selector"], "#university-field")
        self.assertEqual(call_kwargs["value"], "University of California, Berkeley")
        self.assertEqual(call_kwargs["field_type"], "school")
        self.assertEqual(call_kwargs["profile_data"], self.profile_data)
        
        return result
        
    def test_typeahead_action_with_field_name(self):
        """Test typeahead action with field name lookup."""
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(self._async_test_with_field_name())
        self.assertTrue(result)
        
    async def _async_test_with_field_name(self):
        """Test typeahead action using field name to find selector."""
        # Create a TypeaheadAction with only field name (no selector)
        action = TypeaheadAction(
            field_name="University", 
            value="University of California, Berkeley",
            field_type="school",
            profile_data=self.profile_data
        )
        
        # Execute the action
        result = await self.action_executor._execute_typeahead_action(action)
        
        # Verify _find_field_by_name was called
        self.action_executor._find_field_by_name.assert_called_once_with("University")
        
        # Verify handle_typeahead_with_ai was called with the found selector
        self.mock_form_interaction.handle_typeahead_with_ai.assert_called_once()
        call_kwargs = self.mock_form_interaction.handle_typeahead_with_ai.call_args.kwargs
        self.assertEqual(call_kwargs["selector"], "#university-field")
        
        return result
        
    def test_typeahead_action_field_not_found(self):
        """Test typeahead action when field cannot be found."""
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(self._async_test_field_not_found())
        self.assertFalse(result)
        
    async def _async_test_field_not_found(self):
        """Test case where field name doesn't match any element."""
        # Create a TypeaheadAction with only field name
        action = TypeaheadAction(
            field_name="Nonexistent Field", 
            value="Some Value"
        )
        
        # Configure _find_field_by_name to return None
        self.action_executor._find_field_by_name = AsyncMock(return_value=None)
        
        # Execute the action
        result = await self.action_executor._execute_typeahead_action(action)
        
        # Verify typeahead method was not called
        self.mock_form_interaction.handle_typeahead_with_ai.assert_not_called()
        
        # The method returns False immediately without logging an error
        # in the specific case of field not found
        self.assertFalse(result)
        
        return result

if __name__ == '__main__':
    unittest.main() 