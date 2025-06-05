import logging
import json
import time
from typing import Dict, Any, List, Optional, Union
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field
import uuid

logger = logging.getLogger("WorkingMemory")

class TaskStatus(str, Enum):
    """Enum for tracking the status of a task."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIALLY_SUCCEEDED = "partially_succeeded"

class StepStatus(str, Enum):
    """Enum for tracking the status of a plan step."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"

class PlanStep(BaseModel):
    """A single step in a plan."""
    tool: str = Field(..., description="The tool to use for this step")
    parameters: Dict[str, Any] = Field(..., description="Parameters for the tool")
    goal: str = Field(..., description="The goal of this step")
    status: StepStatus = Field(default=StepStatus.PENDING, description="Current status of the step")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Result of executing the step")
    error: Optional[str] = Field(default=None, description="Error message if the step failed")
    
    class Config:
        use_enum_values = True

class Plan(BaseModel):
    """A complete plan for achieving a goal."""
    goal: str = Field(..., description="The high-level goal of the plan")
    steps: List[PlanStep] = Field(..., description="List of steps to execute")
    
    class Config:
        use_enum_values = True

class Observation(BaseModel):
    """A single observation from interacting with the environment."""
    timestamp: float = Field(default_factory=time.time, description="When the observation was made")
    source: str = Field(..., description="Source of the observation (e.g., tool name)")
    data: Dict[str, Any] = Field(..., description="The observation data")
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }

class WorkingMemory:
    """Holds the agent's state during a single run.
    
    This includes the current plan, observations, results of steps, and a scratchpad
    for intermediate reasoning.
    """
    
    def __init__(self, run_id: Optional[str] = None, goal: Optional[str] = None):
        """Initialize the working memory.
        
        Args:
            run_id: Unique identifier for this run (generated if not provided)
            goal: High-level goal for this run
        """
        self.run_id = run_id or f"run_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self.goal = goal
        self.plan: Optional[Plan] = None
        self.observations: List[Observation] = []
        self.current_step_index: Optional[int] = None
        self.status: TaskStatus = TaskStatus.NOT_STARTED
        self.errors: List[str] = []
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        self.scratchpad: Dict[str, Any] = {}
        
        logger.info(f"Initialized working memory for run {self.run_id}")
    
    def set_plan(self, plan: Plan) -> None:
        """Set the execution plan.
        
        Args:
            plan: The plan to execute
        """
        self.plan = plan
        self.status = TaskStatus.IN_PROGRESS
        self.current_step_index = 0
        logger.info(f"Set plan with {len(plan.steps)} steps for goal: {plan.goal}")
    
    def get_current_step(self) -> Optional[PlanStep]:
        """Get the current step in the plan.
        
        Returns:
            The current step, or None if no plan or all steps complete
        """
        if self.plan is None or self.current_step_index is None:
            return None
        
        if self.current_step_index >= len(self.plan.steps):
            return None
            
        return self.plan.steps[self.current_step_index]
    
    def advance_to_next_step(self) -> Optional[PlanStep]:
        """Advance to the next step in the plan.
        
        Returns:
            The next step, or None if no more steps
        """
        if self.plan is None or self.current_step_index is None:
            return None
            
        self.current_step_index += 1
        
        if self.current_step_index >= len(self.plan.steps):
            logger.info("Reached end of plan")
            return None
            
        next_step = self.plan.steps[self.current_step_index]
        logger.info(f"Advanced to step {self.current_step_index + 1}: {next_step.goal}")
        return next_step
    
    def add_observation(self, source: str, data: Dict[str, Any]) -> Observation:
        """Add an observation to memory.
        
        Args:
            source: Source of the observation (e.g., tool name)
            data: The observation data
            
        Returns:
            The created Observation object
        """
        observation = Observation(source=source, data=data)
        self.observations.append(observation)
        return observation
    
    def update_step_result(self, result: Dict[str, Any], status: StepStatus = StepStatus.SUCCEEDED) -> None:
        """Update the result of the current step.
        
        Args:
            result: The result data
            status: The new status of the step
        """
        if self.plan is None or self.current_step_index is None:
            logger.warning("Cannot update step result: No current step")
            return
            
        if self.current_step_index >= len(self.plan.steps):
            logger.warning("Cannot update step result: Current step index out of range")
            return
            
        current_step = self.plan.steps[self.current_step_index]
        current_step.result = result
        current_step.status = status
        
        if status == StepStatus.FAILED:
            error_msg = result.get("error", "Unknown error")
            current_step.error = error_msg
            self.errors.append(f"Step {self.current_step_index + 1} failed: {error_msg}")
            
        logger.info(f"Updated result for step {self.current_step_index + 1} with status: {status}")
    
    def complete_task(self, status: TaskStatus) -> None:
        """Mark the task as complete with the given status.
        
        Args:
            status: The final status of the task
        """
        self.status = status
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        logger.info(f"Task completed with status {status} in {duration:.2f} seconds")
    
    def add_to_scratchpad(self, key: str, value: Any) -> None:
        """Add data to the scratchpad for temporary storage.
        
        Args:
            key: Key to store the value under
            value: The value to store
        """
        self.scratchpad[key] = value
    
    def get_from_scratchpad(self, key: str, default: Any = None) -> Any:
        """Get data from the scratchpad.
        
        Args:
            key: The key to retrieve
            default: Default value if key doesn't exist
            
        Returns:
            The stored value, or the default if not found
        """
        return self.scratchpad.get(key, default)
    
    def get_state_dict(self) -> Dict[str, Any]:
        """Get a dictionary representation of the current state.
        
        This is useful for serializing the state or providing it to the LLM.
        
        Returns:
            Dictionary with the current state
        """
        # Get the last few observations (most recent first)
        recent_observations = self.observations[-5:] if self.observations else []
        
        state = {
            "run_id": self.run_id,
            "goal": self.goal,
            "status": self.status,
            "errors": self.errors,
            "current_step_index": self.current_step_index,
            "recent_observations": [obs.dict() for obs in recent_observations],
            "scratchpad": self.scratchpad
        }
        
        # Add plan information if available
        if self.plan:
            state["plan"] = {
                "goal": self.plan.goal,
                "total_steps": len(self.plan.steps),
                "completed_steps": sum(1 for step in self.plan.steps 
                                     if step.status in [StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.SKIPPED]),
                "current_step": self.get_current_step().dict() if self.get_current_step() else None
            }
        
        return state
    
    def to_json(self) -> str:
        """Convert the working memory to a JSON string.
        
        Returns:
            JSON string representation
        """
        state = self.get_state_dict()
        
        # Add more detailed information for full serialization
        if self.plan:
            state["plan"]["steps"] = [step.dict() for step in self.plan.steps]
            
        state["all_observations"] = [obs.dict() for obs in self.observations]
        state["start_time"] = self.start_time
        state["end_time"] = self.end_time
        
        return json.dumps(state, default=str, indent=2) 