"""Application Executor Agent for filling and submitting job applications."""

import logging
from typing import Dict, Any, List
from crewai import Agent

logger = logging.getLogger(__name__)

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
    
    @staticmethod
    def create(
        llm: Any,
        tools: List[Any] = None,
        verbose: bool = False
    ) -> Agent:
        """
        Create an Application Executor Agent.
        
        Args:
            llm: Language model to use
            tools: List of tools the agent can use
            verbose: Whether to enable verbose output
            
        Returns:
            Agent instance
        """
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
    
    @staticmethod
    def create_execution_prompt(
        form_structure: Dict[str, Any],
        field_mappings: Dict[str, Any],
        test_mode: bool = False
    ) -> str:
        """
        Create a prompt for executing a job application.
        
        Args:
            form_structure: Analyzed form structure
            field_mappings: Field mappings from profile
            test_mode: Whether to run in test mode
            
        Returns:
            A prompt string for the LLM
        """
        return f"""
        TASK: Create a detailed execution plan for filling and submitting this job application form.
        
        FORM STRUCTURE:
        ```
        {form_structure}
        ```
        
        FIELD MAPPINGS:
        ```
        {field_mappings}
        ```
        
        TEST MODE: {'Yes - Do not actually submit the application' if test_mode else 'No - Proceed with submission'}
        
        EXECUTION REQUIREMENTS:
        
        1. Field Filling Order:
           - Start with high-importance required fields
           - Then handle medium-importance fields
           - Finally complete optional fields
           - Special fields (file uploads) should be handled separately with explicit instructions
        
        2. Specific Handling Per Field Type:
           - Text inputs: Simple value filling
           - Dropdowns: Select closest matching option, ensure dropdown triggers correctly
           - Checkboxes/Radios: Select appropriate values
           - File uploads: Provide exact file paths and upload steps
           - Text areas: Format content with proper line breaks
        
        3. Error Prevention:
           - After each field group, include a verification step
           - Provide fallback values for required fields
           - For dropdowns, include alternative selector strategies
           - For locations or schools, use fuzzy matching with 70% threshold
        
        4. Post-Filling Actions:
           - Verify all required fields are filled
           - Handle any popup confirmation dialogs
           - Scroll to and locate the submit button
           - Execute final submission (if not in test mode)
        
        OUTPUT FORMAT:
        Provide your execution plan as this exact JSON structure:
        {
            "execution_plan": {
                "stages": [
                    {
                        "name": "stage_name",
                        "description": "What this stage accomplishes",
                        "operations": [
                            {
                                "type": "operation_type",
                                "field_id": "target_field_id",
                                "value": "value_to_enter",
                                "selector": "field_selector",
                                "verification": "how to verify success",
                                "fallback": "fallback approach if needed"
                            }
                        ]
                    }
                ],
                "submission": {
                    "should_submit": false,
                    "submit_selector": "selector for submit button",
                    "confirmation_handling": "how to handle confirmation dialogs"
                }
            },
            "error_handling": {
                "common_issues": [
                    {
                        "issue": "potential issue description",
                        "detection": "how to detect this issue",
                        "resolution": "how to resolve this issue"
                    }
                ]
            }
        }
        """ 