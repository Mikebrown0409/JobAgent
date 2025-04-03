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
    
    async def map_profile_to_form(self, form_structure, user_profile, job_description=None):
        """Map user profile to form fields using LLM."""
        self.logger.info("Mapping user profile to form fields")
        try:
            # Create mapping prompt
            mapping_prompt = self.create_mapping_prompt(form_structure, user_profile, job_description)
            
            try:
                # Use the call method for the latest CrewAI LLM interface
                # Format as a user message according to documentation
                response = self.llm.call(mapping_prompt)
                
            except Exception as e:
                # Fall back to using a basic mapping
                self.logger.error(f"LLM call failed: {str(e)}")
                return self._create_basic_mapping(form_structure, user_profile)
            
            # Log the mapping for debugging
            self.logger.debug(f"Received mapping from LLM: {response}")
            
            # Try to extract JSON from response
            mapping = self._extract_json_from_response(response)
            
            if not mapping:
                self.logger.warning("Failed to get valid mapping from LLM, using basic mapping")
                mapping = self._create_basic_mapping(form_structure, user_profile)
            
            return mapping
            
        except Exception as e:
            self.logger.error(f"Error mapping profile to form: {str(e)}")
            # Return basic mapping as fallback
            return self._create_basic_mapping(form_structure, user_profile)
    
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