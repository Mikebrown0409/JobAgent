"""Tools for formatting and validating form data."""

import re
import logging
from typing import Dict, Any, Optional, Union
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Result of data validation."""
    is_valid: bool
    formatted_value: Any = None
    error_message: str = None

class DataFormatter:
    """Formats and validates form data."""
    
    def __init__(self, diagnostics_manager=None):
        """
        Initialize the data formatter.
        
        Args:
            diagnostics_manager: Optional diagnostics manager
        """
        self.logger = logging.getLogger(__name__)
        self.diagnostics_manager = diagnostics_manager
        
        # Common validation patterns
        self.patterns = {
            "email": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
            "phone": r"^\+?1?\d{9,15}$",
            "url": r"^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)$",
            "date": r"^\d{4}-\d{2}-\d{2}$"
        }
    
    def format_text(self, value: str, max_length: Optional[int] = None) -> ValidationResult:
        """
        Format and validate text input.
        
        Args:
            value: Input text
            max_length: Optional maximum length
            
        Returns:
            ValidationResult
        """
        if not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                error_message=f"Expected string, got {type(value)}"
            )
        
        # Strip whitespace
        formatted = value.strip()
        
        # Check length
        if max_length and len(formatted) > max_length:
            return ValidationResult(
                is_valid=False,
                error_message=f"Text exceeds maximum length of {max_length}"
            )
        
        return ValidationResult(
            is_valid=True,
            formatted_value=formatted
        )
    
    def format_email(self, value: str) -> ValidationResult:
        """Format and validate email address."""
        if not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                error_message=f"Expected string, got {type(value)}"
            )
        
        # Normalize
        email = value.strip().lower()
        
        # Validate format
        if not re.match(self.patterns["email"], email):
            return ValidationResult(
                is_valid=False,
                error_message="Invalid email format"
            )
        
        return ValidationResult(
            is_valid=True,
            formatted_value=email
        )
    
    def format_phone(self, value: str) -> ValidationResult:
        """Format and validate phone number."""
        if not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                error_message=f"Expected string, got {type(value)}"
            )
        
        # Remove non-numeric characters
        phone = re.sub(r"\D", "", value)
        
        # Validate format
        if not re.match(self.patterns["phone"], phone):
            return ValidationResult(
                is_valid=False,
                error_message="Invalid phone number format"
            )
        
        # Format as +X-XXX-XXX-XXXX
        if len(phone) == 10:  # US number without country code
            phone = f"+1-{phone[:3]}-{phone[3:6]}-{phone[6:]}"
        elif len(phone) == 11 and phone.startswith("1"):  # US number with country code
            phone = f"+{phone[0]}-{phone[1:4]}-{phone[4:7]}-{phone[7:]}"
        
        return ValidationResult(
            is_valid=True,
            formatted_value=phone
        )
    
    def format_date(self, value: Union[str, datetime]) -> ValidationResult:
        """Format and validate date."""
        try:
            if isinstance(value, str):
                # Try parsing various formats
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"]:
                    try:
                        date = datetime.strptime(value, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    return ValidationResult(
                        is_valid=False,
                        error_message="Invalid date format"
                    )
            elif isinstance(value, datetime):
                date = value
            else:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Expected string or datetime, got {type(value)}"
                )
            
            # Format as YYYY-MM-DD
            formatted = date.strftime("%Y-%m-%d")
            
            return ValidationResult(
                is_valid=True,
                formatted_value=formatted
            )
            
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                error_message=f"Error formatting date: {str(e)}"
            )
    
    def format_select_value(self, value: str, options: list) -> ValidationResult:
        """
        Format and validate select field value.
        
        Args:
            value: Selected value
            options: List of valid options
            
        Returns:
            ValidationResult
        """
        if not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                error_message=f"Expected string, got {type(value)}"
            )
        
        formatted = value.strip()
        
        # Case-insensitive match
        formatted_options = [opt.strip().lower() for opt in options]
        if formatted.lower() not in formatted_options:
            return ValidationResult(
                is_valid=False,
                error_message=f"Value '{formatted}' not in options: {options}"
            )
        
        # Use original case from options
        formatted = options[formatted_options.index(formatted.lower())]
        
        return ValidationResult(
            is_valid=True,
            formatted_value=formatted
        )
    
    def format_field_value(
        self,
        field_type: str,
        value: Any,
        validation_rules: Optional[Dict[str, Any]] = None,
        options: Optional[list] = None
    ) -> ValidationResult:
        """
        Format and validate a field value based on its type and rules.
        
        Args:
            field_type: Type of field (text, email, phone, etc.)
            value: Value to format
            validation_rules: Optional validation rules
            options: Optional list of valid options for select fields
            
        Returns:
            ValidationResult
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage("format_field")
            
        try:
            # Handle empty values
            if value is None or (isinstance(value, str) and not value.strip()):
                return ValidationResult(
                    is_valid=True,
                    formatted_value=""
                )
            
            # Format based on field type
            field_type = field_type.lower()
            if field_type == "email":
                result = self.format_email(value)
            elif field_type == "phone":
                result = self.format_phone(value)
            elif field_type == "date":
                result = self.format_date(value)
            elif field_type in ["select", "multiselect"] and options:
                result = self.format_select_value(value, options)
            else:  # Default to text
                max_length = validation_rules.get("max_length") if validation_rules else None
                result = self.format_text(value, max_length)
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    result.is_valid,
                    details={
                        "field_type": field_type,
                        "original_value": value,
                        "formatted_value": result.formatted_value if result.is_valid else None,
                        "error": result.error_message if not result.is_valid else None
                    }
                )
            
            return result
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    False,
                    error=str(e)
                )
            self.logger.error(f"Error formatting field value: {e}")
            return ValidationResult(
                is_valid=False,
                error_message=f"Error formatting value: {str(e)}"
            )
    
    def format_form_data(
        self,
        data: Dict[str, Any],
        field_types: Dict[str, str],
        validation_rules: Optional[Dict[str, Dict[str, Any]]] = None,
        select_options: Optional[Dict[str, list]] = None
    ) -> Dict[str, ValidationResult]:
        """
        Format and validate a complete form data dictionary.
        
        Args:
            data: Dictionary of field values
            field_types: Dictionary mapping field IDs to their types
            validation_rules: Optional dictionary of validation rules per field
            select_options: Optional dictionary of options for select fields
            
        Returns:
            Dictionary mapping field IDs to their ValidationResults
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage("format_form")
            
        try:
            results = {}
            
            for field_id, value in data.items():
                if field_id not in field_types:
                    results[field_id] = ValidationResult(
                        is_valid=False,
                        error_message=f"Unknown field: {field_id}"
                    )
                    continue
                
                field_type = field_types[field_id]
                field_rules = validation_rules.get(field_id, {}) if validation_rules else {}
                field_options = select_options.get(field_id, []) if select_options else None
                
                results[field_id] = self.format_field_value(
                    field_type,
                    value,
                    field_rules,
                    field_options
                )
            
            if self.diagnostics_manager:
                valid_count = sum(1 for r in results.values() if r.is_valid)
                self.diagnostics_manager.end_stage(
                    all(r.is_valid for r in results.values()),
                    details={
                        "total_fields": len(results),
                        "valid_fields": valid_count,
                        "invalid_fields": len(results) - valid_count
                    }
                )
            
            return results
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    False,
                    error=str(e)
                )
            self.logger.error(f"Error formatting form data: {e}")
            return {
                field_id: ValidationResult(
                    is_valid=False,
                    error_message=f"Error formatting form data: {str(e)}"
                )
                for field_id in data
            } 