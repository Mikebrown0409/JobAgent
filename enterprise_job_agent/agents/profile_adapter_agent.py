"""Agent for adapting user profiles to job applications."""

import logging
import re
import json
from typing import Dict, Any, Optional
from crewai import LLM

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

APPROACH YOUR ANALYSIS:
1. Review form structure and requirements
2. Analyze user profile data
3. Create optimal field mappings
4. Handle special cases and transformations
5. Validate mappings meet requirements

FOCUS ON:
- Required vs optional fields
- Field type compatibility
- Data formatting requirements
- Special field handling (dropdowns, multi-select)
- Default values for unmapped fields

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
    
    def create_mapping_prompt(
        self,
        form_structure: Dict[str, Any],
        user_profile: Dict[str, Any],
        job_description: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a prompt for mapping user profile to form fields.
        
        Args:
            form_structure: Analyzed form structure
            user_profile: User profile data
            job_description: Optional job description data
            
        Returns:
            A prompt string for the LLM
        """
        # Extract resume and cover letter paths if available
        resume_path = user_profile.get("resume_path", "path/to/resume.pdf")
        cover_letter_path = user_profile.get("cover_letter_path", "path/to/cover_letter.pdf")
        
        # Add specific instructions for handling file paths
        file_instructions = f"""
        SPECIAL FILE HANDLING:
        - For resume fields, use the actual file path: {resume_path}
        - For cover letter fields, use the actual file path: {cover_letter_path}
        """
        
        job_desc_section = f"""
        JOB DESCRIPTION:
        ```
        {job_description}
        ```
        """ if job_description else ""
        
        return f"""
        TASK: Map the user profile to form fields in the most optimal way for this job application.
        
        USER PROFILE:
        ```
        {user_profile}
        ```
        
        FORM STRUCTURE:
        ```
        {form_structure}
        ```
        {job_desc_section}
        
        MAPPING REQUIREMENTS:
        
        1. For each form field:
           - Identify the most relevant user profile data
           - Format the data to match the field's expected format
           - Optimize high-importance fields with most relevant information
           - For dropdown fields, find the closest match to the user's data
        
        2. Strategic optimization:
           - For required fields, ensure complete and accurate information
           - For experience fields, highlight achievements relevant to the job
           - For education fields, format consistently with the form expectations
           - For skills fields, prioritize skills mentioned in the job description
        
        3. Special handling:
           - For location fields, format as "City, State" or according to form expectations
           - For phone numbers, format consistently (e.g., XXX-XXX-XXXX)
           - For dates, use the format expected by the form
           - For dropdown fields, identify closest match to user data
        
        {file_instructions}
        
        OUTPUT FORMAT:
        Return your mapping as this exact JSON structure:
        {{
            "field_mappings": [
                {{
                    "field_id": "original_field_id",
                    "value": "optimized value for this field",
                    "importance": "high|medium|low",
                    "reasoning": "Brief explanation of why this value was chosen"
                }}
            ],
            "strategic_approach": [
                "Strategic insight 1 about how to approach this application",
                "Strategic insight 2 about key strengths to emphasize"
            ]
        }}
        """
    
    async def adapt_profile(self, user_profile, form_structure, job_description=None):
        """
        Alias for map_profile_to_form, maintains compatibility with existing code.
        
        Args:
            user_profile: User profile data
            form_structure: Analyzed form structure
            job_description: Optional job description data
            
        Returns:
            Mapped profile data
        """
        return await self.map_profile_to_form(form_structure, user_profile, job_description)
    
    async def map_profile_to_form(self, form_structure, user_profile, job_description=None):
        """Map user profile to form fields using LLM."""
        self.logger.info("Mapping user profile to form fields")
        try:
            # Create mapping prompt
            mapping_prompt = self.create_mapping_prompt(form_structure, user_profile, job_description)
            
            # Use the call method for the latest CrewAI LLM interface
            # Format as a user message according to documentation
            response = self.llm.call(mapping_prompt)
            
            # Log the mapping for debugging
            self.logger.debug(f"Received mapping from LLM: {response}")
            
            # Try to extract JSON from response
            mapping = self._extract_json_from_response(response)
            
            # Post-process the mapping
            improved_mapping = await self._post_process_mapping(mapping, form_structure)
            
            return improved_mapping
            
        except Exception as e:
            self.logger.error(f"Error mapping profile to form: {str(e)}")
            # Comment out the fallback mapping so we can see the real error
            # return self._create_basic_mapping(form_structure, user_profile)
            
            # Instead, raise the exception so we can see what's happening
            raise
    
    def _extract_json_from_response(self, response):
        """Extract JSON from the LLM response."""
        try:
            # Try direct JSON parsing
            import json
            import re
            
            # Try to extract JSON from the response (it might be wrapped in markdown code blocks)
            json_match = re.search(r'```(?:json)?(.*?)```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1).strip()
                return json.loads(json_str)
            else:
                # Try parsing the whole response as JSON
                return json.loads(response)
        except Exception as e:
            self.logger.error(f"Error extracting JSON from response: {str(e)}")
            return None
            
    def _create_basic_mapping(self, form_structure, user_profile):
        """Create a basic mapping for important fields as fallback."""
        field_mappings = []
        
        # Basic extraction for common fields if we failed to get mapping from LLM
        for section in form_structure.get("form_structure", {}).get("sections", []):
            for element in section.get("fields", []):
                field_id = element.get("id", "")
                
                # Only map required fields in fallback mode
                if not element.get("required", False):
                    continue
                
                # Try to extract value based on field ID and label
                value = self._extract_fallback_value(element, user_profile)
                
                if value:
                    field_mappings.append({
                        "field_id": field_id,
                        "value": value,
                        "importance": "high" if element.get("required", False) else "medium",
                        "reasoning": "Basic fallback mapping for required field"
                    })
        
        return {
            "field_mappings": field_mappings,
            "strategic_approach": [
                "Using basic fallback mapping due to LLM error",
                "Only mapping required fields with direct matches"
            ]
        }
    
    def _extract_fallback_value(self, element: Dict[str, Any], user_profile: Dict[str, Any]) -> str:
        """Extract a profile value for a form field as a fallback."""
        field_id = element.get("id", "").lower()
        field_label = element.get("label", "").lower()
        
        if "first" in field_id or "first" in field_label:
            return user_profile.get("personal", {}).get("first_name", "")
        elif "last" in field_id or "last" in field_label:
            return user_profile.get("personal", {}).get("last_name", "")
        elif "email" in field_id or "email" in field_label:
            return user_profile.get("personal", {}).get("email", "")
        elif "phone" in field_id or "phone" in field_label:
            return user_profile.get("personal", {}).get("phone", "")
        elif "location" in field_id or "city" in field_label:
            return user_profile.get("personal", {}).get("city", "") + ", " + user_profile.get("personal", {}).get("state", "")
        elif "website" in field_id or "website" in field_label:
            return user_profile.get("personal", {}).get("website", "")
        elif "linkedin" in field_id or "linkedin" in field_label:
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

    async def _post_process_mapping(self, mapping: Dict[str, Any], form_structure: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process the mapping to improve field values.
        
        Args:
            mapping: The original mapping from LLM
            form_structure: The form structure
            
        Returns:
            Improved mapping
        """
        if not mapping or "field_mappings" not in mapping:
            return mapping
            
        # Get dropdown fields from form structure
        dropdown_fields = []
        for element in form_structure.get("form_elements", []):
            if element.get("type") == "select":
                dropdown_fields.append(element.get("id"))
                
        # Check for any detected dropdowns from analysis
        dropdown_analysis = form_structure.get("dropdown_analysis", {})
        detected_dropdowns = dropdown_analysis.get("detected_dropdowns", [])
        dropdown_fields.extend(detected_dropdowns)
        
        # Deduplicate
        dropdown_fields = list(set(dropdown_fields))
        
        # Update mappings
        field_mappings = mapping.get("field_mappings", [])
        for i, field_mapping in enumerate(field_mappings):
            field_id = field_mapping.get("field_id")
            value = field_mapping.get("value")
            
            # Skip if field already has a good value that's not a placeholder
            placeholder_values = ["n/a", "none", "null", "undefined", "to be determined"]
            if value and value.lower() not in placeholder_values:
                continue
                
            # For dropdown fields, provide appropriate default values based on field type
            if field_id in dropdown_fields:
                if "gender" in field_id.lower():
                    field_mappings[i]["value"] = "Decline To Self Identify"
                    field_mappings[i]["reasoning"] += " Updated with standard decline option for gender."
                elif "ethnicity" in field_id.lower() or "race" in field_id.lower():
                    field_mappings[i]["value"] = "Decline To Self Identify"
                    field_mappings[i]["reasoning"] += " Updated with standard decline option for ethnicity/race."
                elif "veteran" in field_id.lower():
                    field_mappings[i]["value"] = "I don't wish to answer"
                    field_mappings[i]["reasoning"] += " Updated with standard decline option for veteran status."
                elif "disability" in field_id.lower():
                    field_mappings[i]["value"] = "I do not want to answer"
                    field_mappings[i]["reasoning"] += " Updated with standard decline option for disability status."
                elif "school" in field_id.lower() or "university" in field_id.lower() or "education" in field_id.lower():
                    field_mappings[i]["value"] = "Other"
                    field_mappings[i]["reasoning"] += " Set to 'Other' as a fallback for education institutions."
                elif "degree" in field_id.lower():
                    field_mappings[i]["value"] = "Bachelor's Degree"
                    field_mappings[i]["reasoning"] += " Set to common degree type as fallback."
                elif "discipline" in field_id.lower() or "major" in field_id.lower():
                    field_mappings[i]["value"] = "Computer Science"
                    field_mappings[i]["reasoning"] += " Set to common field of study as fallback."
                elif "yes" in str(form_structure).lower() and "no" in str(form_structure).lower() and field_id.lower().startswith(("question_", "q_")):
                    # For yes/no questions
                    field_mappings[i]["value"] = "No"
                    field_mappings[i]["reasoning"] += " Updated with default 'No' for yes/no question."
                elif field_id.lower().startswith(("question_", "q_")):
                    field_mappings[i]["value"] = "Other"
                    field_mappings[i]["reasoning"] += " Updated with generic 'Other' option for dropdown question."
                else:
                    # For any other dropdown field, try to use a safe fallback
                    field_mappings[i]["value"] = "Other"
                    field_mappings[i]["reasoning"] += " Updated with generic 'Other' option as fallback."
                    
            # For non-dropdown empty fields, add appropriate defaults
            elif not value or value.lower() in placeholder_values:
                if "linkedin" in field_id.lower():
                    field_mappings[i]["value"] = ""
                    field_mappings[i]["reasoning"] += " Left empty as optional professional network field."
                elif "website" in field_id.lower():
                    field_mappings[i]["value"] = ""
                    field_mappings[i]["reasoning"] += " Left empty as optional website field."
                elif field_id.lower().startswith(("question_", "q_")):
                    field_mappings[i]["value"] = "Not applicable"
                    field_mappings[i]["reasoning"] += " Updated with standard response for optional question."
                elif "referral" in field_id.lower():
                    field_mappings[i]["value"] = "Job Board"
                    field_mappings[i]["reasoning"] += " Updated with common referral source."
        
        mapping["field_mappings"] = field_mappings
        return mapping 