"""
Intelligent Form Filler - AI-Powered Form Automation

Enterprise-grade form filling system with AI-powered field mapping,
semantic matching, and dynamic content generation for any job application format.
"""

import asyncio
import logging
import re
from typing import Dict, Any, Optional, List, Tuple, Union
from difflib import SequenceMatcher
from datetime import datetime, timedelta
import json
from dataclasses import dataclass
from enum import Enum

from job_application_agent.core.config import Config
from job_application_agent.tools.browser_tool import AdvancedBrowserTool


class FieldMatchStrategy(Enum):
    """Field matching strategies in order of preference."""
    EXACT_MATCH = "exact_match"
    SEMANTIC_MATCH = "semantic_match"
    FUZZY_MATCH = "fuzzy_match"
    PATTERN_MATCH = "pattern_match"
    CONTEXT_MATCH = "context_match"
    FALLBACK_MATCH = "fallback_match"


@dataclass
class FieldMapping:
    """Represents a mapping between profile data and form field."""
    field_info: Dict[str, Any]
    profile_key: str
    profile_value: Any
    strategy: FieldMatchStrategy
    confidence: float
    selectors: List[str]
    fill_method: str  # 'type', 'select', 'upload', 'click'
    pre_actions: List[str] = None  # Actions to perform before filling
    post_actions: List[str] = None  # Actions to perform after filling


class IntelligentFormFiller:
    """
    AI-powered form filler that can handle any job application format.
    
    Features:
    - Semantic field matching with multiple strategies
    - Dynamic content generation for open-ended questions
    - Advanced data extraction and formatting
    - Platform-specific optimizations
    - Robust error handling and recovery
    """
    
    def __init__(self, config: Config, browser_tool: AdvancedBrowserTool, llm_service):
        """Initialize the intelligent form filler."""
        self.config = config
        self.browser_tool = browser_tool
        self.llm_service = llm_service
        self.logger = logging.getLogger(__name__)
        
        # Caching for performance
        self._field_mappings_cache: Dict[str, List[FieldMapping]] = {}
        self._generated_content_cache: Dict[str, str] = {}
        
        # Performance tracking
        self._fill_statistics = {
            'total_fields': 0,
            'successful_fills': 0,
            'failed_fills': 0,
            'strategy_usage': {strategy.value: 0 for strategy in FieldMatchStrategy}
        }
    
    async def fill_application_intelligently(self, profile_data: Dict[str, Any], 
                                           page_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fill job application using intelligent field mapping and AI-generated content.
        
        Args:
            profile_data: Complete user profile data
            page_analysis: Analyzed page structure from browser tool
            
        Returns:
            Result of intelligent form filling
        """
        try:
            self.logger.info("Starting intelligent form filling")
            
            # Extract forms and fields from page analysis
            page_info = page_analysis.get('page_info', {})
            forms = page_info.get('forms', [])
            standalone_fields = page_info.get('standalone_fields', [])
            
            if not forms and not standalone_fields:
                return {
                    "success": False,
                    "error": "No forms or fields found on page",
                    "action": "fill_application_intelligently"
                }
            
            # Generate intelligent field mappings
            all_fields = []
            for form in forms:
                all_fields.extend(form.get('fields', []))
            all_fields.extend(standalone_fields)
            
            field_mappings = await self._generate_intelligent_mappings(profile_data, all_fields)
            
            # Sort mappings by confidence score (highest first)
            field_mappings.sort(key=lambda x: x.confidence, reverse=True)
            
            # Fill fields using the mappings
            fill_results = await self._execute_field_mappings(field_mappings, profile_data, page_info)
            
            # Generate summary
            return self._generate_fill_summary(fill_results, field_mappings)
            
        except Exception as e:
            self.logger.error(f"Intelligent form filling failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "action": "fill_application_intelligently"
            }
    
    async def _generate_intelligent_mappings(self, profile_data: Dict[str, Any], 
                                           fields: List[Dict[str, Any]]) -> List[FieldMapping]:
        """Generate intelligent field mappings using multiple strategies."""
        mappings = []
        
        for field in fields:
            if not field.get('is_visible', True) or not field.get('is_enabled', True):
                continue
            
            mapping = await self._map_field_intelligently(field, profile_data)
            if mapping and mapping.confidence > 0.1:  # Only include mappings with decent confidence
                mappings.append(mapping)
        
        return mappings
    
    async def _map_field_intelligently(self, field: Dict[str, Any], 
                                     profile_data: Dict[str, Any]) -> Optional[FieldMapping]:
        """Map a single field using intelligent strategies."""
        field_purpose = field.get('field_purpose', 'text')
        field_type = field.get('type', 'text')
        
        # Try different mapping strategies
        strategies = [
            self._try_exact_match,
            self._try_semantic_match,
            self._try_fuzzy_match,
            self._try_pattern_match,
            self._try_context_match,
            self._try_fallback_match
        ]
        
        best_mapping = None
        best_confidence = 0.0
        
        for strategy_func in strategies:
            try:
                mapping = await strategy_func(field, profile_data)
                if mapping and mapping.confidence > best_confidence:
                    best_mapping = mapping
                    best_confidence = mapping.confidence
                    
                    # If we have a high-confidence match, use it
                    if best_confidence > 0.8:
                        break
                        
            except Exception as e:
                self.logger.debug(f"Strategy {strategy_func.__name__} failed: {str(e)}")
                continue
        
        return best_mapping
    
    async def _try_exact_match(self, field: Dict[str, Any], 
                             profile_data: Dict[str, Any]) -> Optional[FieldMapping]:
        """Try exact field purpose matching."""
        field_purpose = field.get('field_purpose', '')
        
        # Direct mapping for common fields
        exact_mappings = {
            'first_name': ('basics.name', lambda name: name.split()[0] if name else ''),
            'last_name': ('basics.name', lambda name: ' '.join(name.split()[1:]) if name and len(name.split()) > 1 else ''),
            'full_name': ('basics.name', lambda name: name),
            'email': ('basics.email', lambda email: email),
            'phone': ('basics.phone', lambda phone: phone),
            'address': ('basics.location.address', lambda addr: addr),
            'city': ('basics.location.city', lambda city: city),
            'state': ('basics.location.region', lambda region: region),
            'zip': ('basics.location.postalCode', lambda zip_code: zip_code),
            'country': ('basics.location.country', lambda country: country),
            'linkedin': ('basics.linkedin', lambda linkedin: linkedin),
            'website': ('basics.website', lambda website: website),
        }
        
        if field_purpose in exact_mappings:
            profile_path, value_func = exact_mappings[field_purpose]
            value = self._get_nested_value(profile_data, profile_path)
            
            if value:
                processed_value = value_func(value)
                if processed_value:
                    return FieldMapping(
                        field_info=field,
                        profile_key=profile_path,
                        profile_value=processed_value,
                        strategy=FieldMatchStrategy.EXACT_MATCH,
                        confidence=0.95,
                        selectors=field.get('selectors', []),
                        fill_method=self._determine_fill_method(field)
                    )
        
        return None
    
    async def _try_semantic_match(self, field: Dict[str, Any], 
                                profile_data: Dict[str, Any]) -> Optional[FieldMapping]:
        """Try semantic field matching using AI understanding."""
        # For open-ended questions and complex fields
        field_purpose = field.get('field_purpose', '')
        label = field.get('label', '')
        placeholder = field.get('placeholder', '')
        context = field.get('context', '')
        
        # Check if this is a text area or long text field
        if field.get('tag') == 'textarea' or field.get('type') == 'text':
            # Generate content for open-ended questions
            if any(keyword in f"{label} {placeholder} {context}".lower() 
                   for keyword in ['why', 'tell us', 'describe', 'explain', 'motivation', 'interest']):
                
                # Generate AI response
                generated_content = await self._generate_contextual_content(
                    field, profile_data
                )
                
                if generated_content:
                    return FieldMapping(
                        field_info=field,
                        profile_key='generated_content',
                        profile_value=generated_content,
                        strategy=FieldMatchStrategy.SEMANTIC_MATCH,
                        confidence=0.85,
                        selectors=field.get('selectors', []),
                        fill_method=self._determine_fill_method(field)
                    )
        
        return None
    
    async def _try_fuzzy_match(self, field: Dict[str, Any], 
                             profile_data: Dict[str, Any]) -> Optional[FieldMapping]:
        """Try fuzzy string matching for field purposes."""
        field_text = f"{field.get('label', '')} {field.get('placeholder', '')} {field.get('name', '')}".lower()
        
        # Profile data paths to search
        searchable_paths = [
            ('basics.name', 'name'),
            ('basics.email', 'email'),
            ('basics.phone', 'phone'),
            ('basics.location.city', 'city'),
            ('basics.location.region', 'state'),
            ('basics.location.country', 'country'),
            ('basics.summary', 'summary'),
        ]
        
        best_match = None
        best_ratio = 0.0
        
        for profile_path, search_term in searchable_paths:
            ratio = SequenceMatcher(None, field_text, search_term).ratio()
            if ratio > best_ratio and ratio > 0.6:  # Minimum threshold
                best_ratio = ratio
                value = self._get_nested_value(profile_data, profile_path)
                if value:
                    best_match = FieldMapping(
                        field_info=field,
                        profile_key=profile_path,
                        profile_value=value,
                        strategy=FieldMatchStrategy.FUZZY_MATCH,
                        confidence=best_ratio * 0.8,  # Reduce confidence for fuzzy matches
                        selectors=field.get('selectors', []),
                        fill_method=self._determine_fill_method(field)
                    )
        
        return best_match
    
    async def _try_pattern_match(self, field: Dict[str, Any], 
                               profile_data: Dict[str, Any]) -> Optional[FieldMapping]:
        """Try pattern-based matching for complex fields."""
        field_text = f"{field.get('label', '')} {field.get('placeholder', '')} {field.get('context', '')}".lower()
        
        # Education patterns
        education_patterns = [
            r'school|university|college|education|degree|institution',
            r'graduation|graduated|alma.mater|study|studied'
        ]
        
        if any(re.search(pattern, field_text) for pattern in education_patterns):
            education = profile_data.get('education', [])
            if education:
                # Get most recent education
                recent_edu = education[0] if education else {}
                institution = recent_edu.get('institution', '')
                if institution:
                    return FieldMapping(
                        field_info=field,
                        profile_key='education.0.institution',
                        profile_value=institution,
                        strategy=FieldMatchStrategy.PATTERN_MATCH,
                        confidence=0.75,
                        selectors=field.get('selectors', []),
                        fill_method=self._determine_fill_method(field)
                    )
        
        # Experience patterns
        experience_patterns = [
            r'experience|work|job|employment|position|company|employer',
            r'current.role|previous.role|job.title'
        ]
        
        if any(re.search(pattern, field_text) for pattern in experience_patterns):
            work = profile_data.get('work', [])
            if work:
                # Get most recent work
                recent_work = work[0] if work else {}
                company = recent_work.get('company', '')
                position = recent_work.get('position', '')
                
                # Choose appropriate value based on field context
                if 'company' in field_text or 'employer' in field_text:
                    value = company
                elif 'position' in field_text or 'title' in field_text or 'role' in field_text:
                    value = position
                else:
                    value = f"{position} at {company}" if position and company else company or position
                
                if value:
                    return FieldMapping(
                        field_info=field,
                        profile_key='work.0',
                        profile_value=value,
                        strategy=FieldMatchStrategy.PATTERN_MATCH,
                        confidence=0.70,
                        selectors=field.get('selectors', []),
                        fill_method=self._determine_fill_method(field)
                    )
        
        return None
    
    async def _try_context_match(self, field: Dict[str, Any], 
                               profile_data: Dict[str, Any]) -> Optional[FieldMapping]:
        """Try matching based on surrounding context."""
        context = field.get('context', '').lower()
        
        # Look for context clues
        if 'salary' in context or 'compensation' in context or 'pay' in context:
            # For salary fields, we might want to skip or provide a range
            return FieldMapping(
                field_info=field,
                profile_key='preference',
                profile_value='Competitive salary based on experience',
                strategy=FieldMatchStrategy.CONTEXT_MATCH,
                confidence=0.60,
                selectors=field.get('selectors', []),
                fill_method=self._determine_fill_method(field)
            )
        
        if 'available' in context or 'start' in context:
            return FieldMapping(
                field_info=field,
                profile_key='preference',
                profile_value='Immediately',
                strategy=FieldMatchStrategy.CONTEXT_MATCH,
                confidence=0.65,
                selectors=field.get('selectors', []),
                fill_method=self._determine_fill_method(field)
            )
        
        return None
    
    async def _try_fallback_match(self, field: Dict[str, Any], 
                                profile_data: Dict[str, Any]) -> Optional[FieldMapping]:
        """Try fallback matching for unrecognized fields."""
        field_type = field.get('type', 'text')
        
        # For select fields, try to find a reasonable default
        if field.get('tag') == 'select':
            return FieldMapping(
                field_info=field,
                profile_key='fallback',
                profile_value='auto_select',  # Special value to trigger smart selection
                strategy=FieldMatchStrategy.FALLBACK_MATCH,
                confidence=0.30,
                selectors=field.get('selectors', []),
                fill_method='select'
            )
        
        # For text fields, leave empty or use profile summary
        if field_type == 'text' and field.get('tag') == 'textarea':
            summary = profile_data.get('basics', {}).get('summary', '')
            if summary:
                return FieldMapping(
                    field_info=field,
                    profile_key='basics.summary',
                    profile_value=summary,
                    strategy=FieldMatchStrategy.FALLBACK_MATCH,
                    confidence=0.40,
                    selectors=field.get('selectors', []),
                    fill_method='type'
                )
        
        return None
    
    async def _generate_contextual_content(self, field: Dict[str, Any], 
                                         profile_data: Dict[str, Any]) -> str:
        """Generate contextual content for open-ended questions using AI."""
        cache_key = f"{field.get('label', '')}-{field.get('placeholder', '')}"
        
        if cache_key in self._generated_content_cache:
            return self._generated_content_cache[cache_key]
        
        try:
            # Create prompt for content generation
            field_context = {
                'label': field.get('label', ''),
                'placeholder': field.get('placeholder', ''),
                'context': field.get('context', ''),
                'type': field.get('type', 'text')
            }
            
            # Generate content using LLM
            generated_content = await self.llm_service.generate_contextual_answer(
                field_context, profile_data
            )
            
            # Cache the result
            self._generated_content_cache[cache_key] = generated_content
            
            return generated_content
            
        except Exception as e:
            self.logger.error(f"Content generation failed: {str(e)}")
            return ""
    
    async def _execute_field_mappings(self, mappings: List[FieldMapping], 
                                    profile_data: Dict[str, Any], 
                                    page_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute the field mappings to fill the form."""
        results = []
        
        for mapping in mappings:
            try:
                result = await self._fill_single_field(mapping)
                results.append(result)
                
                # Update statistics
                self._fill_statistics['total_fields'] += 1
                self._fill_statistics['strategy_usage'][mapping.strategy.value] += 1
                
                if result.get('success'):
                    self._fill_statistics['successful_fills'] += 1
                else:
                    self._fill_statistics['failed_fills'] += 1
                
                # Add small delay between fills
                await asyncio.sleep(0.1)
                
            except Exception as e:
                self.logger.error(f"Failed to fill field {mapping.field_info.get('name', 'unknown')}: {str(e)}")
                results.append({
                    'success': False,
                    'error': str(e),
                    'field': mapping.field_info.get('name', 'unknown')
                })
        
        return results
    
    async def _fill_single_field(self, mapping: FieldMapping) -> Dict[str, Any]:
        """Fill a single field using enhanced interaction strategies."""
        field_info = mapping.field_info
        value = mapping.profile_value
        fill_method = mapping.fill_method
        
        # Handle special fill methods first
        if fill_method in ['select', 'upload', 'click']:
            return await self._fill_special_field(mapping)
        
        # For text fields, use the enhanced field interaction
        try:
            result = await self.browser_tool.fill_field_enhanced(field_info, str(value))
            
            if result.get('success'):
                self.logger.info(f"Successfully filled field using enhanced interaction")
                return {
                    'success': True,
                    'value': str(value),
                    'strategy': mapping.strategy.value,
                    'confidence': mapping.confidence,
                    'enhanced_result': result.get('result', {})
                }
            else:
                # Fallback to basic method if enhanced fails
                return await self._fill_basic_field(mapping)
                
        except Exception as e:
            self.logger.warning(f"Enhanced field filling failed, falling back to basic: {str(e)}")
            return await self._fill_basic_field(mapping)
    
    async def _fill_special_field(self, mapping: FieldMapping) -> Dict[str, Any]:
        """Handle special field types (select, upload, click)."""
        field_info = mapping.field_info
        value = mapping.profile_value
        selectors = mapping.selectors
        fill_method = mapping.fill_method
        
        # Try each selector until one works
        for selector in selectors:
            try:
                element = await self.browser_tool.page.query_selector(selector)
                if not element:
                    continue
                
                # Check if element is interactable
                if not await element.is_visible() or not await element.is_enabled():
                    continue
                
                # Perform pre-actions if specified
                if mapping.pre_actions:
                    for action in mapping.pre_actions:
                        await self._execute_action(action, element)
                
                # Fill based on method
                success = False
                if fill_method == 'select':
                    if value == 'auto_select':
                        success = await self._smart_select(element, field_info)
                    else:
                        await element.select_option(value=str(value))
                        success = True
                elif fill_method == 'upload':
                    success = await self._handle_file_upload(element, value, field_info)
                elif fill_method == 'click':
                    await element.click()
                    success = True
                
                # Perform post-actions if specified
                if mapping.post_actions:
                    for action in mapping.post_actions:
                        await self._execute_action(action, element)
                
                if success:
                    self.logger.info(f"Successfully filled special field with selector: {selector}")
                    return {
                        'success': True,
                        'selector': selector,
                        'value': str(value),
                        'strategy': mapping.strategy.value,
                        'confidence': mapping.confidence
                    }
                
            except Exception as e:
                self.logger.debug(f"Selector {selector} failed: {str(e)}")
                continue
        
        return {
            'success': False,
            'error': 'No working selector found for special field',
            'field': field_info.get('name', 'unknown'),
            'attempted_selectors': selectors
        }
    
    async def _fill_basic_field(self, mapping: FieldMapping) -> Dict[str, Any]:
        """Fallback basic field filling method."""
        field_info = mapping.field_info
        value = mapping.profile_value
        selectors = mapping.selectors
        
        # Try each selector until one works
        for selector in selectors:
            try:
                element = await self.browser_tool.page.query_selector(selector)
                if not element:
                    continue
                
                # Check if element is interactable
                if not await element.is_visible() or not await element.is_enabled():
                    continue
                
                # Basic fill approach
                await element.click()  # Focus first
                await element.fill(str(value))
                
                self.logger.info(f"Successfully filled field with basic method: {selector}")
                return {
                    'success': True,
                    'selector': selector,
                    'value': str(value),
                    'strategy': mapping.strategy.value,
                    'confidence': mapping.confidence,
                    'method': 'basic_fallback'
                }
                
            except Exception as e:
                self.logger.debug(f"Basic fill failed for selector {selector}: {str(e)}")
                continue
        
        return {
            'success': False,
            'error': 'No working selector found in basic fallback',
            'field': field_info.get('name', 'unknown'),
            'attempted_selectors': selectors
        }
    
    def _determine_fill_method(self, field: Dict[str, Any]) -> str:
        """Determine the appropriate fill method for a field."""
        tag = field.get('tag', 'input')
        field_type = field.get('type', 'text')
        
        if tag == 'select':
            return 'select'
        elif field_type == 'file':
            return 'upload'
        elif field_type in ['checkbox', 'radio']:
            return 'click'
        else:
            return 'type'
    
    async def _smart_select(self, element, field_info: Dict[str, Any]) -> bool:
        """Intelligently select from dropdown options."""
        try:
            # Get all options
            options = await element.query_selector_all('option')
            if not options:
                return False
            
            option_texts = []
            for option in options:
                text = await option.inner_text()
                value = await option.get_attribute('value')
                option_texts.append((text.strip(), value))
            
            # Select the most appropriate option
            field_context = field_info.get('context', '').lower()
            field_label = field_info.get('label', '').lower()
            
            # Simple heuristics for common selections
            for text, value in option_texts:
                text_lower = text.lower()
                
                # Skip empty or placeholder options
                if not text.strip() or text_lower in ['select', 'choose', 'please select', '-- select --']:
                    continue
                
                # For yes/no questions, default to yes
                if text_lower in ['yes', 'true', '1']:
                    await element.select_option(value=value)
                    return True
                
                # For experience levels, select mid-level
                if 'experience' in field_label and text_lower in ['intermediate', 'mid', '3-5 years', '2-5 years']:
                    await element.select_option(value=value)
                    return True
            
            # Default to first non-empty option
            for text, value in option_texts:
                if text.strip() and text.lower() not in ['select', 'choose', 'please select', '-- select --']:
                    await element.select_option(value=value)
                    return True
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Smart select failed: {str(e)}")
            return False
    
    async def _handle_file_upload(self, element, value: str, field_info: Dict[str, Any]) -> bool:
        """Handle file upload fields."""
        try:
            field_purpose = field_info.get('field_purpose', '')
            
            # Determine which file to upload based on field purpose
            if field_purpose == 'resume' or 'resume' in field_info.get('label', '').lower():
                file_path = self.config.resume_path
            elif field_purpose == 'cover_letter' or 'cover' in field_info.get('label', '').lower():
                file_path = self.config.cover_letter_path
            else:
                # Default to resume
                file_path = self.config.resume_path
            
            if file_path and file_path.exists():
                await element.set_input_files([str(file_path)])
                return True
            else:
                self.logger.warning(f"File not found for upload: {file_path}")
                return False
                
        except Exception as e:
            self.logger.error(f"File upload failed: {str(e)}")
            return False
    
    async def _execute_action(self, action: str, element) -> None:
        """Execute a pre/post action."""
        try:
            if action == 'click':
                await element.click()
            elif action == 'focus':
                await element.focus()
            elif action == 'blur':
                await element.blur()
            elif action.startswith('wait:'):
                delay = float(action.split(':')[1])
                await asyncio.sleep(delay)
        except Exception as e:
            self.logger.debug(f"Action {action} failed: {str(e)}")
    
    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get nested value from dictionary using dot notation."""
        try:
            keys = path.split('.')
            value = data
            for key in keys:
                if isinstance(value, dict):
                    value = value.get(key)
                elif isinstance(value, list) and key.isdigit():
                    index = int(key)
                    value = value[index] if 0 <= index < len(value) else None
                else:
                    return None
                
                if value is None:
                    return None
            
            return value
        except (KeyError, IndexError, ValueError):
            return None
    
    def _generate_fill_summary(self, results: List[Dict[str, Any]], 
                             mappings: List[FieldMapping]) -> Dict[str, Any]:
        """Generate summary of form filling results."""
        successful_fills = [r for r in results if r.get('success')]
        failed_fills = [r for r in results if not r.get('success')]
        
        strategy_breakdown = {}
        for mapping in mappings:
            strategy = mapping.strategy.value
            strategy_breakdown[strategy] = strategy_breakdown.get(strategy, 0) + 1
        
        return {
            "success": len(successful_fills) > 0,
            "action": "fill_application_intelligently",
            "summary": {
                "total_fields_processed": len(results),
                "successful_fills": len(successful_fills),
                "failed_fills": len(failed_fills),
                "success_rate": len(successful_fills) / len(results) if results else 0,
                "strategy_breakdown": strategy_breakdown,
                "overall_statistics": self._fill_statistics
            },
            "successful_fields": successful_fills,
            "failed_fields": failed_fills,
            "recommendations": self._generate_recommendations(failed_fills)
        }
    
    def _generate_recommendations(self, failed_fills: List[Dict[str, Any]]) -> List[str]:
        """Generate recommendations based on failed fills."""
        recommendations = []
        
        if failed_fills:
            recommendations.append("Consider manual review of failed fields")
            
            if len(failed_fills) > len(failed_fills) * 0.5:  # More than 50% failed
                recommendations.append("Page may have dynamic content - consider waiting longer before filling")
            
            # Check for common failure patterns
            selector_failures = [f for f in failed_fills if 'selector' in f.get('error', '')]
            if selector_failures:
                recommendations.append("Some fields may have changed selectors - consider updating field detection")
        
        return recommendations 