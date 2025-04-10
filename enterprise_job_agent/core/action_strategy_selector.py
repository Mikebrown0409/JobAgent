"""Selects the optimal interaction strategy for a given form element using an LLM."""

import logging
import json
import re
import difflib # Add this import
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

# Assuming access to a BaseLLM compatible interface
# from langchain_core.language_models import BaseLLM 

logger = logging.getLogger(__name__)

class ActionStrategySelector:
    """Uses an LLM to determine the best strategy for interacting with a form element."""

    # --- Constants for text processing (moved from DropdownMatcher) ---
    PREFIXES_TO_STRIP = [
        "university of", "the university of", "college of", "institute of", "school of", "the "
    ]
    SUFFIXES_TO_STRIP = [
        " university", " college", " institute", " school"
    ]
    SEPARATORS_TO_NORMALIZE = [",", "-", "–", "/", " at ", " in "]
    STATE_MAP = { # From _get_state_abbreviation
        'alabama': 'al', 'alaska': 'ak', 'arizona': 'az', 'arkansas': 'ar',
        'california': 'ca', 'colorado': 'co', 'connecticut': 'ct', 'delaware': 'de',
        'florida': 'fl', 'georgia': 'ga', 'hawaii': 'hi', 'idaho': 'id',
        'illinois': 'il', 'indiana': 'in', 'iowa': 'ia', 'kansas': 'ks',
        'kentucky': 'ky', 'louisiana': 'la', 'maine': 'me', 'maryland': 'md',
        'massachusetts': 'ma', 'michigan': 'mi', 'minnesota': 'mn', 'mississippi': 'ms',
        'missouri': 'mo', 'montana': 'mt', 'nebraska': 'ne', 'nevada': 'nv',
        'new hampshire': 'nh', 'new jersey': 'nj', 'new mexico': 'nm', 'new york': 'ny',
        'north carolina': 'nc', 'north dakota': 'nd', 'ohio': 'oh', 'oklahoma': 'ok',
        'oregon': 'or', 'pennsylvania': 'pa', 'rhode island': 'ri', 'south carolina': 'sc',
        'south dakota': 'sd', 'tennessee': 'tn', 'texas': 'tx', 'utah': 'ut',
        'vermont': 'vt', 'virginia': 'va', 'washington': 'wa', 'west virginia': 'wv',
        'wisconsin': 'wi', 'wyoming': 'wy',
        # Add territories/districts if needed
        'district of columbia': 'dc', 'puerto rico': 'pr'
    }
    # --- End Constants ---

    def __init__(self, llm: Any, diagnostics_manager: Any):
        """Initialize the strategy selector.
        
        Args:
            llm: An initialized LLM client compatible with the expected interface.
            diagnostics_manager: The diagnostics manager instance.
        """
        if llm is None:
            raise ValueError("LLM instance is required for ActionStrategySelector.")
        self.llm = llm
        self.diagnostics_manager = diagnostics_manager
        self.logger = logger

    async def select_strategy(self, element_data: Dict[str, Any], desired_value: Any) -> Optional[str]:
        """Determines the best interaction strategy for a form element.

        Args:
            element_data: Dictionary containing details about the form element 
                          (must include 'widget_type', 'field_type', 'tag_name', 
                           'selector', 'label_text', potentially 'options').
            desired_value: The value the user wants to input/select.

        Returns:
            A string representing the chosen strategy (e.g., 'fill', 'select_option_by_value'), 
            or None if a strategy cannot be determined.
        """
        if not element_data or not element_data.get('widget_type'):
            self.logger.error("Cannot select strategy: Missing element_data or widget_type.")
            return None

        widget_type = element_data.get('widget_type')
        possible_strategies = self._get_possible_strategies(widget_type)

        if not possible_strategies:
            self.logger.warning(f"No defined strategies for widget_type: {widget_type}. Cannot select strategy.")
            return None

        # Construct the prompt for the LLM
        prompt = self._build_prompt(element_data, desired_value, possible_strategies)
        
        # If prompt building failed (due to bad element_data), fallback immediately
        if prompt is None:
            self.logger.warning(f"Prompt generation failed for widget '{widget_type}'. Falling back to default strategy: {possible_strategies[0]}")
            return possible_strategies[0]

        self.logger.debug(f"Attempting to select strategy for selector: {element_data.get('selector')}, widget: {widget_type}")
        self.logger.debug(f"Prompt for strategy selection:\n{prompt}")

        try:
            # Invoke the LLM 
            # Corrected: Use .call() for CrewAI LLM sync operation
            response = self.llm.call(prompt)
            
            # Parse the response
            chosen_strategy = self._parse_llm_response(response, possible_strategies)

            if chosen_strategy:
                self.logger.info(f"LLM selected strategy: '{chosen_strategy}' for widget '{widget_type}'")
                return chosen_strategy
            else:
                self.logger.warning(f"LLM did not return a valid strategy from the provided list for widget '{widget_type}'. Response: {response}")
                # Fallback? Maybe return the first possible strategy?
                return possible_strategies[0] # Basic fallback for now

        except Exception as e:
            self.logger.error(f"Error invoking LLM for strategy selection: {e}", exc_info=True)
            # Fallback in case of error
            self.logger.warning(f"LLM failed. Falling back to default strategy for widget '{widget_type}': {possible_strategies[0]}")
            return possible_strategies[0]

    def _get_possible_strategies(self, widget_type: str) -> List[str]:
        """Returns a list of possible interaction strategies based on the widget type."""
        strategy_map = {
            # Text Inputs
            "text_input": ["fill", "type_slowly", "clear_and_fill"],
            "email_input": ["fill", "clear_and_fill"],
            "password_input": ["fill", "clear_and_fill"],
            "number_input": ["fill", "clear_and_fill"],
            "tel_input": ["fill", "clear_and_fill"],
            "url_input": ["fill", "clear_and_fill"],
            "date_input": ["fill", "clear_and_fill"],
            # Text Areas
            "text_area": ["fill", "type_slowly", "clear_and_fill"],
            "rich_text_editor": ["fill", "type_slowly", "clear_and_fill"], # May need more nuanced strategies later
            # Standard Select
            "standard_select": ["select_option_by_label", "select_option_by_value", "select_option_by_fuzzy_match"], # Order matters
            # Custom Select / Autocomplete
            "custom_select": ["click_and_select_exact", "click_and_select_fuzzy", "type_and_select_exact", "type_and_select_fuzzy"],
            "autocomplete": ["type_and_select_exact", "type_and_select_fuzzy", "fill_and_confirm", "clear_and_type_and_select"],
            # Checkbox / Radio
            "checkbox": ["check", "uncheck", "click"],
            "radio_button": ["click_by_value", "click_by_label"],
            # File Input (delegation)
            "file_input": ["use_fileupload_handler"], # Special case: delegate back
            # Buttons
            "button": ["click", "js_click", "press_enter"],
            "button_input": ["click", "js_click", "press_enter"]
        }
        return strategy_map.get(widget_type, ["click", "fill"]) # Default fallback

    def _build_prompt(self, element_data: Dict[str, Any], desired_value: Any, possible_strategies: List[str]) -> Optional[str]:
        """Constructs the prompt for the LLM to select an interaction strategy. Returns None if element_data is invalid."""
        # --- Add Check for valid element_data --- 
        if not element_data:
            self.logger.warning("Cannot build strategy selection prompt: element_data is None.")
            return None
        # --- End Check --- 
        
        # Extract relevant details, limiting length
        label = element_data.get('label_text', '')[:100]
        widget = element_data.get('widget_type', 'unknown')
        # Handle case where widget_type itself might be None
        if not widget:
             self.logger.warning(f"Cannot build strategy selection prompt: widget_type is missing in element_data for selector {element_data.get('selector')}")
             return None
             
        tag = element_data.get('tag_name', 'unknown')
        role = element_data.get('role')
        selector = element_data.get('selector', '')[:150]
        html_snippet = element_data.get('html_snippet', '')[:300] # Limit snippet length
        # Safely get options, handle if options key exists but is None
        options_list = element_data.get('options')
        options_sample = str(options_list[:5])[:200] if isinstance(options_list, list) else 'N/A'
        
        # Format the desired value cleanly
        value_str = str(desired_value)[:100]
        
        prompt = f"""You are an expert web automation assistant.
        Given the details of a form element and the desired value, choose the single BEST strategy to interact with it from the provided list.

        Element Details:
        - Widget Type: {widget}
        - HTML Tag: {tag}
        - Role: {role or 'N/A'}
        - Label/Text: {label or 'N/A'}
        - Selector Hint: {selector}
        - HTML Snippet: {html_snippet}
        - Options Sample: {options_sample}

        Desired Value: {value_str}

        Possible Strategies for '{widget}':
        """
        for i, strategy in enumerate(possible_strategies):
            prompt += f"- {strategy}\n"
        
        prompt += f"\nBased on the element details and the desired value, which *single* strategy from the list above is most likely to succeed for interacting with this specific '{widget}'?\n"
        prompt += "Respond ONLY with the name of the chosen strategy from the list.\n"
        prompt += "Example Response: fill\n"
        prompt += "Chosen Strategy:"
        
        return prompt

    def _parse_llm_response(self, response: Any, possible_strategies: List[str]) -> Optional[str]:
        """Parses the LLM response to extract the chosen strategy.
        
        Args:
            response: The raw response from the LLM.
            possible_strategies: The list of valid strategies provided to the LLM.
        
        Returns:
            The validated chosen strategy string, or None if parsing fails.
        """
        # TODO: Implement robust parsing based on expected LLM response format
        # This will depend heavily on how the LLM is invoked (direct call, agent tool, etc.)
        # For now, assume a simple string response containing the strategy name.
        
        if not response:
            self.logger.warning("Received empty response from LLM for strategy selection.")
            return None

        # Assuming response might be a string or have a 'content' attribute like LangChain messages
        if hasattr(response, 'content'):
            response_text = str(response.content).strip()
        else:
            response_text = str(response).strip()

        # Clean the response: remove potential prefixes like "Chosen Strategy:"
        if ":" in response_text:
            response_text = response_text.split(":")[-1].strip()
            
        # Improve parsing: Check for exact match against possible strategies
        for strategy in possible_strategies:
            # Case-insensitive exact match
            if strategy.lower() == response_text.lower():
                self.logger.debug(f"Successfully parsed strategy: {strategy} from response: {response_text}")
                return strategy

        self.logger.warning(f"Could not parse a valid strategy from LLM response: {response_text}. Valid options: {possible_strategies}")
        return None # Return None if no exact match found, let caller handle fallback

    async def find_best_match_semantic(self, desired_value: str, options: List[str], element_context: Optional[Dict[str, Any]] = None, value_variants: Optional[List[str]] = None) -> Optional[str]:
        """Uses the LLM to find the best semantic match for a desired value among options.

        Args:
            desired_value: The target value the user wants to select/enter.
            options: A list of available option strings scraped from the element.
            element_context: Optional dictionary describing the element (tag, attributes, etc.).
            value_variants: Optional list of lexical variants for the desired value.

        Returns:
            The best matching option string from the list, or None if no suitable match is found.
        """
        if not desired_value or not options:
            return None

        # Generate variants only if not provided
        if value_variants is None:
             value_variants = self.generate_text_variants(desired_value, field_type=field_type)

        # Build prompt for LLM
        prompt = self._build_semantic_match_prompt(desired_value, options, value_variants, element_context)
        
        # Add detailed logging before sending to LLM
        self.logger.debug("--- Semantic Match Request ---")
        self.logger.debug(f"Desired Value: {desired_value}")
        self.logger.debug(f"Field Type Hint: {field_type}")
        self.logger.debug(f"Generated Variants: {value_variants}")
        # Log only the first N options to avoid flooding logs
        max_options_to_log = 20
        log_options = options[:max_options_to_log]
        options_truncated = len(options) > max_options_to_log
        self.logger.debug(f"Options Presented ({len(options)} total): {log_options}{'...' if options_truncated else ''}")
        # Consider logging element_context selectively if needed (can be large)
        # self.logger.debug(f"Element Context: {element_context}")
        self.logger.debug("--- End Semantic Match Request ---")

        self.logger.debug(f"Sending semantic match prompt to LLM for value '{desired_value}' against {len(options)} options.") # Old log line replaced by detailed block
        try:
            # Corrected: Use .call() for CrewAI LLM sync operation
            response = self.llm.call(prompt) 
            
            if not response:
                self.logger.warning("Received empty response from LLM for semantic match.")
                return None
                
            # Assuming response might be a string or have a 'content' attribute
            if hasattr(response, 'content'):
                match_text = str(response.content).strip()
            else:
                match_text = str(response).strip()

            # Check if LLM indicated no match
            if match_text == "NO_MATCH_FOUND":
                self.logger.info(f"LLM indicated NO_MATCH_FOUND for '{desired_value}'")
                return None

            # IMPORTANT: Verify the LLM returned one of the actual options provided
            # Use case-insensitive comparison for robustness
            options_lower = {opt.lower(): opt for opt in options}
            if match_text.lower() in options_lower:
                 exact_option = options_lower[match_text.lower()]
                 self.logger.info(f"LLM returned valid semantic match: '{exact_option}' for desired '{desired_value}'")
                 return exact_option
            else:
                 self.logger.warning(f"LLM returned text '{match_text}' which is not in the original options list.")
                 # Maybe try fuzzy matching the response against options here?
                 # For now, return None if it's not an exact match from the list.
                 return None

        except Exception as e:
            self.logger.error(f"Error invoking LLM for semantic match: {e}", exc_info=True)
            return None # Return None on error

    # --- Migrated Text Utility Methods ---

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize text by lowercasing, removing punctuation/accents, and stripping affixes."""
        if not isinstance(text, str) or not text:
            return ""
        
        text = text.lower()
        
        # Normalize separators
        for sep in ActionStrategySelector.SEPARATORS_TO_NORMALIZE:
            text = text.replace(sep, " ")
            
        # Remove common prefixes
        for prefix in ActionStrategySelector.PREFIXES_TO_STRIP:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                
        # Remove common suffixes
        for suffix in ActionStrategySelector.SUFFIXES_TO_STRIP:
            if text.endswith(suffix):
                text = text[:-len(suffix)].strip()
        
        # Remove punctuation (allow spaces, hyphens)
        text = re.sub(r'[^\w\s-]', '', text)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    @staticmethod
    def generate_text_variants(value: str, field_type: Optional[str] = None) -> List[str]:
        """Generate a minimal set of variants based on the input value, focusing on normalization."""
        if not value:
            return []

        variants = set()
        variants.add(value) # Original value
        
        normalized = ActionStrategySelector.normalize_text(value)
        if normalized != value.lower(): # Add normalized only if different (ignoring case)
            variants.add(normalized)
        
        # Basic abbreviation: Initials (e.g., University of California -> uc)
        if field_type == 'school':
            words = normalized.split()
            if len(words) > 1:
                skip_words = ['of', 'the', 'and', 'in', 'at', 'for', 'a', 'an']
                initials = ''.join(w[0] for w in words if w not in skip_words and w)
                if len(initials) >= 2:
                    variants.add(initials)
                    
        # Basic location variants: City only, City+State abbreviation
        if field_type == 'location':
            parts = [p.strip() for p in value.split(',')]
            if len(parts) > 0:
                variants.add(parts[0]) # City only
            if len(parts) > 1:
                state_abbrev = ActionStrategySelector._get_state_abbreviation(parts[1])
                if state_abbrev:
                    variants.add(f"{parts[0]}, {state_abbrev}")
                    variants.add(state_abbrev) # State abbreviation only
                else:
                    variants.add(f"{parts[0]}, {parts[1]}") # City, Original State/Region
                    
        # Basic degree variants: Abbreviations
        if field_type == 'degree':
            if 'bachelor' in normalized: variants.update(['bs','ba'])
            if 'master' in normalized: variants.update(['ms','ma', 'mba'])
            if 'doctor' in normalized or 'phd' in normalized: variants.add('phd')
            if 'associate' in normalized: variants.update(['aa','as'])
            
        # Basic Yes/No variants for demographics
        if field_type == 'demographic':
            if normalized == 'yes': variants.update(['y'])
            if normalized == 'no': variants.update(['n'])
            if normalized == 'prefer not to say': variants.update(['decline', 'na', 'n/a'])

        result = sorted(list(variants), key=len, reverse=True)
        logger.debug(f"Generated {len(result)} simplified variants for '{value}': {result[:5]}...")
        return result
    
    @staticmethod
    def _get_state_abbreviation(state_name: str) -> Optional[str]:
        """Simple mapping for common US state names to abbreviations."""
        normalized_state = state_name.lower().strip()
        return ActionStrategySelector.STATE_MAP.get(normalized_state)

    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        """Calculate similarity between two strings using SequenceMatcher."""
        if not text1 or not text2:
            return 0.0
        # Use SequenceMatcher for fuzzy matching ratio
        return difflib.SequenceMatcher(None, text1, text2).ratio() 