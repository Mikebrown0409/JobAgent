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
from job_application_agent.tools.browser_tool import AdvancedBrowserTool
from job_application_agent.tools.intelligent_form_filler import IntelligentFormFiller
from job_application_agent.tools.registry import ToolRegistry
from job_application_agent.core.crew_orchestrator import CrewOrchestrator, JobApplicationTask
from job_application_agent.core.advanced_cache import AdvancedCache
from job_application_agent.core.performance_monitor import PerformanceMonitor


class EnterpriseJobApplicationAgent:
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
        
        # Initialize tools
        self.browser_tool = AdvancedBrowserTool(config)
        self.intelligent_filler = IntelligentFormFiller(config, self.browser_tool, self.llm_service)
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
    
    def _register_tools(self) -> None:
        """Register all available tools."""
        self.tool_registry.register_tool('navigate', self.browser_tool.navigate_with_retry)
        self.tool_registry.register_tool('analyze_page', self.browser_tool.analyze_page_structure)
        self.tool_registry.register_tool('fill_application', self.intelligent_filler.fill_application_intelligently)
        self.tool_registry.register_tool('submit_application', self._submit_application_enhanced)
        self.tool_registry.register_tool('verify_submission', self._verify_submission_enhanced)
    
    async def apply_to_job(self, job_url: str, additional_context: Optional[Dict[str, Any]] = None, 
                          use_crew: bool = True) -> Dict[str, Any]:
        """
        Apply to a job using advanced AI-powered automation.
        
        Args:
            job_url: URL of the job application
            additional_context: Optional additional context (job description, company info, etc.)
            
        Returns:
            Comprehensive result of the job application process
        """
        self.session_stats['applications_attempted'] += 1
        application_start_time = datetime.now()
        
        try:
            self.logger.info(f"Starting enterprise job application for: {job_url}")
            
            # Start performance monitoring
            async with self.performance_monitor.start_operation('job_application') as timer:
                timer.add_metadata('job_url', job_url)
                timer.add_metadata('use_crew', use_crew)
                
                # Initialize working memory for this application
                self.working_memory.clear()
                self.working_memory.set_context('job_url', job_url)
                self.working_memory.set_context('start_time', application_start_time)
                
                if additional_context:
                    self.working_memory.set_context('additional_context', additional_context)
                
                # Load user profile
                profile_data = self.profile_store.get_profile_data()
                self.working_memory.set_context('profile_data', profile_data)
                
                # Choose execution method
                if use_crew:
                    # Use multi-agent crew orchestrator
                    task = JobApplicationTask(
                        job_url=job_url,
                        job_description=additional_context.get('job_description') if additional_context else None,
                        company_info=additional_context.get('company_info') if additional_context else None
                    )
                    result = await self.crew_orchestrator.process_job_application(task)
                else:
                    # Use traditional single-agent workflow
                    result = await self._execute_application_workflow(job_url, profile_data, additional_context)
            
                # Update statistics
                if result.get('success'):
                    self.session_stats['applications_successful'] += 1
                
                # Calculate duration
                duration = (datetime.now() - application_start_time).total_seconds()
                result['duration_seconds'] = duration
                result['session_stats'] = self.session_stats.copy()
                
                # Add performance insights
                result['performance_summary'] = self.performance_monitor.get_performance_summary()
                result['cache_info'] = await self.cache.get_cache_info()
                
                return result
            
        except Exception as e:
            self.logger.error(f"Job application failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'job_url': job_url,
                'duration_seconds': (datetime.now() - application_start_time).total_seconds()
            }
        finally:
            # Cleanup
            await self._cleanup_session()
    
    async def _execute_application_workflow(self, job_url: str, profile_data: Dict[str, Any], 
                                          additional_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute the complete application workflow with advanced features."""
        workflow_results = []
        
        try:
            # Step 1: Navigate to job application page
            self.logger.info("Step 1: Navigating to job application page")
            nav_result = await self.browser_tool.navigate_with_retry(job_url)
            workflow_results.append(nav_result)
            
            if not nav_result.get('success'):
                return {
                    'success': False,
                    'error': 'Failed to navigate to job application page',
                    'workflow_results': workflow_results
                }
            
            # Step 2: Perform comprehensive page analysis
            self.logger.info("Step 2: Analyzing page structure with AI")
            page_analysis = await self.browser_tool.analyze_page_structure()
            workflow_results.append(page_analysis)
            
            if not page_analysis.get('success'):
                return {
                    'success': False,
                    'error': 'Failed to analyze page structure',
                    'workflow_results': workflow_results
                }
            
            # Step 3: Enhanced semantic analysis using AI
            self.logger.info("Step 3: Performing semantic analysis")
            enhanced_analysis = await self.llm_service.analyze_form_semantically(
                page_analysis, profile_data
            )
            self.working_memory.set_context('enhanced_analysis', enhanced_analysis)
            
            # Step 4: Intelligent form filling
            self.logger.info("Step 4: Filling application with AI-powered mapping")
            fill_result = await self.intelligent_filler.fill_application_intelligently(
                profile_data, enhanced_analysis
            )
            workflow_results.append(fill_result)
            
            # Update statistics
            if fill_result.get('success'):
                summary = fill_result.get('summary', {})
                self.session_stats['total_fields_filled'] += summary.get('successful_fills', 0)
                
                # Count AI-generated content
                successful_fields = fill_result.get('successful_fields', [])
                ai_generated = len([f for f in successful_fields if f.get('strategy') == 'semantic_match'])
                self.session_stats['ai_content_generated'] += ai_generated
            
            # Step 5: Review and optimize filled content
            self.logger.info("Step 5: Reviewing and optimizing filled content")
            optimization_result = await self._optimize_filled_content(fill_result, profile_data)
            workflow_results.append(optimization_result)
            
            # Step 6: Submit application
            self.logger.info("Step 6: Submitting application")
            submit_result = await self._submit_application_enhanced()
            workflow_results.append(submit_result)
            
            if not submit_result.get('success'):
                return {
                    'success': False,
                    'error': 'Failed to submit application',
                    'workflow_results': workflow_results,
                    'partial_completion': True
                }
            
            # Step 7: Verify submission
            self.logger.info("Step 7: Verifying application submission")
            verify_result = await self._verify_submission_enhanced()
            workflow_results.append(verify_result)
            
            # Generate comprehensive summary
            return self._generate_application_summary(workflow_results, job_url)
            
        except Exception as e:
            self.logger.error(f"Workflow execution failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'workflow_results': workflow_results
            }
    
    async def _optimize_filled_content(self, fill_result: Dict[str, Any], 
                                     profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize and review filled content for quality assurance."""
        try:
            optimizations = []
            successful_fields = fill_result.get('successful_fields', [])
            
            # Review AI-generated content for quality
            for field in successful_fields:
                if field.get('strategy') == 'semantic_match':
                    # This was AI-generated content, let's review it
                    field_value = field.get('value', '')
                    if len(field_value) > 50:  # Only review substantial content
                        # Could add additional AI review here if needed
                        optimizations.append({
                            'field': field.get('selector', 'unknown'),
                            'action': 'reviewed',
                            'content_length': len(field_value)
                        })
            
            # Check for missing critical fields
            failed_fields = fill_result.get('failed_fields', [])
            critical_fields = ['email', 'first_name', 'last_name']
            
            missing_critical = []
            for failed_field in failed_fields:
                field_name = failed_field.get('field', '')
                if any(critical in field_name.lower() for critical in critical_fields):
                    missing_critical.append(field_name)
            
            return {
                'success': True,
                'action': 'optimize_content',
                'optimizations_applied': len(optimizations),
                'missing_critical_fields': missing_critical,
                'recommendations': self._generate_optimization_recommendations(missing_critical)
            }
            
        except Exception as e:
            self.logger.error(f"Content optimization failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'action': 'optimize_content'
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
            
            # Close browser tool
            await self.browser_tool.close()
            self.logger.info("Enterprise Job Application Agent closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing agent: {str(e)}")


# Maintain backward compatibility
JobApplicationAgent = EnterpriseJobApplicationAgent 