"""
Advanced Field Detection System

Implements Claude-like intelligence for finding and interacting with form fields.
Uses multiple strategies with aggressive timeout prevention.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from playwright.async_api import Page, ElementHandle, TimeoutError


class AdvancedFieldDetector:
    """
    Claude-like field detection with multiple strategies and timeout prevention.
    
    Follows the principle: "How would Claude find this field if the obvious way didn't work?"
    """
    
    def __init__(self, page: Page, config):
        self.page = page
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Performance tracking
        self.detection_stats = {
            'total_attempts': 0,
            'successful_detections': 0,
            'strategy_usage': {},
            'average_time': 0
        }
        
        # Claude-like timeout settings (aggressive prevention)
        self.MAX_WAIT_PER_FIELD = 5000  # 5 seconds max per field
        self.MAX_ATTEMPTS_PER_STRATEGY = 3
        self.STRATEGY_TIMEOUT = 2000  # 2 seconds per strategy
        
    async def find_and_fill_field_intelligently(self, field_info: Dict[str, Any], value: str) -> Dict[str, Any]:
        """
        Find and fill a field using Claude-like intelligence.
        
        Never gets stuck - always has fallback strategies.
        """
        start_time = datetime.now()
        field_purpose = field_info.get('field_purpose', 'unknown')
        
        self.logger.info(f"🎯 Finding field: {field_purpose} (Claude-like approach)")
        
        try:
            # Strategy progression like Claude's thinking
            strategies = self._get_detection_strategies(field_info, value)
            
            for i, strategy in enumerate(strategies):
                strategy_start = datetime.now()
                
                self.logger.debug(f"  Strategy {i+1}/{len(strategies)}: {strategy['name']}")
                
                try:
                    # Execute strategy with aggressive timeout
                    result = await asyncio.wait_for(
                        strategy['function'](field_info, value),
                        timeout=self.STRATEGY_TIMEOUT / 1000
                    )
                    
                    if result['success']:
                        duration = (datetime.now() - start_time).total_seconds()
                        self._update_stats(strategy['name'], True, duration)
                        
                        self.logger.info(f"✅ Field filled successfully using {strategy['name']} in {duration:.2f}s")
                        return result
                        
                except asyncio.TimeoutError:
                    self.logger.warning(f"⏰ Strategy {strategy['name']} timed out after {self.STRATEGY_TIMEOUT/1000}s")
                    continue
                except Exception as e:
                    self.logger.debug(f"  Strategy {strategy['name']} failed: {str(e)}")
                    continue
                
                # Check total time (Claude never gets stuck)
                total_time = (datetime.now() - start_time).total_seconds()
                if total_time > self.MAX_WAIT_PER_FIELD / 1000:
                    self.logger.warning(f"🚨 Aborting field {field_purpose} - total time exceeded {self.MAX_WAIT_PER_FIELD/1000}s")
                    break
            
            # If all strategies failed, return graceful failure
            duration = (datetime.now() - start_time).total_seconds()
            self._update_stats('all_failed', False, duration)
            
            return {
                'success': False,
                'error': f'All {len(strategies)} strategies failed within timeout limits',
                'field_purpose': field_purpose,
                'strategies_attempted': len(strategies),
                'total_time': duration
            }
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self.logger.error(f"❌ Critical error in field detection: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'field_purpose': field_purpose,
                'total_time': duration
            }
    
    def _get_detection_strategies(self, field_info: Dict[str, Any], value: str) -> List[Dict[str, Any]]:
        """Get ordered list of detection strategies like Claude's approach."""
        
        return [
            {
                'name': 'semantic_understanding',
                'function': self._strategy_semantic_understanding,
                'description': 'Understand field meaning like Claude'
            },
            {
                'name': 'context_clues',
                'function': self._strategy_context_clues,
                'description': 'Use surrounding context'
            },
            {
                'name': 'visual_patterns',
                'function': self._strategy_visual_patterns,
                'description': 'Analyze visual layout'
            },
            {
                'name': 'attribute_matching',
                'function': self._strategy_attribute_matching,
                'description': 'Traditional attribute matching'
            },
            {
                'name': 'fuzzy_search',
                'function': self._strategy_fuzzy_search,
                'description': 'AI-powered fuzzy matching'
            },
            {
                'name': 'human_like_scanning',
                'function': self._strategy_human_scanning,
                'description': 'Scan like a human would'
            }
        ]
    
    async def _strategy_semantic_understanding(self, field_info: Dict[str, Any], value: str) -> Dict[str, Any]:
        """Strategy 1: Semantic understanding like Claude."""
        
        field_purpose = field_info.get('field_purpose', '')
        
        # Claude-like semantic mapping
        semantic_selectors = {
            'first_name': [
                'input[placeholder*="first" i]',
                'input[placeholder*="given" i]',
                'input[aria-label*="first" i]',
                '[data-testid*="first" i]'
            ],
            'last_name': [
                'input[placeholder*="last" i]',
                'input[placeholder*="family" i]',
                'input[placeholder*="surname" i]',
                'input[aria-label*="last" i]'
            ],
            'full_name': [
                'input[placeholder*="full name" i]',
                'input[placeholder*="name" i]:not([placeholder*="first" i]):not([placeholder*="last" i])',
                'input[aria-label*="full name" i]',
                'input[name="name"]:not([name*="first"]):not([name*="last"])'
            ],
            'email': [
                'input[type="email"]',
                'input[placeholder*="email" i]',
                'input[name*="email" i]',
                'input[aria-label*="email" i]'
            ],
            'phone': [
                'input[type="tel"]',
                'input[placeholder*="phone" i]',
                'input[placeholder*="mobile" i]',
                'input[name*="phone" i]'
            ]
        }
        
        selectors = semantic_selectors.get(field_purpose, [])
        
        for selector in selectors:
            try:
                element = await self.page.wait_for_selector(selector, timeout=1000)
                if element and await element.is_visible():
                    await element.fill(value)
                    return {
                        'success': True,
                        'strategy': 'semantic_understanding',
                        'selector': selector,
                        'field_purpose': field_purpose
                    }
            except:
                continue
        
        return {'success': False, 'strategy': 'semantic_understanding'}
    
    async def _strategy_context_clues(self, field_info: Dict[str, Any], value: str) -> Dict[str, Any]:
        """Strategy 2: Use context clues like Claude notices."""
        
        field_purpose = field_info.get('field_purpose', '')
        
        # Look for labels and associated inputs
        context_keywords = {
            'first_name': ['first', 'given', 'forename'],
            'last_name': ['last', 'family', 'surname'],
            'full_name': ['full name', 'name', 'your name'],
            'email': ['email', 'e-mail', 'electronic'],
            'phone': ['phone', 'telephone', 'mobile', 'cell']
        }
        
        keywords = context_keywords.get(field_purpose, [field_purpose])
        
        for keyword in keywords:
            try:
                # Find label containing keyword
                label = await self.page.wait_for_selector(f'label:has-text("{keyword}")', timeout=800)
                if label:
                    # Find associated input
                    for_attr = await label.get_attribute('for')
                    if for_attr:
                        element = await self.page.query_selector(f'#{for_attr}')
                        if element and await element.is_visible():
                            await element.fill(value)
                            return {
                                'success': True,
                                'strategy': 'context_clues',
                                'keyword': keyword,
                                'field_purpose': field_purpose
                            }
            except:
                continue
        
        return {'success': False, 'strategy': 'context_clues'}
    
    async def _strategy_visual_patterns(self, field_info: Dict[str, Any], value: str) -> Dict[str, Any]:
        """Strategy 3: Visual pattern recognition like Claude."""
        
        # Get all visible input fields
        try:
            inputs = await self.page.query_selector_all('input[type="text"], input[type="email"], input[type="tel"], input:not([type])')
            
            field_purpose = field_info.get('field_purpose', '')
            
            for i, input_elem in enumerate(inputs):
                if not await input_elem.is_visible():
                    continue
                
                # Use position and context for inference
                placeholder = await input_elem.get_attribute('placeholder') or ''
                name = await input_elem.get_attribute('name') or ''
                
                # Smart matching based on field purpose and position
                if field_purpose == 'first_name' and i == 0:  # Usually first field
                    await input_elem.fill(value)
                    return {'success': True, 'strategy': 'visual_patterns', 'position': 'first'}
                elif field_purpose == 'last_name' and i == 1:  # Usually second field
                    await input_elem.fill(value)
                    return {'success': True, 'strategy': 'visual_patterns', 'position': 'second'}
                elif field_purpose == 'email' and ('email' in placeholder.lower() or 'email' in name.lower()):
                    await input_elem.fill(value)
                    return {'success': True, 'strategy': 'visual_patterns', 'email_match': True}
                
        except Exception as e:
            self.logger.debug(f"Visual pattern strategy failed: {str(e)}")
        
        return {'success': False, 'strategy': 'visual_patterns'}
    
    async def _strategy_attribute_matching(self, field_info: Dict[str, Any], value: str) -> Dict[str, Any]:
        """Strategy 4: Traditional attribute matching."""
        
        # Try original selectors from field_info
        selectors = field_info.get('context_clues', [])
        element_selector = field_info.get('element_selector', '')
        
        all_selectors = [element_selector] + selectors if element_selector else selectors
        
        for selector in all_selectors:
            if not selector:
                continue
                
            try:
                element = await self.page.wait_for_selector(selector, timeout=800)
                if element and await element.is_visible():
                    await element.fill(value)
                    return {
                        'success': True,
                        'strategy': 'attribute_matching',
                        'selector': selector
                    }
            except:
                continue
        
        return {'success': False, 'strategy': 'attribute_matching'}
    
    async def _strategy_fuzzy_search(self, field_info: Dict[str, Any], value: str) -> Dict[str, Any]:
        """Strategy 5: AI-powered fuzzy matching."""
        
        field_purpose = field_info.get('field_purpose', '')
        
        try:
            # Get all input elements
            inputs = await self.page.query_selector_all('input, textarea')
            
            best_match = None
            best_score = 0
            
            for input_elem in inputs:
                if not await input_elem.is_visible():
                    continue
                
                # Calculate fuzzy match score
                score = await self._calculate_field_match_score(input_elem, field_purpose)
                
                if score > best_score and score > 0.6:  # Minimum confidence threshold
                    best_score = score
                    best_match = input_elem
            
            if best_match:
                await best_match.fill(value)
                return {
                    'success': True,
                    'strategy': 'fuzzy_search',
                    'confidence': best_score,
                    'field_purpose': field_purpose
                }
                
        except Exception as e:
            self.logger.debug(f"Fuzzy search strategy failed: {str(e)}")
        
        return {'success': False, 'strategy': 'fuzzy_search'}
    
    async def _strategy_human_scanning(self, field_info: Dict[str, Any], value: str) -> Dict[str, Any]:
        """Strategy 6: Human-like scanning patterns."""
        
        field_purpose = field_info.get('field_purpose', '')
        
        try:
            # Scan inputs in reading order (top to bottom, left to right)
            inputs = await self.page.query_selector_all('input[type="text"], input[type="email"], input[type="tel"], input:not([type])')
            
            # Filter for visible inputs
            visible_inputs = []
            for input_elem in inputs:
                if await input_elem.is_visible():
                    visible_inputs.append(input_elem)
            
            # Human-like heuristics
            if field_purpose == 'first_name' and len(visible_inputs) >= 1:
                await visible_inputs[0].fill(value)
                return {'success': True, 'strategy': 'human_scanning', 'heuristic': 'first_input'}
            elif field_purpose == 'last_name' and len(visible_inputs) >= 2:
                await visible_inputs[1].fill(value)
                return {'success': True, 'strategy': 'human_scanning', 'heuristic': 'second_input'}
            elif field_purpose == 'email':
                # Look for email-like field
                for input_elem in visible_inputs:
                    input_type = await input_elem.get_attribute('type')
                    if input_type == 'email':
                        await input_elem.fill(value)
                        return {'success': True, 'strategy': 'human_scanning', 'heuristic': 'email_type'}
            
        except Exception as e:
            self.logger.debug(f"Human scanning strategy failed: {str(e)}")
        
        return {'success': False, 'strategy': 'human_scanning'}
    
    async def _calculate_field_match_score(self, element: ElementHandle, field_purpose: str) -> float:
        """Calculate how well an element matches the field purpose."""
        
        score = 0.0
        
        try:
            # Get element attributes
            name = await element.get_attribute('name') or ''
            id_attr = await element.get_attribute('id') or ''
            placeholder = await element.get_attribute('placeholder') or ''
            input_type = await element.get_attribute('type') or 'text'
            
            combined_text = f"{name} {id_attr} {placeholder}".lower()
            
            # Scoring based on field purpose
            if field_purpose == 'first_name':
                if any(word in combined_text for word in ['first', 'given', 'fname']):
                    score += 0.8
                elif 'name' in combined_text and 'last' not in combined_text:
                    score += 0.4
            elif field_purpose == 'last_name':
                if any(word in combined_text for word in ['last', 'family', 'surname', 'lname']):
                    score += 0.8
            elif field_purpose == 'email':
                if input_type == 'email' or 'email' in combined_text:
                    score += 0.9
            elif field_purpose == 'phone':
                if input_type == 'tel' or any(word in combined_text for word in ['phone', 'tel', 'mobile']):
                    score += 0.9
            
            return score
            
        except Exception:
            return 0.0
    
    def _update_stats(self, strategy: str, success: bool, duration: float):
        """Update detection statistics."""
        
        self.detection_stats['total_attempts'] += 1
        if success:
            self.detection_stats['successful_detections'] += 1
        
        if strategy not in self.detection_stats['strategy_usage']:
            self.detection_stats['strategy_usage'][strategy] = {'count': 0, 'success': 0}
        
        self.detection_stats['strategy_usage'][strategy]['count'] += 1
        if success:
            self.detection_stats['strategy_usage'][strategy]['success'] += 1
        
        # Update average time
        total_time = self.detection_stats.get('total_time', 0) + duration
        self.detection_stats['total_time'] = total_time
        self.detection_stats['average_time'] = total_time / self.detection_stats['total_attempts']
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        
        success_rate = 0
        if self.detection_stats['total_attempts'] > 0:
            success_rate = self.detection_stats['successful_detections'] / self.detection_stats['total_attempts']
        
        return {
            'success_rate': success_rate,
            'average_time': self.detection_stats['average_time'],
            'total_attempts': self.detection_stats['total_attempts'],
            'strategy_performance': self.detection_stats['strategy_usage']
        } 