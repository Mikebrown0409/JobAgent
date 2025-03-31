"""Rate limiting for API calls."""

import asyncio
import time
import logging
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class RateLimitedQueue:
    """Queue with rate limiting for API calls."""
    
    def __init__(self, rpm_limit: int = 6):
        """
        Initialize the rate limited queue.
        
        Args:
            rpm_limit: Maximum requests per minute
        """
        self.rpm_limit = rpm_limit
        self.time_between_requests = 60 / rpm_limit  # seconds
        self.last_request_time = 0
        self.queue = asyncio.Queue()
        self.running = False
        self._processor_task = None
        logger.info(f"Rate limiter initialized with {rpm_limit} RPM limit")
        
    async def add_task(self, task_func: Callable, *args: Any, **kwargs: Any) -> None:
        """
        Add a task to the rate-limited queue.
        
        Args:
            task_func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
        """
        await self.queue.put((task_func, args, kwargs))
        logger.debug(f"Task added to queue: {task_func.__name__}")
        
        # Start processor if not already running
        if not self.running:
            self.start_processor()
    
    def start_processor(self) -> None:
        """Start the queue processor task."""
        if self._processor_task is None or self._processor_task.done():
            self.running = True
            self._processor_task = asyncio.create_task(self.process_queue())
            logger.debug("Queue processor started")
    
    async def process_queue(self) -> None:
        """Process tasks in the queue with rate limiting."""
        logger.info("Queue processor running")
        try:
            while not self.queue.empty():
                task_func, args, kwargs = await self.queue.get()
                
                # Ensure rate limit
                time_since_last = time.time() - self.last_request_time
                if time_since_last < self.time_between_requests:
                    delay = self.time_between_requests - time_since_last
                    logger.debug(f"Rate limiting: waiting {delay:.2f}s before next request")
                    await asyncio.sleep(delay)
                
                # Execute task
                self.last_request_time = time.time()
                logger.debug(f"Executing task: {task_func.__name__}")
                try:
                    await task_func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error executing task {task_func.__name__}: {e}")
                
                self.queue.task_done()
        finally:
            self.running = False
            logger.info("Queue processor finished")
    
    async def execute_api_call(self, api_func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Execute an API call with rate limiting.
        
        Args:
            api_func: API function to call
            *args: Positional arguments for the API function
            **kwargs: Keyword arguments for the API function
            
        Returns:
            Result from the API function
        """
        # Ensure rate limit
        time_since_last = time.time() - self.last_request_time
        if time_since_last < self.time_between_requests:
            delay = self.time_between_requests - time_since_last
            logger.debug(f"Rate limiting: waiting {delay:.2f}s before API call")
            await asyncio.sleep(delay)
        
        # Execute API call
        self.last_request_time = time.time()
        logger.debug(f"Making API call: {api_func.__name__ if hasattr(api_func, '__name__') else api_func}")
        return await api_func(*args, **kwargs)
    
    async def wait_until_processed(self) -> None:
        """Wait until all tasks in the queue have been processed."""
        await self.queue.join()
        logger.debug("All queued tasks processed") 