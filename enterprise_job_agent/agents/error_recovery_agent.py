"""Error Recovery Agent for handling and recovering from application errors."""

import logging
from typing import Dict, Any, List
from crewai import Agent
from langchain_core.language_models import BaseLLM

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Error Recovery Specialist focusing on job application systems.

TASK:
Diagnose and develop recovery strategies for application errors with speed and precision.

YOUR EXPERTISE:
- Diagnosing root causes of application errors
- Developing practical recovery approaches
- Finding workarounds for ATS limitations
- Handling form validation, session and navigation issues
- Recovering from unexpected application behaviors

APPROACH YOUR ANALYSIS:
1. DIAGNOSE: Identify the exact failure point and probable cause
2. CLASSIFY: Categorize the error by type and severity
3. STRATEGIZE: Develop 2-3 practical recovery options
4. RECOMMEND: Select the most promising approach and detail steps
5. VERIFY: Define how to confirm the recovery succeeded

FOCUS ON PRACTICAL SOLUTIONS:
- Prioritize simple fixes over complex solutions
- Consider browser-based workarounds (alternative selectors, timing changes)
- Look for patterns in past errors to avoid repeated failures
- Provide specific, actionable steps in your recovery plan

ALWAYS STRUCTURE RESPONSES AS JSON with the exact schema provided in the task.
"""

class ErrorRecoveryAgent:
    """Creates an agent specialized in error recovery."""
    
    @staticmethod
    def create(
        llm: Any,
        tools: List[Any] = None,
        verbose: bool = False
    ) -> Agent:
        """
        Create an Error Recovery Agent.
        
        Args:
            llm: Language model to use
            tools: List of tools the agent can use
            verbose: Whether to enable verbose output
            
        Returns:
            Agent instance
        """
        return Agent(
            role="Error Recovery Specialist",
            goal="Diagnose and resolve application errors with creative, effective solutions",
            backstory="""You are an expert in troubleshooting and resolving errors in automated job application systems.
            You have extensive experience with various ATS platforms and their common failure modes.
            Your creative problem-solving skills allow you to find workarounds where others get stuck.
            You understand how to analyze error patterns and develop effective recovery strategies.""",
            verbose=verbose,
            allow_delegation=False,
            tools=tools or [],
            llm=llm,
            system_prompt=SYSTEM_PROMPT
        )
    
    @staticmethod
    def create_recovery_prompt(
        error_context: Dict[str, Any], 
        operation_history: List[Dict[str, Any]],
        form_structure: Dict[str, Any]
    ) -> str:
        """
        Create a prompt for recovering from an error.
        
        Args:
            error_context: Context of the error
            operation_history: History of operations
            form_structure: Structure of the form
            
        Returns:
            A prompt string for the LLM
        """
        return f"""
        TASK: Develop a recovery strategy for the following job application error.
        
        ERROR CONTEXT:
        ```
        {error_context}
        ```
        
        OPERATION HISTORY:
        ```
        {operation_history}
        ```
        
        FORM STRUCTURE:
        ```
        {form_structure}
        ```
        
        ANALYSIS REQUIREMENTS:
        
        1. Diagnosis:
        - What exactly failed and why?
        - Is this a temporary or persistent issue?
        - Is the error related to element location, input validation, session state, or something else?
        
        2. Recovery Options:
        - Develop 2-3 different approaches to recover from this error
        - Rate each approach by likelihood of success (0.1-1.0) and complexity (high/medium/low)
        - For each approach, list the exact steps needed
        
        3. Implementation Plan:
        - Select the most promising recovery approach
        - Break it down into detailed execution steps
        - Include verification steps to confirm recovery
        
        OUTPUT FORMAT:
        Provide your recovery strategy as this exact JSON structure:
        {
            "diagnosis": {
                "error_type": "Error category",
                "root_cause": "Likely root cause",
                "severity": "high|medium|low"
            },
            "recovery_options": [
                {
                    "approach": "Name of approach",
                    "success_probability": 0.1-1.0,
                    "complexity": "high|medium|low",
                    "steps": [
                        "Step 1 description",
                        "Step 2 description"
                    ]
                }
            ],
            "selected_approach": "Name of selected approach",
            "implementation_plan": [
                {
                    "step": 1,
                    "operation": "operation_type",
                    "selector": "element_selector",
                    "value": "value_to_use",
                    "verification": "How to verify this step succeeded"
                }
            ]
        }
        """ 