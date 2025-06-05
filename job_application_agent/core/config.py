"""
Configuration Management - Enterprise Settings

Centralized configuration management with environment variable support,
validation, and enterprise-grade settings.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class Config(BaseModel):
    """
    Enterprise configuration model with comprehensive settings.
    
    Supports environment variables, file paths, and advanced features.
    """
    
    # Browser settings
    headless: bool = Field(default=True, description="Run browser in headless mode")
    browser_timeout: int = Field(default=30000, description="Browser operation timeout in ms")
    page_load_timeout: int = Field(default=60000, description="Page load timeout in ms")
    
    # LLM settings
    google_api_key: Optional[str] = Field(default=None, description="Google API key for Gemini")
    gemini_model: str = Field(default="gemini-1.5-flash", description="Gemini model to use")
    llm_temperature: float = Field(default=0.7, description="LLM temperature for content generation")
    llm_max_tokens: int = Field(default=1000, description="Maximum tokens for LLM responses")
    
    # Profile and file paths
    profile_path: str = Field(default="data/profiles/profile.json", description="Path to user profile JSON")
    resume_path: Optional[Path] = Field(default=None, description="Path to resume file")
    cover_letter_path: Optional[Path] = Field(default=None, description="Path to cover letter file")
    
    # Logging settings
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: Optional[str] = Field(default=None, description="Log file path")
    
    # Performance settings
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    retry_delay: float = Field(default=1.0, description="Delay between retries in seconds")
    concurrent_applications: int = Field(default=1, description="Number of concurrent applications")
    
    # Enterprise features
    enable_ai_content: bool = Field(default=True, description="Enable AI content generation")
    enable_semantic_analysis: bool = Field(default=True, description="Enable semantic form analysis")
    enable_performance_tracking: bool = Field(default=True, description="Enable performance tracking")
    enable_caching: bool = Field(default=True, description="Enable result caching")
    
    # Security settings
    user_agent: str = Field(
        default="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        description="User agent string"
    )
    stealth_mode: bool = Field(default=True, description="Enable stealth browsing features")
    
    # Data storage
    results_dir: str = Field(default="results", description="Directory for storing results")
    logs_dir: str = Field(default="logs", description="Directory for storing logs")
    cache_dir: str = Field(default=".cache", description="Directory for caching")
    
    model_config = ConfigDict(
        env_prefix="JOB_AGENT_",
        case_sensitive=False,
        extra="ignore"  # Ignore extra environment variables
    )
    
    @field_validator('resume_path', mode='before')
    @classmethod
    def validate_resume_path(cls, v):
        """Validate and convert resume path."""
        if v is None:
            return None
        path = Path(v)
        if not path.exists():
            logging.warning(f"Resume file not found: {path}")
        return path
    
    @field_validator('cover_letter_path', mode='before')
    @classmethod
    def validate_cover_letter_path(cls, v):
        """Validate and convert cover letter path."""
        if v is None:
            return None
        path = Path(v)
        if not path.exists():
            logging.warning(f"Cover letter file not found: {path}")
        return path
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()
    
    @field_validator('llm_temperature')
    @classmethod
    def validate_temperature(cls, v):
        """Validate LLM temperature."""
        if not 0.0 <= v <= 2.0:
            raise ValueError("LLM temperature must be between 0.0 and 2.0")
        return v
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Create configuration from environment variables."""
        # Load from environment with fallbacks
        config_data = {}
        
        # Browser settings
        config_data['headless'] = os.getenv('JOB_AGENT_HEADLESS', 'true').lower() == 'true'
        config_data['browser_timeout'] = int(os.getenv('JOB_AGENT_BROWSER_TIMEOUT', '30000'))
        config_data['page_load_timeout'] = int(os.getenv('JOB_AGENT_PAGE_LOAD_TIMEOUT', '60000'))
        
        # LLM settings
        config_data['google_api_key'] = os.getenv('GEMINI_API_KEY') or os.getenv('JOB_AGENT_GOOGLE_API_KEY')
        config_data['gemini_model'] = os.getenv('JOB_AGENT_GEMINI_MODEL', 'gemini-1.5-flash')
        config_data['llm_temperature'] = float(os.getenv('JOB_AGENT_LLM_TEMPERATURE', '0.7'))
        config_data['llm_max_tokens'] = int(os.getenv('JOB_AGENT_LLM_MAX_TOKENS', '1000'))
        
        # File paths
        config_data['profile_path'] = os.getenv('JOB_AGENT_PROFILE_PATH', 'data/profiles/profile.json')
        
        resume_path = os.getenv('JOB_AGENT_RESUME_PATH')
        if resume_path:
            config_data['resume_path'] = resume_path
        
        cover_letter_path = os.getenv('JOB_AGENT_COVER_LETTER_PATH')
        if cover_letter_path:
            config_data['cover_letter_path'] = cover_letter_path
        
        # Logging
        config_data['log_level'] = os.getenv('JOB_AGENT_LOG_LEVEL', 'INFO')
        config_data['log_file'] = os.getenv('JOB_AGENT_LOG_FILE')
        
        # Performance
        config_data['max_retries'] = int(os.getenv('JOB_AGENT_MAX_RETRIES', '3'))
        config_data['retry_delay'] = float(os.getenv('JOB_AGENT_RETRY_DELAY', '1.0'))
        config_data['concurrent_applications'] = int(os.getenv('JOB_AGENT_CONCURRENT_APPLICATIONS', '1'))
        
        # Enterprise features
        config_data['enable_ai_content'] = os.getenv('JOB_AGENT_ENABLE_AI_CONTENT', 'true').lower() == 'true'
        config_data['enable_semantic_analysis'] = os.getenv('JOB_AGENT_ENABLE_SEMANTIC_ANALYSIS', 'true').lower() == 'true'
        config_data['enable_performance_tracking'] = os.getenv('JOB_AGENT_ENABLE_PERFORMANCE_TRACKING', 'true').lower() == 'true'
        config_data['enable_caching'] = os.getenv('JOB_AGENT_ENABLE_CACHING', 'true').lower() == 'true'
        
        # Security
        config_data['stealth_mode'] = os.getenv('JOB_AGENT_STEALTH_MODE', 'true').lower() == 'true'
        
        # Directories
        config_data['results_dir'] = os.getenv('JOB_AGENT_RESULTS_DIR', 'results')
        config_data['logs_dir'] = os.getenv('JOB_AGENT_LOGS_DIR', 'logs')
        config_data['cache_dir'] = os.getenv('JOB_AGENT_CACHE_DIR', '.cache')
        
        return cls(**config_data)
    
    def ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        directories = [
            self.results_dir,
            self.logs_dir,
            self.cache_dir,
            os.path.dirname(self.profile_path)
        ]
        
        for directory in directories:
            if directory:
                Path(directory).mkdir(parents=True, exist_ok=True)
    
    def get_resume_path(self) -> Optional[Path]:
        """Get resume path if it exists."""
        if self.resume_path and isinstance(self.resume_path, Path) and self.resume_path.exists():
            return self.resume_path
        
        # Try common locations
        common_paths = [
            Path("resume.pdf"),
            Path("data/resume.pdf"),
            Path("documents/resume.pdf"),
            Path("files/resume.pdf")
        ]
        
        for path in common_paths:
            if path.exists():
                return path
        
        return None
    
    def get_cover_letter_path(self) -> Optional[Path]:
        """Get cover letter path if it exists."""
        if self.cover_letter_path and isinstance(self.cover_letter_path, Path) and self.cover_letter_path.exists():
            return self.cover_letter_path
        
        # Try common locations
        common_paths = [
            Path("cover_letter.pdf"),
            Path("data/cover_letter.pdf"),
            Path("documents/cover_letter.pdf"),
            Path("files/cover_letter.pdf")
        ]
        
        for path in common_paths:
            if path.exists():
                return path
        
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return self.dict()
    
    def is_ai_enabled(self) -> bool:
        """Check if AI features are enabled and properly configured."""
        return (
            self.enable_ai_content and 
            self.google_api_key is not None and 
            isinstance(self.google_api_key, str) and
            len(self.google_api_key.strip()) > 0
        )
    
    def get_browser_args(self) -> list[str]:
        """Get browser launch arguments based on configuration."""
        args = [
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--no-first-run',
            '--no-default-browser-check'
        ]
        
        if self.stealth_mode:
            args.extend([
                '--disable-blink-features=AutomationControlled',
                '--disable-extensions',
                '--disable-background-timer-throttling',
                '--disable-renderer-backgrounding',
                '--disable-backgrounding-occluded-windows'
            ])
        
        return args
    
    def get_context_headers(self) -> Dict[str, str]:
        """Get HTTP headers for browser context."""
        headers = {
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Upgrade-Insecure-Requests': '1'
        }
        
        if self.stealth_mode:
            headers.update({
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none'
            })
        
        return headers 