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

logger = logging.getLogger(__name__)

class JobApplicationCrew:
    """
    Manages a crew of agents for the job application process.
    """
    
    def __init__(
        self, 
        llm: Any,
        verbose: bool = False
    ):
        """
        Initialize the crew manager.
        
        Args:
            llm: Language model to use for agents
            verbose: Whether to enable verbose logging
        """
        self.llm = llm
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
    
    def create_application_execution_task(self, form_analysis, profile_mapping, test_mode):
        """Create a task for application execution."""
        return Task(
            description=f"""
            Prepare the final submission data for the job application.
            
            Based on the form analysis and field mappings, create the final submission data:
            1. Ensure all required fields have values
            2. Format all data according to field requirements
            3. Validate the submission data for completeness and correctness
            4. Identify any fields that require special attention before submission
            
            {'This is a TEST MODE run - no actual submission will be made.' if test_mode else 'This will be used for ACTUAL SUBMISSION - ensure all data is accurate.'}
            """,
            expected_output="""A JSON structure containing:
            1. Complete submission data for all form fields
            2. Validation results and confidence level
            3. Any warnings or issues to address
            4. Final submission readiness assessment
            """,
            agent=self.agents["submission_agent"]
        )
    
    async def execute_job_application_process(
        self,
        form_data: Dict[str, Any],
        user_profile: Dict[str, Any],
        job_description: Dict[str, Any],
        test_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Execute the full job application process using the agent crew.
        
        Args:
            form_data: Raw form data
            user_profile: User profile data
            job_description: Optional job description
            test_mode: Whether to run in test mode
            
        Returns:
            Results of the job application process
        """
        logger.info("Starting job application process using agent crew")
        
        try:
            # Define tasks for each agent
            form_analysis_task = self.create_form_analysis_task(form_data)
            field_mapping_task = self.create_profile_mapping_task(form_data, user_profile, job_description)
            submission_preparation_task = self.create_application_execution_task(form_data, form_data, test_mode)
            
            # Create the crew with the agents and tasks
            self.crew = self.create_crew()
            self.crew.tasks = [form_analysis_task, field_mapping_task, submission_preparation_task]
            
            # Run the crew asynchronously
            results = await self._run_crew_async(self.crew)
            
            # Process and return the results
            return self._process_results(results, test_mode)
            
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
                        processed_results["submission_data"] = parsed_content
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
                    "task": "application_execution"
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