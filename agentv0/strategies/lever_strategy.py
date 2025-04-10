import logging
import json
import os
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from .base_strategy import BaseApplicationStrategy
# Removed direct browser_controller import for find_fields, will use probe
from probe_page_structure import probe_page_for_llm # Import the LLM probe function
import action_taker # Use default actions as fallback
from action_taker import add_random_delay
import re

# --- Gemini API Integration ---
import google.generativeai as genai

# Configure Gemini API (Assuming API key is set as an environment variable)
try:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        logging.warning("GEMINI_API_KEY environment variable not set. AI field identification will fail.")
        genai.configure(api_key="DUMMY_KEY_PLACEHOLDER") # Avoid crash if key missing
    else:
        genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    logging.error(f"Error configuring Gemini API: {e}")
    # Consider how to handle this - maybe fall back to non-AI methods?

def call_gemini_for_fields(page_structure_json: str) -> dict:
    """
    Calls the Gemini API to identify field selectors based on page structure.
    Takes the JSON page structure and returns a dict mapping standard profile keys 
    to potential CSS selectors identified by the AI.
    """
    if not GEMINI_API_KEY: # Don't attempt call if key wasn't found
        logging.error("Cannot call Gemini: API key not configured.")
        return {}

    logging.info("--- Calling Gemini API for field identification --- ")
    model = genai.GenerativeModel('gemini-1.5-flash')

    # Define the STANDARD fields we want the AI to find
    # Expand this list significantly!
    standard_fields = [
        # Core Info
        "full_name", "email", "phone", "location", 
        # Links
        "linkedin_url", "github_url", "portfolio_url", "other_url",
        # Uploads
        "resume_upload", "cover_letter_upload", 
        # Authorization / Logistics
        "work_authorization_us", "require_sponsorship", "salary_expectation",
        # EEO Section
        "gender", "race", "veteran_status", "disability_status",
        # Common Custom Questions (Keywords - AI might find variations)
        "notice_period", "how_did_you_hear",
        # The critical final step
        "submit_button"
    ]

    prompt = f"""
Analyze the following JSON representation of interactive elements found on a job application page. 
Identify the most likely CSS selector for each of the requested standard fields based ONLY on the provided data (labels, attributes, text context, etc.).

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

Example valid response format:
{{ "full_name": "#first_name_field", "email": "input[name='email']", "gender": "select[name='gender']", "race": "#race-checkbox-group", "submit_button": "button[type='submit']", "location": null }}

JSON Response:
"""

    try:
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        logging.debug(f"Raw Gemini Response:\n{response_text}")

        # Clean the response: remove potential markdown code block fences
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        # Parse the JSON response from Gemini
        identified_selectors = json.loads(response_text)
        logging.info(f"--- Gemini API Response (Parsed) --- :\n{json.dumps(identified_selectors, indent=2)}")
        return identified_selectors

    except json.JSONDecodeError as json_err:
        logging.error(f"Gemini API Response - JSON Decode Error: {json_err}")
        logging.error(f"Invalid JSON received: {response_text}")
        return {} # Return empty on decode failure
    except Exception as e:
        logging.error(f"Error calling Gemini API or processing response: {e}")
        # Log the full response text if available and error occurred during parsing/processing
        if 'response_text' in locals():
            logging.error(f"Gemini raw text at time of error: {response_text}")
        return {}

# ------------------------------------------

class LeverStrategy(BaseApplicationStrategy):
    """Strategy implementation for Lever job application forms using AI interaction."""

    def find_fields(self, page: Page) -> tuple[list[dict], dict]:
        """Uses AI-driven analysis via page probe and LLM call to identify fields. 
           Returns a tuple: (list_of_validated_fields, probe_context_map)."""
        logging.info("Using AI-driven field finding for Lever strategy...")
        validated_fields = [] # Initialize here
        probe_elements_map = {} # Initialize here
        
        try:
            logging.info(f"Probing current page structure for LLM analysis: {page.url}")
            page_structure_json = probe_page_for_llm(page) 

            if not page_structure_json or page_structure_json.strip() in ["[]", "{}"]:
                logging.error("Probe returned empty or invalid structure. Cannot proceed.")
                return [], {} # Return empty tuple
                
            try:
                probe_data = json.loads(page_structure_json)
                if isinstance(probe_data, dict) and "error" in probe_data:
                     logging.error(f"Probe failed with error: {probe_data['error']}")
                     return [], {} 
                if not isinstance(probe_data, list):
                    logging.error(f"Probe returned unexpected data type: {type(probe_data)}")
                    return [], {}
                if not probe_data: 
                    logging.warning("Probe returned an empty list of elements. Cannot proceed.")
                    return [], {}

            except json.JSONDecodeError:
                logging.error("Failed to decode JSON from probe output.")
                return [], {}

            # Create the context map BEFORE calling Gemini
            # Use stable_selector from probe data as the key
            probe_elements_map = {item['selector']: item for item in probe_data if item.get('selector')}
            if not probe_elements_map:
                logging.warning("Probe data did not yield any elements with stable selectors.")
                # Continue, but mapping might be difficult if AI relies on selectors.

            logging.info("Requesting field identification from Gemini...")
            llm_identified_selectors = call_gemini_for_fields(page_structure_json)

            if not llm_identified_selectors:
                logging.warning("Gemini returned no selectors or call failed.")
                return [], probe_elements_map # Return empty fields but the context map

            # --- Validate LLM selectors and format output ---
            logging.info("Validating selectors returned by Gemini...")
            for profile_key, selector in llm_identified_selectors.items():
                if not selector: 
                    logging.info(f"Gemini returned null/empty selector for key '{profile_key}'. Skipping.")
                    continue 

                try:
                    element_count = page.locator(selector).count()
                    if element_count > 0:
                        if element_count > 1:
                             logging.warning(f"Selector '{selector}' for key '{profile_key}' matched {element_count} elements. Using the first one.")
                        
                        logging.info(f"Validated selector '{selector}' for key '{profile_key}'.")
                        
                        # Retrieve full context from the map we created earlier
                        probe_info = probe_elements_map.get(selector, {}) 
                        if not probe_info:
                             logging.warning(f"Selector '{selector}' from Gemini not found in probe_elements_map. Cannot get label/type info.")
                             # Decide how to handle - skip? add with defaults?
                             # Add with defaults for now, but this is suboptimal.
                             label = "Unknown (Selector not in probe map)"
                             field_type = "text" # Default guess
                        else:
                            label = probe_info.get('label', 'Label not in probe')
                            field_type = self._infer_field_type(profile_key, probe_info)

                        validated_fields.append({
                            "key": profile_key,
                            "selector": selector,
                            "label": label, 
                            "type": field_type
                        })
                    else:
                        logging.warning(f"Selector '{selector}' for key '{profile_key}' returned by Gemini was NOT found on the page.")
                except PlaywrightTimeoutError:
                     logging.warning(f"Timeout validating selector '{selector}' for key '{profile_key}'. Skipping.")
                except Exception as e:
                    if "SyntaxError" in str(e):
                         logging.error(f"Invalid CSS selector syntax '{selector}' returned by Gemini for key '{profile_key}': {e}")
                    else:
                         logging.error(f"Error validating selector '{selector}' for key '{profile_key}': {e}")
            
            logging.info(f"AI-driven field finding complete. Validated {len(validated_fields)} fields.")
            return validated_fields, probe_elements_map # Return both

        except Exception as e:
            logging.exception(f"Error during AI-driven field finding: {e}")
            return [], {} # Return empty tuple on failure

    def _infer_field_type(self, profile_key: str, probe_info: dict) -> str:
        """Infers the field type needed by action_taker based on profile key and probe data."""
        # Priority 1: Specific profile keys
        if profile_key == 'resume_upload': return 'file'
        if profile_key == 'cover_letter_upload': return 'file' # Added cover letter
        if profile_key == 'submit_button': return 'button'

        # Priority 2: HTML tag from probe
        tag = probe_info.get('tag', '')
        if tag == 'select': return 'select'
        if tag == 'textarea': return 'textarea' 
        
        # Priority 3: Input type attribute from probe (using type_guess)
        type_guess = probe_info.get('type_guess', '')
        if tag == 'input':
            # Explicit input types
            if type_guess == 'email': return 'email'
            if type_guess == 'tel': return 'tel'
            if type_guess == 'number': return 'number'
            if type_guess == 'url': return 'url'
            if type_guess == 'radio': return 'radio' # Handle radio buttons
            if type_guess == 'checkbox': return 'checkbox' # Handle checkboxes
            if type_guess == 'file': 
                # Double check key if type is file
                if profile_key == 'resume_upload' or profile_key == 'cover_letter_upload':
                    return 'file'
                else:
                    logging.warning(f"Input type='file' found for unexpected key '{profile_key}'. Treating as text for now.")
                    return 'text' # Fallback if type=file but key doesn't match uploads
            
            # Most others map to 'text' for filling (text, password, search, date etc.)
            return 'text' 
            
        # Priority 4: Role attribute
        role = probe_info.get('role', '')
        if role == 'combobox' or role == 'listbox': return 'select' 
        if role == 'radiogroup': return 'radio' # Group of radio buttons
        
        # Default fallback
        return 'text'

    def _get_ai_interaction_snippet(self, element_context: dict, desired_value: str | list) -> str | None:
        """Calls Gemini with element context and desired value to get an interaction snippet."""
        if not GEMINI_API_KEY:
            logging.error("Cannot call Gemini for interaction: API key not configured.")
            return None

        logging.info(f"--- Calling Gemini API for interaction snippet --- Selector: {element_context.get('selector')}, Desired Value: {desired_value}")
        model = genai.GenerativeModel('gemini-1.5-flash') 

        # Format desired value for prompt (handle lists for checkboxes)
        formatted_value = json.dumps(desired_value)
        element_type = element_context.get('type_guess', element_context.get('tag', 'unknown')) # Get type hint

        prompt = f"""
You are an expert Playwright automation assistant specializing in filling web forms.
Your task is to generate a Python code snippet using ONLY the `page` object provided to interact with a specific web element to set its value.

**Goal:** Set the element described below to match the desired value: {formatted_value}

**Element Context (JSON):**
```json
{json.dumps(element_context, indent=2)}
```

**Instructions:**
1. Analyze the context JSON ('tag', 'type_guess', 'role', 'label', 'selector', 'group_options', etc.).
2. Determine the correct Playwright action based on the element type and goal:
    - **Checkboxes (`input[type=checkbox]`):** Use `page.locator(...).check()`. If {formatted_value} is a list, generate a `check()` call for *each* item in the list whose value/label matches.
    - **Radio Buttons (`input[type=radio]`):** Use `page.locator(...).check()`. Generate code to check the *single* radio button whose value or label matches {formatted_value}.
    - **Select Dropdowns (`select`):** Use `page.select_option(selector, label=...)` or `page.select_option(selector, value=...)`. Prefer matching by `label` if {formatted_value} looks like visible text, otherwise match by `value`. Use the main element's `selector` from the context.
    - **Text/Other Inputs (`input`, `textarea`):** Use `page.locator(...).fill(...)` or `page.locator(...).press_sequentially(...)`.
    - **Buttons/Links:** Use `page.locator(...).click()`.
3. Use the most specific selector available:
    - For radio/checkbox groups, use the selectors provided within `group_options` if available.
    - If `group_options` are missing, construct a precise selector using attributes (`value`, `id`, `name`) or text content (e.g., find a label containing {formatted_value} and check the associated input). Use the main `selector` from the context as a base if needed.
4. **Crucially:**
    - The snippet MUST use the variable `page`.
    - The snippet MUST NOT include `import` statements.
    - The snippet MUST NOT include `async` or `await`.
    - The snippet MUST NOT define functions or classes.
    - The snippet MUST NOT create new browser contexts or pages.
    - The snippet MUST NOT contain comments or explanations.
    - The snippet MUST contain at least one `page.` action.
5. If the element is complex (like a custom dropdown requiring clicks), generate the sequence of `page.locator(...).click()` actions needed.
6. Add short `add_random_delay(0.1, 0.3)` calls between actions if multiple steps are needed (e.g., click dropdown, then click option).

**Example Snippets:**
- Checkbox: `page.locator('input[name="option1"][value="Yes"]').check()`
- Select by label: `page.select_option('select#gender', label='Female')`
- Select by value: `page.select_option('select#country', value='US')`
- Radio group: `page.locator('label:has-text("Maybe")').locator('input[type="radio"]').check()`
- Fill text: `page.locator('#first_name').fill('John')`

**Respond ONLY with the raw Python code snippet.**

**Python Code Snippet:**
"""

        try:
            response = model.generate_content(prompt)
            snippet = response.text.strip()
            
            # Basic cleaning of potential markdown fences
            if snippet.startswith('```python'):
                snippet = snippet[9:]
            elif snippet.startswith('```'):
                 snippet = snippet[3:]
            if snippet.endswith('```'):
                snippet = snippet[:-3]
            snippet = snippet.strip()

            logging.info(f"--- Gemini Interaction Snippet Received ---\n{snippet}")
            # Basic validation: check if it contains 'page.'?
            if not snippet or "page." not in snippet:
                 logging.error(f"Received invalid/empty interaction snippet from Gemini: {snippet}")
                 return None
            
            return snippet
        except Exception as e:
            logging.error(f"Error calling Gemini API for interaction snippet: {e}")
            if 'response' in locals(): logging.error(f"Gemini raw text at time of error: {response.text}")
            return None

    def handle_field(self, page: Page, profile_key: str, selector: str, value: str | list, probe_elements_map: dict) -> bool:
        """Handles fields, checking for file uploads first, then delegating complex interactions to AI."""
        logging.debug(f"Handling Lever field: key={profile_key}, selector={selector}")
        handled_by_strategy = False 
        action_success = False
        field_context = probe_elements_map.get(selector) # Get full context from map
        
        # Define keys specifically for file uploads
        file_upload_keys = ["resume_upload", "cover_letter_upload"]

        if not field_context:
            logging.warning(f"Context not found for selector '{selector}' in probe_elements_map. Cannot use AI interaction or advanced handling. Deferring to default.")
            return False # Let main_v0 handle it with default action_taker
            
        # Check if value is None or empty
        if value is None or (isinstance(value, str) and value.strip() == ""):
            logging.warning(f"Missing value for {profile_key} even after profile enhancement. Field may be left blank.")
            return False # Nothing to fill, let main_v0 potentially skip it cleanly

        # --- 1. Explicit Handling for File Uploads (Highest Priority) ---
        if profile_key in file_upload_keys:
            handled_by_strategy = True
            element_tag = field_context.get('tag')
            element_type_attr = field_context.get('attributes', {}).get('type')

            if element_tag == 'input' and element_type_attr == 'file':
                logging.info(f"Handling file upload for {profile_key} with selector {selector}")
                if isinstance(value, str) and os.path.exists(value):
                    action_success = action_taker.upload_file(page, selector, value)
                elif isinstance(value, str): # Check if path doesn't exist
                    logging.error(f"File path '{value}' for {profile_key} does not exist. Skipping upload.")
                    action_success = False # Indicate failure due to bad path
                else:
                    logging.error(f"Invalid file path value '{value}' for {profile_key}. Skipping upload.")
                    action_success = False
            elif element_tag == 'textarea':
                logging.warning(f"Gemini mapped file upload key '{profile_key}' to a <textarea> ({selector}). This is likely incorrect for a file upload. Attempting to paste content instead.")
                try:
                    if isinstance(value, str) and os.path.exists(value):
                        with open(value, 'r', encoding='utf-8', errors='ignore') as f:
                            file_content = f.read()
                        logging.info(f"Pasting content of {value} into textarea for {profile_key}")
                        action_success = action_taker.fill_field(page, selector, file_content)
                    else:
                        logging.error(f"Cannot read file path '{value}' to paste into textarea for {profile_key}. Skipping.")
                        action_success = False # Cannot fill textarea if file is unreadable
                except Exception as e:
                    logging.error(f"Error reading file {value} or filling textarea for {profile_key}: {e}")
                    action_success = False
            else:
                logging.warning(f"Gemini mapped file upload key '{profile_key}' to an unexpected element: tag={element_tag}, type={element_type_attr}, selector={selector}. Skipping action.")
                action_success = True # Mark as handled (by skipping) to prevent default action
            
            return action_success # Return result of file handling

        # --- 2. AI Interaction Logic for Complex Types ---
        # Now check for other complex types if it wasn't a file upload key
        field_type = self._infer_field_type(profile_key, field_context) 
        ai_interaction_types = ['checkbox', 'radio', 'select']
        if field_type in ai_interaction_types:
            logging.info(f"Attempting AI-driven interaction for complex field: {profile_key} (type: {field_type}), Value: {value}")
            handled_by_strategy = True
            snippet = self._get_ai_interaction_snippet(field_context, value)
            
            if snippet:
                logging.info(f"Executing AI-generated snippet for {profile_key}...")
                try:
                    exec_globals = {
                        "page": page, 
                        "logging": logging, 
                        "add_random_delay": add_random_delay, 
                    }
                    exec(snippet, exec_globals)
                    action_success = True # Assume success if exec doesn't raise error
                    logging.info(f"Successfully executed AI snippet for {profile_key}.")
                except Exception as exec_err:
                    logging.error(f"Error executing AI-generated snippet for {profile_key}: {exec_err}", exc_info=True)
                    logging.error(f"--- Failed Snippet Start ---\n{snippet}\n--- Failed Snippet End ---") # Log the exact snippet
                    action_success = False
            else:
                logging.error(f"Failed to get AI interaction snippet for {profile_key}. Cannot proceed with this field.")
                action_success = False
            
            return action_success # Return result of AI handling

        # --- 3. Fallback/Return --- 
        # If not handled by file upload logic or AI interaction,
        # return False so main_v0 can use action_taker.fill_field as default.
        logging.debug(f"No specific Lever strategy handler or AI interaction needed for '{profile_key}' (type: {field_type}). Deferring to main_v0 default fallback.")
        return False

    def get_submit_selectors(self) -> list[str]:
        """Returns common submit button texts/selectors for Lever."""
        # Lever forms often use a specific button type/class
        return [
            'button[data-qa="btn-submit-application"]', # Lever's typical submit button QA selector
            "Submit application", # Text fallback
            "Submit" # Generic fallback
        ]

    def perform_pre_upload_steps(self, page: Page):
        """Lever might require clicking a resume upload button first."""
        # Example: Click button if resume input itself isn't found by default finder
        logging.debug("Checking if pre-upload steps needed for Lever...")
        # Add logic here if tests show resume upload fails without prior action
        pass

    def perform_pre_submit_steps(self, page: Page):
        """No specific pre-submit steps identified for Lever yet."""
        logging.debug("No Lever-specific pre-submit steps required yet.")
        pass
