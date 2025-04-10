"""Agent for adapting user profiles to job applications."""

import logging
import re
import json
import os
from typing import Dict, Any, Optional, List
from crewai import LLM

# Import ActionContext (assuming it's in action_executor.py)
try:
    # Adjust path as necessary based on project structure
    from enterprise_job_agent.core.action_executor import ActionContext, ActionExecutionError 
except ImportError:
     # Fallback if structure is different or during testing
     ActionContext = dict # Use dict as placeholder if import fails
     ActionExecutionError = Exception

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Profile Mapping Specialist.

YOUR TASK:
Map user profile data to job application form fields accurately and effectively.

YOUR EXPERTISE:
- Deep understanding of job application forms and fields
- Expert at matching profile data to form requirements
- Skilled at handling complex form structures
- Experience with various ATS systems
- Knowledge of industry-standard field mappings
- Crafting compelling open-ended responses that pass ATS and impress recruiters

APPROACH YOUR ANALYSIS:
1. Review form structure and requirements
2. Analyze user profile data
3. Create optimal field mappings
4. Handle special cases and transformations
5. Validate mappings meet requirements
6. Generate eloquent, persuasive responses for open-ended questions

FOCUS ON:
- Required vs optional fields
- Field type compatibility
- Data formatting requirements
- Special field handling (dropdowns, multi-select)
- Default values for unmapped fields
- Creating THOUGHTFUL, DETAILED responses for open-ended questions about motivation, experience, and qualifications

ALWAYS STRUCTURE RESPONSES AS JSON with the exact schema provided in the task."""

class ProfileAdapterAgent:
    """Agent for adapting user profiles to job applications."""
    
    def __init__(self, llm: Any, verbose: bool = False):
        """
        Initialize a profile adapter agent.
        
        Args:
            llm: Language model to use
            verbose: Whether to enable verbose output
        """
        self.llm = llm
        self.verbose = verbose
        self.logger = logging.getLogger(__name__)
        self.user_profile = {}  # Initialize user_profile as empty dict
    
    def create_mapping_prompt(
        self,
        form_elements: List[Dict[str, Any]],
        user_profile: Dict[str, Any],
        job_description: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a prompt for mapping user profile to form fields based on live analysis data.
        
        Args:
            form_elements: List of elements extracted from live analysis
            user_profile: User profile data
            job_description: Optional job description data
            
        Returns:
            A prompt string for the LLM
        """
        # Extract file paths directly from profile within the prompt context if needed
        resume_path = user_profile.get('resume_path', user_profile.get('documents', {}).get('resume', '[RESUME PATH NOT FOUND IN PROFILE]'))
        cover_letter_path = user_profile.get('cover_letter_path', user_profile.get('documents', {}).get('cover_letter', '[COVER LETTER PATH NOT FOUND IN PROFILE]'))

        file_instructions = f"""
        SPECIAL FILE HANDLING:
        - For resume fields (type='file', label contains 'resume' or 'cv'), use this EXACT path: {resume_path}
        - For cover letter fields (type='file', label contains 'cover'), use this EXACT path: {cover_letter_path}
        - If the path is '[PATH NOT FOUND...]', leave the value empty or state path is missing.
        - DO NOT use placeholder values like 'path/to/...' unless the actual path is a placeholder.
        """
        
        job_desc_section = f"""
        JOB DESCRIPTION CONTEXT:
        ```
        {json.dumps(job_description, indent=2) if job_description else 'N/A'}
        ```
        """ 
        
        # Format form elements for the prompt (includes frame_id now)
        formatted_elements = json.dumps(form_elements, indent=2)
        
        open_ended_instructions = """
        OPEN-ENDED QUESTION HANDLING:
        
        First, analyze the question context and type:
        
        - SHORT-ANSWER QUESTIONS (yes/no, availability, relocation, etc.):
          * Answer directly and concisely (1 sentence)
          * Be honest based on the user profile data
          * For binary questions like "Can you commute?" provide a simple "Yes" or "No" with minimal context
          * For questions about availability or relocation, keep it brief but informative
        
        - STANDARD OPEN-ENDED QUESTIONS (experience, motivation, etc.):
          * Generate natural, conversational responses (2-4 sentences)
          * Match response length to question complexity
          * Ensure authenticity and relevance to the job/company
          * Include 1-2 specific details from the candidate's profile
        
        Key principles for ALL responses:
        - Natural: Write like a real human would - conversational, not overly formal
        - Authentic: Express genuine interest without excessive enthusiasm
        - Specific: Reference concrete details from profile when relevant
        - Tailored: Adapt response length to question type/complexity
        
        AVOID:
        - Verbose responses when a short answer would suffice
        - Generic statements that could apply to any company
        - Unnecessary details or irrelevant information
        - The "AI assistant voice" - maintain human job applicant voice
        
        These responses should sound exactly like a real human job applicant - natural, focused, and appropriately concise.
        """
        
        return f"""
        TASK: Determine the sequence of actions needed to fill this job application form based on the analyzed elements (potentially across multiple frames) and the user profile.
        
        USER PROFILE:
        ```json
        {json.dumps(user_profile, indent=2)}
        ```
        
        ANALYZED FORM ELEMENTS (from live page analysis across frames):
        ```json
        {formatted_elements}
        ```
        {job_desc_section}
        
        ACTION GENERATION REQUIREMENTS:
        
        1. Iterate through the ANALYZED FORM ELEMENTS.
        2. For each element, decide if an action is needed (fill, select, click, etc.).
        3. If action is needed:
            - Map user profile data based on element attributes ('label', 'name_attr', etc.).
            - For 'select', find best match in 'options'.
            - For 'click', value is null.
            - For 'file', use exact paths from SPECIAL FILE HANDLING.
            - **Crucially, note the 'frame_id' provided for each element.**
        4. For OPEN-ENDED QUESTIONS (textarea elements with labels like "Why do you want to work here", etc.):
            - Follow the OPEN-ENDED QUESTION HANDLING guidelines carefully
            - Create natural, conversational responses that sound like a real job applicant
            - Keep responses concise (3-5 sentences for most questions)
        5. Populate the output JSON actions list.
        
        {file_instructions}
        
        {open_ended_instructions}
        
        OUTPUT FORMAT:
        Return your determined actions as this exact JSON structure. ONLY include elements that require an action.
        ```json
        {{
            "actions": [
                {{
                    "element_description": "Brief description (e.g., 'First Name Input')",
                    "selector": "<selector_from_analysis>",          // Use 'selector' from analysis
                    "field_type": "<field_type_from_analysis>",    // Use 'field_type' from analysis
                    "value": "<value_from_profile_or_null>",      // Mapped value or null
                    "fallback_text": "<fallback_text_if_click>",    // Use 'fallback_text' from analysis if click type
                    "frame_id": "<frame_id_from_analysis>",      // Include the 'frame_id' from the analysis data for this element
                    "reasoning": "Why this action/value was chosen/skipped"
                }}
                // ... more actions
            ],
            "strategic_approach": [
                "Strategic insight 1 about how to approach this application",
                "Strategic insight 2 about key strengths to emphasize"
            ]
        }}
        ```
        Ensure the 'selector', 'field_type', 'fallback_text', and **'frame_id'** fields in your output JSON use the corresponding values directly from the ANALYZED FORM ELEMENTS data provided above.
        **CRITICAL: You MUST use the exact 'selector' value from the ANALYZED FORM ELEMENTS data for each action. Do NOT generate generic selectors like 'input'. If you cannot determine the correct action or value for a specific analyzed element based on its selector, omit it from your output.**
        """
    
    async def adapt_profile(self, user_profile, form_elements, job_description=None):
        """
        Alias for map_profile_to_form.
        Accepts the new form_elements structure.
        
        Args:
            user_profile: User profile data
            form_elements: List of analyzed form elements from live analysis
            job_description: Optional job description data
            
        Returns:
            List of ActionContext objects or equivalent action plan.
        """
        return await self.map_profile_to_form(form_elements, user_profile, job_description)
    
    async def map_profile_to_form(self, form_elements: List[Dict[str, Any]], user_profile: Dict[str, Any], job_description=None) -> List[ActionContext]:
        """Generates an action plan (list of ActionContext) by mapping user profile to live form elements using LLM."""
        self.logger.info(f"Generating action plan based on {len(form_elements)} live form elements.")
        try:
            # Store user profile for later use in post-processing
            self.user_profile = user_profile
            
            # Create mapping prompt using the new form_elements structure
            mapping_prompt = self.create_mapping_prompt(form_elements, user_profile, job_description)
            
            # Use the call method for the latest CrewAI LLM interface
            # Format as a user message according to documentation
            response = self.llm.call(mapping_prompt)
            
            # Log the raw response for debugging
            self.logger.debug(f"Received raw action plan from LLM: {response}")
            
            # Try to extract JSON from response
            llm_actions_data = self._extract_json_from_response(response)
            
            # Log the extracted JSON data from LLM
            self.logger.debug(f"Extracted JSON data from LLM: {json.dumps(llm_actions_data, indent=2)}")
            
            # --- Log Inputs to _create_action_context_list --- 
            try:
                 # Log a summary of the form analysis result (form_elements)
                 if form_elements:
                      elements_summary = {}
                      for el in form_elements:
                           # Ensure el is a dictionary before accessing keys
                           if isinstance(el, dict):
                                fid = el.get('frame_id', 'unknown')
                                elements_summary[fid] = elements_summary.get(fid, 0) + 1
                           else:
                                self.logger.warning(f"Found non-dict item in form_elements: {type(el)}")
                      self.logger.debug(f"Form Elements Summary (Count per Frame): {elements_summary}")
                      # Avoid logging full elements by default - too verbose
                      # self.logger.debug(f"Full form_elements: {json.dumps(form_elements, indent=2)}") 
                 else:
                      self.logger.warning("Form elements list is empty or None when creating action context.")
                 
                 # Log the raw LLM action data (parsed JSON)
                 self.logger.debug(f"Parsed LLM actions data: {json.dumps(llm_actions_data, indent=2)}")
            except Exception as log_ex:
                 self.logger.error(f"Error logging inputs for action context creation: {log_ex}")
            # --- End Logging --- 

            # Post-process the extracted actions into ActionContext objects
            action_plan = await self._create_action_context_list(llm_actions_data, form_elements)
            
            self.logger.info(f"Successfully generated action plan with {len(action_plan)} actions.")
            return action_plan
            
        except Exception as e:
            self.logger.error(f"Error generating action plan: {str(e)}", exc_info=True)
            # Comment out the fallback mapping so we can see the real error
            # return self._create_basic_mapping(form_structure, user_profile)
            
            # Instead, raise the exception so we can see what's happening
            raise
    
    def _extract_json_from_response(self, response: str) -> Dict[str, Any]:
        """
        Extract JSON from the response text using regex.
        """
        try:
            # Use regex to extract JSON from the response
            # Make pattern non-greedy and handle potential markdown variations
            json_pattern = r'```(?:json)?\s*({.*?})\s*```' 
            json_match = re.search(json_pattern, response, re.DOTALL | re.IGNORECASE)
            
            if json_match:
                json_text = json_match.group(1)
                # Attempt to parse the JSON
                parsed_json = json.loads(json_text)
                self.logger.debug("Successfully extracted and parsed JSON from LLM response.")
                return parsed_json
            else:
                self.logger.error(f"Could not extract JSON block from LLM response. Response: {response[:500]}...")
                return {"actions": [], "error": "Failed to extract JSON block"}
        except json.JSONDecodeError as json_err:
            self.logger.error(f"Error decoding JSON from LLM response: {json_err}. Text: {json_text[:500]}...")
            return {"actions": [], "error": f"JSON Decode Error: {json_err}"}
        except Exception as e:
            self.logger.error(f"Unexpected error extracting JSON from response: {e}")
            return {"actions": [], "error": f"Unexpected error during JSON extraction: {e}"}
    
    def _create_basic_mapping(self, form_elements, user_profile):
        """Create a basic mapping for important fields as fallback."""
        self.logger.warning("_create_basic_mapping is deprecated and may not work with live analysis data.")
        field_mappings = []
        
        # Basic extraction for common fields if we failed to get mapping from LLM
        for element in form_elements:
            field_id = element.get("selector") or element.get("field_id_attr") # Use selector or fallback ID
            
            # Basic fallback logic might need refinement
            if field_id and element.get("is_required"): # Only map required fields in fallback
                 fallback_value = self._extract_fallback_value(element, user_profile)
                 if fallback_value:
                    field_mappings.append({
                        "field_id": field_id, # Store selector/ID used
                        "value": fallback_value
                    })
        
        return {"field_mappings": field_mappings}
    
    def _extract_fallback_value(self, element: Dict[str, Any], user_profile: Dict[str, Any]) -> str:
        """Extract a fallback value from the user profile based on element info."""
        # Basic heuristic matching - needs improvement
        label = element.get("label", "").lower()
        field_id = element.get("field_id_attr", "").lower()
        name = element.get("name_attr", "").lower()
        
        # Simple matching logic
        if "first" in field_id or "first" in label or "first" in name:
            return user_profile.get("personal", {}).get("first_name", "")
        elif "last" in field_id or "last" in label or "last" in name:
            return user_profile.get("personal", {}).get("last_name", "")
        elif "email" in field_id or "email" in label or "email" in name:
            return user_profile.get("personal", {}).get("email", "")
        elif "phone" in field_id or "phone" in label or "phone" in name:
            return user_profile.get("personal", {}).get("phone", "")
        elif "location" in field_id or "city" in label or "city" in name:
            return user_profile.get("personal", {}).get("city", "") + ", " + user_profile.get("personal", {}).get("state", "")
        elif "website" in field_id or "website" in label or "website" in name:
            return user_profile.get("personal", {}).get("website", "")
        elif "linkedin" in field_id or "linkedin" in label or "linkedin" in name:
            return user_profile.get("personal", {}).get("linkedin", "")
        else:
            return ""
    
    def enhance_application_strategy(
        self,
        strategy: Dict[str, Any],
        job_description: Dict[str, Any],
        user_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enhance application strategy with additional insights.
        
        Args:
            strategy: Base application strategy
            job_description: Job description data
            user_profile: User profile data
            
        Returns:
            Enhanced application strategy
        """
        logger.info("Enhancing application strategy")
        
        # For now, just add a simple insight
        enhanced = strategy.copy()
        enhanced["insights"] = [
            "Focus on highlighting media infrastructure experience",
            "Emphasize experience with FFmpeg, WebRTC, and streaming technologies"
        ]
        
        return enhanced 

    async def _create_action_context_list(self, llm_actions_data: Dict[str, Any], form_elements: List[Dict[str, Any]]) -> List[ActionContext]:
        """Creates a list of ActionContext objects from parsed LLM actions and form elements."""
        action_contexts = []
        if not form_elements or not llm_actions_data:
            self.logger.warning("Missing form elements or LLM actions data, cannot create action contexts.")
            return []

        # Create a lookup for form elements by selector for quick access
        form_elements_lookup = {}
        for el in form_elements:
            if isinstance(el, dict) and el.get('selector'):
                form_elements_lookup[el['selector']] = el
            else:
                self.logger.warning(f"Found non-dict item in form_elements: {type(el)}")

        # Parse the JSON string from LLM output
        parsed_llm_actions = None
        if isinstance(llm_actions_data, str): # Check if it's a string (might be pre-parsed dict)
            try:
                parsed_llm_actions_outer = json.loads(llm_actions_data)
                # The actual actions are usually nested under an 'actions' key
                if isinstance(parsed_llm_actions_outer, dict) and 'actions' in parsed_llm_actions_outer:
                    parsed_llm_actions = parsed_llm_actions_outer['actions']
                elif isinstance(parsed_llm_actions_outer, list): # Handle case where outer layer is the list
                    parsed_llm_actions = parsed_llm_actions_outer
                else:
                     raise ValueError("Parsed LLM data is not a dict with 'actions' or a list.")
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse LLM actions JSON string: {e}. Data: {llm_actions_data[:500]}...")
                return []
            except ValueError as e:
                 self.logger.error(f"Error processing LLM actions data structure: {e}")
                 return []
        elif isinstance(llm_actions_data, dict) and 'actions' in llm_actions_data: # Handle if already parsed dict
            parsed_llm_actions = llm_actions_data['actions']
        elif isinstance(llm_actions_data, list): # Handle if already a list (less common)
             parsed_llm_actions = llm_actions_data
        
        if not isinstance(parsed_llm_actions, list):
            self.logger.error(f"Could not extract a list of actions from LLM data. Data provided: {llm_actions_data}")
            return []

        log_prefix = "ACTION_CONTEXT_CREATE: "
        self.logger.debug(f"{log_prefix}Processing {len(parsed_llm_actions)} actions from LLM.")

        for index, action_data in enumerate(parsed_llm_actions):
            
            # Basic validation of action data structure
            if not isinstance(action_data, dict) or 'selector' not in action_data or 'value' not in action_data or 'field_type' not in action_data:
                self.logger.warning(f"{log_prefix}Skipping invalid action data at index {index} (missing keys): {action_data}")
                continue
            
            self.logger.debug(f"{log_prefix}Processing LLM Action {index+1}/{len(parsed_llm_actions)}: {action_data}")

            selector = action_data.get('selector')
            field_type = action_data.get('field_type').lower()  # Normalize field type
            field_value = action_data.get('value')
            
            # --- VALIDATE LLM-provided selector --- 
            if not selector or selector not in form_elements_lookup:
                self.logger.error(f"{log_prefix}Action {index+1}: LLM provided an invalid or missing selector ('{selector}') that doesn't match any analyzed element. Skipping this action. LLM Action Details: {action_data}")
                continue # Skip this action entirely
            # --- END VALIDATION ---

            # Ensure value is string or list, handle None/null explicitly
            if field_value is None:
                 # Decide how to handle None values - log a warning for now, might skip or use empty string
                 self.logger.warning(f"{log_prefix}Action for selector '{selector}' has a null value. Proceeding with None.")
                 # field_value = "" # Option to replace None with empty string
            elif not isinstance(field_value, (str, list)):
                 field_value = str(field_value) # Convert other types (like numbers) to string
                 
            field_name = action_data.get('field_name')
            
            # Retrieve the original element data using the selector
            element_data_for_context = form_elements_lookup.get(selector)
            
            # --- DETAILED LOGGING ADDED --- 
            if element_data_for_context:
                self.logger.debug(f"{log_prefix}Action {index+1}: Found matching original element data for selector '{selector}'. Frame ID: {element_data_for_context.get('frame_id')}")
                # Log a snippet of the data, avoid logging excessively large HTML snippets
                log_data_snippet = {k: v for k, v in element_data_for_context.items() if k != 'html_snippet'}
                self.logger.debug(f"{log_prefix}Action {index+1}: Matched Element Data Snippet: {log_data_snippet}")
            else:
                self.logger.warning(f"{log_prefix}Action {index+1}: Could not find matching form element for selector '{selector}' from LLM action. LLM Action Details: {action_data}")
                # Decide if we should skip this action or create a context with default frame_id='main'?
                # For now, let's skip if we can't find the element, as frame_id is crucial.
                continue # Skip this action if original element data isn't found
            # --- END DETAILED LOGGING --- 

            frame_id = element_data_for_context.get('frame_id', 'main') # Default to main if somehow missing
            
            # Add context clues based on field type (optional but helpful)
            options_dict = {
                "description": action_data.get("description", element_data_for_context.get("label") or selector), 
                # --- IMPORTANT: Include the full element_data here --- 
                "element_data": element_data_for_context
            }
            
            fallback_text = action_data.get("fallback_text") # Optional text for error recovery

            # Construct ActionContext
            try:
                action_context = ActionContext(
                    field_id=selector,
                    field_type=field_type,
                    field_value=field_value,
                    frame_id=frame_id,
                    options=options_dict,
                    fallback_text=fallback_text,
                    field_name=field_name,
                    # profile_data could be added here if needed for specific handlers
                )
                self.logger.debug(f"{log_prefix}Action {index+1}: Created ActionContext object id={id(action_context)}: field_id='{action_context.field_id}', type='{action_context.field_type}', value='{str(action_context.field_value)[:50]}...', frame='{action_context.frame_id}'")
                action_contexts.append(action_context)
            except Exception as e:
                 self.logger.error(f"{log_prefix}Action {index+1}: Error creating ActionContext for selector '{selector}': {e}", exc_info=True)

        self.logger.info(f"{log_prefix}Created {len(action_contexts)} valid action contexts.")
        return action_contexts

    # --- Deprecated methods remain below --- 
    # ...

    # ... (rest of the original methods remain unchanged) ...

    # ... (rest of the original methods remain unchanged) ... 