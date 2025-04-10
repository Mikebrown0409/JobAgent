import google.generativeai as genai
import logging
import json
import os
import re
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Global variable for the client
genai_client = None

def configure_gemini_client():
    """Configures and returns the Gemini client based on the API key in .env."""
    global genai_client
    load_dotenv() # Ensure latest .env is loaded
    API_KEY = os.getenv("GEMINI_API_KEY")
    if not API_KEY:
        logging.warning("GEMINI_API_KEY not found in .env file. AI mapping will remain disabled.")
        genai_client = None
        return None
    
    if genai_client: # Avoid re-configuring if already done
        logging.debug("Gemini client already configured.")
        return genai_client

    try:
        genai.configure(api_key=API_KEY)
        generation_config = {
            "temperature": 0.2,
            "top_p": 1,
            "top_k": 1,
            "max_output_tokens": 2048,
            "response_mime_type": "application/json",
        }
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        genai_client = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        logging.info("Gemini AI client configured successfully.")
        return genai_client
    except Exception as e:
        logging.error(f"Failed to configure Gemini client: {e}")
        genai_client = None
        return None

# --- Initial Configuration Attempt ---
configure_gemini_client() # Attempt configuration when module is loaded

# --- Rule-Based Mapping Logic ---

def map_by_rules(profile_keys: list[str], detected_fields: list[dict]) -> tuple[dict, list[str]]:
    """Applies simple rules to map profile keys to detected fields."""
    mapping = {}
    remaining_keys = list(profile_keys)
    used_selectors = set()

    prioritized_attributes = ['id', 'name']
    common_keywords = { # Map profile keys to common keywords/patterns
        'first_name': [r'first[_ ]?name', r'given[_ ]?name'],
        'last_name': [r'last[_ ]?name', r'family[_ ]?name', r'surname'],
        'email': [r'email', r'e-mail'],
        'phone': [r'phone', r'mobile', r'contact[_ ]?number'],
        'location': [r'location', r'city', r'address'], # Keep location keywords
        'linkedin_url': [r'linkedin'],
        'github_url': [r'github'],
        'portfolio_url': [r'portfolio', r'website', r'url'],
        'resume_path': [r'resume', r'cv', r'attachment', r'upload'],
        'cover_letter_path': [r'cover[_ ]?letter'] # Added cover letter
    }
    
    # Keywords often associated with demographic/EEO fields to AVOID mapping general fields to.
    exclusion_keywords = re.compile(r'(race|ethnicity|hispanic|latino|gender|sex|lgbtq|disability|veteran|military|eeo|voluntary|demographic)', re.IGNORECASE)

    # Phase 1: Exact Attribute Matching (ID/Name)
    # Check specifically for first_name, last_name before general keywords
    priority_keys = ['first_name', 'last_name', 'email', 'phone']
    for key in priority_keys:
        if key not in remaining_keys: continue # Skip if already mapped or not in profile
        # Normalize key for matching (e.g., first_name -> firstname)
        normalized_key = key.replace('_', '')
        for field in detected_fields:
            selector = field.get('selector')
            if not selector or selector in used_selectors: continue
            texts_to_check = [field.get('label'), field.get('id'), field.get('name')]
            if any(exclusion_keywords.search(text) for text in texts_to_check if text):
                logging.debug(f"Skipping exact match for '{key}' to '{selector}' due to exclusion keyword.")
                continue 
                
            matched = False
            for attr in prioritized_attributes:
                attr_value = field.get(attr)
                if attr_value and (attr_value.lower() == key.lower() or attr_value.lower() == normalized_key):
                    logging.info(f"[Rule Match - Exact {attr}] '{key}' -> '{selector}'")
                    mapping[key] = selector
                    used_selectors.add(selector)
                    remaining_keys.remove(key)
                    matched = True
                    break # Move to next attribute check
            if matched: break # Move to next field if matched
        # Note: We don't break the outer loop here, allow checking all fields for priority keys

    # Phase 2: Keyword Matching in Label/ID/Name
    for key in list(remaining_keys):
        if key in mapping: continue
        potential_matches = []
        if key in common_keywords:
            patterns = [re.compile(p, re.IGNORECASE) for p in common_keywords[key]]
            for field in detected_fields:
                selector = field.get('selector')
                if not selector or selector in used_selectors:
                    continue
                
                texts_to_check = [field.get('label'), field.get('id'), field.get('name')]
                
                # **Crucial Check:** If any exclusion keyword is present, skip this field for this profile key mapping.
                # Filter out None values before searching
                if any(exclusion_keywords.search(text) for text in texts_to_check if text):
                    logging.debug(f"Skipping keyword match for '{key}' to '{selector}' due to exclusion keyword.")
                    continue

                for text in texts_to_check:
                    # Ensure text is not None before proceeding with pattern search
                    if text:
                        for pattern in patterns:
                            if pattern.search(text):
                                # Basic check for input type compatibility
                                field_type = field.get('type')
                                if key == 'resume_path' and field_type != 'file':
                                    continue # Skip non-file inputs for resume
                                if key == 'email' and field_type not in ['email', 'text']:
                                    continue # Skip non-email or non-text inputs for email
                                if key == 'phone' and field_type not in ['tel', 'text']:
                                    continue # Skip non-tel or non-text inputs for phone
                                    
                                potential_matches.append(field)
                                break
                        if field in potential_matches: break

        if potential_matches:
            best_match_selector = potential_matches[0]['selector']
            logging.info(f"[Rule Match - Keyword] '{key}' -> '{best_match_selector}'")
            mapping[key] = best_match_selector
            used_selectors.add(best_match_selector)
            remaining_keys.remove(key)

    logging.info(f"Rule-based mapping complete. Mapped {len(mapping)} fields. Remaining keys: {remaining_keys}")
    return mapping, remaining_keys

# --- AI Mapping Logic ---
def map_by_ai(profile_keys: list[str], detected_fields: list[dict]) -> dict:
    """Uses Gemini AI to map remaining profile keys to detected fields."""
    global genai_client # Ensure it uses the potentially re-configured client
    if not genai_client or not profile_keys:
        logging.info("Skipping AI mapping (No client or no remaining keys).")
        return {}

    logging.info(f"Attempting AI mapping for keys: {profile_keys}")

    # Prepare concise field info for the prompt
    field_context = []
    for i, field in enumerate(detected_fields):
        field_info = f"Field {i}: {{ "
        field_info += f"selector: \"{field.get('selector', 'N/A')}\", "
        field_info += f"label: \"{field.get('label', 'N/A')}\", "
        field_info += f"type: \"{field.get('type', 'N/A')}\", "
        field_info += f"name: \"{field.get('name', 'N/A')}\", "
        field_info += f"id: \"{field.get('id', 'N/A')}\" }}"
        field_context.append(field_info)
    
    field_context_str = "\n".join(field_context)

    prompt = f"""
Objective: Map user profile keys to the most appropriate web form field selectors based on the provided field details. Prioritize semantic meaning and likely field types.

User Profile Keys to Map:
{json.dumps(profile_keys)}

Detected Web Form Fields:
{field_context_str}

Instructions:
Return a JSON object mapping *only* the user profile keys you can confidently map to one of the provided field selectors. Use the exact profile key from the list and the exact selector from the field details.
Example Format: {{"profile_key_1": "selector_for_field_x", "profile_key_2": "selector_for_field_y"}}
If a key cannot be confidently mapped, do not include it in the output.
"""

    logging.debug(f"Gemini Prompt:\n{prompt}")

    try:
        response = genai_client.generate_content(prompt)
        ai_mapping_json = response.text
        logging.debug(f"Gemini Raw Response:\n{ai_mapping_json}")
        
        ai_mapping = json.loads(ai_mapping_json)
        logging.info(f"AI mapping successful: {ai_mapping}")
        return ai_mapping
    except Exception as e:
        logging.error(f"AI mapping failed: {e}")
        logging.error(f"Gemini Raw Response (if available):\n{response.text if 'response' in locals() else 'N/A'}")
        return {}

# --- Main Mapping Function ---

def map_profile_to_fields(profile_data: dict, detected_fields: list[dict]) -> dict:
    """Maps profile data keys to detected form field selectors using rules and AI."""
    logging.info("Starting form mapping...")
    profile_keys = list(profile_data.keys())
    
    # Step 1: Apply rules
    rule_mapping, remaining_keys = map_by_rules(profile_keys, detected_fields)
    
    # Step 2: Use AI for remaining keys
    ai_mapping = {}
    global genai_client # Ensure it uses the potentially re-configured client
    if remaining_keys and genai_client:
        # Filter AI mapping to avoid overwriting rule-based maps or mapping already used selectors
        used_selectors_by_rules = set(rule_mapping.values())
        potential_ai_mapping = map_by_ai(remaining_keys, detected_fields)
        
        for key, selector in potential_ai_mapping.items():
            if key in remaining_keys and selector not in used_selectors_by_rules:
                # Basic validation: Check if selector exists in detected fields (sanity check)
                if any(f.get('selector') == selector for f in detected_fields):
                    ai_mapping[key] = selector
                    used_selectors_by_rules.add(selector) # Mark as used now
                    logging.info(f"[AI Match] '{key}' -> '{selector}'")
                else:
                     logging.warning(f"AI suggested mapping '{key}' -> '{selector}', but selector not found in detected fields. Skipping.")
            else:
                logging.warning(f"AI suggested mapping for '{key}' ('{selector}') conflicts with rule-based mapping or already used selector. Skipping.")

    # Step 3: Combine results (AI map adds to rule map)
    final_mapping = rule_mapping.copy()
    final_mapping.update(ai_mapping)
    
    logging.info(f"Final mapping complete: {len(final_mapping)} fields mapped.")
    logging.debug(f"Final Mapping Details: {final_mapping}")
    
    # Log unmapped keys
    unmapped_keys = [key for key in profile_keys if key not in final_mapping]
    if unmapped_keys:
        logging.warning(f"Unmapped profile keys: {unmapped_keys}")
        
    return final_mapping

# Example Usage (for testing)
if __name__ == '__main__':
    # Dummy data for testing
    test_profile = {
        "full_name": "Elon Musk",
        "email": "elon@example.com",
        "phone": "111-222-3333",
        "resume_path": "/fake/path/resume.pdf",
        "linkedin_url": "https://linkedin.com/in/elon"
    }
    test_fields = [
        {'selector': '#name_field', 'label': 'Full Name', 'type': 'text', 'name': 'fullname', 'id': 'name_field'},
        {'selector': 'input[name="email_address"]', 'label': 'Email Address', 'type': 'email', 'name': 'email_address', 'id': None},
        {'selector': '#phone', 'label': 'Contact Number', 'type': 'tel', 'name': 'phone', 'id': 'phone'},
        {'selector': '#resume_upload', 'label': 'Upload Resume', 'type': 'file', 'name': 'resume', 'id': 'resume_upload'},
        {'selector': '#website', 'label': 'Personal Website or Portfolio', 'type': 'url', 'name': 'website', 'id': 'website'} # This one won't match profile
    ]

    print("--- Testing Form Mapper ---")
    if not genai_client:
        print("WARN: Gemini client not configured. AI mapping will be skipped.")
        
    final_map = map_profile_to_fields(test_profile, test_fields)
    
    print("\n--- Final Mapping Result ---")
    print(json.dumps(final_map, indent=2))
    
    print("\n--- Note ---")
    print("Check logs for detailed rule vs. AI mapping decisions.")
    print("Ensure GEMINI_API_KEY is set in a .env file in the AgentV0 directory for AI mapping.")
