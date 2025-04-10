import logging
import json
import os
import google.generativeai as genai
from typing import Dict, List, Any, Tuple, Optional, Union
import re

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.warning("GEMINI_API_KEY environment variable not set.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

class AdaptiveFieldMapper:
    """Adaptive field mapping system that uses structural understanding and AI to map form fields.
       Generates default values on demand instead of relying on a fallback profile.
    """
    
    def __init__(self, profile_data: Dict = None):
        self.knowledge_base = self._load_knowledge_base()
        self.profile_data = profile_data if profile_data is not None else {} # Store the loaded user profile
        self.field_mappings = self._load_field_mappings() # Load common field aliases
        # No longer loading fallback_profile or enhancing here.
        logging.info(f"AdaptiveFieldMapper initialized with profile keys: {list(self.profile_data.keys())}")
    
    def _load_knowledge_base(self) -> Dict:
        """Load learned patterns from knowledge base."""
        try:
            if os.path.exists('knowledge_base.json'):
                with open('knowledge_base.json', 'r') as f:
                    return json.load(f)
        except Exception as e:
            logging.warning(f"Could not load knowledge base: {e}")
        return {"field_patterns": {}, "section_patterns": {}, "successful_strategies": {}}
    
    def _load_field_mappings(self) -> Dict:
        """Load field mappings from a default configuration.
           This allows mapping common variations (e.g., 'salary' -> 'salary_expectation').
        """
        mapping_data = {
            "salary": "salary_expectation", "salary_requirements": "salary_expectation",
            "desired_salary": "salary_expectation", "compensation": "salary_expectation",
            "availability": "start_date", "available_start_date": "start_date",
            "when_can_you_start": "start_date", "referral_source": "how_did_you_hear",
            "how_did_you_hear_about_us": "how_did_you_hear", "source": "how_did_you_hear",
            "relocate": "willing_to_relocate", "relocation": "willing_to_relocate",
            "work_remotely": "remote_work", "willing_to_work_remotely": "remote_work",
            "authorized_to_work": "work_authorization", "eligible_to_work": "work_authorization",
            "legally_authorized": "work_authorization", "need_sponsorship": "require_sponsorship",
            "visa_sponsorship": "require_sponsorship", "sponsorship_required": "require_sponsorship",
            "linkedin": "linkedin_url", "github": "github_url", "portfolio": "portfolio_url",
            "personal_website": "website", "location": "full_location",
            "why_do_you_want_to_work_here": "why_company", "what_interests_you_about_this_position": "why_position",
            "tell_us_about_yourself": "strengths", "describe_your_background": "strengths",
            "what_are_your_strengths": "strengths", "what_are_your_weaknesses": "weaknesses",
            "biggest_achievement": "greatest_achievement", "greatest_accomplishment": "greatest_achievement",
            "challenge_overcome": "challenges", "future_plans": "future_goals",
            "career_goals": "future_goals", "where_do_you_see_yourself": "future_goals",
            "preferred_work_environment": "work_environment", "work_style": "work_environment",
            # Add mappings for file uploads
            "resume_upload": "resume_path",
            "cover_letter_upload": "cover_letter_path"
        }
        logging.info(f"Loaded {len(mapping_data)} field mappings.")
        return mapping_data
    
    def _save_knowledge_base(self):
        """Save learned patterns to knowledge base."""
        try:
            with open('knowledge_base.json', 'w') as f:
                json.dump(self.knowledge_base, f, indent=2)
        except Exception as e:
            logging.error(f"Could not save knowledge base: {e}")
    
    def get_value_for_key(self, key: str, question_text: Optional[str] = None, job_details: Optional[dict] = None, _call_stack: Optional[set] = None) -> Any:
        """Gets the value for a given key from the profile data.

        Handles direct lookups, alias mapping, default value generation, and AI generation.
        Accepts optional question_text and job_details for AI context.
        Uses a call stack to prevent infinite recursion.
        
        Args:
            key: The key to search for.
            question_text: The actual text of the question from the form label.
            job_details: Dictionary containing scraped job title and company name.
            _call_stack: Internal set to track keys during recursive calls.
            
        Returns:
            The value if found/generated, None otherwise.
        """
        # --- Recursion Prevention & Init ---
        if _call_stack is None: _call_stack = set()
        if job_details is None: job_details = {} # Ensure it's a dict
        if key in _call_stack:
            logging.error(f"Recursion detected for key: '{key}'. Stack: {_call_stack}")
            return None
        _call_stack.add(key)

        try:
            logging.debug(f"Get value for key: '{key}' (Depth: {len(_call_stack)}) Job: {job_details.get('job_title', 'N/A')}")

            # Define search locations in order of preference
            search_locations = [
                (self.profile_data, key), # Direct key in root
                (self.profile_data.get('basics', {}), key), # Basics section
                (self.profile_data.get('eeo', {}), key), # EEO section
                (self.profile_data.get('preferences', {}), key), # Preferences section
                (self.profile_data.get('authorization', {}), key), # Auth section
                (self.profile_data.get('other', {}), key), # Other section
                (self.profile_data.get('custom_questions', {}), key), # Custom Qs section
                (self.profile_data.get('online_presence', {}), key), # Online Presence
                (self.profile_data.get('work', {}), key), # Work section (simplified)
                (self.profile_data.get('education', {}), key), # Education section (simplified)
                (self.profile_data.get('skills', {}), key), # Skills section
                (self.profile_data.get('custom_fields', {}), key) # Custom Fields section
            ]

            # Helper function for checking locations and formatting
            def _check_locations_for_target(target_key: str):
                temp_search_locations = [
                    (self.profile_data, target_key), # Root level first
                    (self.profile_data.get('basics', {}), target_key),
                    (self.profile_data.get('custom_fields', {}), target_key), # Add custom_fields here
                    (self.profile_data.get('eeo', {}), target_key),
                    (self.profile_data.get('preferences', {}), target_key),
                    (self.profile_data.get('authorization', {}), target_key),
                    (self.profile_data.get('other', {}), target_key),
                    (self.profile_data.get('custom_questions', {}), target_key),
                    (self.profile_data.get('online_presence', {}), target_key),
                    (self.profile_data.get('work', {}), target_key),
                    (self.profile_data.get('education', {}), target_key),
                    (self.profile_data.get('skills', {}), target_key)
                ]
                for location, current_key in temp_search_locations:
                    if location and current_key in location:
                        value = location[current_key]
                        if value is not None and value != "":
                            logging.debug(f"Found value for original key '{key}' (via '{target_key}') in location: {value}")
                            # Format EEO values specifically
                            if target_key in ['veteran_status', 'disability_status', 'gender', 'race', 'ethnicity']:
                                 # Pass job_details down if needed by EEO formatter (currently not needed)
                                 return self._get_eeo_formatted_value(target_key, base_value=value)
                            return value
                return None

            # 1. Check direct locations
            value = _check_locations_for_target(key)
            if value is not None: return value

            # 2. Check aliases
            standard_key = self.field_mappings.get(key)
            if standard_key:
                value = _check_locations_for_target(standard_key)
                if value is not None: return value

            # 3. Check standard key's aliases
            for alias, std_key in self.field_mappings.items():
                if std_key == key:
                    value = _check_locations_for_target(alias)
                    if value is not None: return value

            # 4. Special formatted values - PASS STACK, question_text, job_details
            if key == 'full_name' or key == 'name':
                first = self.profile_data.get('basics', {}).get('first_name')
                last = self.profile_data.get('basics', {}).get('last_name')
                if first and last: return f"{first} {last}"
                if first: return first
                if last: return last
                # Pass a copy of the call stack to prevent interference between branches
                if not first: first = self.get_value_for_key('first_name', question_text=question_text, job_details=job_details, _call_stack=_call_stack.copy())
                if not last: last = self.get_value_for_key('last_name', question_text=question_text, job_details=job_details, _call_stack=_call_stack.copy())
                if first and last: return f"{first} {last}"
                if first: return first
                if last: return last

            if key == 'location' or key == 'full_location':
                loc_data = self.profile_data.get('basics', {}).get('location', {})
                parts = [loc_data.get(p) for p in ['city', 'region', 'country'] if loc_data.get(p)]
                if parts: return ", ".join(parts)
                # Pass a copy of the call stack to prevent interference between branches
                city = self.get_value_for_key('city', question_text=question_text, job_details=job_details, _call_stack=_call_stack.copy())
                region = self.get_value_for_key('region', question_text=question_text, job_details=job_details, _call_stack=_call_stack.copy())
                country = self.get_value_for_key('country', question_text=question_text, job_details=job_details, _call_stack=_call_stack.copy())
                parts = [p for p in [city, region, country] if p]
                if parts: return ", ".join(parts)

            # 5. Generate default/AI value - PASS question_text, job_details
            logging.info(f"Value for key '{key}' not found. Attempting default/AI generation.")
            default_value = self._generate_default_value(key, question_text=question_text, job_details=job_details)

            if default_value is not None:
                logging.info(f"Generated default/AI value for {key}: {default_value}")
                if key in ['veteran_status', 'disability_status', 'gender', 'race', 'ethnicity']:
                     return self._get_eeo_formatted_value(key, base_value=default_value, use_decline_default=True)
                return default_value

            logging.warning(f"Could not find or generate value for key: '{key}'")
            return None
        finally:
            if key in _call_stack: _call_stack.remove(key)

    def _generate_default_value(self, key: str, question_text: Optional[str] = None, job_details: Optional[dict] = None) -> Optional[str]:
        """Generates default value OR triggers AI answer generation with job context.
        
        Args:
            key: The key to search for.
            question_text: The actual text of the question from the form label.
            job_details: Dictionary containing scraped job title and company name.
            
        Returns:
            The value if found/generated, None otherwise.
        """
        if job_details is None: job_details = {}
        normalized_key = key.lower().replace('_', ' ').strip() if key else ""
        logging.debug(f"Generating default value for norm key: '{normalized_key}', Job: {job_details.get('job_title')}")

        # --- Open-ended questions -> Trigger AI (pass job_details) ---
        open_ended_markers = ["why company", "why position", "strengths", "weaknesses", "tell me about", "describe a time", "motivation", "cover letter", "additional information"]
        is_open_ended_key = key in ["why_company", "why_position", "cover_letter_paste", "additional_information"]

        if any(marker in normalized_key for marker in open_ended_markers) or is_open_ended_key:
            if question_text:
                logging.info(f"Triggering AI answer for key '{key}', question: '{question_text}'")
                profile_summary = self.profile_data.get('basics', {}).get('summary', '')
                skills = self.profile_data.get('skills', [])
                context_for_ai = {
                    "profile_summary": profile_summary,
                    "skills": skills,
                    "job_title": job_details.get('job_title'),
                    "company_name": job_details.get('company_name')
                }
                # Call AI generator with context
                ai_answer = self._generate_ai_answer(question_text, context_for_ai)
                if ai_answer:
                    return ai_answer
                else:
                    logging.warning(f"AI failed for '{key}'. Falling back.")
                    return "Response generation failed."
        else:
                logging.warning(f"Open-ended key '{key}', but no question_text. Cannot generate AI answer.")
                if key == "cover_letter_paste":
                     logging.info("Pasting profile summary as cover letter fallback.")
                     return self.profile_data.get('basics', {}).get('summary', 'Not specified.')
                return "Response not available in profile."

        # --- EEO Fields - Default to a value indicating decline/no answer ---
        if any(k in normalized_key for k in ["gender", "race", "ethnicity", "veteran", "disability"]):
            return "Prefer not to answer"

        # --- Common logistical questions ---
        if "salary" in normalized_key or "compensation" in normalized_key: return "Competitive / Market Rate"
        if "notice period" in normalized_key: return "2 weeks"
        if "start date" in normalized_key or "availability" in normalized_key: return "Immediately"
        if "how did you hear" in normalized_key or "source" in normalized_key or "referral" in normalized_key: return "Company Website / LinkedIn"
        if "sponsorship" in normalized_key: return "No"
        if "authorized" in normalized_key or "eligible" in normalized_key: return "Yes"
        if "relocate" in normalized_key: return "Yes, willing to relocate"
        if "travel" in normalized_key: return "Yes, willing to travel"
        if any(k in normalized_key for k in ["agree", "consent", "terms", "conditions", "background check"]): return "Yes"
        if any(k in normalized_key for k in ["convicted", "felony"]): return "No"

        # --- Links - Provide placeholder ---
        if any(k in normalized_key for k in ["linkedin", "github", "portfolio", "website"]): return f"Not Specified"

        # --- Prepare Key & Context --- 
        # Strip quotes and normalize key if it looks quoted (common from LLM)
        if key and isinstance(key, str) and (key.startswith(('"', "`", "'")) or key.endswith(('"', "`", "'"))):
            key = re.sub(r'^[\"\`\']|[\"\`\']$', '', key)  # Remove quotes if present
            logging.debug(f"Removed quotes from key, now: '{key}'")
        
        logging.info(f"No specific default or AI generation rule found for key: '{key}'")
        return None

    def _generate_ai_answer(self, question_text: str, profile_context: dict) -> Optional[str]:
        """Generates an answer to an open-ended question using AI (Gemini).
        Uses a more detailed prompt and incorporates profile context including job details.
        
        Args:
            question_text: The specific question asked in the form.
            profile_context: Relevant parts of the user's profile AND job details.
        """
        logging.info(f"AI generation called for question: '{question_text}'")
        if not GEMINI_API_KEY: # Check if API key is available
            logging.error("Cannot generate AI answer: GEMINI_API_KEY not set.")
            return None

        # Extract key profile and job elements from context
        summary = profile_context.get('profile_summary', '')
        skills_list = profile_context.get('skills', [])
        job_title = profile_context.get('job_title', 'the position') 
        company_name = profile_context.get('company_name', 'the company')
        job_url = profile_context.get('url', '[Unknown URL]') # Extract URL
        
        # Handle skills_list potentially containing dicts
        if skills_list and isinstance(skills_list[0], dict):
            skill_names = [skill.get('name') for skill in skills_list if skill.get('name')]
            skills_str = ", ".join(skill_names) if skill_names else "No specific skills listed."
        elif skills_list: # Assume it's already a list of strings
            skills_str = ", ".join(skills_list)
        else:
            skills_str = "No specific skills listed."

        # Update prompt to use job_title and company_name variables
        prompt = f'''**Role:** You are assisting a job candidate in filling out an online application. Your task is to generate a professional, concise, and positive answer to the specific question asked on the form, based *only* on the provided profile information.

**Candidate Profile Summary:**
{summary if summary else '[No summary provided]'}

**Candidate Skills:**
{skills_str}

**Application Context:**
- Applying for: {job_title}
- At: {company_name}
- URL: {job_url}

**Specific Question Asked on Form:**
{question_text}

**Instructions:**
1.  Carefully read the specific question.
2.  Review the candidate's profile summary and skills.
3.  Generate an answer (2-4 sentences maximum) that directly addresses the question.
4.  The tone should be professional, confident, and enthusiastic.
5.  **Crucially: Do NOT invent skills, experiences, or motivations not explicitly supported by the provided profile context.** If the profile lacks relevant information to answer fully, acknowledge this honestly but positively (e.g., "While my profile summary provides an overview, I look forward to discussing my specific qualifications for this aspect further in an interview."). Avoid generic platitudes if possible, but use them if the profile offers nothing relevant.
6.  Do not include conversational filler like "Here is the answer:". Output only the answer itself.

**Generated Answer:**
''' # Prompt definition ends here

        try:
            logging.debug(f"Sending enhanced AI answer generation prompt to Gemini:\n{prompt}")
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # Re-enable safety settings - ensure structure is correct
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            ]
            
            response = model.generate_content(prompt, safety_settings=safety_settings)
            
            # Check for blocks or empty responses
            if not response.candidates or not response.candidates[0].content.parts:
                block_reason = response.prompt_feedback.block_reason if response.prompt_feedback else 'Unknown'
                logging.error(f"Gemini blocked response. Reason: {block_reason}")
                # Attempt to log safety ratings if available
                if response.prompt_feedback and response.prompt_feedback.safety_ratings:
                     logging.error(f"Safety Ratings: {response.prompt_feedback.safety_ratings}")
                return None # Return None on block/empty
            
            answer = response.candidates[0].content.parts[0].text.strip()
            logging.info(f"--- Gemini Generated Answer ---\n{answer}")
            
            if not answer:
                 logging.error("Gemini returned an empty answer.")
                 return None
                 
            return answer

        except Exception as e:
            logging.error(f"Error calling Gemini for answer generation: {e}")
            if 'response' in locals(): 
                 try:
                     logging.error(f"Gemini raw text on error: {response.text}")
                 except Exception as log_e:
                     logging.error(f"Error logging Gemini response text: {log_e}")
            return None

    def _get_eeo_formatted_value(self, key: str, base_value: Optional[str] = None, use_decline_default: bool = False) -> Optional[str]:
        """Get an appropriately formatted value for EEO fields, optionally defaulting to decline.
        
        Args:
            key: The EEO field key.
            base_value: The value found in the profile (if any).
            use_decline_default: If True and no profile value, force 'I prefer not to answer'.
            
        Returns:
            A formatted string value or None.
        """
        # If base_value is not provided, try to find it (used when called directly)
        if base_value is None:
            # Need to use get_value_for_key carefully here to avoid recursion if called directly
            # Pass an empty stack to prevent infinite loops if EEO keys had aliases
            # Pass None for job_details as EEO formatting doesn't use it currently
            base_value = self.get_value_for_key(key, job_details=None, _call_stack=set())

        if not base_value:
            if use_decline_default:
                logging.debug(f"No EEO value for {key}, using decline default.")
                return "I prefer not to answer"
            else:
                logging.debug(f"No EEO value found for {key}. Returning None.")
                return None # No value and not forcing default
            
        # Convert base value to string and lowercase for comparison
        if isinstance(base_value, (bool, int)):
            base_value = "Yes" if base_value else "No"
        base_value_lower = str(base_value).lower()
        
        logging.debug(f"Formatting EEO key '{key}' from base value '{base_value}'")

        # Format based on the field type
        if key == 'veteran_status':
            if 'yes' in base_value_lower or 'protected' in base_value_lower: return "I identify as one or more of the classifications of protected veteran"
            if 'no' in base_value_lower or 'not' in base_value_lower: return "I am not a protected veteran"
            return "I prefer not to answer"
                
        elif key == 'disability_status':
            if 'yes' in base_value_lower or 'disability' in base_value_lower: return "Yes, I have a disability (or previously had a disability)"
            if 'no' in base_value_lower or 'not' in base_value_lower: return "No, I don't have a disability"
            return "I prefer not to answer"
                
        elif key == 'gender':
            if 'female' in base_value_lower: return "Female"
            if 'male' in base_value_lower: return "Male"
            if 'non-binary' in base_value_lower or 'nonbinary' in base_value_lower: return "Non-binary"
            return "I prefer not to answer"
                
        elif key == 'race':
            if 'white' in base_value_lower: return "White"
            if 'black' in base_value_lower or 'african' in base_value_lower: return "Black or African American"
            if 'asia' in base_value_lower: return "Asian"
            if 'hispanic' in base_value_lower or 'latino' in base_value_lower: return "Hispanic or Latino" # Often listed under race too
            if 'native' in base_value_lower and 'american' in base_value_lower: return "American Indian or Alaska Native"
            if 'hawaii' in base_value_lower or 'pacific' in base_value_lower: return "Native Hawaiian or Other Pacific Islander"
            if 'two' in base_value_lower or 'multiple' in base_value_lower: return "Two or More Races"
            return "I prefer not to answer"
                
        elif key == 'ethnicity': # Primarily Hispanic/Latino distinction
            if 'yes' in base_value_lower or ('hispanic' in base_value_lower and 'not' not in base_value_lower):
                return "Yes, I am Hispanic or Latino"
            if 'no' in base_value_lower or ('not' in base_value_lower and 'hispanic' in base_value_lower):
                return "No, I am not Hispanic or Latino"
            return "I prefer not to answer"
                
        logging.warning(f"_get_eeo_formatted_value called with unhandled key: {key}")
        return base_value # Return raw value as last resort

    # Removed placeholder methods for identify_fields, _identify_sections, etc.


# Unused helper functions removed.
# The core logic for mapping and interaction is now handled by Strategy classes
# and action_taker.py.

# def adaptive_map_fields(page_structure: str, profile: Dict) -> Tuple[List[Dict], Dict]:
#     """Use the adaptive mapper to identify fields in a form."""
#     mapper = AdaptiveFieldMapper()
#     return mapper.identify_fields(page_structure, profile)
# 
# def generate_field_interaction(field: Dict, value: Any, element_context: Dict) -> str:
#     """Generate code to interact with a field."""
#     mapper = AdaptiveFieldMapper()
#     return mapper.generate_ai_interaction_code(field, value, element_context)
# 
# def record_interaction_outcome(field: Dict, strategy: Dict, code: str, success: bool, error: str = None):
#     """Record the outcome of a field interaction for learning."""
#     mapper = AdaptiveFieldMapper()
#     mapper.record_interaction_result(field, strategy, code, success, error) 