"""Profile management for the enterprise job application system."""

import json
import logging
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ProfileManager:
    """Manages user profiles for job applications."""
    
    def __init__(self, profile_path: Optional[str] = None):
        """
        Initialize the profile manager.
        
        Args:
            profile_path: Path to user profile JSON file
        """
        # Use default path if none provided
        if not profile_path:
            # Use a path relative to this script's location
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.profile_path = os.path.join(script_dir, "test_user/user_profile.json")
        else:
            # If path is relative and doesn't exist, try relative to script directory
            if not os.path.isabs(profile_path) and not os.path.exists(profile_path):
                script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                alternative_path = os.path.join(script_dir, profile_path)
                if os.path.exists(alternative_path):
                    self.profile_path = alternative_path
                else:
                    self.profile_path = profile_path
            else:
                self.profile_path = profile_path
                
        self.profile_data = {}
        self._load_profile()
    
    def _load_profile(self) -> None:
        """Load profile data from file."""
        try:
            if not os.path.exists(self.profile_path):
                logger.warning(f"Profile file not found: {self.profile_path}")
                return
            
            with open(self.profile_path, "r") as f:
                self.profile_data = json.load(f)
                
            logger.info(f"Loaded profile from {self.profile_path}")
        except Exception as e:
            logger.error(f"Error loading profile: {e}")
            
    def get_profile(self) -> Dict[str, Any]:
        """
        Get the user profile data.
        
        Returns:
            User profile data as a dictionary
        """
        if not self.profile_data:
            logger.warning("No profile data loaded")
        
        return self.profile_data
    
    def get_document_path(self, document_type: str) -> Optional[str]:
        """
        Get the path to a document in the profile.
        
        Args:
            document_type: Type of document ("resume" or "cover_letter")
            
        Returns:
            Path to the document, or None if not found
        """
        if not self.profile_data or "documents" not in self.profile_data:
            return None
        
        document_path = self.profile_data.get("documents", {}).get(document_type, "")
        
        if not document_path:
            return None
        
        # If document path is relative, make it relative to the profile path
        if not os.path.isabs(document_path):
            profile_dir = os.path.dirname(os.path.abspath(self.profile_path))
            document_path = os.path.join(profile_dir, document_path)
        
        if not os.path.exists(document_path):
            logger.warning(f"Document not found: {document_path}")
            return None
        
        return document_path
    
    def get_field_value(self, field_path: str, default: Any = None) -> Any:
        """
        Get a value from the profile using a dot-notation path.
        
        Args:
            field_path: Dot-notation path to the field (e.g., "personal.first_name")
            default: Default value to return if field not found
            
        Returns:
            Field value or default if not found
        """
        if not self.profile_data:
            return default
        
        parts = field_path.split(".")
        current = self.profile_data
        
        try:
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return default
            
            return current
        except Exception:
            return default 