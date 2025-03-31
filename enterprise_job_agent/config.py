"""Configuration module for the enterprise job application system."""

import os
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Dictionary mapping job types to their URLs
JOB_URLS = {
    "discord": "https://job-boards.greenhouse.io/discord/jobs/7845336002",
    "google": "https://careers.google.com/jobs/results/",
    "microsoft": "https://careers.microsoft.com/professionals/us/en/job/",
    "meta": "https://www.metacareers.com/jobs/",
    "apple": "https://jobs.apple.com/en-us/details/",
    "amazon": "https://www.amazon.jobs/en/jobs/",
    # Add more job URLs as needed
}

class Config:
    """
    Configuration manager for the enterprise job application system.
    """
    
    # Default configuration values
    DEFAULTS = {
        "api": {
            "openai_api_key": "",
            "model": "gpt-4o",
            "temperature": 0.7
        },
        "browser": {
            "headless": True,
            "user_data_dir": None,
            "proxy": None,
            "timeout": 30000
        },
        "application": {
            "max_retries": 3,
            "timeout": 1800,  # 30 minutes
            "test_mode": False,
            "auto_submit": False
        },
        "profiles": {
            "default_profile": "default",
            "profiles_dir": "~/.jobagent/profiles"
        },
        "logging": {
            "level": "INFO",
            "log_file": "job_application.log",
            "console_output": True
        },
        "storage": {
            "metrics_dir": "~/.jobagent/metrics",
            "screenshots_dir": "~/.jobagent/screenshots",
            "results_dir": "~/.jobagent/results"
        }
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration.
        
        Args:
            config_path: Path to configuration file. If None, uses default location.
        """
        if config_path:
            self.config_path = config_path
        else:
            # Use default location in user's home directory
            self.config_path = os.path.expanduser("~/.jobagent/config.json")
            
        # Load configuration
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from file or create default.
        
        Returns:
            Dictionary with configuration
        """
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # Merge with defaults to ensure all required fields exist
                merged_config = self._merge_with_defaults(config)
                logger.info(f"Loaded configuration from {self.config_path}")
                return merged_config
            else:
                logger.warning(f"Configuration file not found at {self.config_path}. Creating default configuration.")
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                
                # Save default configuration
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.DEFAULTS, f, indent=2)
                    
                return self.DEFAULTS.copy()
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return self.DEFAULTS.copy()
    
    def _merge_with_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge user configuration with defaults to ensure all required fields exist.
        
        Args:
            config: User configuration
            
        Returns:
            Merged configuration
        """
        merged = self.DEFAULTS.copy()
        
        def deep_merge(target, source):
            for key, value in source.items():
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    deep_merge(target[key], value)
                else:
                    target[key] = value
        
        deep_merge(merged, config)
        return merged
    
    def save(self) -> bool:
        """
        Save configuration to file.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            # Save configuration
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)
                
            logger.info(f"Saved configuration to {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: Configuration key (dotted notation, e.g. 'api.openai_api_key')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        try:
            parts = key.split('.')
            value = self.config
            
            for part in parts:
                if part in value:
                    value = value[part]
                else:
                    return default
                    
            return value
        except Exception:
            return default
    
    def set(self, key: str, value: Any) -> bool:
        """
        Set a configuration value.
        
        Args:
            key: Configuration key (dotted notation, e.g. 'api.openai_api_key')
            value: Value to set
            
        Returns:
            True if successful, False otherwise
        """
        try:
            parts = key.split('.')
            config = self.config
            
            # Navigate to the correct nested dictionary
            for i, part in enumerate(parts[:-1]):
                if part not in config:
                    config[part] = {}
                config = config[part]
                
            # Set the value
            config[parts[-1]] = value
            
            # Save the configuration
            return self.save()
        except Exception as e:
            logger.error(f"Error setting configuration value: {e}")
            return False
    
    def get_api_key(self) -> str:
        """
        Get the OpenAI API key, with environment variable fallback.
        
        Returns:
            API key
        """
        # Check configuration first
        api_key = self.get('api.openai_api_key')
        
        # If not set, check environment variable
        if not api_key:
            api_key = os.environ.get('OPENAI_API_KEY', '')
            
        return api_key
    
    def configure_logging(self):
        """Configure logging based on configuration."""
        log_level = getattr(logging, self.get('logging.level', 'INFO'))
        log_file = self.get('logging.log_file', 'job_application.log')
        console_output = self.get('logging.console_output', True)
        
        handlers = []
        
        # File handler
        if log_file:
            handlers.append(logging.FileHandler(log_file))
            
        # Console handler
        if console_output:
            handlers.append(logging.StreamHandler())
            
        # Configure logging
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=handlers
        )
    
    def get_browser_options(self) -> Dict[str, Any]:
        """
        Get browser configuration options.
        
        Returns:
            Dictionary with browser options
        """
        return {
            'headless': self.get('browser.headless', True),
            'user_data_dir': self.get('browser.user_data_dir'),
            'proxy': self.get('browser.proxy'),
            'timeout': self.get('browser.timeout', 30000)
        }
    
    def get_application_options(self) -> Dict[str, Any]:
        """
        Get application configuration options.
        
        Returns:
            Dictionary with application options
        """
        return {
            'max_retries': self.get('application.max_retries', 3),
            'timeout': self.get('application.timeout', 1800),
            'test_mode': self.get('application.test_mode', False),
            'auto_submit': self.get('application.auto_submit', False)
        }
    
    def get_storage_path(self, storage_type: str) -> str:
        """
        Get a storage path with user expansion.
        
        Args:
            storage_type: Type of storage (metrics, screenshots, results)
            
        Returns:
            Expanded path
        """
        path = self.get(f'storage.{storage_type}_dir')
        if path:
            return os.path.expanduser(path)
        else:
            return os.path.expanduser(f"~/.jobagent/{storage_type}")

# Create a global instance for easy access
config = Config() 