"""Analytics utilities for tracking job application metrics and performance."""

import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Union

logger = logging.getLogger(__name__)

class ApplicationMetrics:
    """
    Tracks metrics for job applications.
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize application metrics.
        
        Args:
            storage_path: Path to store metrics data. If None, uses default location.
        """
        if storage_path:
            self.storage_path = storage_path
        else:
            # Use default location in user's home directory
            self.storage_path = os.path.expanduser("~/.jobagent/metrics")
            
        # Ensure directory exists
        os.makedirs(self.storage_path, exist_ok=True)
        
        self.current_session = {
            "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "start_time": time.time(),
            "end_time": None,
            "applications": [],
            "errors": [],
            "performance_metrics": {}
        }
    
    def start_application(self, job_url: str, company_name: Optional[str] = None, position_title: Optional[str] = None) -> str:
        """
        Start tracking a new job application.
        
        Args:
            job_url: URL of the job posting
            company_name: Name of the company
            position_title: Title of the position
            
        Returns:
            Application ID
        """
        app_id = f"app_{len(self.current_session['applications']) + 1}_{int(time.time())}"
        
        application = {
            "id": app_id,
            "job_url": job_url,
            "company_name": company_name,
            "position_title": position_title,
            "start_time": time.time(),
            "end_time": None,
            "duration": None,
            "steps": [],
            "current_step": None,
            "status": "in_progress",
            "errors": [],
            "form_elements": 0,
            "fields_filled": 0
        }
        
        self.current_session["applications"].append(application)
        
        logger.info(f"Started tracking application {app_id} for {position_title or 'unknown position'} at {company_name or 'unknown company'}")
        return app_id
    
    def complete_application(self, app_id: str, status: str = "completed", notes: Optional[str] = None) -> bool:
        """
        Mark an application as completed.
        
        Args:
            app_id: Application ID
            status: Final status (completed, failed, abandoned)
            notes: Additional notes
            
        Returns:
            True if successful, False otherwise
        """
        application = self._find_application(app_id)
        if not application:
            logger.error(f"Application {app_id} not found")
            return False
        
        application["end_time"] = time.time()
        application["duration"] = application["end_time"] - application["start_time"]
        application["status"] = status
        
        if notes:
            application["notes"] = notes
        
        if application["current_step"]:
            self.complete_step(app_id, application["current_step"]["id"], status)
        
        logger.info(f"Completed application {app_id} with status: {status}")
        return True
    
    def start_step(self, app_id: str, step_name: str, step_type: str) -> Optional[str]:
        """
        Start tracking a new step in the application.
        
        Args:
            app_id: Application ID
            step_name: Name of the step
            step_type: Type of step (form_analysis, profile_mapping, form_filling, etc.)
            
        Returns:
            Step ID or None if application not found
        """
        application = self._find_application(app_id)
        if not application:
            logger.error(f"Application {app_id} not found")
            return None
        
        # Complete the current step if one exists
        if application["current_step"]:
            self.complete_step(app_id, application["current_step"]["id"])
        
        step_id = f"step_{len(application['steps']) + 1}_{int(time.time())}"
        
        step = {
            "id": step_id,
            "name": step_name,
            "type": step_type,
            "start_time": time.time(),
            "end_time": None,
            "duration": None,
            "status": "in_progress",
            "metrics": {}
        }
        
        application["steps"].append(step)
        application["current_step"] = step
        
        logger.info(f"Started step {step_name} for application {app_id}")
        return step_id
    
    def complete_step(self, app_id: str, step_id: str, status: str = "completed") -> bool:
        """
        Mark a step as completed.
        
        Args:
            app_id: Application ID
            step_id: Step ID
            status: Final status (completed, failed, skipped)
            
        Returns:
            True if successful, False otherwise
        """
        application = self._find_application(app_id)
        if not application:
            logger.error(f"Application {app_id} not found")
            return False
        
        step = self._find_step(application, step_id)
        if not step:
            logger.error(f"Step {step_id} not found in application {app_id}")
            return False
        
        step["end_time"] = time.time()
        step["duration"] = step["end_time"] - step["start_time"]
        step["status"] = status
        
        # Clear current step if this was it
        if application["current_step"] and application["current_step"]["id"] == step_id:
            application["current_step"] = None
        
        logger.info(f"Completed step {step['name']} for application {app_id} with status: {status}")
        return True
    
    def log_form_metrics(self, app_id: str, total_elements: int, required_elements: int) -> bool:
        """
        Log form metrics for an application.
        
        Args:
            app_id: Application ID
            total_elements: Total number of form elements
            required_elements: Number of required elements
            
        Returns:
            True if successful, False otherwise
        """
        application = self._find_application(app_id)
        if not application:
            logger.error(f"Application {app_id} not found")
            return False
        
        application["form_elements"] = total_elements
        application["required_elements"] = required_elements
        
        logger.info(f"Logged form metrics for application {app_id}: {total_elements} elements, {required_elements} required")
        return True
    
    def increment_fields_filled(self, app_id: str, count: int = 1) -> bool:
        """
        Increment the count of fields filled.
        
        Args:
            app_id: Application ID
            count: Number of fields to increment by
            
        Returns:
            True if successful, False otherwise
        """
        application = self._find_application(app_id)
        if not application:
            logger.error(f"Application {app_id} not found")
            return False
        
        application["fields_filled"] += count
        
        logger.debug(f"Incremented fields filled for application {app_id} by {count}")
        return True
    
    def log_error(self, app_id: str, error_type: str, error_message: str, error_context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Log an error for an application.
        
        Args:
            app_id: Application ID
            error_type: Type of error
            error_message: Error message
            error_context: Additional context information
            
        Returns:
            True if successful, False otherwise
        """
        application = self._find_application(app_id)
        if not application:
            logger.error(f"Application {app_id} not found")
            return False
        
        error = {
            "timestamp": time.time(),
            "type": error_type,
            "message": error_message,
            "context": error_context or {}
        }
        
        # Add to application errors
        application["errors"].append(error)
        
        # Add to session errors
        self.current_session["errors"].append({
            "application_id": app_id,
            **error
        })
        
        logger.info(f"Logged error for application {app_id}: {error_type} - {error_message}")
        return True
    
    def log_step_metric(self, app_id: str, step_id: str, metric_name: str, metric_value: Any) -> bool:
        """
        Log a metric for a specific step.
        
        Args:
            app_id: Application ID
            step_id: Step ID
            metric_name: Name of the metric
            metric_value: Value of the metric
            
        Returns:
            True if successful, False otherwise
        """
        application = self._find_application(app_id)
        if not application:
            logger.error(f"Application {app_id} not found")
            return False
        
        step = self._find_step(application, step_id)
        if not step:
            logger.error(f"Step {step_id} not found in application {app_id}")
            return False
        
        step["metrics"][metric_name] = metric_value
        
        logger.debug(f"Logged metric {metric_name}={metric_value} for step {step_id} in application {app_id}")
        return True
    
    def save_session(self) -> str:
        """
        Save the current session metrics to disk.
        
        Returns:
            Path to the saved file
        """
        # Set end time if not already set
        if not self.current_session["end_time"]:
            self.current_session["end_time"] = time.time()
            
        # Calculate performance metrics
        total_apps = len(self.current_session["applications"])
        completed_apps = sum(1 for app in self.current_session["applications"] if app["status"] == "completed")
        failed_apps = sum(1 for app in self.current_session["applications"] if app["status"] == "failed")
        
        self.current_session["performance_metrics"] = {
            "total_applications": total_apps,
            "completed_applications": completed_apps,
            "failed_applications": failed_apps,
            "success_rate": (completed_apps / total_apps if total_apps > 0 else 0) * 100,
            "total_errors": len(self.current_session["errors"]),
            "total_duration": self.current_session["end_time"] - self.current_session["start_time"],
            "average_application_time": sum(
                (app["duration"] or 0) for app in self.current_session["applications"]
            ) / total_apps if total_apps > 0 else 0
        }
        
        # Save to file
        filename = f"session_{self.current_session['session_id']}.json"
        file_path = os.path.join(self.storage_path, filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.current_session, f, indent=2)
            
        logger.info(f"Saved session metrics to {file_path}")
        return file_path
    
    def _find_application(self, app_id: str) -> Optional[Dict[str, Any]]:
        """
        Find an application by ID.
        
        Args:
            app_id: Application ID
            
        Returns:
            Application dictionary or None if not found
        """
        for app in self.current_session["applications"]:
            if app["id"] == app_id:
                return app
        return None
    
    def _find_step(self, application: Dict[str, Any], step_id: str) -> Optional[Dict[str, Any]]:
        """
        Find a step by ID within an application.
        
        Args:
            application: Application dictionary
            step_id: Step ID
            
        Returns:
            Step dictionary or None if not found
        """
        for step in application["steps"]:
            if step["id"] == step_id:
                return step
        return None
    
    def get_application_summary(self, app_id: str) -> Dict[str, Any]:
        """
        Get a summary of an application.
        
        Args:
            app_id: Application ID
            
        Returns:
            Dictionary with application summary
        """
        application = self._find_application(app_id)
        if not application:
            logger.error(f"Application {app_id} not found")
            return {}
        
        # Calculate completion rate
        completion_rate = 0
        if application["form_elements"] > 0:
            completion_rate = (application["fields_filled"] / application["form_elements"]) * 100
        
        return {
            "id": application["id"],
            "company": application["company_name"] or "Unknown",
            "position": application["position_title"] or "Unknown",
            "status": application["status"],
            "duration": application["duration"] if application["duration"] is not None else 
                       (time.time() - application["start_time"]),
            "steps_completed": sum(1 for step in application["steps"] if step["status"] == "completed"),
            "total_steps": len(application["steps"]),
            "errors": len(application["errors"]),
            "completion_rate": completion_rate,
            "fields_filled": application["fields_filled"],
            "total_fields": application["form_elements"]
        }
    
    def get_session_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current session.
        
        Returns:
            Dictionary with session summary
        """
        total_apps = len(self.current_session["applications"])
        completed_apps = sum(1 for app in self.current_session["applications"] if app["status"] == "completed")
        
        return {
            "session_id": self.current_session["session_id"],
            "start_time": datetime.fromtimestamp(self.current_session["start_time"]).strftime("%Y-%m-%d %H:%M:%S"),
            "duration": time.time() - self.current_session["start_time"],
            "applications": {
                "total": total_apps,
                "completed": completed_apps,
                "failed": sum(1 for app in self.current_session["applications"] if app["status"] == "failed"),
                "in_progress": sum(1 for app in self.current_session["applications"] if app["status"] == "in_progress"),
                "success_rate": (completed_apps / total_apps if total_apps > 0 else 0) * 100
            },
            "errors": len(self.current_session["errors"]),
            "most_common_error": self._get_most_common_error()
        }
    
    def _get_most_common_error(self) -> str:
        """
        Get the most common error type in the session.
        
        Returns:
            Most common error type or "None" if no errors
        """
        if not self.current_session["errors"]:
            return "None"
        
        error_types = {}
        for error in self.current_session["errors"]:
            error_type = error["type"]
            if error_type in error_types:
                error_types[error_type] += 1
            else:
                error_types[error_type] = 1
        
        if not error_types:
            return "None"
        
        return max(error_types.items(), key=lambda x: x[1])[0]

# Create a global instance for easy access
metrics = ApplicationMetrics() 