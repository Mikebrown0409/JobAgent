"""Manages the crew of agents for the enterprise job application system."""

import asyncio
import json
import logging
import os
import time
import traceback
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime
from crewai import Crew, Agent, Task, Process
from crewai.tasks.task_output import TaskOutput
from langchain_core.language_models import BaseLLM

from enterprise_job_agent.config import Config
from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.tools.data_formatter import DataFormatter
from enterprise_job_agent.tools.form_interaction import FormInteraction
from enterprise_job_agent.agents.profile_adapter_agent import ProfileAdapterAgent
from enterprise_job_agent.agents.session_manager_agent import SessionManagerAgent
from enterprise_job_agent.agents.form_analyzer_agent import FormAnalyzerAgent
from enterprise_job_agent.agents.error_recovery_agent import ErrorRecoveryAgent
from enterprise_job_agent.tools.element_selector import ElementSelector
from enterprise_job_agent.core.frame_manager import AdvancedFrameManager
from enterprise_job_agent.core.llm_wrapper import LLMWrapper
from enterprise_job_agent.core.action_executor import ActionExecutor, ActionContext
from enterprise_job_agent.core.action_strategy_selector import ActionStrategySelector
from enterprise_job_agent.core.exceptions import ActionExecutionError

logger = logging.getLogger(__name__)

class JobApplicationCrew:
    """Manages the sequential execution of agents for the job application process."""
    
    def __init__(
        self, 
        url: str,                  # Required: Job URL
        user_profile: Dict[str, Any], # Required: User profile data
        browser_manager: BrowserManager, # Required: Initialized BrowserManager
        action_executor: ActionExecutor, # Required: Initialized ActionExecutor
        form_analyzer_agent: FormAnalyzerAgent, # Required: Initialized FormAnalyzerAgent
        profile_adapter_agent: ProfileAdapterAgent, # Required: Initialized ProfileAdapterAgent
        error_recovery_agent: ErrorRecoveryAgent, # Required: Initialized ErrorRecoveryAgent
        diagnostics_manager: DiagnosticsManager, # Required: Initialized DiagnosticsManager
        test_mode: bool = True      # Required: Test mode flag
    ):
        """Initialize the crew manager with all necessary pre-initialized components."""
        self.url = url
        self.user_profile = user_profile
        self.browser_manager = browser_manager
        self.action_executor = action_executor
        self.form_analyzer = form_analyzer_agent
        self.profile_adapter = profile_adapter_agent
        self.error_recovery_agent = error_recovery_agent
        self.diagnostics_manager = diagnostics_manager
        self.test_mode = test_mode
        self.logger = logging.getLogger(__name__)
        
        # No need for internal agent/task/crew setup if running sequentially
        self.logger.debug("JobApplicationCrew initialized for sequential execution.")

    async def run(self) -> Dict[str, Any]:
        """Execute the job application process sequentially using the provided agents."""
        run_id_str = self.diagnostics_manager.run_id if self.diagnostics_manager else "unknown_run"
        self.logger.info(f"Starting sequential job application process for URL: {self.url} (Run ID: {run_id_str}, Test Mode: {self.test_mode})")
        overall_success = False
        final_result = {}
        form_elements_list = []
        action_plan: List[ActionContext] = []
        execution_summary = {}

        try:
            # --- Step 1: Form Analysis --- 
            analysis_result_data = None
            with self.diagnostics_manager.track_stage("form_analysis"):
                try:
                    # Directly call the FormAnalyzerAgent method that interacts with the browser
                    # Ensure the agent has access to the necessary browser manager instance
                    analysis_result_data = await self.form_analyzer.analyze_form_with_browser(self.browser_manager, self.url)
                    
                    # Process the result (handle potential dict structure workaround if still needed)
                    # This logic should ideally live within the agent, but we replicate if necessary
                    if isinstance(analysis_result_data, dict) and "form_elements" in analysis_result_data:
                        form_elements_list = analysis_result_data.get("form_elements", [])
                        self.logger.debug(f"Extracted form_elements list from analysis dict result.")
                    elif isinstance(analysis_result_data, list):
                         form_elements_list = analysis_result_data # Assume direct list output if not dict
                         self.logger.debug(f"Received form_elements as a direct list from analysis.")
                    else:
                         # Handle unexpected format
                         raise TypeError(f"Unexpected format received from form analyzer: {type(analysis_result_data)}")

                    if not form_elements_list:
                        raise ValueError("Form analysis returned no valid elements.")
                        
                    self.logger.info(f"Form analysis successful. Found {len(form_elements_list)} elements.")
                    # Save intermediate result (use the raw data before potential transformation)
                    self.diagnostics_manager.save_intermediate_result("01_form_analysis.json", analysis_result_data)
                
                except Exception as e:
                    self.logger.error(f"Form analysis failed: {e}", exc_info=True)
                    # Save failed analysis attempt if possible
                    if analysis_result_data is not None: # Check if variable exists
                         self.diagnostics_manager.save_intermediate_result("01_form_analysis_failed.json", analysis_result_data)
                    raise ActionExecutionError(f"Form analysis failed: {e}") from e
            
            # --- Step 2: Profile Mapping (Action Plan Generation) --- 
            action_plan_dicts = [] # Store dict representation for saving
            with self.diagnostics_manager.track_stage("profile_mapping"):
                try:
                    # Directly call the ProfileAdapterAgent method
                    action_plan = await self.profile_adapter.map_profile_to_form(
                        user_profile=self.user_profile, 
                        form_elements=form_elements_list # Pass the extracted list
                    )
                    
                    if not action_plan:
                         raise ValueError("Profile mapping generated an empty action plan.")
                         
                    self.logger.info(f"Profile mapping successful. Generated {len(action_plan)} actions.")
                    # Convert ActionContext objects to dicts for saving
                    action_plan_dicts = [ctx.to_dict() for ctx in action_plan]
                    self.diagnostics_manager.save_intermediate_result("02_action_plan.json", action_plan_dicts)

                except Exception as e:
                    self.logger.error(f"Profile mapping failed: {e}", exc_info=True)
                    # Save failed mapping attempt if possible (e.g., save the input form_elements)
                    self.diagnostics_manager.save_intermediate_result("02_action_plan_failed_input.json", {"form_elements": form_elements_list})
                    raise ActionExecutionError(f"Profile mapping failed: {e}") from e
            
            # --- Step 3: Action Execution --- 
            with self.diagnostics_manager.track_stage("action_execution"):
                 try:
                    self.action_executor.set_test_mode(self.test_mode)
                    execution_summary = await self.action_executor.execute_form_actions(
                        actions=action_plan, 
                        stop_on_error=False # Get results even if some actions fail
                    )
                    self.logger.info(f"Action execution completed. Status: {execution_summary.get('status')}, Filled: {execution_summary.get('fields_filled')}, Failed: {execution_summary.get('fields_failed')}")
                    self.diagnostics_manager.save_intermediate_result("03_execution_summary.json", execution_summary)
                    
                    # Determine overall success based on execution results
                    # Consider a field failed if status is not 'completed' or explicitly failed
                    failed_count = execution_summary.get("fields_failed", 0)
                    overall_success = execution_summary.get("status") == "completed" and failed_count == 0

                 except Exception as e:
                    self.logger.error(f"Action execution failed critically: {e}", exc_info=True)
                    # Save partial summary if available
                    if execution_summary: 
                        self.diagnostics_manager.save_intermediate_result("03_execution_summary_failed.json", execution_summary)
                    raise ActionExecutionError(f"Action execution failed critically: {e}") from e

            # --- Step 4: Final Result Aggregation --- 
            final_result = {
                "status": "success" if overall_success else "failed",
                "run_id": run_id_str,
                "url": self.url,
                "test_mode": self.test_mode,
                "analysis_summary": {"elements_found": len(form_elements_list)},
                "mapping_summary": {"actions_generated": len(action_plan)},
                "execution_summary": execution_summary,
            }
            self.logger.info(f"Job application process finished. Overall status: {final_result['status']}")

        except ActionExecutionError as aee: # Catch specific errors from our flow
            error_stage = self.diagnostics_manager.current_stage or 'unknown stage'
            error_msg = f"Process failed during '{error_stage}': {aee}"
            self.logger.error(error_msg, exc_info=False) # Log concise error
            # Ensure stage is marked failed if context manager didn't catch it
            if self.diagnostics_manager.current_stage and self.diagnostics_manager.stages[error_stage].success is None:
                 self.diagnostics_manager.end_stage(success=False, error=str(aee))
            final_result = {"status": "error", "failed_stage": error_stage, "message": error_msg, "run_id": run_id_str}
            overall_success = False
        except Exception as e:
            error_stage = self.diagnostics_manager.current_stage or 'unknown stage'
            error_msg = f"An unexpected error occurred in CrewManager run during '{error_stage}': {e}"
            self.logger.error(error_msg, exc_info=True)
            # Ensure stage is marked failed
            if self.diagnostics_manager.current_stage and self.diagnostics_manager.stages[error_stage].success is None:
                 self.diagnostics_manager.end_stage(success=False, error=f"Unhandled exception: {str(e)}")
            final_result = {"status": "error", "failed_stage": error_stage, "message": error_msg, "run_id": run_id_str, "traceback": traceback.format_exc()}
            overall_success = False
            
        finally:
            # --- Step 5: Save Final Report --- 
            outcome_status = "SUCCESS" if overall_success else "FAILED"
            # Use message from final_result if available, otherwise generate default
            outcome_message = final_result.get("message", f"Run completed with status: {outcome_status.lower()}")
            
            # Add stage summary to the final report
            stage_diagnostics = self.diagnostics_manager.get_diagnostics() if self.diagnostics_manager else {}

            final_report_data = { 
                 "run_id": run_id_str,
                 "timestamp": datetime.now().isoformat(),
                 "url": self.url,
                 "status": outcome_status,
                 "message": outcome_message,
                 "test_mode": self.test_mode,
                 "final_summary": final_result, # Include detailed summary from try block
                 "stage_diagnostics": stage_diagnostics.get("stages", {}) # Add stage timing/status
            }
            # Use a consistent filename prefix
            report_filename = "_final_report.json" 
            try:
                 self.diagnostics_manager.save_intermediate_result(report_filename, final_report_data)
                 self.logger.info(f"Saved final report to {report_filename} for run {run_id_str}")
            except Exception as report_e:
                 self.logger.error(f"Failed to save final report {report_filename}: {report_e}")
        
        return final_result

    # Remove the old execute_job_application_process method if it exists
    # Remove _initialize_agents method if tasks are created directly
    # Remove the crewai Crew setup if running agents sequentially