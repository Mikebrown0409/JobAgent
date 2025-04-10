import logging
import json
import os
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from .base_strategy import BaseApplicationStrategy
# We might need access to the default browser_controller functions if not overridden
import browser_controller 
import action_taker # For fallback actions if handle_field doesn't cover everything
from probe_page_structure import probe_page_for_llm # Import the LLM probe function
from action_taker import add_random_delay

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
    standard_fields = [
        # Core Info
        "full_name", "first_name", "last_name", "email", "phone", "location", 
        # Links
        "linkedin_url", "github_url", "portfolio_url", "other_url", "website",
        # Uploads
        "resume_upload", "cover_letter_upload", 
        # Authorization / Logistics
        "work_authorization_us", "require_sponsorship", "salary_expectation",
        # EEO Section
        "gender", "race", "ethnicity", "veteran_status", "disability_status",
        # Common Custom Questions (Keywords - AI might find variations)
        "notice_period", "how_did_you_hear", "why_company", "why_position",
        # The critical final step
        "submit_button"
    ]

    prompt = f"""
Analyze the following JSON representation of interactive elements found on a job application page.
This is specifically a Greenhouse job application form. 

Identify the most likely CSS selector for each of the requested standard fields based ONLY on the provided data (labels, attributes, text context, etc.).

Requested standard fields: {json.dumps(standard_fields)}

Page Elements JSON:
```json
{page_structure_json}
```

Respond ONLY with a valid JSON object mapping the standard field names (from the requested list) to their corresponding best-guess CSS selector string found in the input JSON. 
Use the 'selector' value from the input JSON elements for the mapping.
Map profile keys to the specific INPUT, SELECT, or TEXTAREA selector, NOT the surrounding div or label.
For Greenhouse, many fields will have IDs like '#first_name', '#last_name', '#email', '#phone', or '#question_123456' for custom questions.
If a standard field corresponds to multiple elements (e.g., radio buttons for 'gender', checkboxes for 'race'), return the selector for the *most relevant containing element* or the first option's selector if that's not possible.
If a standard field cannot be confidently matched to any element in the provided JSON, map it to `null` or omit it from the response JSON.

Example valid response format:
{{ "first_name": "#first_name", "last_name": "#last_name", "email": "#email", "phone": "#phone", "why_company": "#question_12345678", "submit_button": "input[type='submit']", "location": null }}

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

class GreenhouseStrategy(BaseApplicationStrategy):
    """Strategy implementation for Greenhouse job application forms using AI interaction."""

    def find_fields(self, page: Page) -> tuple[list[dict], dict]:
        """Uses AI-driven analysis via page probe and LLM call to identify fields. 
           Returns a tuple: (list_of_validated_fields, probe_context_map)."""
        logging.info("Using AI-driven field finding for Greenhouse strategy...")
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
                             # Add with defaults
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
        if profile_key == 'cover_letter_upload': return 'file'
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
            if type_guess == 'radio': return 'radio'
            if type_guess == 'checkbox': return 'checkbox'
            if type_guess == 'file': 
                if profile_key == 'resume_upload' or profile_key == 'cover_letter_upload':
                    return 'file'
                else:
                    logging.warning(f"Input type='file' found for unexpected key '{profile_key}'. Treating as text for now.")
                    return 'text'
            
            # Most others map to 'text' for filling
            return 'text' 
            
        # Priority 4: Role attribute
        role = probe_info.get('role', '')
        if role == 'combobox' or role == 'listbox': return 'select' 
        if role == 'radiogroup': return 'radio'
        
        # Default fallback
        return 'text'

    def _get_ai_interaction_snippet(self, element_context: dict, desired_value: str | list) -> str | None:
        """Calls Gemini with element context and desired value to get an interaction snippet."""
        if not GEMINI_API_KEY:
            logging.error("Cannot call Gemini for interaction: API key not configured.")
            return None

        logging.info(f"--- Calling Gemini API for interaction snippet --- Selector: {element_context.get('selector')}, Value: {desired_value}")
        model = genai.GenerativeModel('gemini-1.5-flash')

        # Format desired value for prompt (handle lists for checkboxes)
        formatted_value = json.dumps(desired_value)
        element_type = element_context.get('type_guess', element_context.get('tag', 'unknown'))
        
        # Enhanced prompt for EEO and dropdown fields
        is_eeo_field = False
        field_key = element_context.get('field_key', '')
        label_text = element_context.get('label', '').lower()
        
        eeo_keywords = ['gender', 'race', 'ethnicity', 'veteran', 'disability', 'equal opportunity', 'diversity']
        if field_key and any(keyword in field_key.lower() for keyword in eeo_keywords):
            is_eeo_field = True
        elif label_text and any(keyword in label_text for keyword in eeo_keywords):
            is_eeo_field = True

        prompt = f"""
You are an expert Playwright automation assistant specializing in filling web forms.
Your task is to generate a Python code snippet using ONLY the `page` object provided to interact with a specific web element to set its value.

**Goal:** Set the element described below to match the desired value: {formatted_value}

**Element Context (JSON):**
```json
{json.dumps(element_context, indent=2)}
```

**Instructions:**
1. Analyze the context JSON ('tag', 'type_guess', 'role', 'label', 'selector', etc.).
2. Determine the correct Playwright action based on the element type and goal:
    - **Checkboxes (`input[type=checkbox]`):** Use `page.locator(...).check()`. 
    - **Radio Buttons (`input[type=radio]`):** Use `page.locator(...).check()`. Generate code to check the radio button whose value or label matches {formatted_value}.
    - **Select Dropdowns (`select`):** Implement intelligent option discovery and matching:
      ```python
      # First - extract all available options to know what we're working with
      options = page.evaluate('''(selector) => {{
          const select = document.querySelector(selector);
          if (!select) return [];
          return Array.from(select.options).map(o => ({{
              text: o.text.trim(), 
              value: o.value,
              selected: o.selected,
              index: o.index
          }}));
      }}''', '{element_context.get('selector')}')
      
      logging.info(f"Available dropdown options for {element_context.get('selector')}: {{options}}")
      
      # No simple mapping works in all cases - we need to be intelligent
      desired_value = {formatted_value}
      desired_lower = desired_value.lower() if isinstance(desired_value, str) else ""
      
      # Initialize variables to track best matches
      best_match = None
      best_match_score = 0
      fallback_match = None
      
      # Common patterns for Yes/No/Decline answers in EEO questions
      yes_patterns = ["yes", "i am", "i do", "i have", "identify", "protected veteran", "disability"]
      no_patterns = ["no", "i do not", "don't", "i am not", "not a protected", "no disability"]
      decline_patterns = ["decline", "don't wish", "prefer not", "not to answer", "choose not"] 
      
      # Step 1: Try direct equality match
      for option in options:
          option_text = option['text'].lower()
          # Direct match is best
          if desired_lower == option_text or desired_lower in option_text:
              best_match = option
              best_match_score = 100
              break
              
      # Step 2: If no direct match and this looks like yes/no/decline field, try pattern matching
      if not best_match and best_match_score < 80:
          # For Yes values
          if any(pattern in desired_lower for pattern in yes_patterns):
              for option in options:
                  option_text = option['text'].lower()
                  # Look for yes patterns in options
                  matches = sum(pattern in option_text for pattern in yes_patterns)
                  if matches > best_match_score:
                      best_match = option
                      best_match_score = matches
                      
          # For No values
          elif any(pattern in desired_lower for pattern in no_patterns):
              for option in options:
                  option_text = option['text'].lower()
                  # Look for no patterns in options
                  matches = sum(pattern in option_text for pattern in no_patterns)
                  if matches > best_match_score:
                      best_match = option
                      best_match_score = matches
                      
          # Set a fallback to "prefer not to answer" if we need it
          for option in options:
              option_text = option['text'].lower()
              if any(pattern in option_text for pattern in decline_patterns):
                  fallback_match = option
      
      # Use the best match we found, fallback if needed
      if best_match:
          logging.info(f"Selected best matching option: {{best_match}}")
          if best_match['value']:
              page.select_option('{element_context.get('selector')}', value=best_match['value'])
          else:
              page.select_option('{element_context.get('selector')}', index=best_match['index'])
      elif fallback_match:
          logging.info(f"Using fallback 'decline to answer' option: {{fallback_match}}")
          if fallback_match['value']:
              page.select_option('{element_context.get('selector')}', value=fallback_match['value'])
          else:
              page.select_option('{element_context.get('selector')}', index=fallback_match['index'])
      else:
          logging.warning(f"No matching option found for {formatted_value}. Attempt direct selection.")
          try:
              page.select_option('{element_context.get('selector')}', label={formatted_value})
          except Exception as e:
              logging.error(f"Failed to select option: {{e}}")
      ```
    - **Text/Other Inputs (`input`, `textarea`):** Use `page.locator(...).fill(...)`.
    - **Buttons/Links:** Use `page.locator(...).click()`.
3. Use the most specific selector available in the context.
4. **Important:**
    - The snippet MUST use the variable `page`.
    - The snippet MUST NOT include `import` statements.
    - The snippet MUST NOT include `async` or `await`.
    - The snippet MUST NOT define functions or classes.
    - The snippet MUST NOT create new browser contexts or pages.
    - The snippet MUST contain at least one `page.` action.
5. For EEO dropdown fields (gender, ethnicity, race, veteran_status, disability_status):
   - Don't assume exact text matches will work
   - Use intelligent pattern matching across all available options
   - Log the options found before making a selection decision
   - Include a fallback to "prefer not to answer" option if no good match is found

**Example Snippets:**
- Checkbox: `page.locator('input[name="option1"][value="Yes"]').check()`
- Fill text: `page.locator('#first_name').fill('John')`
- Radio button: `page.locator('input[type="radio"][value="Yes"]').check()`
- Complex dropdown with inspection:
```python
# Get all options
options = page.evaluate('''(selector) => {{
    const select = document.querySelector(selector);
    if (!select) return [];
    return Array.from(select.options).map(o => ({{ text: o.text, value: o.value, index: o.index }}));
}}''', '#veteran_status')

logging.info(f"Available options: {{options}}")

# Find best match for "No" response
best_match = None
for option in options:
    if "not a protected veteran" in option['text'].lower():
        best_match = option
        break

if best_match:
    page.select_option('#veteran_status', value=best_match['value'])
else:
    # Fallback to option containing "no" or index 1 (often the "No" option)
    for option in options:
        if "no" in option['text'].lower():
            page.select_option('#veteran_status', value=option['value'])
            break
    else:
        # Last resort fallback
        if len(options) > 1:
            page.select_option('#veteran_status', index=1)
```

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
            if not snippet or "page." not in snippet:
                 logging.error(f"Received invalid/empty interaction snippet from Gemini: {snippet}")
                 return None
            
            return snippet
        except Exception as e:
            logging.error(f"Error calling Gemini API for interaction snippet: {e}")
            if 'response' in locals(): logging.error(f"Gemini raw text at time of error: {response.text}")
            return None

    def handle_field(self, page: Page, profile_key: str, selector: str, value: str | list, probe_elements_map: dict = None) -> bool:
        """Handles fields, delegating complex interactions (checkbox, radio, EEO select) to AI-generated snippets."""
        logging.debug(f"Handling Greenhouse field: key={profile_key}, selector={selector}")
        handled_by_strategy = False 
        action_success = False
        field_context = probe_elements_map.get(selector) if probe_elements_map else {}
        field_type = self._infer_field_type(profile_key, field_context if field_context else {})
        
        # Check if value is None or empty
        if value is None or (isinstance(value, str) and value.strip() == ""):
            logging.warning(f"Missing value for {profile_key} even after profile enhancement. Field may be left blank.")
            return False

        # --- Define Types Requiring AI Interaction --- 
        ai_interaction_types = ['checkbox', 'radio', 'select']

        # --- AI Interaction Logic for Complex Types ---
        # Use AI if the inferred type requires complex interaction
        if field_type in ai_interaction_types and field_context:
            logging.info(f"Attempting AI-driven interaction for complex field: {profile_key} (type: {field_type}), Value: {value}")
            handled_by_strategy = True
            snippet = self._get_ai_interaction_snippet(field_context, value)
            
            if snippet:
                logging.info(f"Executing AI-generated snippet for {profile_key}...")
                try:
                    # Execute the snippet
                    exec_globals = {
                        "page": page, 
                        "logging": logging, 
                        "add_random_delay": add_random_delay
                    }
                    exec(snippet, exec_globals)
                    action_success = True
                    logging.info(f"Successfully executed AI snippet for {profile_key}.")
                except Exception as exec_err:
                    logging.error(f"Error executing AI-generated snippet for {profile_key}: {exec_err}", exc_info=True)
                    logging.error(f"--- Failed Snippet Start ---\n{snippet}\n--- Failed Snippet End ---")
                    action_success = False
        else:
                logging.error(f"Failed to get AI interaction snippet for {profile_key}. Falling back to default handling.")
                action_success = False
                handled_by_strategy = False
        
        # If not handled by AI or AI failed, try standard handling
        if not handled_by_strategy:
            logging.debug(f"Using default action handling for '{profile_key}' (type: {field_type}).")
            return False  # Let main_v0 use action_taker as default

    def get_submit_selectors(self) -> list[str]:
        """Returns common submit button texts/selectors for Greenhouse."""
        return [
            'input[type="submit"]',
            'button[type="submit"]',
            "Submit Application", 
            "Submit", 
            "Apply"
        ]

    def perform_pre_upload_steps(self, page: Page):
        """No specific pre-upload steps typically needed for Greenhouse."""
        logging.debug("No Greenhouse-specific pre-upload steps required.")
        pass

    def perform_pre_submit_steps(self, page: Page):
        """No specific pre-submit steps typically needed for Greenhouse."""
        logging.debug("No Greenhouse-specific pre-submit steps required.")
        pass
