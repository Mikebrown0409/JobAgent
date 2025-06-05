from typing import Dict, List, Type, Optional, Any
import logging
from agentv0.tools.base import BaseTool

class ToolRegistry:
    """Registry for managing and accessing tools.
    
    The ToolRegistry maintains a collection of tool instances that can be
    accessed by name. It ensures that tools are properly initialized and
    provides a unified interface for the Orchestrator to discover and use tools.
    """
    
    def __init__(self):
        """Initialize an empty tool registry."""
        self._tools: Dict[str, BaseTool] = {}
        self.logger = logging.getLogger("ToolRegistry")
    
    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool instance with the registry.
        
        Args:
            tool: An instance of a BaseTool subclass
            
        Raises:
            ValueError: If a tool with the same name is already registered
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool with name '{tool.name}' is already registered")
        
        self._tools[tool.name] = tool
        self.logger.info(f"Registered tool: {tool.name}")
    
    def get_tool(self, name: str) -> BaseTool:
        """Get a tool by name.
        
        Args:
            name: The name of the tool to retrieve
            
        Returns:
            The requested tool instance
            
        Raises:
            KeyError: If no tool with the given name is registered
        """
        if name not in self._tools:
            raise KeyError(f"No tool with name '{name}' is registered")
        
        return self._tools[name]
    
    def list_tools(self) -> List[str]:
        """List the names of all registered tools.
        
        Returns:
            A list of tool names
        """
        return list(self._tools.keys())
    
    def get_tool_specifications(self) -> List[Dict[str, Any]]:
        """Get specifications for all registered tools.
        
        Returns:
            A list of tool specifications as dictionaries
        """
        return [tool.get_specification() for tool in self._tools.values()]
    
    def unregister_tool(self, name: str) -> None:
        """Remove a tool from the registry.
        
        Args:
            name: The name of the tool to remove
            
        Raises:
            KeyError: If no tool with the given name is registered
        """
        if name not in self._tools:
            raise KeyError(f"No tool with name '{name}' is registered")
        
        del self._tools[name]
        self.logger.info(f"Unregistered tool: {name}") 