"""
Working Memory - Runtime State Management

Manages the agent's state during a single run including:
- Current goal and plan
- Step results and observations  
- Error tracking
- Execution context
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class StepResult:
    """Result of executing a single plan step."""
    step_number: int
    action: str
    tool: str
    parameters: Dict[str, Any]
    success: bool
    result: Dict[str, Any]
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    duration: Optional[float] = None  # seconds


@dataclass
class Observation:
    """Observation from the environment after an action."""
    source: str  # tool name
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ErrorRecord:
    """Record of an error that occurred."""
    error_type: str
    message: str
    context: Dict[str, Any]
    step_number: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)


class WorkingMemory:
    """
    Manages the agent's working memory during task execution.
    
    This includes the current goal, execution plan, step results,
    observations, and error tracking.
    """
    
    def __init__(self):
        """Initialize working memory."""
        self.logger = logging.getLogger(__name__)
        
        # Core execution state
        self.goal: Optional[str] = None
        self.plan: List[Dict[str, Any]] = []
        self.current_step: int = 0
        
        # Execution tracking
        self.step_results: List[StepResult] = []
        self.observations: List[Observation] = []
        self.errors: List[ErrorRecord] = []
        
        # Context and metadata
        self.context: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}
        
        # Session info
        self.session_start: datetime = datetime.now()
        self.last_update: datetime = datetime.now()
    
    def set_goal(self, goal: str) -> None:
        """Set the current goal."""
        self.goal = goal
        self.last_update = datetime.now()
        self.logger.info(f"Goal set: {goal}")
    
    def set_plan(self, plan: List[Dict[str, Any]]) -> None:
        """Set the execution plan."""
        self.plan = plan
        self.current_step = 0
        self.last_update = datetime.now()
        self.logger.info(f"Plan set with {len(plan)} steps")
    
    def add_step_result(self, step_number: int, result: Dict[str, Any]) -> None:
        """Add result of a plan step execution."""
        step_result = StepResult(
            step_number=step_number,
            action=result.get('action', 'unknown'),
            tool=result.get('tool', 'unknown'),
            parameters=result.get('parameters', {}),
            success=result.get('success', False),
            result=result,
            error=result.get('error'),
            duration=result.get('duration')
        )
        
        self.step_results.append(step_result)
        self.current_step = max(self.current_step, step_number)
        self.last_update = datetime.now()
        
        self.logger.info(f"Step {step_number} result added: {'success' if step_result.success else 'failed'}")
    
    def add_observation(self, source: str, data: Dict[str, Any]) -> None:
        """Add an observation from the environment."""
        observation = Observation(source=source, data=data)
        self.observations.append(observation)
        self.last_update = datetime.now()
        
        self.logger.debug(f"Observation added from {source}")
    
    def add_error(self, message: str, error_type: str = "GeneralError", 
                  context: Optional[Dict[str, Any]] = None, 
                  step_number: Optional[int] = None) -> None:
        """Add an error record."""
        error_record = ErrorRecord(
            error_type=error_type,
            message=message,
            context=context or {},
            step_number=step_number
        )
        
        self.errors.append(error_record)
        self.last_update = datetime.now()
        
        self.logger.error(f"Error recorded: {message}")
    
    def update_context(self, key: str, value: Any) -> None:
        """Update context information."""
        self.context[key] = value
        self.last_update = datetime.now()
    
    def set_context(self, key: str, value: Any) -> None:
        """Set context information (alias for update_context)."""
        self.update_context(key, value)
    
    def get_context(self, key: Optional[str] = None) -> Any:
        """Get current execution context or specific context value."""
        if key is not None:
            return self.context.get(key)
        
        return {
            "goal": self.goal,
            "current_step": self.current_step,
            "total_steps": len(self.plan),
            "context": self.context,
            "last_successful_step": self._get_last_successful_step(),
            "error_count": len(self.errors),
            "session_duration": (datetime.now() - self.session_start).total_seconds()
        }
    
    def _get_last_successful_step(self) -> Optional[int]:
        """Get the number of the last successful step."""
        for result in reversed(self.step_results):
            if result.success:
                return result.step_number
        return None
    
    def get_current_step_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the current step."""
        if self.current_step < len(self.plan):
            return self.plan[self.current_step]
        return None
    
    def get_next_step_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the next step."""
        next_step = self.current_step + 1
        if next_step < len(self.plan):
            return self.plan[next_step]
        return None
    
    def get_step_results_summary(self) -> Dict[str, Any]:
        """Get summary of step execution results."""
        if not self.step_results:
            return {"total": 0, "successful": 0, "failed": 0, "success_rate": 0.0}
        
        successful = sum(1 for result in self.step_results if result.success)
        failed = len(self.step_results) - successful
        
        return {
            "total": len(self.step_results),
            "successful": successful,
            "failed": failed,
            "success_rate": successful / len(self.step_results) if self.step_results else 0.0
        }
    
    def get_recent_observations(self, limit: int = 5) -> List[Observation]:
        """Get the most recent observations."""
        return self.observations[-limit:] if self.observations else []
    
    def get_recent_errors(self, limit: int = 5) -> List[ErrorRecord]:
        """Get the most recent errors."""
        return self.errors[-limit:] if self.errors else []
    
    def has_errors(self) -> bool:
        """Check if any errors have occurred."""
        return len(self.errors) > 0
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of errors that occurred."""
        if not self.errors:
            return {"total": 0, "types": {}}
        
        error_types = {}
        for error in self.errors:
            error_types[error.error_type] = error_types.get(error.error_type, 0) + 1
        
        return {
            "total": len(self.errors),
            "types": error_types,
            "recent": [{"type": e.error_type, "message": e.message} for e in self.errors[-3:]]
        }
    
    def clear_errors(self) -> None:
        """Clear all error records."""
        self.errors.clear()
        self.last_update = datetime.now()
        self.logger.info("Error records cleared")
    
    def reset(self) -> None:
        """Reset working memory for a new task."""
        self.goal = None
        self.plan = []
        self.current_step = 0
        self.step_results.clear()
        self.observations.clear()
        self.errors.clear()
        self.context.clear()
        self.metadata.clear()
        self.session_start = datetime.now()
        self.last_update = datetime.now()
        
        self.logger.info("Working memory reset")
    
    def clear(self) -> None:
        """Clear the working memory (alias for reset)."""
        self.reset()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert working memory to dictionary for serialization."""
        return {
            "goal": self.goal,
            "plan": self.plan,
            "current_step": self.current_step,
            "step_results": [
                {
                    "step_number": r.step_number,
                    "action": r.action,
                    "tool": r.tool,
                    "parameters": r.parameters,
                    "success": r.success,
                    "result": r.result,
                    "error": r.error,
                    "timestamp": r.timestamp.isoformat(),
                    "duration": r.duration
                }
                for r in self.step_results
            ],
            "observations": [
                {
                    "source": o.source,
                    "data": o.data,
                    "timestamp": o.timestamp.isoformat()
                }
                for o in self.observations
            ],
            "errors": [
                {
                    "error_type": e.error_type,
                    "message": e.message,
                    "context": e.context,
                    "step_number": e.step_number,
                    "timestamp": e.timestamp.isoformat()
                }
                for e in self.errors
            ],
            "context": self.context,
            "metadata": self.metadata,
            "session_start": self.session_start.isoformat(),
            "last_update": self.last_update.isoformat(),
            "summary": {
                "step_results": self.get_step_results_summary(),
                "error_summary": self.get_error_summary(),
                "session_duration": (datetime.now() - self.session_start).total_seconds()
            }
        }
    
    def __str__(self) -> str:
        """String representation of working memory."""
        return f"WorkingMemory(goal='{self.goal}', steps={len(self.plan)}, current={self.current_step}, errors={len(self.errors)})" 