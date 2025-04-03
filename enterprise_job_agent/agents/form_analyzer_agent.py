"""Form Analyzer Agent for analyzing job application forms."""

import logging
import json
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from crewai import Agent
from langchain_core.language_models import BaseLLM

from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager

logger = logging.getLogger(__name__)

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
    
    async def analyze_form(
        self,
        form_data: Dict[str, Any],
        page_url: str,
        job_details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze a form structure and create a detailed representation.
        
        Args:
            form_data: Raw form data to analyze
            page_url: URL of the page containing the form
            job_details: Optional job posting details for context
            
        Returns:
            Analyzed form structure
        """
        try:
            # Start with basic validation
            if not form_data or not isinstance(form_data, dict):
                raise ValueError("Invalid form data provided")
                
            # Extract form elements
            form_elements = form_data.get("form_elements", [])
            if not form_elements:
                raise ValueError("No form elements found in form data")
                
            # Group fields by purpose
            field_groups = self._group_fields_by_purpose(form_elements)
            
            # Analyze field relationships
            field_relationships = self._analyze_field_relationships(form_elements)
            
            # Determine field importance
            field_importance = self._determine_field_importance(
                form_elements,
                job_details or {}
            )
            
            # Create structured analysis
            analysis = {
                "form_structure": {
                    "url": page_url,
                    "sections": self._create_form_sections(
                        field_groups,
                        field_importance,
                        field_relationships
                    ),
                    "navigation": self._analyze_navigation(form_data),
                    "validation_rules": self._extract_validation_rules(form_elements)
                },
                "field_analysis": {
                    "total_fields": len(form_elements),
                    "required_fields": len([f for f in form_elements if f.get("required", False)]),
                    "field_types": self._count_field_types(form_elements),
                    "frame_distribution": self._analyze_frame_distribution(form_elements)
                },
                "strategic_insights": self._generate_strategic_insights(
                    form_elements,
                    field_relationships,
                    job_details
                )
            }
            
            return analysis
            
        except Exception as e:
            error_msg = f"Form analysis failed: {str(e)}"
            logger.error(error_msg)
            raise
    
    def _group_fields_by_purpose(self, form_elements: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group form fields by their purpose."""
        groups = {
            "personal_info": [],
            "contact": [],
            "education": [],
            "experience": [],
            "skills": [],
            "preferences": [],
            "diversity": [],
            "other": []
        }
        
        for field in form_elements:
            # Safely get field attributes, defaulting to empty string if None
            label = (field.get("label") or "").lower()
            field_id = (field.get("id") or "").lower()
            field_name = (field.get("name") or "").lower()
            
            # Personal info fields
            if any(term in label or term in field_id or term in field_name for term in 
                ["name", "email", "phone", "mobile", "birth"]):
                groups["personal_info"].append(field)
                
            # Contact fields
            elif any(term in label or term in field_id or term in field_name for term in 
                ["address", "city", "state", "zip", "postal", "country"]):
                groups["contact"].append(field)
                
            # Education fields
            elif any(term in label or term in field_id or term in field_name for term in 
                ["education", "school", "university", "degree", "major", "gpa"]):
                groups["education"].append(field)
                
            # Experience fields
            elif any(term in label or term in field_id or term in field_name for term in 
                ["experience", "work", "employment", "job", "company", "role", "position"]):
                groups["experience"].append(field)
                
            # Skills fields
            elif any(term in label or term in field_id or term in field_name for term in 
                ["skill", "technology", "programming", "language", "certification"]):
                groups["skills"].append(field)
                
            # Preferences fields
            elif any(term in label or term in field_id or term in field_name for term in 
                ["salary", "location", "remote", "travel", "start", "availability"]):
                groups["preferences"].append(field)
                
            # Diversity fields
            elif any(term in label or term in field_id or term in field_name for term in 
                ["gender", "race", "ethnicity", "veteran", "disability", "diversity"]):
                groups["diversity"].append(field)
                
            # Other fields
            else:
                groups["other"].append(field)
        
        return groups
    
    def _analyze_field_relationships(self, form_elements: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Analyze relationships between form fields."""
        relationships = {}
        
        for field in form_elements:
            field_id = field.get("id")
            if not field_id:
                continue
                
            related_fields = []
            
            # Check for common relationships
            for other_field in form_elements:
                other_id = other_field.get("id")
                if not other_id or other_id == field_id:
                    continue
                    
                # Get field names safely
                field_name = (field.get("name") or "").lower()
                other_name = (other_field.get("name") or "").lower()
                
                # Check if fields are part of the same group (based on prefix)
                if field_name and other_name:
                    field_prefix = field_name.split("_")[0] if "_" in field_name else field_name
                    other_prefix = other_name.split("_")[0] if "_" in other_name else other_name
                    if field_prefix == other_prefix:
                        related_fields.append(other_id)
                    
                # Get labels safely
                field_label = (field.get("label") or "").lower()
                other_label = (other_field.get("label") or "").lower()
                
                # Check for dependent fields (e.g., state depends on country)
                if field_label == "country" and other_label in ["state", "province"]:
                    related_fields.append(other_id)
                    
                # Check for date field relationships
                if field_name and other_name:
                    if field_name.endswith("_month") and other_name.endswith("_year"):
                        related_fields.append(other_id)
            
            if related_fields:
                relationships[field_id] = related_fields
        
        return relationships
    
    def _determine_field_importance(
        self,
        form_elements: List[Dict[str, Any]],
        job_details: Dict[str, Any]
    ) -> Dict[str, str]:
        """Determine importance level for each field."""
        importance = {}
        
        for field in form_elements:
            field_id = field.get("id")
            if not field_id:
                continue
                
            # Start with medium importance
            level = "medium"
            
            # Required fields are high importance
            if field.get("required", False):
                level = "high"
                
            # Get field attributes safely
            label = (field.get("label") or "").lower()
            field_name = (field.get("name") or "").lower()
            field_type = (field.get("type") or "").lower()
            
            # High importance fields
            if any(term in label or term in field_name for term in [
                "name", "email", "phone", "education", "experience",
                "resume", "cv", "cover"
            ]):
                level = "high"
                
            # Medium importance fields
            elif any(term in label or term in field_name for term in [
                "address", "skills", "salary", "references"
            ]):
                level = "medium"
                
            # Low importance fields
            elif any(term in label or term in field_name for term in [
                "subscribe", "newsletter", "preference", "optional"
            ]):
                level = "low"
                
            # File upload fields are typically high importance
            if field_type == "file":
                level = "high"
                
            importance[field_id] = level
        
        return importance
    
    def _create_form_sections(
        self,
        field_groups: Dict[str, List[Dict[str, Any]]],
        field_importance: Dict[str, str],
        field_relationships: Dict[str, List[str]]
    ) -> List[Dict[str, Any]]:
        """Create structured form sections."""
        sections = []
        
        for group_name, fields in field_groups.items():
            if not fields:
                continue
                
            section = {
                "name": group_name,
                "importance": "high" if any(field_importance.get(f.get("id"), "low") == "high" 
                    for f in fields) else "medium",
                "fields": []
            }
            
            for field in fields:
                field_id = field.get("id")
                if not field_id:
                    continue
                    
                field_info = {
                    "id": field_id,
                    "label": field.get("label", ""),
                    "type": field.get("type", "text"),
                    "purpose": group_name,
                    "importance": field_importance.get(field_id, "medium"),
                    "required": field.get("required", False),
                    "validation": field.get("validation", ""),
                    "dependencies": field_relationships.get(field_id, []),
                    "selector_strategies": self._generate_selector_strategies(field)
                }
                
                section["fields"].append(field_info)
            
            sections.append(section)
        
        return sections
    
    def _analyze_navigation(self, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze form navigation structure."""
        navigation = {
            "multi_page": False,
            "navigation_elements": []
        }
        
        # Check for navigation elements
        form_elements = form_data.get("form_elements", [])
        for element in form_elements:
            # Get element attributes safely
            element_type = (element.get("type") or "").lower()
            element_label = (element.get("label") or "").lower()
            element_name = (element.get("name") or "").lower()
            element_selector = element.get("selector", "")
            
            # Check for submit buttons
            if element_type == "submit":
                navigation["navigation_elements"].append({
                    "label": element.get("label") or "Submit",
                    "purpose": "submit",
                    "selector": element_selector
                })
            # Check for navigation buttons
            elif any(term in element_label or term in element_name for term in ["next", "continue", "previous", "back"]):
                navigation["multi_page"] = True
                navigation["navigation_elements"].append({
                    "label": element.get("label", ""),
                    "purpose": "next" if "next" in element_label or "continue" in element_label else "previous",
                    "selector": element_selector
                })
        
        return navigation
    
    def _extract_validation_rules(self, form_elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract validation rules for form fields."""
        validation_rules = {}
        
        for field in form_elements:
            field_id = field.get("id")
            if not field_id:
                continue
                
            rules = {
                "required": field.get("required", False),
                "type": field.get("type", "text"),
                "pattern": field.get("pattern", ""),
                "min_length": field.get("minlength"),
                "max_length": field.get("maxlength")
            }
            
            # Add field-specific validation
            field_type = field.get("type", "").lower()
            if field_type == "email":
                rules["format"] = "email"
            elif field_type == "tel":
                rules["format"] = "phone"
            elif field_type == "url":
                rules["format"] = "url"
                
            validation_rules[field_id] = rules
        
        return validation_rules
    
    def _count_field_types(self, form_elements: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count occurrences of each field type."""
        type_counts = {}
        
        for field in form_elements:
            field_type = field.get("type", "text")
            type_counts[field_type] = type_counts.get(field_type, 0) + 1
        
        return type_counts
    
    def _analyze_frame_distribution(self, form_elements: List[Dict[str, Any]]) -> Dict[str, int]:
        """Analyze distribution of fields across frames."""
        frame_counts = {}
        
        for field in form_elements:
            frame = field.get("frame", "main")
            frame_counts[frame] = frame_counts.get(frame, 0) + 1
        
        return frame_counts
    
    def _generate_strategic_insights(
        self,
        form_elements: List[Dict[str, Any]],
        field_relationships: Dict[str, List[str]],
        job_details: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Generate strategic insights for form handling."""
        insights = []
        
        # Analyze form complexity
        total_fields = len(form_elements)
        required_fields = len([f for f in form_elements if f.get("required", False)])
        custom_dropdowns = len([f for f in form_elements if f.get("type") == "select"])
        
        if total_fields > 30:
            insights.append(f"Complex form with {total_fields} fields - consider breaking into logical chunks")
            
        if required_fields / total_fields > 0.8:
            insights.append(f"High proportion of required fields ({required_fields}/{total_fields})")
            
        if custom_dropdowns > 5:
            insights.append(f"Form contains {custom_dropdowns} dropdowns - prepare for extensive option matching")
            
        # Check for potential challenges
        frame_distribution = self._analyze_frame_distribution(form_elements)
        if len(frame_distribution) > 1:
            insights.append(f"Form spans {len(frame_distribution)} frames - careful frame management required")
            
        if field_relationships:
            insights.append(f"Found {len(field_relationships)} field dependencies - handle in correct order")
            
        # Job-specific insights
        if job_details:
            job_title = job_details.get("title", "").lower()
            if "senior" in job_title or "staff" in job_title:
                insights.append("Senior position - emphasize leadership and advanced technical skills")
            elif "engineer" in job_title:
                insights.append("Technical role - focus on relevant technical experience and skills")
        
        return insights
    
    def _generate_selector_strategies(self, field: Dict[str, Any]) -> List[str]:
        """Generate selector strategies for a field."""
        strategies = []
        
        # Start with provided selector
        if field.get("selector"):
            strategies.append(field["selector"])
            
        # Add ID-based selector if available
        if field.get("id"):
            strategies.append(f"#{field['id']}")
            
        # Add name-based selector if available
        if field.get("name"):
            strategies.append(f"[name='{field['name']}']")
            
        # Add label-based selector if available
        if field.get("label"):
            strategies.append(f"label:has-text('{field['label']}')")
            
        # Add role-based selector for special elements
        if field.get("role"):
            strategies.append(f"[role='{field['role']}']")
            
        return strategies

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