import sys
import json
import logging
from playwright.sync_api import Page
import re # For cleaning

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Common User Agent String (Copied from browser_controller)
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

def find_label(page: Page, element) -> str:
    """Attempts to find a label for a given element using various heuristics."""
    label_text = ""
    element_id = element.get_attribute('id')
    
    try:
        # 1. aria-labelledby
        aria_labelledby = element.get_attribute('aria-labelledby')
        if aria_labelledby:
            label_elements = page.locator(f"#{aria_labelledby}")
            if label_elements.count() > 0:
                label_text = " ".join(label_elements.all_text_contents()).strip()
                if label_text: return label_text

        # 2. aria-label
        aria_label = element.get_attribute('aria-label')
        if aria_label: 
            label_text = aria_label.strip()
            if label_text: return label_text

        # 3. Standard label[for]
        if element_id:
            label = page.locator(f'label[for="{element_id}"]').first
            # Use a short timeout as the label should be readily available if it exists
            if label.is_visible(timeout=150): 
                label_text = label.text_content().strip()
                if label_text: return label_text

        # 4. Wrapper + Preceding Sibling Heuristic (Common Pattern)
        wrapper = element.locator('xpath=ancestor::div[contains(@class, "field") or contains(@class, "question") or contains(@class, "form-group")][1]').first
        if wrapper.count() > 0:
             # Check inside wrapper first
             label_in_wrapper = wrapper.locator('label, strong, h1, h2, h3, h4, h5, h6').first
             if label_in_wrapper.is_visible(timeout=100): 
                 label_text = label_in_wrapper.text_content().strip()
                 if label_text: return label_text.replace('*','').strip() # Clean common markers
                 
             # Check element preceding the wrapper
             label_element = wrapper.locator('xpath=preceding-sibling::*[self::label or self::div or self::span or self::strong][1]').first
             if label_element.is_visible(timeout=100):
                 label_text = label_element.text_content().strip()
                 if label_text: return label_text.replace('*','').strip()
                 
        # 5. Direct Preceding Sibling (if no wrapper found/matched)
        label_element = element.locator('xpath=preceding-sibling::*[self::label or self::div or self::span or self::strong][1]').first
        if label_element.is_visible(timeout=100):
            label_text = label_element.text_content().strip()
            if label_text: return label_text.replace('*','').strip()

        # 6. Placeholder
        placeholder = element.get_attribute('placeholder')
        if placeholder: 
            label_text = placeholder.strip()
            if label_text: return label_text

    except Exception as e:
        logging.warning(f"Label finding error for element: {e}")

    return "No label found"

def find_label_for_probe(page: Page, element) -> str:
    """Finds the best associated label for a form element (heuristic)."""
    try:
        # 1. Check for aria-labelledby
        aria_labelledby = element.get_attribute('aria-labelledby')
        if aria_labelledby:
            # Find elements with those IDs and concatenate text
            label_texts = []
            for label_id in aria_labelledby.split():
                label_element = page.locator(f'#{label_id}')
                if label_element.count() > 0:
                    label_texts.append(label_element.first.text_content(timeout=500).strip())
            if label_texts:
                return " ".join(label_texts)
                
        # 2. Check for aria-label
        aria_label = element.get_attribute('aria-label')
        if aria_label:
            return aria_label

        # 3. Check for wrapping <label>
        # Note: Playwright's element selectors don't directly support parent traversal easily in locator strings.
        # We can use evaluate to check the parent node.
        is_wrapped = element.evaluate(
            'el => el.parentElement && el.parentElement.tagName === "LABEL"'
        )
        if is_wrapped:
            parent_label_text = element.evaluate(
                'el => el.parentElement.textContent'
            ).strip()
            if parent_label_text: return parent_label_text

        # 4. Check for <label for=...> matching element's ID
        element_id = element.get_attribute('id')
        if element_id:
            label_element = page.locator(f'label[for="{element_id}"]')
            if label_element.count() > 0:
                label_text = label_element.first.text_content(timeout=500).strip()
                if label_text: return label_text

        # 5. Heuristic: Find closest preceding label/strong/b tag (might need refinement)
        # This is harder and potentially brittle with Playwright locators alone.
        # A simpler approach might be to get nearby text, but that's less precise.
        # For now, let's skip this complex heuristic.

        return "No label found" # Default if no label found
    except Exception as e:
        logging.warning(f"Error finding label: {e}")
        return "Error finding label"

def generate_stable_selector(element) -> str | None:
    """Generates the most stable CSS selector possible (ID > QA > Name > Type+Index as last resort)."""
    element_id = element.get_attribute('id')
    if element_id:
        # Basic sanitation for CSS ID selector
        sanitized_id = re.sub(r'[^a-zA-Z0-9_-]', '_', element_id)
        return f"#{sanitized_id}"
        
    data_qa = element.get_attribute('data-qa')
    if data_qa:
        return f"[data-qa=\"{data_qa}\"]"
        
    element_name = element.get_attribute('name')
    if element_name:
        tag_name = element.evaluate('el => el.tagName.toLowerCase()')
        escaped_name = element_name.replace('"', '\\"').replace(':', '\\:').replace('[', '\\[').replace(']', '\\]')
        return f"{tag_name}[name=\"{escaped_name}\"]"
        
    # Add more robust fallback later if needed (e.g., based on class, text)
    logging.debug("Could not generate stable selector based on ID/QA/Name.")
    return None # Indicate no stable selector found

def probe_page_for_llm(page: Page) -> str:
    """Probes the page structure and returns a JSON representation of interactive elements for LLM analysis."""
    logging.info("Starting LLM element probe on the current page state...")
    
    # Execute in browser context to gather elements with their structural context
    page_elements = page.evaluate("""() => {
        // Helper function to get text content of an element, normalized
        function getVisibleText(element) {
            if (!element) return '';
            let text = element.textContent || '';
            return text.trim().replace(/\\s+/g, ' ');
        }
        
        // Helper function to find the closest label for an input
        function findLabelFor(element) {
            // First try by 'for' attribute matching id
            if (element.id) {
                const label = document.querySelector(`label[for="${element.id}"]`);
                if (label) return getVisibleText(label);
            }
            
            // Try parent label
            let parent = element.parentElement;
            while (parent && parent.tagName !== 'BODY') {
                if (parent.tagName === 'LABEL') {
                    return getVisibleText(parent);
                }
                parent = parent.parentElement;
            }
            
            // Try nearby heading or text
            const rect = element.getBoundingClientRect();
            const nearbyElements = Array.from(document.querySelectorAll('label, h1, h2, h3, h4, h5, h6, p, div, span'))
                .filter(el => {
                    // Only consider elements above or to the left of our input
                    const elRect = el.getBoundingClientRect();
                    return (elRect.bottom <= rect.top + 50 && Math.abs(elRect.left - rect.left) < 200) || 
                           (elRect.right <= rect.left + 20 && Math.abs(elRect.top - rect.top) < 100);
                })
                .sort((a, b) => {
                    // Sort by distance (simplified)
                    const aRect = a.getBoundingClientRect();
                    const bRect = b.getBoundingClientRect();
                    const aDist = Math.sqrt(Math.pow(aRect.left - rect.left, 2) + Math.pow(aRect.top - rect.top, 2));
                    const bDist = Math.sqrt(Math.pow(bRect.left - rect.left, 2) + Math.pow(bRect.top - rect.top, 2));
                    return aDist - bDist;
                });
            
            for (const el of nearbyElements) {
                const text = getVisibleText(el);
                if (text && text.length < 200) return text;  // Reasonable label length
            }
            
            return '';
        }

        // Generate a stable, robust selector for an element
        function generateStableSelector(element) {
            // Start with tag name
            let selector = element.tagName.toLowerCase();
            
            // Add ID if present (most specific)
            if (element.id) {
                return `#${element.id}`;
            }
            
            // Add important attributes that help identify the element
            const keyAttributes = ['name', 'data-qa', 'data-test', 'data-testid', 'aria-label'];
            for (const attr of keyAttributes) {
                if (element.hasAttribute(attr)) {
                    const value = element.getAttribute(attr);
                    // Handle special characters in attribute selectors
                    const escapedValue = value.replace(/\\]/g, '\\\\]').replace(/\\[/g, '\\\\[');
                    return `${selector}[${attr}="${escapedValue}"]`;
                }
            }
            
            // Add class if present
            if (element.className && typeof element.className === 'string') {
                const classes = element.className.trim().split(/\\s+/);
                // Use only stable-looking classes (avoid auto-generated ones)
                const stableClasses = classes.filter(cls => 
                    !cls.match(/^[0-9]/) && 
                    !cls.match(/^[a-z][a-z0-9]{0,2}$/) && 
                    cls.length > 2
                );
                
                if (stableClasses.length > 0) {
                    selector += '.' + stableClasses.join('.');
                    // Check uniqueness
                    if (document.querySelectorAll(selector).length === 1) {
                        return selector;
                    }
                }
            }
            
            // Add parent context for specificity
            let parent = element.parentElement;
            if (parent && parent.tagName !== 'BODY') {
                const parentTag = parent.tagName.toLowerCase();
                
                // Special case for common containers
                if (parentTag === 'label') {
                    const labelText = getVisibleText(parent).substring(0, 40);
                    if (labelText) {
                        return `label:has-text("${labelText}") ${selector}`;
                    }
                }
                
                if (parent.id) {
                    return `#${parent.id} > ${selector}`;
                }
                
                if (parent.getAttribute('data-qa')) {
                    return `[data-qa="${parent.getAttribute('data-qa')}"] > ${selector}`;
                }
            }
            
            // Placeholder with name attribute as fallback
            if (element.name) {
                const escapedName = element.name.replace(/\\]/g, '\\\\]').replace(/\\[/g, '\\\\[');
                return `${selector}[name="${escapedName}"]`;
            }
            
            // Add nth-child as last resort
            const siblings = Array.from(element.parentNode.children);
            const index = siblings.indexOf(element);
            return `${selector}:nth-child(${index + 1})`;
        }

        // Find form sections and fieldsets to establish hierarchy
        function getFormSections() {
            const sections = [];
            // Look for fieldsets, sections, divs with headings, etc.
            const potentialSections = Array.from(document.querySelectorAll('fieldset, section, .form-section, div > h2, div > h3'));
            
            potentialSections.forEach(section => {
                // If it's a heading, use its parent div as the section
                if (['H2', 'H3', 'H4'].includes(section.tagName)) {
                    section = section.parentElement;
                }
                
                const heading = section.querySelector('legend, h2, h3, h4') || section;
                const headingText = getVisibleText(heading);
                
                // Get all form elements within this section
                const formElements = Array.from(section.querySelectorAll('input, select, textarea'));
                
                if (formElements.length > 0) {
                    sections.push({
                        title: headingText,
                        selector: generateStableSelector(section),
                        elements: formElements.map(el => generateStableSelector(el))
                    });
                }
            });
            
            return sections;
        }

        // Get structural context for a field
        function getStructuralContext(element) {
            const structuralContext = {
                ancestors: [],
                siblings: [],
                isWithinFieldset: false,
                nearbyText: [],
                section: null
            };
            
            // Build ancestor chain (limited depth)
            let current = element.parentElement;
            let depth = 0;
            while (current && current.tagName !== 'BODY' && depth < 3) {
                structuralContext.ancestors.push({
                    tag: current.tagName.toLowerCase(),
                    classes: Array.from(current.classList),
                    id: current.id || null,
                    text: getVisibleText(current).substring(0, 100)
                });
                
                if (current.tagName === 'FIELDSET') {
                    structuralContext.isWithinFieldset = true;
                    const legend = current.querySelector('legend');
                    if (legend) {
                        structuralContext.fieldsetTitle = getVisibleText(legend);
                    }
                }
                
                current = current.parentElement;
                depth++;
            }
            
            // Get direct siblings that might be related (labels, hints, errors)
            if (element.parentElement) {
                const siblings = Array.from(element.parentElement.children);
                structuralContext.siblings = siblings
                    .filter(sib => sib !== element && ['LABEL', 'SPAN', 'DIV', 'P', 'SMALL'].includes(sib.tagName))
                    .map(sib => ({
                        tag: sib.tagName.toLowerCase(),
                        text: getVisibleText(sib).substring(0, 100)
                    }));
            }
            
            // Find nearby text for context (limited to reasonable candidates)
            const rect = element.getBoundingClientRect();
            const nearby = Array.from(document.querySelectorAll('label, p, span, div:not(:has(*))'))
                .filter(el => {
                    if (!el.textContent.trim()) return false;
                    const elRect = el.getBoundingClientRect();
                    const verticallyNear = Math.abs(elRect.top - rect.top) < 100;
                    const horizontallyNear = Math.abs(elRect.left - rect.left) < 300;
                    return verticallyNear && horizontallyNear;
                })
                .slice(0, 5); // Limit to 5 nearest elements
                
            structuralContext.nearbyText = nearby.map(el => getVisibleText(el)).filter(text => text.length > 0 && text.length < 200);
            
            return structuralContext;
        }

        // Get options from a select element
        function getSelectOptions(element) {
            if (element.tagName !== 'SELECT') return [];
            
            return Array.from(element.options).map(option => ({
                value: option.value,
                text: option.text.trim(),
                selected: option.selected
            }));
        }
        
        // Get radio/checkbox options from a group
        function getOptionGroup(element) {
            if (!['radio', 'checkbox'].includes(element.type)) return [];
            
            // Try to find related inputs with the same name
            const name = element.name;
            if (!name) return [];
            
            const selector = `input[type="${element.type}"][name="${name.replace(/"/g, '\\"')}"]`;
            const groupElements = Array.from(document.querySelectorAll(selector));
            
            return groupElements.map(input => {
                // Find label for this specific input
                let label = '';
                
                // Check for explicit label
                if (input.id) {
                    const labelEl = document.querySelector(`label[for="${input.id}"]`);
                    if (labelEl) {
                        label = getVisibleText(labelEl);
                    }
                }
                
                // Check for wrapping label
                if (!label) {
                    let parent = input.parentElement;
                    while (parent && parent.tagName !== 'BODY') {
                        if (parent.tagName === 'LABEL') {
                            // Extract text excluding nested input text
                            const cloned = parent.cloneNode(true);
                            const nestedInputs = cloned.querySelectorAll('input');
                            nestedInputs.forEach(el => el.remove());
                            label = getVisibleText(cloned);
                            break;
                        }
                        parent = parent.parentElement;
                    }
                }
                
                // If still no label, check nearby text
                if (!label) {
                    const inputRect = input.getBoundingClientRect();
                    const nearby = Array.from(document.querySelectorAll('span, div:not(:has(*))'))
                        .filter(el => {
                            if (!el.textContent.trim()) return false;
                            const elRect = el.getBoundingClientRect();
                            return (Math.abs(elRect.top - inputRect.top) < 30 && 
                                   Math.abs(elRect.left - inputRect.left) < 200);
                        })
                        .sort((a, b) => {
                            const aRect = a.getBoundingClientRect();
                            const bRect = b.getBoundingClientRect();
                            const aDist = Math.abs(aRect.left - inputRect.left);
                            const bDist = Math.abs(bRect.left - inputRect.left);
                            return aDist - bDist;
                        });
                        
                    if (nearby.length > 0) {
                        label = getVisibleText(nearby[0]);
                    }
                }
                
                return {
                    value: input.value,
                    label: label,
                    checked: input.checked,
                    selector: generateStableSelector(input),
                    disabled: input.disabled
                };
            });
        }

        // Main function to collect all interactive elements
        const interactiveElements = Array.from(document.querySelectorAll('input, select, textarea, button, [role="button"], [role="checkbox"], [role="radio"], [role="switch"], [role="listbox"], [role="combobox"]'));
        const elements = [];
        const processedSelectors = new Set(); // Avoid duplicates
        
        // Process form sections first to establish hierarchy
        const formSections = getFormSections();
        
        // Process each interactive element
        interactiveElements.forEach(element => {
            // Skip hidden elements
            if (element.type === 'hidden' || element.style.display === 'none' || element.style.visibility === 'hidden') {
                return;
            }
            
            // Skip elements without position/size (likely not rendered)
            const rect = element.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) {
                return;
            }
            
            const selector = generateStableSelector(element);
            
            // Skip if we already processed this selector
            if (processedSelectors.has(selector)) return;
            processedSelectors.add(selector);
            
            // Basic element info
            const elementInfo = {
                selector: selector,
                tag: element.tagName.toLowerCase(),
                type_guess: element.type || null,
                name: element.name || null,
                id: element.id || null,
                placeholder: element.placeholder || null,
                value: element.value || null,
                required: element.required || false,
                disabled: element.disabled || false,
                readonly: element.readOnly || false,
                role: element.getAttribute('role'),
                ariaLabel: element.getAttribute('aria-label'),
                ariaLabelledby: element.getAttribute('aria-labelledby'),
                ariaDescribedby: element.getAttribute('aria-describedby'),
                classes: Array.from(element.classList)
            };
            
            // Find label text
            elementInfo.label = findLabelFor(element);
            
            // Add structural context
            elementInfo.structuralContext = getStructuralContext(element);
            
            // Find which form section this element belongs to
            for (const section of formSections) {
                if (section.elements.includes(selector)) {
                    elementInfo.section = section.title;
                    break;
                }
            }
            
            // Add field-type specific information
            if (element.tagName === 'SELECT') {
                elementInfo.options = getSelectOptions(element);
            } else if (['radio', 'checkbox'].includes(element.type)) {
                elementInfo.group_options = getOptionGroup(element);
            } else if (element.tagName === 'BUTTON' || element.getAttribute('role') === 'button') {
                elementInfo.button_text = getVisibleText(element);
            }
            
            elements.push(elementInfo);
        });

        return elements;
    }""")
    
    # Process results
    if not page_elements or len(page_elements) == 0:
        logging.warning("No interactive elements found by LLM probe.")
        return "[]"
    
    logging.info(f"Found {len(page_elements)} potential interactive elements for LLM probe.")
    
    # Sort elements by importance based on structural cues
    # This helps the LLM focus on the most relevant elements first
    page_elements.sort(key=lambda e: (
        e.get('section', 'z') is None,  # Elements with section context first
        not e.get('label', ''),        # Elements with labels next
        e.get('tag') == 'button',      # Push buttons lower in the list
        e.get('disabled', False),      # Disabled elements last
        e.get('readonly', False)       # Readonly elements last
    ))
    
    # Convert to JSON string for LLM
    try:
        elements_json = json.dumps(page_elements, indent=2)
        logging.info(f"LLM probe complete. Generated summaries for {len(page_elements)} elements.")
        return elements_json
    except Exception as e:
        logging.error(f"Error serializing probe results to JSON: {e}")
        return "[]"

# Modify the __main__ block for testing if needed, or remove it
if __name__ == "__main__":
    # This main block won't work anymore as it requires a live Page object.
    # It should be removed or adapted for specific testing scenarios that 
    # involve launching playwright and navigating before calling the probe.
    print("This script is now designed to be imported and called with a Playwright Page object.")
    print("The __main__ block cannot execute the probe directly.")
    # Example usage (requires playwright setup):
    # from playwright.sync_api import sync_playwright
    # with sync_playwright() as p:
    #    browser = p.chromium.launch()
    #    page = browser.new_page()
    #    page.goto("some_url")
    #    json_output = probe_page_for_llm(page)
    #    print(json_output)
    #    browser.close()
    sys.exit(1) 