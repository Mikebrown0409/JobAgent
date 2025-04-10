"""Tools for identifying and analyzing form fields in job applications."""

import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum, auto
import re
import difflib
import asyncio

from playwright.async_api import Page, Frame, Locator, ElementHandle

logger = logging.getLogger(__name__)

class FieldType(Enum):
    """Types of form fields."""
    TEXT = auto()
    EMAIL = auto()
    PHONE = auto()
    DATE = auto()
    SELECT = auto()
    MULTISELECT = auto()
    CHECKBOX = auto()
    RADIO = auto()
    FILE = auto()
    TEXTAREA = auto()
    HIDDEN = auto()
    SUBMIT = auto()
    UNKNOWN = auto()

@dataclass
class FieldInfo:
    """Information about a detected form field."""
    selector: str
    field_type: str
    label: Optional[str] = None
    placeholder: Optional[str] = None
    required: bool = False
    visible: bool = True
    options: Optional[List[str]] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    autocomplete: Optional[str] = None
    id: Optional[str] = None
    name: Optional[str] = None
    frame_id: Optional[str] = None

class FieldIdentifier:
    """Identifies and analyzes form fields for job applications."""
    
    def __init__(self, diagnostics_manager=None):
        """
        Initialize the field identifier.
        
        Args:
            diagnostics_manager: Optional diagnostics manager
        """
        self.logger = logging.getLogger(__name__)
        self.diagnostics_manager = diagnostics_manager
        
        # Common field patterns
        self.field_patterns = {
            "name": {
                "keywords": ["name", "full name", "first name", "last name"],
                "importance": "high",
                "type": FieldType.TEXT
            },
            "email": {
                "keywords": ["email", "e-mail", "email address"],
                "importance": "high",
                "type": FieldType.EMAIL
            },
            "phone": {
                "keywords": ["phone", "telephone", "mobile", "cell"],
                "importance": "high",
                "type": FieldType.PHONE
            },
            "education": {
                "keywords": ["education", "school", "university", "degree", "qualification"],
                "importance": "high",
                "type": FieldType.TEXT
            },
            "experience": {
                "keywords": ["experience", "work history", "employment"],
                "importance": "high",
                "type": FieldType.TEXTAREA
            },
            "skills": {
                "keywords": ["skills", "technologies", "programming languages"],
                "importance": "high",
                "type": FieldType.TEXT
            },
            "location": {
                "keywords": ["location", "city", "state", "country", "address"],
                "importance": "medium",
                "type": FieldType.TEXT
            }
        }
    
    def identify_field_type(self, element: Dict[str, Any]) -> FieldType:
        """
        Identify the type of a form field.
        
        Args:
            element: Form element data
            
        Returns:
            FieldType enum value
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage("identify_field_type")
            
        try:
            # Check element type
            el_type = element.get("type", "").lower()
            tag_name = element.get("tagName", "").lower()
            
            # Map HTML types to FieldTypes
            type_mapping = {
                "text": FieldType.TEXT,
                "email": FieldType.EMAIL,
                "tel": FieldType.PHONE,
                "date": FieldType.DATE,
                "select": FieldType.SELECT,
                "select-multiple": FieldType.MULTISELECT,
                "checkbox": FieldType.CHECKBOX,
                "radio": FieldType.RADIO,
                "file": FieldType.FILE,
                "textarea": FieldType.TEXTAREA,
                "hidden": FieldType.HIDDEN,
                "submit": FieldType.SUBMIT
            }
            
            field_type = type_mapping.get(el_type, None)
            if field_type:
                if self.diagnostics_manager:
                    self.diagnostics_manager.end_stage(True, details={"method": "type_attribute"})
                return field_type
            
            # Check tag name
            if tag_name == "select":
                multiple = element.get("multiple", False)
                if self.diagnostics_manager:
                    self.diagnostics_manager.end_stage(True, details={"method": "tag_name"})
                return FieldType.MULTISELECT if multiple else FieldType.SELECT
            
            if tag_name == "textarea":
                if self.diagnostics_manager:
                    self.diagnostics_manager.end_stage(True, details={"method": "tag_name"})
                return FieldType.TEXTAREA
            
            # Check role attribute
            role = element.get("role", "").lower()
            role_mapping = {
                "combobox": FieldType.SELECT,
                "listbox": FieldType.SELECT,
                "checkbox": FieldType.CHECKBOX,
                "radio": FieldType.RADIO
            }
            
            field_type = role_mapping.get(role, None)
            if field_type:
                if self.diagnostics_manager:
                    self.diagnostics_manager.end_stage(True, details={"method": "role_attribute"})
                return field_type
            
            # Default to text if no other type identified
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(True, details={"method": "default"})
            return FieldType.TEXT
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    False,
                    error=str(e)
                )
            self.logger.error(f"Error identifying field type: {e}")
            return FieldType.UNKNOWN
    
    def analyze_field(self, element: Dict[str, Any]) -> FieldInfo:
        """
        Analyze a form field and extract its information.
        
        Args:
            element: Form element data
            
        Returns:
            FieldInfo object
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage("analyze_field")
            
        try:
            # Get basic field info
            field_id = element.get("id", "") or element.get("name", "")
            field_type = self.identify_field_type(element)
            label = element.get("label", "") or element.get("placeholder", "")
            required = element.get("required", False) or "required" in element.get("aria-required", "")
            
            # Get options for select fields
            options = None
            if field_type in [FieldType.SELECT, FieldType.MULTISELECT]:
                options = [
                    opt.get("text", "")
                    for opt in element.get("options", [])
                ]
            
            # Get validation rules
            validation = {}
            if "pattern" in element:
                validation["pattern"] = element["pattern"]
            if "minLength" in element:
                validation["min_length"] = element["minLength"]
            if "maxLength" in element:
                validation["max_length"] = element["maxLength"]
            
            # Determine importance
            importance = "medium"
            if required:
                importance = "high"
            else:
                # Check against known field patterns
                label_lower = label.lower()
                for pattern in self.field_patterns.values():
                    if any(keyword in label_lower for keyword in pattern["keywords"]):
                        importance = pattern["importance"]
                        break
            
            field_info = FieldInfo(
                selector=field_id,
                field_type=field_type.name,
                label=label,
                placeholder=element.get("placeholder"),
                required=required,
                visible=True,
                options=options,
                min_length=validation.get("min_length"),
                max_length=validation.get("max_length"),
                pattern=validation.get("pattern"),
                autocomplete=element.get("autocomplete"),
                id=field_id,
                name=field_id,
                frame_id=None
            )
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(True, details={
                    "field_id": field_id,
                    "field_type": field_type.name,
                    "importance": importance
                })
            
            return field_info
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    False,
                    error=str(e)
                )
            self.logger.error(f"Error analyzing field: {e}")
            return None
    
    def create_application_strategy(
        self,
        form_elements: List[Dict[str, Any]],
        user_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create an application strategy for a form.
        
        Args:
            form_elements: List of form elements
            user_profile: User profile data
            
        Returns:
            Dictionary with application strategy
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage("create_strategy")
            
        try:
            # Analyze all fields
            fields = []
            for element in form_elements:
                field_info = self.analyze_field(element)
                if field_info:
                    fields.append(field_info)
            
            # Group fields by importance
            high_priority = []
            medium_priority = []
            low_priority = []
            
            for field in fields:
                if field.importance == "high":
                    high_priority.append(field)
                elif field.importance == "medium":
                    medium_priority.append(field)
                else:
                    low_priority.append(field)
            
            # Create strategy
            strategy = {
                "required_fields": [
                    field.field_id for field in fields if field.required
                ],
                "field_priorities": {
                    "high": [field.field_id for field in high_priority],
                    "medium": [field.field_id for field in medium_priority],
                    "low": [field.field_id for field in low_priority]
                },
                "field_types": {
                    field.field_id: field.field_type
                    for field in fields
                },
                "validation_rules": {
                    field.field_id: field.validation
                    for field in fields
                    if field.validation
                },
                "select_options": {
                    field.field_id: field.options
                    for field in fields
                    if field.options
                }
            }
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(True, details={
                    "total_fields": len(fields),
                    "required_fields": len(strategy["required_fields"])
                })
            
            return strategy
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    False,
                    error=str(e)
                )
            self.logger.error(f"Error creating application strategy: {e}")
            return {
                "error": str(e),
                "form_elements": len(form_elements),
                "profile_fields": len(user_profile)
            }

    def identify_field(self, field_data: Dict[str, Any]) -> FieldInfo:
        """Identify field type and requirements from field data.
        
        Args:
            field_data: Raw field data from form analysis
            
        Returns:
            FieldInfo object with field type and requirements
        """
        # Extract basic field properties
        field_type = self._determine_field_type(field_data)
        label = field_data.get("label", "")
        required = field_data.get("required", False)
        
        # Calculate field importance
        importance = self._calculate_importance(field_data)
        
        # Extract validation rules
        validation_rules = self._extract_validation_rules(field_data)
        
        return FieldInfo(
            selector=field_data.get("id", ""),
            field_type=field_type.name,
            label=label,
            placeholder=field_data.get("placeholder"),
            required=required,
            visible=True,
            options=None,
            min_length=validation_rules.get("min_length"),
            max_length=validation_rules.get("max_length"),
            pattern=validation_rules.get("pattern"),
            autocomplete=field_data.get("autocomplete"),
            id=field_data.get("id"),
            name=field_data.get("name"),
            frame_id=None
        )
    
    def _determine_field_type(self, field_data: Dict[str, Any]) -> FieldType:
        """Determine the type of field from its properties."""
        # Check explicit type first
        field_type = field_data.get("type", "").lower()
        tag_name = field_data.get("tag", "").lower()
        
        # Handle select elements
        if tag_name == "select" or field_type == "select":
            return FieldType.SELECT
            
        # Handle textareas
        if tag_name == "textarea" or field_type == "textarea":
            return FieldType.TEXTAREA
            
        # Handle checkboxes
        if field_type == "checkbox":
            return FieldType.CHECKBOX
            
        # Handle radio buttons
        if field_type == "radio":
            return FieldType.RADIO
            
        # Handle file inputs
        if field_type == "file":
            return FieldType.FILE
            
        # Handle hidden inputs
        if field_type == "hidden":
            return FieldType.HIDDEN
            
        # Handle submit buttons
        if field_type == "submit":
            return FieldType.SUBMIT
            
        # Default to text for regular inputs
        if tag_name == "input" or field_type == "text":
            return FieldType.TEXT
            
        return FieldType.UNKNOWN
    
    def _calculate_importance(self, field_data: Dict[str, Any]) -> float:
        """Calculate the importance score for a field."""
        importance = 0.0
        
        # Required fields are more important
        if field_data.get("required", False):
            importance += 0.5
            
        # Fields with labels are more important
        if field_data.get("label"):
            importance += 0.2
            
        # Fields with validation are more important
        if field_data.get("validation_rules"):
            importance += 0.2
            
        # Visible fields are more important than hidden
        if field_data.get("type") != "hidden":
            importance += 0.1
            
        return min(importance, 1.0)
    
    def _extract_validation_rules(self, field_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract validation rules from field data."""
        rules = {}
        
        # Get basic HTML validation attributes
        if "minlength" in field_data:
            rules["min_length"] = field_data["minlength"]
        if "maxlength" in field_data:
            rules["max_length"] = field_data["maxlength"]
        if "pattern" in field_data:
            rules["pattern"] = field_data["pattern"]
            
        # Get custom validation rules
        if "validation_rules" in field_data:
            rules.update(field_data["validation_rules"])
            
        return rules

class FieldDetector:
    """Advanced field detection for job application forms."""
    
    def __init__(self, page: Page, debug_mode: bool = False):
        """Initialize field detector.
        
        Args:
            page: The Playwright page to use
            debug_mode: Whether to enable detailed logging
        """
        self.page = page
        self.debug_mode = debug_mode
        self.logger = logger
        
    async def find_field_by_name(
        self,
        field_name: str,
        frame: Optional[Frame] = None,
        field_types: Optional[List[str]] = None
    ) -> Optional[Tuple[str, Locator]]:
        """
        Find a form field by name using multiple detection strategies.
        
        Args:
            field_name: The name or label text to find
            frame: Optional frame to search in (uses page if None)
            field_types: Optional list of field types to search for
            
        Returns:
            Tuple of (selector, locator) if found, None otherwise
        """
        self.logger.debug(f"Finding field by name: '{field_name}'")
        
        if not field_name:
            self.logger.error("Cannot find field: field_name is empty")
            return None
            
        # Use the provided frame or default to page
        context = frame or self.page
        
        # Normalize field name for better matching
        cleaned_name = self._clean_field_name(field_name).lower()
        self.logger.debug(f"Cleaned field name: '{cleaned_name}'")
        
        # Prepare type constraints for selectors
        type_constraint = ""
        if field_types and len(field_types) > 0:
            type_constraint = ",".join(field_types)
        else:
            type_constraint = "input,select,textarea,*[contenteditable='true']"
            
        # Strategy 1: Try to find by ID or name attribute containing the cleaned field name
        self.logger.debug(f"Strategy 1: Searching by ID/name containing '{cleaned_name}'")
        try:
            # Create selector that matches ID or name attributes
            id_selector = f"{type_constraint}[id*='{cleaned_name}' i], {type_constraint}[name*='{cleaned_name}' i]"
            element = await context.query_selector(id_selector)
            if element:
                selector = await element.get_attribute("id") or await element.get_attribute("name")
                if selector:
                    selector_str = f"#{selector}" if await element.get_attribute("id") else f"[name='{selector}']"
                    self.logger.info(f"Found field by ID/name: {selector_str}")
                    return (selector_str, context.locator(selector_str))
        except Exception as e:
            self.logger.debug(f"Error in strategy 1: {e}")
            
        # Strategy 2: Try to find by placeholder text
        self.logger.debug(f"Strategy 2: Searching by placeholder containing '{cleaned_name}'")
        try:
            placeholder_selector = f"{type_constraint}[placeholder*='{cleaned_name}' i]"
            element = await context.query_selector(placeholder_selector)
            if element:
                self.logger.info(f"Found field by placeholder: {placeholder_selector}")
                return (placeholder_selector, context.locator(placeholder_selector))
        except Exception as e:
            self.logger.debug(f"Error in strategy 2: {e}")
            
        # Strategy 3: Try to find by aria-label, title, or data attributes
        self.logger.debug(f"Strategy 3: Searching by aria-label/title containing '{cleaned_name}'")
        try:
            aria_selector = f"{type_constraint}[aria-label*='{cleaned_name}' i], " + \
                           f"{type_constraint}[title*='{cleaned_name}' i], " + \
                           f"{type_constraint}[data-field*='{cleaned_name}' i]"
            element = await context.query_selector(aria_selector)
            if element:
                self.logger.info(f"Found field by aria attributes: {aria_selector}")
                return (aria_selector, context.locator(aria_selector))
        except Exception as e:
            self.logger.debug(f"Error in strategy 3: {e}")
            
        # Strategy 4: Try to find by associated label
        self.logger.debug(f"Strategy 4: Searching by label text containing '{cleaned_name}'")
        try:
            # First find labels containing the field name
            label_selector = f"label:has-text('{cleaned_name}')"
            labels = await context.query_selector_all(label_selector)
            
            for label in labels:
                # Try 'for' attribute first
                for_id = await label.get_attribute("for")
                if for_id:
                    # Check if element with this ID exists
                    input_selector = f"#{for_id}"
                    input_element = await context.query_selector(input_selector)
                    if input_element:
                        self.logger.info(f"Found field by label 'for' attribute: {input_selector}")
                        return (input_selector, context.locator(input_selector))
                
                # Try nested input elements
                nested_input = await label.query_selector("input, select, textarea")
                if nested_input:
                    input_id = await nested_input.get_attribute("id")
                    if input_id:
                        input_selector = f"#{input_id}"
                        self.logger.info(f"Found field by nested input: {input_selector}")
                        return (input_selector, context.locator(input_selector))
                        
                    input_name = await nested_input.get_attribute("name")
                    if input_name:
                        input_selector = f"[name='{input_name}']"
                        self.logger.info(f"Found field by nested input name: {input_selector}")
                        return (input_selector, context.locator(input_selector))
                
                # Try nearby inputs (following the label)
                try:
                    # Use JS to find the nearest input after this label
                    js_script = """
                    (labelEl) => {
                        // Helper to find inputs in or after an element
                        function findFieldAfter(el) {
                            // Check inside first
                            let field = el.querySelector('input, select, textarea');
                            if (field) return field;
                            
                            // Check siblings
                            let sibling = el.nextElementSibling;
                            while (sibling) {
                                if (sibling.tagName === 'INPUT' || 
                                    sibling.tagName === 'SELECT' || 
                                    sibling.tagName === 'TEXTAREA') {
                                    return sibling;
                                }
                                
                                // Check inside sibling
                                field = sibling.querySelector('input, select, textarea');
                                if (field) return field;
                                
                                sibling = sibling.nextElementSibling;
                            }
                            
                            // Check parent next sibling if no luck
                            if (el.parentElement) {
                                sibling = el.parentElement.nextElementSibling;
                                while (sibling) {
                                    if (sibling.tagName === 'INPUT' || 
                                        sibling.tagName === 'SELECT' || 
                                        sibling.tagName === 'TEXTAREA') {
                                        return sibling;
                                    }
                                    
                                    // Check inside sibling
                                    field = sibling.querySelector('input, select, textarea');
                                    if (field) return field;
                                    
                                    sibling = sibling.nextElementSibling;
                                }
                            }
                            
                            return null;
                        }
                        
                        // Find field after this label
                        const field = findFieldAfter(labelEl);
                        if (!field) return null;
                        
                        // Return field info
                        return {
                            tagName: field.tagName.toLowerCase(),
                            id: field.id || '',
                            name: field.name || '',
                            type: field.type || ''
                        };
                    }
                    """
                    
                    result = await label.evaluate(js_script)
                    if result:
                        if result.get('id'):
                            input_selector = f"#{result['id']}"
                            element = await context.query_selector(input_selector)
                            if element:
                                self.logger.info(f"Found field after label using ID: {input_selector}")
                                return (input_selector, context.locator(input_selector))
                        elif result.get('name'):
                            input_selector = f"[name='{result['name']}']"
                            element = await context.query_selector(input_selector)
                            if element:
                                self.logger.info(f"Found field after label using name: {input_selector}")
                                return (input_selector, context.locator(input_selector))
                except Exception as js_error:
                    self.logger.debug(f"Error in JS label search: {js_error}")
        except Exception as e:
            self.logger.debug(f"Error in strategy 4: {e}")
            
        # Strategy 5: Try generic approaches for simple forms
        self.logger.debug(f"Strategy 5: Trying generic approaches for simple forms")
        try:
            # For forms with few fields, look for any visible field that might match
            inputs = await context.query_selector_all(f"{type_constraint}")
            visible_inputs = []
            
            # Filter for visible inputs
            for input_el in inputs:
                try:
                    is_visible = await input_el.is_visible()
                    if is_visible:
                        visible_inputs.append(input_el)
                except Exception:
                    continue
                    
            # If there's only one visible input, it might be what we want
            if len(visible_inputs) == 1:
                input_id = await visible_inputs[0].get_attribute("id")
                if input_id:
                    input_selector = f"#{input_id}"
                    self.logger.info(f"Found single visible input: {input_selector}")
                    return (input_selector, context.locator(input_selector))
                    
                input_name = await visible_inputs[0].get_attribute("name")
                if input_name:
                    input_selector = f"[name='{input_name}']"
                    self.logger.info(f"Found single visible input by name: {input_selector}")
                    return (input_selector, context.locator(input_selector))
                    
            # For forms with few fields, try matching by attributes
            if len(visible_inputs) < 5:
                for input_el in visible_inputs:
                    # Check various attributes for the field name
                    for attr in ["id", "name", "placeholder", "aria-label", "title"]:
                        attr_value = await input_el.get_attribute(attr)
                        if attr_value and (cleaned_name in attr_value.lower() or self._similar_strings(cleaned_name, attr_value.lower())):
                            # Found a potential match
                            if attr == "id":
                                input_selector = f"#{attr_value}"
                                self.logger.info(f"Found field by attribute match (id): {input_selector}")
                                return (input_selector, context.locator(input_selector))
                            elif attr == "name":
                                input_selector = f"[name='{attr_value}']"
                                self.logger.info(f"Found field by attribute match (name): {input_selector}")
                                return (input_selector, context.locator(input_selector))
                            else:
                                input_id = await input_el.get_attribute("id")
                                if input_id:
                                    input_selector = f"#{input_id}"
                                    self.logger.info(f"Found field by {attr} match, using ID: {input_selector}")
                                    return (input_selector, context.locator(input_selector))
                                else:
                                    input_selector = f"[{attr}='{attr_value}']"
                                    self.logger.info(f"Found field by attribute match ({attr}): {input_selector}")
                                    return (input_selector, context.locator(input_selector))
        except Exception as e:
            self.logger.debug(f"Error in strategy 5: {e}")
            
        self.logger.warning(f"Could not find field with name: '{field_name}'")
        return None
            
    def _clean_field_name(self, field_name: str) -> str:
        """Clean field name for better matching."""
        # Convert to lowercase and remove punctuation
        cleaned = re.sub(r'[^\w\s]', '', field_name)
        # Replace spaces with common field name separators
        cleaned = re.sub(r'\s+', '_', cleaned)
        return cleaned
        
    def _similar_strings(self, str1: str, str2: str, threshold: float = 0.7) -> bool:
        """Check if two strings are similar using fuzzy matching."""
        if not str1 or not str2:
            return False
            
        # Direct contains check
        if str1 in str2 or str2 in str1:
            return True
            
        # Check similarity ratio
        similarity = difflib.SequenceMatcher(None, str1, str2).ratio()
        return similarity >= threshold
    
    async def get_dropdown_options(self, field_selector: str, frame: Optional[Frame] = None) -> List[str]:
        """
        Get the available options for a dropdown field.
        
        Args:
            field_selector: The selector for the dropdown field
            frame: Optional frame to search in
            
        Returns:
            List of option text values
        """
        context = frame or self.page
        options = []
        
        try:
            # Try to get options from standard select element
            option_elements = await context.query_selector_all(f"{field_selector} option")
            if option_elements and len(option_elements) > 0:
                for option in option_elements:
                    option_text = await option.text_content()
                    if option_text and option_text.strip():
                        options.append(option_text.strip())
                return options
                
            # If no options found, try clicking the element to open dropdown
            field = await context.query_selector(field_selector)
            if field:
                await field.click()
                await asyncio.sleep(0.3)  # Wait for dropdown to appear
                
                # Try various option selectors
                for option_selector in [
                    "li[role='option']", 
                    ".dropdown-item", 
                    "[role='option']", 
                    ".select-option",
                    "li"
                ]:
                    option_elements = await context.query_selector_all(option_selector)
                    if option_elements and len(option_elements) > 0:
                        for option in option_elements:
                            option_text = await option.text_content()
                            if option_text and option_text.strip():
                                options.append(option_text.strip())
                        
                        # Close dropdown by clicking elsewhere
                        try:
                            await context.click("body", position={"x": 0, "y": 0})
                        except Exception:
                            pass
                            
                        if options:
                            return options
                
                # If we still don't have options, try JavaScript
                js_script = """
                () => {
                    const getVisibleOptions = () => {
                        return Array.from(document.querySelectorAll(
                            'li, [role="option"], .dropdown-item, .select-option, option'
                        )).filter(el => {
                            const style = window.getComputedStyle(el);
                            return style.display !== 'none' && style.visibility !== 'hidden';
                        }).map(el => el.textContent.trim());
                    };
                    
                    return getVisibleOptions().filter(text => text.length > 0);
                }
                """
                js_options = await context.evaluate(js_script)
                if js_options and len(js_options) > 0:
                    return js_options
        except Exception as e:
            self.logger.error(f"Error getting dropdown options for {field_selector}: {e}")
            
        return options
        
    async def analyze_field(self, field_selector: str, frame: Optional[Frame] = None) -> Optional[FieldInfo]:
        """
        Analyze a form field to extract its properties.
        
        Args:
            field_selector: The selector for the field
            frame: Optional frame to search in
            
        Returns:
            FieldInfo object with field properties
        """
        context = frame or self.page
        
        try:
            element = await context.query_selector(field_selector)
            if not element:
                self.logger.warning(f"Field not found: {field_selector}")
                return None
                
            # Get element tag name
            tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
            
            # Determine field type
            field_type = "text"  # Default
            if tag_name == "select":
                field_type = "select"
            elif tag_name == "textarea":
                field_type = "textarea"
            elif tag_name == "input":
                input_type = await element.get_attribute("type")
                field_type = input_type or "text"
                
            # Check if required
            required = await element.get_attribute("required") is not None
            
            # Check if visible
            visible = await element.is_visible()
            
            # Get field attributes
            id_attr = await element.get_attribute("id")
            name_attr = await element.get_attribute("name")
            placeholder = await element.get_attribute("placeholder")
            min_length = await element.get_attribute("minlength")
            max_length = await element.get_attribute("maxlength")
            pattern = await element.get_attribute("pattern")
            autocomplete = await element.get_attribute("autocomplete")
            
            # Get associated label text
            label_text = None
            if id_attr:
                label_element = await context.query_selector(f"label[for='{id_attr}']")
                if label_element:
                    label_text = await label_element.text_content()
                    if label_text:
                        label_text = label_text.strip()
                        
            # For select fields, get options
            options = None
            if field_type == "select" or "select" in field_type.lower():
                options = await self.get_dropdown_options(field_selector, frame)
                
            # Convert numeric attributes to integers
            min_length_int = int(min_length) if min_length and min_length.isdigit() else None
            max_length_int = int(max_length) if max_length and max_length.isdigit() else None
            
            return FieldInfo(
                selector=field_selector,
                field_type=field_type,
                label=label_text,
                placeholder=placeholder,
                required=required,
                visible=visible,
                options=options,
                min_length=min_length_int,
                max_length=max_length_int,
                pattern=pattern,
                autocomplete=autocomplete,
                id=id_attr,
                name=name_attr,
                frame_id=None
            )
        except Exception as e:
            self.logger.error(f"Error analyzing field {field_selector}: {e}")
            return None 