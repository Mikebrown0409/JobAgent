"""Manages the crew of agents for the enterprise job application system."""

import asyncio
import json
import logging
import os
import time
from typing import Dict, List, Any, Optional
from crewai import Crew, Agent, Task, Process

from enterprise_job_agent.core.field_identification_system import FieldIdentificationSystem
from enterprise_job_agent.agents.profile_adapter_agent import ProfileAdapterAgent
from crewai.tasks.task_output import TaskOutput
from enterprise_job_agent.core.browser_manager import BrowserManager

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
    """
    Manages a crew of agents for the job application process.
    """
    
    def __init__(
        self, 
        llm: Any,
        browser_manager: Any,
        verbose: bool = False
    ):
        """
        Initialize the crew manager.
        
        Args:
            llm: Language model to use for agents
            browser_manager: Instance of BrowserManager for executing actions
            verbose: Whether to enable verbose logging
        """
        self.llm = llm
        self.browser_manager = browser_manager
        self.verbose = verbose
        self.field_system = FieldIdentificationSystem()
        self.profile_adapter = ProfileAdapterAgent(llm=llm, verbose=verbose)
        self.agents = {}
        self.tasks = {}
        self.crew = None
        self._initialize_agents()
    
    def _initialize_agents(self):
        """Initialize all the agents needed for the job application process."""
        logger.info("Initializing job application agents")
        
        # Initialize common kwargs for all agents
        agent_kwargs = {
            "allow_delegation": False,
            "verbose": self.verbose,
            "llm": self.llm,
            "temperature": 0.4,  # Lower temperature for more consistent outputs
        }
        
        # Create form analyzer agent
        self.agents["form_analyzer"] = Agent(
            role="Form Analysis Expert",
            goal="Analyze job application forms to understand their structure and requirements",
            backstory="""You are an expert in analyzing web forms, particularly job application forms.
            Your deep understanding of form structures, field types, and validation requirements
            allows you to provide detailed insights on how to best approach complex forms.
            You can identify required vs. optional fields, analyze field types, and determine
            the importance of different sections in a form.""",
            **agent_kwargs
        )
        
        # Create profile adapter agent
        self.agents["profile_adapter"] = Agent(
            role="Profile Optimization Specialist",
            goal="Adapt candidate profiles to maximize relevance and impact for specific job applications",
            backstory="""You are an expert in optimizing candidate profiles for job applications.
            You have years of experience in recruiting and understand how to present qualifications
            in the most compelling way possible while maintaining accuracy. Your strategic insights
            help candidates highlight their most relevant experience for each opportunity.""",
            verbose=self.verbose,
            llm=self.llm
        )
        
        # Create field mapper agent (used by profile_mapping_task)
        self.agents["field_mapper"] = Agent(
            role="Form Field Mapping Specialist",
            goal="Map user profile data to job application form fields",
            backstory="""You are a specialist in mapping user data to form fields accurately.
            With your expertise in data structures and form patterns, you can intelligently 
            determine how user profile information should be applied to various form fields.
            You understand common field naming conventions, required formats, and how to
            translate between different data representations.""",
            **agent_kwargs
        )
        
        # Create application executor agent
        self.agents["application_executor"] = Agent(
            role="Application Execution Specialist",
            goal="Execute job applications with precision, overcoming obstacles and ensuring completion",
            backstory="""You are an expert in executing complex web-based job applications.
            You have deep technical knowledge of browser automation and form interactions.
            Your methodical approach ensures applications are filled correctly and completely,
            even when encountering unexpected challenges or unusual form structures.""",
            verbose=self.verbose,
            llm=self.llm
        )
        
        # Create submission agent (used by application_execution_task)
        self.agents["submission_agent"] = Agent(
            role="Job Application Submission Expert",
            goal="Prepare the final form submission data",
            backstory="""You are a meticulous expert in job application submissions.
            Your attention to detail ensures that all application data is correctly
            formatted and meets the requirements of the job application systems.
            You perform final data validation, ensure all required fields are complete,
            and optimize the application formatting to increase chances of success.""",
            **agent_kwargs
        )
        
        # Create error recovery agent
        self.agents["error_recovery"] = Agent(
            role="Error Recovery Specialist",
            goal="Diagnose and recover from errors in the job application process",
            backstory="""You are an expert in diagnosing and recovering from errors in complex systems.
            Your analytical abilities allow you to identify the root causes of failures and
            develop effective strategies to recover from them. You understand common failure
            patterns in form submissions and can suggest targeted fixes.""",
            **agent_kwargs
        )
        
        logger.info("All agents initialized successfully")
    
    def create_crew(self):
        """Create a crew for the job application process."""
        return Crew(
            agents=list(self.agents.values()),
            verbose=self.verbose
        )
    
    def create_form_analysis_task(self, form_data):
        """Create a task for form analysis."""
        return Task(
            description=f"""
            Analyze the following job application form structure:
            
            {json.dumps(form_data, indent=2)}
            
            Your task is to:
            1. Identify all form sections and their purposes
            2. Categorize all fields by type (text, select, file upload, etc.)
            3. Determine which fields are required vs. optional
            4. Assign importance levels (high, medium, low) to each field
            5. Provide strategic insights on how to approach this form
            
            Your analysis should help the Field Mapping Specialist understand 
            how to best map user profile data to these fields.
            """,
            expected_output="""A JSON structure containing:
            1. Structured analysis of the form
            2. Field categorization by type and requirement
            3. Importance levels for each field
            4. Strategic insights for form completion
            """,
            agent=self.agents["form_analyzer"]
        )
    
    def create_error_recovery_task(self, error_context, operation_history, form_data):
        """Create a task for error recovery."""
        return Task(
            description=f"""
            Diagnose and recover from the following error in the job application process:
            
            ERROR:
            {error_context.get('error_message', 'Unknown error')}
            Error Type: {error_context.get('error_type', 'Unknown')}
            Task: {error_context.get('task', 'Unknown')}
            
            FORM DATA:
            {json.dumps(form_data, indent=2)[:1000] + "..." if len(json.dumps(form_data)) > 1000 else json.dumps(form_data, indent=2)}
            
            Your task is to:
            1. Identify the type and root cause of the error
            2. Determine if it's related to form structure, data mapping, or submission
            3. Suggest 2-3 possible approaches to recover from this error
            4. Recommend the best approach to try
            
            Provide a detailed diagnostic report that can help resolve this issue.
            """,
            expected_output="""A JSON structure containing:
            1. Error diagnosis (type, root cause, severity)
            2. Potential recovery approaches
            3. Recommended approach with implementation steps
            4. Preventive measures for future applications
            """,
            agent=self.agents["error_recovery"]
        )
        
    def create_profile_mapping_task(self, form_data, user_profile, job_description):
        """Create a task for profile mapping."""
        return Task(
            description=f"""
            Map the user profile data to the job application form fields.
            
            USER PROFILE:
            {json.dumps(user_profile, indent=2)}
            
            JOB DESCRIPTION:
            {json.dumps(job_description, indent=2)}
            
            Use the Form Analysis results to intelligently map user data to form fields.
            For each field, determine:
            1. What user profile data should populate this field
            2. Any transformations needed to format the data correctly
            3. Special handling for fields without direct user profile mapping
            
            Focus especially on required and high-importance fields identified in the form analysis.
            """,
            expected_output="""A JSON structure containing:
            1. Mappings between user profile data and form fields
            2. Transformation rules for data formatting
            3. Special case handling instructions
            4. Recommendations for fields requiring user input
            """,
            agent=self.agents["field_mapper"]
        )
    
    def create_execution_plan_task(self, form_analysis, profile_mapping, test_mode):
        """Create a task for generating the application execution plan."""
        # Define the expected JSON output structure for the plan
        # (This should match the structure requested in ApplicationExecutorAgent.create_execution_prompt)
        execution_plan_schema = { 
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
                                "value": "Value to enter/select/upload path", # Optional depending on type
                                "trigger_selector": "Selector for dropdown trigger", # For custom_dropdown
                                "options_selector": "Selector for dropdown options", # For custom_dropdown
                                "should_be_checked": True, # For checkbox/radio
                                "frame_identifier": "Optional frame name/ID/URL part",
                                "verification": "Description of how to verify success", # Optional
                                "fallback": "Description of fallback approach" # Optional
                            }
                        ]
                    }
                ],
                "submission": {
                    "should_submit": False, # Based on test_mode
                    "submit_selector": "Selector for submit button",
                    "confirmation_handling": "Description of confirmation handling" # Optional
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

        return Task(
            description=f"""
            Generate a detailed execution plan for filling and submitting the job application form.
            
            FORM ANALYSIS:
            ```json
            {json.dumps(form_analysis, indent=2)}
            ```
            
            FIELD MAPPINGS:
            ```json
            {json.dumps(profile_mapping, indent=2)}
            ```
            
            TEST MODE: {'Yes - Do not actually submit the application' if test_mode else 'No - Proceed with submission'}
            
            INSTRUCTIONS:
            - Create a step-by-step plan using stages and operations.
            - Prioritize required fields.
            - Specify the correct 'type' for each operation based on the field.
            - Include necessary selectors and values.
            - For custom dropdowns, provide trigger_selector and options_selector.
            - For file uploads, provide the file path in the 'value' field.
            - For checkboxes/radio, set 'should_be_checked'.
            - If an element is in an iframe, specify the 'frame_identifier'.
            - Set 'should_submit' in the submission section based on the TEST MODE flag.
            - Ensure the final output is a single JSON object matching the provided schema EXACTLY.
            """,
            expected_output=f"""A single JSON object representing the execution plan, strictly adhering to the following schema:
            ```json
            {json.dumps(execution_plan_schema, indent=2)}
            ```
            """,
            # Assign to the correct agent
            agent=self.agents["application_executor"] 
        )
    
    async def execute_job_application_process(
        self,
        form_data: Dict[str, Any],
        user_profile: Dict[str, Any],
        job_description: Dict[str, Any],
        test_mode: bool = False,
        job_url: str = ""
    ) -> Dict[str, Any]:
        """
        Execute the full job application process using the agent crew.
        
        Args:
            form_data: Raw form data
            user_profile: User profile data
            job_description: Optional job description
            test_mode: Whether to run in test mode
            job_url: URL of the job posting
            
        Returns:
            Results of the job application process
        """
        logger.info("Starting job application process using agent crew")
        
        try:
            # Define tasks for each agent
            form_analysis_task = self.create_form_analysis_task(form_data)
            field_mapping_task = self.create_profile_mapping_task(form_data, user_profile, job_description)
            execution_plan_task = self.create_execution_plan_task(form_data, form_data, test_mode)
            
            # Create the crew with the agents and tasks
            self.crew = self.create_crew()
            self.crew.tasks = [form_analysis_task, field_mapping_task, execution_plan_task]
            
            # Run the crew asynchronously
            results = await self._run_crew_async(self.crew)
            
            # Process results
            processed_results = self._process_results(results, test_mode)
            logger.debug(f"Processed crew results: {processed_results}")

            # Execute the plan
            execution_plan = processed_results.get("execution_plan")
            execution_successful = False
            if execution_plan:
                try:
                    # Pass the plan, form_data, and job_url to the execution method
                    execution_successful = await self._execute_plan(execution_plan, form_data, job_url)
                    processed_results["execution_status"] = "Success" if execution_successful else "Failed"
                except Exception as e:
                    logger.error(f"Exception occurred during plan execution: {e}")
                    processed_results["execution_status"] = "Failed due to exception"
                    # Optionally trigger error recovery here as well
            else:
                 logger.error("No execution plan found in agent results.")
                 processed_results["execution_status"] = "Failed - No Plan"

            return processed_results
            
        except Exception as e:
            logger.error(f"Error in job application process: {str(e)}")
            # Attempt error recovery
            recovery_result = await self._handle_error(e, form_data, user_profile, job_description)
            
            return {
                "success": False,
                "error": str(e),
                "recovery_result": recovery_result,
                "test_mode": test_mode
            }
    
    async def _run_crew_async(self, crew: Crew) -> List[TaskOutput]:
        """
        Run the crew asynchronously.
        
        Args:
            crew: The CrewAI crew to run
            
        Returns:
            Results from the crew tasks
        """
        # Since CrewAI's run() method is synchronous, we'll run it in a separate thread
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
        logger.warning(f"Unexpected result type from crew: {type(result)}")
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
                        processed_results["execution_plan"] = parsed_content
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
        """Execute the browser actions defined in the execution plan."""
        logger.info("Starting execution of the generated plan.")
        plan_successful = True

        if not execution_plan or 'execution_plan' not in execution_plan:
            logger.error("Execution plan is missing or invalid.")
            return False

        plan_data = execution_plan['execution_plan']
        stages = plan_data.get('stages', [])

        for stage in stages:
            stage_name = stage.get('name', 'Unnamed Stage')
            logger.info(f"--- Executing Stage: {stage_name} ---")
            operations = stage.get('operations', [])
            
            for op in operations:
                op_type = op.get('type')
                selector = op.get('selector')
                value = op.get('value') # Might be None for clicks
                frame_id = op.get('frame_identifier') # Defaults to None if missing
                
                logger.debug(f"Executing operation: {op_type} on selector '{selector}' with value '{value}' in frame '{frame_id}'")
                
                success = False
                try:
                    if op_type == 'fill':
                        if selector and value is not None:
                            success = await self.browser_manager.fill_field(selector, value, frame_identifier=frame_id)
                        else:
                             logger.warning(f"Skipping fill operation due to missing selector or value: {op}")
                    elif op_type == 'click':
                        if selector:
                            success = await self.browser_manager.click_element(selector, frame_identifier=frame_id)
                        else:
                            logger.warning(f"Skipping click operation due to missing selector: {op}")
                    elif op_type == 'select_custom_dropdown':
                        trigger_selector = op.get('trigger_selector')
                        options_selector = op.get('options_selector')
                        if trigger_selector and options_selector and value is not None:
                            success = await self.browser_manager.select_custom_dropdown(
                                trigger_selector, options_selector, value, frame_identifier=frame_id
                            )
                        else:
                             logger.warning(f"Skipping select_custom_dropdown operation due to missing selectors or value: {op}")
                    elif op_type == 'upload_file':
                        if selector and value:
                             # Ensure value (file path) exists - BrowserManager also checks but good to check early
                             if os.path.exists(value):
                                 success = await self.browser_manager.upload_file(selector, value, frame_identifier=frame_id)
                             else:
                                 logger.error(f"File path specified in plan does not exist: {value}")
                                 success = False
                        else:
                            logger.warning(f"Skipping upload_file operation due to missing selector or file path: {op}")
                    elif op_type == 'set_checkbox_radio':
                        should_be_checked = op.get('should_be_checked', True)
                        if selector:
                            success = await self.browser_manager.set_checkbox_radio(selector, should_be_checked, frame_identifier=frame_id)
                        else:
                            logger.warning(f"Skipping set_checkbox_radio operation due to missing selector: {op}")
                    else:
                        logger.warning(f"Unsupported operation type '{op_type}' in execution plan: {op}")

                    if not success:
                        logger.error(f"Execution failed at stage '{stage_name}' on operation: {op}")
                        error_context = {
                            "error_message": f"Operation failed: {op_type} on {selector}",
                            "error_type": "OperationFailed",
                            "task": "plan_execution",
                            "failed_operation": op
                        }
                        # Log the failure
                        log_execution_failure(job_url, op, error_context)
                        # Call error handler
                        await self._handle_error(error_context, form_data, {}, {})
                        # Abort plan execution
                        return False 
                    else:
                        logger.debug(f"Operation successful: {op_type} on {selector}")
                        # Optional delay between operations
                        await asyncio.sleep(0.2)

                except Exception as e:
                    logger.error(f"Exception during operation execution: {op}. Error: {e}")
                    plan_successful = False
                    # --- Enhanced Error Handling --- 
                    error_context = {
                        "error_message": str(e),
                        "error_type": type(e).__name__,
                        "task": "plan_execution",
                        "failed_operation": op
                    }
                    # Log the failure
                    log_execution_failure(job_url, op, error_context)
                    # Call error handler
                    await self._handle_error(error_context, form_data, {}, {})
                    # Abort plan execution
                    # --- End Enhanced Error Handling --- 
                    return False # Abort on unexpected exception

        logger.info("--- Completed all planned operations --- ")

        # Handle Submission
        submission_details = plan_data.get('submission', {})
        should_submit = submission_details.get('should_submit', False)
        submit_selector = submission_details.get('submit_selector')

        if should_submit:
            if submit_selector:
                logger.info(f"Attempting final submission by clicking: {submit_selector}")
                try:
                    submit_success = await self.browser_manager.click_element(submit_selector)
                    if not submit_success:
                        logger.error("Failed to click the submit button.")
                        plan_successful = False
                    else:
                        logger.info("Submit button clicked successfully.")
                        # Add potential wait/check for confirmation if needed based on `confirmation_handling`
                except Exception as e:
                     logger.error(f"Exception during submission click: {e}")
                     plan_successful = False
            else:
                logger.warning("Plan specified submission, but no submit_selector was provided.")
                plan_successful = False # Cannot submit without selector
        else:
            logger.info("Skipping final submission as per execution plan (test_mode likely enabled).")

        return plan_successful 