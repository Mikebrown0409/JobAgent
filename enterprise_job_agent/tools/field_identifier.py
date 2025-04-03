"""Tools for identifying and analyzing form fields in job applications."""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum, auto

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
    """Information about a form field."""
    field_id: str
    field_type: FieldType
    label: str
    required: bool
    options: List[str] = None
    validation: Dict[str, Any] = None
    importance: str = "medium"  # high, medium, low

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
                field_id=field_id,
                field_type=field_type,
                label=label,
                required=required,
                options=options,
                validation=validation,
                importance=importance
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
                    field.field_id: field.field_type.name
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
            field_id=field_data.get("id", ""),
            field_type=field_type,
            label=label,
            required=required,
            options=None,
            validation=validation_rules,
            importance=importance
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