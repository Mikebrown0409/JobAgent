import logging
import json
import os
from typing import Dict, List, Any, Tuple, Optional, Union
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, Locator, Error as PlaywrightError
import google.generativeai as genai
import re # Import re for escaping
import random

from .base_strategy import BaseApplicationStrategy
from probe_page_structure import probe_page_for_llm
import action_taker
from adaptive_mapper import AdaptiveFieldMapper
from action_taker import add_random_delay

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.warning("GEMINI_API_KEY environment variable not set. AI features will fail.")
    # Set a dummy key to avoid crashes if it's used later inadvertently
    try:
        genai.configure(api_key="DUMMY_KEY_PLACEHOLDER")
    except Exception:
        pass # Avoid crashing if configure fails without key
else:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        logging.error(f"Error configuring Gemini API: {e}")
        GEMINI_API_KEY = None # Ensure it's None if config fails

class AdaptiveStrategy(BaseApplicationStrategy):
    """An adaptive strategy that uses AI and structural recognition to handle any job application form.
    
    This strategy:
    1. Probes the page to extract rich structural information about all interactive elements
    2. Uses AI (Gemini) to identify fields based on the probe data (platform-agnostic)
    3. Maps profile data to the appropriate form fields
    4. Generates custom interaction code using AI (Gemini) for each field based on its structure
    5. Attempts standard fallback actions if AI interaction fails.
    """
    
    def __init__(self):
        """Initialize the adaptive strategy."""
        # Instantiate the mapper; it handles profile loading/enhancement internally
        self.mapper = AdaptiveFieldMapper()

    def _call_gemini_for_fields(self, page_structure_json: str) -> dict:
        """
        Calls the Gemini API to identify field selectors based on page structure (Platform-Agnostic).
        """
        if not GEMINI_API_KEY:
            logging.error("Cannot call Gemini for field ID: API key not configured.")
            return {}

        logging.info("--- Calling Gemini API for Adaptive Field Identification --- ")
        model = genai.GenerativeModel('gemini-1.5-flash')

        # Define the STANDARD fields we want the AI to find (general list)
        standard_fields = [
            "full_name", "first_name", "last_name", "email", "phone", "location", 
            "linkedin_url", "github_url", "portfolio_url", "other_url", "website",
            "resume_upload", "cover_letter_upload", 
            "work_authorization_us", "require_sponsorship", "salary_expectation",
            "gender", "race", "ethnicity", "veteran_status", "disability_status",
            "notice_period", "how_did_you_hear", "why_company", "why_position",
            "submit_button"
        ]

        prompt = f"""
Analyze the following JSON representation of interactive elements found on a job application page. 
Do NOT assume a specific platform (like Greenhouse or Lever). Identify the most likely CSS selector for each of the requested standard fields based ONLY on the provided data (labels, attributes, text context, etc.).

Requested standard fields: {json.dumps(standard_fields)}

Page Elements JSON:
```json
{page_structure_json}
```

Respond ONLY with a valid JSON object mapping the standard field names (from the requested list) to their corresponding best-guess CSS selector string found in the input JSON. 
Use the 'selector' value from the input JSON elements for the mapping.
Map profile keys to the specific INPUT, SELECT, or TEXTAREA selector, NOT the surrounding div or label.
If a standard field corresponds to multiple elements (e.g., radio buttons for 'gender', checkboxes for 'race'), return the selector for the *most relevant containing element* or the first option's selector if that's not possible.
If a standard field cannot be confidently matched to any element in the provided JSON, map it to `null` or omit it from the response JSON.
**Important:** CSS IDs starting with a number are invalid unless escaped (e.g., `#\31 23id`). Prefer selectors that do not rely on potentially invalid numeric IDs if alternatives exist.

Example valid response format:
{{ "full_name": "#full_name_field", "email": "input[name='email']", "gender": "select[name='gender']", "submit_button": "button[type='submit']", "location": null }}

JSON Response:
"""

        try:
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            logging.debug(f"Raw Gemini Field ID Response:\n{response_text}")

            # Clean the response
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            identified_selectors = json.loads(response_text)
            logging.info(f"--- Gemini Field ID Response (Parsed) --- :\n{json.dumps(identified_selectors, indent=2)}")
            return identified_selectors

        except json.JSONDecodeError as json_err:
            logging.error(f"Gemini Field ID Response - JSON Decode Error: {json_err}")
            logging.error(f"Invalid JSON received: {response_text}")
            return {}
        except Exception as e:
            logging.error(f"Error calling Gemini Field ID API: {e}")
            if 'response_text' in locals(): logging.error(f"Gemini raw text: {response_text}")
            return {}

    def _get_ai_interaction_snippet(self, element_context: dict, desired_value: str | list) -> str | None:
        """Calls Gemini with element context and desired value to get an interaction snippet."""
        if not GEMINI_API_KEY:
            logging.error("Cannot call Gemini for interaction: API key not configured.")
            return None

        logging.info(f"--- Calling Gemini API for interaction snippet --- Selector: {element_context.get('selector')}, Value: {desired_value}")
        model = genai.GenerativeModel('gemini-1.5-flash')

        formatted_value = json.dumps(desired_value)
        selector = element_context.get('selector', '[unknown-selector]') # Get selector for prompt

        prompt = f"""
You are an expert Playwright automation assistant specializing in filling web forms.
Your task is to generate a Python code snippet using ONLY the `page` object provided to interact with a specific web element to set its value.

**Goal:** Set the element described below to match the desired value: {formatted_value}

**Element Context (JSON):**
```json
{json.dumps(element_context, indent=2)}
```

**Instructions:**
1. Analyze the context JSON ('tag', 'type_guess', 'role', 'label', 'selector', 'options').
2. Determine the correct Playwright action based on the element type and goal:
    - **Checkboxes (`input[type=checkbox]`):** Use `page.locator(...).check()`. Find the checkbox whose label or value closely matches {formatted_value}. If {formatted_value} is a list, check all matching.
    - **Radio Buttons (`input[type=radio]`):** Use `page.locator(...).check()`. Identify the correct radio button within the group ({selector}) whose value or associated label text most closely matches {formatted_value}. If the 'options' list is present in the context, use the 'value' or 'text' from the options to help construct the specific locator for the target radio button. For example: `page.locator('input[name="race"][value="White"]').check()` or `page.locator('label:has-text("Asian")').locator('input[type=radio]').check()`.
    - **Select Dropdowns (`select`):** Use intelligent option discovery and matching:
      ```python
      options = page.evaluate('''(selector) => {{
          const select = document.querySelector(selector);
          if (!select) return [];
          return Array.from(select.options).map(o => ({{text: o.text.trim(), value: o.value, index: o.index}}));
      }}''', '{selector}')
      logging.info(f"Available options for {selector}: {{options}}")
      desired_value = {formatted_value}
      desired_lower = desired_value.lower() if isinstance(desired_value, str) else ""
      best_match, best_score, fallback_match = None, 0, None
      yes_patterns = ["yes", "i am", "i do", "i have", "identify", "protected veteran", "disability"]
      no_patterns = ["no", "i do not", "don't", "i am not", "not a protected", "no disability"]
      decline_patterns = ["decline", "don't wish", "prefer not", "not to answer", "choose not"]
      for option in options:
          option_text = option['text'].lower()
          if desired_lower == option_text or desired_lower in option_text:
              best_match, best_score = option, 100; break
      if not best_match:
          if any(p in desired_lower for p in yes_patterns):
              for o in options: 
                  score = sum(p in o['text'].lower() for p in yes_patterns)
                  if score > best_score: best_match, best_score = o, score
          elif any(p in desired_lower for p in no_patterns):
              for o in options: 
                  score = sum(p in o['text'].lower() for p in no_patterns)
                  if score > best_score: best_match, best_score = o, score
          for o in options: 
              if any(p in o['text'].lower() for p in decline_patterns): fallback_match = o; break
      if best_match:
          logging.info(f"Selecting best match: {{best_match}}")
          if best_match['value']: page.select_option('{selector}', value=best_match['value'])
          else: page.select_option('{selector}', index=best_match['index'])
      elif fallback_match:
          logging.info(f"Using fallback 'decline': {{fallback_match}}")
          if fallback_match['value']: page.select_option('{selector}', value=fallback_match['value'])
          else: page.select_option('{selector}', index=fallback_match['index'])
      else:
          logging.warning(f"No matching option for {formatted_value}. Trying direct select.")
          try: page.select_option('{selector}', label={formatted_value})
          except Exception as e: logging.error(f"Direct select failed: {{e}}")
      ```
    - **Text/Other Inputs (`input`, `textarea`):** Use `page.locator(...).fill(...)`.
    - **Buttons/Links:** Use `page.locator(...).click()`.
3. Use the most specific selector available ({selector}).
4. **Important:**
    - Use variable `page`. No `import`, `async`, `await`, functions, classes, comments.
    - Snippet must perform at least one `page.` action.
    - Add `add_random_delay(0.1, 0.3)` between multiple actions.
5. For EEO dropdowns, the intelligent matching code provided handles common patterns and fallbacks.

**Example Snippets:**
- Checkbox: `page.locator('input[value="Yes"]').check()`
- Fill text: `page.locator('#first_name').fill('John')`
- Complex dropdown handled by the provided Python block.

**Respond ONLY with the raw Python code snippet.**

**Python Code Snippet:**
"""

        try:
            response = model.generate_content(prompt)
            snippet = response.text.strip()
            
            # Clean snippet
            if snippet.startswith('```python'): snippet = snippet[9:]
            elif snippet.startswith('```'): snippet = snippet[3:]
            if snippet.endswith('```'): snippet = snippet[:-3]
            snippet = snippet.strip()

            logging.info(f"--- Gemini Interaction Snippet Received ---\n{snippet}")
            if not snippet or "page." not in snippet:
                 logging.error(f"Invalid interaction snippet: {snippet}")
                 return None
            
            return snippet
        except Exception as e:
            logging.error(f"Error calling Gemini Interaction API: {e}")
            if 'response' in locals(): logging.error(f"Gemini raw text: {response.text}")
            return None

    def find_fields(self, page: Page, processed_selectors: set = None) -> tuple[list[dict], dict]:
        """Find fields using AI, validate/correct selectors, and exclude already processed ones."""
        logging.info("Using adaptive field finding with structural and contextual analysis...")
        validated_fields = []
        probe_elements_map = {}
        if processed_selectors is None: # Initialize if first pass
            processed_selectors = set()
        
        try:
            # Probe the page structure
            logging.info(f"Probing current page structure for adaptive analysis: {page.url}")
            page_structure_json = probe_page_for_llm(page)
            
            if not page_structure_json or page_structure_json.strip() in ["[]", "{}"]:
                logging.error("Probe returned empty structure. Cannot proceed.")
                return [], {}
            
            try:
                probe_data = json.loads(page_structure_json)
                if isinstance(probe_data, dict) and "error" in probe_data:
                     logging.error(f"Probe failed: {probe_data['error']}")
                     return [], {} 
                if not isinstance(probe_data, list) or not probe_data:
                    logging.error(f"Probe returned invalid/empty data: {type(probe_data)}")
                    return [], {}
                # Build context map from probe data
                probe_elements_map = {item['selector']: item for item in probe_data if item.get('selector')}
            except json.JSONDecodeError:
                logging.error("Failed to decode JSON from probe.")
                return [], {}

            # Call Gemini for field identification
            llm_identified_selectors = self._call_gemini_for_fields(page_structure_json)

            if not llm_identified_selectors:
                logging.warning("Gemini field identification failed or returned empty.")
                return [], probe_elements_map

            # Validate LLM selectors, correct simple issues, and format output
            logging.info("Validating selectors returned by Gemini...")
            for profile_key, selector in llm_identified_selectors.items():
                if not selector: 
                    logging.debug(f"Gemini returned null for '{profile_key}'. Skipping.")
                    continue 
                
                # Skip if selector already processed in a previous pass
                if selector in processed_selectors:
                    logging.debug(f"Skipping selector '{selector}' for '{profile_key}' as it was already processed.")
                    continue
                
                original_selector = selector
                is_valid = False
                corrected_selector = None

                # Attempt 1: Validate original selector
                try:
                    element_count = page.locator(selector).count()
                    is_valid = True
                except Exception as e:
                    logging.debug(f"Initial validation failed for selector '{selector}' for '{profile_key}': {e}")
                    # Check for specific error: invalid numeric ID
                    if selector.startswith('#') and selector[1].isdigit():
                        try:
                            # Attempt to escape the numeric ID
                            escaped_id = '#' + '\\3' + selector[1] + ' ' + selector[2:]
                            logging.warning(f"Attempting to correct numeric ID selector for {profile_key}: '{selector}' -> '{escaped_id}'")
                            element_count = page.locator(escaped_id).count()
                            logging.info(f"Successfully validated corrected selector '{escaped_id}' for {profile_key}.")
                            selector = escaped_id # Use the corrected selector
                            corrected_selector = selector
                            is_valid = True
                        except Exception as escape_err:
                            logging.error(f"Failed to validate corrected selector '{escaped_id}' for {profile_key}: {escape_err}")
                    # else: Keep is_valid = False if it's another type of error
                
                # If valid (original or corrected), add to list
                if is_valid:
                    if element_count > 0:
                        if element_count > 1:
                             logging.warning(f"Selector '{selector}' for '{profile_key}' matched {element_count}. Using first.")
                        
                        log_selector = corrected_selector or original_selector
                        logging.info(f"Validated: '{log_selector}' for '{profile_key}'.")
                        
                        probe_info = probe_elements_map.get(original_selector, probe_elements_map.get(corrected_selector, {}))
                        label = probe_info.get('label', 'Unknown')
                        field_type = self._infer_field_type(profile_key, probe_info)
                        validated_fields.append({
                            "key": profile_key,
                            "selector": selector, # Use potentially corrected selector
                            "label": label,
                            "type": field_type
                        })
                    else:
                        logging.warning(f"Selector '{selector}' for '{profile_key}' validated but NOT FOUND on page (count=0). Skipping field.")
                else:
                     # Log final failure if neither original nor corrected selector worked
                     logging.error(f"Failed to validate selector '{original_selector}' for '{profile_key}' after potential correction. Skipping field.")
            
            logging.info(f"Adaptive field finding complete for this pass. Validated {len(validated_fields)} new fields.")
            return validated_fields, probe_elements_map
            
        except Exception as e:
            logging.exception(f"Error during adaptive field finding: {e}")
            return [], {} # Return empty on major error
    
    def handle_field(self, page: Page, profile_key: str, selector: str, value: str | list, probe_elements_map: dict, job_details: Optional[dict] = None) -> bool:
        """Handles fields adaptively, prioritizing file uploads, then AI interaction, with improved fallbacks.
           Now passes question text and job details to the mapper for potential AI answer generation.
        """
        logging.debug(f"Handling Adaptive field: key={profile_key}, selector={selector}")
        # Ensure job_details is a dict even if None is passed
        if job_details is None:
            job_details = {}
            
        handled_by_strategy = True
        action_success = False
        field_context = probe_elements_map.get(selector)
        file_upload_keys = ["resume_upload", "cover_letter_upload"]

        if not field_context:
            logging.warning(f"Context not found for selector '{selector}'. Deferring to main_v0 default.")
            return False 

        question_text = field_context.get('label')
        if not question_text:
            logging.warning(f"Could not extract question text (label) for key '{profile_key}' from context. AI answer generation might be limited.")
            question_text = profile_key.replace('_', ' ').capitalize()

        # --- Pass question_text and job_details to the value retrieval --- 
        value_to_fill = self.mapper.get_value_for_key(
            profile_key,
            question_text=question_text,
            job_details=job_details # Pass job details here
        )

        if value_to_fill is None or (isinstance(value_to_fill, str) and value_to_fill.strip() == ""):
            logging.warning(f"Missing or empty value retrieved/generated for {profile_key} (Question: '{question_text}'). Field will be left blank.")
            return True
            
        # --- 1. Explicit Handling for File Uploads (Using value_to_fill) ---
        if profile_key in file_upload_keys:
            handled_by_strategy = True
            element_tag = field_context.get('tag')

            # ** Logic Adjustment: Handle textareas even if key suggests file **
            if element_tag == 'textarea':
                logging.warning(f"Treating file upload key '{profile_key}' as text paste for <textarea> ({selector}).")
                if isinstance(value_to_fill, str):
                    # Check if the value looks like a path that exists
                    if os.path.exists(value_to_fill):
                        try:
                            with open(value_to_fill, 'r', encoding='utf-8', errors='ignore') as f: file_content = f.read()
                            logging.info(f"Pasting content of file '{value_to_fill}' into textarea for {profile_key}")
                            action_success = action_taker.fill_field(page, selector, file_content)
        except Exception as e:
                            logging.error(f"Error reading file '{value_to_fill}' for pasting into textarea: {e}")
                            action_success = False
                    else:
                        # If it doesn't look like a path, paste the value directly (e.g., AI generated text or summary)
                        logging.info(f"Pasting direct text content into textarea for {profile_key}")
                        action_success = action_taker.fill_field(page, selector, value_to_fill)
                else:
                    logging.error(f"Cannot paste non-string value into textarea for {profile_key}: {type(value_to_fill)}")
                    action_success = False
            
            # ** Original logic for actual file inputs **
            elif element_tag == 'input':
                logging.info(f"Handling file upload for {profile_key} (tag: input) with selector {selector}")
                if isinstance(value_to_fill, str) and os.path.exists(value_to_fill):
                    action_success = action_taker.upload_file(page, selector, value_to_fill)
                elif isinstance(value_to_fill, str):
                    logging.error(f"File path '{value_to_fill}' for {profile_key} does not exist. Skipping upload.")
                    action_success = False
                else:
                    logging.error(f"Invalid file path value '{value_to_fill}' for {profile_key}. Skipping upload.")
                    action_success = False
            else:
                 logging.warning(f"Mapped file upload key '{profile_key}' to unexpected element tag: {element_tag}. Selector: {selector}. Skipping.")
                 action_success = True # Handled by skipping
            
            return action_success

        # --- 2. Explicit Handling for Standard Select Dropdowns (Using value_to_fill) ---
        field_type = self._infer_field_type(profile_key, field_context)
        if field_type == 'select':
            handled_by_strategy = True
            logging.info(f"Handling standard select dropdown for {profile_key} using action_taker.select_option")
            formatted_select_value = value_to_fill if isinstance(value_to_fill, str) else str(value_to_fill)
            action_success = action_taker.select_option(page, selector, formatted_select_value)
            if not action_success: 
                logging.error(f"action_taker.select_option failed for {profile_key} ({selector})")
            return action_success

        # --- 3. AI Interaction Logic for Checkbox/Radio (Using value_to_fill) ---
        ai_interaction_types = ['checkbox', 'radio']
        if field_type in ai_interaction_types:
            logging.info(f"Attempting AI-driven interaction for complex field: {profile_key} (type: {field_type}), Value: {value_to_fill}")
            interaction_code = self._get_ai_interaction_snippet(field_context, value_to_fill)
            
            if interaction_code:
                logging.info(f"Executing AI-generated interaction code for {profile_key}...")
                try:
                    exec_globals = {"page": page, "logging": logging, "add_random_delay": add_random_delay}
                    exec(interaction_code, exec_globals)
                    action_success = True
                    logging.info(f"Successfully executed AI snippet for {profile_key}.")
                except Exception as exec_err:
                    logging.error(f"Error executing AI interaction code for {profile_key}: {exec_err}", exc_info=False)
                    logging.error(f"--- Failed AI Snippet Start ---\n{interaction_code}\n--- Failed AI Snippet End ---")
                    action_success = False
                    
                    # Fallback Logic
                    logging.warning(f"AI interaction failed for {profile_key}. Attempting standard fallback.")
                    if field_type == 'checkbox' or field_type == 'radio':
                        logging.warning(f"No simple fallback for failed AI on {field_type} '{profile_key}'. Field may be incorrect.")
                        action_success = False
                    else:
                         logging.warning(f"Unknown field type '{field_type}' for AI fallback logic for {profile_key}. Attempting fill_field.")
                         if isinstance(value_to_fill, str): 
                              action_success = action_taker.fill_field(page, selector, value_to_fill)
                         else:
                              action_success = False
                         if action_success: logging.info(f"Recovered {profile_key} using fill_field fallback.")
                         else: logging.error(f"fill_field fallback failed for {profile_key}.")

            else:
                logging.error(f"Failed to get AI interaction snippet for {profile_key}. Cannot proceed with this field via AI.")
                action_success = False
                if field_type == 'checkbox' or field_type == 'radio':
                     logging.warning(f"No simple fallback for {field_type} '{profile_key}' after failed AI snippet generation.")
                     action_success = False

            return action_success

        # --- 4. Default Handling (Simple Fields like text, textarea, etc.) (Using value_to_fill) ---
        # Includes fields where AI *generated* the answer (e.g., open-ended questions)
        logging.debug(f"Using standard action_taker.fill_field for field '{profile_key}' (type: {field_type}).")
        if isinstance(value_to_fill, str):
             action_success = action_taker.fill_field(page, selector, value_to_fill)
        elif isinstance(value_to_fill, dict) and profile_key == 'location': # Handle location dict specifically
             loc_str = ", ".join(filter(None, [value_to_fill.get('city'), value_to_fill.get('region')]))
             if loc_str:
                 action_success = action_taker.fill_field(page, selector, loc_str)
             else:
                 logging.warning(f"Could not format location value for {profile_key}: {value_to_fill}")
                 action_success = False
        else:
             logging.warning(f"Cannot fill field {profile_key} with non-string value: {value_to_fill} (type: {type(value_to_fill)}). Skipping.")
             action_success = False

        return action_success
    
    def _infer_field_type(self, profile_key: str, element_context: dict) -> str:
        """Infer the field type from the element context and profile key."""
        # Reuse the robust inference logic (same as Lever/Greenhouse)
        tag = element_context.get('tag', '')
        type_guess = element_context.get('type_guess', '')
        role = element_context.get('role', '')
        if profile_key == 'resume_upload': return 'file'
        if profile_key == 'cover_letter_upload': return 'file'
        if profile_key == 'submit_button': return 'button'
        if tag == 'select': return 'select'
        if tag == 'textarea': return 'textarea' 
        if tag == 'input':
            if type_guess in ['email', 'tel', 'number', 'url', 'radio', 'checkbox', 'file']:
                 # Double check file type against key
                 if type_guess == 'file' and profile_key not in ['resume_upload', 'cover_letter_upload']:
                      logging.warning(f"Input type='file' for unexpected key '{profile_key}'. Treating as text.")
                      return 'text'
                 return type_guess
            return 'text' 
        if role == 'combobox' or role == 'listbox': return 'select' 
        if role == 'radiogroup': return 'radio'
        if role == 'checkbox': return 'checkbox' # Added role=checkbox
        if role == 'button': return 'button'
        return 'text'

    def get_submit_selectors(self) -> list[str]:
        """Returns common submit button texts/selectors for Greenhouse."""
        return [
            "button:has-text('Submit Application')",
            'button[data-qa="submit_button"]', # Common QA attribute
            "button[type='submit']",
            "Submit application", # Text fallback
            "Submit" # Generic fallback
        ]

    def perform_pre_upload_steps(self, page: Page):
        # Greenhouse typically doesn't require pre-upload steps for standard resume/CL inputs
        pass

    def perform_pre_submit_steps(self, page: Page):
        # Greenhouse might have consent checkboxes etc.
        # Example: Check for a common consent checkbox pattern
        consent_selectors = [
            'input[type="checkbox"][name*="consent"]'
            # Add other potential selectors based on observation
        ]
        for selector in consent_selectors:
            try:
                checkbox = page.locator(selector).first
                if checkbox.count() > 0 and checkbox.is_visible() and not checkbox.is_checked():
                    logging.info(f"Found potential consent checkbox '{selector}'. Checking it.")
                    action_taker.check_checkbox(page, selector)
                    add_random_delay(0.2, 0.5)
            except PlaywrightError as e:
                 logging.debug(f"Could not check optional consent box {selector}: {e}")
            except Exception as e:
                logging.warning(f"Unexpected error checking consent box {selector}: {e}")
        pass

    def perform_initial_apply_click(self, page: Page):
        """Checks for and clicks common initial 'Apply' buttons before main form loads."""
        logging.info("Checking for initial 'Apply' button before main field finding...")
        # More generic selectors suitable for unknown platforms - removed unnecessary escapes
        initial_apply_selectors = [
            'button:has-text("Apply Now")',
            'button:has-text("Apply")',
            'a:has-text("Apply Now")',
            'a:has-text("Apply")',
            '[data-testid="apply-button"]' # Common test ID
        ]
        clicked = False
        for selector in initial_apply_selectors:
            try:
                button = page.locator(selector).first
                # Use a short timeout, as this button should be visible quickly if present
                if button.is_visible(timeout=1500):
                     logging.info(f"Found initial apply button/link with selector: {selector}. Clicking...")
                     if action_taker.click_button(page, selector):
                         # Wait a bit longer after clicking to allow form transition/load
                         reveal_wait = random.uniform(3.0, 5.0) 
                         logging.info(f"Waiting {reveal_wait:.2f}s for potential form reveal...")
                         page.wait_for_timeout(reveal_wait * 1000)
                         clicked = True
                         break # Clicked one, stop searching
                     else:
                         logging.warning(f"Click failed for initial apply selector: {selector}")
            except PlaywrightError as e:
                 logging.debug(f"Error checking initial apply selector {selector}: {e}") # Often times out harmlessly
            except Exception as e:
                logging.warning(f"Unexpected error checking initial apply selector {selector}: {e}")
        
        if not clicked:
            logging.info("No initial 'Apply' button found or clicked, proceeding...") 