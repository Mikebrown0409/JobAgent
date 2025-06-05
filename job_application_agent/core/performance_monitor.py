"""
Performance Monitor - Enterprise Performance Tracking

Advanced performance monitoring system for tracking agent performance,
form filling success rates, AI model performance, and user satisfaction metrics.
"""

import asyncio
import logging
import time
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path
import statistics

from job_application_agent.core.config import Config


@dataclass
class PerformanceMetrics:
    """Individual performance measurement."""
    timestamp: datetime
    operation: str
    duration: float
    success: bool
    details: Dict[str, Any]
    error_message: Optional[str] = None


@dataclass
class SessionMetrics:
    """Session-level performance metrics."""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    total_applications: int = 0
    successful_applications: int = 0
    total_fields_filled: int = 0
    successful_fields_filled: int = 0
    ai_content_generated: int = 0
    semantic_matches: int = 0
    average_application_time: float = 0.0
    platform_breakdown: Dict[str, int] = None
    
    def __post_init__(self):
        if self.platform_breakdown is None:
            self.platform_breakdown = {}


class PerformanceMonitor:
    """
    Enterprise performance monitoring system.
    
    Tracks:
    - Application success rates
    - Form filling performance
    - AI model performance
    - Response times and latency
    - Platform-specific metrics
    - Resource utilization
    """
    
    def __init__(self, config: Config):
        """Initialize the performance monitor."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Performance data storage
        self.metrics: List[PerformanceMetrics] = []
        self.session_metrics: Dict[str, SessionMetrics] = {}
        self.current_session_id = self._generate_session_id()
        
        # Real-time statistics
        self.real_time_stats = {
            'current_operations': {},
            'recent_success_rate': 0.0,
            'average_response_time': 0.0,
            'ai_model_performance': {},
            'platform_performance': {}
        }
        
        # Initialize current session
        self.session_metrics[self.current_session_id] = SessionMetrics(
            session_id=self.current_session_id,
            start_time=datetime.now()
        )
        
        # Performance thresholds
        self.thresholds = {
            'application_time_warning': 300.0,  # 5 minutes
            'application_time_critical': 600.0,  # 10 minutes
            'success_rate_warning': 0.8,  # 80%
            'success_rate_critical': 0.6,  # 60%
            'field_fill_time_warning': 5.0,  # 5 seconds per field
        }
        
        # Initialize storage
        self._ensure_directories()
    
    def start_operation(self, operation: str, details: Optional[Dict[str, Any]] = None) -> str:
        """
        Start tracking a performance operation.
        
        Args:
            operation: Name of the operation
            details: Additional operation details
            
        Returns:
            Operation ID for tracking
        """
        operation_id = f"{operation}_{int(time.time() * 1000)}"
        
        self.real_time_stats['current_operations'][operation_id] = {
            'operation': operation,
            'start_time': time.time(),
            'details': details or {}
        }
        
        return operation_id
    
    def end_operation(self, operation_id: str, success: bool, 
                     details: Optional[Dict[str, Any]] = None,
                     error_message: Optional[str] = None) -> None:
        """
        End tracking a performance operation.
        
        Args:
            operation_id: Operation ID from start_operation
            success: Whether the operation succeeded
            details: Additional operation details
            error_message: Error message if operation failed
        """
        if operation_id not in self.real_time_stats['current_operations']:
            self.logger.warning(f"Unknown operation ID: {operation_id}")
            return
        
        operation_data = self.real_time_stats['current_operations'].pop(operation_id)
        duration = time.time() - operation_data['start_time']
        
        # Create performance metric
        metric = PerformanceMetrics(
            timestamp=datetime.now(),
            operation=operation_data['operation'],
            duration=duration,
            success=success,
            details={**operation_data['details'], **(details or {})},
            error_message=error_message
        )
        
        self.metrics.append(metric)
        
        # Update real-time statistics
        self._update_real_time_stats(metric)
        
        # Check for performance issues
        self._check_performance_thresholds(metric)
    
    def track_application_result(self, job_url: str, result: Dict[str, Any]) -> None:
        """Track a complete job application result."""
        session = self.session_metrics[self.current_session_id]
        session.total_applications += 1
        
        if result.get('success'):
            session.successful_applications += 1
        
        # Extract detailed metrics from result
        if 'workflow_results' in result:
            for workflow_step in result['workflow_results']:
                if 'successful_fills' in workflow_step.get('summary', {}):
                    session.successful_fields_filled += workflow_step['summary']['successful_fills']
                if 'total_fields' in workflow_step.get('summary', {}):
                    session.total_fields_filled += workflow_step['summary']['total_fields']
        
        # Track AI content generation
        if 'ai_content_generated' in result:
            session.ai_content_generated += result['ai_content_generated']
        
        # Track platform
        platform = self._detect_platform(job_url)
        if platform:
            session.platform_breakdown[platform] = session.platform_breakdown.get(platform, 0) + 1
        
        # Update session averages
        if session.total_applications > 0:
            session.average_application_time = statistics.mean([
                m.duration for m in self.metrics 
                if m.operation == 'job_application' and m.timestamp >= session.start_time
            ])
    
    def track_ai_performance(self, ai_operation: str, success: bool, 
                           confidence: Optional[float] = None,
                           details: Optional[Dict[str, Any]] = None) -> None:
        """Track AI model performance metrics."""
        ai_stats = self.real_time_stats['ai_model_performance']
        
        if ai_operation not in ai_stats:
            ai_stats[ai_operation] = {
                'total_calls': 0,
                'successful_calls': 0,
                'average_confidence': 0.0,
                'confidence_scores': []
            }
        
        operation_stats = ai_stats[ai_operation]
        operation_stats['total_calls'] += 1
        
        if success:
            operation_stats['successful_calls'] += 1
        
        if confidence is not None:
            operation_stats['confidence_scores'].append(confidence)
            operation_stats['average_confidence'] = statistics.mean(
                operation_stats['confidence_scores'][-100:]  # Keep last 100 scores
            )
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        session = self.session_metrics[self.current_session_id]
        
        # Calculate success rates
        application_success_rate = (
            session.successful_applications / session.total_applications 
            if session.total_applications > 0 else 0.0
        )
        
        field_fill_success_rate = (
            session.successful_fields_filled / session.total_fields_filled 
            if session.total_fields_filled > 0 else 0.0
        )
        
        # Recent performance (last hour)
        recent_cutoff = datetime.now() - timedelta(hours=1)
        recent_metrics = [m for m in self.metrics if m.timestamp >= recent_cutoff]
        recent_success_rate = (
            len([m for m in recent_metrics if m.success]) / len(recent_metrics)
            if recent_metrics else 0.0
        )
        
        return {
            'session_id': self.current_session_id,
            'session_duration': (datetime.now() - session.start_time).total_seconds(),
            'overall_performance': {
                'application_success_rate': application_success_rate,
                'field_fill_success_rate': field_fill_success_rate,
                'total_applications': session.total_applications,
                'total_fields_filled': session.total_fields_filled,
                'ai_content_generated': session.ai_content_generated,
                'average_application_time': session.average_application_time
            },
            'recent_performance': {
                'success_rate_last_hour': recent_success_rate,
                'operations_last_hour': len(recent_metrics)
            },
            'ai_performance': self.real_time_stats['ai_model_performance'],
            'platform_breakdown': session.platform_breakdown,
            'current_operations': len(self.real_time_stats['current_operations']),
            'performance_alerts': self._get_performance_alerts()
        }
    
    def get_detailed_analytics(self) -> Dict[str, Any]:
        """Get detailed analytics for enterprise reporting."""
        if not self.metrics:
            return {'error': 'No performance data available'}
        
        # Group metrics by operation type
        operations = {}
        for metric in self.metrics:
            if metric.operation not in operations:
                operations[metric.operation] = []
            operations[metric.operation].append(metric)
        
        analytics = {}
        for operation, metrics_list in operations.items():
            successful = [m for m in metrics_list if m.success]
            failed = [m for m in metrics_list if not m.success]
            
            analytics[operation] = {
                'total_operations': len(metrics_list),
                'successful_operations': len(successful),
                'failed_operations': len(failed),
                'success_rate': len(successful) / len(metrics_list) if metrics_list else 0,
                'average_duration': statistics.mean([m.duration for m in metrics_list]),
                'median_duration': statistics.median([m.duration for m in metrics_list]),
                'min_duration': min([m.duration for m in metrics_list]),
                'max_duration': max([m.duration for m in metrics_list]),
                'duration_std_dev': statistics.stdev([m.duration for m in metrics_list]) if len(metrics_list) > 1 else 0,
                'common_errors': self._analyze_common_errors([m for m in metrics_list if not m.success])
            }
        
        return {
            'total_metrics': len(self.metrics),
            'time_range': {
                'start': min([m.timestamp for m in self.metrics]).isoformat(),
                'end': max([m.timestamp for m in self.metrics]).isoformat()
            },
            'operations': analytics,
            'trends': self._calculate_performance_trends(),
            'recommendations': self._generate_performance_recommendations()
        }
    
    async def save_performance_data(self) -> None:
        """Save performance data to file."""
        try:
            performance_file = Path(self.config.results_dir) / f"performance_{self.current_session_id}.json"
            
            data = {
                'session_metrics': {k: asdict(v) for k, v in self.session_metrics.items()},
                'detailed_metrics': [asdict(m) for m in self.metrics],
                'summary': self.get_performance_summary(),
                'analytics': self.get_detailed_analytics()
            }
            
            # Convert datetime objects to strings for JSON serialization
            data_str = json.dumps(data, default=str, indent=2)
            
            with open(performance_file, 'w') as f:
                f.write(data_str)
            
            self.logger.info(f"Performance data saved to {performance_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to save performance data: {str(e)}")
    
    def _update_real_time_stats(self, metric: PerformanceMetrics) -> None:
        """Update real-time statistics."""
        # Update recent success rate (last 50 operations)
        recent_metrics = self.metrics[-50:]
        if recent_metrics:
            self.real_time_stats['recent_success_rate'] = (
                len([m for m in recent_metrics if m.success]) / len(recent_metrics)
            )
        
        # Update average response time
        if self.metrics:
            self.real_time_stats['average_response_time'] = statistics.mean([
                m.duration for m in self.metrics[-20:]  # Last 20 operations
            ])
    
    def _check_performance_thresholds(self, metric: PerformanceMetrics) -> None:
        """Check if performance thresholds are exceeded."""
        if metric.operation == 'job_application':
            if metric.duration > self.thresholds['application_time_critical']:
                self.logger.critical(f"CRITICAL: Application took {metric.duration:.2f}s (threshold: {self.thresholds['application_time_critical']}s)")
            elif metric.duration > self.thresholds['application_time_warning']:
                self.logger.warning(f"WARNING: Application took {metric.duration:.2f}s (threshold: {self.thresholds['application_time_warning']}s)")
        
        # Check success rate
        if self.real_time_stats['recent_success_rate'] < self.thresholds['success_rate_critical']:
            self.logger.critical(f"CRITICAL: Success rate dropped to {self.real_time_stats['recent_success_rate']:.1%}")
        elif self.real_time_stats['recent_success_rate'] < self.thresholds['success_rate_warning']:
            self.logger.warning(f"WARNING: Success rate is {self.real_time_stats['recent_success_rate']:.1%}")
    
    def _detect_platform(self, job_url: str) -> Optional[str]:
        """Detect job platform from URL."""
        platform_patterns = {
            'greenhouse': 'greenhouse.io',
            'lever': 'lever.co',
            'workday': 'workday.com',
            'smartrecruiters': 'smartrecruiters.com',
            'icims': 'icims.com',
            'ashby': 'ashbyhq.com',
            'google': 'careers.google.com',
            'apple': 'jobs.apple.com',
            'tesla': 'tesla.com',
            'amazon': 'amazon.jobs'
        }
        
        for platform, pattern in platform_patterns.items():
            if pattern in job_url:
                return platform
        
        return 'unknown'
    
    def _get_performance_alerts(self) -> List[Dict[str, Any]]:
        """Get current performance alerts."""
        alerts = []
        
        # Check success rate
        if self.real_time_stats['recent_success_rate'] < self.thresholds['success_rate_critical']:
            alerts.append({
                'type': 'critical',
                'category': 'success_rate',
                'message': f"Success rate critically low: {self.real_time_stats['recent_success_rate']:.1%}",
                'threshold': self.thresholds['success_rate_critical']
            })
        
        # Check response time
        if self.real_time_stats['average_response_time'] > self.thresholds['application_time_warning']:
            alerts.append({
                'type': 'warning',
                'category': 'response_time',
                'message': f"Average response time high: {self.real_time_stats['average_response_time']:.2f}s",
                'threshold': self.thresholds['application_time_warning']
            })
        
        return alerts
    
    def _analyze_common_errors(self, failed_metrics: List[PerformanceMetrics]) -> List[Dict[str, Any]]:
        """Analyze common error patterns."""
        error_counts = {}
        for metric in failed_metrics:
            if metric.error_message:
                error_counts[metric.error_message] = error_counts.get(metric.error_message, 0) + 1
        
        return [
            {'error': error, 'count': count, 'percentage': count / len(failed_metrics) * 100}
            for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        ]
    
    def _calculate_performance_trends(self) -> Dict[str, Any]:
        """Calculate performance trends over time."""
        if len(self.metrics) < 10:
            return {'insufficient_data': True}
        
        # Split metrics into recent and historical
        split_point = len(self.metrics) // 2
        historical = self.metrics[:split_point]
        recent = self.metrics[split_point:]
        
        historical_success_rate = len([m for m in historical if m.success]) / len(historical)
        recent_success_rate = len([m for m in recent if m.success]) / len(recent)
        
        historical_avg_time = statistics.mean([m.duration for m in historical])
        recent_avg_time = statistics.mean([m.duration for m in recent])
        
        return {
            'success_rate_trend': recent_success_rate - historical_success_rate,
            'response_time_trend': recent_avg_time - historical_avg_time,
            'trend_direction': 'improving' if recent_success_rate > historical_success_rate else 'declining'
        }
    
    def _generate_performance_recommendations(self) -> List[str]:
        """Generate performance improvement recommendations."""
        recommendations = []
        
        # Success rate recommendations
        if self.real_time_stats['recent_success_rate'] < 0.8:
            recommendations.append("Consider updating field matching algorithms - success rate below 80%")
        
        # Response time recommendations
        if self.real_time_stats['average_response_time'] > 120:
            recommendations.append("Optimize browser interactions - average response time over 2 minutes")
        
        # AI performance recommendations
        ai_perf = self.real_time_stats['ai_model_performance']
        for operation, stats in ai_perf.items():
            if stats['total_calls'] > 10 and stats['successful_calls'] / stats['total_calls'] < 0.7:
                recommendations.append(f"Review {operation} AI model performance - success rate below 70%")
        
        return recommendations
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    def _ensure_directories(self) -> None:
        """Ensure required directories exist."""
        Path(self.config.results_dir).mkdir(parents=True, exist_ok=True) 