"""Wrapper for interacting with the configured Language Model."""
import logging
import litellm 
from typing import Any, List, Dict, Optional

# Assume config might provide API key and model details
# from enterprise_job_agent.config import Config 

logger = logging.getLogger(__name__)

class LLMWrapper:
    """Provides a consistent interface to the chosen LLM."""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize the LLM wrapper.
        
        Args:
            model: The LLM model name (e.g., 'gemini/gemini-1.5-flash'). 
                   Defaults to value from config or a standard default.
            api_key: The API key for the LLM service. 
                     Defaults to value from config or environment variables.
        """
        # TODO: Load model and API key from config/env if not provided
        self.model = model or "gemini/gemini-1.5-flash" # Example default
        # self.api_key = api_key or Config.get_llm_api_key() # Example config usage
        self.api_key = api_key # For now, assume API key is handled by litellm's env var logic

        logger.info(f"LLMWrapper initialized with model: {self.model}")
        
        # Perform a simple test call to verify setup (optional but recommended)
        # try:
        #     litellm.completion(model=self.model, messages=[{"role": "user", "content": "Test"}])
        #     logger.info("LLM connection verified.")
        # except Exception as e:
        #     logger.error(f"LLM connection test failed: {e}")
        #     # Decide if this should be a fatal error

    @property
    def llm(self) -> Any:
        """Provides access to the underlying LLM interface if needed, 
           though using the wrapper's methods is preferred."""
        # This is a placeholder. Depending on how litellm or other libraries are used,
        # returning the raw client might not be necessary or straightforward.
        # Often, you'd just use the `call` method of this wrapper.
        # For compatibility with existing code that expects an LLM object with invoke/call:
        return self # Return self, as this class will implement the call interface

    def call(self, prompt: str, stop: Optional[List[str]] = None, temperature: float = 0.2, max_tokens: Optional[int] = None) -> str:
        """
        Makes a synchronous call to the LLM using litellm.
        Mimics a common LLM interface method.

        Args:
            prompt: The input prompt string.
            stop: Optional list of stop sequences.
            temperature: Sampling temperature.
            max_tokens: Optional maximum tokens to generate.

        Returns:
            The LLM's response content as a string.
            
        Raises:
            Exception: If the litellm call fails.
        """
        messages = [{"role": "user", "content": prompt}]
        try:
            logger.debug(f"Sending prompt to LLM ({self.model}): {prompt[:100]}...")
            response = litellm.completion(
                model=self.model,
                messages=messages,
                api_key=self.api_key, # Pass API key if needed by litellm setup
                temperature=temperature,
                stop=stop,
                max_tokens=max_tokens
            )
            
            # Extract content based on litellm's response structure
            # Accessing choices[0].message.content is common
            content = response.choices[0].message.content
            logger.debug(f"Received LLM response: {content[:100]}...")
            return content.strip() if content else ""

        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            # Re-raise or return an error indicator
            raise Exception(f"LLM communication error: {e}") from e

    async def acall(self, prompt: str, stop: Optional[List[str]] = None, temperature: float = 0.2, max_tokens: Optional[int] = None) -> str:
        """
        Makes an asynchronous call to the LLM using litellm.
        Needed for async operations like in agent tools or async frameworks.

        Args:
            prompt: The input prompt string.
            stop: Optional list of stop sequences.
            temperature: Sampling temperature.
            max_tokens: Optional maximum tokens to generate.
            
        Returns:
            The LLM's response content as a string.
            
        Raises:
            Exception: If the litellm call fails.
        """
        messages = [{"role": "user", "content": prompt}]
        try:
            logger.debug(f"Sending async prompt to LLM ({self.model}): {prompt[:100]}...")
            response = await litellm.acompletion( # Use acompletion for async
                model=self.model,
                messages=messages,
                api_key=self.api_key,
                temperature=temperature,
                stop=stop,
                max_tokens=max_tokens
            )
            
            content = response.choices[0].message.content
            logger.debug(f"Received async LLM response: {content[:100]}...")
            return content.strip() if content else ""

        except Exception as e:
            logger.error(f"Async LLM call failed: {e}", exc_info=True)
            raise Exception(f"Async LLM communication error: {e}") from e

    # Alias invoke/ainvoke to call/acall for compatibility if needed
    def invoke(self, prompt: str, stop: Optional[List[str]] = None, temperature: float = 0.2, max_tokens: Optional[int] = None) -> str:
        return self.call(prompt, stop, temperature, max_tokens)
        
    async def ainvoke(self, prompt: str, stop: Optional[List[str]] = None, temperature: float = 0.2, max_tokens: Optional[int] = None) -> str:
        return await self.acall(prompt, stop, temperature, max_tokens) 