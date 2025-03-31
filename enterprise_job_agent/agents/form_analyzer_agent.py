"""Form Analyzer Agent for detecting and analyzing job application forms."""

import logging
from typing import Dict, Any, List
from crewai import Agent
from langchain_core.language_models import BaseLLM

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Form Structure Analyst specializing in job application forms.

YOUR TASK:
Analyze job application forms to extract clear structured data for form automation.

YOUR EXPERTISE:
- Identifying all form elements and their relationships
- Categorizing fields by purpose and importance
- Understanding field validation requirements
- Recognizing multi-page application flows
- Detecting common ATS (Applicant Tracking System) patterns

APPROACH:
1. Identify each form element by ID, type and purpose
2. Prioritize fields by importance (required > optional > supplementary)
3. Group fields into logical sections
4. Detect dependencies between fields
5. Note navigation elements and submission buttons

ATTENTION TO DETAIL:
- Consider field names, labels, placeholders and attributes
- Look for required field indicators
- Identify field validation requirements (e.g., email format, character limits)
- Detect dropdown options and select fields
- Note file upload fields and requirements

ALWAYS STRUCTURE YOUR ANALYSIS AS JSON following the exact schema provided in the task.
"""

class FormAnalyzerAgent:
    """Creates an agent specialized in form analysis."""
    
    @staticmethod
    def create(
        llm: Any,
        tools: List[Any] = None,
        verbose: bool = False
    ) -> Agent:
        """
        Create a Form Analyzer Agent.
        
        Args:
            llm: Language model to use
            tools: List of tools the agent can use
            verbose: Whether to enable verbose output
            
        Returns:
            Agent instance
        """
        return Agent(
            role="Form Structure Analyst",
            goal="Analyze job application forms to create detailed, actionable structured representations",
            backstory="""You are an expert in analyzing web forms with years of experience working with job application systems.
            You excel at identifying form elements, their relationships, and strategic importance.
            Your analysis guides automated systems to intelligently fill applications without hardcoding.""",
            verbose=verbose,
            allow_delegation=False,
            tools=tools or [],
            llm=llm,
            system_prompt=SYSTEM_PROMPT
        )
    
    @staticmethod
    def create_analyzing_prompt(form_data: Dict[str, Any]) -> str:
        """
        Create a prompt for analyzing a form structure.
        
        Args:
            form_data: Raw form data to analyze
            
        Returns:
            A prompt string for the LLM
        """
        return f"""
        TASK: Analyze the job application form data and provide a structured JSON representation.
        
        FORM DATA:
        ```
        {form_data}
        ```
        
        ANALYSIS REQUIREMENTS:
        For each form element:
        1. Assign importance level (high/medium/low) based on:
           - Required status (required = high importance)
           - Field purpose (contact info = high, preferences = medium)
           - Application impact (education/experience = high)
        
        2. Categorize each field by purpose:
           - personal_info (name, email, phone)
           - contact (address, city, state)
           - education (school, degree, graduation date)
           - experience (company, role, dates, responsibilities)
           - skills (technical, soft skills)
           - preferences (salary, location, remote)
           - diversity (gender, ethnicity, veteran status)
           - other (custom questions)
        
        3. Identify field dependencies and relationships
        
        4. Note validation requirements (patterns, formats, limits)
        
        GROUP FIELDS into logical sections based on purpose.
        
        OUTPUT FORMAT:
        Return your analysis in this exact JSON structure:
        {
            "form_structure": {
                "sections": [
                    {
                        "name": "section_name",
                        "importance": "high|medium|low",
                        "fields": [
                            {
                                "id": "field_id",
                                "label": "field_label",
                                "type": "field_type",
                                "purpose": "field_purpose",
                                "importance": "high|medium|low",
                                "required": true|false,
                                "validation": "any validation requirements",
                                "dependencies": ["ids of dependent fields"],
                                "selector_strategies": [
                                    "strategy1",
                                    "strategy2"
                                ]
                            }
                        ]
                    }
                ],
                "navigation": {
                    "multi_page": true|false,
                    "navigation_elements": [
                        {
                            "label": "element_label",
                            "purpose": "next|previous|submit",
                            "selector": "element_selector"
                        }
                    ]
                }
            },
            "strategic_insights": [
                "Insight 1 about how to approach this form",
                "Insight 2 about potential challenges"
            ]
        }
        """ 