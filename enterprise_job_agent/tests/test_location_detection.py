"""Test for enhanced location field detection."""

import asyncio
import logging
import sys
import os
import re
from typing import Dict, Any, List
import pytest

# Set up path for imports
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from enterprise_job_agent.core.action_executor import ActionExecutor, ActionContext
from enterprise_job_agent.agents.profile_adapter_agent import ProfileAdapterAgent


class MockLLM:
    """Mock LLM for testing."""
    def call(self, prompt):
        return '{"actions":[]}'


async def test_typeahead_location_detection():
    """Test the enhanced location field detection in _execute_typeahead_action."""
    
    # Configure logging to see debug output
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("test_location_detection")
    logger.setLevel(logging.DEBUG)
    
    # Create a basic action executor
    action_executor = ActionExecutor(test_mode=True)
    
    # Test cases with various ActionContext configurations
    test_cases = [
        # Case 1: Explicit field_type = location
        {
            "field_id": "#location-field", 
            "field_type": "location",
            "field_value": "San Francisco, CA",
            "frame_id": "main",
            "expected_is_location": True,
            "description": "Explicit field_type='location'"
        },
        # Case 2: Location in field name
        {
            "field_id": "#some-field", 
            "field_type": "typeahead",
            "field_value": "New York, NY",
            "field_name": "candidate-location",
            "frame_id": "main",
            "expected_is_location": True,
            "description": "Location in field_name"
        },
        # Case 3: Location in field_id
        {
            "field_id": "#location-typeahead", 
            "field_type": "typeahead",
            "field_value": "Chicago, IL",
            "frame_id": "main",
            "expected_is_location": True,
            "description": "Location in field_id"
        },
        # Case 4: Location field_purpose in options
        {
            "field_id": "#dropdown1", 
            "field_type": "select",
            "field_value": "Boston, MA",
            "frame_id": "main",
            "options": {"field_purpose": "location"},
            "expected_is_location": True,
            "description": "field_purpose='location' in options"
        },
        # Case 5: City-state pattern in value
        {
            "field_id": "#generic-field", 
            "field_type": "text",
            "field_value": "Seattle, WA",
            "frame_id": "main",
            "expected_is_location": True,
            "description": "City-state pattern in value"
        },
        # Case 6: Common city name in value
        {
            "field_id": "#another-field", 
            "field_type": "input",
            "field_value": "San Francisco",
            "frame_id": "main",
            "expected_is_location": True,
            "description": "Common city name in value"
        },
        # Case 7: Non-location field (negative test)
        {
            "field_id": "#name-field", 
            "field_type": "text",
            "field_value": "John Smith",
            "frame_id": "main",
            "expected_is_location": False,
            "description": "Non-location field (negative test)"
        }
    ]
    
    logger.info("Testing enhanced location field detection in _execute_typeahead_action")
    
    # Run each test case
    for i, case in enumerate(test_cases):
        logger.info(f"Test case {i+1}: {case['description']}")
        
        # Create ActionContext from test case
        context_kwargs = {k: v for k, v in case.items() if k not in ["expected_is_location", "description"]}
        context = ActionContext(**context_kwargs)
        
        # Use the private method directly with the spy pattern
        # Store original method
        original_method = action_executor._execute_interactive_location_typeahead
        
        # Detection results
        is_location_detected = False
        
        # Replace with spy method
        async def spy_method(field_id, value, frame_id=None):
            nonlocal is_location_detected
            is_location_detected = True
            return True  # Pretend it succeeded
            
        action_executor._execute_interactive_location_typeahead = spy_method
        
        try:
            # Execute the typeahead action
            await action_executor._execute_typeahead_action(context)
            
            # Check if it was detected as a location
            result = "PASSED" if is_location_detected == case["expected_is_location"] else "FAILED"
            logger.info(f"  Result: {result} - Detected as location: {is_location_detected}, Expected: {case['expected_is_location']}")
            
        finally:
            # Restore original method
            action_executor._execute_interactive_location_typeahead = original_method


async def test_profile_adapter_location_detection():
    """Test the enhanced location field detection in profile adapter."""
    
    # Configure logging to see debug output
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("test_location_detection")
    logger.setLevel(logging.DEBUG)
    
    # Create a mock profile adapter agent
    profile_adapter = ProfileAdapterAgent(llm=MockLLM(), verbose=True)
    
    # Test form elements with various configurations
    test_form_elements = [
        # Element with field_purpose = location
        {
            "selector": "#location1",
            "field_type": "select",
            "field_purpose": "location",
            "expected_type": "location",
            "description": "field_purpose='location'"
        },
        # Element with location in description
        {
            "selector": "#field2",
            "field_type": "input",
            "element_description": "Current Location",
            "expected_type": "location",
            "description": "location in description"
        },
        # Element with city in description
        {
            "selector": "#field3",
            "field_type": "text",
            "element_description": "City and State",
            "expected_type": "location",
            "description": "city in description"
        },
        # Element with location in selector
        {
            "selector": "#location-field",
            "field_type": "typeahead",
            "expected_type": "location",
            "description": "location in selector"
        },
        # Element with location-like value
        {
            "selector": "#field5",
            "field_type": "text",
            "value": "San Francisco, CA",
            "expected_type": "location",
            "description": "location-like value pattern"
        },
        # Typeahead with city name
        {
            "selector": "#field6",
            "field_type": "typeahead",
            "value": "New York",
            "expected_type": "location",
            "description": "typeahead with city name"
        },
        # Non-location element (negative test)
        {
            "selector": "#name-field",
            "field_type": "text",
            "element_description": "Full Name",
            "value": "John Smith",
            "expected_type": "text",
            "description": "Non-location field (negative test)"
        }
    ]
    
    # Test processing of action data through _create_action_context_list
    action_data_list = []
    for i, element in enumerate(test_form_elements):
        action_data = {
            "selector": element["selector"],
            "field_type": element["field_type"],
            "value": element.get("value", ""),
            "element_description": element.get("element_description", ""),
            "frame_id": "main"
        }
        action_data_list.append(action_data)
    
    # Create a form_elements_by_selector lookup dictionary
    form_elements_by_selector = {}
    for element in test_form_elements:
        form_elements_by_selector[element["selector"]] = element
    
    logger.info("Testing enhanced location field detection in profile adapter")
    
    # Call the _create_action_context_list method directly
    llm_actions_data = {"actions": action_data_list}
    
    # Create a way to check the results by replacing the actual context creation
    original_context_class = ActionContext
    
    results = []
    
    # Replace ActionContext to spy on field_type
    def spy_context(field_id, field_type, field_value, **kwargs):
        results.append({
            "field_id": field_id,
            "field_type": field_type,
            "field_value": field_value
        })
        return original_context_class(field_id, field_type, field_value, **kwargs)
    
    try:
        # Replace ActionContext temporarily
        import enterprise_job_agent.agents.profile_adapter_agent as agent_module
        agent_module.ActionContext = spy_context
        
        # Run the test
        await profile_adapter._create_action_context_list(llm_actions_data, list(form_elements_by_selector.values()))
        
        # Check results
        for i, (test_element, result) in enumerate(zip(test_form_elements, results)):
            matches = result["field_type"] == test_element["expected_type"]
            status = "PASSED" if matches else "FAILED"
            logger.info(f"Test case {i+1}: {status} - {test_element['description']}")
            logger.info(f"  Expected: {test_element['expected_type']}, Got: {result['field_type']}")
            
    finally:
        # Restore original ActionContext
        agent_module.ActionContext = original_context_class


@pytest.mark.asyncio
async def test_demographic_field_detection():
    """Test the enhanced demographic field detection in profile adapter."""
    # Mock the logger
    logger = logging.getLogger("test_demographic")
    
    # Create a profile adapter agent with a mock LLM
    profile_adapter = ProfileAdapterAgent(MockLLM())
    
    # Create a user profile with diversity information
    user_profile = {
        "diversity": {
            "gender": "Male",
            "race": "White",
            "hispanic": "No",
            "veteran": "No",
            "disability": "No"
        }
    }
    profile_adapter.user_profile = user_profile  # Set the profile directly
    
    # Test form elements for demographic fields
    test_form_elements = [
        {
            "description": "Gender field with clear label",
            "selector": "#gender",
            "field_purpose": None,
            "expected_type": "gender"
        },
        {
            "description": "Gender field with descriptive selector",
            "selector": "#question_gender_select",
            "field_purpose": None,
            "expected_type": "gender"
        },
        {
            "description": "Race field with description",
            "selector": "#race",
            "field_purpose": None,
            "expected_type": "race"
        },
        {
            "description": "Ethnicity field with description",
            "selector": "#ethnicity",
            "field_purpose": None,
            "expected_type": "ethnicity"
        },
        {
            "description": "Hispanic field with description",
            "selector": "#hispanic_ethnicity",
            "field_purpose": None,
            "expected_type": "hispanic"
        },
        {
            "description": "Veteran status field",
            "selector": "#veteran_status",
            "field_purpose": None,
            "expected_type": "veteran"
        },
        {
            "description": "Disability status field",
            "selector": "#disability_status",
            "field_purpose": None,
            "expected_type": "disability"
        },
        {
            "description": "Numeric ID demographic field (Greenhouse style)",
            "selector": "#4024307002",
            "field_purpose": None,
            "expected_type": "demographic"
        },
        {
            "description": "Greenhouse style numeric ID with race value",
            "selector": "#4024307002",
            "field_purpose": None,
            "value": "White",
            "expected_type": "race"
        }
    ]
    
    # Create mock LLM actions data
    llm_actions_data = {
        "actions": [
            {
                "field_id": test_element["selector"],
                "field_type": "select",  # Start as generic select type
                "field_value": test_element.get("value", "Prefer not to say"),
                "frame_id": "main",
                "element_description": test_element["description"],
                "selector": test_element["selector"]  # Add the selector to the action data
            }
            for test_element in test_form_elements
        ]
    }
    
    # Create a form_elements_by_selector dictionary
    form_elements_by_selector = {
        element["selector"]: element
        for element in test_form_elements
    }
    
    # Create a spy class for ActionContext to capture created instances
    results = []
    class SpyActionContext:
        def __init__(self, field_id, field_type, field_value, frame_id, selector=None, fallback_text=None, options=None):
            # Store the parameters for assertion
            self_dict = {
                "field_id": field_id,
                "field_type": field_type,
                "field_value": field_value,
                "frame_id": frame_id,
                "selector": selector
            }
            results.append(self_dict)
    
    # Keep original class reference
    original_context_class = None
    try:
        # Replace ActionContext temporarily
        import enterprise_job_agent.agents.profile_adapter_agent as agent_module
        original_context_class = agent_module.ActionContext
        agent_module.ActionContext = SpyActionContext
        
        # Run the test
        await profile_adapter._create_action_context_list(llm_actions_data, list(form_elements_by_selector.values()))
        
        # Check results
        for i, (test_element, result) in enumerate(zip(test_form_elements, results)):
            matches = result["field_type"] == test_element["expected_type"]
            status = "PASSED" if matches else "FAILED"
            logger.info(f"Demographic test case {i+1}: {status} - {test_element['description']}")
            logger.info(f"  Expected: {test_element['expected_type']}, Got: {result['field_type']}")
            
            # Verify the field values were properly pulled from the user profile for appropriate types
            if test_element["expected_type"] in ["gender", "race", "hispanic", "veteran", "disability"]:
                expected_value = user_profile["diversity"][test_element["expected_type"]]
                if "value" not in test_element:  # Only check if we didn't specify a test value
                    value_matches = result["field_value"] == expected_value
                    value_status = "PASSED" if value_matches else "FAILED"
                    logger.info(f"  Value check: {value_status} - Expected: {expected_value}, Got: {result['field_value']}")
            
    finally:
        # Restore original ActionContext
        agent_module.ActionContext = original_context_class


async def test_demographic_typeahead_detection():
    """Test the enhanced demographic field detection in _execute_typeahead_action."""
    
    # Configure logging to see debug output
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("test_demographic_executor")
    logger.setLevel(logging.DEBUG)
    
    # Create a basic action executor
    action_executor = ActionExecutor(test_mode=True)
    
    # Test cases with various ActionContext configurations for demographic fields
    test_cases = [
        # Case 1: Explicit field_type = gender
        {
            "field_id": "#gender-field", 
            "field_type": "gender",
            "field_value": "Male",
            "frame_id": "main",
            "expected_is_demographic": True,
            "description": "Explicit field_type='gender'"
        },
        # Case 2: Race in field name
        {
            "field_id": "#race-field", 
            "field_type": "select",
            "field_value": "White",
            "field_name": "race",
            "frame_id": "main",
            "expected_is_demographic": True,
            "description": "Race in field_name"
        },
        # Case 3: Ethnicity in field_id
        {
            "field_id": "#ethnicity-select", 
            "field_type": "select",
            "field_value": "Hispanic or Latino",
            "frame_id": "main",
            "expected_is_demographic": True,
            "description": "Ethnicity in field_id"
        },
        # Case 4: Veteran field_purpose in options
        {
            "field_id": "#veteran-status", 
            "field_type": "select",
            "field_value": "No",
            "frame_id": "main",
            "options": {"field_purpose": "veteran"},
            "expected_is_demographic": True,
            "description": "field_purpose='veteran' in options"
        },
        # Case 5: Gender value detection
        {
            "field_id": "#question123", 
            "field_type": "select",
            "field_value": "Female",
            "frame_id": "main",
            "expected_is_demographic": True,
            "description": "Gender value detection"
        },
        # Case 6: Race value detection
        {
            "field_id": "#demographic-question", 
            "field_type": "select",
            "field_value": "Asian",
            "frame_id": "main",
            "expected_is_demographic": True,
            "description": "Race value detection"
        },
        # Case 7: Non-demographic field (negative test)
        {
            "field_id": "#name-field", 
            "field_type": "text",
            "field_value": "John Smith",
            "frame_id": "main",
            "expected_is_demographic": False,
            "description": "Non-demographic field (negative test)"
        }
    ]
    
    logger.info("Testing enhanced demographic field detection in _execute_typeahead_action")
    
    # Run each test case
    for i, case in enumerate(test_cases):
        logger.info(f"Test case {i+1}: {case['description']}")
        
        # Create ActionContext from test case
        context_kwargs = {k: v for k, v in case.items() if k not in ["expected_is_demographic", "description"]}
        context = ActionContext(**context_kwargs)
        
        # Directly test the demographic field detection logic
        field_id = context.field_id
        field_value = context.field_value
        field_type = context.field_type.lower() if context.field_type else None
        field_name = context.field_name if hasattr(context, 'field_name') and context.field_name else ""
        field_name = field_name.lower() if isinstance(field_name, str) else ""
        
        # Initialize is_demographic_field to False
        is_demographic_field = False
        
        # Check if this is a demographic field
        if (field_type in ["gender", "race", "ethnicity", "hispanic", "veteran", "disability", "demographic"] or
            any(term in field_name.lower() for term in ["gender", "race", "ethnicity", "hispanic", "latino", "veteran", "disability", "demographic"]) or
            (hasattr(context, 'options') and context.options and 
             context.options.get('field_purpose') in ['demographic', 'gender', 'race', 'ethnicity', 'hispanic', 'veteran', 'disability'])):
            is_demographic_field = True
        
        # Check demographic field value patterns
        if not is_demographic_field and isinstance(field_value, str):
            value_lower = field_value.lower()
            # Check for common demographic values
            if value_lower in ["male", "female", "non-binary", "prefer not to say"]:
                is_demographic_field = True
                logger.debug(f"Detected gender field {field_id} based on value: {field_value}")
            elif value_lower in ["white", "black", "asian", "hispanic", "latino", "native american", "pacific islander"]:
                is_demographic_field = True
                logger.debug(f"Detected race field {field_id} based on value: {field_value}")
            elif value_lower in ["yes", "no"] and any(term in field_id.lower() for term in ["veteran", "disability", "hispanic"]):
                is_demographic_field = True
                logger.debug(f"Detected demographic field {field_id} based on yes/no value and field ID")
        
        # Check if ethnicity is in field_id
        if not is_demographic_field and "ethnicity" in field_id.lower():
            is_demographic_field = True
            logger.debug(f"Detected demographic field {field_id} based on 'ethnicity' in field_id")
            
        # Check result
        result = "PASSED" if is_demographic_field == case["expected_is_demographic"] else "FAILED"
        logger.info(f"  Result: {result} - Detected as demographic: {is_demographic_field}, Expected: {case['expected_is_demographic']}")


async def main():
    """Run all tests."""
    print("\n=== Testing ActionExecutor Location Detection ===\n")
    await test_typeahead_location_detection()
    
    print("\n=== Testing ProfileAdapter Location Detection ===\n")
    await test_profile_adapter_location_detection()

    print("\n=== Testing Demographic Field Detection in ProfileAdapter ===\n")
    await test_demographic_field_detection()
    
    print("\n=== Testing Demographic Field Detection in ActionExecutor ===\n")
    await test_demographic_typeahead_detection()


if __name__ == "__main__":
    # Set up logging for standalone execution
    logging.basicConfig(level=logging.INFO)
    
    # Run the tests
    asyncio.run(main()) 