"""
Enhanced Field Interaction - Robust Form Field Handling

Advanced field interaction system that can handle any type of form field
with multiple filling strategies, anti-detection capabilities, and smart retries.
"""

import asyncio
import logging
import re
from typing import Dict, Any, Optional, List, Tuple, Union
from playwright.async_api import Page, ElementHandle, Locator
from datetime import datetime
import json


class FieldInteractionError(Exception):
    """Custom exception for field interaction failures."""
    pass


class EnhancedFieldInteractor:
    """
    Enhanced field interaction system with multiple strategies for field filling.
    
    This class handles the complex scenarios that cause form filling failures,
    including dynamic fields, protected fields, and various input types.
    """
    
    def __init__(self, page: Page, config):
        """Initialize the enhanced field interactor."""
        self.page = page
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Interaction statistics
        self.stats = {
            'total_attempts': 0,
            'successful_fills': 0,
            'strategy_success': {},
            'retry_counts': {}
        }
    
    async def fill_field_robustly(self, field_info: Dict[str, Any], value: str, 
                                max_retries: int = 3) -> Dict[str, Any]:
        """
        Fill a field using multiple robust strategies.
        
        Args:
            field_info: Information about the field (selectors, type, etc.)
            value: Value to fill
            max_retries: Maximum number of retry attempts
            
        Returns:
            Result of the field filling operation
        """
        self.stats['total_attempts'] += 1
        
        # Get all possible selectors for this field
        selectors = self._get_all_selectors(field_info)
        field_type = field_info.get('type', 'text')
        field_purpose = field_info.get('field_purpose', 'text')
        
        self.logger.info(f"Attempting to fill field: {field_purpose} with value: {value}")
        
        # Define filling strategies in order of preference
        strategies = [
            self._strategy_direct_fill,
            self._strategy_focus_and_type,
            self._strategy_clear_and_fill,
            self._strategy_click_and_type,
            self._strategy_simulate_human_typing,
            self._strategy_javascript_injection,
            self._strategy_dispatch_events
        ]
        
        last_error = None
        
        for attempt in range(max_retries):
            for strategy_name, strategy_func in [(s.__name__, s) for s in strategies]:
                try:
                    result = await self._try_with_strategy(
                        strategy_func, selectors, value, field_info, attempt
                    )
                    
                    if result['success']:
                        self.stats['successful_fills'] += 1
                        self.stats['strategy_success'][strategy_name] = \
                            self.stats['strategy_success'].get(strategy_name, 0) + 1
                        
                        self.logger.info(f"Successfully filled field with strategy: {strategy_name}")
                        return result
                        
                except Exception as e:
                    last_error = e
                    self.logger.debug(f"Strategy {strategy_name} failed on attempt {attempt + 1}: {str(e)}")
                    continue
            
            # Wait between retry attempts
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
        
        # All strategies failed
        return {
            'success': False,
            'error': f"All strategies failed. Last error: {str(last_error)}",
            'field_info': field_info,
            'attempted_strategies': len(strategies),
            'total_retries': max_retries
        }
    
    async def _try_with_strategy(self, strategy_func, selectors: List[str], 
                               value: str, field_info: Dict[str, Any], 
                               attempt: int) -> Dict[str, Any]:
        """Try a filling strategy with error handling."""
        for selector in selectors:
            try:
                element = await self._find_element_safely(selector)
                if element:
                    success = await strategy_func(element, value, field_info)
                    if success:
                        # Verify the fill was successful
                        verification = await self._verify_field_filled(element, value, field_info)
                        return {
                            'success': True,
                            'strategy': strategy_func.__name__,
                            'selector': selector,
                            'attempt': attempt + 1,
                            'verification': verification
                        }
            except Exception as e:
                self.logger.debug(f"Selector {selector} failed with {strategy_func.__name__}: {str(e)}")
                continue
        
        raise FieldInteractionError(f"Strategy {strategy_func.__name__} failed for all selectors")
    
    async def _strategy_direct_fill(self, element: ElementHandle, value: str, 
                                  field_info: Dict[str, Any]) -> bool:
        """Direct fill strategy - simple fill."""
        await element.fill(value)
        return True
    
    async def _strategy_focus_and_type(self, element: ElementHandle, value: str, 
                                     field_info: Dict[str, Any]) -> bool:
        """Focus then type strategy."""
        await element.focus()
        await asyncio.sleep(0.1)
        await element.fill("")  # Clear first
        await element.type(value, delay=50)  # Slow typing to mimic human
        return True
    
    async def _strategy_clear_and_fill(self, element: ElementHandle, value: str, 
                                     field_info: Dict[str, Any]) -> bool:
        """Clear field completely then fill."""
        # Try multiple clear methods
        await element.click()
        await element.press('Control+a')  # Select all
        await element.press('Delete')     # Delete
        await asyncio.sleep(0.1)
        await element.fill(value)
        return True
    
    async def _strategy_click_and_type(self, element: ElementHandle, value: str, 
                                     field_info: Dict[str, Any]) -> bool:
        """Click, then clear, then type character by character."""
        await element.click()
        await asyncio.sleep(0.05)
        
        # Clear field using multiple methods
        await element.press('Control+a')
        await element.press('Backspace')
        await element.fill("")
        
        # Type character by character with delays
        for char in value:
            await element.type(char, delay=30)
            await asyncio.sleep(0.02)
        
        return True
    
    async def _strategy_simulate_human_typing(self, element: ElementHandle, value: str, 
                                            field_info: Dict[str, Any]) -> bool:
        """Simulate human-like typing with natural delays and corrections."""
        await element.click()
        await asyncio.sleep(0.1)
        
        # Clear field
        await element.press('Control+a')
        await element.press('Delete')
        
        # Type with human-like variations
        for i, char in enumerate(value):
            # Add random small delays to simulate human typing
            delay = 40 + (i % 3) * 10  # Vary typing speed
            await element.type(char, delay=delay)
            
            # Occasional pause (like humans do)
            if i > 0 and i % 5 == 0:
                await asyncio.sleep(0.05)
        
        return True
    
    async def _strategy_javascript_injection(self, element: ElementHandle, value: str, 
                                           field_info: Dict[str, Any]) -> bool:
        """Use JavaScript to directly set field value."""
        # Get element selector for JavaScript
        element_id = await element.get_attribute('id')
        element_name = await element.get_attribute('name')
        
        js_script = f"""
        (function() {{
            let element = null;
            
            // Try to find element by id, name, or other attributes
            if ('{element_id}') {{
                element = document.getElementById('{element_id}');
            }}
            if (!element && '{element_name}') {{
                element = document.querySelector('input[name="{element_name}"]');
            }}
            
            if (element) {{
                // Set value
                element.value = '{value}';
                
                // Trigger events that frameworks expect
                element.dispatchEvent(new Event('input', {{ bubbles: true }}));
                element.dispatchEvent(new Event('change', {{ bubbles: true }}));
                element.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                
                return true;
            }}
            return false;
        }})();
        """
        
        result = await self.page.evaluate(js_script)
        return result
    
    async def _strategy_dispatch_events(self, element: ElementHandle, value: str, 
                                      field_info: Dict[str, Any]) -> bool:
        """Fill using event dispatching for framework compatibility."""
        await element.focus()
        
        # Set value using JavaScript but with proper event handling
        await element.evaluate(f"""
            (element) => {{
                // Set value
                element.value = '{value}';
                
                // Create and dispatch events for React/Vue/Angular compatibility
                const events = ['focus', 'input', 'change', 'blur'];
                events.forEach(eventType => {{
                    const event = new Event(eventType, {{
                        bubbles: true,
                        cancelable: true
                    }});
                    element.dispatchEvent(event);
                }});
                
                // Special handling for React
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                nativeInputValueSetter.call(element, '{value}');
                
                const inputEvent = new Event('input', {{ bubbles: true }});
                element.dispatchEvent(inputEvent);
            }}
        """)
        
        return True
    
    async def _find_element_safely(self, selector: str) -> Optional[ElementHandle]:
        """Safely find an element with error handling."""
        try:
            # Wait for element to be visible and stable
            element = self.page.locator(selector).first
            await element.wait_for(state='visible', timeout=2000)
            await element.wait_for(state='stable', timeout=1000)
            
            return await element.element_handle()
        except Exception as e:
            self.logger.debug(f"Could not find element with selector {selector}: {str(e)}")
            return None
    
    async def _verify_field_filled(self, element: ElementHandle, expected_value: str, 
                                 field_info: Dict[str, Any]) -> Dict[str, Any]:
        """Verify that the field was filled correctly."""
        try:
            actual_value = await element.input_value()
            
            # For name fields, allow partial matches (first name only, etc.)
            field_purpose = field_info.get('field_purpose', '')
            if 'name' in field_purpose.lower():
                # Check if actual value is a substring of expected or vice versa
                if (actual_value.lower().strip() in expected_value.lower().strip() or 
                    expected_value.lower().strip() in actual_value.lower().strip()):
                    return {'verified': True, 'actual_value': actual_value, 'match_type': 'partial'}
            
            # Exact match verification
            if actual_value.strip() == expected_value.strip():
                return {'verified': True, 'actual_value': actual_value, 'match_type': 'exact'}
            
            return {
                'verified': False, 
                'actual_value': actual_value, 
                'expected_value': expected_value,
                'match_type': 'none'
            }
            
        except Exception as e:
            return {'verified': False, 'error': str(e)}
    
    def _get_all_selectors(self, field_info: Dict[str, Any]) -> List[str]:
        """Get all possible selectors for a field in order of preference."""
        selectors = []
        
        # Primary selectors from field analysis
        if 'selectors' in field_info:
            selectors.extend(field_info['selectors'])
        
        # Fallback selectors based on field attributes
        field_id = field_info.get('id')
        field_name = field_info.get('name')
        field_type = field_info.get('type', 'text')
        field_purpose = field_info.get('field_purpose', '')
        
        if field_id:
            selectors.extend([
                f"#{field_id}",
                f"input#{field_id}",
                f"[id='{field_id}']"
            ])
        
        if field_name:
            selectors.extend([
                f"[name='{field_name}']",
                f"input[name='{field_name}']"
            ])
        
        # Purpose-based selectors
        if field_purpose:
            purpose_selectors = self._generate_purpose_selectors(field_purpose)
            selectors.extend(purpose_selectors)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_selectors = []
        for selector in selectors:
            if selector not in seen:
                seen.add(selector)
                unique_selectors.append(selector)
        
        return unique_selectors
    
    def _generate_purpose_selectors(self, purpose: str) -> List[str]:
        """Generate selectors based on field purpose."""
        selectors = []
        purpose_lower = purpose.lower()
        
        # Common field patterns
        patterns = {
            'first_name': ['input[name*="first"]', 'input[id*="first"]', 'input[placeholder*="first"]'],
            'last_name': ['input[name*="last"]', 'input[id*="last"]', 'input[placeholder*="last"]'],
            'email': ['input[type="email"]', 'input[name*="email"]', 'input[id*="email"]'],
            'phone': ['input[type="tel"]', 'input[name*="phone"]', 'input[id*="phone"]'],
            'address': ['input[name*="address"]', 'input[id*="address"]', 'textarea[name*="address"]'],
        }
        
        for pattern_key, pattern_selectors in patterns.items():
            if pattern_key in purpose_lower:
                selectors.extend(pattern_selectors)
        
        return selectors
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get interaction statistics."""
        total = self.stats['total_attempts']
        successful = self.stats['successful_fills']
        
        return {
            'total_attempts': total,
            'successful_fills': successful,
            'success_rate': successful / total if total > 0 else 0,
            'strategy_success': self.stats['strategy_success'],
            'retry_counts': self.stats['retry_counts']
        } 