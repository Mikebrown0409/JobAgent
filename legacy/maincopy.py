import os
import json
import argparse
import asyncio
import logging
from typing import Dict, Any, List, Optional
import re
import uuid
import time
import difflib # Import difflib for fuzzy matching
from crewai import Agent, Task, Crew
from playwright.async_api import async_playwright, Page, Locator, Frame

# Logging setup
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Extractor: Structured Form Data Extraction
async def extract_form_data(job_url: str) -> Dict[str, Any]:
    """Extracts all relevant form elements from the job URL using Playwright."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        page.set_default_timeout(20000)

        logger.info(f"Navigating to {job_url}...")
        await page.goto(job_url, wait_until="networkidle", timeout=120000)
        final_url = page.url
        await page.wait_for_timeout(3000)

        form_elements = []
        processed_selectors = set()
        processed_element_identifiers = set() # Store unique IDs/Names of elements found in IFRAMES

        # --- REVISED FRAME HANDLING (AGAIN) ---
        # Identify all contexts (page + frames with URLs/Names) first
        contexts_to_process_info = [("main", page)] # Start with main page

        logger.debug(f"Identifying frames...")
        all_frames = page.frames
        for frame in all_frames:
            frame_url = frame.url
            frame_name = frame.name
            js_evaluated_url = None

            if not frame_url or frame_url == 'about:blank':
                try:
                    js_evaluated_url = await frame.evaluate("() => window.location.href")
                    if js_evaluated_url and js_evaluated_url != 'about:blank':
                        frame_url = js_evaluated_url
                        logger.debug(f"Frame URL resolved via JS: '{frame_url}'")
                    else:
                        # Keep original 'about:blank' or empty if JS fails
                        pass
                except Exception as js_eval_e:
                    logger.warning(f"Failed to evaluate window.location.href in frame: {js_eval_e}")

            # Use the resolved URL or name to get the identifier
            identifier = get_frame_identifier({"url": frame_url, "name": frame_name})
            if identifier != "main": # Only add identifiable frames
                 contexts_to_process_info.append((identifier, frame))
            elif frame_url or frame_name: # Log frames that defaulted to main
                 logger.debug(f"Frame with URL='{frame_url}', Name='{frame_name}' defaulted to 'main' identifier.")
            # else: skip frames with no url/name and failed JS eval

        logger.info(f"Processing {len(contexts_to_process_info)} contexts (page + identifiable frames).")

        # Separate main page and iframe contexts
        main_context_info = None
        iframe_context_infos = []
        for identifier, context in contexts_to_process_info:
            if identifier == "main":
                main_context_info = (identifier, context)
            else:
                iframe_context_infos.append((identifier, context))

        # ---> PROCESS IFRAMES FIRST <---
        for context_identifier_str, context_obj in iframe_context_infos:
            logger.debug(f"Extracting from IFRAME context: ID='{context_identifier_str}'")
            # Define the frame_info specific TO THIS context
            current_frame_info = {"url": context_obj.url, "name": context_obj.name}
            # Ensure the identifier URL is used if it's the primary identifier
            if context_identifier_str.startswith("http") and current_frame_info["url"] != context_identifier_str:
                 logger.debug(f"Updating frame_info url from '{current_frame_info['url']}' to identifier '{context_identifier_str}'")
                 current_frame_info["url"] = context_identifier_str

            try:
                logger.debug(f"Waiting for load state 'networkidle' in frame: {context_identifier_str}")
                await context_obj.wait_for_load_state('networkidle', timeout=25000)
                logger.debug(f"Frame load state 'networkidle' reached for: {context_identifier_str}")
                await context_obj.wait_for_timeout(2000)
            except Exception as frame_load_e:
                logger.warning(f"Timeout or error waiting for frame load state in {context_identifier_str}: {frame_load_e}")


            # Define roles and selectors to query *within this context_obj*
            roles_to_get = ["textbox", "textarea", "checkbox", "radio", "button", "combobox"]
            tag_locators = ["select", "input[type='file']"]

            elements_in_context = [] # Collect all locators found in this specific context

            for role in roles_to_get:
                try:
                    # Find elements BY ROLE *within this context_obj*
                    elements = await context_obj.get_by_role(role).all()
                    logger.debug(f"[{context_identifier_str}] Found {len(elements)} elements with role='{role}'")
                    elements_in_context.extend(elements)
                except Exception as role_e:
                    logger.warning(f"[{context_identifier_str}] Error getting elements by role '{role}': {role_e}")

            for tag_selector in tag_locators:
                 try:
                     # Find elements BY SELECTOR *within this context_obj*
                     elements = await context_obj.locator(tag_selector).all(timeout=10000)
                     logger.debug(f"[{context_identifier_str}] Found {len(elements)} matching selector '{tag_selector}'")
                     elements_in_context.extend(elements)
                 except Exception as tag_e:
                      if "Timeout" not in str(tag_e):
                          logger.warning(f"[{context_identifier_str}] Error getting elements by selector '{tag_selector}': {tag_e}")

            logger.debug(f"[{context_identifier_str}] Total elements found in this iframe context: {len(elements_in_context)}")
            await asyncio.sleep(0.1) # Small pause

            # Process elements found ONLY in this iframe context
            for elem in elements_in_context:
                label = "N/A" # Default label for logging
                selector = "N/A" # Default selector for logging
                try:
                    # ---> Fetch attributes using the same JS evaluation <---
                    attributes = await elem.evaluate("""el => {
                        const tagName = el.tagName.toLowerCase();
                        const typeAttr = (el.getAttribute('type') || '').toLowerCase();
                        const roleAttr = (el.getAttribute('role') || '').toLowerCase();
                        let elementType = 'unknown';

                        // Determine type based on tag, type attribute, and role
                        if (tagName === 'select') {
                            elementType = 'select';
                        } else if (tagName === 'textarea') {
                            elementType = 'textarea';
                        } else if (tagName === 'button' || roleAttr === 'button') {
                            elementType = 'button';
                        } else if (tagName === 'input') {
                            if (['radio', 'checkbox', 'file', 'submit', 'button', 'reset', 'image'].includes(typeAttr)) {
                                elementType = typeAttr;
                            } else if (roleAttr === 'combobox') { // Input acting as combobox trigger
                                elementType = 'combobox';
                            } else {
                                // Default input types (text, email, tel, etc.)
                                elementType = 'text'; 
                            }
                        } else if (roleAttr === 'combobox') { // Non-input elements acting as combobox
                            elementType = 'combobox';
                        } else if (roleAttr === 'radio') {
                             elementType = 'radio'; // e.g., a div styled as a radio button
                        } else if (roleAttr === 'checkbox') {
                             elementType = 'checkbox'; // e.g., a div styled as a checkbox
                        } else if (el.isContentEditable) {
                             elementType = 'textarea'; // Treat contenteditable divs like textareas
                        }
                        // Add more specific checks if needed for custom components

                        // Extract other attributes
                        return {
                            id: el.id,
                            name: el.name,
                            detected_type: elementType, // Use the detected type
                            tagName: tagName,
                            type_attr: typeAttr, // Keep original type attribute if needed
                            role_attr: roleAttr, // Keep original role attribute
                            'data-testid': el.getAttribute('data-testid'),
                            'aria-label': el.getAttribute('aria-label'),
                            placeholder: el.getAttribute('placeholder'),
                            required: el.required || el.getAttribute('aria-required') === 'true',
                            // Improved label finding
                            label_for: document.querySelector(`label[for="${el.id}"]`)?.textContent.trim(),
                            label_closest: el.closest('label')?.textContent.trim(),
                            label_aria: el.getAttribute('aria-labelledby') ? document.getElementById(el.getAttribute('aria-labelledby'))?.textContent.trim() : null,
                            options: tagName === 'select' ? Array.from(el.options || []).map(o => o.text.trim()) : [],
                            value: el.value,
                            text_content: el.textContent.trim()
                        };
                    }""")

                    elem_id = attributes.get('id')
                    elem_name = attributes.get('name')
                    elem_type = attributes.get('detected_type', 'unknown')
                    elem_tag = attributes.get('tagName')
                    # ---> FIX: Define variables here <---
                    elem_testid = attributes.get('data-testid')
                    elem_aria_label = attributes.get('aria-label')
                    elem_placeholder = attributes.get('placeholder')
                    elem_text = attributes.get('text_content')
                    # ---> END FIX <---

                    # Skip unknown types for now, unless they are buttons found by text
                    if elem_type == 'unknown' and not (elem_tag == 'button' and elem_text):
                         continue

                    # ---> Generate unique identifier for the element itself (prioritize ID, then Name) <---
                    element_unique_id = None
                    if elem_id:
                        element_unique_id = f"id::{elem_id}"
                    elif elem_name and elem_type != 'radio': # Name less reliable for radios
                        element_unique_id = f"name::{elem_name}"
                        # Consider adding value for radios: f"name_value::{elem_name}::{attributes.get('value')}"

                    # ---> Generate selector using the context_obj <---
                    selector = None
                    if elem_id:
                        potential_selector = f"#{elem_id}"
                        count = await context_obj.locator(potential_selector).count() # Use context_obj
                        if count == 1: selector = potential_selector
                    if not selector and elem_name and elem_type != 'radio':
                         potential_selector = f"{elem_tag}[name=\"{elem_name}\"]"
                         count = await context_obj.locator(potential_selector).count()
                         if count == 1: selector = potential_selector
                    if not selector and elem_testid:
                        potential_selector = f"{elem_tag}[data-testid=\"{elem_testid}\"]"
                        count = await context_obj.locator(potential_selector).count()
                        if count == 1: selector = potential_selector

                    # Try placeholder for text-like inputs
                    if not selector and elem_placeholder and elem_type in ['text', 'textarea', 'combobox']:
                        potential_selector = f"{elem_tag}[placeholder=\"{elem_placeholder}\"]"
                        count = await context_obj.locator(potential_selector).count()
                        if count == 1: selector = potential_selector
                    
                    # Try aria-label
                    if not selector and elem_aria_label:
                         potential_selector = f"{elem_tag}[aria-label=\"{elem_aria_label}\"]"
                         count = await context_obj.locator(potential_selector).count()
                         if count == 1: selector = potential_selector

                    # Try text content for buttons
                    if not selector and elem_text and elem_type == 'button':
                         # Be careful with quotes in text
                         escaped_text = elem_text.replace('"', '\\"')
                         potential_selector = f"{elem_tag}:has-text(\"{escaped_text}\")" 
                         count = await context_obj.locator(potential_selector).count()
                         if count == 1: selector = potential_selector
                    
                    # Specific fallback for radio buttons by value if name is known
                    if not selector and elem_type == 'radio' and elem_name and attributes.get('value'):
                         val = attributes['value'].replace('"', '\\"')
                         potential_selector = f"input[type='radio'][name=\"{elem_name}\"][value=\"{val}\"]"
                         count = await context_obj.locator(potential_selector).count()
                         if count == 1: selector = potential_selector

                    if not selector:
                        # logger.debug(f"[{context_identifier_str}] Could not generate unique selector for element...")
                        continue

                    # Check selector uniqueness *within this frame context*
                    full_selector_id = f"{context_identifier_str}::{selector}"
                    if full_selector_id in processed_selectors:
                        # logger.debug(f"Skipping duplicate selector within frame: {full_selector_id}")
                        continue
                    processed_selectors.add(full_selector_id)

                    label = attributes.get('label_for') or attributes.get('label_aria') or attributes.get('aria-label') or attributes.get('label_closest') or attributes.get('placeholder') or attributes.get('text_content') or "Unlabeled"
                    is_visible = True # Keep assuming visible for now

                    # *** CRITICAL: Assign the frame_info OF THE CURRENT IFRAME CONTEXT ***
                    assigned_frame_identifier = get_frame_identifier(current_frame_info)
                    logger.debug(f"Found IFRAME Element: Label='{label}', Selector='{selector}', Type='{elem_type}'. ASSIGNED IDENTIFIER: '{assigned_frame_identifier}' (Context: {context_identifier_str})")

                    form_elements.append({
                        "label": label.strip(),
                        "selector": selector,
                        "type": elem_type,
                        "name": elem_name,
                        "id": elem_id,
                        "required": attributes.get('required', False),
                        "options": attributes.get('options', []),
                        "value": attributes.get('value'),
                        # *** Use the correct frame info for this context ***
                        "frame_info": current_frame_info,
                        "is_visible": is_visible
                    })

                    # ---> Store the unique identifier of this processed iframe element <---
                    if element_unique_id:
                        processed_element_identifiers.add(element_unique_id)
                        logger.debug(f"Stored iframe element identifier: {element_unique_id}")

                except Exception as e:
                    logger.error(f"ERROR processing IFRAME element details in {context_identifier_str}. Label='{label}', Selector='{selector}'. Error: {e}", exc_info=True)

        # ---> PROCESS MAIN PAGE LAST <---
        if main_context_info:
            context_identifier_str, context_obj = main_context_info
            logger.debug(f"Extracting from MAIN context: ID='{context_identifier_str}'")
            current_frame_info = {"url": "main", "name": "main"}

            # Define roles and selectors to query *within this context_obj*
            roles_to_get = ["textbox", "textarea", "checkbox", "radio", "button", "combobox"]
            tag_locators = ["select", "input[type='file']"]
            elements_in_context = []

            for role in roles_to_get:
                try:
                    elements = await context_obj.get_by_role(role).all()
                    logger.debug(f"[{context_identifier_str}] Found {len(elements)} elements with role='{role}'")
                    elements_in_context.extend(elements)
                except Exception as role_e:
                    logger.warning(f"[{context_identifier_str}] Error getting elements by role '{role}': {role_e}")

            for tag_selector in tag_locators:
                 try:
                     elements = await context_obj.locator(tag_selector).all(timeout=5000) # Shorter timeout for main?
                     logger.debug(f"[{context_identifier_str}] Found {len(elements)} matching selector '{tag_selector}'")
                     elements_in_context.extend(elements)
                 except Exception as tag_e:
                      if "Timeout" not in str(tag_e):
                           logger.warning(f"[{context_identifier_str}] Error getting elements by selector '{tag_selector}': {tag_e}")

            logger.debug(f"[{context_identifier_str}] Total elements found in this main context: {len(elements_in_context)}")
            await asyncio.sleep(0.1)

            # Process elements found ONLY in this main context
            for elem in elements_in_context:
                label = "N/A"
                selector = "N/A"
                try:
                    attributes = await elem.evaluate("""el => {
                        const tagName = el.tagName.toLowerCase();
                        const typeAttr = (el.getAttribute('type') || '').toLowerCase();
                        const roleAttr = (el.getAttribute('role') || '').toLowerCase();
                        let elementType = 'unknown';

                        // Determine type based on tag, type attribute, and role
                        if (tagName === 'select') {
                            elementType = 'select';
                        } else if (tagName === 'textarea') {
                            elementType = 'textarea';
                        } else if (tagName === 'button' || roleAttr === 'button') {
                            elementType = 'button';
                        } else if (tagName === 'input') {
                            if (['radio', 'checkbox', 'file', 'submit', 'button', 'reset', 'image'].includes(typeAttr)) {
                                elementType = typeAttr;
                            } else if (roleAttr === 'combobox') { // Input acting as combobox trigger
                                elementType = 'combobox';
                            } else {
                                // Default input types (text, email, tel, etc.)
                                elementType = 'text'; 
                            }
                        } else if (roleAttr === 'combobox') { // Non-input elements acting as combobox
                            elementType = 'combobox';
                        } else if (roleAttr === 'radio') {
                             elementType = 'radio'; // e.g., a div styled as a radio button
                        } else if (roleAttr === 'checkbox') {
                             elementType = 'checkbox'; // e.g., a div styled as a checkbox
                        } else if (el.isContentEditable) {
                             elementType = 'textarea'; // Treat contenteditable divs like textareas
                        }
                        // Add more specific checks if needed for custom components

                        // Extract other attributes
                        return {
                            id: el.id,
                            name: el.name,
                            detected_type: elementType, // Use the detected type
                            tagName: tagName,
                            type_attr: typeAttr, // Keep original type attribute if needed
                            role_attr: roleAttr, // Keep original role attribute
                            'data-testid': el.getAttribute('data-testid'),
                            'aria-label': el.getAttribute('aria-label'),
                            placeholder: el.getAttribute('placeholder'),
                            required: el.required || el.getAttribute('aria-required') === 'true',
                            // Improved label finding
                            label_for: document.querySelector(`label[for="${el.id}"]`)?.textContent.trim(),
                            label_closest: el.closest('label')?.textContent.trim(),
                            label_aria: el.getAttribute('aria-labelledby') ? document.getElementById(el.getAttribute('aria-labelledby'))?.textContent.trim() : null,
                            options: tagName === 'select' ? Array.from(el.options || []).map(o => o.text.trim()) : [],
                            value: el.value,
                            text_content: el.textContent.trim()
                        };
                    }""")

                    elem_id = attributes.get('id')
                    elem_name = attributes.get('name')
                    elem_type = attributes.get('detected_type', 'unknown')
                    elem_tag = attributes.get('tagName')
                    # ---> FIX: Define variables here <---
                    elem_testid = attributes.get('data-testid')
                    elem_aria_label = attributes.get('aria-label')
                    elem_placeholder = attributes.get('placeholder')
                    elem_text = attributes.get('text_content')
                    # ---> END FIX <---

                    if elem_type == 'unknown' and not (elem_tag == 'button' and elem_text):
                         continue

                    # ---> Generate unique identifier for the element itself <---
                    element_unique_id = None
                    if elem_id:
                        element_unique_id = f"id::{elem_id}"
                    elif elem_name and elem_type != 'radio':
                        element_unique_id = f"name::{elem_name}"
                        # Consider adding value for radios: f"name_value::{elem_name}::{attributes.get('value')}"

                    # ---> Generate selector using the context_obj <---
                    selector = None
                    if elem_id:
                        potential_selector = f"#{elem_id}"
                        count = await context_obj.locator(potential_selector).count() # Use context_obj
                        if count == 1: selector = potential_selector
                    if not selector and elem_name and elem_type != 'radio':
                         potential_selector = f"{elem_tag}[name=\"{elem_name}\"]"
                         count = await context_obj.locator(potential_selector).count()
                         if count == 1: selector = potential_selector
                    if not selector and elem_testid:
                        potential_selector = f"{elem_tag}[data-testid=\"{elem_testid}\"]"
                        count = await context_obj.locator(potential_selector).count()
                        if count == 1: selector = potential_selector

                    # Try placeholder for text-like inputs
                    if not selector and elem_placeholder and elem_type in ['text', 'textarea', 'combobox']:
                        potential_selector = f"{elem_tag}[placeholder=\"{elem_placeholder}\"]"
                        count = await context_obj.locator(potential_selector).count()
                        if count == 1: selector = potential_selector
                    
                    # Try aria-label
                    if not selector and elem_aria_label:
                         potential_selector = f"{elem_tag}[aria-label=\"{elem_aria_label}\"]"
                         count = await context_obj.locator(potential_selector).count()
                         if count == 1: selector = potential_selector

                    # Try text content for buttons
                    if not selector and elem_text and elem_type == 'button':
                         # Be careful with quotes in text
                         escaped_text = elem_text.replace('"', '\\"')
                         potential_selector = f"{elem_tag}:has-text(\"{escaped_text}\")" 
                         count = await context_obj.locator(potential_selector).count()
                         if count == 1: selector = potential_selector
                    
                    # Specific fallback for radio buttons by value if name is known
                    if not selector and elem_type == 'radio' and elem_name and attributes.get('value'):
                         val = attributes['value'].replace('"', '\\"')
                         potential_selector = f"input[type='radio'][name=\"{elem_name}\"][value=\"{val}\"]"
                         count = await context_obj.locator(potential_selector).count()
                         if count == 1: selector = potential_selector

                    if not selector:
                        continue

                    # ---> REVISED CHECK IF ALREADY PROCESSED IN AN IFRAME <---
                    already_processed = False
                    if element_unique_id and element_unique_id in processed_element_identifiers:
                        # If ID/Name match found in iframe elements, mark as processed
                        already_processed = True
                        logger.debug(f"Skipping MAIN context element via ID/Name (Already found in iframe): ID/Name='{element_unique_id}' Selector='{selector}'")
                    elif not element_unique_id:
                         # Fallback check for elements without ID/Name: Check by SELECTOR against iframe elements
                         # Iterate through elements already added (which are iframe elements at this point)
                         for existing_elem in form_elements:
                              # Check if selector matches AND the existing element is from an iframe
                              if existing_elem.get("selector") == selector and get_frame_identifier(existing_elem.get("frame_info", {})) != "main":
                                   already_processed = True
                                   logger.debug(f"Skipping MAIN context element via Selector fallback (Already found in iframe): Selector='{selector}'")
                                   break # Found a match, no need to check further

                    if already_processed:
                         continue # Skip this element if it was found via ID/Name or Selector fallback
                    # ---> END REVISED CHECK <---

                    # Check selector uniqueness *within this frame context* (main)
                    full_selector_id = f"{context_identifier_str}::{selector}"
                    if full_selector_id in processed_selectors:
                        # logger.debug(f"Skipping duplicate selector within frame: {full_selector_id}")
                        continue
                    processed_selectors.add(full_selector_id)

                    label = attributes.get('label_for') or attributes.get('label_aria') or attributes.get('aria-label') or attributes.get('label_closest') or attributes.get('placeholder') or attributes.get('text_content') or "Unlabeled"
                    is_visible = True

                    # *** Assign the frame_info OF THE MAIN CONTEXT ***
                    logger.debug(f"Found MAIN Element: Label='{label}', Selector='{selector}', Type='{elem_type}'. ASSIGNED IDENTIFIER: 'main' (Context: {context_identifier_str})")

                    form_elements.append({
                        "label": label.strip(),
                        "selector": selector,
                        "type": elem_type,
                        "name": elem_name,
                        "id": elem_id,
                        "required": attributes.get('required', False),
                        "options": attributes.get('options', []),
                        "value": attributes.get('value'),
                        # *** Use the correct frame info for this context ***
                        "frame_info": current_frame_info,
                        "is_visible": is_visible
                    })
                except Exception as e:
                    logger.error(f"ERROR processing MAIN element details in {context_identifier_str}. Label='{label}', Selector='{selector}'. Error: {e}", exc_info=True)

        # --- END REVISED FRAME HANDLING ---

        # Keep screenshot logic
        screenshot = f"extract_{uuid.uuid4().hex[:8]}.png"
        try:
            await page.screenshot(path=screenshot, full_page=True)
        except Exception:
             await page.screenshot(path=screenshot)

        await browser.close()

        logger.info(f"Extracted {len(form_elements)} potentially actionable form elements from {final_url}")
        # Save extracted data for debugging
        with open(f"extracted_elements_{uuid.uuid4().hex[:8]}.json", "w") as f:
            json.dump({"final_url": final_url, "form_elements": form_elements}, f, indent=2)
            
        return {"final_url": final_url, "form_elements": form_elements, "screenshot": screenshot}

# Mapper: AI Agent for Action Planning
def create_mapper_agent() -> Agent:
    """Creates an AI agent for mapping profile data to form fields."""
    if not os.environ.get("TOGETHERAI_API_KEY"):
        raise ValueError("TOGETHERAI_API_KEY not set")
    return Agent(
        role="Form Data Mapper",
        goal="Accurately map user profile data to structured form fields and plan actions.",
        backstory="An expert at interpreting form fields and user profiles, crafting precise action plans.",
        llm="together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
        verbose=True,
        max_iter=1
    )

# Helper function to get the best frame identifier string
def get_frame_identifier(frame_info: Dict[str, str]) -> str:
    url = frame_info.get("url")
    if url and (url.startswith("http://") or url.startswith("https://")):
        return url
    else:
        if url or frame_info.get("name"):
             logger.debug(f"Frame info {frame_info} lacks http(s) URL, defaulting identifier to 'main'.")
        return "main"

# ---> NEW: Helper to group elements by frame identifier <---
def group_elements_by_frame(elements: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped = {"main": []}
    for elem in elements:
        frame_id = get_frame_identifier(elem.get("frame_info", {}))
        # Clean the element dict for the LLM - remove frame_info
        elem_copy = elem.copy()
        elem_copy.pop("frame_info", None) 
        if frame_id == "main":
            grouped["main"].append(elem_copy)
        else:
            if frame_id not in grouped:
                grouped[frame_id] = []
            grouped[frame_id].append(elem_copy)
    # Remove empty groups
    return {k: v for k, v in grouped.items() if v}
# ---> END NEW <---

def create_basic_fields_task(agent: Agent, form_data: Dict[str, Any], profile: Dict[str, Any]) -> Task:
    """Task for mapping basic fields (name, email, phone)."""
    # Filter relevant fields first
    relevant_elements = [
        f for f in form_data["form_elements"] 
        if f["type"] in ["text", "email", "tel"] and (f["id"] is None or "question" not in f["id"])
    ]
    # ---> FIX: Group elements by frame <---
    grouped_elements = group_elements_by_frame(relevant_elements)
    grouped_elements_str = json.dumps(grouped_elements, indent=2)
    logger.debug(f"Data for Basic Fields Task (Grouped): {grouped_elements_str}")
    # ---> END FIX <---

    profile_str = json.dumps(profile["personal"], indent=2)
    field_mappings = {"first name": "first_name", "last name": "last_name", "email": "email", "phone": "phone_number"}

    return Task(
        description=f"""
        **Objective:** Map basic profile fields to form elements provided below, grouped by their frame.
        
        **Form Elements (Grouped by Frame Identifier):** 
        ```json
        {grouped_elements_str}
        ```

        **Profile:** {profile_str}
        **Mappings:** {json.dumps(field_mappings)}

        **FRAME IDENTIFIER RULES (EXTREMELY IMPORTANT):**
        - The keys in the "Form Elements" JSON above ("main" or a URL) are the only valid `frame_identifier` values.
        - In your output JSON action, you MUST use the EXACT `frame_identifier` key associated with the element's group.
        - **DO NOT** create or invent descriptive frame names. **ONLY USE** the provided URL string or the string "main".

        **SELECTOR RULES (EXTREMELY IMPORTANT):**
        - For the `"selector"` field in your output JSON action, you MUST use the EXACT string value provided in the `"selector"` key for the corresponding element in the input "Form Elements" JSON.
        - **DO NOT** use the element's `label`, `name`, or `id` as the selector unless it is the exact value provided in the `"selector"` key.

        **Instructions:**
        - For each element in the groups above, match profile data using the mappings.
        - Output a JSON list of actions. Each action MUST include the correct `frame_identifier` (the key from the group the element was in) AND the correct `selector` (the value from the element's `"selector"` key).
        - Action Format: {{"action_type": "fill", "selector": "<exact_selector_from_input>", "value": "<val>", "label": "<lbl>", "frame_identifier": "<url_or_main>"}}
        
        **Output:** JSON list of fill actions.
        """,
        expected_output="A JSON list of fill actions for basic fields, using only 'main' or a URL as the frame_identifier and the exact selector provided in the input.",
        agent=agent
    )

def create_uploads_task(agent: Agent, form_data: Dict[str, Any], profile: Dict[str, Any]) -> Task:
    """Task for handling file uploads (resume, cover letter)."""
    relevant_elements = [f for f in form_data["form_elements"] if f["type"] == "file"]
    # ---> FIX: Group elements by frame <---
    grouped_elements = group_elements_by_frame(relevant_elements)
    grouped_elements_str = json.dumps(grouped_elements, indent=2)
    logger.debug(f"Data for Uploads Task (Grouped): {grouped_elements_str}")
    # ---> END FIX <---
    profile_str = json.dumps(profile["documents"], indent=2)
    resume_path = profile.get("resume_path", "N/A")

    return Task(
        description=f"""
        **Objective:** Plan file uploads for form elements provided below, grouped by their frame.

        **Available File Input Elements (Grouped by Frame Identifier):** 
        ```json
        {grouped_elements_str}
        ```

        **User Profile Documents:** {profile_str}
        **Resume Path on Disk:** {resume_path}

        **FRAME IDENTIFIER RULES (EXTREMELY IMPORTANT):** 
        - The keys in the "Available File Input Elements" JSON ("main" or a URL) are the only valid `frame_identifier` values.
        - In your output JSON action, you MUST use the EXACT `frame_identifier` key associated with the element's group.
        - **DO NOT** create or invent descriptive frame names. **ONLY USE** the provided URL string or the string "main".

        **VERY IMPORTANT Instructions:**
        1. Identify the file input element for 'Resume/CV' from the groups above.
        2. If cover letter needed, plan for that too.
        3. **YOU MUST use the exact 'selector' AND the correct `frame_identifier` (the key from the group the element was in).**
        4. Format the output as a JSON list of actions.

        **Output Action Format:**
        ```json
        [
          {{"action_type": "upload", "selector": "<selector_from_data>", "value": "<path_to_file>", "label": "<label_from_data>", "frame_identifier": "<url_or_main>"}}
        ]
        ```
        **Output:** A JSON list containing upload actions, using the correct frame_identifier.
        """,
        expected_output="A JSON list of upload actions, ensuring the correct frame_identifier (URL or 'main') is used.",
        agent=agent
    )

def create_custom_questions_task(agent: Agent, form_data: Dict[str, Any], profile: Dict[str, Any]) -> Task:
    """Task for handling custom questions (location, work auth, dropdowns, demographics, etc.)."""
    relevant_elements = []
    for f in form_data["form_elements"]:
        if (f["type"] in ["textarea", "select", "combobox", "radio", "checkbox"]
            or (f["id"] and "question" in f["id"]) 
            or "location" in f["label"].lower()
            or any(keyword in f["label"].lower() for keyword in ['gender', 'race', 'ethnicity', 'veteran', 'disability'])):
            relevant_elements.append(f)
            
    # ---> FIX: Group elements by frame <---
    grouped_elements = group_elements_by_frame(relevant_elements)
    grouped_elements_str = json.dumps(grouped_elements, indent=2)
    logger.debug(f"Data for Custom Questions Task (Grouped): {grouped_elements_str}")
    # ---> END FIX <---
    profile_str = json.dumps({k: profile[k] for k in ["location", "preferences", "education", "diversity", "custom_questions"] if k in profile}, indent=2)

    return Task(
        description=f"""
        **Objective:** Map profile data to custom form questions provided below, grouped by their frame.

        **Form Elements (Grouped by Frame Identifier):** 
        ```json
        {grouped_elements_str}
        ```

        **Profile Data:** {profile_str}

        **FRAME IDENTIFIER RULES (EXTREMELY IMPORTANT):**
        - The keys in the "Form Elements" JSON ("main" or a URL) are the only valid `frame_identifier` values.
        - In your output JSON action, you MUST use the EXACT `frame_identifier` key associated with the element's group.
        - **DO NOT** create or invent descriptive frame names. **ONLY USE** the provided URL string or the string "main".
        
        **ACTION TYPE RULES (CRITICAL):**
        - Use `action_type: "click"` ONLY for elements with `type: "radio"` or `type: "checkbox"`.
        - Use `action_type: "fill"` ONLY for elements with `type: "text"` or `type: "textarea"`.
        - Use `action_type: "select-native"` ONLY for elements with `type: "select"`. These are native HTML dropdowns.
        - Use `action_type: "select-custom"` ONLY for elements with `type: "combobox"`. These are custom dropdowns/searchable selects.
        - **NEVER use `select-native` for a `combobox`. NEVER use `select-custom` for a `select`.** Match the action type precisely to the element's `"type"` field.

        **Instructions:**
        1. For each element in the groups above, match profile data based on labels and context.
        2. Generate the appropriate action based **strictly** on the element's `"type"` field using the rules above.
        3. Each action MUST include the correct `frame_identifier` (the key from the group the element was in).
        4. Handle optional demographic questions based on profile data.
        5. Output a JSON list of actions.

        **Action Formats:**
        - Fill: {{"action_type": "fill", "selector": "<sel>", "value": "<val>", "label": "<lbl>", "frame_identifier": "<url_or_main>"}}
        - Native Select: {{"action_type": "select-native", "selector": "<sel>", "value": "<option_text>", "label": "<lbl>", "frame_identifier": "<url_or_main>"}} (ONLY for type: "select")
        - Custom Select: {{"action_type": "select-custom", "selector": "<trigger_sel>", "value": "<option_text>", "label": "<lbl>", "frame_identifier": "<url_or_main>"}} (ONLY for type: "combobox")
        - Radio/Checkbox Click: {{"action_type": "click", "selector": "<specific_radio_or_checkbox_sel>", "label": "<lbl>", "frame_identifier": "<url_or_main>"}} (ONLY for type: "radio" or "checkbox")

        **Output:** JSON list of actions for custom questions, strictly following the type mapping rules.
        """,
        expected_output="A JSON list of actions ('fill', 'select-native', 'select-custom', 'click') for custom questions, using only 'main' or a URL as the frame_identifier AND strictly mapping element type to action type.",
        agent=agent
    )

def create_submit_task(agent: Agent, form_data: Dict[str, Any], profile: Dict[str, Any]) -> Task:
    """Task for identifying and clicking the submit button."""
    # Find ALL buttons/submits first, log them
    all_buttons_submits = [
        f for f in form_data["form_elements"] 
        if f["type"] in ["button", "submit"] or f["selector"].lower().startswith("button") or "[type='submit']" in f["selector"].lower()
    ]
    logger.info(f"Extractor found {len(all_buttons_submits)} potential buttons/submit inputs total.")
    # ---> FIX: Add detailed logging BEFORE keyword filtering <---
    if all_buttons_submits:
         logger.debug(f"ALL potential buttons/submits found by extractor (before keyword filter): {json.dumps(all_buttons_submits, indent=2)}")
    else:
         logger.debug("Extractor found NO elements matching button/submit types or selectors.")
    # ---> END FIX <---

    button_fields_raw = [] # Store raw buttons before grouping
    for f in all_buttons_submits:
        label_lower = f["label"].lower()
        value_lower = str(f.get("value", "")).lower()
        if any(keyword in label_lower for keyword in ["submit", "apply", "continue", "next", "save"]) or \
           any(keyword in value_lower for keyword in ["submit", "apply", "continue", "next", "save"]):
             button_fields_raw.append(f) # Keep frame_info here for now

    # ---> FIX: Group button fields <---
    grouped_button_fields = group_elements_by_frame(button_fields_raw)
    grouped_button_fields_str = json.dumps(grouped_button_fields, indent=2)
    logger.info(f"Found {len(button_fields_raw)} candidate submit/apply/continue/next/save buttons for the task.")
    logger.debug(f"Candidate Submit Buttons (Grouped): {grouped_button_fields_str}")
    if not button_fields_raw and all_buttons_submits:
         logger.warning("Extractor found buttons/submits, but none matched keywords in label or value.")
    # ---> END FIX <---

    # ---> TEMPORARY DEBUGGING: Hardcode if no candidates found (Improved URL finding) <---
    if not button_fields_raw:
        logger.warning("Submit Task: No candidate buttons found by extractor. Attempting to hardcode Greenhouse submit button as a fallback for debugging.")
        gh_iframe_url = None
        # Look for *any* element that came from a greenhouse iframe URL
        for elem_data in form_data.get("form_elements", []):
            frame_id = get_frame_identifier(elem_data.get("frame_info", {}))
            if frame_id != "main" and "greenhouse.io" in frame_id:
                 gh_iframe_url = frame_id
                 logger.debug(f"Submit Task: Found potential Greenhouse iframe URL via element: {gh_iframe_url}")
                 break 

        if gh_iframe_url:
             logger.warning(f"Submit Task: Injecting hardcoded Greenhouse submit button action for iframe: {gh_iframe_url}")
             # Create the structure the LLM expects (grouped)
             grouped_button_fields = {
                 gh_iframe_url: [{
                     "label": "Submit Application (Hardcoded)",
                     "selector": "#submit_button", 
                     "type": "button" 
                     # No frame_identifier needed inside the element dict itself anymore
                 }]
             }
             grouped_button_fields_str = json.dumps(grouped_button_fields, indent=2) # Update string for prompt
        else:
             logger.error("Submit Task: Hardcoding failed. Could not find a likely Greenhouse iframe URL in extracted elements.")
             grouped_button_fields = {} # Pass empty dict
             grouped_button_fields_str = "{}" # Update string for prompt
    # ---> END TEMPORARY DEBUGGING <---

    return Task(
        description=f"""
        **Objective:** Identify the final button to submit or proceed with the application.
        
        **Form Elements (Candidate Buttons Grouped by Frame Identifier):** 
        ```json
        {grouped_button_fields_str} 
        ```

        **FRAME IDENTIFIER RULES (EXTREMELY IMPORTANT):**
        - The keys in the "Form Elements" JSON ("main" or a URL) are the only valid `frame_identifier` values.
        - In your output JSON action, you MUST use the EXACT `frame_identifier` key associated with the element's group.
        - **DO NOT** create or invent descriptive frame names. **ONLY USE** the provided URL string or the string "main".

        **Instructions:**
        - Analyze the candidate buttons provided in the groups above. If the JSON is empty (`{{}}`), state that no button was found.
        - If candidates exist, pick the single button that most likely submits the entire application or moves to the final step (prioritize 'submit' or 'apply' if available, then 'continue', 'next', 'save').
        - Output a single JSON action. The action MUST include the correct `frame_identifier` (the key from the group the element was in).
        - Action Format: {{"action_type": "click", "selector": "<sel>", "label": "<txt>", "frame_identifier": "<url_or_main>"}}
        
        **Output:** Single JSON click action, or a message indicating no button was found if the input JSON was empty.
        """,
        expected_output="A single JSON click action for the final submission or progression button, using the correct frame_identifier (URL or 'main').",
        agent=agent
    )

async def map_form_data(form_data: Dict[str, Any], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Maps form data to profile using multiple crews with delays to respect rate limits."""
    agent = create_mapper_agent()

    # ---> FIX: Log the full extracted elements before any tasks run <---
    logger.debug(f"Full extracted form elements being passed to mapping tasks:\n{json.dumps(form_data.get('form_elements', []), indent=2)}")
    # ---> END FIX <---

    tasks = [
        create_basic_fields_task(agent, form_data, profile),
        create_uploads_task(agent, form_data, profile),
        create_custom_questions_task(agent, form_data, profile),
        create_submit_task(agent, form_data, profile) # Pass profile here too if needed by task
    ]
    action_plan = []
    # Define delay between tasks in seconds (adjust as needed based on rate limit)
    # 6 queries/min = 1 query / 10 seconds. Add a buffer.
    TASK_DELAY = 12 

    for task in tasks:
        task_desc_snippet = task.description[:50] if task and hasattr(task, 'description') else "Unknown Task"
        logger.info(f"Starting task: {task_desc_snippet}...")
        # Create a new Crew for each task to execute individually
        crew = Crew(agents=[agent], tasks=[task], verbose=True) 
        try:
            result = await crew.kickoff_async() 
            
            # Process the single task's output
            if not result or not result.tasks_output or not result.tasks_output[0]:
                 logger.warning(f"Crew kickoff returned no result for task: {task_desc_snippet}")
                 continue # Skip to next task if this one failed to produce output

            task_output = result.tasks_output[0]

            if not hasattr(task_output, 'raw') or not task_output.raw: 
                logger.warning(f"LLM returned empty or invalid output for task: {task_desc_snippet}...")
                continue 

            logger.debug(f"Raw LLM response for {task_desc_snippet}...: {task_output.raw}")
            # Ensure robust JSON parsing
            try:
                actions_str = task_output.raw.strip()
                actions = None # Initialize actions to None

                # ---> FIX: Simplify JSON handling logic <---
                # Check if the string looks like a JSON object or array before trying to parse
                if actions_str.startswith('{') and actions_str.endswith('}'):
                    try:
                        actions = json.loads(actions_str)
                    except json.JSONDecodeError as json_e:
                        logger.error(f"Failed to parse potential JSON object for task {task_desc_snippet}: {json_e}\nRaw output: {actions_str}")
                elif actions_str.startswith('[') and actions_str.endswith(']'):
                     try:
                        actions = json.loads(actions_str)
                     except json.JSONDecodeError as json_e:
                        logger.error(f"Failed to parse potential JSON array for task {task_desc_snippet}: {json_e}\nRaw output: {actions_str}")
                elif actions_str == "No button was found.":
                     logger.warning(f"Submit task reported no button found. No action added.")
                else:
                    # Attempt to extract from markdown block as a fallback
                    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", actions_str)
                    if match:
                        extracted_json_str = match.group(1).strip()
                        try:
                            actions = json.loads(extracted_json_str)
                            logger.debug(f"Successfully extracted JSON from markdown block for task {task_desc_snippet}")
                        except json.JSONDecodeError as json_e:
                             logger.error(f"Failed to parse JSON from markdown block for task {task_desc_snippet}: {json_e}\nExtracted: {extracted_json_str}")
                    else:
                         logger.error(f"Could not parse or extract JSON for task {task_desc_snippet}. Raw output was not JSON or 'No button was found.'\nRaw output: {actions_str}")

                # Process actions if parsing was successful
                if actions:
                    if isinstance(actions, list):
                        action_plan.extend(actions)
                    elif isinstance(actions, dict):
                        action_plan.append(actions)
                    else:
                        logger.warning(f"Unexpected data type after parsing task {task_desc_snippet}: {type(actions)}")
                # ---> END FIX <---

            except Exception as e:
                 logger.error(f"Unexpected error processing task output for {task_desc_snippet}: {e}", exc_info=True)
                 # raise # Optional: re-raise other unexpected errors

            # --- Add delay after processing each task ---
            logger.info(f"Waiting for {TASK_DELAY} seconds before next task...")
            await asyncio.sleep(TASK_DELAY)

        except Exception as e:
            # Catch errors during individual crew kickoff (like RateLimitError)
            logger.error(f"Task execution failed for {task_desc_snippet}: {e}", exc_info=True)
            # Decide if you want to stop the whole process or try the next task
            # For RateLimitError, stopping might be best unless LiteLLM handles retries internally
            if isinstance(e, ImportError): # Placeholder for actual RateLimitError if needed
                 raise # Re-raise critical errors like rate limiting
            # Otherwise, maybe just log and continue? Depends on desired robustness.
            logger.info(f"Waiting for {TASK_DELAY} seconds after task failure...")
            await asyncio.sleep(TASK_DELAY) # Still wait even if failed

    logger.info("Finished mapping all tasks.")
    return action_plan

# --- Helper for Fuzzy Matching ---
def find_best_match(target_value: str, options: List[str]) -> Optional[str]:
    """Finds the best match for target_value in a list of options using fuzzy matching."""
    if not options:
        return None
    # Use SequenceMatcher to find the best match
    # get_close_matches returns a list, we want the best one (first element if list not empty)
    matches = difflib.get_close_matches(target_value, options, n=1, cutoff=0.6) # cutoff=0.6 requires 60% similarity
    if matches:
        return matches[0]
    else:
        # Optional: Add a fallback for very poor matches if needed, e.g., check for containment
        target_lower = target_value.lower()
        for option in options:
            if target_lower in option.lower():
                logger.warning(f"Fuzzy match failed for '{target_value}', falling back to containment match: '{option}'")
                return option
        return None # No good match found

# Executor: Action Plan Execution
async def execute_action_plan(final_url: str, action_plan: List[Dict[str, Any]]) -> Dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto(final_url, wait_until="networkidle", timeout=120000) 
        execution_log = []

        # ---> REVERT: Simplify frame finding logic <---
        try:
            # Log URLs of available frames for debugging
            all_frame_urls = [f.url for f in page.frames]
            logger.debug(f"Executor: Available frame URLs on page: {all_frame_urls}")
        except Exception as frame_log_e:
            logger.error(f"Executor: Error logging available frames: {frame_log_e}")

        for action in action_plan:
            action_type = action["action_type"]
            selector = action["selector"]
            value = action.get("value")
            label = action["label"]
            # ---> FIX: Get frame identifier from action <---
            frame_identifier = action.get("frame_identifier", "main") # Expect URL or "main"
            # ---> END FIX <---
            
            logger.debug(f"Executor: Attempting to find context for identifier: '{frame_identifier}'")
            
            context: Optional[Page | Frame] = None
            if frame_identifier == "main":
                context = page
                logger.debug("Executor: Using main page context.")
            else:
                # Find frame strictly by URL
                context = next((f for f in page.frames if f.url == frame_identifier), None)
                if context:
                    logger.debug(f"Executor: Found frame by URL: {frame_identifier}")
            # ---> END REVERT <---

            await page.wait_for_timeout(250) 

            if not context:
                # ---> REVERT: Update error message <---
                msg = f"Frame not found using identifier (expected URL or 'main'): '{frame_identifier}'"
                # ---> END REVERT <---
                execution_log.append({"action": action, "result": {"success": False, "message": msg}})
                logger.error(msg)
                break 

            elem: Optional[Locator] = None
            try:
                elem = context.locator(selector)
                await elem.wait_for(state="attached", timeout=20000)
            except Exception as locate_e:
                 # ---> REVERT: Update error message format <---
                 msg = f"Failed to locate element for '{label}' using selector '{selector}' in frame '{frame_identifier}': {str(locate_e)}"
                 # ---> END REVERT <---
                 result = {"success": False, "message": msg}
                 logger.error(msg)
                 execution_log.append({"action": action, "result": result})
                 # Decide if we should stop on locate failure - maybe only for submit?
                 if action_type == "click" and any(k in label.lower() for k in ["submit", "apply", "continue"]): # Broaden check here too
                     break
                 else:
                     continue

            result = {"success": False, "message": ""}

            try:
                # Ensure element is visible (unless it's file upload) before interaction
                if action_type != "upload":
                    await elem.wait_for(state="visible", timeout=10000)
                    await elem.scroll_into_view_if_needed()
                    await page.wait_for_timeout(300) # Short pause after scroll

                if action_type == "fill":
                    # Clear field before filling? Optional, can cause issues sometimes.
                    # await elem.fill("") 
                    await elem.fill(str(value))
                    result["message"] = f"Filled '{label}' with '{value}'"
                
                elif action_type == "select-native":
                    # This code should ONLY run for actual <select> elements
                    logger.debug(f"Attempting native select for '{label}' with value '{value}'")
                    try:
                         options_texts = await elem.evaluate("el => Array.from(el.options).map(o => o.text.trim())")
                    except Exception as eval_e:
                         # This might happen if it's misidentified as native select
                         raise Exception(f"Failed to get options for native select '{label}'. Is it truly a native select element? Error: {eval_e}")

                    best_option_text = find_best_match(str(value), options_texts)
                    if best_option_text:
                        await elem.select_option(label=best_option_text)
                        result["message"] = f"Selected native option '{best_option_text}' (matched for '{value}') for '{label}'"
                        logger.info(f"Selected native option '{best_option_text}' for '{label}' matching '{value}'")
                    else:
                         # ... fallback select by value or raise error ...
                         raise Exception(f"Could not find matching option for '{value}' in native select '{label}'.")

                elif action_type == "select-custom":
                    # This code runs for elements identified as combobox
                    logger.info(f"Handling custom dropdown/combobox for '{label}' with value '{value}'")
                    
                    # 1. Click trigger (elem)
                    await elem.click()
                    await page.wait_for_timeout(1000) # Wait for options to potentially appear

                    # 2. Try search input (optional - can be added if needed later)
                    #    Look for an input *near* the trigger, maybe with aria-controls matching trigger id
                    
                    # 3. Locate options (generic selectors - might need refinement per site)
                    #    Use context to ensure options are searched within the correct frame
                    option_selector = "[role='option'], .select2-results__option, [class*='option']" 
                    options_locator = context.locator(option_selector).filter(visible=True)
                    try:
                         await options_locator.first.wait_for(state="visible", timeout=7000)
                    except Exception:
                         # Attempt to dismiss and retry click if options didn't appear? Or just fail.
                         logger.warning(f"No options became visible after clicking custom dropdown trigger '{label}'. Trying body click to dismiss potential stale overlay.")
                         try: await context.locator('body').click(timeout=1000) # Try dismissing
                         except: pass
                         raise Exception(f"No options became visible after clicking custom dropdown '{label}'")
                    
                    # 4. Find best match
                    all_option_texts = await options_locator.all_text_contents()
                    cleaned_options = [opt.strip() for opt in all_option_texts if opt.strip()] # Clean whitespace
                    best_option_text = find_best_match(str(value), cleaned_options)

                    if best_option_text:
                        # 5. Click best match
                        #    Use a potentially stricter filter for the selected option text
                        best_match_locator = options_locator.filter(has_text=re.compile(f"^{re.escape(best_option_text)}$"))
                        count = await best_match_locator.count()
                        if count == 0:
                             # Fallback if exact match filter fails (e.g., extra spaces in HTML)
                             logger.warning(f"Could not locate option '{best_option_text}' with exact text match. Trying broader filter.")
                             best_match_locator = options_locator.filter(has_text=best_option_text).first
                        else:
                             best_match_locator = best_match_locator.first # Take the first if multiple exact matches (unlikely)

                        await best_match_locator.click(timeout=10000)
                        result["message"] = f"Selected custom option '{best_option_text}' (matched for '{value}') for '{label}'"
                        logger.info(f"Selected custom option '{best_option_text}' for '{label}' matching '{value}'")
                        
                        # ---> ADD DISMISS LOGIC <---
                        await page.wait_for_timeout(500) # Short pause after clicking option
                        logger.debug(f"Attempting to dismiss dropdown for '{label}' by clicking body.")
                        try:
                            # Click the body of the context (frame or page) where the dropdown existed
                            await context.locator('body').click(timeout=2000, force=True) # Use force=True to bypass checks if needed
                            await page.wait_for_timeout(300) # Short pause after dismiss attempt
                        except Exception as dismiss_e:
                            logger.warning(f"Could not click body to dismiss dropdown for '{label}': {dismiss_e}")
                        # ---> END ADD DISMISS LOGIC <---

                    else:
                         # If no match, still try to dismiss before failing
                         logger.warning(f"Could not find suitable option for '{value}' in custom dropdown '{label}'. Options: {cleaned_options}. Trying to dismiss.")
                         try: await context.locator('body').click(timeout=1000, force=True)
                         except: pass
                         raise Exception(f"Could not find suitable option for '{value}' in custom dropdown '{label}'.")
                 # ---> END SPLIT <---

                elif action_type == "upload":
                    # ... upload logic ...
                    await elem.wait_for(state="attached", timeout=10000) 
                    abs_path = os.path.abspath(value)
                    if not os.path.exists(abs_path):
                        raise FileNotFoundError(f"File not found: {abs_path}")
                    logger.info(f"Attempting to set input files directly for '{label}' using selector '{selector}'")
                    await elem.set_input_files(abs_path)
                    await page.wait_for_timeout(1000) # Increased pause after upload
                    result["message"] = f"Set input files for '{label}' to '{os.path.basename(value)}'"
                    
                elif action_type == "click":
                    # ---> FIX: Indent click logic <---
                    await elem.click(timeout=10000) 
                    await page.wait_for_timeout(2000) # Increased pause after click, esp. for submit
                    result["message"] = f"Clicked '{label}'"
                    # ---> END FIX <---

                result["success"] = True
            except Exception as e:
                # ---> FIX: Ensure this block is also indented correctly relative to the try <---
                error_message = f"Failed '{action_type}' on '{label}' (Selector: {selector}, Frame: {frame_identifier}): {str(e)}"
                result["message"] = error_message
                logger.error(error_message, exc_info=True) 
                # ---> END FIX <---

            execution_log.append({"action": action, "result": result})
            # ---> FIX: Broaden check here too <---
            if not result["success"] and action_type == "click" and any(k in label.lower() for k in ["submit", "apply", "continue"]):
                logger.error("Submit/Apply/Continue action failed. Stopping execution.")
                break


        # Keep screenshot and result aggregation
        screenshot = f"execute_{uuid.uuid4().hex[:8]}.png"
        try:
            await page.screenshot(path=screenshot, full_page=True)
        except Exception:
             await page.screenshot(path=screenshot)
             
        await browser.close()
        success = all(step["result"]["success"] for step in execution_log)
        return {"success": success, "log": execution_log, "screenshot": screenshot}

# Orchestration
async def apply_to_job(job_url: str, user_profile_path: str = "user_profile.json", test_mode: bool = False) -> str:
    """Orchestrates the Extract -> Map -> Execute workflow."""
    start_time = time.time()
    report_filename = f"application_report_{uuid.uuid4().hex[:8]}.txt"

    try:
        logger.info("Starting extraction...")
        form_data = await extract_form_data(job_url)

        with open(user_profile_path) as f:
            profile = json.load(f)
        profile["resume_path"] = os.path.abspath(profile.get("resume_path", "resume.pdf"))

        logger.info("Mapping form data to profile...")
        action_plan = await map_form_data(form_data, profile)

        # --- Verification Step: Check if all required fields are in the action plan ---
        required_fields_extracted = {
             # Use a tuple of (selector, frame_identifier) as the key for uniqueness
             (f["selector"], get_frame_identifier(f.get("frame_info", {}))): f["label"]
             for f in form_data.get("form_elements", []) 
             if f.get("required", False) and f.get("selector") 
        }
        
        selectors_in_action_plan = {
             # Use a tuple of (selector, frame_identifier) as the key
             (action["selector"], action.get("frame_identifier", "main"))
             for action in action_plan 
             if action.get("selector") 
        }

        missing_required_fields = {}
        for (selector, frame_id), label in required_fields_extracted.items():
             if (selector, frame_id) not in selectors_in_action_plan:
                 # Check if it's a radio group where only one option needed clicking
                 # This is a heuristic: if another action targets an element with the same name attribute (common for radio groups), assume it's handled.
                 element_details = next((f for f in form_data["form_elements"] 
                                         if f["selector"] == selector and get_frame_identifier(f.get("frame_info", {})) == frame_id), None)
                 element_name = element_details.get("name") if element_details else None
                 
                 handled_by_group = False
                 if element_name and element_details.get("type") == "radio":
                     for action_selector, action_frame_id in selectors_in_action_plan:
                          # Find the element corresponding to the action
                          action_element = next((f for f in form_data["form_elements"] 
                                                 if f["selector"] == action_selector and get_frame_identifier(f.get("frame_info", {})) == action_frame_id), None)
                          if action_element and action_element.get("name") == element_name:
                              handled_by_group = True
                              break
                 
                 if not handled_by_group:
                     missing_required_fields[f"{frame_id}::{selector}"] = label # Store with identifier
                     logger.warning(f"Verification Warning: Required field '{label}' (Selector: {selector}, Frame: {frame_id}) extracted but not found in the action plan.")
        
        verification_passed = not bool(missing_required_fields)
        # --- End Verification Step ---

        # --- Post-processing Step: Correct Submit Button Frame ---
        submit_action_index = -1
        iframe_submit_selector = None
        # ---> FIX: Store frame identifier <---
        iframe_identifier = None 
        # ---> END FIX <---
        found_submit_specific = False 

        for i, action in enumerate(action_plan):
            label_lower = action.get("label", "").lower()
            # ---> FIX: Broaden check <---
            if action["action_type"] == "click" and any(k in label_lower for k in ["submit", "apply", "continue"]):
            # ---> END FIX <---
                submit_action_index = i
                break
        
        # ---> FIX: Check if LLM chose 'main' identifier <---
        if submit_action_index != -1 and action_plan[submit_action_index].get("frame_identifier", "main") == "main":
            logger.warning(f"LLM chose submit/apply/continue button in 'main' frame/context. Checking for iframe alternative...")
            
            for element in form_data.get("form_elements", []):
                el_label_lower = element.get("label", "").lower()
                # ---> FIX: Broaden check <---
                is_submit_apply_button = element["type"] in ["button", "submit"] and any(k in el_label_lower for k in ["submit", "apply", "continue"])
                # ---> FIX: Check frame_info <---
                element_frame_identifier = get_frame_identifier(element.get("frame_info", {}))
                is_in_iframe = element_frame_identifier != "main" 
                
                if is_submit_apply_button and is_in_iframe:
                    if "submit application" in el_label_lower: # Prioritize specific text
                        iframe_submit_selector = element["selector"]
                        iframe_identifier = element_frame_identifier # Store identifier
                        found_submit_specific = True
                        logger.info(f"Found 'Submit application' button in iframe: selector='{iframe_submit_selector}', identifier='{iframe_identifier}'")
                        break 
                    elif not found_submit_specific: # Fallback
                        iframe_submit_selector = element["selector"]
                        iframe_identifier = element_frame_identifier # Store identifier
                        logger.info(f"Found alternative button '{el_label_lower}' in iframe (will keep searching for 'Submit application'): selector='{iframe_submit_selector}', identifier='{iframe_identifier}'")
                        
            if iframe_submit_selector and iframe_identifier:
                logger.warning(f"Correcting submit/apply/continue action to use iframe: {iframe_identifier} with selector {iframe_submit_selector}")
                action_plan[submit_action_index]["selector"] = iframe_submit_selector
                # ---> FIX: Update frame_identifier <---
                action_plan[submit_action_index]["frame_identifier"] = iframe_identifier 
                action_plan[submit_action_index]["label"] = "Submit application" if found_submit_specific else element.get("label", "Submit") # Use found label
            else:
                 logger.warning(f"Could not find a submit/apply/continue button alternative in an iframe. Proceeding with LLM's choice (might fail).")
        # ---> END FIX <---
        # --- End Post-processing Step ---

        if test_mode:
             # ---> FIX: Broaden check <---
            action_plan = [a for a in action_plan if a["action_type"] != "click" or not any(k in a["label"].lower() for k in ["submit", "apply", "continue"])]

        logger.info("Executing action plan...")
        logger.debug(f"Final action plan for execution:\n{json.dumps(action_plan, indent=2)}") 
        execution_result = await execute_action_plan(form_data["final_url"], action_plan)

        # Determine final status based on both execution and verification
        final_status = "Unknown"
        if execution_result["success"] and verification_passed:
             final_status = "Completed"
        elif execution_result["success"] and not verification_passed:
             final_status = "Completed with missing required fields"
             logger.error(f"Application reported as completed, but verification failed. Missing required fields: {missing_required_fields}")
        else:
             # Execution failed, regardless of verification
             final_status = "Failed during execution"

        # Update report generation
        status = final_status # Use the more detailed status
        total_time = time.time() - start_time
        report = f"Job: {job_url}\nStatus: {status}\nTime: {total_time:.2f}s\nReport: {report_filename}"
        with open(report_filename, "w") as f:
            f.write(report + "\nExecution Log:\n" + json.dumps(execution_result["log"], indent=2) + 
                    f"\nExtract Screenshot: {form_data['screenshot']}\nExecute Screenshot: {execution_result['screenshot']}")
            if not verification_passed:
                 f.write(f"\n\nVerification Warnings (Required fields potentially missed):\n{json.dumps(missing_required_fields, indent=2)}")
        return report

    except Exception as e:
        logger.error(f"Application failed: {e}", exc_info=True)
        total_time = time.time() - start_time
        report = f"Job: {job_url}\nStatus: Failed ({type(e).__name__})\nTime: {total_time:.2f}s\nReport: {report_filename}"
        with open(report_filename, "w") as f:
            f.write(report + f"\nError: {str(e)}")
        return report

# Entry Point
async def main():
    parser = argparse.ArgumentParser(description="Job Application Automation")
    parser.add_argument("--job-url", required=True, help="Job posting URL")
    parser.add_argument("--user-profile", default="user_profile.json", help="User profile JSON path")
    parser.add_argument("--test", action="store_true", help="Test mode (no submit)")
    args = parser.parse_args()

    # Ensure TOGETHERAI_API_KEY is set
    if not os.environ.get("TOGETHERAI_API_KEY"):
        logger.error("TOGETHERAI_API_KEY environment variable not set.")
        return

    # Uncomment to save extracted data for debugging
    # Make sure the directory exists if you uncomment this
    # if not os.path.exists("extracted_data"):
    #      os.makedirs("extracted_data")

    print(await apply_to_job(args.job_url, args.user_profile, args.test))

if __name__ == "__main__":
    asyncio.run(main())