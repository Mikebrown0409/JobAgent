"""
Crew Orchestrator - Multi-Agent Job Application System

Advanced multi-agent system using CrewAI for orchestrating specialized agents
to handle different aspects of job application automation.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass

try:
    from crewai import Agent, Task, Crew, Process
    from crewai.tools import BaseTool
    import os
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False
    # Fallback classes for when CrewAI is not available
    class Agent:
        def __init__(self, *args, **kwargs): pass
    class Task:
        def __init__(self, *args, **kwargs): pass
    class Crew:
        def __init__(self, *args, **kwargs): pass
    class Process:
        sequential = "sequential"
    class BaseTool:
        def __init__(self, *args, **kwargs): pass

from job_application_agent.core.config import Config
from job_application_agent.tools.browser_tool import AdvancedBrowserTool
from job_application_agent.tools.intelligent_form_filler import IntelligentFormFiller
from job_application_agent.core.llm_service import LLMService
from job_application_agent.core.memory.profile_store import ProfileStore


@dataclass
class JobApplicationTask:
    """Represents a job application task."""
    job_url: str
    job_description: Optional[str] = None
    company_info: Optional[Dict[str, Any]] = None
    priority: int = 1  # 1-5, 1 being highest
    deadline: Optional[datetime] = None
    custom_requirements: Optional[Dict[str, Any]] = None


class CrewOrchestrator:
    """
    Multi-agent orchestrator for job applications using CrewAI.
    
    Manages specialized agents:
    - Research Agent: Analyzes job postings and company information
    - Form Analysis Agent: Analyzes and understands form structures
    - Application Agent: Handles the actual form filling and submission
    - Quality Assurance Agent: Reviews and validates applications
    """
    
    def __init__(self, config: Config):
        """Initialize the crew orchestrator."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        if not CREWAI_AVAILABLE:
            self.logger.warning("CrewAI not available, using fallback single-agent mode")
            self._use_crewai = False
        else:
            self._use_crewai = True
        
        # Initialize core components
        self.llm_service = LLMService(config)
        self.profile_store = ProfileStore(config.profile_path)
        self.browser_tool = AdvancedBrowserTool(config)
        self.form_filler = IntelligentFormFiller(config, self.browser_tool, self.llm_service)
        
        # Initialize agents if CrewAI is available
        if self._use_crewai:
            # Configure environment for Gemini
            if config.google_api_key:
                os.environ["GEMINI_API_KEY"] = config.google_api_key
                
                # Initialize LLM for CrewAI agents
                try:
                    from crewai import LLM
                    self.crew_llm = LLM(
                        model=f"gemini/{config.gemini_model}",
                        api_key=config.google_api_key,
                        temperature=config.llm_temperature
                    )
                    self.logger.info(f"Configured CrewAI to use Gemini: {config.gemini_model}")
                except ImportError:
                    self.logger.error("CrewAI LLM import failed, falling back to single-agent mode")
                    self._use_crewai = False
                    return
            else:
                self.logger.warning("No Gemini API key found, agents may not work properly")
                self._use_crewai = False
                return
            self._initialize_agents()
        
        # Task queue for batch processing
        self.task_queue: List[JobApplicationTask] = []
        self.processing_stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'average_completion_time': 0
        }
    
    def _initialize_agents(self):
        """Initialize specialized agents using CrewAI."""
        # Research Agent - Analyzes job postings and companies
        self.research_agent = Agent(
            role="Job Research Analyst",
            goal="Analyze job postings and company information to optimize application strategy",
            backstory="You are an expert job market analyst with deep understanding of industry trends, "
                     "company cultures, and hiring practices. You excel at extracting key information "
                     "from job postings and tailoring application approaches.",
            verbose=self.config.log_level == "DEBUG",
            allow_delegation=False
        )
        
        # Form Analysis Agent - Understands form structures
        self.form_analysis_agent = Agent(
            role="Form Structure Analyst",
            goal="Analyze and understand complex form structures to optimize filling strategies",
            backstory="You are a specialist in web form analysis and user interface patterns. "
                     "You understand how to navigate complex, dynamic forms across different platforms "
                     "and can identify the best strategies for field mapping and data entry.",
            verbose=self.config.log_level == "DEBUG",
            allow_delegation=False
        )
        
        # Application Agent - Handles form filling
        self.application_agent = Agent(
            role="Application Specialist",
            goal="Execute form filling and application submission with highest success rate",
            backstory="You are an expert at filling out job applications efficiently and accurately. "
                     "You understand how to handle different input types, validation requirements, "
                     "and can adapt to various application platforms seamlessly.",
            verbose=self.config.log_level == "DEBUG",
            allow_delegation=False
        )
        
        # Quality Assurance Agent - Reviews applications
        self.qa_agent = Agent(
            role="Quality Assurance Specialist",
            goal="Review and validate job applications before submission to ensure quality",
            backstory="You are a meticulous quality assurance expert who ensures every application "
                     "meets the highest standards. You check for completeness, accuracy, and "
                     "optimize content for maximum impact with hiring managers.",
            verbose=self.config.log_level == "DEBUG",
            allow_delegation=False
        )
        
        self.logger.info("CrewAI agents initialized successfully")
    
    async def process_job_application(self, task: JobApplicationTask) -> Dict[str, Any]:
        """
        Process a single job application using the multi-agent system.
        
        Args:
            task: Job application task to process
            
        Returns:
            Result of the job application process
        """
        start_time = datetime.now()
        
        try:
            if self._use_crewai:
                result = await self._process_with_crew(task)
            else:
                result = await self._process_fallback(task)
            
            # Update statistics
            duration = (datetime.now() - start_time).total_seconds()
            self._update_stats(True, duration)
            
            result['duration'] = duration
            return result
            
        except Exception as e:
            self.logger.error(f"Job application processing failed: {str(e)}")
            duration = (datetime.now() - start_time).total_seconds()
            self._update_stats(False, duration)
            
            return {
                'success': False,
                'error': str(e),
                'job_url': task.job_url,
                'duration': duration
            }
    
    async def _process_with_crew(self, task: JobApplicationTask) -> Dict[str, Any]:
        """Process job application using CrewAI multi-agent system."""
        profile_data = self.profile_store.get_profile_data()
        
        # Task 1: Research and Analysis
        research_task = Task(
            description=f"""
            Analyze the job posting at {task.job_url} and extract key information:
            1. Job requirements and qualifications
            2. Company culture and values
            3. Application strategy recommendations
            4. Key phrases and terms to include in responses
            
            Job URL: {task.job_url}
            Additional context: {task.job_description or 'None provided'}
            """,
            agent=self.research_agent,
            expected_output="Detailed analysis with strategic recommendations"
        )
        
        # Task 2: Form Structure Analysis
        form_analysis_task = Task(
            description=f"""
            Navigate to {task.job_url} and analyze the form structure:
            1. Identify all form fields and their purposes
            2. Determine optimal filling strategies for each field
            3. Identify potential challenges or special requirements
            4. Map form fields to user profile data
            
            Focus on creating a comprehensive field mapping strategy.
            """,
            agent=self.form_analysis_agent,
            expected_output="Complete form analysis with field mapping recommendations"
        )
        
        # Task 3: Application Execution
        application_task = Task(
            description=f"""
            Execute the job application based on previous analysis:
            1. Fill out all form fields accurately using profile data
            2. Apply the research insights for optimal responses
            3. Handle any dynamic or complex form elements
            4. Prepare for submission but do not submit yet
            
            User Profile Summary:
            - Name: {profile_data.get('basics', {}).get('name', 'Not provided')}
            - Email: {profile_data.get('basics', {}).get('email', 'Not provided')}
            - Experience: {len(profile_data.get('work', []))} positions
            """,
            agent=self.application_agent,
            expected_output="Completed application ready for review"
        )
        
        # Task 4: Quality Assurance
        qa_task = Task(
            description="""
            Review the completed application for quality and completeness:
            1. Verify all required fields are filled accurately
            2. Check that responses align with job requirements
            3. Ensure professional tone and correct formatting
            4. Validate that all information is consistent
            5. Provide final submission recommendation
            """,
            agent=self.qa_agent,
            expected_output="Quality assessment with submission recommendation"
        )
        
        # Create and execute crew
        crew = Crew(
            agents=[self.research_agent, self.form_analysis_agent, 
                   self.application_agent, self.qa_agent],
            tasks=[research_task, form_analysis_task, application_task, qa_task],
            process=Process.sequential,
            verbose=self.config.log_level == "DEBUG"
        )
        
        # Execute the crew
        result = crew.kickoff()
        
        return {
            'success': True,
            'job_url': task.job_url,
            'crew_result': result,
            'method': 'crewai_multi_agent'
        }
    
    async def _process_fallback(self, task: JobApplicationTask) -> Dict[str, Any]:
        """Fallback processing without CrewAI."""
        self.logger.info("Processing job application using fallback single-agent mode")
        
        # Initialize browser
        await self.browser_tool._ensure_initialized()
        
        # Navigate to job application
        nav_result = await self.browser_tool.navigate_with_retry(task.job_url)
        if not nav_result.get('success'):
            raise Exception(f"Failed to navigate to job application: {nav_result.get('error')}")
        
        # Analyze page structure
        page_analysis = await self.browser_tool.analyze_page_structure()
        if not page_analysis.get('success'):
            raise Exception(f"Failed to analyze page structure: {page_analysis.get('error')}")
        
        # Fill application
        profile_data = self.profile_store.get_profile_data()
        fill_result = await self.form_filler.fill_application_intelligently(
            profile_data, page_analysis
        )
        
        return {
            'success': fill_result.get('success', False),
            'job_url': task.job_url,
            'navigation': nav_result,
            'page_analysis': page_analysis,
            'fill_result': fill_result,
            'method': 'fallback_single_agent'
        }
    
    def add_task(self, task: JobApplicationTask) -> None:
        """Add a task to the processing queue."""
        self.task_queue.append(task)
        self.processing_stats['total_tasks'] += 1
    
    async def process_queue(self, max_concurrent: int = 3) -> List[Dict[str, Any]]:
        """
        Process all tasks in the queue with controlled concurrency.
        
        Args:
            max_concurrent: Maximum number of concurrent tasks
            
        Returns:
            List of processing results
        """
        if not self.task_queue:
            return []
        
        self.logger.info(f"Processing {len(self.task_queue)} tasks with max concurrency: {max_concurrent}")
        
        # Sort tasks by priority (1 = highest priority)
        self.task_queue.sort(key=lambda x: x.priority)
        
        results = []
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(task):
            async with semaphore:
                return await self.process_job_application(task)
        
        # Process tasks in batches
        tasks_to_process = [process_with_semaphore(task) for task in self.task_queue]
        results = await asyncio.gather(*tasks_to_process, return_exceptions=True)
        
        # Clear the queue
        self.task_queue.clear()
        
        # Process exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    'success': False,
                    'error': str(result),
                    'task_index': i
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    def _update_stats(self, success: bool, duration: float) -> None:
        """Update processing statistics."""
        if success:
            self.processing_stats['completed_tasks'] += 1
        else:
            self.processing_stats['failed_tasks'] += 1
        
        # Update average completion time
        total_completed = self.processing_stats['completed_tasks']
        if total_completed > 0:
            current_avg = self.processing_stats['average_completion_time']
            self.processing_stats['average_completion_time'] = (
                (current_avg * (total_completed - 1) + duration) / total_completed
            )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics."""
        total = self.processing_stats['total_tasks']
        completed = self.processing_stats['completed_tasks']
        failed = self.processing_stats['failed_tasks']
        
        return {
            **self.processing_stats,
            'success_rate': completed / total if total > 0 else 0,
            'failure_rate': failed / total if total > 0 else 0,
            'crewai_enabled': self._use_crewai,
            'queue_size': len(self.task_queue)
        }
    
    async def close(self) -> None:
        """Clean up resources."""
        if self.browser_tool:
            await self.browser_tool.close() 