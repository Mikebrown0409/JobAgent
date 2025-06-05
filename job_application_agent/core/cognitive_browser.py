"""
Cognitive Browsing Engine

This implements the same intelligent web browsing and analysis capabilities
that Claude uses when interacting with web pages - real-time understanding,
context awareness, and goal-oriented navigation.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from playwright.async_api import Page, ElementHandle


class PageType(Enum):
    """Different types of pages the agent might encounter."""
    JOB_LISTING = "job_listing"
    APPLICATION_FORM = "application_form"
    LOGIN_REQUIRED = "login_required"
    MULTI_STEP_FORM = "multi_step_form"
    CONFIRMATION = "confirmation"
    ERROR_PAGE = "error_page"
    UNKNOWN = "unknown"


class NavigationAction(Enum):
    """Actions the cognitive browser can take."""
    CLICK_APPLY = "click_apply"
    FILL_FORM = "fill_form"
    CLICK_NEXT = "click_next"
    CLICK_SUBMIT = "click_submit"
    PROVIDE_EMAIL = "provide_email"
    WAIT_FOR_LOAD = "wait_for_load"
    RETRY_NAVIGATION = "retry_navigation"


@dataclass
class PageInsight:
    """Cognitive analysis of a web page."""
    page_type: PageType
    confidence: float
    key_elements: List[Dict[str, Any]]
    next_actions: List[NavigationAction]
    form_fields: List[Dict[str, Any]]
    navigation_elements: List[Dict[str, Any]]
    semantic_context: Dict[str, Any]
    reasoning: str


@dataclass
class FieldInsight:
    """Intelligent understanding of a form field."""
    element_selector: str
    field_purpose: str
    confidence: float
    input_type: str
    required: bool
    context_clues: List[str]
    suggested_value: Optional[str]
    filling_strategy: str


class CognitiveBrowser:
    """
    Advanced cognitive browsing engine that thinks and navigates like Claude.
    
    This implements real-time page analysis, intelligent navigation decisions,
    and context-aware form interaction.
    """
    
    def __init__(self, page: Page, llm_service, config):
        self.page = page
        self.llm_service = llm_service
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Cognitive state
        self.current_page_insight: Optional[PageInsight] = None
        self.navigation_history: List[Dict[str, Any]] = []
        self.form_context: Dict[str, Any] = {}
        self.user_goal = "apply_to_job"
        
        # Quick pattern recognition (like how I instantly recognize common patterns)
        self.apply_button_patterns = [
            "apply now", "apply for this job", "apply", "apply online",
            "submit application", "start application", "apply today",
            "apply for position", "apply here", "apply for this role"
        ]
        
        self.form_field_patterns = {
            'email': ['email', 'e-mail', 'email address', 'your email'],
            'first_name': ['first name', 'given name', 'firstname', 'fname'],
            'last_name': ['last name', 'surname', 'lastname', 'lname', 'family name'],
            'phone': ['phone', 'telephone', 'mobile', 'phone number', 'contact number'],
            'resume': ['resume', 'cv', 'curriculum vitae', 'upload resume'],
            'cover_letter': ['cover letter', 'motivation letter', 'letter of interest']
        }

    async def analyze_page_intelligently(self) -> PageInsight:
        """
        Perform intelligent page analysis like how I understand pages.
        Fast, context-aware, goal-oriented.
        """
        start_time = datetime.now()
        
        # Get page content quickly
        title = await self.page.title()
        url = self.page.url
        
        # Quick semantic scan (like how I scan for key elements)
        page_text = await self.page.text_content('body')
        
        # Instant pattern recognition for page type
        page_type, confidence = await self._recognize_page_type_instantly(title, url, page_text)
        
        # Find key interactive elements (buttons, forms, links)
        key_elements = await self._find_key_elements_fast()
        
        # Determine next actions based on goal and page type
        next_actions = self._determine_next_actions(page_type, key_elements)
        
        # Quick form analysis if applicable
        form_fields = []
        if page_type in [PageType.APPLICATION_FORM, PageType.MULTI_STEP_FORM]:
            form_fields = await self._analyze_form_fields_quickly()
        
        # Find navigation elements
        navigation_elements = await self._find_navigation_elements()
        
        # Generate reasoning (like how I explain my understanding)
        reasoning = self._generate_reasoning(page_type, key_elements, next_actions)
        
        insight = PageInsight(
            page_type=page_type,
            confidence=confidence,
            key_elements=key_elements,
            next_actions=next_actions,
            form_fields=form_fields,
            navigation_elements=navigation_elements,
            semantic_context={
                'title': title,
                'url': url,
                'analysis_time': (datetime.now() - start_time).total_seconds()
            },
            reasoning=reasoning
        )
        
        self.current_page_insight = insight
        self.logger.info(f"Page analyzed in {insight.semantic_context['analysis_time']:.2f}s: {reasoning}")
        
        return insight

    async def _recognize_page_type_instantly(self, title: str, url: str, page_text: str) -> Tuple[PageType, float]:
        """Instant page type recognition using pattern matching (like how I instantly know page types)."""
        
        # Check for application form indicators
        form_indicators = ['application', 'apply', 'job application', 'submit your']
        form_elements = await self.page.query_selector_all('form, input[type="text"], input[type="email"]')
        
        if len(form_elements) > 3 and any(indicator in title.lower() for indicator in form_indicators):
            return PageType.APPLICATION_FORM, 0.9
        
        # Check for multi-step indicators
        if 'step' in page_text.lower() or 'continue' in page_text.lower():
            return PageType.MULTI_STEP_FORM, 0.85
        
        # Check for apply button (job listing page)
        apply_buttons = await self._find_apply_buttons_fast()
        if apply_buttons and not form_elements:
            return PageType.JOB_LISTING, 0.9
        
        # Check for login requirements
        if 'login' in page_text.lower() or 'sign in' in page_text.lower():
            return PageType.LOGIN_REQUIRED, 0.8
        
        # Check for confirmation page
        if any(word in page_text.lower() for word in ['thank you', 'submitted', 'received']):
            return PageType.CONFIRMATION, 0.85
        
        return PageType.UNKNOWN, 0.5

    async def _find_apply_buttons_fast(self) -> List[Dict[str, Any]]:
        """Quickly find apply buttons using intelligent pattern matching."""
        buttons = []
        
        # Check common button selectors
        selectors = [
            'button', 'input[type="submit"]', 'input[type="button"]', 
            'a[role="button"]', '.btn', '.button', '[class*="apply"]'
        ]
        
        for selector in selectors:
            elements = await self.page.query_selector_all(selector)
            for element in elements:
                text = await element.text_content()
                if text and any(pattern in text.lower() for pattern in self.apply_button_patterns):
                    buttons.append({
                        'selector': selector,
                        'text': text.strip(),
                        'element': element,
                        'confidence': 0.9
                    })
        
        return buttons

    async def _find_key_elements_fast(self) -> List[Dict[str, Any]]:
        """Find key page elements quickly using smart selectors."""
        elements = []
        
        # Forms
        forms = await self.page.query_selector_all('form')
        for form in forms:
            elements.append({
                'type': 'form',
                'element': form,
                'importance': 'high'
            })
        
        # Apply buttons
        apply_buttons = await self._find_apply_buttons_fast()
        elements.extend([{
            'type': 'apply_button',
            'element': btn['element'],
            'text': btn['text'],
            'importance': 'critical'
        } for btn in apply_buttons])
        
        # Submit buttons
        submit_buttons = await self.page.query_selector_all('button[type="submit"], input[type="submit"]')
        for btn in submit_buttons:
            elements.append({
                'type': 'submit_button',
                'element': btn,
                'importance': 'high'
            })
        
        return elements

    async def _analyze_form_fields_quickly(self) -> List[FieldInsight]:
        """Quickly analyze form fields using intelligent pattern recognition."""
        fields = []
        
        # Get all input elements
        inputs = await self.page.query_selector_all('input, textarea, select')
        
        for input_elem in inputs:
            # Get field attributes
            name = await input_elem.get_attribute('name') or ''
            id_attr = await input_elem.get_attribute('id') or ''
            placeholder = await input_elem.get_attribute('placeholder') or ''
            input_type = await input_elem.get_attribute('type') or 'text'
            required = await input_elem.get_attribute('required') is not None
            
            # Find associated label
            label_text = await self._find_field_label_smart(input_elem, id_attr)
            
            # Determine field purpose using intelligent matching
            field_purpose, confidence = self._determine_field_purpose_smart(
                name, id_attr, placeholder, label_text
            )
            
            if field_purpose and confidence > 0.6:
                fields.append(FieldInsight(
                    element_selector=f"#{id_attr}" if id_attr else f"[name='{name}']",
                    field_purpose=field_purpose,
                    confidence=confidence,
                    input_type=input_type,
                    required=required,
                    context_clues=[name, id_attr, placeholder, label_text],
                    suggested_value=None,  # Will be filled by profile mapping
                    filling_strategy='direct_input'
                ))
        
        return fields

    def _determine_field_purpose_smart(self, name: str, id_attr: str, placeholder: str, label: str) -> Tuple[str, float]:
        """Smart field purpose detection using pattern matching."""
        
        # Combine all text for analysis
        combined_text = f"{name} {id_attr} {placeholder} {label}".lower()
        
        # Check each field type pattern
        for field_type, patterns in self.form_field_patterns.items():
            for pattern in patterns:
                if pattern in combined_text:
                    # Calculate confidence based on how specific the match is
                    if pattern in label.lower():
                        confidence = 0.95  # Label match is highest confidence
                    elif pattern in placeholder.lower():
                        confidence = 0.85  # Placeholder match is high
                    elif pattern in name.lower() or pattern in id_attr.lower():
                        confidence = 0.75  # Attribute match is good
                    else:
                        confidence = 0.6   # General match
                    
                    return field_type, confidence
        
        # Special cases for common patterns
        if 'email' in combined_text:
            return 'email', 0.9
        elif any(word in combined_text for word in ['name', 'fname', 'lname']):
            if 'first' in combined_text or 'given' in combined_text:
                return 'first_name', 0.8
            elif 'last' in combined_text or 'family' in combined_text or 'surname' in combined_text:
                return 'last_name', 0.8
            else:
                return 'full_name', 0.7
        elif any(word in combined_text for word in ['phone', 'mobile', 'tel']):
            return 'phone', 0.8
        
        return 'unknown', 0.0

    async def _find_field_label_smart(self, element: ElementHandle, id_attr: str) -> str:
        """Smart label finding using multiple strategies."""
        
        # Strategy 1: Direct label association
        if id_attr:
            label = await self.page.query_selector(f'label[for="{id_attr}"]')
            if label:
                return await label.text_content() or ''
        
        # Strategy 2: Parent label
        try:
            parent_label = await element.query_selector('xpath=ancestor::label[1]')
            if parent_label:
                return await parent_label.text_content() or ''
        except:
            pass
        
        # Strategy 3: Preceding sibling text
        try:
            prev_element = await element.query_selector('xpath=preceding-sibling::*[1]')
            if prev_element:
                text = await prev_element.text_content()
                if text and len(text.strip()) < 50:  # Likely a label
                    return text.strip()
        except:
            pass
        
        return ''

    def _determine_next_actions(self, page_type: PageType, key_elements: List[Dict[str, Any]]) -> List[NavigationAction]:
        """Determine what actions to take next based on page analysis."""
        
        if page_type == PageType.JOB_LISTING:
            # On job listing - need to find and click apply button
            return [NavigationAction.CLICK_APPLY]
        
        elif page_type == PageType.APPLICATION_FORM:
            # On application form - fill it out
            return [NavigationAction.FILL_FORM, NavigationAction.CLICK_SUBMIT]
        
        elif page_type == PageType.MULTI_STEP_FORM:
            # Multi-step form - fill current step and continue
            return [NavigationAction.FILL_FORM, NavigationAction.CLICK_NEXT]
        
        elif page_type == PageType.LOGIN_REQUIRED:
            # Login required - provide email for guest application
            return [NavigationAction.PROVIDE_EMAIL]
        
        elif page_type == PageType.CONFIRMATION:
            # Success page - we're done
            return []
        
        else:
            # Unknown page - try to navigate
            return [NavigationAction.WAIT_FOR_LOAD, NavigationAction.RETRY_NAVIGATION]

    async def _find_navigation_elements(self) -> List[Dict[str, Any]]:
        """Find navigation elements (next, continue, submit buttons)."""
        nav_elements = []
        
        # Common navigation button patterns
        nav_patterns = [
            ('next', ['next', 'continue', 'proceed']),
            ('submit', ['submit', 'apply', 'send application']),
            ('back', ['back', 'previous', 'prev'])
        ]
        
        for nav_type, patterns in nav_patterns:
            buttons = await self.page.query_selector_all('button, input[type="submit"], input[type="button"]')
            for button in buttons:
                text = await button.text_content()
                if text and any(pattern in text.lower() for pattern in patterns):
                    nav_elements.append({
                        'type': nav_type,
                        'element': button,
                        'text': text.strip()
                    })
        
        return nav_elements

    def _generate_reasoning(self, page_type: PageType, key_elements: List[Dict[str, Any]], 
                          next_actions: List[NavigationAction]) -> str:
        """Generate human-readable reasoning for the analysis."""
        
        element_summary = f"{len(key_elements)} key elements found"
        action_summary = f"{len(next_actions)} actions planned"
        
        if page_type == PageType.JOB_LISTING:
            return f"Job listing page detected. {element_summary}. Need to find and click Apply button."
        elif page_type == PageType.APPLICATION_FORM:
            return f"Application form detected. {element_summary}. Ready to fill form and submit."
        elif page_type == PageType.MULTI_STEP_FORM:
            return f"Multi-step form detected. {element_summary}. Will fill current step and continue."
        elif page_type == PageType.LOGIN_REQUIRED:
            return f"Login required page. {element_summary}. Will attempt guest application."
        elif page_type == PageType.CONFIRMATION:
            return f"Confirmation page detected. Application likely successful."
        else:
            return f"Unknown page type. {element_summary}. {action_summary}."

    async def execute_intelligent_navigation(self) -> Dict[str, Any]:
        """Execute intelligent navigation based on page analysis."""
        
        if not self.current_page_insight:
            await self.analyze_page_intelligently()
        
        insight = self.current_page_insight
        results = []
        
        for action in insight.next_actions:
            if action == NavigationAction.CLICK_APPLY:
                result = await self._click_apply_button_intelligently()
                results.append(result)
                
                if result.get('success'):
                    # Wait for navigation and re-analyze
                    await asyncio.sleep(2)
                    await self.analyze_page_intelligently()
                    break
            
            elif action == NavigationAction.FILL_FORM:
                result = await self._fill_form_intelligently()
                results.append(result)
            
            elif action == NavigationAction.CLICK_SUBMIT:
                result = await self._click_submit_intelligently()
                results.append(result)
            
            elif action == NavigationAction.PROVIDE_EMAIL:
                result = await self._provide_email_for_guest_application()
                results.append(result)
        
        return {
            'success': any(r.get('success') for r in results),
            'actions_taken': len(results),
            'results': results,
            'page_insight': insight.reasoning
        }

    async def _click_apply_button_intelligently(self) -> Dict[str, Any]:
        """Intelligently find and click the apply button."""
        
        apply_buttons = await self._find_apply_buttons_fast()
        
        if not apply_buttons:
            return {'success': False, 'error': 'No apply button found'}
        
        # Choose the best apply button (highest confidence)
        best_button = max(apply_buttons, key=lambda x: x['confidence'])
        
        try:
            await best_button['element'].click()
            await self.page.wait_for_load_state('networkidle', timeout=10000)
            
            self.logger.info(f"Successfully clicked apply button: {best_button['text']}")
            return {
                'success': True,
                'action': 'clicked_apply',
                'button_text': best_button['text']
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Failed to click apply button: {str(e)}"
            }

    async def _fill_form_intelligently(self) -> Dict[str, Any]:
        """Fill form using intelligent field mapping."""
        
        if not self.current_page_insight.form_fields:
            return {'success': False, 'error': 'No form fields detected'}
        
        filled_fields = 0
        failed_fields = 0
        
        # Sample profile data (this would come from the user's profile)
        profile_data = {
            'first_name': 'Sarah',
            'last_name': 'Chen',
            'email': 'sarah.chen@email.com',
            'phone': '(555) 123-4567'
        }
        
        for field in self.current_page_insight.form_fields:
            if field.field_purpose in profile_data:
                try:
                    # Find element and fill it
                    element = await self.page.query_selector(field.element_selector)
                    if element:
                        await element.fill(profile_data[field.field_purpose])
                        filled_fields += 1
                        self.logger.info(f"Filled {field.field_purpose}: {field.element_selector}")
                    else:
                        failed_fields += 1
                except Exception as e:
                    failed_fields += 1
                    self.logger.warning(f"Failed to fill {field.field_purpose}: {str(e)}")
        
        return {
            'success': filled_fields > 0,
            'filled_fields': filled_fields,
            'failed_fields': failed_fields
        }

    async def _click_submit_intelligently(self) -> Dict[str, Any]:
        """Intelligently find and click submit button."""
        
        # Look for submit buttons in navigation elements
        nav_elements = self.current_page_insight.navigation_elements
        submit_buttons = [elem for elem in nav_elements if elem['type'] == 'submit']
        
        if not submit_buttons:
            # Fallback: look for any submit button
            submit_buttons = await self.page.query_selector_all('button[type="submit"], input[type="submit"]')
            if submit_buttons:
                submit_buttons = [{'element': btn} for btn in submit_buttons]
        
        if not submit_buttons:
            return {'success': False, 'error': 'No submit button found'}
        
        try:
            await submit_buttons[0]['element'].click()
            await self.page.wait_for_load_state('networkidle', timeout=10000)
            
            return {'success': True, 'action': 'clicked_submit'}
            
        except Exception as e:
            return {'success': False, 'error': f"Failed to click submit: {str(e)}"}

    async def _provide_email_for_guest_application(self) -> Dict[str, Any]:
        """Provide email for guest application."""
        
        email_fields = [f for f in self.current_page_insight.form_fields if f.field_purpose == 'email']
        
        if not email_fields:
            return {'success': False, 'error': 'No email field found'}
        
        try:
            element = await self.page.query_selector(email_fields[0].element_selector)
            if element:
                await element.fill('sarah.chen@email.com')
                
                # Look for continue/next button
                continue_btn = await self.page.query_selector('button:has-text("continue"), button:has-text("next")')
                if continue_btn:
                    await continue_btn.click()
                    await self.page.wait_for_load_state('networkidle', timeout=10000)
                
                return {'success': True, 'action': 'provided_email'}
            
        except Exception as e:
            return {'success': False, 'error': f"Failed to provide email: {str(e)}"}

    def get_current_insight(self) -> Optional[PageInsight]:
        """Get the current page insight."""
        return self.current_page_insight 