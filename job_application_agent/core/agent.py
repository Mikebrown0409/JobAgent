"""
Main Job Application Agent - Core Orchestrator

This is the central brain that manages the overall task lifecycle, including:
- Planning and execution
- State tracking and error handling
- Tool coordination and LLM integration
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum

from job_application_agent.core.config import get_config
from job_application_agent.core.llm_service import LLMService
from job_application_agent.core.memory.profile_store import ProfileStore
from job_application_agent.core.memory.working_memory import WorkingMemory
from job_application_agent.tools.registry import ToolRegistry
from job_application_agent.tools.browser_tool import BrowserTool
from job_application_agent.utils.logging_setup import setup_logging


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    PARTIALLY_SUCCEEDED = "partially_succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobApplicationAgent:
    """
    Main Job Application Agent that orchestrates the entire job application process.
    
    This agent follows the ReAct pattern: Reason -> Act -> Observe
    """
    
    def __init__(self, profile_path: Optional[str] = None, config_override: Optional[Dict] = None):
        """
        Initialize the Job Application Agent.
        
        Args:
            profile_path: Path to user profile JSON file
            config_override: Optional configuration overrides
        """
        self.config = get_config()
        if config_override:
            for key, value in config_override.items():
                setattr(self.config, key, value)
        
        # Setup logging
        self.logger = setup_logging(self.config.log_level)
        
        # Initialize core components
        self.profile_store = ProfileStore(profile_path or self.config.profile_path)
        self.working_memory = WorkingMemory()
        self.llm_service = LLMService(self.config)
        self.tool_registry = ToolRegistry()
        
        # Register core tools
        self._register_tools()
        
        # Agent state
        self.status = TaskStatus.PENDING
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.results: Dict[str, Any] = {}
        
        self.logger.info("JobApplicationAgent initialized successfully")
    
    def _register_tools(self) -> None:
        """Register available tools with the tool registry."""
        browser_tool = BrowserTool(self.config)
        self.tool_registry.register("browser", browser_tool)
        # Additional tools can be registered here
    
    async def execute_task(self, goal: str) -> TaskStatus:
        """
        Execute a job application task.
        
        Args:
            goal: High-level goal description (e.g., "Apply to job at URL X")
            
        Returns:
            TaskStatus indicating success/failure
        """
        self.start_time = datetime.now()
        self.status = TaskStatus.IN_PROGRESS
        self.working_memory.set_goal(goal)
        
        self.logger.info(f"Starting task execution: {goal}")
        
        try:
            # Phase 1: Planning
            plan = await self._generate_plan(goal)
            self.working_memory.set_plan(plan)
            self.logger.info(f"Generated plan with {len(plan)} steps")
            
            # Phase 2: Execution
            execution_result = await self._execute_plan(plan)
            
            # Phase 3: Verification
            success = await self._verify_completion()
            
            # Determine final status
            if success:
                self.status = TaskStatus.SUCCEEDED
            elif execution_result.get('partial_success', False):
                self.status = TaskStatus.PARTIALLY_SUCCEEDED
            else:
                self.status = TaskStatus.FAILED
                
        except Exception as e:
            self.logger.error(f"Task execution failed: {str(e)}", exc_info=True)
            self.status = TaskStatus.FAILED
            self.working_memory.add_error(str(e))
        
        finally:
            self.end_time = datetime.now()
            self._finalize_results()
            await self._cleanup()
        
        self.logger.info(f"Task completed with status: {self.status.value}")
        return self.status
    
    async def _generate_plan(self, goal: str) -> List[Dict[str, Any]]:
        """Generate an execution plan for the given goal."""
        try:
            # Get available tools
            available_tools = self.tool_registry.list_tools()
            
            # Get user profile context
            profile_data = self.profile_store.get_profile_data()
            
            # Generate plan using LLM
            plan = await self.llm_service.generate_plan(
                goal=goal,
                available_tools=available_tools,
                profile_context=profile_data
            )
            
            return plan
            
        except Exception as e:
            self.logger.error(f"Plan generation failed: {str(e)}")
            # Fallback to default plan
            return self._get_default_plan(goal)
    
    def _get_default_plan(self, goal: str) -> List[Dict[str, Any]]:
        """Generate a default plan for job applications."""
        # Extract URL from goal if possible
        url = self._extract_url_from_goal(goal)
        
        return [
            {
                "step": 1,
                "action": "navigate",
                "tool": "browser",
                "parameters": {"url": url},
                "description": "Navigate to job posting URL"
            },
            {
                "step": 2,
                "action": "analyze_page",
                "tool": "browser", 
                "parameters": {},
                "description": "Analyze page structure and identify forms"
            },
            {
                "step": 3,
                "action": "fill_application",
                "tool": "browser",
                "parameters": {"profile_data": self.profile_store.get_profile_data()},
                "description": "Fill out job application form"
            },
            {
                "step": 4,
                "action": "submit_application",
                "tool": "browser",
                "parameters": {},
                "description": "Submit the application"
            },
            {
                "step": 5,
                "action": "verify_submission",
                "tool": "browser",
                "parameters": {},
                "description": "Verify successful submission"
            }
        ]
    
    def _extract_url_from_goal(self, goal: str) -> str:
        """Extract URL from goal string."""
        import re
        url_pattern = r'https?://[^\s]+'
        matches = re.findall(url_pattern, goal)
        return matches[0] if matches else ""
    
    async def _execute_plan(self, plan: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute the generated plan step by step."""
        results = {"steps_completed": 0, "steps_failed": 0, "partial_success": False}
        
        for step in plan:
            try:
                self.logger.info(f"Executing step {step['step']}: {step['description']}")
                
                # Get the tool
                tool_name = step["tool"]
                tool = self.tool_registry.get_tool(tool_name)
                
                if not tool:
                    raise ValueError(f"Tool '{tool_name}' not found")
                
                # Execute the action
                action = step["action"]
                parameters = step.get("parameters", {})
                
                result = await self._execute_tool_action(tool, action, parameters)
                
                # Store result in working memory
                self.working_memory.add_step_result(step["step"], result)
                
                if result.get("success", False):
                    results["steps_completed"] += 1
                else:
                    results["steps_failed"] += 1
                    # Try error recovery
                    recovery_success = await self._attempt_error_recovery(step, result)
                    if recovery_success:
                        results["partial_success"] = True
                        results["steps_completed"] += 1
                    
            except Exception as e:
                self.logger.error(f"Step {step['step']} failed: {str(e)}")
                results["steps_failed"] += 1
                self.working_memory.add_error(f"Step {step['step']}: {str(e)}")
        
        return results
    
    async def _execute_tool_action(self, tool: Any, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a specific action on a tool."""
        if hasattr(tool, action):
            method = getattr(tool, action)
            if asyncio.iscoroutinefunction(method):
                return await method(**parameters)
            else:
                return method(**parameters)
        else:
            raise ValueError(f"Action '{action}' not supported by tool")
    
    async def _attempt_error_recovery(self, failed_step: Dict[str, Any], error_result: Dict[str, Any]) -> bool:
        """Attempt to recover from a failed step."""
        if not self.config.enable_error_recovery:
            return False
        
        try:
            # Use LLM service for error recovery strategy
            recovery_plan = await self.llm_service.generate_error_recovery(
                failed_step=failed_step,
                error_result=error_result,
                context=self.working_memory.get_context()
            )
            
            # Execute recovery plan
            for recovery_action in recovery_plan:
                tool = self.tool_registry.get_tool(recovery_action["tool"])
                result = await self._execute_tool_action(
                    tool,
                    recovery_action["action"],
                    recovery_action.get("parameters", {})
                )
                
                if result.get("success", False):
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error recovery failed: {str(e)}")
            return False
    
    async def _verify_completion(self) -> bool:
        """Verify that the task was completed successfully."""
        try:
            # Check if we have browser tool to verify
            browser_tool = self.tool_registry.get_tool("browser")
            if browser_tool:
                return await browser_tool.verify_application_submitted()
            return False
            
        except Exception as e:
            self.logger.error(f"Verification failed: {str(e)}")
            return False
    
    def _finalize_results(self) -> None:
        """Finalize and store execution results."""
        self.results = {
            "goal": self.working_memory.goal,
            "status": self.status.value,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": (self.end_time - self.start_time).total_seconds() if self.start_time and self.end_time else None,
            "steps_executed": len(self.working_memory.step_results),
            "errors": self.working_memory.errors,
            "memory_snapshot": self.working_memory.to_dict()
        }
    
    async def _cleanup(self) -> None:
        """Clean up resources."""
        try:
            # Close browser if it's open
            browser_tool = self.tool_registry.get_tool("browser")
            if browser_tool:
                await browser_tool.close()
                
        except Exception as e:
            self.logger.error(f"Cleanup failed: {str(e)}")
    
    def save_results(self, output_path: str) -> None:
        """Save execution results to file."""
        import json
        
        try:
            with open(output_path, 'w') as f:
                json.dump(self.results, f, indent=2)
            self.logger.info(f"Results saved to {output_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to save results: {str(e)}")
    
    def get_status(self) -> TaskStatus:
        """Get current task status."""
        return self.status
    
    def get_results(self) -> Dict[str, Any]:
        """Get execution results."""
        return self.results 