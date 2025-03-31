"""Browser automation tools for navigating and interacting with job application forms."""

import asyncio
import json
import logging
import os
import tempfile
import time
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Locator, ElementHandle
from playwright.async_api._generated import Error as PlaywrightError

logger = logging.getLogger(__name__)

class BrowserManager:
    """
    Manages browser instances for job application automation.
    """
    
    def __init__(
        self, 
        headless: bool = False,
        proxy: Optional[Dict[str, str]] = None,
        user_data_dir: Optional[str] = None
    ):
        """
        Initialize the browser manager.
        
        Args:
            headless: Whether to run the browser in headless mode
            proxy: Optional proxy configuration
            user_data_dir: Directory to store user data (cookies, localStorage, etc.)
        """
        self.headless = headless
        self.proxy = proxy
        self.user_data_dir = user_data_dir
        
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
    async def start(self) -> bool:
        """
        Start the browser and create a page.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Starting browser")
            self.playwright = await async_playwright().start()
            
            # Prepare browser launch options
            launch_options = {
                "headless": self.headless
            }
            
            if self.proxy:
                launch_options["proxy"] = self.proxy
            
            # Launch browser
            self.browser = await self.playwright.chromium.launch(**launch_options)
            
            # Create a browser context with user data directory if specified
            context_options = {}
            
            if self.user_data_dir:
                context_options["user_data_dir"] = self.user_data_dir
            
            # Set default viewport size
            context_options["viewport"] = {"width": 1280, "height": 960}
            
            # Create context and page
            self.context = await self.browser.new_context(**context_options)
            self.page = await self.context.new_page()
            
            # Set default timeout
            self.page.set_default_timeout(30000)
            
            # Enable request interception for more verbose logging
            await self.page.route("**/*", self._log_request)
            
            logger.info("Browser started successfully")
            return True
        except Exception as e:
            logger.error(f"Error starting browser: {e}")
            await self.close()
            return False
    
    async def _log_request(self, route, request):
        """Log requests for debugging purposes."""
        if request.resource_type in ["document", "xhr", "fetch"]:
            logger.debug(f"Request: {request.method} {request.url} ({request.resource_type})")
        await route.continue_()
    
    async def close(self) -> bool:
        """
        Close the browser and clean up resources.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Closing browser")
            
            if self.page:
                await self.page.close()
                self.page = None
            
            if self.context:
                await self.context.close()
                self.context = None
            
            if self.browser:
                await self.browser.close()
                self.browser = None
            
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            
            logger.info("Browser closed successfully")
            return True
        except Exception as e:
            logger.error(f"Error closing browser: {e}")
            return False
    
    async def get_page(self) -> Optional[Page]:
        """
        Get the current page, or create a new one if needed.
        
        Returns:
            Playwright Page object or None if browser not started
        """
        if not self.browser:
            logger.warning("Browser not started, attempting to start")
            if not await self.start():
                return None
        
        if not self.page:
            logger.info("Creating new page")
            self.page = await self.context.new_page()
        
        return self.page
    
    async def navigate(self, url: str, wait_until: str = "networkidle") -> bool:
        """
        Navigate to a URL.
        
        Args:
            url: URL to navigate to
            wait_until: When to consider navigation complete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            page = await self.get_page()
            if not page:
                return False
            
            logger.info(f"Navigating to {url}")
            
            # Add http:// if missing
            if not url.startswith("http"):
                url = f"http://{url}"
            
            response = await page.goto(url, wait_until=wait_until)
            
            # Check if navigation was successful
            if response and response.status < 400:
                logger.info(f"Successfully loaded {url} (status: {response.status})")
                return True
            else:
                status = response.status if response else "unknown"
                logger.error(f"Failed to load {url} (status: {status})")
                return False
        except Exception as e:
            logger.error(f"Error navigating to {url}: {e}")
            return False
    
    async def take_screenshot(self, path: Optional[str] = None) -> Optional[str]:
        """
        Take a screenshot of the current page.
        
        Args:
            path: Path to save the screenshot. If None, uses a temporary file.
            
        Returns:
            Path to the screenshot or None if failed
        """
        try:
            page = await self.get_page()
            if not page:
                return None
            
            # Generate path if not provided
            if not path:
                temp_dir = tempfile.gettempdir()
                timestamp = int(asyncio.get_event_loop().time())
                path = os.path.join(temp_dir, f"screenshot_{timestamp}.png")
            
            # Take screenshot
            await page.screenshot(path=path, full_page=True)
            logger.info(f"Screenshot saved to {path}")
            
            return path
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            return None
    
    async def wait_for_selector(
        self, 
        selector: str, 
        state: str = "visible", 
        timeout: int = 30000
    ) -> Optional[ElementHandle]:
        """
        Wait for an element to be present.
        
        Args:
            selector: CSS selector
            state: State to wait for (attached, detached, visible, hidden)
            timeout: Timeout in milliseconds
            
        Returns:
            Element handle or None if not found
        """
        try:
            page = await self.get_page()
            if not page:
                return None
            
            logger.debug(f"Waiting for selector '{selector}' to be {state}")
            element = await page.wait_for_selector(selector, state=state, timeout=timeout)
            
            if element:
                logger.debug(f"Found element matching '{selector}'")
                return element
            else:
                logger.warning(f"Element '{selector}' not found")
                return None
        except PlaywrightError as e:
            logger.warning(f"Timeout waiting for selector '{selector}': {e}")
            return None
        except Exception as e:
            logger.error(f"Error waiting for selector '{selector}': {e}")
            return None
    
    async def extract_job_details(self) -> Dict[str, Any]:
        """
        Extract job details from the current page.
        
        Returns:
            Dictionary with job details
        """
        try:
            page = await self.get_page()
            if not page:
                return {}
            
            logger.info("Extracting job details from page")
            
            # Execute JavaScript to extract job details
            job_details = await page.evaluate("""() => {
                const extractText = (selector) => {
                    const el = document.querySelector(selector);
                    return el ? el.innerText.trim() : '';
                };
                
                // Try various selectors for job titles
                let title = extractText('h1.job-title') || 
                           extractText('.job-title') || 
                           extractText('h1') ||
                           extractText('[data-automation="job-detail-title"]') ||
                           '';
                
                // Try various selectors for company
                let company = extractText('.company-name') || 
                             extractText('.employer-name') || 
                             extractText('[data-automation="job-detail-company"]') ||
                             '';
                
                // Try various selectors for location
                let location = extractText('.location') || 
                              extractText('.job-location') || 
                              extractText('[data-automation="job-detail-location"]') ||
                              '';
                
                // Try various selectors for job description
                let description = extractText('.job-description') || 
                                 extractText('#job-description') || 
                                 extractText('[data-automation="job-detail-description"]') ||
                                 '';
                
                // Extract application deadline if available
                let deadline = extractText('.deadline') || 
                              extractText('.closing-date') || 
                              '';
                
                // Extract salary information if available
                let salary = extractText('.salary') || 
                            extractText('[data-automation="job-detail-salary"]') || 
                            '';
                
                // Extract job type/employment type
                let jobType = extractText('.job-type') || 
                             extractText('.employment-type') || 
                             '';
                
                // Extract all paragraphs from the job description for better analysis
                const descriptionParagraphs = Array.from(
                    document.querySelectorAll('.job-description p, #job-description p, [data-automation="job-detail-description"] p')
                ).map(p => p.innerText.trim()).filter(Boolean);
                
                // Extract skills from job description using keyword detection
                const skillKeywords = [
                    'skills', 'requirements', 'qualifications', 'experience with', 
                    'proficiency', 'knowledge of', 'familiar with', 'expertise in'
                ];
                
                const liElements = Array.from(document.querySelectorAll('ul li'));
                const potentialSkills = liElements.filter(li => {
                    const text = li.innerText.toLowerCase();
                    // Look for short bullet points that might be skills
                    return text.length < 100 && !text.includes('.') && !text.includes('?');
                }).map(li => li.innerText.trim());
                
                const skillSection = Array.from(document.querySelectorAll('h2, h3, h4')).find(heading => {
                    const text = heading.innerText.toLowerCase();
                    return skillKeywords.some(keyword => text.includes(keyword));
                });
                
                let skillsList = [];
                if (skillSection) {
                    let element = skillSection.nextElementSibling;
                    while (element && !['H2', 'H3', 'H4'].includes(element.tagName)) {
                        if (element.tagName === 'UL' || element.tagName === 'OL') {
                            const items = Array.from(element.querySelectorAll('li')).map(li => li.innerText.trim());
                            skillsList = skillsList.concat(items);
                        }
                        element = element.nextElementSibling;
                    }
                } else {
                    skillsList = potentialSkills;
                }
                
                // Extract application instructions
                const applicationInstructions = Array.from(document.querySelectorAll('p, div')).filter(el => {
                    const text = el.innerText.toLowerCase();
                    return text.includes('apply') && text.includes('please') && text.length < 500;
                }).map(el => el.innerText.trim());
                
                return {
                    title,
                    company,
                    location,
                    description,
                    description_paragraphs: descriptionParagraphs,
                    deadline,
                    salary,
                    job_type: jobType,
                    skills: skillsList,
                    application_instructions: applicationInstructions,
                    page_url: window.location.href,
                    page_title: document.title
                };
            }""")
            
            logger.info(f"Extracted job details: {job_details['title']} at {job_details['company']}")
            return job_details
        except Exception as e:
            logger.error(f"Error extracting job details: {e}")
            return {} 