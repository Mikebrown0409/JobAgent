"""Core application state management for job applications."""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json

from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.tools.metrics_collector import MetricsCollector
from enterprise_job_agent.tools.report_generator import ReportGenerator

logger = logging.getLogger(__name__)

@dataclass
class ApplicationContext:
    """Context for a single job application attempt."""
    job_url: str
    start_time: datetime = field(default_factory=datetime.now)
    form_structure: Dict[str, Any] = field(default_factory=dict)
    field_mappings: Dict[str, Any] = field(default_factory=dict)
    current_stage: str = ""
    stage_data: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    success: bool = False

class ApplicationState:
    """Manages state and coordination for job applications."""
    
    def __init__(
        self,
        output_dir: str = "output",
        metrics_dir: str = "metrics",
        reports_dir: str = "reports"
    ):
        """
        Initialize the application state manager.
        
        Args:
            output_dir: Base directory for output
            metrics_dir: Directory for metrics
            reports_dir: Directory for reports
        """
        self.base_dir = Path(output_dir)
        self.base_dir.mkdir(exist_ok=True)
        
        # Initialize managers
        self.diagnostics_manager = DiagnosticsManager()
        self.metrics_collector = MetricsCollector(metrics_dir)
        self.report_generator = ReportGenerator(reports_dir)
        
        # State
        self.current_context: Optional[ApplicationContext] = None
        self.previous_contexts: List[ApplicationContext] = []
    
    def start_application(self, job_url: str) -> None:
        """
        Start a new job application attempt.
        
        Args:
            job_url: URL of the job to apply for
        """
        # Store previous context if exists
        if self.current_context:
            self.previous_contexts.append(self.current_context)
        
        # Create new context
        self.current_context = ApplicationContext(job_url=job_url)
        
        # Start diagnostics
        self.diagnostics_manager.start_application(job_url)
        logger.info(f"Starting new application for {job_url}")
    
    def set_stage(self, stage_name: str, data: Optional[Dict[str, Any]] = None) -> None:
        """
        Set the current application stage.
        
        Args:
            stage_name: Name of the current stage
            data: Optional data associated with the stage
        """
        if not self.current_context:
            raise RuntimeError("No active application context")
        
        self.current_context.current_stage = stage_name
        if data:
            self.current_context.stage_data[stage_name] = data
        
        self.diagnostics_manager.start_stage(stage_name)
        logger.info(f"Entering stage: {stage_name}")
    
    def end_stage(self, success: bool, error: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
        """
        End the current stage.
        
        Args:
            success: Whether the stage was successful
            error: Optional error message
            details: Optional details about the stage
        """
        if not self.current_context:
            raise RuntimeError("No active application context")
        
        if error:
            self.current_context.errors.append({
                "stage": self.current_context.current_stage,
                "error": error,
                "details": details or {}
            })
        
        self.diagnostics_manager.end_stage(success, error, details)
        logger.info(f"Completed stage {self.current_context.current_stage}: {'success' if success else 'failed'}")
    
    def update_form_structure(self, structure: Dict[str, Any]) -> None:
        """
        Update the form structure information.
        
        Args:
            structure: Analyzed form structure
        """
        if not self.current_context:
            raise RuntimeError("No active application context")
        
        self.current_context.form_structure = structure
        logger.debug("Updated form structure")
    
    def update_field_mappings(self, mappings: Dict[str, Any]) -> None:
        """
        Update the field mappings.
        
        Args:
            mappings: Field mapping information
        """
        if not self.current_context:
            raise RuntimeError("No active application context")
        
        self.current_context.field_mappings = mappings
        logger.debug("Updated field mappings")
    
    def complete_application(self, success: bool) -> str:
        """
        Complete the current application attempt.
        
        Args:
            success: Whether the application was successful
            
        Returns:
            Path to the generated report
        """
        if not self.current_context:
            raise RuntimeError("No active application context")
        
        self.current_context.success = success
        
        # Get diagnostics report
        diagnostics_report = self.diagnostics_manager.get_report()
        
        # Add to metrics
        self.metrics_collector.add_application_result(diagnostics_report)
        
        # Generate performance analysis
        metrics_analysis = self.metrics_collector.analyze_performance()
        
        # Generate report
        report_path = self.report_generator.generate_report(
            diagnostics_report,
            metrics_analysis
        )
        
        # Save application data
        self._save_application_data()
        
        logger.info(f"Completed application for {self.current_context.job_url}")
        return report_path
    
    def _save_application_data(self) -> None:
        """Save the current application data to disk."""
        if not self.current_context:
            return
            
        # Create unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.base_dir / f"application_{timestamp}.json"
        
        # Prepare data
        data = {
            "job_url": self.current_context.job_url,
            "start_time": self.current_context.start_time.isoformat(),
            "form_structure": self.current_context.form_structure,
            "field_mappings": self.current_context.field_mappings,
            "stages": self.current_context.stage_data,
            "errors": self.current_context.errors,
            "success": self.current_context.success
        }
        
        # Save to file
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved application data to {filename}")
    
    def get_application_history(self) -> List[Dict[str, Any]]:
        """
        Get history of previous applications.
        
        Returns:
            List of previous application contexts
        """
        history = []
        for context in self.previous_contexts:
            history.append({
                "job_url": context.job_url,
                "start_time": context.start_time.isoformat(),
                "success": context.success,
                "error_count": len(context.errors)
            })
        return history 