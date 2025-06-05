from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union, List
import logging

class BaseTool(ABC):
    """Base class for all tools used by the agent.
    
    All tools must inherit from this class and implement its methods.
    This ensures a consistent interface for the Orchestrator to use.
    """
    
    def __init__(self, name: str, description: str):
        """Initialize the tool with a name and description.
        
        Args:
            name: A unique name for the tool
            description: A brief description of what the tool does
        """
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"Tool.{name}")
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool's primary function.
        
        Args:
            **kwargs: Tool-specific parameters
            
        Returns:
            A dictionary containing the result of the tool execution.
            Must include 'success' (bool) and 'observation' keys.
            May include additional tool-specific result data.
        """
        pass
    
    def get_specification(self) -> Dict[str, Any]:
        """Get a specification of the tool for use by the Orchestrator.
        
        Returns:
            A dictionary containing the tool's name, description, and parameter schema.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self._get_parameter_schema()
        }
    
    @abstractmethod
    def _get_parameter_schema(self) -> Dict[str, Any]:
        """Define the schema for the parameters this tool accepts.
        
        Returns:
            A dictionary representing a JSONSchema for the parameters.
        """
        pass 