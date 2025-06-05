import logging
import os
import json
import asyncio
import argparse
import sys
from typing import Dict, Any, List, Optional, Union, Tuple
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import config
from agentv0.config import config, get_logging_config

# Configure logging
logging_config = get_logging_config()
logging.basicConfig(
    level=getattr(logging, logging_config["level"]),
    format=logging_config["format"]
)
logger = logging.getLogger("AgentCore")

# Import components
from agentv0.memory.profile_store import UserProfileStore
from agentv0.memory.working_memory import WorkingMemory, TaskStatus, StepStatus, Plan
from agentv0.llm_service import LLMService
from agentv0.tools.registry import ToolRegistry
from agentv0.tools.browser_tool import BrowserTool

class AgentCore:
    """The central orchestrator for the agent.
    
    This class manages the overall task lifecycle, including planning, execution,
    state tracking, and error handling.
    """
    
    def __init__(self, profile_path: str, fallback_path: Optional[str] = None, headless: Optional[bool] = None):
        """Initialize the agent core.
        
        Args:
            profile_path: Path to the user profile JSON file
            fallback_path: Optional path to a fallback profile for missing values
            headless: Whether to run the browser in headless mode (overrides config)
        """
        # Initialize memory components
        self.profile_store = UserProfileStore(profile_path, fallback_path)
        self.working_memory = WorkingMemory()
        
        # Initialize LLM service using config
        self.llm_service = LLMService(model_name=config.llm_model_name)
        
        # Initialize tool registry
        self.tool_registry = ToolRegistry()
        
        # Register tools (use provided headless value or fall back to config)
        self._register_tools(headless if headless is not None else config.browser_headless)
        
        logger.info("AgentCore initialized successfully")
    
    def _register_tools(self, headless: bool) -> None:
        """Register all available tools with the tool registry.
        
        Args:
            headless: Whether to run the browser in headless mode
        """
        # Create and register browser tool
        browser_tool = BrowserTool(headless=headless)
        self.tool_registry.register_tool(browser_tool)
        
        # Register other tools here
        # self.tool_registry.register_tool(WebSearchTool())
        # self.tool_registry.register_tool(FileSystemTool())
        
        logger.info(f"Registered {len(self.tool_registry.list_tools())} tools")
    
    async def execute_task(self, goal: str) -> TaskStatus:
        """Execute a task based on a high-level goal.
        
        This is the main entry point for running the agent.
        
        Args:
            goal: The high-level goal to achieve
            
        Returns:
            The final status of the task
        """
        try:
            # Set up the task
            self.working_memory.goal = goal
            logger.info(f"Starting task with goal: {goal}")
            
            # --- Initial Navigation and Analysis ---
            logger.info("Performing initial navigation and page analysis...")
            browser_tool = self.tool_registry.get_tool("browser") # Assuming browser tool is always registered
            
            # Step 1: Navigate
            # Extract URL from goal (simple split for now)
            url_parts = goal.split("URL: ")
            url_to_navigate = url_parts[-1] if len(url_parts) > 1 else goal # Fallback if split fails
            if not url_to_navigate.startswith(("http://", "https://")):
                 raise ValueError(f"Could not extract valid URL from goal: {goal}")
                 
            nav_result = await browser_tool.execute(action="navigate", url=url_to_navigate)
            if not nav_result.get("success", False):
                raise RuntimeError(f"Initial navigation failed: {nav_result.get('observation', 'Unknown error')}")
            self.working_memory.add_observation(source="browser_setup", data=nav_result)
            
            # Step 2: Analyze Page Structure
            analysis_result = await browser_tool.execute(action="analyze_page_structure")
            if not analysis_result.get("success", False):
                 raise RuntimeError(f"Initial page analysis failed: {analysis_result.get('observation', 'Unknown error')}")
            self.working_memory.add_observation(source="browser_setup", data=analysis_result)
            page_elements = analysis_result.get("elements", [])
            if not page_elements:
                logger.warning("Initial page analysis found no interactive elements.")
            # --- End Initial Navigation and Analysis ---

            # Get tool specifications for planning
            tool_specs = self.tool_registry.get_tool_specifications()
            
            # Generate plan using page analysis results
            logger.info("Generating plan based on page analysis...")
            profile_data = self.profile_store.get_all_values()
            plan = await self.llm_service.generate_plan(goal, tool_specs, page_elements, profile_data)
            
            # Convert to our internal Plan type and set in working memory
            plan_steps = []
            for step in plan.steps:
                plan_steps.append({
                    "tool": step["tool"],
                    "parameters": step["parameters"],
                    "goal": step["goal"],
                    "status": StepStatus.PENDING,
                    "result": None,
                    "error": None
                })
            
            internal_plan = Plan(goal=plan.goal, steps=plan_steps)
            self.working_memory.set_plan(internal_plan)
            
            # Execute plan
            status = await self._execute_plan()
            return status
            
        except Exception as e:
            logger.error(f"Task execution failed: {str(e)}", exc_info=True)
            self.working_memory.errors.append(f"Task execution failed: {str(e)}")
            self.working_memory.complete_task(TaskStatus.FAILED)
            return TaskStatus.FAILED
    
    async def _execute_plan(self) -> TaskStatus:
        """Execute the current plan in the working memory.
        
        Returns:
            The final status of the plan execution
        """
        if not self.working_memory.plan:
            logger.error("No plan to execute")
            return TaskStatus.FAILED
        
        logger.info(f"Executing plan with {len(self.working_memory.plan.steps)} steps")
        
        # Track success/failure counts
        success_count = 0
        failure_count = 0
        
        # Execute each step in the plan
        while current_step := self.working_memory.get_current_step():
            try:
                # Update step status
                current_step.status = StepStatus.IN_PROGRESS
                
                # Get the tool for this step
                tool_name = current_step.tool
                try:
                    tool = self.tool_registry.get_tool(tool_name)
                except KeyError:
                    raise ValueError(f"Unknown tool: {tool_name}")
                
                # --- Handle GENERATE_ANSWER_PROMPT --- 
                step_params = current_step.parameters.copy() # Work with a copy
                if tool_name == "browser" and step_params.get("action") == "fill_text_field":
                    text_to_fill = step_params.get("text", "")
                    generate_prefix = "GENERATE_ANSWER_PROMPT:"
                    if isinstance(text_to_fill, str) and text_to_fill.startswith(generate_prefix):
                        prompt_for_llm = text_to_fill[len(generate_prefix):].strip()
                        logger.info(f"Detected text generation request for field: {step_params.get('selector')}")
                        
                        # Prepare context for the LLM
                        context = {
                            "profile": self.profile_store.get_all_values(),
                            "goal": self.working_memory.goal,
                            # TODO: Add job description if available
                        }
                        
                        try:
                            generated_answer = await self.llm_service.generate_text_answer(prompt_for_llm, context)
                            # Replace the parameter with the generated answer
                            step_params["text"] = generated_answer 
                            logger.info(f"Generated answer: {generated_answer[:100]}...")
                        except Exception as gen_e:
                            logger.error(f"Failed to generate text answer: {str(gen_e)}")
                            # Fail the step if generation fails
                            raise RuntimeError(f"Failed to generate required text answer: {str(gen_e)}") from gen_e
                # --- End Handle GENERATE_ANSWER_PROMPT ---
                
                # Execute the tool with potentially modified parameters
                logger.info(f"Executing step: {current_step.goal} using tool: {tool_name}")
                result = await tool.execute(**step_params)
                
                # Add observation
                self.working_memory.add_observation(source=tool_name, data=result)
                
                # Update step with result
                if result.get("success", False):
                    self.working_memory.update_step_result(result, StepStatus.SUCCEEDED)
                    success_count += 1
                else:
                    failure_reason = result.get("observation", "Unknown failure")
                    logger.warning(f"Step failed: {failure_reason}")
                    self.working_memory.update_step_result(result, StepStatus.FAILED)
                    failure_count += 1
                    
                    # Decide whether to continue or adapt plan
                    should_continue = await self._handle_step_failure(self.working_memory.current_step_index, result)
                    if not should_continue:
                        break
                
                # Move to next step
                self.working_memory.advance_to_next_step()
                
            except Exception as e:
                logger.error(f"Error executing step: {str(e)}", exc_info=True)
                self.working_memory.update_step_result(
                    {"success": False, "error": str(e), "observation": f"Exception: {str(e)}"},
                    StepStatus.FAILED
                )
                failure_count += 1
                
                # Move to next step despite failure
                self.working_memory.advance_to_next_step()
        
        # Clean up tools (especially important for browser)
        await self._cleanup_tools()
        
        # Determine final status
        final_status = self._determine_task_status(success_count, failure_count)
        self.working_memory.complete_task(final_status)
        
        logger.info(f"Plan execution completed with status: {final_status}")
        return final_status
    
    async def _handle_step_failure(self, failed_step_index: int, result: Dict[str, Any]) -> bool:
        """Handle a failed step, potentially by adapting the plan.
        
        Args:
            failed_step_index: The index of the step that failed
            result: The failure result
            
        Returns:
            True if execution should continue (after potential retry), False if it should stop
        """
        # Get state for LLM decision
        state = self.working_memory.get_state_dict()
        failed_step = self.working_memory.plan.steps[failed_step_index]
        
        # Add specific information about the failure
        state["current_failure"] = {
            "step": failed_step.dict(),
            "result": result
        }
        
        # Get tool specifications for potential recovery
        tool_specs = self.tool_registry.get_tool_specifications()
        
        try:
            # Ask LLM what to do next
            next_action_data = await self.llm_service.choose_next_action(state, tool_specs)
            
            reasoning = next_action_data.get("reasoning", "No reasoning provided")
            logger.info(f"Failure handling reasoning: {reasoning}")
            
            action = next_action_data.get("action", {})
            tool_name = action.get("tool")
            parameters = action.get("parameters")
            
            if tool_name == "abort":
                logger.info("LLM decided to abort the plan execution")
                return False # Stop execution
            
            if tool_name and parameters is not None:
                logger.info(f"LLM suggested retrying step {failed_step_index} with new action: {tool_name} - {parameters}")

                # 1. Get the tool
                try:
                    tool = self.tool_registry.get_tool(tool_name)
                except KeyError:
                    logger.error(f"Invalid tool suggested by LLM for retry: {tool_name}")
                    return True # Skip retry, continue

                # 2. Validate Parameters
                try:
                    tool_schema = tool._get_parameter_schema()
                    required_params = tool_schema.get('required', [])
                    all_allowed_params = set(tool_schema.get('properties', {}).keys())

                    # Check for missing required parameters
                    missing_params = [p for p in required_params if p not in parameters]
                    if missing_params:
                        raise ValueError(f"Missing required parameters: {missing_params}")

                    # Check for unknown parameters
                    unknown_params = set(parameters.keys()) - all_allowed_params
                    if unknown_params:
                        raise ValueError(f"Unknown parameters provided: {unknown_params}")

                    # Check parameter types (basic check)
                    for param_name, param_value in parameters.items():
                        param_schema = tool_schema['properties'].get(param_name, {})
                        expected_type_str = param_schema.get('type')
                        if expected_type_str == 'string' and not isinstance(param_value, str):
                            raise ValueError(f"Invalid type for '{param_name}'. Expected string, got {type(param_value).__name__}")
                        if expected_type_str == 'integer' and not isinstance(param_value, int):
                            raise ValueError(f"Invalid type for '{param_name}'. Expected integer, got {type(param_value).__name__}")
                        if expected_type_str == 'boolean' and not isinstance(param_value, bool):
                             raise ValueError(f"Invalid type for '{param_name}'. Expected boolean, got {type(param_value).__name__}")

                    logger.debug("LLM suggested parameters are valid.")

                except ValueError as validation_e:
                    logger.error(f"Invalid parameters suggested by LLM for retry: {str(validation_e)}")
                    return True # Skip retry, continue with next step
                except Exception as schema_e: # Catch errors getting/parsing schema
                     logger.error(f"Error during parameter schema validation: {str(schema_e)}")
                     return True # Skip retry

                # 3. Attempt Retry
                try:
                    retry_result = await tool.execute(**parameters)
                    self.working_memory.add_observation(source=f"{tool_name}_retry", data=retry_result)

                    if retry_result.get("success", False):
                        logger.info(f"Retry of step {failed_step_index} succeeded!")
                        # Update the original failed step to success with the retry result
                        self.working_memory.update_step_result(retry_result, StepStatus.SUCCEEDED)
                        return True # Continue execution
                    else:
                        logger.warning(f"Retry of step {failed_step_index} also failed: {retry_result.get('observation', 'Unknown failure')}")
                        # Keep the original failure status
                        return True # Continue execution
                except Exception as retry_e:
                    logger.error(f"Error during retry of step {failed_step_index}: {str(retry_e)}", exc_info=True)
                    # Keep the original failure status
                    return True # Continue execution
            else:
                logger.warning("LLM did not provide a valid retry action. Continuing with next step.")
                return True # Continue with the next step in the original plan
            
        except Exception as e:
            logger.error(f"Error in failure handling decision process: {str(e)}")
            # Default to continuing when there's an error in the decision process
            return True
    
    def _determine_task_status(self, success_count: int, failure_count: int) -> TaskStatus:
        """Determine the overall task status based on step successes and failures.
        
        Args:
            success_count: Number of successfully completed steps
            failure_count: Number of failed steps
            
        Returns:
            The overall task status
        """
        total_steps = success_count + failure_count
        
        # No steps executed
        if total_steps == 0:
            return TaskStatus.FAILED
            
        # All steps succeeded
        if failure_count == 0:
            return TaskStatus.SUCCEEDED
            
        # All steps failed
        if success_count == 0:
            return TaskStatus.FAILED
            
        # Some steps succeeded, some failed
        return TaskStatus.PARTIALLY_SUCCEEDED
    
    async def _cleanup_tools(self) -> None:
        """Clean up resources used by tools."""
        for tool_name in self.tool_registry.list_tools():
            try:
                tool = self.tool_registry.get_tool(tool_name)
                if hasattr(tool, "close") and callable(tool.close):
                    logger.info(f"Cleaning up tool: {tool_name}")
                    await tool.close()
            except Exception as e:
                logger.error(f"Error cleaning up tool {tool_name}: {str(e)}")
    
    def save_results(self, output_path: str) -> None:
        """Save the task results to a file.
        
        Args:
            output_path: Path to save the results to
        """
        results = self.working_memory.to_json()
        
        try:
            with open(output_path, 'w') as f:
                f.write(results)
            logger.info(f"Results saved to {output_path}")
        except Exception as e:
            logger.error(f"Error saving results: {str(e)}")

async def main():
    """Main entry point for running the agent from the command line."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run the AgentV0 autonomous agent")
    parser.add_argument("--goal", required=True, help="High-level goal for the agent to achieve")
    parser.add_argument("--profile", required=True, help="Path to user profile JSON file")
    parser.add_argument("--fallback", help="Path to fallback profile JSON file")
    parser.add_argument("--output", help="Path to save results to")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    
    args = parser.parse_args()
    
    # Create output path if not provided
    if not args.output:
        os.makedirs("run_results", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"run_results/{timestamp}.json"
    
    # Initialize and run the agent
    agent = AgentCore(
        profile_path=args.profile,
        fallback_path=args.fallback,
        headless=args.headless
    )
    
    # Execute the task
    status = await agent.execute_task(args.goal)
    
    # Save results
    agent.save_results(args.output)
    
    # Return appropriate exit code
    if status == TaskStatus.SUCCEEDED:
        logger.info("Task completed successfully")
        return 0
    elif status == TaskStatus.PARTIALLY_SUCCEEDED:
        logger.info("Task completed with partial success")
        return 1
    else:
        logger.error("Task failed")
        return 2

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 