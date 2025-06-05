import logging
import time
import os
import json
import ast
from typing import Dict, Any, List, Optional, Tuple, Union
from enum import Enum
import asyncio
import google.generativeai as genai
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger("LLMService")

# Initialize API key for Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY not found in environment variables")


class TaskType(str, Enum):
    PLANNING = "planning"
    ACTION_SELECTION = "action_selection"
    FIELD_MAPPING = "field_mapping"
    TEXT_GENERATION = "text_generation"


class Plan(BaseModel):
    """A structured plan consisting of a sequence of steps."""
    goal: str = Field(..., description="The high-level goal of the plan")
    steps: List[Dict[str, Any]] = Field(..., description="List of steps to execute")


class LLMService:
    """Service for interacting with Large Language Models.
    
    This class centralizes all LLM interactions and provides methods for
    specific tasks like planning, action selection, field mapping, and text generation.
    """
    
    def __init__(self, model_name: str = "gemini-1.5-flash"):
        """Initialize the LLM service.
        
        Args:
            model_name: The name of the model to use
        """
        self.model_name = model_name
        self.safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
        ]
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 2  # seconds
        
        # Initialize the model with a check to make sure the API key is available
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is required")
            
        try:
            # Initialize model for generation
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={"temperature": 0.0, "top_p": 0.95, "top_k": 0},
                safety_settings=self.safety_settings
            )
            logger.info(f"Initialized {model_name} model")
        except Exception as e:
            logger.error(f"Failed to initialize model: {str(e)}")
            raise
    
    async def _call_model(self, prompt: str, task_type: TaskType, system_instruction: str, temperature: float = 0.0) -> str:
        """Make an API call to the model with retries.
        
        Args:
            prompt: The user prompt
            task_type: The type of task being performed
            system_instruction: The system instruction to guide the model
            temperature: The temperature for generation (higher = more creative)
            
        Returns:
            The model's response text
            
        Raises:
            Exception: If all retries fail
        """
        logger.info(f"Calling model for {task_type.value} task")
        
        # Configure generation parameters based on task type
        if task_type == TaskType.PLANNING or task_type == TaskType.ACTION_SELECTION:
            temperature = 0.2  # Slightly higher for planning/reasoning
        elif task_type == TaskType.TEXT_GENERATION:
            temperature = 0.7  # Higher for creative text generation
        
        # Configure generation for this call
        generation_config = {
            "temperature": temperature,
            "top_p": 0.95,
            "top_k": 0,
            "max_output_tokens": 2048
        }
        
        retries = 0
        while retries <= self.max_retries:
            try:
                # Create a new model instance with the specific generation config
                model = genai.GenerativeModel(
                    model_name=self.model_name,
                    generation_config=generation_config,
                    safety_settings=self.safety_settings
                )
                
                # Combine system instruction and user prompt for models that don't support system role
                combined_prompt = f"{system_instruction}\n\nUSER PROMPT:\n{prompt}"
                
                # Make the API call with combined prompt under user role
                response = model.generate_content(
                    contents=[
                        # {"role": "system", "parts": [system_instruction]},
                        {"role": "user", "parts": [combined_prompt]}
                    ]
                )
                
                # Extract and return the text
                return response.text
                
            except Exception as e:
                retries += 1
                logger.warning(f"API call failed (attempt {retries}/{self.max_retries}): {str(e)}")
                
                if retries <= self.max_retries:
                    # Exponential backoff
                    wait_time = self.retry_delay * (2 ** (retries - 1))
                    logger.info(f"Waiting {wait_time} seconds before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All {self.max_retries} retries failed for {task_type.value} task")
                    raise
    
    async def generate_plan(self, goal: str, available_tools: List[Dict[str, Any]], page_elements: List[Dict[str, Any]], profile_data: Dict[str, Any]) -> Plan:
        """Generate a plan for achieving a goal using available tools and page context.
        
        Args:
            goal: The high-level goal to achieve
            available_tools: List of tool specifications available to the agent
            page_elements: List of interactive elements found on the current page
            profile_data: The user's profile data (for context like file paths)
            
        Returns:
            A structured Plan object with steps
        """
        logger.info(f"Generating plan for goal: {goal}")
        
        # Format the available tools, page elements, and relevant profile data for the prompt
        tools_text = json.dumps(available_tools, indent=2)
        elements_text = json.dumps(page_elements, indent=2) if page_elements else "No interactive elements found."
        # Include relevant profile data like file paths
        profile_context = {
             "resume_path": profile_data.get("resume_path"),
             "cover_letter_path": profile_data.get("cover_letter_path")
        }
        profile_text = json.dumps(profile_context, indent=2)
        
        # Create the system instruction
        system_instruction = """
        You are an expert planner for an autonomous agent. Your task is to break down a high-level goal into a 
        sequence of concrete, executable steps using the available tools. Each step should specify:
        1. The tool to use
        2. The parameters to pass to that tool
        3. The specific sub-goal that step is trying to achieve
        
        Generate a plan that is efficient, robust, and achieves the specified goal.
        
        IMPORTANT: Output ONLY the raw JSON object representing the plan, following the schema below.
        Use ONLY standard CSS selectors (no pseudo-classes like :contains).
        Use ONLY the parameters defined for each tool in the schema.
        Do NOT include markdown formatting (like ```json), introductory text, explanations, or concluding remarks.
        
        JSON Schema:
        {
            "goal": "the original goal",
            "steps": [
                {
                    "tool": "tool_name",
                    "parameters": {"param1": "value1", ...},
                    "goal": "what this step accomplishes"
                },
                ...
            ]
        }
        """
        
        # Create the user prompt
        prompt = f"""
        GOAL: {goal}
        
        AVAILABLE TOOLS:
        {tools_text}
        
        CURRENT PAGE ELEMENTS:
        {elements_text}

        USER PROFILE INFO (for context):
        {profile_text}
        
        Please generate a detailed plan to accomplish the full goal: {goal}
        
        IMPORTANT INSTRUCTIONS:
        - Use the selectors provided in the CURRENT PAGE ELEMENTS list for all browser actions.
        - For standard fields (name, email, phone, etc.), plan to fill them directly.
        - For file uploads (resume, cover letter), plan the 'upload_file' action using the path from USER PROFILE INFO.
        - For custom questions or free-text fields requiring unique answers (e.g., "Why work here?", "Describe a challenge..."),
          plan a 'fill_text_field' action, but set the 'text' parameter to start with the special prefix
          'GENERATE_ANSWER_PROMPT:' followed by the actual question/prompt for the LLM to answer.
        - Do not invent selectors or parameters.
        - Use ONLY the actions and parameters defined in the AVAILABLE TOOLS schema.
        - Use standard CSS selectors.
        """
        
        # Call the model
        response_text = await self._call_model(
            prompt=prompt,
            task_type=TaskType.PLANNING,
            system_instruction=system_instruction,
            temperature=0.2
        )
        
        try:
            # Attempt to extract JSON if wrapped in markdown
            if response_text.strip().startswith("```json"):
                response_text = response_text.strip()[7:-3].strip() # Remove ```json and ```
            elif response_text.strip().startswith("```"):
                 response_text = response_text.strip()[3:-3].strip() # Remove ```

            # Parse the JSON response
            plan_dict = json.loads(response_text)
            # Validate and create the Plan object
            plan = Plan(**plan_dict)
            logger.info(f"Generated plan with {len(plan.steps)} steps")
            return plan
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse plan JSON: {str(e)}")
            logger.debug(f"Raw LLM response for plan generation:\n---\n{response_text}\n---")
            raise ValueError(f"Model did not return valid JSON: {str(e)}")
        except Exception as e:
            logger.error(f"Error validating plan: {str(e)}")
            raise
    
    async def choose_next_action(self, state: Dict[str, Any], available_tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Choose the next action to take based on the current state.
        
        Args:
            state: The current state of the agent's working memory
            available_tools: List of tool specifications available to the agent
            
        Returns:
            An action specification with tool name and parameters
        """
        logger.info("Choosing next action based on current state")
        
        # Format the available tools and state for the prompt
        tools_text = json.dumps(available_tools, indent=2)
        state_text = json.dumps(state, indent=2)
        
        # Create the system instruction
        system_instruction = """
        You are an intelligent agent deciding on the next action to take. Based on the current state and available tools,
        select the most appropriate action that advances toward the goal. Your selection should include the tool name
        and any required parameters.
        
        Output ONLY valid JSON matching this schema:
        Use ONLY standard CSS selectors (no pseudo-classes like :contains).
        Use ONLY the parameters defined for each tool in the AVAILABLE TOOLS schema.
        {
            "reasoning": "explanation of why you chose this action",
            "action": {
                "tool": "tool_name",
                "parameters": {"param1": "value1", ...}
            }
        }
        """
        
        # Create the user prompt
        prompt = f"""
        CURRENT STATE:
        {state_text}
        
        AVAILABLE TOOLS:
        {tools_text}
        
        Please determine the next best action to take to advance toward the goal.
        Use standard CSS selectors and only parameters defined in the tool schema.
        """
        
        # Call the model
        response_text = await self._call_model(
            prompt=prompt,
            task_type=TaskType.ACTION_SELECTION,
            system_instruction=system_instruction,
            temperature=0.2
        )
        
        try:
            # Attempt to extract JSON if wrapped in markdown
            if response_text.strip().startswith("```json"):
                response_text = response_text.strip()[7:-3].strip() # Remove ```json and ```
            elif response_text.strip().startswith("```"):
                 response_text = response_text.strip()[3:-3].strip() # Remove ```

            # Parse the JSON response
            action_dict = json.loads(response_text)
            logger.info(f"Chose next action: {action_dict.get('action', {}).get('tool', 'unknown')}") # Safer logging
            return action_dict
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse action JSON: {str(e)}")
            logger.debug(f"Raw response: {response_text}")
            raise ValueError(f"Model did not return valid JSON: {str(e)}")
        except Exception as e:
            logger.error(f"Error in action selection: {str(e)}")
            raise
    
    async def map_profile_to_form(self, profile_data: Dict[str, Any], form_structure: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Map user profile data to form fields.
        
        Args:
            profile_data: The user's profile information
            form_structure: Structured information about the form fields
            
        Returns:
            A list of mappings from selectors to values/actions
        """
        logger.info(f"Mapping profile data to {len(form_structure)} form fields")
        
        # Create the system instruction
        system_instruction = """
        You are a form-filling assistant. Your task is to map user profile data to form fields on a webpage.
        For each form field, determine the appropriate value from the profile or specify that a custom response
        needs to be generated.
        
        Output ONLY valid JSON as a list of mappings. For each mapping, include:
        1. The selector for the form field
        2. Either a direct value OR an action to generate text with a specific prompt
        
        Follow this schema:
        [
            {
                "selector": "CSS selector",
                "value": "direct value from profile"
            },
            {
                "selector": "CSS selector for field needing generated text",
                "action": "generate_text_answer",
                "prompt": "specific instructions for generating text"
            },
            ...
        ]
        
        Never generate executable code. Only map values to fields or request text generation.
        """
        
        # Format the profile and form structure for the prompt
        profile_json = json.dumps(profile_data, indent=2)
        form_json = json.dumps(form_structure, indent=2)
        
        # Create the user prompt
        prompt = f"""
        USER PROFILE:
        {profile_json}
        
        FORM STRUCTURE:
        {form_json}
        
        Please map the profile data to the form fields. For free-text fields that need a custom response
        (like cover letters, "Why do you want to work here?", etc.), specify the "action": "generate_text_answer"
        and include a detailed prompt.
        """
        
        # Call the model
        response_text = await self._call_model(
            prompt=prompt,
            task_type=TaskType.FIELD_MAPPING,
            system_instruction=system_instruction,
            temperature=0.0
        )
        
        try:
            # Parse the JSON response
            mappings = json.loads(response_text)
            if not isinstance(mappings, list):
                raise ValueError("Expected a list of mappings")
                
            # Basic validation of each mapping
            for mapping in mappings:
                if "selector" not in mapping:
                    raise ValueError(f"Mapping missing 'selector': {mapping}")
                if "value" not in mapping and ("action" not in mapping or mapping.get("action") != "generate_text_answer"):
                    raise ValueError(f"Mapping must have either 'value' or 'action': {mapping}")
                    
            logger.info(f"Generated {len(mappings)} field mappings")
            return mappings
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse mapping JSON: {str(e)}")
            logger.debug(f"Raw response: {response_text}")
            raise ValueError(f"Model did not return valid JSON: {str(e)}")
        except Exception as e:
            logger.error(f"Error in field mapping: {str(e)}")
            raise
    
    async def generate_text_answer(self, prompt: str, context: Dict[str, Any]) -> str:
        """Generate a text answer for a free-form field.
        
        Args:
            prompt: The specific prompt for text generation
            context: Context information (profile data, job details, etc.)
            
        Returns:
            The generated text
        """
        logger.info(f"Generating text answer for prompt: {prompt[:50]}...")
        
        # Format the context for the model
        context_json = json.dumps(context, indent=2)
        
        # Create the system instruction
        system_instruction = """
        You are an AI assistant helping to write high-quality, personalized responses for job applications.
        Generate text that is professional, authentic, and tailored to the specific prompt and context provided.
        
        Your response should be in plain text format, ready to be entered directly into the form field.
        Do not include any markdown formatting, JSON structure, or programming elements.
        """
        
        # Create the user prompt
        user_prompt = f"""
        PROMPT: {prompt}
        
        CONTEXT:
        {context_json}
        
        Please generate a professional, personalized response based on the above information.
        """
        
        # Call the model
        response_text = await self._call_model(
            prompt=user_prompt,
            task_type=TaskType.TEXT_GENERATION,
            system_instruction=system_instruction,
            temperature=0.7
        )
        
        # Clean the response (remove any potential JSON/code artifacts)
        cleaned_text = response_text.strip()
        
        logger.info(f"Generated text answer ({len(cleaned_text)} chars)")
        return cleaned_text 