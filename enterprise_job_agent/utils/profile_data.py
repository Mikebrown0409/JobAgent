"""Utilities for working with user profile data."""

import json
import logging
import os
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class ProfileManager:
    """
    Manages user profile data for job applications.
    """
    
    def __init__(self, profile_path: str):
        """
        Initialize with path to profile JSON file.
        
        Args:
            profile_path: Path to the profile JSON file.
        """
        self.profile_path = profile_path
        self.profile = self._load_profile()
    
    def _load_profile(self) -> Dict[str, Any]:
        """
        Load profile from JSON file.
        
        Returns:
            The profile data as a dictionary.
        """
        try:
            if os.path.exists(self.profile_path):
                with open(self.profile_path, 'r') as f:
                    profile = json.load(f)
                logger.info(f"Loaded profile from {self.profile_path}")
                return profile
            else:
                logger.warning(f"Profile file not found: {self.profile_path}")
                return self._create_empty_profile()
        except Exception as e:
            logger.error(f"Error loading profile: {e}")
            return self._create_empty_profile()
    
    def _create_empty_profile(self) -> Dict[str, Any]:
        """
        Create an empty profile structure.
        
        Returns:
            An empty profile dictionary.
        """
        return {
            "personal": {
                "first_name": "",
                "last_name": "",
                "email": "",
                "phone": "",
                "address": "",
                "city": "",
                "state": "",
                "zip": "",
                "country": "USA",
                "linkedin": "",
                "github": "",
                "website": ""
            },
            "experience": [],
            "education": [],
            "skills": [],
            "resume_path": "",
            "cover_letter_path": "",
            "preferences": {
                "job_type": "Full-time",
                "remote": True,
                "relocation": False,
                "salary_min": 120000,
                "start_date": "Immediately"
            }
        }
    
    def get_profile(self) -> Dict[str, Any]:
        """
        Get the profile data.
        
        Returns:
            The profile dictionary.
        """
        return self.profile
    
    def save_profile(self, profile: Dict[str, Any]) -> bool:
        """
        Save profile to JSON file.
        
        Args:
            profile: The profile data to save.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            with open(self.profile_path, 'w') as f:
                json.dump(profile, f, indent=2)
            logger.info(f"Saved profile to {self.profile_path}")
            self.profile = profile
            return True
        except Exception as e:
            logger.error(f"Error saving profile: {e}")
            return False
    
    def update_profile(self, updates: Dict[str, Any]) -> bool:
        """
        Update specific profile fields.
        
        Args:
            updates: Dictionary of updates to apply to the profile.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Apply updates recursively
            self._recursive_update(self.profile, updates)
            return self.save_profile(self.profile)
        except Exception as e:
            logger.error(f"Error updating profile: {e}")
            return False
    
    def _recursive_update(self, target: Dict[str, Any], updates: Dict[str, Any]) -> None:
        """
        Recursively update nested dictionaries.
        
        Args:
            target: The target dictionary to update.
            updates: The updates to apply.
        """
        for key, value in updates.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._recursive_update(target[key], value)
            else:
                target[key] = value
    
    def update_personal_info(self, personal_info: Dict[str, Any]) -> bool:
        """
        Update personal information in the profile.
        
        Args:
            personal_info: Dictionary with personal information
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.profile["personal"].update(personal_info)
            return True
        except Exception as e:
            logger.error(f"Error updating personal info: {e}")
            return False
    
    def add_education(self, education: Dict[str, Any]) -> bool:
        """
        Add education entry to the profile.
        
        Args:
            education: Dictionary with education information
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.profile["education"].append(education)
            return True
        except Exception as e:
            logger.error(f"Error adding education: {e}")
            return False
    
    def add_experience(self, experience: Dict[str, Any]) -> bool:
        """
        Add work experience entry to the profile.
        
        Args:
            experience: Dictionary with work experience information
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.profile["experience"].append(experience)
            return True
        except Exception as e:
            logger.error(f"Error adding experience: {e}")
            return False
    
    def add_skill(self, skill: str, category: str = "technical") -> bool:
        """
        Add a skill to the profile.
        
        Args:
            skill: Skill to add
            category: Skill category (technical, soft, languages)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if category in self.profile["skills"]:
                if skill not in self.profile["skills"][category]:
                    self.profile["skills"][category].append(skill)
                return True
            else:
                logger.error(f"Unknown skill category: {category}")
                return False
        except Exception as e:
            logger.error(f"Error adding skill: {e}")
            return False
    
    def update_document_path(self, doc_type: str, path: str) -> bool:
        """
        Update document path in the profile.
        
        Args:
            doc_type: Document type (resume, cover_letter, portfolio)
            path: Path to the document
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if doc_type in self.profile["documents"]:
                self.profile["documents"][doc_type] = path
                return True
            elif doc_type == "additional":
                self.profile["documents"]["additional"].append(path)
                return True
            else:
                logger.error(f"Unknown document type: {doc_type}")
                return False
        except Exception as e:
            logger.error(f"Error updating document path: {e}")
            return False
    
    def get_field_value(self, field_path: str) -> Any:
        """
        Get a specific field value from the profile using dot notation.
        
        Args:
            field_path: Path to the field using dot notation (e.g., "personal.first_name")
            
        Returns:
            Value of the field or None if not found
        """
        try:
            parts = field_path.split('.')
            value = self.profile
            for part in parts:
                if part.isdigit() and isinstance(value, list):
                    value = value[int(part)]
                elif isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    logger.warning(f"Field path not found: {field_path}")
                    return None
            return value
        except Exception as e:
            logger.error(f"Error getting field value for {field_path}: {e}")
            return None
    
    def map_profile_to_form_fields(self, form_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Map profile data to form fields based on field labels.
        
        Args:
            form_fields: List of form field descriptions
            
        Returns:
            Dictionary mapping field IDs to values
        """
        field_mapping = {}
        
        # Common field mappings
        common_mappings = {
            "first name": "personal.first_name",
            "last name": "personal.last_name",
            "full name": lambda: f"{self.get_field_value('personal.first_name')} {self.get_field_value('personal.last_name')}",
            "email": "personal.email",
            "phone": "personal.phone",
            "address": lambda: f"{self.get_field_value('personal.address.street')}, {self.get_field_value('personal.address.city')}, {self.get_field_value('personal.address.state')} {self.get_field_value('personal.address.zip')}",
            "street": "personal.address.street",
            "city": "personal.address.city",
            "state": "personal.address.state",
            "zip": "personal.address.zip",
            "postal code": "personal.address.zip",
            "country": "personal.address.country",
            "linkedin": "personal.linkedin",
            "website": "personal.website",
            "github": "personal.github",
            "resume": "documents.resume"
        }
        
        for field in form_fields:
            field_id = field.get("id", "")
            field_label = field.get("label", "").lower()
            field_name = field.get("name", "").lower()
            
            # Try to match the field
            match_key = None
            
            # Check label
            for key in common_mappings:
                if key in field_label:
                    match_key = key
                    break
            
            # If no match in label, check name
            if not match_key and field_name:
                for key in common_mappings:
                    if key in field_name:
                        match_key = key
                        break
            
            # If we found a match, get the value
            if match_key:
                mapping = common_mappings[match_key]
                
                if callable(mapping):
                    field_mapping[field_id] = mapping()
                else:
                    field_mapping[field_id] = self.get_field_value(mapping)
        
        return field_mapping 