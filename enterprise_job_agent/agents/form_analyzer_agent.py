"""Form Analyzer Agent for analyzing job application forms."""

import logging
import json
import re
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from crewai import Agent
from langchain_core.language_models import BaseLLM
from playwright.async_api import Error, Page, Frame, ElementHandle

from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.tools.element_selector import ElementSelector

logger = logging.getLogger(__name__)

# Define the new constant near the others
MAX_HTML_SNIPPET_LENGTH = 500; # Max length for HTML snippets
MAX_PARENT_HTML_SNIPPET_LENGTH = 1000 # Max length for Parent HTML snippet
REQUIRED_INDICATOR_REGEX = re.compile(r"(\\*|required|req'd)", re.IGNORECASE) # Regex for common required indicators

@dataclass
class FormAnalysisResult:
    """Result of a form analysis operation."""
    success: bool
    form_structure: Dict[str, Any]
    error: Optional[str] = None

SYSTEM_PROMPT = """You are an expert Form Analysis Specialist focusing on job applications.

TASK:
Analyze job application forms to extract their structure, field types, and requirements for automated completion.

YOUR EXPERTISE:
- Deep understanding of web form structure and field types
- Recognizing common job application patterns and fields
- Identifying required fields, validation rules, and relationships
- Detecting multi-page form structures and navigation
- Categorizing form elements by purpose and importance

APPROACH:
1. Examine HTML structure to identify form elements, particularly focusing on:
   - Input fields (text, select, checkbox, radio, file uploads)
   - Field labels and placeholders
   - Required field indicators
   - Validation rules
   - Dropdown options (critical for proper field classification)
   - Section and grouping elements

2. For dropdowns/selects:
   - Identify not just by HTML tag but also by UI behavior
   - Look for elements with classes like 'dropdown', 'select', 'combo'
   - Consider fields with names like 'degree', 'school', 'education', 'location' as likely dropdowns
   - Capture all available options when present

3. For form fields, classify by:
   - Purpose (personal info, education, experience, etc.)
   - Importance (required, important but optional, purely optional)
   - Field type (text, select, checkbox, file, etc.)
   - Expected format (email, date, phone number, etc.)

4. Analyze form navigation and structure:
   - Detect multi-page forms and their navigation elements
   - Identify frames and embedded forms
   - Note any special handling needed for specific fields

ALWAYS STRUCTURE YOUR ANALYSIS AS JSON following the exact schema provided in the task.
"""

class FormAnalyzerAgent:
    """Creates an agent specialized in form analysis."""
    
    def __init__(
        self,
        llm: Any,
        diagnostics_manager: Optional[DiagnosticsManager] = None,
        tools: List[Any] = None,
        verbose: bool = False
    ):
        """Initialize the form analyzer agent."""
        self.llm = llm
        self.diagnostics_manager = diagnostics_manager
        self.verbose = verbose
        self.logger = logging.getLogger(__name__)
        self.agent = self.create(llm, tools, verbose)
    
    @staticmethod
    def create(
        llm: Any,
        tools: List[Any] = None,
        verbose: bool = False
    ) -> Agent:
        """Create a Form Analyzer Agent."""
        return Agent(
            role="Form Analysis Specialist",
            goal="Analyze job application forms to extract their structure for automated completion",
            backstory="""You are an expert in analyzing complex web forms, particularly for job applications.
            Your detailed analysis helps AI systems navigate and complete these forms efficiently.
            You have a keen eye for identifying required fields, validation rules, and form navigation.
            Your expertise in recognizing dropdown fields and their available options is particularly valuable.""",
            verbose=verbose,
            allow_delegation=False,
            tools=tools or [],
            llm=llm,
            system_prompt=SYSTEM_PROMPT
        )
    
    async def analyze_form_with_browser(
        self,
        browser_manager,
        url: str,
        mapped_frames: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Analyze a form using a browser manager by inspecting the live DOM across frames.
        
        Args:
            browser_manager: Browser manager instance with an active page.
            url: URL of the page (used for context).
            mapped_frames: Optional dictionary of frame_id: frame_object from FrameManager.
            
        Returns:
            List of analyzed form elements from all analyzed frames.
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage("analyze_live_form_across_frames")

        all_form_elements = []
        analysis_errors = []
        
        # Instantiate ElementSelector here
        element_selector = ElementSelector(browser_manager, self.diagnostics_manager)

        try:
            if not browser_manager or not browser_manager.page:
                raise ValueError("BrowserManager or its page is not initialized.")
            
            # Use provided mapped frames or default to just the main frame
            frames_to_analyze = mapped_frames
            if not frames_to_analyze:
                 self.logger.warning("No mapped_frames provided, analyzing only main frame.")
                 main_frame = browser_manager.page.main_frame
                 if not main_frame:
                     raise ConnectionError("Could not access the main frame of the page.")
                 frames_to_analyze = {"main": main_frame} # Default identifier

            self.logger.info(f"Analyzing {len(frames_to_analyze)} frame(s)...")

            # Analyze structure for each frame
            for frame_id, frame_obj in frames_to_analyze.items():
                 if not frame_obj: # Skip if frame object is invalid
                      self.logger.warning(f"Skipping analysis for frame '{frame_id}': Invalid frame object.")
                      continue
                 try:
                     self.logger.debug(f"Analyzing frame: {frame_id} (URL: {frame_obj.url})")
                     # Pass element_selector to the analysis method
                     frame_elements = await self.analyze_live_form_structure(frame_obj, frame_id, element_selector)
                     all_form_elements.extend(frame_elements)
                     self.logger.debug(f"Found {len(frame_elements)} elements in frame '{frame_id}'")
                 except Exception as frame_e:
                      error_msg = f"Failed to analyze frame '{frame_id}': {frame_e}"
                      self.logger.error(error_msg, exc_info=True)
                      analysis_errors.append(error_msg)
                      # Continue analyzing other frames if one fails?
                      # For now, let's continue
                      pass 
            
            # Combine results - NO! Return only the list to match Task expected_output
            # analysis_output = {
            #     "form_elements": all_form_elements,
            #     "url": url, # Keep URL for context
            #     "analysis_type": "live_multi_frame",
            #     "frames_analyzed": list(frames_to_analyze.keys()),
            #     "errors": analysis_errors
            # }
            
            if self.diagnostics_manager:
                # Log details before returning just the list
                self.diagnostics_manager.end_stage(
                    stage_name="analyze_live_form_across_frames", # Use the correct stage name
                    success=not analysis_errors, 
                    error="; ".join(analysis_errors) or None, 
                    details={"total_elements_found": len(all_form_elements), "frames_analyzed": len(frames_to_analyze)}
                 )
            
            # Return ONLY the list of elements
            return all_form_elements
            
        except Exception as e:
            error_msg = f"Live multi-frame analysis failed for {url}: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(False, error=error_msg)
            raise
    
    async def analyze_live_form_structure(self, frame: Any, frame_id: str, element_selector: ElementSelector) -> List[Dict[str, Any]]:
         """Analyzes the structure of a form within a given Playwright frame.
         
         Args:
             frame: The Playwright Frame object to analyze.
             frame_id: The identifier assigned to this frame by FrameManager.
             element_selector: The ElementSelector instance for this frame
             
         Returns:
             A list of dictionaries, each representing a found form element.
         """
         self.logger.info(f"Starting live analysis of frame '{frame_id}' (URL: {frame.url})")
         form_elements = []

         # Enhanced selectors for better field detection
         field_selectors = "input, select, textarea, [role='combobox'], [role='listbox'], [role='textbox'], [contenteditable='true'], .form-control, .input-field, .react-select"
         button_selectors = "button, input[type='submit'], input[type='button'], [role='button'], a.btn, a.button, .btn, .button, [aria-label*='submit'], [aria-label*='apply']"
         container_selectors = "form, [role='form'], .form, .form-group, fieldset, .field-container, .input-container, .form-section"
         required_attr_selectors = "[required], [aria-required='true'], .required, .mandatory"

         try:
             # --- First, identify form containers to help with context ---
             container_locators = frame.locator(container_selectors)
             container_count = await container_locators.count()
             self.logger.debug(f"Found {container_count} potential form containers")
             
             # --- Identify all required fields first with attribute-based detection ---
             required_field_map = {}
             required_locators = frame.locator(required_attr_selectors)
             required_count = await required_locators.count()
             self.logger.debug(f"Found {required_count} elements with explicit required attributes")
             
             for i in range(required_count):
                 try:
                     element_handle = await required_locators.nth(i).element_handle()
                     if not element_handle: continue
                     
                     element_id = await element_handle.get_attribute("id") or ""
                     element_name = await element_handle.get_attribute("name") or ""
                     
                     # Store in map for later reference
                     key = f"{element_id or ''}_{element_name or ''}".strip("_")
                     if key:
                         required_field_map[key] = True
                         self.logger.debug(f"Marked field as required by attribute: {key}")
                 except Exception as e:
                     self.logger.debug(f"Error processing required field: {e}")

             # --- Analyze Form Fields --- 
             field_locators = frame.locator(field_selectors)
             count = await field_locators.count()
             self.logger.debug(f"Found {count} potential form fields using enhanced selectors")

             for i in range(count):
                 try:
                     element_handle = await field_locators.nth(i).element_handle()
                     if not element_handle: continue

                     # Extract basic element data
                     element_data = await self._extract_element_data(frame, element_handle, "field", frame_id, element_selector)
                     if not element_data: continue
                     
                     # Enhanced required field detection
                     element_id = element_data.get("element_id", "")
                     name = element_data.get("name", "")
                     label_text = element_data.get("label_text", "").lower()
                     
                     # Check if this field was already marked as required by attribute
                     key = f"{element_id or ''}_{name or ''}".strip("_")
                     
                     # Additional required field detection logic
                     if not element_data.get("required", False):
                         # Check the map from previous required attribute scan
                         if key and key in required_field_map:
                            element_data["required"] = True
                            element_data["required_reason"] = "Attribute map"
                            self.logger.debug(f"Field {element_data['selector']} marked required via attribute map.")
                         # Check label text for common required markers (asterisk, "(required)")
                         elif any(marker in label_text for marker in ["*", "(required)"]):
                             # Avoid marking purely informational fields like headers if they accidentally match
                             if element_data.get("field_type") not in ["label", "heading", "unknown"]:
                                element_data["required"] = True
                                element_data["required_reason"] = "Label text"
                                self.logger.debug(f"Field {element_data['selector']} marked required via label text.")

                     form_elements.append(element_data)
                 except Error as playwright_error:
                     # Catch Playwright-specific errors (e.g., element detached)
                     self.logger.warning(f"Playwright error processing field {i}: {playwright_error}")
                 except Exception as e:
                     self.logger.error(f"Error processing form field {i}: {e}", exc_info=True)
                     # Optionally append error information to the element data or a separate error list

             # --- Analyze Buttons --- 
             button_locators = frame.locator(button_selectors)
             btn_count = await button_locators.count()
             self.logger.debug(f"Found {btn_count} potential buttons")

             for i in range(btn_count):
                 try:
                     element_handle = await button_locators.nth(i).element_handle()
                     if not element_handle: continue

                     element_data = await self._extract_element_data(frame, element_handle, "button", frame_id, element_selector)
                     if element_data:
                         # Prioritize submit/apply buttons
                         button_text = element_data.get("text_content", "").lower()
                         if any(action in button_text for action in ["submit", "apply", "continue", "next"]):
                             element_data["is_submit"] = True
                         form_elements.append(element_data)
                 except Error as playwright_error:
                     self.logger.warning(f"Playwright error processing button {i}: {playwright_error}")
                 except Exception as e:
                     self.logger.error(f"Error processing button {i}: {e}", exc_info=True)

         except Error as playwright_error:
             self.logger.error(f"Playwright error during live analysis of frame '{frame_id}': {playwright_error}")
             raise # Re-raise Playwright errors
         except Exception as e:
             self.logger.error(f"Unexpected error during live analysis of frame '{frame_id}': {e}", exc_info=True)
             # Consider whether to raise or return partial results
             # For now, return what we have, errors should be logged in analyze_form_with_browser
             pass 

         self.logger.info(f"Finished live analysis of frame '{frame_id}', found {len(form_elements)} elements.")
         return form_elements

    async def _extract_element_data(self, frame: Any, element_handle: Any, element_category: str, frame_id: str, element_selector: ElementSelector) -> Optional[Dict[str, Any]]:
         """Extracts detailed data about a single form element handle.
         Now includes widget_type classification.
         """
         element_info = None # Initialize to ensure it's defined
         try:
             log_prefix = "ELEM_DATA_LOG: "
             dbg_id = await element_handle.get_attribute("id") or "[no id]"
             dbg_tag = await element_handle.evaluate("el => el.tagName.toLowerCase()") or "unknown"
             self.logger.debug(f"{log_prefix}Starting extraction for {dbg_tag}#{dbg_id}")

             tag_name = (await element_handle.evaluate("el => el.tagName.toLowerCase()")) or "unknown"
             element_id = await element_handle.get_attribute("id")
             name = await element_handle.get_attribute("name")
             placeholder = await element_handle.get_attribute("placeholder")
             element_type = await element_handle.get_attribute("type") if tag_name == "input" else None
             role = await element_handle.get_attribute("role")
             class_name = await element_handle.get_attribute("class") or ""
             
             self.logger.debug(f"{log_prefix}Element {dbg_tag}#{dbg_id} attributes: tag={tag_name}, role='{role}', type='{element_type}', class='{class_name[:50]}...'") # Log key attributes

             is_visible = await element_handle.is_visible()
             is_enabled = await element_handle.is_enabled()
             text_content = (await element_handle.text_content() or "").strip()
             outer_html_snippet = await element_handle.evaluate("el => el.outerHTML.substring(0, 500)") # Snippet for context
             
             # Basic required check (more comprehensive check done in analyze_live_form_structure)
             required = await element_handle.evaluate("el => el.required || el.getAttribute('aria-required') === 'true'")
             
             # --- Generate Stable Selector --- 
             selector = None
             if element_category == "button" and await element_handle.evaluate("el => el.getAttribute('type') === 'submit'"):
                 # Prioritize [type="submit"] for submit buttons, potentially with text
                 text = (await element_handle.text_content() or "").strip()
                 if text:
                     # Use element_selector for escaping
                     selector = f"button[type='submit']:has-text('{element_selector._escape_css_string(text)}')"
                 else:
                     selector = "button[type='submit']" # Fallback if no text
                 self.logger.debug(f"Generated submit button selector: {selector}")

             if not selector:
                 # Use the dedicated tool to generate the best possible selector
                 selector = await element_selector.generate_stable_selector(element_handle, frame)
             
             # Fallback selector generation (absolute last resort if tool fails or selector still missing)
             if not selector:
                 self.logger.warning(f"ElementSelector tool failed to generate a stable selector for element {tag_name}#{element_id}. Falling back to basic tag name.")
                 selector = tag_name # Use tag name as the ultimate fallback
                 
             # --- Field Type and Widget Type Classification --- 
             field_type = "unknown"
             widget_type = "unknown" # NEW FIELD
             options = []
             
             classification_path = [] # Track how widget_type is set

             if element_category == "button":
                 field_type = "button"
                 widget_type = "button"
                 classification_path.append("category=button")
             elif tag_name == "select":
                 field_type = "select"
                 widget_type = "standard_select"
                 classification_path.append("tag=select")
                 # Extract options from standard select
                 option_elements = await element_handle.query_selector_all("option")
                 options = []
                 for opt in option_elements:
                     value = await opt.get_attribute("value")
                     text = (await opt.text_content() or "").strip()
                     # Exclude placeholder/disabled options if they have no value and empty text
                     disabled = await opt.is_disabled()
                     if (value or text) and not disabled:
                         options.append({"value": value, "text": text})
             elif tag_name == "textarea":
                 field_type = "textarea"
                 widget_type = "text_area" # Consistent naming convention?
                 classification_path.append("tag=textarea")
             elif tag_name == "input":
                 input_type = element_type.lower() if element_type else "text"
                 field_type = input_type # Default field_type to input type
                 classification_path.append(f"tag=input, type={input_type}")
                 
                 if input_type == "text":
                      widget_type = "text_input"
                 elif input_type == "email":
                      widget_type = "email_input"
                 elif input_type == "password":
                      widget_type = "password_input"
                 elif input_type == "number":
                      widget_type = "number_input"
                 elif input_type == "tel":
                      widget_type = "tel_input"
                 elif input_type == "url":
                      widget_type = "url_input"
                 elif input_type == "date":
                      widget_type = "date_input"
                 elif input_type == "checkbox":
                      field_type = "checkbox" # More specific field_type
                      widget_type = "checkbox"
                 elif input_type == "radio":
                      field_type = "radio" # More specific field_type
                      widget_type = "radio_button"
                 elif input_type == "file":
                      field_type = "file" # More specific field_type
                      widget_type = "file_input"
                 elif input_type == "submit" or input_type == "button" or input_type == "reset":
                      field_type = "button"
                      widget_type = "button_input" # Input button
                 else:
                      widget_type = "text_input" # Fallback for other input types like search, etc.
                 
                 # Refine for autocomplete/typeahead based on role or attributes
                 if role == "combobox" or "autocomplete" in class_name.lower():
                     classification_path.append(f"input refined by role/class -> autocomplete")
                     widget_type = "autocomplete"
                     # Try scraping options if it looks like autocomplete
                     try:
                         options = await self._scrape_dynamic_options(frame, element_handle, element_selector)
                     except Exception as scrape_ex:
                         self.logger.debug(f"Could not scrape options for potential autocomplete {selector}: {scrape_ex}")

             elif role == "combobox" or role == "listbox":
                 field_type = "select" # Treat these roles as selects for field_type purpose
                 widget_type = "custom_select"
                 classification_path.append(f"role={role} -> custom_select")
                 try:
                     options = await self._scrape_dynamic_options(frame, element_handle, element_selector)
                 except Exception as scrape_ex:
                      self.logger.debug(f"Could not scrape options for custom select {selector}: {scrape_ex}")
             elif "select" in class_name.lower() or "dropdown" in class_name.lower():
                 # Heuristic: if class contains 'select' or 'dropdown', treat as custom select
                 if tag_name != 'label': # Avoid misclassifying labels
                     classification_path.append(f"class heuristic -> custom_select")
                     field_type = "select"
                     widget_type = "custom_select"
                     try:
                         options = await self._scrape_dynamic_options(frame, element_handle, element_selector)
                     except Exception as scrape_ex:
                         self.logger.debug(f"Could not scrape options for potential custom select {selector}: {scrape_ex}")
             elif await element_handle.evaluate("el => el.getAttribute('contenteditable') === 'true'"): 
                 field_type = "textarea" # Treat contenteditable like textarea
                 widget_type = "rich_text_editor" # Or content_editable?
                 classification_path.append("contenteditable -> rich_text_editor")

             # --- Label Extraction --- 
             label_text = ""
             aria_label = await element_handle.get_attribute("aria-label")
             aria_labelledby = await element_handle.get_attribute("aria-labelledby")

             if aria_label:
                 label_text = aria_label
             elif aria_labelledby:
                 try:
                     label_element = await frame.query_selector(f"#{aria_labelledby}")
                     if label_element:
                         label_text = (await label_element.text_content() or "").strip()
                 except Exception as e:
                     self.logger.debug(f"Error finding label by aria-labelledby '{aria_labelledby}': {e}")
             
             # If no ARIA label, try standard label finding logic (JS evaluation)
             if not label_text:
                 try:
                     label_text = await element_handle.evaluate("""el => {
                         // Find associated label element
                         const findAssociatedLabel = (element) => {
                             if (!element) return null;
                             // 1. Check aria-label / aria-labelledby (already checked above, but good fallback)
                             const ariaLabel = element.getAttribute('aria-label');
                             if (ariaLabel) return ariaLabel.trim();
                             const labelledby = element.getAttribute('aria-labelledby');
                             if (labelledby) {
                                 const labelEl = document.getElementById(labelledby);
                                 if (labelEl) return labelEl.textContent?.trim() || null;
                             }
                             // 2. Check for <label for="...">
                             if (element.id) {
                                 const label = document.querySelector(`label[for="${element.id}"]`);
                                 if (label) return label.textContent?.trim() || null;
                             }
                             // 3. Check parent <label>
                             let parent = element.parentElement;
                             while (parent) {
                                 if (parent.tagName === 'LABEL') {
                                      // Get text content, excluding the input element's own text/value
                                      let labelClone = parent.cloneNode(true);
                                      let inputClone = labelClone.querySelector(element.tagName);
                                      if (inputClone) labelClone.removeChild(inputClone);
                                      return labelClone.textContent?.trim() || null;
                                 }
                                 // Stop if we hit the body or another form element container
                                 if (parent.tagName === 'BODY' || parent.closest('form, div.form-group, fieldset')) break; 
                                 parent = parent.parentElement;
                             }
                             // 4. Check sibling label or span immediately before/after
                             const prevSibling = element.previousElementSibling;
                             if (prevSibling && (prevSibling.tagName === 'LABEL' || prevSibling.tagName === 'SPAN')) {
                                 return prevSibling.textContent?.trim() || null;
                             }
                             const nextSibling = element.nextElementSibling;
                             if (nextSibling && nextSibling.tagName === 'LABEL') { // Less common
                                 return nextSibling.textContent?.trim() || null;
                             }
                             // 5. Check placeholder attribute (checked below in Python)
                             // 6. Check title attribute (checked below in Python)
                             return null;
                         };
                         return findAssociatedLabel(el);
                     }""")
                     label_text = (label_text or "").strip()
                 except Exception as e:
                     self.logger.debug(f"Error running JS label finder for {selector}: {e}")
             
             # Fallbacks for label
             if not label_text:
                 label_text = placeholder or ""
             if not label_text:
                  label_text = await element_handle.get_attribute("title") or ""
             if not label_text:
                 # Use name as last resort, converting camel/snake case
                  label_text = name or ""
                  label_text = re.sub(r'(?<!^)(?=[A-Z])', ' ', label_text).title() # Camel case
                  label_text = label_text.replace('_', ' ').replace('-', ' ').title() # Snake/kebab case
                 
             label_text = label_text.strip()

             # --- Filter out likely internal/non-interactive elements ---
             if await element_handle.evaluate("el => el.getAttribute('aria-hidden') === 'true'"):
                 self.logger.debug(f"{log_prefix}Skipping element {dbg_tag}#{dbg_id} (selector: {selector}) because aria-hidden is true.")
                 return None
             if await element_handle.evaluate("el => el.getAttribute('tabindex') === '-1'"):
                 # Also consider skipping tabindex=-1 unless it's a known interactive role
                 if role not in ["combobox", "listbox", "textbox"] and tag_name not in ["input", "select", "textarea", "button"]:
                    self.logger.debug(f"{log_prefix}Skipping element {dbg_tag}#{dbg_id} (selector: {selector}) because tabindex is -1 and role/tag is not interactive.")
                    return None
             # --- End Filtering ---

             # <<< START EXTRACTION OF PARENT HTML >>>
             parent_html_snippet: Optional[str] = None
             try:
                 # Use a JS function within evaluate to get the parent's outerHTML
                 parent_html_snippet = await element_handle.evaluate(
                     """(el, maxLength) => {
                         if (el.parentElement) {
                             // Limit length to avoid excessive data
                             return el.parentElement.outerHTML.substring(0, maxLength);
                         }
                         return null; // Return null for Python compatibility
                     }""",
                     MAX_PARENT_HTML_SNIPPET_LENGTH # Pass maxLength as argument
                 )
                 # Evaluate might return None directly if the JS returns null
                 if parent_html_snippet is None:
                     parent_html_snippet = None # Explicitly keep it None
             except Exception as parentHtmlError:
                  # Check if message exists before checking 'target closed'
                  msg = getattr(parentHtmlError, 'message', '')
                  if msg and 'target closed' not in msg: # Avoid spamming "target closed" errors
                      self.logger.warning(f"{log_prefix}Could not get parent HTML for {selector}: {parentHtmlError}")
                  parent_html_snippet = None # Ensure it's None on error
             # <<< END EXTRACTION OF PARENT HTML >>>

             element_info = {
                 "frame_id": frame_id,
                 "selector": selector, # Best guess selector
                 "element_id": element_id,
                 "name": name,
                 "tag_name": tag_name,
                 "field_type": field_type, 
                 "widget_type": widget_type, # Added widget type
                 "role": role,
                 "label_text": label_text,
                 "placeholder": placeholder,
                 "text_content": text_content if element_category == 'button' else None, # Only for buttons usually
                 "options": options if options else None, # Only include if options were found
                 "required": bool(required),
                 "required_reason": "Attribute" if required else None,
                 "is_visible": is_visible,
                 "is_enabled": is_enabled,
                 # Use element_selector for getting ARIA attributes
                 "aria_attributes": await element_selector._get_relevant_aria_attributes(element_handle),
                 "html_snippet": outer_html_snippet,
                 "parent_html_snippet": parent_html_snippet, # Add the new field here
             }

             self.logger.debug(f"{log_prefix}Final classification for {dbg_tag}#{dbg_id}: widget_type='{widget_type}', field_type='{field_type}' (Path: {classification_path})")

             return element_info

         except Error as playwright_error:
             # <<< START MODIFICATION >>>
             # Try to get some identifier even if basic attributes failed
             err_id = "[unknown_id_due_to_error]"
             try: err_id = await element_handle.get_attribute('id') or "[no id]"
             except: pass
             self.logger.error(f"{log_prefix}Playwright Error extracting data for element handle ID='{err_id}': {playwright_error}")
             # <<< END MODIFICATION >>>
             return None # Return None if extraction fails for an element
         except Exception as e:
             # <<< START MODIFICATION >>>
             err_id = "[unknown_id_due_to_error]"
             try: err_id = await element_handle.get_attribute('id') or "[no id]"
             except: pass
             self.logger.error(f"{log_prefix}Unexpected Error extracting data for element handle ID='{err_id}': {e}", exc_info=True)
             # <<< END MODIFICATION >>>
             return None # Return None if extraction fails for an element

    async def _scrape_dynamic_options(self, frame: Any, element_handle: Any, element_selector: ElementSelector) -> List[Dict[str, Any]]:
        """Attempts to scrape options associated with a custom dropdown/combobox/autocomplete.
        This might involve clicking the element and waiting for options to appear.
        Args:
            frame: The Playwright Frame containing the element.
            element_handle: The Playwright ElementHandle for the input/trigger element.
            element_selector: The ElementSelector instance for this frame

        Returns:
            A list of option dictionaries [{'value': ..., 'text': ...}] or an empty list.
        """ 
        options = []
        # Common selectors for dropdown options that appear after interaction
        option_selectors = [
            "li[role='option']", 
            "div[role='option']", 
            ".dropdown-item", 
            ".select-option", 
            ".autocomplete-suggestion",
            ".list-group-item",
            "ul[role='listbox'] > li", # Options within a listbox container
            "div[role='listbox'] > div[role='option']",
             # Add more specific selectors based on common libraries if needed
             # e.g., for React-Select: '.react-select__option'
        ]
        
        associated_list_selector = None
        try:
            # 1. Check ARIA attributes pointing to the list container
            aria_controls = await element_handle.get_attribute("aria-controls")
            aria_owns = await element_handle.get_attribute("aria-owns")
            list_id = aria_controls or aria_owns
            
            # Determine if this is the target field for enhanced logging
            target_element_id = await element_handle.get_attribute("id")
            is_target_field = target_element_id == "degree--0" # Simple check for now
            if is_target_field:
                self.logger.debug(f"DEGREE_FIELD_LOG: Starting _scrape_dynamic_options for target element {target_element_id}")

            if list_id:
                associated_list_selector = f"#{list_id}"
                if is_target_field:
                    self.logger.debug(f"DEGREE_FIELD_LOG: Found potential associated list via ARIA: {associated_list_selector}")
                else:
                    self.logger.debug(f"Found potential associated list via ARIA: {associated_list_selector}")
            else:
                # 2. Heuristic: Look for a nearby sibling/parent ul/div with role=listbox
                nearby_list_js = """el => {
                    let sibling = el.nextElementSibling;
                    if (sibling && sibling.getAttribute('role') === 'listbox') return '#' + sibling.id; // Prefer ID
                    if (sibling && sibling.querySelector('[role=\"listbox\"]')) return '#' + sibling.querySelector('[role=\"listbox\"]').id;
                    let parent = el.parentElement;
                    while (parent && parent.tagName !== 'BODY') {
                        const listbox = parent.querySelector('[role=\"listbox\"]');
                        if (listbox) return '#' + listbox.id; // Prefer ID
                        if (parent.getAttribute('role') === 'listbox') return '#' + parent.id;
                        parent = parent.parentElement;
                    }
                    return null;
                }"""
                try:
                    list_id_from_nearby = await element_handle.evaluate(nearby_list_js)
                    if list_id_from_nearby and list_id_from_nearby.startswith('#'):
                         associated_list_selector = list_id_from_nearby
                         if is_target_field:
                             self.logger.debug(f"DEGREE_FIELD_LOG: Found potential associated list via nearby heuristic: {associated_list_selector}")
                         else:
                            self.logger.debug(f"Found potential associated list via nearby heuristic: {associated_list_selector}")
                except Exception as js_err:
                     self.logger.debug(f"JS error looking for nearby listbox: {js_err}")

            # First check if options are already visible without clicking (non-intrusive)
            visible_without_click = False
            all_scraped_options = set()
            options_from_static = 0
            
            # Try to find options that are already visible without interaction
            for opt_selector in option_selectors:
                try:
                    option_locators = frame.locator(opt_selector)
                    opt_count = await option_locators.count()
                    
                    if opt_count > 0:
                        visible_options = 0
                        # Sample a few to see if any are visible
                        for i in range(min(opt_count, 3)):
                            opt_handle = await option_locators.nth(i).element_handle()
                            if opt_handle and await opt_handle.is_visible():
                                visible_options += 1
                        
                        if visible_options > 0:
                            self.logger.debug(f"Found {visible_options} already-visible options with selector {opt_selector} without clicking")
                            visible_without_click = True
                            
                            # Extract these already visible options
                            for i in range(min(opt_count, 50)):  # Limit to 50 per selector
                                opt_handle = await option_locators.nth(i).element_handle()
                                if not opt_handle or not await opt_handle.is_visible(): 
                                    continue
                                
                                value = await opt_handle.get_attribute("data-value")
                                text = (await opt_handle.text_content() or "").strip()
                                if text:
                                    normalized_text = text.lower()
                                    original_value = value.strip() if value else text
                                    all_scraped_options.add((normalized_text, original_value))
                                    options_from_static += 1
                except Exception:
                    continue
            
            if options_from_static > 0:
                self.logger.info(f"Found {options_from_static} options without clicking. Skipping intrusive dropdown interaction.")
            
            # Only proceed with clicking if we haven't found options yet
            if not visible_without_click and options_from_static == 0:
                # Trigger the dropdown/autocomplete (use click for robustness)
                # Use a short timeout as the list might appear instantly or already be present
                click_successful = False
                for attempt in range(2): # Try clicking twice
                    try:
                        self.logger.debug(f"Attempt {attempt+1}/2: Trying to trigger dropdown/autocomplete for {await element_handle.get_attribute('id') or 'element'}")
                        await element_handle.click(timeout=1500) 
                        await asyncio.sleep(0.3) # Short wait for dynamic content
                        click_successful = True
                        self.logger.debug(f"Click attempt {attempt+1} successful.")
                        break # Exit loop on success
                    except Exception as click_err:
                        error_str = str(click_err)
                        if "timeout" in error_str.lower() or "intercept" in error_str.lower() or "stable" in error_str.lower():
                            if attempt == 0:
                                self.logger.warning(f"Click attempt {attempt+1} failed ({click_err}), retrying after delay...")
                                await asyncio.sleep(0.3) # Delay before retry
                            else:
                                self.logger.warning(f"Click attempt {attempt+1} failed ({click_err}) after retry. Proceeding without confirmed click.")
                        else:
                             # Log other click errors but don't necessarily retry unless it's a timeout/stability issue
                             self.logger.debug(f"Could not click element to trigger options (may not be needed): {click_err}")
                             break # Don't retry for non-timeout/stability errors

                # Define the scope for searching options
                search_scope = frame
                if associated_list_selector:
                     try:
                          list_locator = frame.locator(associated_list_selector).first
                          await list_locator.wait_for(state='visible', timeout=1000) # Wait briefly for list container
                          search_scope = list_locator # Search within the identified container
                          if is_target_field:
                              self.logger.debug(f"DEGREE_FIELD_LOG: Searching for options within specific scope: {associated_list_selector}")
                          else:
                            self.logger.debug(f"Searching for options within scope: {associated_list_selector}")
                     except Exception:
                          if is_target_field:
                              self.logger.debug(f"DEGREE_FIELD_LOG: Associated list container {associated_list_selector} not found/visible. Searching globally.")
                          else:
                            self.logger.debug(f"Associated list container {associated_list_selector} not found or visible. Searching globally in frame.")
                          search_scope = frame # Fallback to frame
                else:
                     if is_target_field:
                         self.logger.debug("DEGREE_FIELD_LOG: No specific list container identified. Searching globally in frame.")
                     else:
                        self.logger.debug("No specific list container identified. Searching globally in frame.")

                # Try each common option selector within the determined scope
                # Consolidate options from ALL selectors
                max_total_options = 100 # Limit total options scraped across all selectors
                
                for opt_selector in option_selectors:
                    if len(all_scraped_options) >= max_total_options:
                         self.logger.debug(f"Reached max option limit ({max_total_options}), stopping selector checks.")
                         break # Stop if we hit the overall limit

                    try:
                        option_locators = search_scope.locator(opt_selector)
                        opt_count = await option_locators.count()

                        if opt_count > 0:
                            self.logger.debug(f"Found {opt_count} options using selector '{opt_selector}' within scope.")
                            # Limit options scraped per selector to avoid excessive time on one bad selector
                            scrape_limit = min(opt_count, 50) 
                            
                            if is_target_field:
                                self.logger.debug(f"DEGREE_FIELD_LOG: Trying selector '{opt_selector}'. Found {opt_count} raw elements (limit {scrape_limit}).")

                            options_from_this_selector = 0
                            for i in range(scrape_limit):
                                if len(all_scraped_options) >= max_total_options: break # Check limit within inner loop too

                                opt_handle = await option_locators.nth(i).element_handle()
                                if not opt_handle: continue
                                if not await opt_handle.is_visible(): continue # Ensure options are visible

                                # Extract value and text - adapt based on element structure
                                # Common patterns: data-value attribute, or just text content
                                value = await opt_handle.get_attribute("data-value")
                                text = (await opt_handle.text_content() or "").strip()
                                aria_label = await opt_handle.get_attribute("aria-label")
                                
                                # Refine text/value extraction
                                if not text and aria_label: # Use aria-label if text is empty
                                    text = aria_label.strip()
                                
                                # Normalize and store if text is valid
                                normalized_text = text.lower() # Store normalized text
                                if normalized_text:
                                    # Store tuple (normalized_text, original_value_or_text)
                                    # Use original text as value if no specific value attribute found
                                    original_value = value.strip() if value else text 
                                    all_scraped_options.add((normalized_text, original_value)) 
                                    options_from_this_selector += 1
                           
                            if options_from_this_selector > 0:
                                if is_target_field:
                                    self.logger.debug(f"DEGREE_FIELD_LOG: Added {options_from_this_selector} unique options from '{opt_selector}'. Total unique now: {len(all_scraped_options)}")
                                else:
                                    self.logger.debug(f"Added {options_from_this_selector} unique options from selector '{opt_selector}'. Total unique: {len(all_scraped_options)}")
                           
                    except Exception as e:
                        if is_target_field:
                            self.logger.debug(f"DEGREE_FIELD_LOG: Error checking option selector '{opt_selector}': {e}")
                        else:
                            self.logger.debug(f"Error checking option selector '{opt_selector}': {e}")
                        continue # Try next selector

                # Enhanced dropdown dismissal with multiple strategies and verification
                dismiss_successful = False
                
                # Strategy 1: Click body (but with better timeout)
                try:
                    await frame.locator('body').click(timeout=1000)
                    await asyncio.sleep(0.3)  # Slightly longer wait
                    dismiss_successful = True
                    self.logger.debug("Dismissed dropdown with body click")
                except Exception as e:
                    self.logger.debug(f"Body click dismissal failed: {e}")
                
                # Strategy 2: Press Escape key on body if first method failed
                if not dismiss_successful:
                    try:
                        await frame.press('body', 'Escape', timeout=1000)
                        await asyncio.sleep(0.3)
                        dismiss_successful = True
                        self.logger.debug("Dismissed dropdown with Escape key")
                    except Exception as e:
                        self.logger.debug(f"Escape key dismissal failed: {e}")
                
                # Strategy 3: Use JavaScript to click away or explicitly close dropdowns
                if not dismiss_successful:
                    try:
                        await frame.evaluate("""() => {
                            // Click the document body
                            document.body.click();
                            
                            // Also try to close any visible dropdowns/menus by attribute
                            const dropdowns = document.querySelectorAll('[aria-expanded="true"], [class*="open"], [class*="active"]');
                            for (const dropdown of dropdowns) {
                                dropdown.setAttribute('aria-expanded', 'false');
                                dropdown.classList.remove('open');
                                dropdown.classList.remove('active');
                            }
                        }""")
                        await asyncio.sleep(0.3)
                        self.logger.debug("Attempted dropdown dismissal with JavaScript")
                    except Exception as e:
                        self.logger.debug(f"JavaScript dismissal failed: {e}")

                # Verify dismissal by checking if dropdown options are still visible
                try:
                    visible_options = False
                    for opt_selector in option_selectors:
                        try:
                            option_locators = frame.locator(opt_selector)
                            opt_count = await option_locators.count()
                            if opt_count > 0:
                                opt_handle = await option_locators.nth(0).element_handle()
                                if opt_handle and await opt_handle.is_visible():
                                    visible_options = True
                                    break
                        except:
                            continue
                    
                    if visible_options:
                        self.logger.warning("Dropdown may still be open after dismissal attempts")
                    else:
                        self.logger.debug("Verified dropdown is no longer visible")
                except Exception as verify_err:
                    self.logger.debug(f"Error verifying dropdown dismissal: {verify_err}")

            # Convert set of tuples back to list of dicts
            options = [{"value": original, "text": original} for norm, original in all_scraped_options] # Simplified structure for now

            if is_target_field:
                self.logger.debug(f"DEGREE_FIELD_LOG: Final options scraped for target field: {options[:10]}..." if len(options) > 10 else options) # Log first 10 options

            if options:
                self.logger.info(f"Successfully scraped {len(options)} unique options in total for element.")
            else:
                 self.logger.debug(f"Could not scrape any dynamic options for element.")
                
        except Exception as e:
            self.logger.error(f"Error scraping dynamic options: {e}", exc_info=True)
        
        return options

    @staticmethod
    async def extract_job_details(page, diagnostics_manager=None) -> Dict[str, Any]:
        """
        Extract job details from the page.
        
        Args:
            page: Playwright page object
            diagnostics_manager: Optional DiagnosticsManager instance
            
        Returns:
            Dictionary containing job details
        """
        try:
            # Start job details extraction stage if diagnostics manager is available
            if diagnostics_manager:
                diagnostics_manager.start_stage("job_details_extraction")
            
            # Common selectors for job details
            selectors = {
                "title": [
                    "h1.job-title", "h1.posting-headline", ".job-title",
                    "h1:has-text('Software')", "h1:has-text('Engineer')",
                    "[data-test='job-title']", ".posting-headline"
                ],
                "company": [
                    ".company-name", ".employer-name", "[data-test='company-name']",
                    ".posting-categories"
                ],
                "location": [
                    ".location", ".job-location", "[data-test='location']",
                    ".posting-categories"
                ],
                "description": [
                    ".job-description", ".description", "[data-test='job-description']",
                    "#job-description", ".posting-description"
                ]
            }
            
            job_details = {}
            
            # Extract text for each field using selectors
            for field, field_selectors in selectors.items():
                for selector in field_selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            text = await element.text_content()
                            if text and text.strip():
                                job_details[field] = text.strip()
                                break
                    except Exception as e:
                        error_msg = f"Error extracting {field} with selector {selector}: {e}"
                        logger.debug(error_msg)
            
            # If no title found, try to get it from page title
            if "title" not in job_details:
                try:
                    title = await page.title()
                    if title:
                        # Clean up title - remove company name and common suffixes
                        title = title.split(" | ")[0].split(" at ")[0].strip()
                        job_details["title"] = title
                except Exception as e:
                    error_msg = f"Error extracting title from page title: {e}"
                    logger.debug(error_msg)
            
            # If no company found, try to get it from URL or title
            if "company" not in job_details:
                try:
                    url = page.url
                    # Extract company from URL (e.g., greenhouse.io/company/...)
                    company = url.split("/")[3].replace("-", " ").title()
                    job_details["company"] = company
                except Exception as e:
                    error_msg = f"Error extracting company from URL: {e}"
                    logger.debug(error_msg)
            
            # Ensure we have at least a title
            if not job_details.get("title"):
                job_details["title"] = "Unknown Position"
            
            # Ensure we have a company
            if not job_details.get("company"):
                job_details["company"] = "Unknown Company"
            
            # Ensure we have a location
            if not job_details.get("location"):
                job_details["location"] = "Location Not Specified"
            
            # Ensure we have a description
            if not job_details.get("description"):
                job_details["description"] = "No description available"
            
            # Create log message
            title = job_details.get("title", "Unknown Position")
            company = job_details.get("company", "Unknown Company")
            log_msg = f"Extracted job details: {title} at {company}"
            logger.info(log_msg)
            
            # End job details extraction stage if diagnostics manager is available
            if diagnostics_manager:
                diagnostics_manager.end_stage(success=True, details=job_details)
            
            return job_details
            
        except Exception as e:
            error_msg = f"Error extracting job details: {e}"
            logger.error(error_msg)
            
            # End job details extraction stage with error if diagnostics manager is available
            if diagnostics_manager:
                diagnostics_manager.end_stage(success=False, error=str(e))
            
            return {
                "title": "Unknown Position",
                "company": "Unknown Company",
                "location": "Location Not Specified",
                "description": "Failed to extract job details"
            }

    def analyze_form_html(self, form_html: str, page_url: str = None) -> Dict[str, Any]:
        """Analyze the HTML of a form to extract its structure.
        
        Args:
            form_html: HTML content of the form
            page_url: URL of the page containing the form
            
        Returns:
            Dict containing the form structure
        """
        # Add enhanced checks for dropdown fields
        enhanced_form_html = self._enhance_form_html_analysis(form_html)
        
        # Run analysis based on enhanced HTML
        form_structure = self._extract_form_structure(enhanced_form_html, page_url)
        
        return form_structure
    
    def _enhance_form_html_analysis(self, form_html: str) -> str:
        """Enhance the form HTML to better detect dropdowns and field types.
        
        Args:
            form_html: Original form HTML
            
        Returns:
            Enhanced form HTML with additional analysis attributes
        """
        # Find potential dropdown indicators that might not be standard <select> elements
        dropdown_indicators = [
            r'class="[^"]*dropdown[^"]*"',
            r'class="[^"]*select[^"]*"',
            r'class="[^"]*combo[^"]*"',
            r'role="combobox"',
            r'role="listbox"',
            r'aria-haspopup="listbox"',
            r'<div[^>]*dropdown[^>]*>',
            r'<ul[^>]*dropdown-menu[^>]*>',
            r'<div[^>]*select-container[^>]*>'
        ]
        
        # Add data-field-type attributes to help classify fields
        enriched_html = form_html
        
        # Mark potential dropdown elements
        for pattern in dropdown_indicators:
            enriched_html = re.sub(
                pattern,
                lambda m: m.group(0) + ' data-field-type="select"',
                enriched_html
            )
        
        # Identify common education and location fields which are typically dropdowns
        education_field_patterns = [
            r'<[^>]*\bid="[^"]*school[^"]*"',
            r'<[^>]*\bid="[^"]*degree[^"]*"',
            r'<[^>]*\bid="[^"]*education[^"]*"',
            r'<[^>]*\bid="[^"]*discipline[^"]*"',
            r'<[^>]*\bid="[^"]*major[^"]*"',
            r'<[^>]*\bid="[^"]*university[^"]*"',
            r'<[^>]*\bid="[^"]*college[^"]*"',
            r'<[^>]*\bname="[^"]*school[^"]*"',
            r'<[^>]*\bname="[^"]*degree[^"]*"',
            r'<[^>]*\bname="[^"]*education[^"]*"',
            r'<[^>]*\bname="[^"]*discipline[^"]*"',
            r'<[^>]*\bname="[^"]*major[^"]*"',
            r'<[^>]*\bname="[^"]*university[^"]*"',
            r'<[^>]*\bname="[^"]*college[^"]*"'
        ]
        
        # Mark education fields
        for pattern in education_field_patterns:
            enriched_html = re.sub(
                pattern,
                lambda m: m.group(0) + ' data-likely-dropdown="true" data-field-category="education"',
                enriched_html
            )
        
        # Location field patterns
        location_field_patterns = [
            r'<[^>]*\bid="[^"]*location[^"]*"',
            r'<[^>]*\bid="[^"]*country[^"]*"',
            r'<[^>]*\bid="[^"]*state[^"]*"',
            r'<[^>]*\bid="[^"]*city[^"]*"',
            r'<[^>]*\bname="[^"]*location[^"]*"',
            r'<[^>]*\bname="[^"]*country[^"]*"',
            r'<[^>]*\bname="[^"]*state[^"]*"',
            r'<[^>]*\bname="[^"]*city[^"]*"'
        ]
        
        # Mark location fields
        for pattern in location_field_patterns:
            enriched_html = re.sub(
                pattern,
                lambda m: m.group(0) + ' data-likely-dropdown="true" data-field-category="location"',
                enriched_html
            )
        
        # Add more data for dropdown options analysis
        # Look for lists that might be dropdown options
        option_patterns = [
            r'(<ul[^>]*>.*?<\/ul>)',
            r'(<div[^>]*dropdown-items[^>]*>.*?<\/div>)',
            r'(<div[^>]*dropdown-menu[^>]*>.*?<\/div>)'
        ]
        
        for pattern in option_patterns:
            enriched_html = re.sub(
                pattern,
                lambda m: m.group(0).replace('>', ' data-option-container="true">'),
                enriched_html,
                flags=re.DOTALL
            )
            
        return enriched_html
    
    def _extract_form_structure(self, form_html: str, page_url: Optional[str] = None) -> Dict[str, Any]:
        """Extract the form structure from the enhanced HTML.
        
        Args:
            form_html: Enhanced form HTML
            page_url: URL of the page containing the form
            
        Returns:
            Dict containing the form structure
        """
        # Placeholder for the extracted structure
        form_structure = {
            "form_elements": [],
            "form_structure": {
                "sections": []
            },
            "element_tags": {},
            "validation_rules": {},
            "html_structure": {},
            "field_analysis": {
                "total_fields": 0,
                "required_fields": 0,
                "field_types": {},
                "frame_distribution": {}
            },
            "dropdown_analysis": {
                "detected_dropdowns": [],
                "detection_methods": {}
            },
            "strategic_insights": []
        }
        
        # Extract form elements
        input_pattern = r'<(input|select|textarea)[^>]*\bid="([^"]*)"[^>]*>'
        for match in re.finditer(input_pattern, form_html, re.DOTALL):
            tag = match.group(1)
            field_id = match.group(2)
            
            # Store element tag info
            form_structure["element_tags"][field_id] = tag
            
            # Store the HTML structure for the field
            element_html = match.group(0)
            form_structure["html_structure"][field_id] = element_html
            
            # Determine field type
            field_type = "text"  # Default
            if tag == "select":
                field_type = "select"
            elif tag == "textarea":
                field_type = "textarea"
            elif "type=" in element_html:
                type_match = re.search(r'type="([^"]*)"', element_html)
                if type_match:
                    input_type = type_match.group(1)
                    if input_type == "file":
                        field_type = "file"
                    elif input_type in ["checkbox", "radio"]:
                        field_type = "checkbox"
            
            # Check for dropdown indicators in data attributes
            if "data-field-type=\"select\"" in element_html or "data-likely-dropdown=\"true\"" in element_html:
                field_type = "select"
                form_structure["dropdown_analysis"]["detected_dropdowns"].append(field_id)
                form_structure["dropdown_analysis"]["detection_methods"][field_id] = "custom_attributes"
            
            # Extract options for dropdowns
            options = []
            if field_type == "select":
                # For standard selects
                option_pattern = r'<option[^>]*value="([^"]*)"[^>]*>(.*?)<\/option>'
                for option_match in re.finditer(option_pattern, form_html, re.DOTALL):
                    option_value = option_match.group(1)
                    option_text = option_match.group(2).strip()
                    options.append(option_text)
                
                # For custom dropdowns, try to find nearby lists
                if not options:
                    field_id_pattern = re.escape(field_id)
                    list_item_pattern = r'id="' + field_id_pattern + r'"[^>]*>.*?(<ul[^>]*>.*?<\/ul>)'
                    list_match = re.search(list_item_pattern, form_html, re.DOTALL)
                    if list_match:
                        list_html = list_match.group(1)
                        item_pattern = r'<li[^>]*>(.*?)<\/li>'
                        for item_match in re.finditer(item_pattern, list_html, re.DOTALL):
                            item_text = item_match.group(1).strip()
                            # Remove HTML tags
                            item_text = re.sub(r'<[^>]*>', '', item_text).strip()
                            options.append(item_text)
            
            # Add to form elements
            form_element = {
                "id": field_id,
                "type": field_type,
                "selector": f"#{field_id}"
            }
            
            # Add options if found
            if options:
                form_element["options"] = options
            
            # Check if required
            is_required = "required" in element_html.lower() or "aria-required=\"true\"" in element_html.lower()
            if is_required:
                form_element["required"] = True
                form_structure["field_analysis"]["required_fields"] += 1
            
            form_structure["form_elements"].append(form_element)
            
            # Update field type counts
            if field_type not in form_structure["field_analysis"]["field_types"]:
                form_structure["field_analysis"]["field_types"][field_type] = 0
            form_structure["field_analysis"]["field_types"][field_type] += 1
        
        # Update total fields count
        form_structure["field_analysis"]["total_fields"] = len(form_structure["form_elements"])
        
        # Add strategic insights
        if form_structure["field_analysis"]["total_fields"] > 20:
            form_structure["strategic_insights"].append(
                f"Complex form with {form_structure['field_analysis']['total_fields']} fields - consider breaking into logical chunks"
            )
        
        if form_structure["dropdown_analysis"]["detected_dropdowns"]:
            form_structure["strategic_insights"].append(
                f"Form contains {len(form_structure['dropdown_analysis']['detected_dropdowns'])} dropdown fields - use smart matching"
            )
        
        return form_structure 