"""
Tool Registry - Dynamic Tool Management

Manages registration and access to available tools.
Provides a clean interface for tool discovery and execution.
"""

import logging
from typing import Dict, Any, List, Optional


class ToolRegistry:
    """Registry for managing available tools."""
    
    def __init__(self):
        """Initialize the tool registry."""
        self.logger = logging.getLogger(__name__)
        self._tools: Dict[str, Any] = {}
    
    def register(self, name: str, tool: Any) -> None:
        """
        Register a tool with the registry.
        
        Args:
            name: Unique name for the tool
            tool: Tool instance
        """
        if name in self._tools:
            self.logger.warning(f"Tool '{name}' already registered, replacing")
        
        self._tools[name] = tool
        self.logger.info(f"Tool '{name}' registered")
    
    def register_tool(self, name: str, tool: Any) -> None:
        """Register a tool with the registry (alias for register)."""
        self.register(name, tool)
    
    def unregister(self, name: str) -> bool:
        """
        Unregister a tool from the registry.
        
        Args:
            name: Name of the tool to unregister
            
        Returns:
            True if tool was unregistered, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            self.logger.info(f"Tool '{name}' unregistered")
            return True
        
        self.logger.warning(f"Tool '{name}' not found for unregistration")
        return False
    
    def get_tool(self, name: str) -> Optional[Any]:
        """
        Get a tool by name.
        
        Args:
            name: Name of the tool
            
        Returns:
            Tool instance or None if not found
        """
        tool = self._tools.get(name)
        if not tool:
            self.logger.warning(f"Tool '{name}' not found")
        return tool
    
    def has_tool(self, name: str) -> bool:
        """
        Check if a tool is registered.
        
        Args:
            name: Name of the tool
            
        Returns:
            True if tool is registered
        """
        return name in self._tools
    
    def list_tools(self) -> List[str]:
        """
        Get list of registered tool names.
        
        Returns:
            List of tool names
        """
        return list(self._tools.keys())
    
    def get_tool_info(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a tool.
        
        Args:
            name: Name of the tool
            
        Returns:
            Tool information or None if not found
        """
        tool = self._tools.get(name)
        if not tool:
            return None
        
        info = {
            "name": name,
            "type": type(tool).__name__,
            "methods": [method for method in dir(tool) if not method.startswith('_')],
        }
        
        # Add description if available
        if hasattr(tool, '__doc__') and tool.__doc__:
            info["description"] = tool.__doc__.strip()
        
        return info
    
    def get_all_tools_info(self) -> Dict[str, Any]:
        """
        Get information about all registered tools.
        
        Returns:
            Dictionary mapping tool names to their info
        """
        return {name: self.get_tool_info(name) for name in self._tools.keys()}
    
    def clear(self) -> None:
        """Clear all registered tools."""
        tool_count = len(self._tools)
        self._tools.clear()
        self.logger.info(f"Cleared {tool_count} tools from registry")
    
    def __len__(self) -> int:
        """Get number of registered tools."""
        return len(self._tools)
    
    def __contains__(self, name: str) -> bool:
        """Check if tool is registered using 'in' operator."""
        return name in self._tools
    
    def __iter__(self):
        """Iterate over tool names."""
        return iter(self._tools.keys())
    
    def __str__(self) -> str:
        """String representation of the registry."""
        return f"ToolRegistry({len(self._tools)} tools: {list(self._tools.keys())})" 