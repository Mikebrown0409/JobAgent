"""Module for generating variations of text values to improve matching with form options.

This utility helps match user input values with dropdown options by generating 
variations that account for common differences in formatting, abbreviations,
and alternative names.
"""

import re
from typing import List, Set
import logging

logger = logging.getLogger(__name__)

def generate_school_variants(school_name: str) -> List[str]:
    """Generate variations of school names to improve matching.
    
    Args:
        school_name: Original school name to generate variants for
        
    Returns:
        List of variant school names including original
    """
    if not school_name:
        return []
        
    variants = {school_name}  # Use a set to avoid duplicates
    original = school_name
    
    # Lowercase for consistent processing
    school_name = school_name.lower()
    
    # Strip punctuation for more flexible matching
    stripped = re.sub(r'[^\w\s]', '', school_name)
    variants.add(stripped)
    
    # Common prefix/suffix handling
    university_variants = _handle_university_prefix_suffix(school_name)
    variants.update(university_variants)
    
    # State university variations
    state_variants = _handle_state_universities(school_name)
    variants.update(state_variants)
    
    # Abbreviation handling
    abbrev_variants = _generate_abbreviations(school_name)
    variants.update(abbrev_variants)
    
    # Remove empty strings and convert to list
    variants.discard("")
    
    # Add original with proper case back to ensure it's included
    variants.add(original)
    
    return list(variants)

def generate_location_variants(location: str) -> List[str]:
    """Generate variations of location names to improve matching.
    
    Args:
        location: Original location string to generate variants for
        
    Returns:
        List of variant location names including original
    """
    if not location:
        return []
        
    variants = {location}  # Use a set to avoid duplicates
    original = location
    
    # Lowercase for consistent processing
    location = location.lower()
    
    # Strip punctuation for more flexible matching
    stripped = re.sub(r'[^\w\s]', '', location)
    variants.add(stripped)
    
    # Handle US states abbreviations
    state_variants = _handle_state_abbreviations(location)
    variants.update(state_variants)
    
    # Handle city, state format variations
    city_state_variants = _handle_city_state_format(location)
    variants.update(city_state_variants)
    
    # Remove empty strings and convert to list
    variants.discard("")
    
    # Add original with proper case back to ensure it's included
    variants.add(original)
    
    return list(variants)

def generate_answer_variants(value: str, field_type: str = None) -> List[str]:
    """Generate appropriate variants based on the field type.
    
    Args:
        value: Original value to generate variants for
        field_type: Optional field type hint (e.g., 'school', 'location', 'yes_no')
        
    Returns:
        List of variant values including original
    """
    if not value:
        return []
        
    # Default to simple variants if no field type specified
    if not field_type:
        return _generate_simple_variants(value)
        
    field_type = field_type.lower()
    
    # Route to appropriate variant generator
    if field_type in ('school', 'university', 'college', 'education'):
        return generate_school_variants(value)
    elif field_type in ('location', 'city', 'state', 'address'):
        return generate_location_variants(value)
    elif field_type in ('yes_no', 'boolean', 'agreement'):
        return _generate_yes_no_variants(value)
    else:
        # Default to simple variants for unknown field types
        return _generate_simple_variants(value)

def _handle_university_prefix_suffix(name: str) -> Set[str]:
    """Handle variations with 'university of' and similar prefixes/suffixes."""
    variants = set()
    
    # Handle 'University of X' <-> 'X University'
    if name.startswith('university of '):
        # University of California -> California University
        remainder = name[13:].strip()
        variants.add(f"{remainder} university")
        # Also add just the location part
        variants.add(remainder)
    elif name.endswith(' university'):
        # Stanford University -> University of Stanford
        prefix = name[:-11].strip()
        variants.add(f"university of {prefix}")
        # Also add just the location part
        variants.add(prefix)
        
    # Handle 'X College' <-> 'College of X'
    if name.startswith('college of '):
        remainder = name[11:].strip()
        variants.add(f"{remainder} college")
        variants.add(remainder)
    elif name.endswith(' college'):
        prefix = name[:-8].strip()
        variants.add(f"college of {prefix}")
        variants.add(prefix)
        
    return variants

def _handle_state_universities(name: str) -> Set[str]:
    """Handle state university variations."""
    variants = set()
    
    # State University patterns
    state_univ_pattern = r'(.*?)\s+state\s+university'
    match = re.search(state_univ_pattern, name)
    if match:
        state_name = match.group(1).strip()
        variants.add(f"{state_name} state")
        variants.add(f"state university of {state_name}")
        
    # University of [State] patterns
    univ_state_pattern = r'university\s+of\s+(.*?)(?:\s|$)'
    match = re.search(univ_state_pattern, name)
    if match:
        state_name = match.group(1).strip()
        variants.add(state_name)
        variants.add(f"{state_name} university")
        
    return variants

def _generate_abbreviations(name: str) -> Set[str]:
    """Generate common abbreviations for institutions."""
    variants = set()
    
    # Generate initials (e.g., "University of California Berkeley" -> "UCB")
    words = name.split()
    if len(words) >= 2:
        initials = ''.join(word[0] for word in words if word.lower() not in ('of', 'the', 'and', '&'))
        variants.add(initials)
        
    # Handle specific common abbreviations
    common_abbreviations = {
        'university': 'univ',
        'institute': 'inst',
        'technology': 'tech',
        'college': 'coll',
        'national': 'natl',
        'international': 'intl',
        'department': 'dept',
        'association': 'assoc',
    }
    
    for full, abbrev in common_abbreviations.items():
        if full in name:
            variants.add(name.replace(full, abbrev))
            
    return variants

def _handle_state_abbreviations(location: str) -> Set[str]:
    """Handle US state name and abbreviation variations."""
    variants = set()
    
    # Map of state names to abbreviations
    state_map = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
    'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
    'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID',
    'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS',
    'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
    'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS',
    'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV',
    'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
    'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK',
    'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
    'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT',
    'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV',
        'wisconsin': 'WI', 'wyoming': 'WY'
    }
    
    # Also create reverse mapping for full state names
    abbrev_to_state = {v.lower(): k for k, v in state_map.items()}
    
    # Check if location contains a state name and generate variant with abbreviation
    for state_name, abbrev in state_map.items():
        if state_name in location:
            variants.add(location.replace(state_name, abbrev))
            
    # Check if location contains a state abbreviation and generate variant with full name
    for abbrev, state_name in abbrev_to_state.items():
        # Make sure we're matching actual abbreviations, not substrings of words
        abbrev_pattern = r'\b' + re.escape(abbrev) + r'\b'
        if re.search(abbrev_pattern, location, re.IGNORECASE):
            variants.add(re.sub(abbrev_pattern, state_name, location, flags=re.IGNORECASE))

    return variants

def _handle_city_state_format(location: str) -> Set[str]:
    """Handle variations in city, state format."""
    variants = set()
    
    # Check for "City, State" pattern
    city_state_match = re.match(r'(.*?),\s*(.*?)$', location)
    if city_state_match:
        city = city_state_match.group(1).strip()
        state = city_state_match.group(2).strip()
        
        # Add city only variant
        variants.add(city)
        
        # Add state only variant
        variants.add(state)
        
        # Add variant without comma
        variants.add(f"{city} {state}")

    return variants

def _generate_yes_no_variants(value: str) -> List[str]:
    """Generate variations of yes/no answers."""
    value = value.lower().strip()
    
    if value in ('yes', 'y', 'true', 't', '1', 'ok', 'okay', 'agree'):
        return ['yes', 'y', 'true', 't', '1', 'True', 'Yes', 'YES']
    elif value in ('no', 'n', 'false', 'f', '0', 'disagree', 'not'):
        return ['no', 'n', 'false', 'f', '0', 'False', 'No', 'NO']
    else:
        return [value]  # Return original if not recognized
        
def _generate_simple_variants(value: str) -> List[str]:
    """Generate simple variants like case changes and punctuation removal."""
    if not value:
        return []
        
    variants = {value}  # Original
    
    # Case variations
    variants.add(value.lower())
    variants.add(value.upper())
    variants.add(value.capitalize())
    
    # Remove punctuation
    stripped = re.sub(r'[^\w\s]', '', value)
    variants.add(stripped)
    
    # Remove empty strings
    variants.discard("")

    return list(variants) 