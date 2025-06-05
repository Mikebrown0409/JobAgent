import logging
import os
from typing import Dict, Any, List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator

class AgentConfig(BaseSettings):
    """Configuration settings for the Agent.
    
    This class uses Pydantic's BaseSettings to load configurations from
    environment variables with fallbacks to default values.
    """
    # LLM Settings
    llm_model_name: str = Field("gemini-1.5-flash-latest", description="Default LLM model to use")
    gemini_api_key: Optional[str] = Field(None, description="API Key for Gemini")
    openai_api_key: Optional[str] = Field(None, description="API Key for OpenAI")
    anthropic_api_key: Optional[str] = Field(None, description="API Key for Anthropic")
    togetherai_api_key: Optional[str] = Field(None, description="API Key for TogetherAI")
    
    # Browser Settings
    browser_headless: bool = Field(default=True, env="BROWSER_HEADLESS")
    browser_stealth_mode: bool = Field(default=True, env="BROWSER_STEALTH_MODE")
    browser_viewport_width: int = Field(default=1920, env="BROWSER_VIEWPORT_WIDTH")
    browser_viewport_height: int = Field(default=1080, env="BROWSER_VIEWPORT_HEIGHT")
    
    # Timeouts and Retries
    default_timeout_ms: int = Field(default=30000, env="DEFAULT_TIMEOUT_MS")
    max_retries: int = Field(default=3, env="MAX_RETRIES")
    retry_delay_seconds: int = Field(default=2, env="RETRY_DELAY_SECONDS")
    
    # Paths
    log_dir: str = Field(default="logs", env="LOG_DIR")
    run_results_dir: str = Field(default="run_results", env="RUN_RESULTS_DIR")
    
    # Logging
    log_level: str = Field(default="DEBUG", env="LOG_LEVEL")
    
    class Config:
        """Pydantic configuration for the AgentConfig."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

# Create a single instance to be imported
config = AgentConfig()

# Helper functions for common config operations
def get_config_dict() -> Dict[str, Any]:
    """Get the configuration as a dictionary.
    
    Returns:
        Dictionary of configuration values
    """
    return config.dict()

def get_logging_config() -> Dict[str, Any]:
    """Get logging configuration settings.
    
    Returns:
        Dictionary with logging configuration
    """
    return {
        "level": getattr(config, "log_level", "INFO"),
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "dir": getattr(config, "log_dir", "logs")
    }

# Create directories as needed
os.makedirs(config.log_dir, exist_ok=True)
os.makedirs(config.run_results_dir, exist_ok=True) 