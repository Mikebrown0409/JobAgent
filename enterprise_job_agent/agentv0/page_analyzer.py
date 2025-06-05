import logging
import re
import json
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from bs4 import BeautifulSoup

logger = logging.getLogger("PageAnalyzer")

async def analyze_page_structure(html: str, current_url: str) -> Dict[str, Any]:
    """Analyze the page structure to identify interactive elements like forms, fields, buttons.
    
    Args:
        html: The HTML content of the page
        current_url: The current URL of the page
        
    Returns:
        A dictionary containing structured information about the page elements
    """
    logger.info(f"Analyzing page structure at {current_url}")
    
    # Parse HTML with BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all interactive elements that are likely part of forms
    elements = []
    
    # Process inputs
    inputs = soup.find_all('input')
    for input_elem in inputs:
        # Skip hidden inputs unless they might be important
        input_type = input_elem.get('type', 'text').lower()
        if input_type == 'hidden' and not input_elem.get('name', '').lower() in ['csrf', 'token', 'auth']:
            continue
            
        element_info = _extract_input_info(input_elem)
        if element_info:
            elements.append(element_info)
    
    # Process selects
    selects = soup.find_all('select')
    for select_elem in selects:
        element_info = _extract_select_info(select_elem)
        if element_info:
            elements.append(element_info)
    
    # Process textareas
    textareas = soup.find_all('textarea')
    for textarea_elem in textareas:
        element_info = _extract_textarea_info(textarea_elem)
        if element_info:
            elements.append(element_info)
    
    # Process buttons and submit inputs
    buttons = soup.find_all(['button', 'input[type="submit"]', 'input[type="button"]'])
    for button_elem in buttons:
        element_info = _extract_button_info(button_elem)
        if element_info:
            elements.append(element_info)
    
    logger.info(f"Found {len(elements)} interactive elements")
    
    return {
        "elements": elements,
        "url": current_url
    }

def _extract_input_info(element) -> Optional[Dict[str, Any]]:
    """Extract information from an input element.
    
    Args:
        element: A BeautifulSoup element representing an input
        
    Returns:
        A dictionary with information about the input, or None if not relevant
    """
    input_type = element.get('type', 'text').lower()
    input_id = element.get('id', '')
    input_name = element.get('name', '')
    input_class = ' '.join(element.get('class', []))
    input_value = element.get('value', '')
    input_placeholder = element.get('placeholder', '')
    
    # Generate a CSS selector for this element
    selector = _generate_selector(element)
    if not selector:
        return None
    
    # Try to find a label for this input
    label_text = _find_label_text(element)
    
    # Get surrounding text for context
    surrounding_text = _get_surrounding_text(element)
    
    # Process different input types
    if input_type in ['text', 'email', 'password', 'number', 'tel', 'url', 'search', 'date', 'datetime-local', 'month', 'week', 'time']:
        return {
            'type': 'input',
            'input_type': input_type,
            'selector': selector,
            'id': input_id,
            'name': input_name,
            'class': input_class,
            'value': input_value,
            'placeholder': input_placeholder,
            'label': label_text,
            'surrounding_text': surrounding_text,
            'required': element.has_attr('required'),
            'maxlength': element.get('maxlength', ''),
            'minlength': element.get('minlength', ''),
            'disabled': element.has_attr('disabled')
        }
    
    elif input_type in ['checkbox', 'radio']:
        return {
            'type': input_type,
            'selector': selector,
            'id': input_id,
            'name': input_name,
            'class': input_class,
            'value': input_value,
            'label': label_text,
            'surrounding_text': surrounding_text,
            'checked': element.has_attr('checked'),
            'required': element.has_attr('required'),
            'disabled': element.has_attr('disabled')
        }
    
    elif input_type == 'file':
        return {
            'type': 'file',
            'selector': selector,
            'id': input_id,
            'name': input_name,
            'class': input_class,
            'label': label_text,
            'surrounding_text': surrounding_text,
            'accept': element.get('accept', ''),
            'required': element.has_attr('required'),
            'disabled': element.has_attr('disabled')
        }
    
    elif input_type in ['submit', 'button']:
        return {
            'type': 'button',
            'button_type': input_type,
            'selector': selector,
            'id': input_id,
            'name': input_name,
            'class': input_class,
            'value': input_value or label_text or 'Submit',
            'text': input_value or label_text or 'Submit',
            'disabled': element.has_attr('disabled')
        }
    
    elif input_type == 'hidden':
        # Only include significant hidden fields
        if input_name.lower() in ['csrf', 'token', 'auth']:
            return {
                'type': 'hidden',
                'selector': selector,
                'id': input_id,
                'name': input_name,
                'value': input_value
            }
    
    return None

def _extract_select_info(element) -> Optional[Dict[str, Any]]:
    """Extract information from a select element.
    
    Args:
        element: A BeautifulSoup element representing a select
        
    Returns:
        A dictionary with information about the select, or None if not relevant
    """
    select_id = element.get('id', '')
    select_name = element.get('name', '')
    select_class = ' '.join(element.get('class', []))
    
    # Generate a CSS selector for this element
    selector = _generate_selector(element)
    if not selector:
        return None
    
    # Try to find a label for this select
    label_text = _find_label_text(element)
    
    # Get surrounding text for context
    surrounding_text = _get_surrounding_text(element)
    
    # Get options
    options = []
    option_elements = element.find_all('option')
    for option in option_elements:
        option_value = option.get('value', '')
        option_text = option.get_text(strip=True)
        option_selected = option.has_attr('selected')
        
        # Skip placeholders with empty values unless they have text
        if not option_value and not option_text:
            continue
            
        options.append({
            'value': option_value,
            'text': option_text,
            'selected': option_selected
        })
    
    return {
        'type': 'select',
        'selector': selector,
        'id': select_id,
        'name': select_name,
        'class': select_class,
        'label': label_text,
        'surrounding_text': surrounding_text,
        'options': options,
        'required': element.has_attr('required'),
        'disabled': element.has_attr('disabled'),
        'multiple': element.has_attr('multiple')
    }

def _extract_textarea_info(element) -> Optional[Dict[str, Any]]:
    """Extract information from a textarea element.
    
    Args:
        element: A BeautifulSoup element representing a textarea
        
    Returns:
        A dictionary with information about the textarea, or None if not relevant
    """
    textarea_id = element.get('id', '')
    textarea_name = element.get('name', '')
    textarea_class = ' '.join(element.get('class', []))
    textarea_placeholder = element.get('placeholder', '')
    
    # Generate a CSS selector for this element
    selector = _generate_selector(element)
    if not selector:
        return None
    
    # Try to find a label for this textarea
    label_text = _find_label_text(element)
    
    # Get surrounding text for context
    surrounding_text = _get_surrounding_text(element)
    
    # Get current value
    textarea_value = element.get_text(strip=True)
    
    return {
        'type': 'textarea',
        'selector': selector,
        'id': textarea_id,
        'name': textarea_name,
        'class': textarea_class,
        'value': textarea_value,
        'placeholder': textarea_placeholder,
        'label': label_text,
        'surrounding_text': surrounding_text,
        'required': element.has_attr('required'),
        'maxlength': element.get('maxlength', ''),
        'minlength': element.get('minlength', ''),
        'disabled': element.has_attr('disabled'),
        'rows': element.get('rows', ''),
        'cols': element.get('cols', '')
    }

def _extract_button_info(element) -> Optional[Dict[str, Any]]:
    """Extract information from a button element.
    
    Args:
        element: A BeautifulSoup element representing a button
        
    Returns:
        A dictionary with information about the button, or None if not relevant
    """
    button_id = element.get('id', '')
    button_name = element.get('name', '')
    button_class = ' '.join(element.get('class', []))
    button_type = element.get('type', 'button').lower() if element.name == 'button' else element.get('type', 'submit').lower()
    
    # Generate a CSS selector for this element
    selector = _generate_selector(element)
    if not selector:
        return None
    
    # Get button text
    if element.name == 'input':
        button_text = element.get('value', 'Submit')
    else:
        button_text = element.get_text(strip=True) or element.get('title', 'Button')
    
    # Determine if this looks like a submit button
    is_submit = button_type == 'submit' or re.search(r'submit|apply|send|continue|next', button_text, re.I) is not None
    
    return {
        'type': 'button',
        'button_type': button_type,
        'selector': selector,
        'id': button_id,
        'name': button_name,
        'class': button_class,
        'text': button_text,
        'is_submit': is_submit,
        'disabled': element.has_attr('disabled')
    }

def _generate_selector(element) -> Optional[str]:
    """Generate a CSS selector for an element.
    
    Args:
        element: A BeautifulSoup element
        
    Returns:
        A CSS selector string, or None if one couldn't be generated
    """
    # Try ID selector first (most reliable)
    if element.has_attr('id'):
        return f"#{element['id']}"
    
    # Try name attribute for form elements
    if element.has_attr('name') and element.name in ['input', 'select', 'textarea', 'button']:
        tag = element.name
        return f"{tag}[name='{element['name']}']"
    
    # For other elements, try multiple attributes
    selectors = []
    
    # By tag and class
    if element.has_attr('class'):
        class_list = element['class']
        if class_list:
            # Use first class if multiple exist
            selectors.append(f"{element.name}.{class_list[0]}")
    
    # By data attributes
    for attr in element.attrs:
        if attr.startswith('data-'):
            selectors.append(f"{element.name}[{attr}='{element[attr]}']")
    
    # By specific attributes based on element type
    if element.name == 'input':
        input_type = element.get('type', 'text')
        if element.has_attr('placeholder'):
            selectors.append(f"input[type='{input_type}'][placeholder='{element['placeholder']}']")
    
    # Final fallback - use a more complex path, but limit depth to avoid selector being too specific
    if not selectors:
        # Create a simple path (at most 2 levels up)
        path = []
        current = element
        for _ in range(2):
            if current.parent and current.parent.name != '[document]':
                parent = current.parent
                siblings = parent.find_all(current.name, recursive=False)
                if len(siblings) > 1:
                    # If there are multiple siblings with same tag, include position
                    position = siblings.index(current) + 1
                    path.insert(0, f"{current.name}:nth-of-type({position})")
                else:
                    path.insert(0, current.name)
                current = parent
            else:
                break
        
        if path:
            selectors.append(' > '.join(path))
    
    # Return the first selector if any were generated
    return selectors[0] if selectors else None

def _find_label_text(element) -> str:
    """Find the label text for a form element.
    
    Args:
        element: A BeautifulSoup element representing a form field
        
    Returns:
        The label text, or an empty string if none found
    """
    # Check for a label with 'for' attribute matching this element's ID
    if element.has_attr('id'):
        label = element.find_previous('label', attrs={'for': element['id']})
        if label:
            return label.get_text(strip=True)
    
    # Check if the element is wrapped in a label
    parent_label = element.find_parent('label')
    if parent_label:
        # Get text while excluding the text of the element itself
        text_parts = []
        for content in parent_label.contents:
            if content != element and hasattr(content, 'get_text'):
                text_parts.append(content.get_text(strip=True))
            elif isinstance(content, str):
                text_parts.append(content.strip())
        return ' '.join(text_parts).strip()
    
    # Check for a nearby label (preceding element with 'label' or 'form-label' class)
    prev_label = element.find_previous(class_=["label", "form-label", "control-label"])
    if prev_label:
        return prev_label.get_text(strip=True)
    
    # Check for a preceding div with a meaningful class
    prev_div = element.find_previous('div', class_=["label", "form-label", "control-label", "form-group"])
    if prev_div:
        label_candidate = prev_div.find('label')
        if label_candidate:
            return label_candidate.get_text(strip=True)
    
    # Check for aria-label attribute
    if element.has_attr('aria-label'):
        return element['aria-label']
    
    # Check for placeholder as fallback
    if element.has_attr('placeholder'):
        return element['placeholder']
    
    return ""

def _get_surrounding_text(element, max_chars: int = 200) -> str:
    """Get surrounding text for context around an element.
    
    Args:
        element: A BeautifulSoup element
        max_chars: Maximum characters to return
        
    Returns:
        A string containing relevant surrounding text
    """
    # Start with the parent element
    parent = element.parent
    if not parent or parent.name == '[document]':
        return ""
    
    # Get text from siblings and parent, excluding the element itself
    text_parts = []
    
    # Try to get text from a container with a form-related class
    form_container = element.find_parent(['div', 'fieldset'], class_=["form-group", "field", "input-group", "question"])
    if form_container:
        # Exclude the element's own text
        for content in form_container.contents:
            if content != element and hasattr(content, 'get_text'):
                text = content.get_text(strip=True)
                if text:
                    text_parts.append(text)
    else:
        # Look at previous siblings for context
        prev_sibling = element.previous_sibling
        while prev_sibling and len(' '.join(text_parts)) < max_chars / 2:
            if hasattr(prev_sibling, 'get_text'):
                text = prev_sibling.get_text(strip=True)
                if text:
                    text_parts.insert(0, text)
            elif isinstance(prev_sibling, str) and prev_sibling.strip():
                text_parts.insert(0, prev_sibling.strip())
            prev_sibling = prev_sibling.previous_sibling
        
        # Add parent's own text (excluding children)
        parent_text = ' '.join(parent.find_all(text=True, recursive=False))
        if parent_text.strip():
            text_parts.append(parent_text.strip())
    
    # Concatenate all parts and limit length
    result = ' '.join(text_parts).strip()
    if len(result) > max_chars:
        result = result[:max_chars] + "..."
    
    return result 