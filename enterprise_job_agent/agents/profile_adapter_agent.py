"""Agent for adapting user profiles to job applications."""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Profile Optimization Specialist focused on job applications.

TASK:
Map candidate profiles to job application form fields with precision and strategic optimization.

YOUR EXPERTISE:
- Tailoring candidate profiles to specific job requirements
- Intelligently mapping profile data to form fields
- Optimizing content based on field importance
- Ensuring accurate format and validation compliance
- Highlighting candidate strengths strategically

APPROACH:
1. Identify the most relevant profile data for each form field
2. Prioritize content based on field importance (required first)
3. Format content to meet field-specific requirements
4. Optimize high-impact fields with tailored, job-relevant information
5. Maintain accuracy while presenting information in the best light

ATTENTION TO DETAIL:
- Match experience descriptions to job requirements
- Format phone numbers, dates and addresses according to field expectations
- For dropdown fields, find the closest matching option
- For education fields, format school names exactly as needed
- Include all required information, prioritize relevant achievements

ALWAYS STRUCTURE RESPONSES AS JSON with the exact schema provided in the task.
"""

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
        {
            "field_mappings": [
                {
                    "field_id": "original_field_id",
                    "value": "optimized value for this field",
                    "importance": "high|medium|low",
                    "reasoning": "Brief explanation of why this value was chosen"
                }
            ],
            "strategic_approach": [
                "Strategic insight 1 about how to approach this application",
                "Strategic insight 2 about key strengths to emphasize"
            ]
        }
        """
    
    def map_profile_to_form(
        self,
        form_structure: Dict[str, Any],
        user_profile: Dict[str, Any],
        job_description: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Map user profile data to form fields.
        
        Args:
            form_structure: Analyzed form structure
            user_profile: User profile data
            job_description: Optional job description
            
        Returns:
            Mapping of profile data to form fields
        """
        logger.info("Mapping user profile to form fields")
        
        # Create the mapping prompt
        prompt = self.create_mapping_prompt(form_structure, user_profile, job_description)
        
        try:
            # Get mapping from LLM
            if isinstance(self.llm, dict) and 'invoke' in dir(self.llm):
                # Handle CrewAI style LLM
                response = self.llm.invoke([
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ])
                mapping_text = response
            else:
                # Try direct invocation for other LLM types
                response = self.llm(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ]
                )
                mapping_text = response.get("content", "")
                
            logger.debug(f"Received mapping: {mapping_text[:500]}...")
            
            # Parse the JSON response
            import json
            import re
            
            # Try to extract JSON from the response (it might be wrapped in markdown code blocks)
            json_match = re.search(r'```(?:json)?(.*?)```', mapping_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                mapping = json.loads(json_str)
            else:
                # Try parsing the whole response as JSON
                mapping = json.loads(mapping_text)
            
            return mapping
        except Exception as e:
            logger.error(f"Error mapping profile to form: {e}")
            # Return a basic mapping for important fields that we can extract directly
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
                    
                    field_mappings.append({
                        "field_id": field_id,
                        "value": value,
                        "importance": "high" if element.get("required", False) else "medium"
                    })
            
            return {"field_mappings": field_mappings}
    
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