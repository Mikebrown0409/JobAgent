"""
Profile Store - User Profile Management

Handles loading, validation, and access to user profile data.
Uses Pydantic for schema validation and type safety.
"""

import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class ContactInfo(BaseModel):
    """Contact information model."""
    address: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None  # State/Province
    postalCode: Optional[str] = None
    country: Optional[str] = None


class WorkExperience(BaseModel):
    """Work experience model."""
    company: str
    position: str
    startDate: str
    endDate: Optional[str] = None
    summary: Optional[str] = None
    location: Optional[str] = None


class Education(BaseModel):
    """Education model."""
    institution: str
    area: str  # Field of study
    studyType: str  # Degree type
    startDate: str
    endDate: Optional[str] = None
    gpa: Optional[str] = None


class Skill(BaseModel):
    """Skill model."""
    name: str
    level: Optional[str] = None  # Beginner, Intermediate, Advanced, Expert
    keywords: Optional[list] = None


class Language(BaseModel):
    """Language model."""
    language: str
    fluency: str  # Native, Fluent, Conversational, Basic


class Basics(BaseModel):
    """Basic information model."""
    name: str
    email: str
    phone: Optional[str] = None
    location: Optional[ContactInfo] = None
    summary: Optional[str] = None
    website: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None


class UserProfile(BaseModel):
    """Complete user profile model."""
    basics: Basics
    work: Optional[list[WorkExperience]] = []
    education: Optional[list[Education]] = []
    skills: Optional[list[Skill]] = []
    languages: Optional[list[Language]] = []
    
    @field_validator('work', mode='before')
    @classmethod
    def validate_work(cls, v):
        if isinstance(v, list):
            return [WorkExperience(**item) if isinstance(item, dict) else item for item in v]
        return v
    
    @field_validator('education', mode='before')
    @classmethod
    def validate_education(cls, v):
        if isinstance(v, list):
            return [Education(**item) if isinstance(item, dict) else item for item in v]
        return v
    
    @field_validator('skills', mode='before')
    @classmethod
    def validate_skills(cls, v):
        if isinstance(v, list):
            return [Skill(**item) if isinstance(item, dict) else item for item in v]
        return v
    
    @field_validator('languages', mode='before')
    @classmethod
    def validate_languages(cls, v):
        if isinstance(v, list):
            return [Language(**item) if isinstance(item, dict) else item for item in v]
        return v


class ProfileStore:
    """
    Manages user profile data with validation and easy access methods.
    """
    
    def __init__(self, profile_path: str):
        """
        Initialize profile store.
        
        Args:
            profile_path: Path to the profile JSON file
        """
        self.profile_path = Path(profile_path)
        self.logger = logging.getLogger(__name__)
        self._profile: Optional[UserProfile] = None
        self._load_profile()
    
    def _load_profile(self) -> None:
        """Load and validate profile from file."""
        try:
            if not self.profile_path.exists():
                raise FileNotFoundError(f"Profile file not found: {self.profile_path}")
            
            with open(self.profile_path, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)
            
            # Validate using Pydantic model
            self._profile = UserProfile(**profile_data)
            self.logger.info(f"Profile loaded successfully from {self.profile_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to load profile: {str(e)}")
            raise
    
    def get_profile_data(self) -> Dict[str, Any]:
        """Get profile data as dictionary."""
        if not self._profile:
            raise ValueError("Profile not loaded")
        return self._profile.model_dump()
    
    def get_profile(self) -> UserProfile:
        """Get profile as Pydantic model."""
        if not self._profile:
            raise ValueError("Profile not loaded")
        return self._profile
    
    def get_basic_info(self) -> Dict[str, Any]:
        """Get basic contact information."""
        if not self._profile:
            raise ValueError("Profile not loaded")
        return self._profile.basics.model_dump()
    
    def get_name(self) -> str:
        """Get full name."""
        return self._profile.basics.name if self._profile else ""
    
    def get_email(self) -> str:
        """Get email address."""
        return self._profile.basics.email if self._profile else ""
    
    def get_phone(self) -> Optional[str]:
        """Get phone number."""
        return self._profile.basics.phone if self._profile else None
    
    def get_location(self) -> Dict[str, Any]:
        """Get location information."""
        if not self._profile or not self._profile.basics.location:
            return {}
        return self._profile.basics.location.model_dump()
    
    def get_work_experience(self) -> list[Dict[str, Any]]:
        """Get work experience list."""
        if not self._profile or not self._profile.work:
            return []
        return [exp.model_dump() for exp in self._profile.work]
    
    def get_education(self) -> list[Dict[str, Any]]:
        """Get education list."""
        if not self._profile or not self._profile.education:
            return []
        return [edu.model_dump() for edu in self._profile.education]
    
    def get_skills(self) -> list[Dict[str, Any]]:
        """Get skills list."""
        if not self._profile or not self._profile.skills:
            return []
        return [skill.model_dump() for skill in self._profile.skills]
    
    def get_languages(self) -> list[Dict[str, Any]]:
        """Get languages list."""
        if not self._profile or not self._profile.languages:
            return []
        return [lang.model_dump() for lang in self._profile.languages]
    
    def get_current_position(self) -> Optional[Dict[str, Any]]:
        """Get current/most recent work position."""
        work_exp = self.get_work_experience()
        if not work_exp:
            return None
        
        # Find current position (no end date) or most recent
        current = None
        for exp in work_exp:
            if not exp.get('endDate') or exp.get('endDate') == 'Present':
                current = exp
                break
        
        # If no current position, return most recent
        if not current and work_exp:
            current = work_exp[0]  # Assuming first is most recent
        
        return current
    
    def get_summary(self) -> Optional[str]:
        """Get profile summary."""
        return self._profile.basics.summary if self._profile else None
    
    def get_linkedin_url(self) -> Optional[str]:
        """Get LinkedIn URL."""
        return self._profile.basics.linkedin if self._profile else None
    
    def get_github_url(self) -> Optional[str]:
        """Get GitHub URL."""
        return self._profile.basics.github if self._profile else None
    
    def get_website_url(self) -> Optional[str]:
        """Get personal website URL."""
        return self._profile.basics.website if self._profile else None
    
    def validate_profile(self) -> bool:
        """Validate that profile has required information for job applications."""
        if not self._profile:
            return False
        
        required_fields = ['name', 'email']
        basics = self._profile.basics
        
        for field in required_fields:
            if not getattr(basics, field, None):
                self.logger.warning(f"Profile missing required field: {field}")
                return False
        
        return True
    
    def reload_profile(self) -> None:
        """Reload profile from file."""
        self._load_profile()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary for serialization."""
        return self.get_profile_data() if self._profile else {} 