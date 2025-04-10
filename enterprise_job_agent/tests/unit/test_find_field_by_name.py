import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os
import asyncio

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from core.action_executor import ActionExecutor

class TestFindFieldByName(unittest.TestCase):
    """Test the _find_field_by_name method in ActionExecutor."""

    def setUp(self):
        """Set up the test."""
        self.action_executor = ActionExecutor(test_mode=True)
        self.action_executor.logger = MagicMock()
        
        # Mock the form_interaction and element_selector
        self.mock_form_interaction = MagicMock()
        self.mock_element_selector = MagicMock()
        self.mock_form_interaction.element_selector = self.mock_element_selector
        self.action_executor.form_interaction = self.mock_form_interaction

    def test_find_field_by_name(self):
        """Test the _find_field_by_name method."""
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(self._async_test_find_field_by_name())
        self.assertIsNotNone(result)

    async def _async_test_find_field_by_name(self):
        """Asynchronous test for _find_field_by_name."""
        field_name = "First Name"
        mock_locator = MagicMock()
        
        # Set up the element_selector to return a locator only for a specific selector
        self.mock_element_selector.get_element = AsyncMock(side_effect=lambda selector: 
            mock_locator if selector == f'input[name="{field_name}"]' else None
        )
        
        # Call the method
        result = await self.action_executor._find_field_by_name(field_name)
        
        # Verify the element_selector was called with the right selectors
        self.mock_element_selector.get_element.assert_any_call(f'input[name="{field_name}"]')
        
        # Check that we get the expected result
        self.assertEqual(result, mock_locator)
        
        return result

    def test_find_field_by_name_not_found(self):
        """Test when field is not found."""
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(self._async_test_field_not_found())
        self.assertIsNone(result)
        
    async def _async_test_field_not_found(self):
        """Test field not found scenario."""
        # Configure element_selector to return None for any selector
        self.mock_element_selector.get_element = AsyncMock(return_value=None)
        
        # Call the method
        result = await self.action_executor._find_field_by_name("Nonexistent Field")
        
        # Verify logging
        self.action_executor.logger.warning.assert_called_once()
        
        return result

if __name__ == '__main__':
    unittest.main() 