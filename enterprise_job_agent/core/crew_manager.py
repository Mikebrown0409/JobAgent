"""Manages the crew of agents for the enterprise job application system."""

import asyncio
import json
import logging
import os
import time
import traceback
from typing import Dict, List, Any, Optional, Tuple, Union
from crewai import Crew, Agent, Task, Process
from crewai.tasks.task_output import TaskOutput

from enterprise_job_agent.core.action_executor import ActionExecutor, ActionContext
from enterprise_job_agent.tools.field_identifier import FieldIdentifier, FieldInfo, FieldType
from enterprise_job_agent.tools.data_formatter import DataFormatter
from enterprise_job_agent.tools.form_interaction import FormInteraction
from enterprise_job_agent.tools.dropdown_matcher import DropdownMatcher
from enterprise_job_agent.agents.profile_adapter_agent import ProfileAdapterAgent
from enterprise_job_agent.agents.application_executor_agent import ApplicationExecutorAgent
from enterprise_job_agent.agents.session_manager_agent import SessionManagerAgent
from enterprise_job_agent.agents.form_analyzer_agent import FormAnalyzerAgent
from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager

logger = logging.getLogger(__name__)

# Define path for failure log
FAILURE_LOG_PATH = "execution_failures.log.json"

def log_execution_failure(job_url: str, failed_op: Dict, error_context: Dict):
    """Logs failed execution step details to a JSON log file."""
    log_entry = {
        "timestamp": time.time(),
        "job_url": job_url,
        "failed_operation": failed_op,
        "error_context": error_context
    }
    try:
        with open(FAILURE_LOG_PATH, "a") as f:
            json.dump(log_entry, f)
            f.write("\n")
    except Exception as e:
        logger.error(f"Failed to write to failure log {FAILURE_LOG_PATH}: {e}")

class JobApplicationCrew:
    """Manages a crew of agents for the job application process."""
    
    def __init__(
        self, 
        llm: Any,
        browser_manager: BrowserManager,
        verbose: bool = False,
        diagnostics_manager: Optional[DiagnosticsManager] = None
    ):
        """Initialize the crew manager."""
        self.llm = llm
        self.browser_manager = browser_manager
        self.verbose = verbose
        self.diagnostics_manager = diagnostics_manager or DiagnosticsManager()
        self.logger = logging.getLogger(__name__)
        
        # Initialize core tools
        self.action_executor = ActionExecutor(
            browser_manager=browser_manager,
            diagnostics_manager=self.diagnostics_manager
        )
        self.dropdown_matcher = DropdownMatcher(
            diagnostics_manager=self.diagnostics_manager,
            match_threshold=0.7  # As specified in project rules
        )
        
        # Initialize specialized agents
        self.session_manager = SessionManagerAgent(
            llm=llm,
            browser_manager=browser_manager,
            diagnostics_manager=self.diagnostics_manager,
            verbose=verbose
        )
        
        self.application_executor = ApplicationExecutorAgent(
            llm=llm,
            action_executor=self.action_executor,
            diagnostics_manager=self.diagnostics_manager,
            verbose=verbose
        )
        
        self.profile_adapter = ProfileAdapterAgent(llm=llm, verbose=verbose)
        
        self.form_analyzer = FormAnalyzerAgent(
            llm=llm,
            diagnostics_manager=self.diagnostics_manager,
            verbose=verbose
        )
        
        # Initialize agent dictionary and crew
        self.agents = {}
        self.tasks = {}
        self.crew = None
        self._initialize_agents()
    
    async def execute_job_application_process(
        self,
        form_data: Dict[str, Any],
        user_profile: Dict[str, Any],
        job_description: Dict[str, Any],
        test_mode: bool = True,
        job_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute the job application process using the initialized agents."""
        try:
            # Check session health
            self.diagnostics_manager.start_stage("session_health_check")
            session_health = await self.session_manager.check_session_health()
            if not session_health:
                self.diagnostics_manager.end_stage(success=False, error="Session health check failed")
                return {"success": False, "error": "Session health check failed"}
            self.diagnostics_manager.end_stage(success=True)
            
            # Initialize session
            self.diagnostics_manager.start_stage("session_initialization")
            session_initialized = await self.session_manager.initialize_session()
            if not session_initialized:
                self.diagnostics_manager.end_stage(success=False, error="Session initialization failed")
                return {"success": False, "error": "Session initialization failed"}
            self.diagnostics_manager.end_stage(success=True)
            
            # Analyze form
            self.diagnostics_manager.start_stage("form_analysis")
            try:
                analyzed_form_data = await self.form_analyzer.analyze_form(
                    form_data=form_data,
                    page_url=job_url,
                    job_details=job_description
                )
                if not analyzed_form_data:
                    self.diagnostics_manager.end_stage(success=False, error="Form analysis failed")
                    return {"success": False, "error": "Form analysis failed"}
                self.diagnostics_manager.end_stage(success=True)
            except Exception as e:
                self.diagnostics_manager.end_stage(success=False, error=str(e))
                raise
            
            # Map profile to form
            self.diagnostics_manager.start_stage("profile_mapping")
            try:
                profile_mapping = await self.profile_adapter.map_profile_to_form(
                    form_structure=analyzed_form_data,
                    user_profile=user_profile,
                    job_description=job_description
                )
                if not profile_mapping:
                    self.diagnostics_manager.end_stage(success=False, error="Profile mapping failed")
                    return {"success": False, "error": "Profile mapping failed"}
                self.diagnostics_manager.end_stage(success=True)
            except Exception as e:
                self.diagnostics_manager.end_stage(success=False, error=str(e))
                raise
            
            # Execute form
            self.diagnostics_manager.start_stage("form_execution")
            try:
                form_executed = await self.application_executor.execute_plan(
                    execution_plan=profile_mapping,
                    form_data=analyzed_form_data
                )
                if not form_executed:
                    self.diagnostics_manager.end_stage_if_active(success=False, error="Form execution failed")
                    return {"success": False, "error": "Form execution failed"}
                
                # Check field success rates
                if "field_type_stats" in form_executed:
                    field_stats = form_executed["field_type_stats"]
                    # Validate that we filled dropdowns successfully
                    select_fields = field_stats.get("select", {})
                    select_total = select_fields.get("total", 0)
                    select_success = select_fields.get("success", 0)
                    
                    # Report on field success rates
                    self.diagnostics_manager.end_stage_if_active(
                        success=True,
                        details={
                            "fields_total": form_executed.get("fields_filled", 0) + form_executed.get("fields_failed", 0),
                            "fields_filled": form_executed.get("fields_filled", 0),
                            "fields_failed": form_executed.get("fields_failed", 0),
                            "field_type_stats": field_stats,
                            "select_fields_total": select_total,
                            "select_fields_success": select_success
                        }
                    )
                else:
                    self.diagnostics_manager.end_stage_if_active(success=True)
            except Exception as e:
                self.diagnostics_manager.end_stage_if_active(success=False, error=str(e))
                raise
            
            return {
                "success": True,
                "form_execution_details": form_executed
            }
            
        except Exception as e:
            self.logger.error(f"Error in job application process: {str(e)}")
            self.logger.error("Traceback:", exc_info=True)
            try:
                if self.diagnostics_manager:
                    self.diagnostics_manager.end_stage_if_active(success=False, error=str(e))
            except Exception as nested_error:
                self.logger.error(f"Error in diagnostics handling: {str(nested_error)}")
            return {"success": False, "error": str(e)}
    
    def _initialize_agents(self):
        """Initialize all the agents needed for the job application process."""
        logger.info("Initializing job application agents")
        
        # Add specialized agents to the dictionary
        self.agents["session_manager"] = self.session_manager.agent
        self.agents["application_executor"] = self.application_executor.agent
        self.agents["form_analyzer"] = self.form_analyzer.agent
        
        # Initialize common kwargs for remaining agents
        agent_kwargs = {
            "allow_delegation": False,
            "verbose": self.verbose,
            "llm": self.llm,
        }
        
        # Create profile adapter agent
        self.agents["profile_adapter"] = Agent(
            role="Profile Mapping Expert",
            goal="Map user profiles to job application forms accurately and effectively",
            backstory="""You are an expert in analyzing and mapping user profiles to job application forms.
            Your deep understanding of both professional profiles and form structures allows you to create
            optimal mappings that maximize the chances of successful applications.""",
            **agent_kwargs
        )
        
        # Create error recovery agent
        self.agents["error_recovery"] = Agent(
            role="Error Recovery Specialist",
            goal="Diagnose and recover from errors in the job application process",
            backstory="""You are an expert in diagnosing and recovering from errors in complex systems.
            Your analytical abilities allow you to identify root causes and develop effective recovery strategies.""",
            **agent_kwargs
        )
        
        logger.info("All agents initialized successfully")

    def create_crew(self):
        """Create a crew with the agents."""
        return Crew(
            agents=list(self.agents.values()),
            verbose=self.verbose,
            process=Process.sequential,  # Use sequential process to ensure dependencies are satisfied
            memory=False,
            cache=True,
        )
    
    async def create_form_analysis_task(self, form_data):
        """Create a task for form analysis."""
        # First analyze form structure using our tools
        field_info = await self.action_executor.analyze_form_structure(form_data)
        
        # Create a more detailed analysis for the agent
        analysis_prompt = f"""
        Analyze the following job application form structure:
        
        Form Data:
        {json.dumps(form_data, indent=2)}
        
        Field Analysis Results:
        {json.dumps({
            field_id: {
                "type": info.field_type.name,
                "required": info.required,
                "importance": info.importance,
                "label": info.label,
                "validation": info.validation_rules if hasattr(info, 'validation_rules') else None
            }
            for field_id, info in field_info.items()
        }, indent=2)}
        
        Your task is to:
        1. Review the automated field analysis and validate its accuracy
        2. Identify any patterns or relationships between fields
        3. Suggest optimal field filling order based on dependencies
        4. Identify potential challenges (e.g., complex dropdowns, file uploads)
        5. Recommend strategies for handling any special cases
        
        Focus on:
        - Required vs optional fields and their strategic importance
        - Fields that may need special handling (schools, locations)
        - Multi-step or dependent field relationships
        - File upload requirements and formats
        - Any fields that might benefit from AI-powered content generation
        
        Your analysis will help the Field Mapping Specialist create optimal
        mappings between user profile data and form fields.
        """
        
        task = Task(
            description=analysis_prompt,
            agent=self.agents["form_analyzer"],
            expected_output="A detailed analysis of the form structure and field relationships."
        )
        
        return task
    
    async def create_error_recovery_task(self, error_context: str) -> Task:
        """Create a task for error recovery."""
        recovery_prompt = f"""
        Analyze the following error and develop a recovery strategy:
        
        Error Context:
        {error_context}
        
        Your task is to:
        1. Diagnose the root cause of the error
        2. Classify the error type and severity
        3. Develop a recovery strategy
        4. Determine if retry is possible
        5. Suggest preventive measures for future
        
        Focus on:
        - Identifying the specific failure point
        - Understanding the error context
        - Determining if the error is recoverable
        - Suggesting specific recovery steps
        - Recommending validation or checks to prevent similar errors
        """
        
        task = Task(
            description=recovery_prompt,
            agent=self.agents["error_recovery"],
            expected_output="A recovery strategy with retry recommendation."
        )
        
        return task
        
    async def create_profile_mapping_task(self, form_data: Dict[str, Any], user_profile: Dict[str, Any], job_description: Dict[str, Any]) -> Task:
        """Create a task for mapping user profile to form fields."""
        mapping_prompt = f"""
        Create optimal mappings between the user profile and form fields:
        
        Form Data:
        {json.dumps(form_data, indent=2)}
        
        User Profile:
        {json.dumps(user_profile, indent=2)}
        
        Job Description:
        {json.dumps(job_description, indent=2)}
        
        Your task is to:
        1. Analyze the form fields and user profile data
        2. Create optimal mappings between profile data and form fields
        3. Handle any special field requirements or transformations
        4. Ensure required fields are mapped
        5. Suggest default values for unmapped required fields
        
        Focus on:
        - Accurate mapping of profile data to form fields
        - Proper formatting and validation of mapped values
        - Handling complex fields (dropdowns, multi-select)
        - Suggesting AI-generated content where appropriate
        - Maintaining data consistency and accuracy
        """
        
        task = Task(
            description=mapping_prompt,
            agent=self.agents["profile_adapter"],
            expected_output="A mapping of user profile data to form fields."
        )
        
        return task
    
    def create_execution_plan_task(self, form_data, profile_mapping, test_mode=False):
        """Create a task for generating an execution plan."""
        
        # Extract form data
        form_data_str = json.dumps(form_data)[:1000] + "..." if len(json.dumps(form_data)) > 1000 else json.dumps(form_data)
        
        # Extract profile mapping
        profile_mapping_str = json.dumps(profile_mapping)[:1000] + "..." if len(json.dumps(profile_mapping)) > 1000 else json.dumps(profile_mapping)
        
        # TEST mode message
        test_mode_str = "Yes - Do not actually submit the application" if test_mode else "No - Execute the full application"
        
        # Define schema separately to avoid deep nesting in format string
        execution_plan_schema = """
{
  "execution_plan": {
    "stages": [
      {
        "name": "stage_name",
        "description": "What this stage accomplishes",
        "operations": [
          {
            "type": "fill | click | select_custom_dropdown | upload_file | set_checkbox_radio",
            "field_id": "Optional logical field ID",
            "selector": "CSS selector for the target element",
            "value": "Value to enter/select/upload path",
            "trigger_selector": "Selector for dropdown trigger",
            "options_selector": "Selector for dropdown options",
            "should_be_checked": true,
            "frame_identifier": "Optional frame name/ID/URL part",
            "verification": "Description of how to verify success",
            "fallback": "Description of fallback approach"
          }
        ]
      }
    ],
    "submission": {
      "should_submit": false,
      "submit_selector": "Selector for submit button",
      "confirmation_handling": "Description of confirmation handling"
    }
  },
  "error_handling": {
    "common_issues": [
      {
        "issue": "Potential issue description",
        "detection": "How to detect this issue",
        "resolution": "How to resolve this issue"
      }
    ]
  }
}
"""
        
        # Create a detailed description for the task
        description = f"""
Generate a detailed execution plan for filling and submitting the job application form, based on:

FORM ANALYSIS:
```json
{form_data_str}
```

PROFILE MAPPING:
```json
{profile_mapping_str}
```

TEST MODE: {test_mode_str}

INSTRUCTIONS FOR FIELD TYPE DETECTION AND HANDLING:

1. Carefully examine each field's properties to determine its type:
   - Check for "field_type" property: "select", "custom_select", "typeahead", etc.
   - Check for "tag" property: "select", "input", "textarea", etc.
   - Check for "is_typeahead" or "might_be_custom_select" properties
   - Look for "options" array which indicates a field has dropdown options

2. Operation type should match the field type:
   - Regular text fields: Use "fill" operations
   - Standard <select> elements (tag="select", field_type="select"): Use "fill" operations
   - Custom dropdowns (field_type="custom_select" or might_be_custom_select=true): Use "select_custom_dropdown" operations
   - Typeahead fields (field_type="typeahead" or is_typeahead=true): Use "fill" operations, but be prepared for dropdowns to appear
   - Location fields (field_subtype="location"): Use "fill" operations
   - Checkboxes/radio buttons: Use "set_checkbox_radio" operations
   - File uploads: Use "upload_file" operations

3. Prioritize:
   - Required fields (required=true)
   - Fields with high importance
   - Fields with proper selectors (selector property exists)

4. NEVER create duplicate operations for the same field (both "fill" AND "select_custom_dropdown")

5. For each field, include:
   - Appropriate selector value
   - Correct frame_identifier if field is in an iframe
   - Verification strategy to confirm successful input

6. Set "should_submit" in the submission section to {test_mode} based on the TEST MODE flag.

Ensure the final output is a single JSON object matching the provided schema EXACTLY.

This is the expected criteria for your final answer: A single JSON object representing the execution plan, strictly adhering to the following schema:
```json
{execution_plan_schema}
```

you MUST return the actual complete content as the final answer, not a summary.
"""
        
        return Task(
            description=description,
            expected_output="A complete and detailed execution plan in JSON format strictly following the schema provided.",
            agent=self.agents["application_executor"]
        )
    
    async def _run_crew_async(self, crew):
        """Run a crew asynchronously."""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, crew.kickoff)
            
            # CrewAI v0.28+ returns a CrewOutput object which contains tasks_output
            # Convert the result to a list of TaskOutput if it's a CrewOutput
            if hasattr(result, 'tasks_output'):
                return result.tasks_output
            
            # Backwards compatibility: if it's already a list, return it as is
            if isinstance(result, list):
                return result
            
            # If it's a single TaskOutput, wrap it in a list
            if hasattr(result, 'agent') and hasattr(result, 'task'):
                return [result]
            
            # Fallback: return empty list if we couldn't determine the result type
            self.logger.warning(f"Unexpected result type from crew: {type(result)}")
            return []
            
        except Exception as e:
            self.logger.error(f"Error running crew: {str(e)}")
            return []
    
    def _process_results(
        self, 
        results: List[TaskOutput], 
        test_mode: bool
    ) -> Dict[str, Any]:
        """
        Process the results from the crew tasks.
        
        Args:
            results: Results from the crew tasks
            test_mode: Whether this was a test mode run
            
        Returns:
            Processed results as a dictionary
        """
        processed_results = {
            "success": True,
            "test_mode": test_mode
        }
        
        # Extract results from each task
        for result in results:
            # Get task info safely, handling different TaskOutput versions
            task_name = "Unknown Task"
            task_agent = "Unknown Agent"
            
            # Get agent info - newer versions have agent as a string
            if hasattr(result, 'agent'):
                if isinstance(result.agent, str):
                    task_agent = result.agent
                elif hasattr(result.agent, 'role'):
                    task_agent = result.agent.role
                
            # Get task info - handle both older and newer versions
            if hasattr(result, 'task') and result.task is not None:
                if hasattr(result.task, 'description'):
                    task_desc = result.task.description.strip()
                    task_name = task_desc.split('\n')[0] if '\n' in task_desc else task_desc
            elif hasattr(result, 'description'):
                task_desc = result.description.strip()
                task_name = task_desc.split('\n')[0] if '\n' in task_desc else task_desc
            
            logger.info(f"Processing result from {task_agent} for task: {task_name[:50]}...")
            
            try:
                # Parse JSON from task output if possible
                # Use the appropriate attribute based on what's available
                if hasattr(result, 'output'):
                    content = result.output
                elif hasattr(result, 'raw'):
                    content = result.raw
                else:
                    content = str(result)
                    
                # Extract JSON if it's embedded in text
                if '```json' in content:
                    json_start = content.find('```json') + 7
                    json_end = content.find('```', json_start)
                    content = content[json_start:json_end].strip()
                elif '```' in content:
                    json_start = content.find('```') + 3
                    json_end = content.find('```', json_start)
                    content = content[json_start:json_end].strip()
                    
                # Parse the JSON content
                try:
                    parsed_content = json.loads(content)
                    
                    # Store results based on the agent that produced them
                    if task_agent == "Form Analysis Expert":
                        processed_results["form_analysis"] = parsed_content
                    elif task_agent == "Form Field Mapping Specialist":
                        processed_results["field_mappings"] = parsed_content
                    elif task_agent == "Application Execution Specialist":
                        # Validate and clean the execution plan
                        processed_results["execution_plan"] = self._validate_and_clean_execution_plan(parsed_content)
                    elif task_agent == "Error Recovery Specialist":
                        processed_results["recovery_data"] = parsed_content
                    
                except json.JSONDecodeError:
                    # Fall back to using the raw string if JSON parsing failed
                    logger.warning(f"Could not parse JSON from task output, using raw text")
                    key = task_agent.lower().replace(" ", "_")
                    processed_results[key] = content
                    
            except Exception as e:
                logger.warning(f"Error processing result from {task_agent}: {str(e)}")
                key = task_agent.lower().replace(" ", "_")
                processed_results[key + "_error"] = str(e)
                
        # Add test mode information
        if test_mode:
            processed_results["test_mode_info"] = "This was a test run. No actual job application was submitted."
            
        logger.info(f"Processed results from {len(results)} tasks")
        return processed_results
    
    def _validate_and_clean_execution_plan(self, plan_content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and clean the execution plan to remove redundancies and ambiguities.
        
        Args:
            plan_content: The raw execution plan generated by the AI
            
        Returns:
            Cleaned and validated execution plan
        """
        if not plan_content or not isinstance(plan_content, dict):
            logger.warning("Invalid execution plan format - not a dictionary")
            return plan_content
            
        # Get the execution plan component
        execution_plan = plan_content.get('execution_plan', {})
        if not execution_plan:
            logger.warning("No 'execution_plan' key found in the AI generated plan")
            return plan_content
            
        stages = execution_plan.get('stages', [])
        if not stages:
            logger.warning("No stages found in execution plan")
            return plan_content
            
        # Track unique fields we've seen to avoid duplicates
        processed_fields = set()
        
        # Clean up the stages
        for stage in stages:
            operations = stage.get('operations', [])
            cleaned_operations = []
            
            # Group operations by selector to find redundancies
            selector_to_operations = {}
            
            for op in operations:
                selector = op.get('selector')
                if not selector:
                    # Keep operations without selectors (rare)
                    cleaned_operations.append(op)
                    continue
                    
                if selector not in selector_to_operations:
                    selector_to_operations[selector] = []
                    
                selector_to_operations[selector].append(op)
            
            # Process each selector group
            for selector, ops in selector_to_operations.items():
                if len(ops) <= 1:
                    # No redundancy, add the single operation
                    cleaned_operations.extend(ops)
                    continue
                
                # Handle multiple operations on the same selector
                
                # Check field types in the operations
                has_select = any(op.get('type') == 'select_custom_dropdown' for op in ops)
                has_fill = any(op.get('type') == 'fill' for op in ops)
                
                # If we have both select and fill for same selector, prioritize select
                if has_select and has_fill:
                    # Keep only the select_custom_dropdown operation
                    select_op = next(op for op in ops if op.get('type') == 'select_custom_dropdown')
                    cleaned_operations.append(select_op)
                    logger.debug(f"Removed redundant 'fill' operation for selector '{selector}' - keeping 'select_custom_dropdown'")
                else:
                    # Keep all operations if they're different types or all the same type
                    cleaned_operations.extend(ops)
            
            # Update the stage with cleaned operations
            stage['operations'] = cleaned_operations
            
        # Update the execution plan with cleaned stages
        execution_plan['stages'] = stages
        cleaned_plan = {'execution_plan': execution_plan}
        
        # If there are other top-level keys, preserve them
        for key, value in plan_content.items():
            if key != 'execution_plan':
                cleaned_plan[key] = value
                
        return cleaned_plan
    
    async def _handle_error(
        self, 
        error: Exception, 
        form_data: Dict[str, Any], 
        user_profile: Dict[str, Any],
        job_description: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle errors in the job application process.
        
        Args:
            error: The error that occurred
            form_data: Form data extracted from the job posting
            user_profile: User profile data
            job_description: Job description data
            
        Returns:
            Error handling results
        """
        logger.info(f"Attempting error recovery for: {str(error)}")
        
        try:
            # Create error recovery task
            error_recovery_task = self.create_error_recovery_task(
                {
                    "error_message": str(error),
                    "error_type": type(error).__name__,
                    "task": "execution_plan"
                },
                [],
                form_data
            )
            
            # Create a small crew with just the error recovery agent
            error_crew = self.create_crew()
            error_crew.tasks = [error_recovery_task]
            
            # Run the error recovery crew
            recovery_results = await self._run_crew_async(error_crew)
            
            # Process recovery results
            if recovery_results and len(recovery_results) > 0:
                result = recovery_results[0]
                
                try:
                    # Parse JSON from task output if possible
                    content = result.output if hasattr(result, 'output') else result.raw
                    
                    # Extract JSON if it's embedded in text
                    if '```json' in content:
                        json_start = content.find('```json') + 7
                        json_end = content.find('```', json_start)
                        content = content[json_start:json_end].strip()
                    elif '```' in content:
                        json_start = content.find('```') + 3
                        json_end = content.find('```', json_start)
                        content = content[json_start:json_end].strip()
                        
                    # Parse the JSON content
                    try:
                        parsed_content = json.loads(content)
                        return parsed_content
                    except json.JSONDecodeError:
                        # Fall back to using the raw string if JSON parsing failed
                        logger.warning("Could not parse JSON from error recovery output, using raw text")
                        return {"diagnosis": "Parse error", "raw_output": content}
                except Exception as e:
                    logger.warning(f"Error processing recovery result: {str(e)}")
                    return {"diagnosis": "Processing error", "error": str(e)}
            
            return {"diagnosis": "No recovery result produced"}
        except Exception as recovery_error:
            logger.error(f"Error in error recovery process: {str(recovery_error)}")
            return {"diagnosis": "Recovery failed", "error": str(recovery_error)}

    async def _execute_plan(self, execution_plan: Dict[str, Any], form_data: Dict[str, Any], job_url: str) -> bool:
        """
        Execute the form filling plan.
        
        Args:
            execution_plan: Plan for executing form actions
            form_data: Form structure and field data
            job_url: URL of the job application
            
        Returns:
            True if execution was successful, False otherwise
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage("execute_plan")
        
        try:
            # First analyze form structure
            field_info = await self.action_executor.analyze_form_structure(form_data)
            
            # Prepare actions for execution
            actions = []
            
            # Track fields that need dropdown matching
            dropdown_fields = {}
            
            for step in execution_plan.get("steps", []):
                field_id = step.get("field_id")
                if not field_id:
                    continue
                
                # Get field information
                info = field_info.get(field_id)
                if not info:
                    logger.warning(f"No field info found for {field_id}")
                    continue
                
                # Handle dropdowns separately
                if info.field_type == FieldType.SELECT:
                    dropdown_fields[field_id] = step.get("value")
                    continue
                
                # Create action context for other fields
                action = ActionContext(
                    field_id=field_id,
                    field_info=info,
                    value=step.get("value"),
                    frame_id=step.get("frame_id"),
                    selector=step.get("selector"),
                    validation_rules=step.get("validation_rules")
                )
                actions.append(action)
            
            # Handle dropdowns with smart matching
            if dropdown_fields:
                for field_id, value in dropdown_fields.items():
                    info = field_info[field_id]
                    options = form_data.get("fields", {}).get(field_id, {}).get("options", [])
                    
                    # Determine field type hint based on field name/label
                    field_type_hint = None
                    field_label = info.label.lower()
                    if any(word in field_label for word in ["school", "university", "college", "education"]):
                        field_type_hint = "school"
                    elif any(word in field_label for word in ["location", "city", "state", "country"]):
                        field_type_hint = "location"
                    
                    # Find best match
                    match, score = self.dropdown_matcher.find_best_match(
                        value,
                        options,
                        field_type=field_type_hint
                    )
                    
                    if match:
                        action = ActionContext(
                            field_id=field_id,
                            field_info=info,
                            value=match,
                            frame_id=step.get("frame_id"),
                            selector=step.get("selector"),
                            options=options
                        )
                        actions.append(action)
                    else:
                        logger.warning(
                            f"No match found for dropdown {field_id} value '{value}' "
                            f"(best score: {score:.2f})"
                        )
            
            # Execute all actions
            results = await self.action_executor.execute_form_actions(
                actions,
                stop_on_error=True  # Stop if any action fails
            )
            
            # Check for failures
            failures = {
                field_id: error
                for field_id, (success, error) in results.items()
                if not success
            }
            
            if failures:
                logger.error(f"Failed actions: {json.dumps(failures, indent=2)}")
                if self.diagnostics_manager:
                    self.diagnostics_manager.end_stage(
                        False,
                        error="Some actions failed",
                        details={"failures": failures}
                    )
                return False
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    True,
                    details={
                        "total_actions": len(actions),
                        "successful_actions": len(results) - len(failures)
                    }
                )
            
            return True
            
        except Exception as e:
            error_msg = f"Error executing plan: {str(e)}"
            logger.error(error_msg)
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(False, error=error_msg)
            
            # Log failure for analysis
            log_execution_failure(
                job_url,
                {"type": "plan_execution", "plan": execution_plan},
                {"error": str(e), "traceback": traceback.format_exc()}
            )
            
            return False
    
    def _get_field_info_for_selector(self, selector: str, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retrieve field information for a given selector from form data.
        This helps with diagnostics and error recovery.
        
        Args:
            selector: CSS selector for the field
            form_data: Form analysis data
            
        Returns:
            Field information if found, empty dict otherwise
        """
        try:
            if not form_data or 'form_analysis' not in form_data:
                return {}
                
            field_details = form_data.get('form_analysis', {}).get('field_details', [])
            
            # Find field by selector
            for field in field_details:
                if field.get('selector') == selector:
                    return field
            
            # If not found by exact selector, try partial match
            for field in field_details:
                field_selector = field.get('selector', '')
                if field_selector and (field_selector in selector or selector in field_selector):
                    return field
                    
            return {}
        except Exception as e:
            logger.warning(f"Error retrieving field info for selector '{selector}': {e}")
            return {}

    def _extract_task_result(self, results, agent_role):
        """Extract and parse the result from a specific agent's task."""
        for result in results:
            # Get agent info
            task_agent = "Unknown Agent"
            if hasattr(result, 'agent'):
                if isinstance(result.agent, str):
                    task_agent = result.agent
                elif hasattr(result.agent, 'role'):
                    task_agent = result.agent.role
                    
            # If this is the result we're looking for
            if agent_role in task_agent:
                try:
                    # Parse JSON from task output if possible
                    if hasattr(result, 'output'):
                        content = result.output
                    elif hasattr(result, 'raw'):
                        content = result.raw
                    else:
                        content = str(result)
                        
                    # Extract JSON if it's embedded in text
                    if '```json' in content:
                        json_start = content.find('```json') + 7
                        json_end = content.find('```', json_start)
                        content = content[json_start:json_end].strip()
                    elif '```' in content:
                        json_start = content.find('```') + 3
                        json_end = content.find('```', json_start)
                        content = content[json_start:json_end].strip()
                        
                    # Parse the JSON content
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse JSON from {agent_role} task output, using empty dict")
                        return {}
                except Exception as e:
                    logger.warning(f"Error extracting result from {agent_role}: {e}")
                    return {}
                    
        # If no matching result found
        logger.warning(f"No result found for agent: {agent_role}")
        return {} 