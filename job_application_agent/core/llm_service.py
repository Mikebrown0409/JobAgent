"""
LLM Service - Centralized AI Integration

Handles all interactions with Large Language Models including:
- Plan generation
- Form field mapping
- Error recovery strategies
- Text generation for custom fields
"""

import asyncio
import logging
import re
import json
from typing import Dict, Any, List, Optional
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from job_application_agent.core.config import Config


class LLMService:
    """Service for all LLM interactions using Google Gemini."""
    
    def __init__(self, config: Config):
        """Initialize LLM service with configuration."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Configure Gemini
        if self.config.google_api_key:
            genai.configure(api_key=self.config.google_api_key)
            self.model = genai.GenerativeModel(self.config.gemini_model)
        else:
            self.logger.warning("No Google API key provided, LLM features will be disabled")
            self.model = None
    
    async def generate_plan(self, goal: str, available_tools: List[str], profile_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate an execution plan for achieving the given goal.
        
        Args:
            goal: High-level goal description
            available_tools: List of available tool names
            profile_context: User profile data for context
            
        Returns:
            List of plan steps
        """
        if not self.model:
            raise ValueError("LLM service not properly configured")
        
        prompt = self._build_planning_prompt(goal, available_tools, profile_context)
        
        try:
            response = await self._generate_text(prompt)
            plan = self._parse_plan_response(response)
            return plan
            
        except Exception as e:
            self.logger.error(f"Plan generation failed: {str(e)}")
            raise
    
    async def map_profile_to_form(self, profile_data: Dict[str, Any], form_structure: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map user profile data to form fields.
        
        Args:
            profile_data: User profile information
            form_structure: Analyzed form structure
            
        Returns:
            Mapping of selectors to values/actions
        """
        if not self.model:
            raise ValueError("LLM service not properly configured")
        
        prompt = self._build_mapping_prompt(profile_data, form_structure)
        
        try:
            response = await self._generate_text(prompt)
            mapping = self._parse_mapping_response(response)
            return mapping
            
        except Exception as e:
            self.logger.error(f"Form mapping failed: {str(e)}")
            raise
    
    async def generate_error_recovery(self, failed_step: Dict[str, Any], error_result: Dict[str, Any], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate error recovery strategies.
        
        Args:
            failed_step: The step that failed
            error_result: Error information
            context: Current execution context
            
        Returns:
            List of recovery actions
        """
        if not self.model:
            return []
        
        prompt = self._build_recovery_prompt(failed_step, error_result, context)
        
        try:
            response = await self._generate_text(prompt)
            recovery_plan = self._parse_recovery_response(response)
            return recovery_plan
            
        except Exception as e:
            self.logger.error(f"Error recovery generation failed: {str(e)}")
            return []
    
    async def generate_text_answer(self, prompt: str, context: Dict[str, Any]) -> str:
        """
        Generate text for free-form fields.
        
        Args:
            prompt: Question or field description
            context: User profile and job context
            
        Returns:
            Generated text response
        """
        if not self.model:
            return ""
        
        full_prompt = self._build_text_generation_prompt(prompt, context)
        
        try:
            response = await self._generate_text(full_prompt)
            return response.strip()
            
        except Exception as e:
            self.logger.error(f"Text generation failed: {str(e)}")
            return ""
    
    async def generate_contextual_answer(self, field_context: Dict[str, Any], 
                                       profile_data: Dict[str, Any]) -> str:
        """
        Generate contextual answers for open-ended questions in job applications.
        
        Args:
            field_context: Information about the field (label, placeholder, context)
            profile_data: Complete user profile data
            
        Returns:
            Generated contextual answer
        """
        if not self.model:
            return ""
        
        # Extract relevant information
        label = field_context.get('label', '')
        placeholder = field_context.get('placeholder', '')
        context = field_context.get('context', '')
        
        # Build comprehensive prompt for contextual answer generation
        prompt = self._build_contextual_answer_prompt(label, placeholder, context, profile_data)
        
        try:
            response = await self._generate_text(prompt)
            
            # Clean and format the response
            cleaned_response = self._clean_generated_text(response)
            
            # Ensure appropriate length (typically 50-300 words for job applications)
            if len(cleaned_response.split()) > 300:
                # Truncate to approximately 300 words
                words = cleaned_response.split()[:300]
                cleaned_response = ' '.join(words)
                # Ensure it ends with a complete sentence
                if not cleaned_response.endswith('.'):
                    last_period = cleaned_response.rfind('.')
                    if last_period > len(cleaned_response) * 0.7:  # If period is in last 30%
                        cleaned_response = cleaned_response[:last_period + 1]
            
            return cleaned_response
            
        except Exception as e:
            self.logger.error(f"Contextual answer generation failed: {str(e)}")
            return ""
    
    async def analyze_form_semantically(self, form_structure: Dict[str, Any], 
                                      profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform semantic analysis of form structure to improve field mapping.
        
        Args:
            form_structure: Complete form structure from page analysis
            profile_data: User profile data
            
        Returns:
            Enhanced form analysis with semantic insights
        """
        if not self.model:
            return form_structure
        
        prompt = self._build_semantic_analysis_prompt(form_structure, profile_data)
        
        try:
            response = await self._generate_text(prompt)
            semantic_analysis = self._parse_semantic_analysis(response)
            
            # Merge semantic insights with original structure
            enhanced_structure = form_structure.copy()
            enhanced_structure['semantic_analysis'] = semantic_analysis
            
            return enhanced_structure
            
        except Exception as e:
            self.logger.error(f"Semantic form analysis failed: {str(e)}")
            return form_structure
    
    async def generate_cover_letter_content(self, job_description: str, 
                                          profile_data: Dict[str, Any]) -> str:
        """
        Generate personalized cover letter content based on job description and profile.
        
        Args:
            job_description: Job posting description
            profile_data: User profile data
            
        Returns:
            Generated cover letter content
        """
        if not self.model:
            return ""
        
        prompt = self._build_cover_letter_prompt(job_description, profile_data)
        
        try:
            response = await self._generate_text(prompt)
            return self._clean_generated_text(response)
            
        except Exception as e:
            self.logger.error(f"Cover letter generation failed: {str(e)}")
            return ""
    
    async def _generate_text(self, prompt: str) -> str:
        """Generate text using the configured model."""
        try:
            generation_config = GenerationConfig(
                temperature=self.config.llm_temperature,
                max_output_tokens=self.config.llm_max_tokens,
            )
            
            # Use asyncio to run the synchronous generate_content method
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.model.generate_content(prompt, generation_config=generation_config)
            )
            
            return response.text
            
        except Exception as e:
            self.logger.error(f"LLM generation failed: {str(e)}")
            raise
    
    def _build_planning_prompt(self, goal: str, available_tools: List[str], profile_context: Dict[str, Any]) -> str:
        """Build prompt for plan generation."""
        return f"""
You are an AI agent planner for job applications. Generate a detailed execution plan to achieve the goal.

Goal: {goal}

Available Tools: {', '.join(available_tools)}

User Profile Context:
- Name: {profile_context.get('basics', {}).get('name', 'Unknown')}
- Email: {profile_context.get('basics', {}).get('email', 'Unknown')}
- Location: {profile_context.get('basics', {}).get('location', {}).get('city', 'Unknown')}

Generate a JSON array of steps with the following format:
[
  {{
    "step": 1,
    "action": "action_name",
    "tool": "tool_name",
    "parameters": {{}},
    "description": "What this step does"
  }}
]

Focus on:
1. Navigating to the job URL
2. Analyzing the page structure
3. Filling application forms systematically
4. Submitting the application
5. Verifying successful submission

Return only the JSON array, no additional text.
"""
    
    def _build_mapping_prompt(self, profile_data: Dict[str, Any], form_structure: Dict[str, Any]) -> str:
        """Build prompt for form field mapping."""
        return f"""
Map user profile data to form fields based on the form structure.

Profile Data:
{profile_data}

Form Structure:
{form_structure}

Generate a JSON object mapping selectors to values or actions:
{{
  "selector1": {{"value": "actual_value"}},
  "selector2": {{"action": "generate_text", "prompt": "question_to_answer"}},
  "selector3": {{"value": "profile_field_value"}}
}}

Rules:
- Use "value" for direct mappings from profile
- Use "action": "generate_text" for fields requiring custom responses
- Match field purposes semantically (first_name, last_name, email, etc.)
- For dropdowns, provide the exact option text that should be selected

Return only the JSON object, no additional text.
"""
    
    def _build_recovery_prompt(self, failed_step: Dict[str, Any], error_result: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Build prompt for error recovery."""
        return f"""
Generate recovery actions for a failed step in job application automation.

Failed Step: {failed_step}
Error Result: {error_result}
Current Context: {context}

Suggest up to 3 alternative approaches as a JSON array:
[
  {{
    "action": "alternative_action",
    "tool": "tool_name", 
    "parameters": {{}},
    "reason": "Why this might work"
  }}
]

Common recovery strategies:
- Try different selectors
- Use JavaScript execution
- Wait for elements to load
- Scroll to element
- Try keyboard navigation
- Refresh page and retry

Return only the JSON array, no additional text.
"""
    
    def _build_text_generation_prompt(self, prompt: str, context: Dict[str, Any]) -> str:
        """Build prompt for text generation."""
        profile = context.get('profile', {})
        basics = profile.get('basics', {})
        
        return f"""
Generate a professional response for a job application field.

Question/Field: {prompt}

Your Profile:
- Name: {basics.get('name', 'N/A')}
- Email: {basics.get('email', 'N/A')}
- Phone: {basics.get('phone', 'N/A')}
- Location: {basics.get('location', {}).get('city', 'N/A')}

Work Experience: {profile.get('work', [])[:2]}  # Last 2 positions
Education: {profile.get('education', [])}
Skills: {profile.get('skills', [])[:10]}  # Top 10 skills

Generate a concise, professional response (1-3 sentences) that directly answers the question.
Be specific and relevant to the question asked.

Response:
"""
    
    def _build_contextual_answer_prompt(self, label: str, placeholder: str, 
                                      context: str, profile_data: Dict[str, Any]) -> str:
        """Build prompt for contextual answer generation."""
        basics = profile_data.get('basics', {})
        work = profile_data.get('work', [])
        education = profile_data.get('education', [])
        skills = profile_data.get('skills', [])
        
        # Extract key information
        name = basics.get('name', 'the applicant')
        current_role = work[0].get('position', '') if work else ''
        current_company = work[0].get('company', '') if work else ''
        recent_education = education[0].get('institution', '') if education else ''
        degree = education[0].get('studyType', '') if education else ''
        top_skills = [skill.get('name', '') for skill in skills[:5]]
        
        return f"""
You are an expert job application assistant. Generate a professional, compelling answer for a job application question.

Question Context:
- Field Label: "{label}"
- Placeholder: "{placeholder}"
- Surrounding Context: "{context}"

Applicant Profile:
- Name: {name}
- Current Role: {current_role} at {current_company}
- Education: {degree} from {recent_education}
- Key Skills: {', '.join(top_skills)}
- Summary: {basics.get('summary', 'Experienced professional')}

Instructions:
1. Generate a professional, authentic response that directly answers the question
2. Incorporate relevant experience and skills from the profile
3. Keep the tone professional but personable
4. Length should be 50-200 words unless the context suggests otherwise
5. Focus on value proposition and relevant achievements
6. Avoid generic responses - make it specific to this applicant's background

Common Question Types and Approaches:
- "Why are you interested?" → Connect personal/professional goals with company/role
- "Tell us about yourself" → Brief professional summary highlighting relevant experience
- "Why should we hire you?" → Focus on unique value proposition and achievements
- "Describe your experience" → Highlight most relevant work experience and accomplishments
- "What are your strengths?" → Connect skills to job requirements with examples

Generate a compelling, professional response:
"""
    
    def _build_semantic_analysis_prompt(self, form_structure: Dict[str, Any], 
                                      profile_data: Dict[str, Any]) -> str:
        """Build prompt for semantic form analysis."""
        return f"""
Analyze this job application form structure and provide semantic insights for better field mapping.

Form Structure:
{json.dumps(form_structure, indent=2)}

User Profile Summary:
- Name: {profile_data.get('basics', {}).get('name', 'Unknown')}
- Email: {profile_data.get('basics', {}).get('email', 'Unknown')}
- Has Work Experience: {len(profile_data.get('work', [])) > 0}
- Has Education: {len(profile_data.get('education', [])) > 0}
- Has Skills: {len(profile_data.get('skills', [])) > 0}

Provide analysis in JSON format:
{{
  "form_purpose": "job_application|login|contact|other",
  "complexity_level": "simple|moderate|complex",
  "required_fields": ["field_purpose1", "field_purpose2"],
  "optional_fields": ["field_purpose1", "field_purpose2"],
  "special_requirements": ["file_upload", "multi_step", "conditional_fields"],
  "platform_hints": ["workday", "greenhouse", "custom"],
  "field_improvements": [
    {{
      "field_id": "field_identifier",
      "suggested_purpose": "improved_purpose",
      "confidence": 0.85,
      "reasoning": "why this mapping is better"
    }}
  ]
}}

Focus on improving field purpose identification and providing actionable insights.
"""
    
    def _build_cover_letter_prompt(self, job_description: str, 
                                 profile_data: Dict[str, Any]) -> str:
        """Build prompt for cover letter generation."""
        basics = profile_data.get('basics', {})
        work = profile_data.get('work', [])
        education = profile_data.get('education', [])
        
        return f"""
Generate a professional cover letter for this job application.

Job Description:
{job_description[:2000]}  # Limit to avoid token overflow

Applicant Profile:
- Name: {basics.get('name', 'Applicant')}
- Email: {basics.get('email', '')}
- Current Role: {work[0].get('position', '') if work else 'Professional'}
- Company: {work[0].get('company', '') if work else ''}
- Education: {education[0].get('studyType', '') if education else ''} from {education[0].get('institution', '') if education else ''}
- Summary: {basics.get('summary', '')}

Work Experience:
{json.dumps(work[:3], indent=2) if work else 'No work experience provided'}

Generate a compelling cover letter that:
1. Opens with enthusiasm for the specific role and company
2. Highlights relevant experience and achievements
3. Connects skills to job requirements
4. Shows knowledge of the company/role
5. Closes with a strong call to action
6. Maintains professional tone throughout
7. Is approximately 250-400 words

Format as a complete cover letter without placeholder text.
"""
    
    def _clean_generated_text(self, text: str) -> str:
        """Clean and format generated text."""
        # Remove common AI artifacts
        text = text.strip()
        
        # Remove markdown formatting
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*(.*?)\*', r'\1', text)      # Italic
        text = re.sub(r'`(.*?)`', r'\1', text)        # Code
        
        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        # Ensure proper sentence structure
        sentences = text.split('. ')
        cleaned_sentences = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and not sentence.endswith('.') and sentence != sentences[-1]:
                sentence += '.'
            if sentence:
                cleaned_sentences.append(sentence)
        
        return ' '.join(cleaned_sentences)
    
    def _parse_semantic_analysis(self, response: str) -> Dict[str, Any]:
        """Parse semantic analysis response."""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                # Fallback to basic analysis
                return {
                    "form_purpose": "job_application",
                    "complexity_level": "moderate",
                    "required_fields": [],
                    "optional_fields": [],
                    "special_requirements": [],
                    "platform_hints": [],
                    "field_improvements": []
                }
        except Exception as e:
            self.logger.debug(f"Failed to parse semantic analysis: {str(e)}")
            return {}
    
    def _parse_plan_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse plan response from LLM."""
        try:
            # Clean response and extract JSON
            cleaned = response.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:-3]
            elif cleaned.startswith('```'):
                cleaned = cleaned[3:-3]
            
            plan = json.loads(cleaned)
            
            # Validate plan structure
            if not isinstance(plan, list):
                raise ValueError("Plan must be a list")
            
            for step in plan:
                required_fields = ['step', 'action', 'tool', 'description']
                for field in required_fields:
                    if field not in step:
                        raise ValueError(f"Step missing required field: {field}")
            
            return plan
            
        except Exception as e:
            self.logger.error(f"Failed to parse plan response: {str(e)}")
            # Return empty plan on parse failure
            return []
    
    def _parse_mapping_response(self, response: str) -> Dict[str, Any]:
        """Parse mapping response from LLM."""
        try:
            cleaned = response.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:-3]
            elif cleaned.startswith('```'):
                cleaned = cleaned[3:-3]
            
            mapping = json.loads(cleaned)
            return mapping
            
        except Exception as e:
            self.logger.error(f"Failed to parse mapping response: {str(e)}")
            return {}
    
    def _parse_recovery_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse recovery response from LLM."""
        try:
            cleaned = response.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:-3]
            elif cleaned.startswith('```'):
                cleaned = cleaned[3:-3]
            
            recovery_plan = json.loads(cleaned)
            return recovery_plan if isinstance(recovery_plan, list) else []
            
        except Exception as e:
            self.logger.error(f"Failed to parse recovery response: {str(e)}")
            return [] 