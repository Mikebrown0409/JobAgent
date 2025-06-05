"""
Enterprise Browser Tool - AI-Powered Web Automation

Advanced browser automation with AI-powered form analysis, intelligent field mapping,
and robust handling of any job application format. Built for enterprise-scale usage.
"""

import asyncio
import logging
import re
from typing import Dict, Any, Optional, List, Tuple, Union
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, ElementHandle
from difflib import SequenceMatcher
from datetime import datetime, timedelta
import json

from job_application_agent.core.config import Config
from job_application_agent.tools.enhanced_field_interaction import EnhancedFieldInteractor


class AdvancedBrowserTool:
    """
    Enterprise-grade browser automation tool with AI-powered capabilities.
    
    Features:
    - AI-powered form analysis and field detection
    - Intelligent field mapping with semantic matching
    - Multi-strategy selector approaches with fallbacks
    - Dynamic content generation for text fields
    - Robust error handling and recovery
    - Performance optimization and caching
    """
    
    def __init__(self, config: Config):
        """Initialize advanced browser tool."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Browser state
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        # Advanced features
        self._field_cache: Dict[str, Any] = {}
        self._form_analysis_cache: Dict[str, Any] = {}
        self._selector_performance: Dict[str, float] = {}
        
        # Enhanced field interaction
        self._field_interactor: Optional[EnhancedFieldInteractor] = None
        
        self._initialized = False
    
    async def _ensure_initialized(self) -> None:
        """Ensure browser is initialized with enhanced settings."""
        if not self._initialized:
            await self._initialize()
    
    async def _initialize(self) -> None:
        """Initialize browser with enterprise-grade settings."""
        try:
            self.playwright = await async_playwright().start()
            
            # Launch browser with optimized settings
            browser_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-extensions',
                '--disable-gpu',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-background-timer-throttling',
                '--disable-renderer-backgrounding',
                '--disable-backgrounding-occluded-windows'
            ]
            
            self.browser = await self.playwright.chromium.launch(
                headless=self.config.headless,
                args=browser_args
            )
            
            # Create context with stealth settings
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                extra_http_headers={
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none'
                }
            )
            
            # Create page
            self.page = await self.context.new_page()
            
            # Initialize enhanced field interactor
            self._field_interactor = EnhancedFieldInteractor(self.page, self.config)
            
            # Configure page settings
            await self.page.set_extra_http_headers({'Accept-Language': 'en-US,en;q=0.9'})
            
            # Set enhanced timeouts
            self.page.set_default_timeout(self.config.browser_timeout)
            self.page.set_default_navigation_timeout(self.config.page_load_timeout)
            
            # Add stealth scripts
            await self.page.add_init_script("""
                // Remove webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                });
                
                // Mock languages and plugins
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
            """)
            
            self._initialized = True
            self.logger.info("Advanced browser initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize browser: {str(e)}")
            raise
    
    async def navigate_with_retry(self, url: str, max_retries: int = 3) -> Dict[str, Any]:
        """Navigate to URL with retry logic and enhanced error handling."""
        await self._ensure_initialized()
        
        for attempt in range(max_retries):
            try:
                self.logger.info(f"Navigating to: {url} (attempt {attempt + 1})")
                
                # Wait for any existing requests to complete
                await self.page.wait_for_load_state('networkidle', timeout=5000)
                
                # Navigate with wait for different states
                response = await self.page.goto(
                    url, 
                    wait_until='domcontentloaded',
                    timeout=30000
                )
                
                if response and response.status < 400:
                    # Wait for page to be fully loaded
                    await self.page.wait_for_load_state('networkidle', timeout=10000)
                    
                    # Wait for any dynamic content
                    await asyncio.sleep(2)
                    
                    current_url = self.page.url
                    title = await self.page.title()
                    
                    # Clear caches for new page
                    self._field_cache.clear()
                    self._form_analysis_cache.clear()
                    
                    return {
                        "success": True,
                        "action": "navigate",
                        "url": current_url,
                        "title": title,
                        "status_code": response.status,
                        "attempt": attempt + 1
                    }
                else:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    
                    return {
                        "success": False,
                        "action": "navigate",
                        "error": f"Navigation failed with status: {response.status if response else 'unknown'}",
                        "attempts": attempt + 1
                    }
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    self.logger.warning(f"Navigation attempt {attempt + 1} failed: {str(e)}")
                    await asyncio.sleep(2 ** attempt)
                    continue
                
                self.logger.error(f"Navigation failed after {max_retries} attempts: {str(e)}")
                return {
                    "success": False,
                    "action": "navigate",
                    "error": str(e),
                    "attempts": max_retries
                }
        
        return {"success": False, "action": "navigate", "error": "Max retries exceeded"}
    
    async def analyze_page_structure(self) -> Dict[str, Any]:
        """Perform comprehensive AI-powered page analysis."""
        await self._ensure_initialized()
        
        try:
            # Get page URL for caching
            page_url = self.page.url
            
            # Check cache first
            if page_url in self._form_analysis_cache:
                return self._form_analysis_cache[page_url]
            
            # Get basic page info
            title = await self.page.title()
            url = self.page.url
            
            # Find all interactive elements
            forms = await self._analyze_all_forms()
            standalone_fields = await self._find_standalone_fields()
            buttons = await self._analyze_buttons()
            
            # Analyze page layout and structure
            layout_info = await self._analyze_page_layout()
            
            # Detect platform/framework
            platform_info = await self._detect_platform()
            
            analysis_result = {
                "success": True,
                "action": "analyze_page_structure",
                "page_info": {
                    "title": title,
                    "url": url,
                    "platform": platform_info,
                    "layout": layout_info,
                    "forms": forms,
                    "standalone_fields": standalone_fields,
                    "buttons": buttons,
                    "total_fields": len(forms) + len(standalone_fields),
                    "analysis_timestamp": datetime.now().isoformat()
                }
            }
            
            # Cache the result
            self._form_analysis_cache[page_url] = analysis_result
            
            return analysis_result
            
        except Exception as e:
            self.logger.error(f"Page analysis failed: {str(e)}")
            return {
                "success": False,
                "action": "analyze_page_structure",
                "error": str(e)
            }

    async def _analyze_all_forms(self) -> List[Dict[str, Any]]:
        """Analyze all forms on the page with enhanced field detection."""
        forms = await self.page.query_selector_all('form')
        form_data = []
        
        for i, form in enumerate(forms):
            try:
                # Get form attributes
                form_action = await form.get_attribute('action') or ''
                form_method = await form.get_attribute('method') or 'get'
                form_class = await form.get_attribute('class') or ''
                form_id = await form.get_attribute('id') or ''
                
                # Find all input elements with multiple strategies
                all_inputs = await form.query_selector_all(
                    'input, select, textarea, [contenteditable="true"], [role="textbox"], [role="combobox"]'
                )
                
                fields = []
                for input_elem in all_inputs:
                    field_info = await self._analyze_field_advanced(input_elem)
                    if field_info:
                        fields.append(field_info)
                
                # Analyze form purpose
                form_purpose = await self._determine_form_purpose(form, fields)
                
                form_data.append({
                    "index": i,
                    "id": form_id,
                    "class": form_class,
                    "action": form_action,
                    "method": form_method,
                    "purpose": form_purpose,
                    "fields": fields,
                    "field_count": len(fields)
                })
                
            except Exception as e:
                self.logger.debug(f"Error analyzing form {i}: {str(e)}")
                continue
        
        return form_data
    
    async def _find_standalone_fields(self) -> List[Dict[str, Any]]:
        """Find input fields that are not inside forms."""
        try:
            # Find all input elements not inside forms
            standalone_inputs = await self.page.query_selector_all(
                'input:not(form input), select:not(form select), textarea:not(form textarea), [contenteditable="true"]:not(form [contenteditable="true"])'
            )
            
            fields = []
            for input_elem in standalone_inputs:
                field_info = await self._analyze_field_advanced(input_elem)
                if field_info:
                    fields.append(field_info)
            
            return fields
            
        except Exception as e:
            self.logger.debug(f"Error finding standalone fields: {str(e)}")
            return []
    
    async def _analyze_field_advanced(self, element: ElementHandle) -> Optional[Dict[str, Any]]:
        """Perform advanced analysis of form fields."""
        try:
            # Get basic attributes
            tag_name = await element.evaluate('el => el.tagName.toLowerCase()')
            field_type = await element.get_attribute('type') or 'text'
            name = await element.get_attribute('name') or ''
            id_attr = await element.get_attribute('id') or ''
            placeholder = await element.get_attribute('placeholder') or ''
            required = await element.get_attribute('required') is not None
            value = await element.get_attribute('value') or ''
            
            # Get additional attributes
            classes = await element.get_attribute('class') or ''
            aria_label = await element.get_attribute('aria-label') or ''
            aria_describedby = await element.get_attribute('aria-describedby') or ''
            autocomplete = await element.get_attribute('autocomplete') or ''
            
            # Find associated labels with multiple strategies
            label_text = await self._find_field_label(element, id_attr, name)
            
            # Determine field purpose using AI-like analysis
            field_purpose = await self._determine_field_purpose(
                tag_name, field_type, name, id_attr, placeholder, 
                label_text, classes, aria_label
            )
            
            # Generate multiple selector strategies
            selectors = await self._generate_selector_strategies(
                tag_name, field_type, name, id_attr, classes, aria_label
            )
            
            # Get field context (nearby text)
            context = await self._get_field_context(element)
            
            # Check if field is visible and interactable
            is_visible = await element.is_visible()
            is_enabled = await element.is_enabled()
            
            return {
                "tag": tag_name,
                "type": field_type,
                "name": name,
                "id": id_attr,
                "label": label_text,
                "placeholder": placeholder,
                "required": required,
                "value": value,
                "classes": classes,
                "aria_label": aria_label,
                "aria_describedby": aria_describedby,
                "autocomplete": autocomplete,
                "field_purpose": field_purpose,
                "selectors": selectors,
                "context": context,
                "is_visible": is_visible,
                "is_enabled": is_enabled,
                "confidence_score": await self._calculate_field_confidence(field_purpose, label_text, placeholder, name)
            }
            
        except Exception as e:
            self.logger.debug(f"Field analysis failed: {str(e)}")
            return None
    
    async def _find_field_label(self, element: ElementHandle, id_attr: str, name: str) -> str:
        """Find field label using multiple strategies."""
        label_text = ''
        
        try:
            # Strategy 1: Direct label association
            if id_attr:
                label = await self.page.query_selector(f'label[for="{id_attr}"]')
                if label:
                    label_text = await label.inner_text()
                    if label_text.strip():
                        return label_text.strip()
            
            # Strategy 2: Parent label
            parent_label = await element.query_selector('xpath=ancestor::label')
            if parent_label:
                label_text = await parent_label.inner_text()
                if label_text.strip():
                    return label_text.strip()
            
            # Strategy 3: Preceding sibling or nearby text
            preceding_text = await element.evaluate('''
                el => {
                    let text = '';
                    let sibling = el.previousElementSibling;
                    while (sibling && !text.trim()) {
                        if (sibling.tagName === 'LABEL' || sibling.tagName === 'SPAN' || sibling.tagName === 'DIV') {
                            text = sibling.textContent || '';
                        }
                        sibling = sibling.previousElementSibling;
                    }
                    return text.trim();
                }
            ''')
            
            if preceding_text.strip():
                return preceding_text.strip()
            
            # Strategy 4: Parent container text
            parent_text = await element.evaluate('''
                el => {
                    let parent = el.parentElement;
                    if (parent) {
                        let text = '';
                        for (let child of parent.children) {
                            if (child !== el && (child.tagName === 'LABEL' || child.tagName === 'SPAN')) {
                                text = child.textContent || '';
                                if (text.trim()) break;
                            }
                        }
                        return text.trim();
                    }
                    return '';
                }
            ''')
            
            return parent_text.strip()
            
        except Exception as e:
            self.logger.debug(f"Label finding failed: {str(e)}")
            return ''
    
    async def _determine_field_purpose(self, tag: str, field_type: str, name: str, 
                                     id_attr: str, placeholder: str, label: str, 
                                     classes: str, aria_label: str) -> str:
        """Determine field purpose using semantic analysis."""
        # Combine all text sources
        all_text = f"{name} {id_attr} {placeholder} {label} {classes} {aria_label}".lower()
        
        # Field purpose patterns (enterprise-grade)
        purpose_patterns = {
            'first_name': [
                'first.?name', 'fname', 'given.?name', 'firstname', 'first_name',
                'prénom', 'nome', 'vorname', 'nombre'
            ],
            'last_name': [
                'last.?name', 'lname', 'surname', 'family.?name', 'lastname', 'last_name',
                'nom', 'apellido', 'nachname', 'cognome'
            ],
            'full_name': [
                'full.?name', 'complete.?name', 'your.?name', '^name$', 'fullname',
                'name', 'applicant.?name'
            ],
            'email': [
                'email', 'e.mail', 'mail', 'correo', 'courrier', 'e-mail',
                'email.?address', 'electronic.?mail'
            ],
            'phone': [
                'phone', 'tel', 'mobile', 'cellular', 'contact', 'número',
                'telefone', 'téléphone', 'telefon', 'telephone'
            ],
            'address': [
                'address', 'street', 'location', 'direccion', 'adresse',
                'endereço', 'indirizzo', 'adresa'
            ],
            'city': [
                'city', 'town', 'ciudad', 'ville', 'cidade', 'città',
                'ort', 'mesto'
            ],
            'state': [
                'state', 'province', 'region', 'estado', 'état', 'provincia',
                'bundesland', 'kraj'
            ],
            'zip': [
                'zip', 'postal', 'code', 'postcode', 'zipcode', 'zip.?code',
                'código.?postal', 'code.?postal', 'plz'
            ],
            'country': [
                'country', 'nation', 'país', 'pays', 'paese', 'land',
                'krajina', 'nationality'
            ],
            'resume': [
                'resume', 'cv', 'curriculum', 'vitae', 'upload', 'file',
                'document', 'attach'
            ],
            'cover_letter': [
                'cover.?letter', 'letter', 'motivation', 'carta', 'lettre',
                'anschreiben', 'motiv'
            ],
            'linkedin': [
                'linkedin', 'linked.in', 'social', 'profile', 'professional.?profile'
            ],
            'website': [
                'website', 'site', 'web', 'url', 'portfolio', 'blog',
                'sitio', 'página'
            ],
            'salary': [
                'salary', 'wage', 'compensation', 'pay', 'salario', 'salaire',
                'gehalt', 'mzda', 'expected.?salary'
            ],
            'experience': [
                'experience', 'years', 'exp', 'experiencia', 'expérience',
                'esperienza', 'erfahrung'
            ],
            'education': [
                'education', 'degree', 'school', 'university', 'college',
                'educación', 'éducation', 'istruzione', 'bildung'
            ],
            'skills': [
                'skills', 'abilities', 'competencies', 'habilidades',
                'compétences', 'competenze', 'fähigkeiten'
            ],
            'why_interested': [
                'why', 'interest', 'motivation', 'reason', 'por.?qué',
                'pourquoi', 'perché', 'warum', 'motivación'
            ],
            'about_yourself': [
                'about', 'yourself', 'tell.?us', 'describe', 'biography',
                'bio', 'introduction', 'acerca', 'à.?propos'
            ],
            'availability': [
                'availability', 'available', 'start.?date', 'when',
                'disponibilidad', 'disponibilité', 'verfügbarkeit'
            ],
            'references': [
                'reference', 'referencia', 'référence', 'referenza',
                'referenz', 'kontakt'
            ]
        }
        
        # Check each pattern
        for purpose, patterns in purpose_patterns.items():
            for pattern in patterns:
                if re.search(pattern, all_text):
                    return purpose
        
        # Special handling for file inputs
        if field_type == 'file':
            if any(word in all_text for word in ['resume', 'cv', 'curriculum']):
                return 'resume'
            elif any(word in all_text for word in ['cover', 'letter', 'motivation']):
                return 'cover_letter'
            else:
                return 'file_upload'
        
        # Default to generic based on input type
        type_mapping = {
            'email': 'email',
            'tel': 'phone',
            'url': 'website',
            'date': 'date',
            'number': 'number',
            'password': 'password',
            'search': 'search'
        }
        
        return type_mapping.get(field_type, 'text')
    
    async def _generate_selector_strategies(self, tag: str, field_type: str, name: str, 
                                          id_attr: str, classes: str, aria_label: str) -> List[str]:
        """Generate multiple selector strategies for robust field finding."""
        selectors = []
        
        # Strategy 1: ID selector (most reliable)
        if id_attr:
            selectors.append(f"#{id_attr}")
        
        # Strategy 2: Name selector
        if name:
            selectors.append(f"[name='{name}']")
            selectors.append(f"{tag}[name='{name}']")
        
        # Strategy 3: Type + Name combination
        if field_type and name:
            selectors.append(f"{tag}[type='{field_type}'][name='{name}']")
        
        # Strategy 4: Class-based selectors
        if classes:
            class_list = classes.split()
            for cls in class_list:
                if cls and len(cls) > 2:  # Avoid single letter classes
                    selectors.append(f".{cls}")
                    selectors.append(f"{tag}.{cls}")
        
        # Strategy 5: Aria-label selector
        if aria_label:
            selectors.append(f"[aria-label='{aria_label}']")
        
        # Strategy 6: Partial matching selectors
        if name:
            selectors.append(f"[name*='{name}']")
        if id_attr:
            selectors.append(f"[id*='{id_attr}']")
        
        # Strategy 7: Type-based selectors
        if field_type:
            selectors.append(f"{tag}[type='{field_type}']")
        
        # Strategy 8: Generic tag selector (last resort)
        selectors.append(tag)
        
        return selectors
    
    async def _get_field_context(self, element: ElementHandle) -> str:
        """Get contextual information around the field."""
        try:
            context = await element.evaluate('''
                el => {
                    let context = '';
                    let parent = el.parentElement;
                    
                    // Get surrounding text
                    if (parent) {
                        let walker = document.createTreeWalker(
                            parent,
                            NodeFilter.SHOW_TEXT,
                            null,
                            false
                        );
                        
                        let textNodes = [];
                        let node;
                        while (node = walker.nextNode()) {
                            if (node.textContent.trim()) {
                                textNodes.push(node.textContent.trim());
                            }
                        }
                        context = textNodes.join(' ').substring(0, 200);
                    }
                    
                    return context;
                }
            ''')
            
            return context.strip()
            
        except Exception as e:
            self.logger.debug(f"Context extraction failed: {str(e)}")
            return ''
    
    async def _calculate_field_confidence(self, purpose: str, label: str, 
                                        placeholder: str, name: str) -> float:
        """Calculate confidence score for field purpose identification."""
        score = 0.0
        
        # Base score
        if purpose != 'text':
            score += 0.3
        
        # Label match
        if label and purpose in label.lower():
            score += 0.4
        
        # Placeholder match
        if placeholder and purpose in placeholder.lower():
            score += 0.3
        
        # Name match
        if name and purpose in name.lower():
            score += 0.4
        
        # Bonus for exact matches
        if label and label.lower() == purpose:
            score += 0.2
        
        return min(score, 1.0)
    
    async def _analyze_buttons(self) -> List[Dict[str, Any]]:
        """Analyze all buttons on the page."""
        try:
            buttons = await self.page.query_selector_all(
                'button, input[type="submit"], input[type="button"], [role="button"], a[href="#"], .btn'
            )
            
            button_data = []
            for i, button in enumerate(buttons):
                try:
                    tag_name = await button.evaluate('el => el.tagName.toLowerCase()')
                    button_type = await button.get_attribute('type') or ''
                    text = await button.inner_text() or ''
                    value = await button.get_attribute('value') or ''
                    classes = await button.get_attribute('class') or ''
                    id_attr = await button.get_attribute('id') or ''
                    
                    # Determine button purpose
                    purpose = self._determine_button_purpose(text, value, classes, button_type)
                    
                    # Check if button is visible and enabled
                    is_visible = await button.is_visible()
                    is_enabled = await button.is_enabled()
                    
                    button_data.append({
                        "index": i,
                        "tag": tag_name,
                        "type": button_type,
                        "text": text.strip(),
                        "value": value,
                        "classes": classes,
                        "id": id_attr,
                        "purpose": purpose,
                        "is_visible": is_visible,
                        "is_enabled": is_enabled
                    })
                    
                except Exception as e:
                    self.logger.debug(f"Button analysis failed: {str(e)}")
                    continue
            
            return button_data
            
        except Exception as e:
            self.logger.debug(f"Button analysis failed: {str(e)}")
            return []
    
    def _determine_button_purpose(self, text: str, value: str, classes: str, button_type: str) -> str:
        """Determine button purpose from text and attributes."""
        all_text = f"{text} {value} {classes}".lower()
        
        # Button purpose patterns
        if any(word in all_text for word in ['submit', 'apply', 'send', 'enviar', 'envoyer']):
            return 'submit'
        elif any(word in all_text for word in ['next', 'continue', 'siguiente', 'suivant']):
            return 'next'
        elif any(word in all_text for word in ['back', 'previous', 'anterior', 'précédent']):
            return 'back'
        elif any(word in all_text for word in ['save', 'guardar', 'sauvegarder']):
            return 'save'
        elif any(word in all_text for word in ['cancel', 'cancelar', 'annuler']):
            return 'cancel'
        elif any(word in all_text for word in ['upload', 'browse', 'choose', 'select']):
            return 'upload'
        elif button_type == 'submit':
            return 'submit'
        else:
            return 'action'
    
    async def _analyze_page_layout(self) -> Dict[str, Any]:
        """Analyze page layout and structure."""
        try:
            layout_info = await self.page.evaluate('''
                () => {
                    const body = document.body;
                    const main = document.querySelector('main') || document.querySelector('#main') || document.querySelector('.main');
                    const content = document.querySelector('.content') || document.querySelector('#content');
                    
                    return {
                        hasMain: !!main,
                        hasContent: !!content,
                        bodyClasses: body.className,
                        viewport: {
                            width: window.innerWidth,
                            height: window.innerHeight
                        },
                        scrollHeight: document.documentElement.scrollHeight,
                        formCount: document.forms.length,
                        inputCount: document.querySelectorAll('input').length,
                        framework: (function() {
                            if (window.React) return 'React';
                            if (window.Vue) return 'Vue';
                            if (window.angular) return 'Angular';
                            if (document.querySelector('[data-reactroot]')) return 'React';
                            if (document.querySelector('[data-server-rendered]')) return 'Vue';
                            return 'Unknown';
                        })()
                    };
                }
            ''')
            
            return layout_info
            
        except Exception as e:
            self.logger.debug(f"Layout analysis failed: {str(e)}")
            return {}
    
    async def _detect_platform(self) -> Dict[str, Any]:
        """Detect job platform or framework."""
        try:
            url = self.page.url.lower()
            title = await self.page.title()
            
            # Common job platforms
            platforms = {
                'linkedin': 'linkedin.com',
                'indeed': 'indeed.com',
                'glassdoor': 'glassdoor.com',
                'monster': 'monster.com',
                'ziprecruiter': 'ziprecruiter.com',
                'careerbuilder': 'careerbuilder.com',
                'workday': 'myworkdayjobs.com',
                'successfactors': 'successfactors.com',
                'icims': 'icims.com',
                'greenhouse': 'greenhouse.io',
                'lever': 'lever.co',
                'smartrecruiters': 'smartrecruiters.com',
                'jobvite': 'jobvite.com',
                'taleo': 'taleo.net'
            }
            
            detected_platform = 'unknown'
            for platform, domain in platforms.items():
                if domain in url:
                    detected_platform = platform
                    break
            
            return {
                "platform": detected_platform,
                "url": url,
                "title": title,
                "is_known_platform": detected_platform != 'unknown'
            }
            
        except Exception as e:
            self.logger.debug(f"Platform detection failed: {str(e)}")
            return {"platform": "unknown", "is_known_platform": False}
    
    async def _determine_form_purpose(self, form: ElementHandle, fields: List[Dict[str, Any]]) -> str:
        """Determine the purpose of a form based on its fields."""
        try:
            form_action = await form.get_attribute('action') or ''
            form_classes = await form.get_attribute('class') or ''
            form_id = await form.get_attribute('id') or ''
            
            # Analyze field types
            field_purposes = [field.get('field_purpose', 'text') for field in fields]
            
            # Check for job application indicators
            if any(purpose in field_purposes for purpose in ['first_name', 'last_name', 'email', 'resume']):
                return 'job_application'
            elif any(purpose in field_purposes for purpose in ['email', 'password']):
                return 'login'
            elif 'search' in field_purposes:
                return 'search'
            elif any(word in form_action.lower() for word in ['apply', 'submit', 'application']):
                return 'job_application'
            elif any(word in form_classes.lower() for word in ['login', 'signin', 'auth']):
                return 'login'
            else:
                return 'general'
                
        except Exception as e:
            self.logger.debug(f"Form purpose detection failed: {str(e)}")
            return 'general'

    async def fill_field_enhanced(self, field_info: Dict[str, Any], value: str) -> Dict[str, Any]:
        """
        Fill a field using enhanced interaction strategies.
        
        Args:
            field_info: Field information from page analysis
            value: Value to fill in the field
            
        Returns:
            Result of the field filling operation
        """
        await self._ensure_initialized()
        
        if not self._field_interactor:
            return {
                "success": False,
                "error": "Enhanced field interactor not initialized",
                "action": "fill_field_enhanced"
            }
        
        try:
            result = await self._field_interactor.fill_field_robustly(field_info, value)
            return {
                "success": result.get('success', False),
                "action": "fill_field_enhanced",
                "field_info": field_info,
                "value": value,
                "result": result
            }
        except Exception as e:
            self.logger.error(f"Enhanced field filling failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "action": "fill_field_enhanced",
                "field_info": field_info,
                "value": value
            }
    
    def get_field_interaction_stats(self) -> Dict[str, Any]:
        """Get statistics from the enhanced field interactor."""
        if self._field_interactor:
            return self._field_interactor.get_statistics()
        return {}

    async def close(self) -> None:
        """Close browser and cleanup resources."""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            
            self._initialized = False
            self.logger.info("Browser closed successfully")
            
        except Exception as e:
            self.logger.error(f"Error closing browser: {str(e)}")
    
    def __del__(self):
        """Cleanup on deletion."""
        if self._initialized:
            self.logger.warning("BrowserTool deleted without proper cleanup. Call close() explicitly.")


# Maintain backward compatibility
BrowserTool = AdvancedBrowserTool 