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
    
    def __init__(
        self,
        llm: Any,
        action_executor: ActionExecutor,
        diagnostics_manager: Optional[DiagnosticsManager] = None,
        tools: List[Any] = None,
        verbose: bool = False
    ):
        """Initialize the application executor agent.
        
        Args:
            llm: Language model to use
            action_executor: Action executor for form interactions
            diagnostics_manager: Optional diagnostics manager
            tools: List of tools the agent can use
            verbose: Whether to enable verbose output
        """
        self.llm = llm
        self.action_executor = action_executor
        self.diagnostics_manager = diagnostics_manager
        self.verbose = verbose
        self.logger = logging.getLogger(__name__)
        
        self.agent = self.create(llm, tools, verbose)
    
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
    
    async def execute_plan(self, execution_plan: Dict[str, Any], form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a job application plan.
        
        Args:
            execution_plan: Field mappings from profile adapter agent
            form_data: Form data and structure
            
        Returns:
            Dict with execution results
        """
        try:
            self.logger.info("Executing form filling plan")
            
            # Extract field mappings from profile adapter output
            field_mappings = execution_plan.get("field_mappings", [])
            if not field_mappings:
                self.logger.warning("No field mappings found in execution plan")
                return {"success": False, "error": "No field mappings found"}
            
            # Create execution steps directly from field_mappings
            execution_steps = []
            for mapping in field_mappings:
                field_id = mapping.get("field_id")
                value = mapping.get("value")
                
                if not field_id or value is None:
                    continue
                
                # Determine field type from form data
                field_type = self._determine_field_type(field_id, form_data)
                
                # Determine appropriate action based on field type
                action = "fill"
                if field_type == "select":
                    action = "select"
                elif field_type == "checkbox":
                    action = "check"
                elif field_type == "file":
                    action = "upload"
                
                # Add to execution steps
                execution_steps.append({
                    "action": action,
                    "field_id": field_id,
                    "value": value,
                    "options": {},
                    "field_type": field_type  # Add field type for better tracking
                })
            
            # Execute each step
            results = []
            fields_processed = 0
            fields_succeeded = 0
            
            # Track different field types for reporting
            field_type_counts = {
                "select": 0,
                "text": 0,
                "checkbox": 0,
                "file": 0,
                "other": 0
            }
            field_type_success = {
                "select": 0,
                "text": 0,
                "checkbox": 0,
                "file": 0,
                "other": 0
            }
            
            for step in execution_steps:
                try:
                    # Track field types
                    field_type = step.get("field_type", "other")
                    field_type_key = field_type if field_type in field_type_counts else "other"
                    field_type_counts[field_type_key] += 1
                    
                    selector = self._get_selector_for_field(step["field_id"], form_data)
                    if not selector:
                        self.logger.warning(f"No selector found for field {step['field_id']}")
                        results.append({
                            "field_id": step["field_id"],
                            "success": False,
                            "error": "No selector found",
                            "field_type": field_type
                        })
                        continue
                    
                    # Execute the appropriate form interaction
                    fields_processed += 1
                    success = False
                    
                    try:
                        if step["action"] == "fill":
                            success = await self.action_executor.form_interaction.fill_field(
                                selector,
                                str(step["value"])
                            )
                        elif step["action"] == "select":
                            # Get dropdown options if available
                            options = self._get_dropdown_options(step["field_id"], form_data)
                            
                            # Perform selection
                            success = await self.action_executor.form_interaction.select_option(
                                selector,
                                step["value"],
                                options
                            )
                        elif step["action"] == "check":
                            success = await self.action_executor.form_interaction.set_checkbox(
                                selector,
                                bool(step["value"])
                            )
                        elif step["action"] == "upload":
                            success = await self.action_executor.form_interaction.upload_file(
                                selector,
                                str(step["value"])
                            )
                        
                        # Update counters and track result
                        if success:
                            fields_succeeded += 1
                            field_type_success[field_type_key] += 1
                            
                            results.append({
                                "field_id": step["field_id"],
                                "success": True,
                                "value": step["value"],
                                "field_type": field_type
                            })
                            self.logger.info(f"Successfully executed {step['action']} for field {step['field_id']} of type {field_type}")
                        else:
                            # The operation failed but didn't throw an exception
                            results.append({
                                "field_id": step["field_id"],
                                "success": False,
                                "error": f"Action {step['action']} failed without exception",
                                "field_type": field_type
                            })
                            self.logger.error(f"Failed to execute {step['action']} for field {step['field_id']} of type {field_type}")
                        
                    except Exception as e:
                        self.logger.error(f"Error executing {step['action']} for field {step['field_id']}: {str(e)}")
                        results.append({
                            "field_id": step["field_id"],
                            "success": False,
                            "error": str(e),
                            "field_type": step.get("field_type", "other")
                        })
                    
                except Exception as e:
                    self.logger.error(f"Error executing {step['action']} for field {step['field_id']}: {str(e)}")
                    results.append({
                        "field_id": step["field_id"],
                        "success": False,
                        "error": str(e),
                        "field_type": step.get("field_type", "other")
                    })
            
            # Determine overall success - require at least one field filled successfully
            success = fields_succeeded > 0
            
            # Calculate success rate
            success_rate = fields_succeeded / fields_processed if fields_processed > 0 else 0
            
            # Report on field type success rates
            field_type_stats = {}
            for field_type in field_type_counts:
                total = field_type_counts[field_type]
                if total > 0:
                    success_count = field_type_success[field_type]
                    field_type_stats[field_type] = {
                        "total": total,
                        "success": success_count,
                        "rate": success_count / total
                    }
            
            return {
                "success": success,
                "field_results": results,
                "fields_filled": fields_succeeded,
                "fields_failed": fields_processed - fields_succeeded,
                "field_type_stats": field_type_stats,
                "success_rate": success_rate
            }
            
        except Exception as e:
            self.logger.error(f"Error in execute_plan: {str(e)}")
            return {
                "success": False,
                "error": f"Execution plan failed: {str(e)}"
            }
    
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