"""
Enterprise Job Application Agent - AI-Powered Automation

Advanced AI agent for automated job applications with intelligent form filling,
semantic analysis, and dynamic content generation.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from job_application_agent.core.config import Config
from job_application_agent.core.llm_service import LLMService
from job_application_agent.core.memory.profile_store import ProfileStore
from job_application_agent.core.memory.working_memory import WorkingMemory
from job_application_agent.tools.browser_tool import BrowserTool
from job_application_agent.tools.intelligent_form_filler import IntelligentFormFiller
from job_application_agent.tools.registry import ToolRegistry
from job_application_agent.core.crew_orchestrator import CrewOrchestrator, JobApplicationTask
from job_application_agent.core.advanced_cache import AdvancedCache
from job_application_agent.core.performance_monitor import PerformanceMonitor
from job_application_agent.tools.browser_tool import BrowserTool


class JobApplicationAgent:
    """
    Enterprise-grade AI job application agent.
    
    Features:
    - AI-powered form analysis and field mapping
    - Intelligent content generation for open-ended questions
    - Multi-platform support with adaptive strategies
    - Advanced error handling and recovery
    - Performance optimization and caching
    - Comprehensive logging and monitoring
    """
    
    def __init__(self, config: Config):
        """Initialize the enterprise job application agent."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize core components
        self.llm_service = LLMService(config)
        self.profile_store = ProfileStore(config.profile_path)
        self.working_memory = WorkingMemory()
        
        # Initialize advanced systems
        self.cache = AdvancedCache(config)
        self.performance_monitor = PerformanceMonitor(config)
        self.crew_orchestrator = CrewOrchestrator(config)
        
        # Initialize tools (browser tool will be created when needed with cognitive capabilities)
        self.browser_tool = None
        self.intelligent_filler = None
        self.tool_registry = ToolRegistry()
        
        # Register tools
        self._register_tools()
        
        # Performance tracking
        self.session_stats = {
            'applications_attempted': 0,
            'applications_successful': 0,
            'total_fields_filled': 0,
            'ai_content_generated': 0,
            'start_time': datetime.now()
        }
    
    async def initialize(self) -> None:
        """Initialize the agent and its components."""
        self.logger.info("🚀 Initializing Cognitive Job Application Agent")
        
        # LLM service is already initialized in constructor
        
        # Memory systems and performance monitoring are already initialized
        
        self.logger.info("✅ Agent initialization complete")
    

    
    def _register_tools(self) -> None:
        """Register all available tools."""
        # Tools will be registered dynamically when browser is initialized
        self.tool_registry.register_tool('submit_application', self._submit_application_enhanced)
        self.tool_registry.register_tool('verify_submission', self._verify_submission_enhanced)
    
    async def apply_to_job(self, job_url: str, additional_context: str = None) -> Dict[str, Any]:
        """Apply to a job with enhanced cognitive automation."""
        
        job_start_time = datetime.now()
        self.logger.info(f"🎯 Starting intelligent job application for: {job_url}")
        
        # Performance monitoring context
        async with self.performance_monitor.operation_timer(f"job_application_{job_url}") as timer:
            try:
                # Initialize browser if needed
                if not self.browser_tool:
                    self.browser_tool = BrowserTool(self.config, self.llm_service)
                    await self.browser_tool.start()
                
                # Step 1: Navigate to job with cognitive analysis
                self.logger.info("🔍 Navigating to job posting...")
                nav_result = await self.browser_tool.navigate_to_job(job_url)
                
                if not nav_result['success']:
                    return {
                        'success': False,
                        'error': f"Failed to navigate to job: {nav_result.get('error', 'Unknown error')}",
                        'job_url': job_url,
                        'duration': (datetime.now() - job_start_time).total_seconds()
                    }
                
                # Log cognitive analysis
                self.logger.info(f"📊 Page Analysis: {nav_result['reasoning']}")
                self.logger.info(f"📄 Page Type: {nav_result['page_type']} (confidence: {nav_result['confidence']:.1%})")
                
                # Step 2: Get user profile data
                profile_data = await self._get_enhanced_profile_data()
                
                # Step 3: Apply intelligently using cognitive browser
                self.logger.info("🤖 Starting cognitive job application process...")
                
                application_result = await self.browser_tool.apply_to_job_intelligently(profile_data)
                
                # Step 4: Process results and generate summary
                total_duration = (datetime.now() - job_start_time).total_seconds()
                
                # Log detailed results
                self.logger.info(f"✅ Application completed in {total_duration:.1f}s")
                self.logger.info(f"🎯 Success: {application_result['success']}")
                self.logger.info(f"📝 Steps taken: {len(application_result.get('application_steps', []))}")
                
                # Enhanced result with cognitive insights
                result = {
                    'success': application_result['success'],
                    'job_url': job_url,
                    'duration': total_duration,
                    'page_analysis': {
                        'initial_page_type': nav_result['page_type'],
                        'final_page_type': application_result.get('final_page_type'),
                        'confidence': nav_result['confidence'],
                        'reasoning': nav_result['reasoning']
                    },
                    'application_steps': application_result.get('application_steps', []),
                    'cognitive_insights': {
                        'navigation_intelligence': nav_result.get('next_actions', []),
                        'form_filling_performance': {
                            'filled_fields': sum(step.get('filled_fields', 0) for step in application_result.get('application_steps', [])),
                            'failed_fields': sum(step.get('failed_fields', 0) for step in application_result.get('application_steps', []))
                        }
                    },
                    'performance_metrics': {
                        'analysis_time': nav_result.get('analysis_time', 0),
                        'total_time': total_duration,
                        'efficiency_score': self._calculate_efficiency_score(application_result, total_duration)
                    }
                }
                
                # Record performance metrics
                self.performance_monitor.record_metric('job_application_success', 1 if application_result['success'] else 0)
                self.performance_monitor.record_metric('job_application_duration', total_duration)
                
                # Take screenshot for verification
                try:
                    screenshot_path = await self.browser_tool.take_screenshot(
                        f"job_application_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    )
                    if screenshot_path:
                        result['screenshot'] = screenshot_path
                except Exception as e:
                    self.logger.warning(f"Screenshot failed: {str(e)}")
                
                return result
                
            except Exception as e:
                error_msg = f"Cognitive job application failed: {str(e)}"
                self.logger.error(error_msg)
                
                # Record failure metrics
                self.performance_monitor.record_metric('job_application_success', 0)
                self.performance_monitor.record_metric('job_application_errors', 1)
                
                return {
                    'success': False,
                    'error': error_msg,
                    'job_url': job_url,
                    'duration': (datetime.now() - job_start_time).total_seconds()
                }

    def _calculate_efficiency_score(self, application_result: Dict[str, Any], duration: float) -> float:
        """Calculate efficiency score based on performance metrics."""
        
        base_score = 100.0
        
        # Penalize for long duration (target: under 30 seconds)
        if duration > 30:
            base_score -= min(50, (duration - 30) * 2)
        
        # Reward for successful completion
        if application_result.get('success'):
            base_score += 20
        
        # Penalize for failed fields
        failed_fields = sum(step.get('failed_fields', 0) for step in application_result.get('application_steps', []))
        base_score -= failed_fields * 10
        
        # Reward for filled fields
        filled_fields = sum(step.get('filled_fields', 0) for step in application_result.get('application_steps', []))
        base_score += filled_fields * 5
        
        return max(0, min(100, base_score))

    async def _get_enhanced_profile_data(self) -> Dict[str, Any]:
        """Get enhanced profile data with additional context."""
        
        # Load base profile
        base_profile = await self._load_user_profile()
        
        # Enhanced with additional intelligent defaults
        enhanced_profile = {
            **base_profile,
            'experience_years': base_profile.get('experience_years', '5'),
            'salary_expectation': base_profile.get('salary_expectation', '80000'),
            'availability': base_profile.get('availability', 'Immediately'),
            'willing_to_relocate': base_profile.get('willing_to_relocate', 'Yes'),
            'work_authorization': base_profile.get('work_authorization', 'Authorized to work'),
            'portfolio': base_profile.get('portfolio', 'https://sarahchen.dev'),
            'github': base_profile.get('github', 'https://github.com/sarahchen'),
            'linkedin': base_profile.get('linkedin', 'https://linkedin.com/in/sarah-chen')
        }
        
        return enhanced_profile

    async def _load_user_profile(self) -> Dict[str, Any]:
        """Load user profile data."""
        try:
            # Try to load from profile store
            profile_data = self.profile_store.get_profile_data()
            if profile_data:
                return profile_data
                
            # Fallback to default profile
            return {
                'first_name': 'Sarah',
                'last_name': 'Chen',
                'email': 'sarah.chen@email.com',
                'phone': '(555) 123-4567',
                'address': '123 Main St, San Francisco, CA 94102',
                'experience_years': '5',
                'linkedin': 'https://linkedin.com/in/sarah-chen',
                'portfolio': 'https://sarahchen.dev'
            }
        except Exception as e:
            self.logger.warning(f"Failed to load profile: {str(e)}, using defaults")
            return {
                'first_name': 'Sarah',
                'last_name': 'Chen',
                'email': 'sarah.chen@email.com',
                'phone': '(555) 123-4567'
            }

    async def get_intelligent_page_analysis(self) -> Dict[str, Any]:
        """Get current intelligent page analysis."""
        
        if not self.browser_tool:
            return {'error': 'Browser not initialized'}
            
        return await self.browser_tool.get_page_analysis()

    async def get_cognitive_insights(self) -> Dict[str, Any]:
        """Get cognitive browsing insights and navigation history."""
        
        if not self.browser_tool:
            return {'error': 'Browser not initialized'}
            
        return {
            'navigation_history': self.browser_tool.get_navigation_history(),
            'application_progress': self.browser_tool.get_application_progress(),
            'current_page_analysis': await self.browser_tool.get_page_analysis()
        }
    
    async def _submit_application_enhanced(self) -> Dict[str, Any]:
        """Enhanced application submission with multiple strategies."""
        try:
            # Strategy 1: Look for primary submit buttons
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Submit")',
                'button:has-text("Apply")',
                'button:has-text("Send Application")',
                '[data-testid*="submit"]',
                '[data-testid*="apply"]',
                '.submit-btn',
                '.apply-btn',
                '#submit',
                '#apply'
            ]
            
            for selector in submit_selectors:
                try:
                    element = await self.browser_tool.page.query_selector(selector)
                    if element and await element.is_visible() and await element.is_enabled():
                        # Scroll element into view
                        await element.scroll_into_view_if_needed()
                        
                        # Click with retry
                        for attempt in range(3):
                            try:
                                await element.click()
                                
                                # Wait for navigation or response
                                await self.browser_tool.page.wait_for_load_state('networkidle', timeout=10000)
                                
                                return {
                                    'success': True,
                                    'action': 'submit_application_enhanced',
                                    'method': 'button_click',
                                    'selector': selector,
                                    'attempt': attempt + 1
                                }
                                
                            except Exception as e:
                                if attempt < 2:
                                    await asyncio.sleep(1)
                                    continue
                                raise e
                                
                except Exception as e:
                    self.logger.debug(f"Submit selector {selector} failed: {str(e)}")
                    continue
            
            # Strategy 2: Form submission
            forms = await self.browser_tool.page.query_selector_all('form')
            for form in forms:
                try:
                    await form.evaluate('form => form.submit()')
                    await self.browser_tool.page.wait_for_load_state('networkidle', timeout=10000)
                    
                    return {
                        'success': True,
                        'action': 'submit_application_enhanced',
                        'method': 'form_submit'
                    }
                    
                except Exception as e:
                    continue
            
            return {
                'success': False,
                'action': 'submit_application_enhanced',
                'error': 'No working submit method found'
            }
            
        except Exception as e:
            self.logger.error(f"Enhanced submission failed: {str(e)}")
            return {
                'success': False,
                'action': 'submit_application_enhanced',
                'error': str(e)
            }
    
    async def _verify_submission_enhanced(self) -> Dict[str, Any]:
        """Enhanced submission verification with multiple indicators."""
        try:
            # Wait a moment for page to update
            await asyncio.sleep(2)
            
            current_url = self.browser_tool.page.url
            page_title = await self.browser_tool.page.title()
            
            # Success indicators
            success_indicators = [
                # Text-based indicators
                'text="Thank you"',
                'text="Application submitted"',
                'text="Successfully submitted"',
                'text="Application received"',
                'text="We have received your application"',
                'text="Your application has been submitted"',
                
                # Class-based indicators
                '.success',
                '.confirmation',
                '.thank-you',
                '.submitted',
                '[data-testid*="success"]',
                '[data-testid*="confirmation"]',
                
                # ID-based indicators
                '#success',
                '#confirmation',
                '#thank-you'
            ]
            
            found_indicators = []
            for indicator in success_indicators:
                try:
                    element = await self.browser_tool.page.query_selector(indicator)
                    if element and await element.is_visible():
                        text = await element.inner_text()
                        found_indicators.append({
                            'selector': indicator,
                            'text': text[:100]  # Limit text length
                        })
                except Exception:
                    continue
            
            # URL-based verification
            url_success_patterns = [
                'success', 'thank', 'confirmation', 'submitted', 
                'complete', 'done', 'received'
            ]
            
            url_indicators = []
            for pattern in url_success_patterns:
                if pattern in current_url.lower():
                    url_indicators.append(pattern)
            
            # Title-based verification
            title_success_patterns = [
                'thank you', 'success', 'submitted', 'confirmation', 'complete'
            ]
            
            title_indicators = []
            for pattern in title_success_patterns:
                if pattern in page_title.lower():
                    title_indicators.append(pattern)
            
            # Determine success
            is_successful = bool(found_indicators or url_indicators or title_indicators)
            
            return {
                'success': is_successful,
                'action': 'verify_submission_enhanced',
                'verification_details': {
                    'current_url': current_url,
                    'page_title': page_title,
                    'element_indicators': found_indicators,
                    'url_indicators': url_indicators,
                    'title_indicators': title_indicators,
                    'confidence_score': self._calculate_verification_confidence(
                        found_indicators, url_indicators, title_indicators
                    )
                }
            }
            
        except Exception as e:
            self.logger.error(f"Enhanced verification failed: {str(e)}")
            return {
                'success': False,
                'action': 'verify_submission_enhanced',
                'error': str(e)
            }
    
    def _calculate_verification_confidence(self, element_indicators: List[Dict], 
                                         url_indicators: List[str], 
                                         title_indicators: List[str]) -> float:
        """Calculate confidence score for submission verification."""
        score = 0.0
        
        # Element indicators (highest weight)
        if element_indicators:
            score += 0.6
            if len(element_indicators) > 1:
                score += 0.2
        
        # URL indicators (medium weight)
        if url_indicators:
            score += 0.3
        
        # Title indicators (lower weight)
        if title_indicators:
            score += 0.2
        
        return min(score, 1.0)
    
    def _generate_optimization_recommendations(self, missing_critical: List[str]) -> List[str]:
        """Generate recommendations for optimization."""
        recommendations = []
        
        if missing_critical:
            recommendations.append(f"Critical fields missing: {', '.join(missing_critical)}")
            recommendations.append("Consider manual review of failed critical fields")
        
        recommendations.append("Review AI-generated content for accuracy and relevance")
        recommendations.append("Verify all contact information is correctly filled")
        
        return recommendations
    
    def _generate_application_summary(self, workflow_results: List[Dict[str, Any]], 
                                    job_url: str) -> Dict[str, Any]:
        """Generate comprehensive application summary."""
        successful_steps = [r for r in workflow_results if r.get('success')]
        failed_steps = [r for r in workflow_results if not r.get('success')]
        
        # Extract fill statistics
        fill_stats = {}
        for result in workflow_results:
            if result.get('action') == 'fill_application_intelligently':
                fill_stats = result.get('summary', {})
                break
        
        # Determine overall success
        submission_successful = any(
            r.get('action') == 'submit_application_enhanced' and r.get('success') 
            for r in workflow_results
        )
        
        verification_successful = any(
            r.get('action') == 'verify_submission_enhanced' and r.get('success') 
            for r in workflow_results
        )
        
        overall_success = submission_successful and verification_successful
        
        return {
            'success': overall_success,
            'job_url': job_url,
            'summary': {
                'total_workflow_steps': len(workflow_results),
                'successful_steps': len(successful_steps),
                'failed_steps': len(failed_steps),
                'submission_successful': submission_successful,
                'verification_successful': verification_successful,
                'fill_statistics': fill_stats,
                'session_statistics': self.session_stats.copy()
            },
            'workflow_results': workflow_results,
            'recommendations': self._generate_final_recommendations(
                workflow_results, overall_success
            )
        }
    
    def _generate_final_recommendations(self, workflow_results: List[Dict[str, Any]], 
                                      success: bool) -> List[str]:
        """Generate final recommendations based on application results."""
        recommendations = []
        
        if success:
            recommendations.append("Application submitted successfully!")
            recommendations.append("Monitor your email for responses from the employer")
        else:
            recommendations.append("Application may need manual completion")
            
            # Analyze failure points
            failed_steps = [r for r in workflow_results if not r.get('success')]
            if failed_steps:
                recommendations.append("Review failed steps for manual intervention")
        
        # Add performance recommendations
        fill_results = next((r for r in workflow_results 
                           if r.get('action') == 'fill_application_intelligently'), None)
        
        if fill_results:
            success_rate = fill_results.get('summary', {}).get('success_rate', 0)
            if success_rate < 0.8:
                recommendations.append("Consider updating profile data for better field matching")
        
        return recommendations
    
    async def _cleanup_session(self) -> None:
        """Cleanup session resources."""
        try:
            # Clear working memory
            self.working_memory.clear()
            
            # Note: Browser cleanup is handled by the browser tool itself
            self.logger.info("Session cleanup completed")
            
        except Exception as e:
            self.logger.error(f"Session cleanup failed: {str(e)}")
    
    async def close(self) -> None:
        """Close the agent and cleanup all resources."""
        try:
            # Close advanced systems
            if hasattr(self, 'cache'):
                await self.cache.close()
            
            if hasattr(self, 'performance_monitor'):
                self.performance_monitor.stop_monitoring()
            
            if hasattr(self, 'crew_orchestrator'):
                await self.crew_orchestrator.close()
            
            # Close browser tool if it exists
            if self.browser_tool:
                await self.browser_tool.close()
                
            self.logger.info("🧠 Cognitive Job Application Agent closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing agent: {str(e)}") 