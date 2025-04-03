"""Tools for generating detailed reports from job application attempts."""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
from pathlib import Path
import markdown2
import plotly.graph_objects as go
from jinja2 import Template

logger = logging.getLogger(__name__)

class ReportGenerator:
    """Generates detailed reports from job application attempts."""
    
    REPORT_TEMPLATE = """
# Job Application Report

## Overview
- **Job URL**: {{ job_url }}
- **Application Time**: {{ start_time }}
- **Overall Status**: {{ "✅ Success" if overall_success else "❌ Failed" }}
- **Total Duration**: {{ "%.2f"|format(total_duration) }}s

## Stage Performance
{% for stage in stages %}
### {{ stage.name }}
- **Status**: {{ "✅ Success" if stage.success else "❌ Failed" }}
- **Duration**: {{ "%.2f"|format(stage.duration) }}s
{% if not stage.success %}
- **Error**: {{ stage.error }}
- **Details**: 
```json
{{ stage.details | tojson(indent=2) }}
```
{% endif %}
{% endfor %}

## Recommendations
{% for rec in recommendations %}
- {{ rec }}
{% endfor %}

## Technical Details
```json
{{ technical_details | tojson(indent=2) }}
```
    """
    
    def __init__(self, output_dir: str = "reports"):
        """
        Initialize the report generator.
        
        Args:
            output_dir: Directory to store generated reports
        """
        self.logger = logging.getLogger(__name__)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def generate_report(
        self,
        diagnostics_report: Dict[str, Any],
        metrics_analysis: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate a detailed report from a job application attempt.
        
        Args:
            diagnostics_report: Report from DiagnosticsManager
            metrics_analysis: Optional analysis from MetricsCollector
            
        Returns:
            Path to the generated report file
        """
        # Prepare report data
        report_data = {
            "job_url": diagnostics_report["job_url"],
            "start_time": diagnostics_report["start_time"],
            "overall_success": diagnostics_report["overall_success"],
            "total_duration": diagnostics_report["summary"]["total_duration"],
            "stages": diagnostics_report["stages"],
            "recommendations": diagnostics_report["recommendations"],
            "technical_details": {
                "diagnostics": diagnostics_report,
                "metrics_analysis": metrics_analysis
            }
        }
        
        # Generate HTML report
        template = Template(self.REPORT_TEMPLATE)
        markdown_content = template.render(**report_data)
        html_content = markdown2.markdown(
            markdown_content,
            extras=["fenced-code-blocks", "tables"]
        )
        
        # Add performance visualizations if metrics available
        if metrics_analysis:
            html_content += self._generate_performance_charts(metrics_analysis)
        
        # Save report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.output_dir / f"report_{timestamp}.html"
        
        with open(report_file, "w") as f:
            f.write(self._wrap_html(html_content))
        
        self.logger.info(f"Generated report: {report_file}")
        return str(report_file)
    
    def _generate_performance_charts(self, metrics: Dict[str, Any]) -> str:
        """Generate performance visualization charts."""
        charts_html = "<h2>Performance Analysis</h2>"
        
        # Success rate over time
        success_fig = go.Figure(data=[
            go.Indicator(
                mode="gauge+number",
                value=metrics["success_rate"],
                title={"text": "Success Rate (%)"},
                gauge={"axis": {"range": [0, 100]}}
            )
        ])
        charts_html += success_fig.to_html(full_html=False)
        
        # Stage performance
        stage_names = list(metrics["stage_performance"].keys())
        success_rates = [
            metrics["stage_performance"][stage]["success_rate"]
            for stage in stage_names
        ]
        
        stage_fig = go.Figure(data=[
            go.Bar(
                x=stage_names,
                y=success_rates,
                name="Success Rate (%)"
            )
        ])
        stage_fig.update_layout(title="Stage Performance")
        charts_html += stage_fig.to_html(full_html=False)
        
        return charts_html
    
    def _wrap_html(self, content: str) -> str:
        """Wrap content in HTML boilerplate with styling."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Job Application Report</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    line-height: 1.6;
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 2rem;
                    color: #333;
                }}
                pre {{
                    background: #f6f8fa;
                    padding: 1rem;
                    border-radius: 4px;
                    overflow-x: auto;
                }}
                h1, h2, h3 {{
                    color: #2c3e50;
                }}
                .success {{
                    color: #27ae60;
                }}
                .failure {{
                    color: #e74c3c;
                }}
            </style>
        </head>
        <body>
            {content}
        </body>
        </html>
        """
    
    def generate_summary(self, reports_dir: Optional[str] = None) -> str:
        """
        Generate a summary of all reports in the directory.
        
        Args:
            reports_dir: Optional alternative directory to scan
            
        Returns:
            Path to the generated summary file
        """
        target_dir = Path(reports_dir) if reports_dir else self.output_dir
        
        # Collect all report data
        summaries = []
        for report_file in target_dir.glob("report_*.html"):
            try:
                # Extract key information from report filename and quick content scan
                timestamp = report_file.stem.split("_")[1]
                with open(report_file) as f:
                    content = f.read()
                    success = "✅ Success" in content
                    
                summaries.append({
                    "timestamp": timestamp,
                    "success": success,
                    "file": report_file.name
                })
            except Exception as e:
                self.logger.error(f"Error processing report {report_file}: {e}")
        
        # Generate summary HTML
        summary_html = """
        <h1>Job Application Reports Summary</h1>
        <table>
            <tr>
                <th>Timestamp</th>
                <th>Status</th>
                <th>Report</th>
            </tr>
        """
        
        for summary in sorted(summaries, key=lambda x: x["timestamp"], reverse=True):
            status_class = "success" if summary["success"] else "failure"
            status_text = "✅ Success" if summary["success"] else "❌ Failed"
            
            summary_html += f"""
            <tr>
                <td>{summary["timestamp"]}</td>
                <td class="{status_class}">{status_text}</td>
                <td><a href="{summary["file"]}">View Report</a></td>
            </tr>
            """
        
        summary_html += "</table>"
        
        # Save summary
        summary_file = target_dir / "summary.html"
        with open(summary_file, "w") as f:
            f.write(self._wrap_html(summary_html))
        
        self.logger.info(f"Generated summary: {summary_file}")
        return str(summary_file) 