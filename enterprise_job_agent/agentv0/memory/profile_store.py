import json
import logging
import os
from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel, Field, validator

logger = logging.getLogger("UserProfileStore")

class WorkExperience(BaseModel):
    """Model for work experience entries in the user profile."""
    company: str = Field(..., description="Company/organization name")
    title: str = Field(..., description="Job title")
    start_date: str = Field(..., description="Start date of employment")
    end_date: str = Field(default="Present", description="End date of employment or 'Present'")
    description: str = Field(default="", description="Job description")
    achievements: List[str] = Field(default_factory=list, description="Key achievements")

class Education(BaseModel):
    """Model for education entries in the user profile."""
    institution: str = Field(..., description="School/university name")
    degree: str = Field(..., description="Degree obtained")
    field_of_study: str = Field(..., description="Field of study")
    start_date: str = Field(..., description="Start date")
    end_date: str = Field(default="Present", description="End date or 'Present'")
    gpa: Optional[str] = Field(default=None, description="GPA if applicable")
    achievements: List[str] = Field(default_factory=list, description="Academic achievements")

class OnlinePresence(BaseModel):
    """Model for online presence entries in the user profile."""
    linkedin: Optional[str] = Field(default=None, description="LinkedIn profile URL")
    github: Optional[str] = Field(default=None, description="GitHub profile URL")
    portfolio: Optional[str] = Field(default=None, description="Personal website/portfolio URL")
    other: Dict[str, str] = Field(default_factory=dict, description="Other online profiles")

class EEO(BaseModel):
    """Model for Equal Employment Opportunity information."""
    gender: Optional[str] = Field(default=None, description="Gender")
    race_ethnicity: Optional[str] = Field(default=None, description="Race/ethnicity")
    veteran_status: Optional[str] = Field(default=None, description="Veteran status")
    disability_status: Optional[str] = Field(default=None, description="Disability status")
    prefer_not_to_answer: bool = Field(default=True, description="Prefer not to answer EEO questions")

class Authorization(BaseModel):
    """Model for work authorization information."""
    authorized_to_work: bool = Field(..., description="Authorized to work in the country")
    require_sponsorship: bool = Field(..., description="Requires visa sponsorship")
    citizenship_status: Optional[str] = Field(default=None, description="Citizenship status")

class UserProfile(BaseModel):
    """Complete model for a user's profile data."""
    # Basic information
    first_name: str = Field(..., description="First name")
    last_name: str = Field(..., description="Last name")
    email: str = Field(..., description="Email address")
    phone: str = Field(..., description="Phone number")
    
    # Location information
    address: Optional[str] = Field(default=None, description="Street address")
    city: str = Field(..., description="City")
    state: str = Field(..., description="State/province")
    zip_code: str = Field(..., description="ZIP/postal code")
    country: str = Field(..., description="Country")
    
    # Professional information
    headline: Optional[str] = Field(default=None, description="Professional headline/title")
    summary: Optional[str] = Field(default=None, description="Professional summary/objective")
    work_experience: List[WorkExperience] = Field(..., description="Work experience history")
    education: List[Education] = Field(..., description="Education history")
    skills: List[str] = Field(..., description="Professional skills")
    
    # Online presence
    online_presence: OnlinePresence = Field(default_factory=OnlinePresence, description="Online profiles")
    
    # EEO and authorization
    eeo: EEO = Field(default_factory=EEO, description="Equal Employment Opportunity information")
    authorization: Authorization = Field(..., description="Work authorization information")
    
    # Additional information
    languages: List[str] = Field(default_factory=list, description="Languages spoken")
    certifications: List[str] = Field(default_factory=list, description="Professional certifications")
    custom_questions: Dict[str, str] = Field(default_factory=dict, description="Answers to common custom questions")
    preferences: Dict[str, Any] = Field(default_factory=dict, description="Job preferences (remote, salary, etc.)")
    
    # Cover letter and resume paths
    resume_path: Optional[str] = Field(default=None, description="Path to resume file")
    cover_letter_path: Optional[str] = Field(default=None, description="Path to cover letter file")
    
    @validator('resume_path', 'cover_letter_path')
    def check_file_exists(cls, v):
        """Validate that file paths point to existing files."""
        if v is not None and not os.path.exists(v):
            raise ValueError(f"File does not exist: {v}")
        return v

class UserProfileStore:
    """Manages loading, validating, and accessing user profile data."""
    
    def __init__(self, profile_path: str, fallback_path: Optional[str] = None):
        """Initialize the profile store.
        
        Args:
            profile_path: Path to the primary profile JSON file
            fallback_path: Optional path to a fallback profile for missing values
        """
        self.profile_path = profile_path
        self.fallback_path = fallback_path
        self.profile: Optional[UserProfile] = None
        self.fallback_data: Dict[str, Any] = {}
        
        # Load profile and fallback data
        self._load_profile()
    
    def _load_profile(self) -> None:
        """Load and validate the profile data from the JSON file."""
        try:
            # Load primary profile
            with open(self.profile_path, 'r') as f:
                profile_data = json.load(f)
            
            # Load fallback data if specified
            if self.fallback_path and os.path.exists(self.fallback_path):
                try:
                    with open(self.fallback_path, 'r') as f:
                        self.fallback_data = json.load(f)
                except Exception as e:
                    logger.error(f"Failed to load fallback profile: {str(e)}")
            
            # Validate profile data using Pydantic model
            self.profile = UserProfile(**profile_data)
            logger.info(f"Successfully loaded and validated profile for {self.profile.first_name} {self.profile.last_name}")
            
        except FileNotFoundError:
            logger.error(f"Profile file not found: {self.profile_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from profile file: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error validating profile data: {str(e)}")
            raise
    
    def get_profile(self) -> UserProfile:
        """Get the validated user profile.
        
        Returns:
            The UserProfile object
            
        Raises:
            ValueError: If the profile hasn't been loaded
        """
        if self.profile is None:
            raise ValueError("Profile not loaded")
        return self.profile
    
    def get_value(self, key_path: str, default: Any = None) -> Any:
        """Get a value from the profile using a dot-notation path.
        
        This allows accessing nested properties like "education.0.institution"
        
        Args:
            key_path: Dot-notation path to the desired value
            default: Default value if the key doesn't exist
            
        Returns:
            The value at the specified path, or the default if not found
        """
        if self.profile is None:
            raise ValueError("Profile not loaded")
            
        # Split the path into parts
        parts = key_path.split('.')
        
        # Start with the full profile dictionary
        value = self.profile.dict()
        
        # Navigate through the path
        try:
            for part in parts:
                # Handle list indices
                if part.isdigit() and isinstance(value, list):
                    index = int(part)
                    if 0 <= index < len(value):
                        value = value[index]
                    else:
                        # Index out of range, try fallback
                        return self._get_fallback_value(key_path, default)
                # Handle dictionary keys
                elif isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    # Key not found, try fallback
                    return self._get_fallback_value(key_path, default)
                    
            return value
        except (KeyError, IndexError, TypeError):
            # Any error, try fallback
            return self._get_fallback_value(key_path, default)
    
    def _get_fallback_value(self, key_path: str, default: Any = None) -> Any:
        """Try to get a value from the fallback data.
        
        Args:
            key_path: Dot-notation path to the desired value
            default: Default value if the key doesn't exist in fallback
            
        Returns:
            The fallback value, or the default if not found
        """
        if not self.fallback_data:
            return default
            
        # Split the path into parts
        parts = key_path.split('.')
        
        # Start with the fallback dictionary
        value = self.fallback_data
        
        # Navigate through the path
        try:
            for part in parts:
                # Handle list indices
                if part.isdigit() and isinstance(value, list):
                    index = int(part)
                    if 0 <= index < len(value):
                        value = value[index]
                    else:
                        return default
                # Handle dictionary keys
                elif isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return default
                    
            return value
        except (KeyError, IndexError, TypeError):
            return default
    
    def get_all_values(self) -> Dict[str, Any]:
        """Get all profile values as a dictionary.
        
        Returns:
            The complete profile as a dictionary
        """
        if self.profile is None:
            raise ValueError("Profile not loaded")
        return self.profile.dict()
    
    def get_resume_path(self) -> Optional[str]:
        """Get the path to the resume file.
        
        Returns:
            The resume file path, or None if not specified
        """
        if self.profile is None:
            raise ValueError("Profile not loaded")
        return self.profile.resume_path
    
    def get_cover_letter_path(self) -> Optional[str]:
        """Get the path to the cover letter file.
        
        Returns:
            The cover letter file path, or None if not specified
        """
        if self.profile is None:
            raise ValueError("Profile not loaded")
        return self.profile.cover_letter_path 