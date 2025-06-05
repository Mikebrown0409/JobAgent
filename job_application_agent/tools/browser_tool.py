"""
Enhanced Browser Tool with Cognitive Intelligence

This integrates the cognitive browsing engine to provide intelligent
web automation capabilities like Claude's browsing abilities.
"""

import asyncio
import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from ..core.cognitive_browser import CognitiveBrowser, PageType, NavigationAction
from ..core.advanced_field_detector import AdvancedFieldDetector


class BrowserTool:
    """Enhanced browser tool with cognitive intelligence."""
    
    def __init__(self, config, llm_service):
        self.config = config
        self.llm_service = llm_service
        self.logger = logging.getLogger(__name__)
        
        # Browser state
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        # Cognitive components
        self.cognitive_browser: Optional[CognitiveBrowser] = None
        self.field_detector: Optional[AdvancedFieldDetector] = None
        
        # Application state
        self.current_job_url = None
        self.application_progress = {}
        self.navigation_history = []

    async def start(self):
        """Start the browser with stealth configuration."""
        if self.playwright is None:
            self.playwright = await async_playwright().start()
            
        if self.browser is None:
            self.browser = await self.playwright.chromium.launch(
                headless=False,  # Set to True for production
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--disable-extensions',
                    '--disable-plugins',
                    '--disable-images',  # Faster loading
                    '--disable-javascript-harmony-shipping',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-features=TranslateUI',
                    '--disable-ipc-flooding-protection',
                ]
            )
            
        if self.context is None:
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                extra_http_headers={
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )
            
        if self.page is None:
            self.page = await self.context.new_page()
            
            # Anti-detection measures
            await self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
                
                window.chrome = {
                    runtime: {},
                };
            """)
            
            # Initialize cognitive browser
            self.cognitive_browser = CognitiveBrowser(
                self.page, 
                self.llm_service, 
                self.config
            )
            
            # Initialize advanced field detector
            self.field_detector = AdvancedFieldDetector(self.page, self.config)
            
        self.logger.info("Browser started with cognitive intelligence")

    async def navigate_to_job(self, job_url: str) -> Dict[str, Any]:
        """Navigate to job posting with intelligent analysis."""
        
        if not self.cognitive_browser:
            await self.start()
            
        self.current_job_url = job_url
        self.logger.info(f"Navigating to job: {job_url}")
        
        try:
            # Navigate to the job posting
            await self.page.goto(job_url, wait_until='networkidle', timeout=30000)
            
            # Immediate cognitive analysis
            insight = await self.cognitive_browser.analyze_page_intelligently()
            
            # Record navigation
            self.navigation_history.append({
                'timestamp': datetime.now().isoformat(),
                'url': job_url,
                'page_type': insight.page_type.value,
                'confidence': insight.confidence,
                'reasoning': insight.reasoning
            })
            
            return {
                'success': True,
                'url': job_url,
                'page_type': insight.page_type.value,
                'confidence': insight.confidence,
                'reasoning': insight.reasoning,
                'next_actions': [action.value for action in insight.next_actions],
                'analysis_time': insight.semantic_context['analysis_time']
            }
            
        except Exception as e:
            self.logger.error(f"Failed to navigate to job: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'url': job_url
            }

    async def apply_to_job_intelligently(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply to job using cognitive intelligence."""
        
        if not self.cognitive_browser:
            return {'success': False, 'error': 'Cognitive browser not initialized'}
            
        start_time = datetime.now()
        application_steps = []
        
        try:
            # Step 1: Analyze current page
            insight = await self.cognitive_browser.analyze_page_intelligently()
            application_steps.append({
                'step': 'initial_analysis',
                'page_type': insight.page_type.value,
                'reasoning': insight.reasoning,
                'timestamp': datetime.now().isoformat()
            })
            
            # Step 2: Execute intelligent navigation
            if insight.page_type == PageType.JOB_LISTING:
                # We're on a job listing - need to find and click apply
                self.logger.info("On job listing page - looking for apply button")
                
                nav_result = await self.cognitive_browser.execute_intelligent_navigation()
                application_steps.append({
                    'step': 'click_apply_button',
                    'success': nav_result['success'],
                    'results': nav_result['results'],
                    'timestamp': datetime.now().isoformat()
                })
                
                if nav_result['success']:
                    # Wait for page to load and re-analyze
                    await asyncio.sleep(3)
                    insight = await self.cognitive_browser.analyze_page_intelligently()
                    application_steps.append({
                        'step': 'post_apply_analysis',
                        'page_type': insight.page_type.value,
                        'reasoning': insight.reasoning,
                        'timestamp': datetime.now().isoformat()
                    })
                    
            # Step 3: Handle application form
            if insight.page_type in [PageType.APPLICATION_FORM, PageType.MULTI_STEP_FORM]:
                self.logger.info("Application form detected - filling intelligently")
                
                # Update cognitive browser with profile data
                form_result = await self._fill_application_form_intelligently(profile_data)
                application_steps.append({
                    'step': 'fill_application_form',
                    'success': form_result['success'],
                    'filled_fields': form_result.get('filled_fields', 0),
                    'failed_fields': form_result.get('failed_fields', 0),
                    'timestamp': datetime.now().isoformat()
                })
                
                # Submit the application
                if form_result['success']:
                    submit_result = await self._submit_application_intelligently()
                    application_steps.append({
                        'step': 'submit_application',
                        'success': submit_result['success'],
                        'timestamp': datetime.now().isoformat()
                    })
                    
            # Step 4: Handle special cases
            elif insight.page_type == PageType.LOGIN_REQUIRED:
                self.logger.info("Login required - attempting guest application")
                
                guest_result = await self.cognitive_browser._provide_email_for_guest_application()
                application_steps.append({
                    'step': 'guest_application',
                    'success': guest_result['success'],
                    'timestamp': datetime.now().isoformat()
                })
                
                if guest_result['success']:
                    # Recursively apply after providing email
                    return await self.apply_to_job_intelligently(profile_data)
                    
            # Final analysis
            final_insight = await self.cognitive_browser.analyze_page_intelligently()
            application_steps.append({
                'step': 'final_analysis',
                'page_type': final_insight.page_type.value,
                'reasoning': final_insight.reasoning,
                'timestamp': datetime.now().isoformat()
            })
            
            # Determine overall success
            total_time = (datetime.now() - start_time).total_seconds()
            success = final_insight.page_type == PageType.CONFIRMATION or any(
                step.get('success') for step in application_steps
            )
            
            return {
                'success': success,
                'total_time': total_time,
                'application_steps': application_steps,
                'final_page_type': final_insight.page_type.value,
                'final_reasoning': final_insight.reasoning,
                'job_url': self.current_job_url
            }
            
        except Exception as e:
            self.logger.error(f"Intelligent job application failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'total_time': (datetime.now() - start_time).total_seconds(),
                'application_steps': application_steps,
                'job_url': self.current_job_url
            }

    async def _fill_application_form_intelligently(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fill application form using cognitive field mapping."""
        
        insight = self.cognitive_browser.get_current_insight()
        if not insight or not insight.form_fields:
            return {'success': False, 'error': 'No form fields detected'}
            
        filled_fields = 0
        failed_fields = 0
        field_details = []
        
        # Enhanced profile data mapping
        profile_mapping = {
            'first_name': profile_data.get('first_name', 'Sarah'),
            'last_name': profile_data.get('last_name', 'Chen'),
            'email': profile_data.get('email', 'sarah.chen@email.com'),
            'phone': profile_data.get('phone', '(555) 123-4567'),
            'full_name': f"{profile_data.get('first_name', 'Sarah')} {profile_data.get('last_name', 'Chen')}",
            'address': profile_data.get('address', '123 Main St, City, State 12345'),
            'linkedin': profile_data.get('linkedin', 'https://linkedin.com/in/sarah-chen'),
            'portfolio': profile_data.get('portfolio', 'https://sarahchen.dev'),
            'experience_years': profile_data.get('experience_years', '5'),
            'salary_expectation': profile_data.get('salary_expectation', '80000'),
            'availability': profile_data.get('availability', 'Immediately')
        }
        
        for field in insight.form_fields:
            if field.field_purpose in profile_mapping:
                value = profile_mapping[field.field_purpose]
                
                # Use advanced field detector with Claude-like intelligence
                result = await self.field_detector.find_and_fill_field_intelligently(
                    field.__dict__, value
                )
                
                if result['success']:
                    filled_fields += 1
                    field_details.append({
                        'field_purpose': field.field_purpose,
                        'value': value,
                        'success': True,
                        'strategy': result.get('strategy', 'unknown'),
                        'confidence': field.confidence,
                        'fill_time': result.get('total_time', 0)
                    })
                    
                    self.logger.info(f"✓ Filled {field.field_purpose}: {value} (using {result.get('strategy', 'unknown')})")
                    
                else:
                    failed_fields += 1
                    field_details.append({
                        'field_purpose': field.field_purpose,
                        'error': result.get('error', 'Unknown error'),
                        'success': False,
                        'strategies_attempted': result.get('strategies_attempted', 0),
                        'fill_time': result.get('total_time', 0)
                    })
                    
                    self.logger.warning(f"✗ Failed to fill {field.field_purpose}: {result.get('error', 'Unknown error')}")
        
        return {
            'success': filled_fields > 0,
            'filled_fields': filled_fields,
            'failed_fields': failed_fields,
            'field_details': field_details
        }

    async def _find_element_intelligently(self, field) -> Optional[Any]:
        """Find form element using multiple intelligent strategies."""
        
        # Strategy 1: Primary selector
        try:
            element = await self.page.query_selector(field.element_selector)
            if element:
                return element
        except:
            pass
            
        # Strategy 2: Try alternative selectors based on context clues
        for clue in field.context_clues:
            if clue:
                # Try name attribute
                try:
                    element = await self.page.query_selector(f'[name="{clue}"]')
                    if element:
                        return element
                except:
                    pass
                    
                # Try ID
                try:
                    element = await self.page.query_selector(f'#{clue}')
                    if element:
                        return element
                except:
                    pass
                    
                # Try placeholder
                try:
                    element = await self.page.query_selector(f'[placeholder*="{clue}"]')
                    if element:
                        return element
                except:
                    pass
                    
        # Strategy 3: Fuzzy matching with AI
        try:
            # Get all input elements and let AI choose
            inputs = await self.page.query_selector_all('input, textarea, select')
            for input_elem in inputs:
                # Check if this could be our field
                name = await input_elem.get_attribute('name') or ''
                id_attr = await input_elem.get_attribute('id') or ''
                placeholder = await input_elem.get_attribute('placeholder') or ''
                
                # Simple fuzzy matching
                field_keywords = field.field_purpose.replace('_', ' ').split()
                combined_text = f"{name} {id_attr} {placeholder}".lower()
                
                if any(keyword.lower() in combined_text for keyword in field_keywords):
                    return input_elem
        except:
            pass
            
        return None

    async def _select_option_intelligently(self, element, value: str):
        """Intelligently select option from dropdown."""
        
        try:
            # Get all options
            options = await element.query_selector_all('option')
            
            for option in options:
                option_text = await option.text_content()
                option_value = await option.get_attribute('value')
                
                # Exact match
                if option_text == value or option_value == value:
                    await element.select_option(option_value or option_text)
                    return
                    
                # Fuzzy match
                if value.lower() in option_text.lower():
                    await element.select_option(option_value or option_text)
                    return
                    
        except Exception as e:
            # Fallback: try to type the value
            await element.fill(value)

    async def _submit_application_intelligently(self) -> Dict[str, Any]:
        """Intelligently submit the application."""
        
        try:
            # Look for submit buttons
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("submit")',
                'button:has-text("apply")',
                'button:has-text("send")',
                '.submit-btn',
                '.apply-btn'
            ]
            
            for selector in submit_selectors:
                elements = await self.page.query_selector_all(selector)
                for element in elements:
                    try:
                        # Check if button is visible and enabled
                        if await element.is_visible() and await element.is_enabled():
                            await element.click()
                            
                            # Wait for submission
                            await self.page.wait_for_load_state('networkidle', timeout=10000)
                            
                            return {
                                'success': True,
                                'action': 'clicked_submit',
                                'selector': selector
                            }
                    except:
                        continue
                        
            return {'success': False, 'error': 'No submit button found'}
            
        except Exception as e:
            return {'success': False, 'error': f"Submit failed: {str(e)}"}

    async def take_screenshot(self, filename: str = None) -> str:
        """Take screenshot of current page."""
        
        if not filename:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            
        try:
            await self.page.screenshot(path=filename, full_page=True)
            return filename
        except Exception as e:
            self.logger.error(f"Screenshot failed: {str(e)}")
            return ""

    async def get_page_analysis(self) -> Dict[str, Any]:
        """Get current page analysis."""
        
        if not self.cognitive_browser:
            return {'error': 'Cognitive browser not initialized'}
            
        insight = await self.cognitive_browser.analyze_page_intelligently()
        
        return {
            'page_type': insight.page_type.value,
            'confidence': insight.confidence,
            'reasoning': insight.reasoning,
            'next_actions': [action.value for action in insight.next_actions],
            'form_fields_count': len(insight.form_fields),
            'key_elements_count': len(insight.key_elements),
            'analysis_time': insight.semantic_context['analysis_time'],
            'url': self.page.url,
            'title': await self.page.title()
        }

    async def close(self):
        """Close browser and cleanup."""
        
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
            
        self.cognitive_browser = None
        self.logger.info("Browser closed")

    def get_navigation_history(self) -> List[Dict[str, Any]]:
        """Get navigation history."""
        return self.navigation_history

    def get_application_progress(self) -> Dict[str, Any]:
        """Get current application progress."""
        return self.application_progress 