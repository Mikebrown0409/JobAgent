"""Application Executor Agent for filling and submitting job applications."""

import logging
import asyncio
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from crewai import Agent

from enterprise_job_agent.core.action_executor import ActionExecutor, ActionContext
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.tools.field_identifier import FieldInfo, FieldType

logger = logging.getLogger(__name__)

@dataclass
class ExecutionResult:
    """Result of an execution operation."""
    success: bool
    stage_name: str
    field_results: Dict[str, Tuple[bool, Optional[str]]]
    error: Optional[str] = None

SYSTEM_PROMPT = """You are an expert Application Execution Specialist focusing on job applications.

TASK:
Execute form filling operations with precision and adaptability to complete job applications successfully.

YOUR EXPERTISE:
- Executing form filling strategies with technical precision
- Navigating complex multi-page application flows
- Handling all form field types (text, dropdowns, checkboxes, file uploads)
- Overcoming common application obstacles and validation issues
- Adapting to unexpected form behaviors

APPROACH:
1. Follow a strategic sequence (required fields first, then important fields, finally optional fields)
2. Handle each field type with appropriate techniques
3. Verify input success before proceeding
4. Detect and recover from errors immediately
5. Ensure all required fields are completed before submission

TECHNICAL CAPABILITIES:
- Text inputs: Clear and accurate data entry
- Dropdowns: Find closest matching option using fuzzy matching
- Checkboxes/Radio buttons: Select appropriate values
- File uploads: Ensure proper file paths and formats
- Specialized fields: Format properly (dates, phone numbers, etc.)
- iframe handling: Navigate between frames when needed

ALWAYS STRUCTURE YOUR EXECUTION PLAN AS JSON following the exact schema provided in the task.
"""

class ApplicationExecutorAgent:
    """Creates an agent specialized in form filling and submission."""
    
    def __init__(self, action_executor: Optional[ActionExecutor] = None, logger=None):
        """Initialize the application executor agent.
        
        Args:
            action_executor: Action executor for form manipulation
            logger: Optional logger instance
        """
        self.action_executor = action_executor or ActionExecutor()
        self.logger = logger or logging.getLogger(__name__)
        
    def set_test_mode(self, test_mode: bool = True):
        """Set the test mode flag.
        
        Args:
            test_mode: Whether to run in test mode
        """
        if hasattr(self.action_executor, 'set_test_mode'):
            self.action_executor.set_test_mode(test_mode)
    
    @staticmethod
    def create(
        llm: Any,
        tools: List[Any] = None,
        verbose: bool = False
    ) -> Agent:
        """Create an Application Executor Agent."""
        return Agent(
            role="Application Execution Specialist",
            goal="Execute job applications with precision, overcoming obstacles and ensuring completion",
            backstory="""You are an expert in executing complex web-based job applications.
            You have deep technical knowledge of browser automation and form interactions.
            Your methodical approach ensures applications are filled correctly and completely,
            even when encountering unexpected challenges or unusual form structures.""",
            verbose=verbose,
            allow_delegation=False,
            tools=tools or [],
            llm=llm,
            system_prompt=SYSTEM_PROMPT
        )
    
    async def execute_plan(
        self,
        profile_mapping: Dict[str, Any],
        form_structure: Dict[str, Any],
        test_mode: bool = True
    ) -> Dict[str, Any]:
        """Execute the field population plan.
        
        Args:
            profile_mapping: Profile to form mapping
            form_structure: Form structure data
            test_mode: Whether to run in test mode
            
        Returns:
            Execution results
        """
        # Extract field mappings
        field_mappings = profile_mapping.get("field_mappings", [])
        
        # Initialize results
        field_results = []
        fields_filled = 0
        fields_failed = 0
        field_type_stats = {}
        
        # Track execution by field type
        for field_mapping in field_mappings:
            field_id = field_mapping.get("field_id")
            value = field_mapping.get("value", "")
            
            # Skip empty fields or recaptcha
            if not field_id or "recaptcha" in field_id.lower():
                continue
            
            # Get field type
            field_type = self._get_field_type(field_id, form_structure)
            
            # Initialize stats for this field type if not already tracked
            if field_type not in field_type_stats:
                field_type_stats[field_type] = {"total": 0, "success": 0}
            
            # Increment total count for this field type
            field_type_stats[field_type]["total"] += 1
            
            # Execute the field
            result = await self._execute_field(field_id, field_type, value, form_structure)
            
            # Set common fields for tracking
            result_with_meta = {
                "field_id": field_id,
                "field_type": field_type,
                "value": value,
                "success": result.get("success", False),
                "error": result.get("error", "")
            }
            
            # Update statistics
            if result.get("success", False):
                fields_filled += 1
                field_type_stats[field_type]["success"] += 1
            else:
                fields_failed += 1
            
            # Add result to tracking
            field_results.append(result_with_meta)
            
            # Short sleep between fields to avoid overwhelming the browser
            await asyncio.sleep(0.2)
        
        # Construct the final results
        execution_results = {
            "success": fields_failed == 0,
            "field_results": field_results,
            "fields_filled": fields_filled,
            "fields_failed": fields_failed,
            "field_type_stats": field_type_stats,
            "test_mode": test_mode
        }
        
        return execution_results
    
    def _determine_field_type(self, field_id: str, form_data: Dict[str, Any]) -> str:
        """Determine the field type from form data."""
        # List of common dropdown field patterns
        dropdown_patterns = [
            "school", "degree", "discipline", "education", "university", 
            "location", "country", "state", "city", "ethnicity", 
            "gender", "veteran_status", "disability_status", "race",
            "major", "title", "role", "position", "department"
        ]
        
        # First check if this is a commonly recognized dropdown field by pattern
        field_name_lower = field_id.lower()
        if any(pattern in field_name_lower for pattern in dropdown_patterns):
            # Check if we have options for this field - strong indicator it's a dropdown
            options = self._get_dropdown_options(field_id, form_data)
            if options:
                self.logger.debug(f"Field {field_id} identified as select based on pattern and available options")
                return "select"
            
            # Additional validation - check field structure for dropdown indicators
            # Check form elements
            for element in form_data.get("form_elements", []):
                if element.get("id") == field_id:
                    # Direct indicators in the element
                    if element.get("type") == "select" or "options" in element:
                        self.logger.debug(f"Field {field_id} identified as select from element structure")
                        return "select"
                    # Check for dropdown class indicators
                    element_class = element.get("class", "").lower()
                    if any(class_indicator in element_class for class_indicator in ["dropdown", "select", "combo"]):
                        self.logger.debug(f"Field {field_id} identified as select from class indicators")
                        return "select"
            
            # Even without direct evidence, education and location fields are almost always dropdowns
            high_confidence_dropdown_patterns = ["school", "degree", "discipline", "university", "education", "country", "state"]
            if any(pattern in field_name_lower for pattern in high_confidence_dropdown_patterns):
                self.logger.debug(f"Field {field_id} identified as select with high confidence based on naming pattern")
                return "select"
        
        # First check form_elements for direct type information
        for element in form_data.get("form_elements", []):
            if element.get("id") == field_id:
                element_type = element.get("type", "text")
                
                # Check for <select> tag or presence of options
                if element_type == "select" or "options" in element:
                    self.logger.debug(f"Field {field_id} identified as select from form_elements")
                    return "select"
                
                return element_type
        
        # Check in sections if available
        if "form_structure" in form_data:
            for section in form_data.get("form_structure", {}).get("sections", []):
                for field in section.get("fields", []):
                    if field.get("id") == field_id:
                        field_type = field.get("type", "text")
                        
                        # Check for <select> tag or presence of options
                        if field_type == "select" or "options" in field:
                            self.logger.debug(f"Field {field_id} identified as select from form_structure")
                            return "select"
                        
                        # Check field label for dropdown indicators
                        field_label = field.get("label", "").lower()
                        if field_label and any(pattern in field_label for pattern in dropdown_patterns):
                            self.logger.debug(f"Field {field_id} identified as select from label pattern: {field_label}")
                            return "select"
                            
                        return field_type
        
        # Look at HTML element tag if available
        if "element_tags" in form_data:
            element_tags = form_data.get("element_tags", {})
            if field_id in element_tags:
                tag = element_tags[field_id].lower()
                if tag == "select":
                    self.logger.debug(f"Field {field_id} identified as select from element_tags")
                    return "select"
                elif tag == "input":
                    input_type = form_data.get("input_types", {}).get(field_id, "text")
                    if input_type == "file":
                        return "file"
                    elif input_type in ["checkbox", "radio"]:
                        return "checkbox"
        
        # Check for HTML structure indicators
        html_structure = form_data.get("html_structure", {})
        if field_id in html_structure:
            field_html = html_structure.get(field_id, "").lower()
            if field_html and any(indicator in field_html for indicator in ["<select", "dropdown", "combobox"]):
                self.logger.debug(f"Field {field_id} identified as select from HTML structure")
                return "select"
            
        # Default to text
        return "text"
    
    def _get_selector_for_field(self, field_id: str, form_data: Dict[str, Any]) -> Optional[str]:
        """Get the selector for a field from form data."""
        # Check if the field has specific selector strategies in form_structure
        if "form_structure" in form_data:
            for section in form_data.get("form_structure", {}).get("sections", []):
                for field in section.get("fields", []):
                    if field.get("id") == field_id:
                        # Use the first selector strategy if available
                        strategies = field.get("selector_strategies", [])
                        
                        # School, degree, and discipline fields often need special handling
                        is_education_field = any(edu_field in field_id for edu_field in ["school", "degree", "discipline"])
                        
                        if strategies:
                            if len(strategies) > 1:
                                # If it's an education field or dropdown, try to find a better selector than just the ID
                                if is_education_field or field.get("type") == "select" or "options" in field:
                                    # Try different selector strategies
                                    for strategy in strategies:
                                        # Prefer selectors that look like complete CSS selectors rather than just IDs
                                        if strategy.startswith('#') and '--' in strategy:
                                            return strategy
                                        elif '[name=' in strategy or '[id=' in strategy:
                                            return strategy
                                
                                # Default to the second strategy (usually the ID selector)
                                return strategies[1]
                            else:
                                return strategies[0]
        
        # Check form_elements
        form_elements = form_data.get("form_elements", [])
        for element in form_elements:
            if element.get("id") == field_id:
                selector = element.get("selector")
                if selector:
                    return selector
                
                # For dropdowns, try to find a more specific selector
                if element.get("type") == "select" or "options" in element:
                    selectors = element.get("selector_strategies", [])
                    if selectors and len(selectors) > 0:
                        return selectors[0]
                
                return f"#{field_id}"  # Default to ID selector
        
        # Fall back to a simple ID selector
        return f"#{field_id}"

    def _importance_to_float(self, importance: str) -> float:
        """Convert importance string to float value."""
        importance_map = {
            "high": 1.0,
            "medium": 0.5,
            "low": 0.1
        }
        return importance_map.get(importance.lower(), 0.1)

    @staticmethod
    def create_execution_prompt(
        form_data: Dict[str, Any],
        field_mappings: Dict[str, Any],
        test_mode: bool = False
    ) -> str:
        """
        Create a prompt for executing a job application.
        
        Args:
            form_data: Form data and structure
            field_mappings: Field mappings from profile
            test_mode: Whether to run in test mode
            
        Returns:
            Execution prompt for the LLM
        """
        mode = "TEST MODE" if test_mode else "LIVE MODE"
        
        task_part = f"""
        TASK:
        Execute the following job application form in {mode}.
        """
        
        form_part = f"""
        FORM STRUCTURE:
        {json.dumps(form_data, indent=2)}
        """
        
        mappings_part = f"""
        FIELD MAPPINGS:
        {json.dumps(field_mappings, indent=2)}
        """
        
        instructions_part = """
        INSTRUCTIONS:
        1. Analyze the form structure and field mappings
        2. Create an execution plan that fills out the form efficiently
        3. Return your plan as a JSON array of steps, where each step has:
           - action: The action to take (e.g., "fill", "select", "upload")
           - field_id: The ID of the field to interact with
           - value: The value to input or select
           - options: Optional parameters for the action
        
        Example output format:
        [
            {
                "action": "fill",
                "field_id": "name",
                "value": "John Smith",
                "options": {}
            },
            {
                "action": "select",
                "field_id": "education",
                "value": "Bachelor's Degree",
                "options": {"exact_match": true}
            }
        ]
        """
        
        return task_part + form_part + mappings_part + instructions_part 

    def _get_dropdown_options(self, field_id: str, form_data: Dict[str, Any]) -> List[str]:
        """Get dropdown options for a field if available."""
        # Check form_elements
        form_elements = form_data.get("form_elements", [])
        for element in form_elements:
            if element.get("id") == field_id and "options" in element:
                return element.get("options", [])
        
        # Check in sections if available
        if "form_structure" in form_data:
            for section in form_data.get("form_structure", {}).get("sections", []):
                for field in section.get("fields", []):
                    if field.get("id") == field_id and "options" in field:
                        return field.get("options", [])
        
        # Look in validation_data
        if "validation_data" in form_data:
            field_validation = form_data.get("validation_data", {}).get(field_id, {})
            if "options" in field_validation:
                return field_validation.get("options", [])
        
        return [] 

    async def _handle_recaptcha_field(self, field_id: str, form_structure: Dict[str, Any]) -> Dict[str, Any]:
        """Handle reCAPTCHA fields specially.
        
        These fields require special handling as they're invisible and filled by the reCAPTCHA service.
        In test mode, we'll skip them; in production, we might attempt some form of workaround.
        
        Args:
            field_id: The field ID
            form_structure: The form structure
            
        Returns:
            Result dictionary
        """
        self.logger.info(f"Detected reCAPTCHA field: {field_id} - marking as handled in test mode")
        return {
            "field_id": field_id,
            "success": True,  # Pretend we handled it in test mode
            "field_type": "recaptcha",
            "value": "[RECAPTCHA FIELD - SKIPPED IN TEST MODE]",
            "error": None
        }

    def _get_field_type(self, field_id: str, form_structure: Dict[str, Any]) -> str:
        """Get the type of a form field from structure.
        
        Args:
            field_id: The field ID
            form_structure: The form structure
            
        Returns:
            Field type (e.g., 'text', 'select', 'file', 'textarea')
        """
        # First check in form_elements list
        if "form_elements" in form_structure:
            for element in form_structure.get("form_elements", []):
                if element.get("id") == field_id:
                    return element.get("type", "text")
        
        # Try to guess from HTML structure
        element_html = form_structure.get("html_structure", {}).get(field_id, "")
        
        if "textarea" in element_html.lower():
            return "textarea"
        elif 'type="file"' in element_html.lower():
            return "file"
        elif 'class="select__input"' in element_html.lower() or 'role="combobox"' in element_html.lower():
            return "select"
        elif "recaptcha" in field_id.lower() or "captcha" in field_id.lower():
            return "recaptcha"
        else:
            return "text" # Default to text input 

    async def _execute_field(self, field_id: str, field_type: str, value: str, form_structure: Dict) -> Dict[str, Any]:
        """Execute an action for a specific field.
        
        Args:
            field_id: ID of the field
            field_type: Type of the field (text, select, etc.)
            value: Value to set
            form_structure: Form structure data
            
        Returns:
            Dictionary with execution result
        """
        try:
            # Get the field's frame ID if applicable
            frame_id = self._get_field_frame(field_id, form_structure)
            
            # Format selector properly for CSS
            selector = f"#{field_id}"
            # Use attribute selector for numeric IDs
            if field_id.isdigit() or (field_id and field_id[0].isdigit()):
                selector = f"[id='{field_id}']"
            
            # Execute appropriate action based on field type
            if field_type == "select":
                success = await self.action_executor.execute_action("select", selector, value, frame_id)
                if not success:
                    self.logger.error(f"Failed to execute select for field {field_id} of type {field_type}")
                    return {"success": False, "error": "Select action failed"}
                else:
                    self.logger.info(f"Successfully executed select for field {field_id} of type {field_type}")
                    return {"success": True}
                    
            elif field_type == "checkbox":
                # Convert value to boolean
                checked = self._parse_bool(value)
                success = await self.action_executor.execute_action("checkbox", selector, checked, frame_id)
                if not success:
                    self.logger.error(f"Failed to execute checkbox for field {field_id} of type {field_type}")
                    return {"success": False, "error": "Checkbox action failed"}
                else:
                    self.logger.info(f"Successfully executed checkbox for field {field_id} of type {field_type}")
                    return {"success": True}
                    
            elif field_type == "file":
                # Handle file uploads
                success = await self.action_executor.execute_action("upload", selector, value, frame_id)
                if not success:
                    self.logger.error(f"Failed to execute file for field {field_id} of type {field_type}")
                    return {"success": False, "error": "File upload failed"}
                else:
                    self.logger.info(f"Successfully executed file for field {field_id} of type {field_type}")
                    return {"success": True}
                    
            elif field_type == "textarea":
                # Handle multiline text
                success = await self.action_executor.execute_action("fill", selector, value, frame_id)
                if not success:
                    self.logger.error(f"Failed to execute textarea for field {field_id} of type {field_type}")
                    return {"success": False, "error": "Text area fill failed"}
                else:
                    self.logger.info(f"Successfully executed textarea for field {field_id} of type {field_type}")
                    return {"success": True}
                    
            else:
                # Default to text input
                success = await self.action_executor.execute_action("fill", selector, value, frame_id)
                if not success:
                    self.logger.error(f"Failed to execute text for field {field_id} of type {field_type}")
                    return {"success": False, "error": "Text fill failed"}
                else:
                    self.logger.info(f"Successfully executed text for field {field_id} of type {field_type}")
                    return {"success": True}
                    
        except Exception as e:
            self.logger.error(f"Error executing field {field_id}: {str(e)}")
            return {"success": False, "error": str(e)} 

    def _get_field_frame(self, field_id: str, form_structure: Dict) -> Optional[str]:
        """Get the frame ID for a field if it exists in a frame.
        
        Args:
            field_id: ID of the field
            form_structure: Form structure data
            
        Returns:
            Frame ID or None if field is in the main frame
        """
        # Check if form structure has frame data
        if "frames" in form_structure:
            # Search for the field in each frame
            for frame_id, frame_data in form_structure.get("frames", {}).items():
                if "fields" in frame_data:
                    # Check if field exists in this frame's fields
                    if field_id in frame_data["fields"]:
                        return frame_id
        
        # Field is in the main frame
        return None
        
    def _parse_bool(self, value: Any) -> bool:
        """Parse a value as boolean.
        
        Args:
            value: Value to parse
            
        Returns:
            Boolean value
        """
        if isinstance(value, bool):
            return value
            
        if isinstance(value, str):
            return value.lower() in ("yes", "true", "t", "1", "on", "y")
            
        if isinstance(value, (int, float)):
            return bool(value)
            
        # Default to False for None or other types
        return False 