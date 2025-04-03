"""Diagnostics manager for job application system."""

import time
import logging
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
    
    def __init__(self):
        """Initialize the diagnostics manager."""
        self.stages: Dict[str, StageInfo] = {}
        self.current_stage: Optional[str] = None
        self.logger = logging.getLogger(__name__)
        self.application_start_time = time.time()
        
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