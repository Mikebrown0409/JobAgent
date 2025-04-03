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
                    "options": {}
                })
            
            # Execute each step
            results = []
            for step in execution_steps:
                try:
                    selector = self._get_selector_for_field(step["field_id"], form_data)
                    if not selector:
                        self.logger.warning(f"No selector found for field {step['field_id']}")
                        results.append({
                            "field_id": step["field_id"],
                            "success": False,
                            "error": "No selector found"
                        })
                        continue
                    
                    # Execute the appropriate form interaction
                    if step["action"] == "fill":
                        await self.action_executor.form_interaction.fill_field(
                            selector,
                            str(step["value"])
                        )
                    elif step["action"] == "select":
                        await self.action_executor.form_interaction.select_option(
                            selector,
                            step["value"],
                            step.get("options", {}).get("options", [])
                        )
                    elif step["action"] == "check":
                        await self.action_executor.form_interaction.set_checkbox(
                            selector,
                            bool(step["value"])
                        )
                    elif step["action"] == "upload":
                        await self.action_executor.form_interaction.upload_file(
                            selector,
                            str(step["value"])
                        )
                    
                    results.append({
                        "field_id": step["field_id"],
                        "success": True,
                        "value": step["value"]
                    })
                    self.logger.info(f"Successfully executed {step['action']} for field {step['field_id']}")
                    
                except Exception as e:
                    self.logger.error(f"Error executing {step['action']} for field {step['field_id']}: {str(e)}")
                    results.append({
                        "field_id": step["field_id"],
                        "success": False,
                        "error": str(e)
                    })
            
            # Determine overall success
            success = any(r["success"] for r in results)
            return {
                "success": success,
                "field_results": results,
                "fields_filled": len([r for r in results if r["success"]]),
                "fields_failed": len([r for r in results if not r["success"]])
            }
            
        except Exception as e:
            self.logger.error(f"Error in execute_plan: {str(e)}")
            return {
                "success": False,
                "error": f"Execution plan failed: {str(e)}"
            }
    
    def _determine_field_type(self, field_id: str, form_data: Dict[str, Any]) -> str:
        """Determine the field type from form data."""
        # First check form_elements
        form_elements = form_data.get("form_elements", [])
        for element in form_elements:
            if element.get("id") == field_id:
                return element.get("type", "text")
        
        # Check in sections if available
        if "form_structure" in form_data:
            for section in form_data.get("form_structure", {}).get("sections", []):
                for field in section.get("fields", []):
                    if field.get("id") == field_id:
                        return field.get("type", "text")
        
        # Default to text
        return "text"
    
    def _get_selector_for_field(self, field_id: str, form_data: Dict[str, Any]) -> Optional[str]:
        """Get the selector for a field from form data."""
        # Check form_elements
        form_elements = form_data.get("form_elements", [])
        for element in form_elements:
            if element.get("id") == field_id:
                return f"#{field_id}"  # Default to ID selector
        
        # Check in sections if available
        if "form_structure" in form_data:
            for section in form_data.get("form_structure", {}).get("sections", []):
                for field in section.get("fields", []):
                    if field.get("id") == field_id:
                        # Use the first selector strategy if available
                        strategies = field.get("selector_strategies", [])
                        if strategies and len(strategies) > 1:
                            return strategies[1]  # Use the second strategy (usually the ID selector)
                        return f"#{field_id}"  # Default to ID selector
        
        return None

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