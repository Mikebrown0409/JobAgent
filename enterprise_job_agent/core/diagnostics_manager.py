"""Diagnostics manager for job application system."""

import time
import logging
import json
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from contextlib import contextmanager

logger = logging.getLogger(__name__)

@dataclass
class StageInfo:
    """Information about a stage in the job application process."""
    name: str
    start_time: float
    end_time: Optional[float] = None
    success: Optional[bool] = None
    duration: Optional[float] = None
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

class DiagnosticsManager:
    """Manages diagnostics for the job application process."""
    
    def __init__(self, run_id: str, enabled: bool = True, base_output_dir: str = "run_results"):
        """Initialize the diagnostics manager.
        
        Args:
            run_id: A unique identifier for this run (e.g., timestamp).
            enabled: Whether diagnostics are enabled.
            base_output_dir: The base directory to store results for all runs.
        """
        self.run_id = run_id
        self.enabled = enabled
        self.logger = logging.getLogger(__name__)
        self.stages: Dict[str, StageInfo] = {}
        self.current_stage: Optional[str] = None
        self.application_start_time = time.time()
        
        self.run_output_dir = os.path.join(base_output_dir, self.run_id)
        
        if self.enabled:
            try:
                os.makedirs(self.run_output_dir, exist_ok=True)
                self.logger.info(f"Diagnostics for run '{self.run_id}' will be saved to {self.run_output_dir}")
            except OSError as e:
                self.logger.error(f"Failed to create diagnostics directory {self.run_output_dir}: {e}")
                self.enabled = False # Disable if directory creation fails

    def save_intermediate_result(self, filename: str, data: Any) -> None:
        """Saves intermediate structured data as a JSON file within the run's directory.

        Args:
            filename: The name of the file (e.g., '01_form_analysis.json').
            data: The Python object (dict, list, etc.) to serialize and save.
        """
        if not self.enabled:
            self.logger.debug(f"Skipping save_intermediate_result for '{filename}' as diagnostics are disabled.")
            return

        if not filename.endswith('.json'):
            filename += '.json'
            
        filepath = os.path.join(self.run_output_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            self.logger.info(f"Successfully saved intermediate result to '{filepath}'")
        except TypeError as e:
            self.logger.error(f"Failed to serialize data to JSON for '{filepath}': {e}. Data type: {type(data)}")
        except OSError as e:
            self.logger.error(f"Failed to write intermediate result to '{filepath}': {e}")
        except Exception as e:
            self.logger.error(f"An unexpected error occurred while saving intermediate result to '{filepath}': {e}")

    def debug(self, message: str) -> None:
        """Log a debug message.
        
        Args:
            message: The message to log
        """
        self.logger.debug(message)
    
    def info(self, message: str) -> None:
        """Log an info message.
        
        Args:
            message: The message to log
        """
        self.logger.info(message)
    
    def warning(self, message: str) -> None:
        """Log a warning message.
        
        Args:
            message: The message to log
        """
        self.logger.warning(message)
    
    def error(self, message: str) -> None:
        """Log an error message.
        
        Args:
            message: The message to log
        """
        self.logger.error(message)
    
    def start_action(self, action_type: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Start tracking an action.
        
        Args:
            action_type: Type of action (e.g., 'fill', 'select', 'click')
            details: Optional details about the action
        """
        if not self.enabled:
            return
            
        if not self.current_stage:
            self.logger.warning(f"Starting action '{action_type}' without an active stage")
            
        action_name = f"action_{action_type}_{time.time()}"
        
        if details:
            log_details = f" ({', '.join(f'{k}={v}' for k, v in details.items())})"
        else:
            log_details = ""
            
        self.logger.debug(f"Starting action: {action_type}{log_details}")
        
        # Store action in current stage's details
        if self.current_stage and self.stages.get(self.current_stage):
            stage = self.stages[self.current_stage]
            if 'actions' not in stage.details:
                stage.details['actions'] = []
                
            action_info = {
                'type': action_type,
                'start_time': time.time(),
                'details': details or {}
            }
            
            stage.details['actions'].append(action_info)
            self._current_action_index = len(stage.details['actions']) - 1
    
    def end_action(self, success: bool, error: Optional[str] = None) -> None:
        """End tracking the current action.
        
        Args:
            success: Whether the action was successful
            error: Optional error message if the action failed
        """
        if not self.enabled or not self.current_stage:
            return
            
        stage = self.stages.get(self.current_stage)
        if not stage or 'actions' not in stage.details or not hasattr(self, '_current_action_index'):
            return
            
        try:
            actions = stage.details['actions']
            if self._current_action_index < 0 or self._current_action_index >= len(actions):
                return
                
            action = actions[self._current_action_index]
            action['end_time'] = time.time()
            action['duration'] = action['end_time'] - action['start_time']
            action['success'] = success
            
            if error:
                action['error'] = error
                
            action_type = action.get('type', 'unknown')
            details = action.get('details', {})
            
            if details:
                log_details = f" ({', '.join(f'{k}={v}' for k, v in details.items() if k != 'details')})"
            else:
                log_details = ""
                
            if success:
                self.logger.debug(f"Action {action_type}{log_details} completed successfully in {action['duration']:.2f}s")
            else:
                err_msg = f": {error}" if error else ""
                self.logger.debug(f"Action {action_type}{log_details} failed{err_msg} after {action['duration']:.2f}s")
                
        except Exception as e:
            self.logger.warning(f"Error recording action end: {e}")
    
    def start_stage(self, stage_name: str) -> None:
        """Start tracking a stage.
        
        Args:
            stage_name: Name of the stage
        """
        self.logger.info(f"Starting stage: {stage_name}")
        self.current_stage = stage_name
        self.stages[stage_name] = StageInfo(
            name=stage_name,
            start_time=time.time()
        )
    
    def end_stage(self, success: bool, error: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
        """End tracking a stage.
        
        Args:
            success: Whether the stage was successful
            error: Optional error message if the stage failed
            details: Optional details about the stage
        """
        if self.current_stage is None:
            self.logger.warning("No current stage to end")
            return
        
        stage = self.stages.get(self.current_stage)
        if not stage:
            self.logger.warning(f"Stage {self.current_stage} not found")
            return
        
        stage.end_time = time.time()
        stage.success = success
        stage.error = error
        stage.duration = stage.end_time - stage.start_time
        
        if details:
            stage.details.update(details)
        
        msg = f"Stage {self.current_stage} {'succeeded' if success else 'failed'}"
        if error:
            msg += f": {error}"
        msg += f" (took {stage.duration:.2f}s)"
        
        log_method = self.logger.info if success else self.logger.error
        log_method(msg)
        
        if not success and error:
            self.logger.error(f"Stage failed: {error}")
        
        self.current_stage = None
    
    @contextmanager
    def wrap_stage(self, stage_name: str):
        """Context manager for tracking a stage.
        
        Args:
            stage_name: Name of the stage
        """
        if not self.enabled:
            yield
            return
            
        self.start_stage(stage_name)
        try:
            yield
            self.end_stage(True)
        except Exception as e:
            self.end_stage(False, error=str(e))
            raise
    
    @contextmanager
    def track_stage(self, stage_name: str):
        """Context manager for tracking a stage.
        
        Args:
            stage_name: Name of the stage
        """
        self.start_stage(stage_name)
        try:
            yield
            self.end_stage(True)
        except Exception as e:
            self.end_stage(False, error=str(e))
            raise
    
    def get_diagnostics(self) -> Dict[str, Any]:
        """Get diagnostics information.
        
        Returns:
            Dict with diagnostics information
        """
        stages_info = {}
        for name, stage in self.stages.items():
            stages_info[name] = {
                "start_time": stage.start_time,
                "end_time": stage.end_time,
                "success": stage.success,
                "duration": stage.duration,
                "error": stage.error,
                "details": stage.details
            }
        
        # Calculate overall duration
        total_duration = time.time() - self.application_start_time
        
        return {
            "start_time": self.application_start_time,
            "duration": total_duration,
            "stages": stages_info
        } 