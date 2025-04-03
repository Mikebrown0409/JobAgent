"""Tools for collecting and analyzing job application metrics."""

import logging
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import statistics

logger = logging.getLogger(__name__)

class MetricsCollector:
    """Collects and analyzes metrics for job applications."""
    
    def __init__(self, metrics_dir: str = "metrics"):
        """
        Initialize the metrics collector.
        
        Args:
            metrics_dir: Directory to store metrics files
        """
        self.logger = logging.getLogger(__name__)
        self.metrics_dir = Path(metrics_dir)
        self.metrics_dir.mkdir(exist_ok=True)
        self.current_session: Dict[str, Any] = {
            "start_time": datetime.now().isoformat(),
            "applications": []
        }
    
    def add_application_result(self, diagnostics_report: Dict[str, Any]) -> None:
        """
        Add results from a job application attempt.
        
        Args:
            diagnostics_report: Report from DiagnosticsManager
        """
        self.current_session["applications"].append(diagnostics_report)
        
        # Save after each application for durability
        self._save_session()
    
    def _save_session(self) -> None:
        """Save the current session to disk."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.metrics_dir / f"session_{timestamp}.json"
        
        with open(filepath, "w") as f:
            json.dump(self.current_session, f, indent=2)
    
    def analyze_performance(self, lookback_days: int = 7) -> Dict[str, Any]:
        """
        Analyze performance metrics over the specified time period.
        
        Args:
            lookback_days: Number of days to analyze
            
        Returns:
            Dictionary containing analysis results
        """
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        
        # Collect all relevant session files
        session_files = []
        for file in self.metrics_dir.glob("session_*.json"):
            try:
                with open(file) as f:
                    session = json.load(f)
                session_start = datetime.fromisoformat(session["start_time"])
                if session_start >= cutoff_date:
                    session_files.append(session)
            except Exception as e:
                self.logger.error(f"Error reading session file {file}: {e}")
        
        # Analyze metrics
        total_applications = 0
        successful_applications = 0
        stage_metrics: Dict[str, List[Dict[str, Any]]] = {}
        durations: List[float] = []
        common_failures: Dict[str, int] = {}
        
        for session in session_files:
            for app in session["applications"]:
                total_applications += 1
                if app["overall_success"]:
                    successful_applications += 1
                
                # Track stage metrics
                for stage in app["stages"]:
                    if stage["name"] not in stage_metrics:
                        stage_metrics[stage["name"]] = []
                    stage_metrics[stage["name"]].append({
                        "success": stage["success"],
                        "duration": stage["duration"],
                        "error": stage["error"] if not stage["success"] else None
                    })
                
                # Track duration
                if "summary" in app and "total_duration" in app["summary"]:
                    durations.append(app["summary"]["total_duration"])
                
                # Track failure reasons
                if not app["overall_success"]:
                    for stage in app["stages"]:
                        if not stage["success"] and stage["error"]:
                            error = stage["error"]
                            common_failures[error] = common_failures.get(error, 0) + 1
        
        # Calculate statistics
        success_rate = (successful_applications / total_applications * 100) if total_applications > 0 else 0
        
        stage_stats = {}
        for stage_name, metrics in stage_metrics.items():
            successes = sum(1 for m in metrics if m["success"])
            stage_stats[stage_name] = {
                "success_rate": (successes / len(metrics) * 100) if metrics else 0,
                "avg_duration": statistics.mean([m["duration"] for m in metrics if m["duration"] is not None]) if metrics else 0,
                "total_attempts": len(metrics)
            }
        
        # Sort failure reasons by frequency
        sorted_failures = sorted(
            common_failures.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]  # Top 5 most common failures
        
        return {
            "period_days": lookback_days,
            "total_applications": total_applications,
            "success_rate": success_rate,
            "avg_duration": statistics.mean(durations) if durations else 0,
            "stage_performance": stage_stats,
            "top_failures": dict(sorted_failures),
            "recommendations": self._generate_recommendations(stage_stats, sorted_failures)
        }
    
    def _generate_recommendations(
        self,
        stage_stats: Dict[str, Dict[str, Any]],
        common_failures: List[Tuple[str, int]]
    ) -> List[str]:
        """Generate recommendations based on performance analysis."""
        recommendations = []
        
        # Check for problematic stages
        for stage_name, stats in stage_stats.items():
            if stats["success_rate"] < 80:
                recommendations.append(
                    f"Investigate {stage_name}: {stats['success_rate']:.1f}% success rate "
                    f"over {stats['total_attempts']} attempts"
                )
        
        # Check for slow stages
        slow_stages = [
            (name, stats["avg_duration"])
            for name, stats in stage_stats.items()
            if stats["avg_duration"] > 5  # More than 5 seconds
        ]
        if slow_stages:
            for name, duration in sorted(slow_stages, key=lambda x: x[1], reverse=True)[:3]:
                recommendations.append(
                    f"Optimize {name}: averaging {duration:.1f}s per attempt"
                )
        
        # Add recommendations based on common failures
        for error, count in common_failures:
            if "selector not found" in error.lower():
                recommendations.append(
                    f"Improve element selection reliability: {error} occurred {count} times"
                )
            elif "timeout" in error.lower():
                recommendations.append(
                    f"Review timing/waiting strategy: {error} occurred {count} times"
                )
        
        return recommendations 