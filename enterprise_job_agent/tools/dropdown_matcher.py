"""Tools for smart dropdown matching and normalization."""

import logging
from typing import Dict, Any, Optional, List, Tuple
from difflib import SequenceMatcher
import re

logger = logging.getLogger(__name__)

class DropdownMatcher:
    """Handles smart matching for dropdown options."""
    
    def __init__(
        self,
        diagnostics_manager=None,
        match_threshold: float = 0.7,
        generate_variants: bool = True
    ):
        """
        Initialize the dropdown matcher.
        
        Args:
            diagnostics_manager: Optional diagnostics manager
            match_threshold: Minimum similarity threshold (0.0 to 1.0)
            generate_variants: Whether to generate text variants for matching
        """
        self.diagnostics_manager = diagnostics_manager
        self.match_threshold = match_threshold
        self.generate_variants = generate_variants
        self.logger = logging.getLogger(__name__)
        
        # Common prefixes to strip for institutions
        self.institution_prefixes = [
            "university of",
            "the university of",
            "college of",
            "institute of",
            "school of"
        ]
        
        # Common location patterns
        self.location_patterns = {
            r"\b([A-Z]{2})\b": "state_code",  # e.g., CA, NY
            r"([^,]+),\s*([A-Z]{2})\b": "city_state",  # e.g., San Francisco, CA
            r"([^,]+),\s*([^,]+)": "city_region"  # e.g., London, UK
        }
    
    def normalize_text(self, text: str) -> str:
        """Basic text normalization."""
        return re.sub(r'\s+', ' ', text.lower().strip())
    
    def generate_text_variants(self, text: str) -> List[str]:
        """
        Generate variants of text for matching.
        
        Args:
            text: Input text
            
        Returns:
            List of text variants
        """
        variants = {text}  # Use set to avoid duplicates
        normalized = self.normalize_text(text)
        variants.add(normalized)
        
        # Generate initials (e.g., "University of California Berkeley" -> "UCB")
        words = normalized.split()
        initials = ''.join(word[0] for word in words if word not in ['of', 'the', 'and'])
        if len(initials) > 1:
            variants.add(initials.upper())
        
        # Strip common prefixes for institutions
        for prefix in self.institution_prefixes:
            if normalized.startswith(prefix):
                stripped = normalized[len(prefix):].strip()
                variants.add(stripped)
                # Also add initials for stripped version
                stripped_words = stripped.split()
                stripped_initials = ''.join(word[0] for word in stripped_words if word not in ['of', 'the', 'and'])
                if len(stripped_initials) > 1:
                    variants.add(stripped_initials.upper())
        
        # Handle location variants
        for pattern, pattern_type in self.location_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if pattern_type == "state_code":
                    variants.add(match.group(1).upper())
                elif pattern_type == "city_state":
                    city, state = match.groups()
                    variants.add(city.strip())
                    variants.add(state.upper())
                elif pattern_type == "city_region":
                    city, region = match.groups()
                    variants.add(city.strip())
                    variants.add(region.strip())
        
        return list(variants)
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using SequenceMatcher."""
        return SequenceMatcher(None, text1, text2).ratio()
    
    def find_best_match(
        self,
        target: str,
        options: List[str],
        field_type: Optional[str] = None
    ) -> Tuple[Optional[str], float]:
        """
        Find the best matching option for the target value.
        
        Args:
            target: Target value to match
            options: List of available options
            field_type: Optional field type hint (e.g., "school", "location")
            
        Returns:
            Tuple of (best_match, similarity_score)
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage("find_match")
        
        try:
            if not options:
                return None, 0.0
            
            # Generate variants for target
            target_variants = (
                self.generate_text_variants(target)
                if self.generate_variants
                else [self.normalize_text(target)]
            )
            
            best_match = None
            best_score = 0.0
            
            # Try each option against all target variants
            for option in options:
                option_variants = (
                    self.generate_text_variants(option)
                    if self.generate_variants
                    else [self.normalize_text(option)]
                )
                
                # Compare all variants
                for target_var in target_variants:
                    for option_var in option_variants:
                        score = self.calculate_similarity(target_var, option_var)
                        if score > best_score:
                            best_score = score
                            best_match = option
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    best_score >= self.match_threshold,
                    details={
                        "target": target,
                        "best_match": best_match,
                        "score": best_score,
                        "threshold": self.match_threshold
                    }
                )
            
            return (best_match, best_score) if best_score >= self.match_threshold else (None, 0.0)
            
        except Exception as e:
            error_msg = f"Error finding match for {target}: {str(e)}"
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(False, error=error_msg)
            self.logger.error(error_msg)
            return None, 0.0
    
    def find_matches(
        self,
        targets: Dict[str, str],
        options: List[str],
        field_type: Optional[str] = None
    ) -> Dict[str, Tuple[Optional[str], float]]:
        """
        Find best matches for multiple target values.
        
        Args:
            targets: Dictionary of field IDs to target values
            options: List of available options
            field_type: Optional field type hint
            
        Returns:
            Dictionary mapping field IDs to (match, score) tuples
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage("find_matches")
        
        results = {}
        for field_id, target in targets.items():
            match, score = self.find_best_match(target, options, field_type)
            results[field_id] = (match, score)
        
        if self.diagnostics_manager:
            matched_count = sum(1 for match, score in results.values() if match is not None)
            self.diagnostics_manager.end_stage(
                matched_count == len(targets),
                details={
                    "total_targets": len(targets),
                    "matched_targets": matched_count,
                    "average_score": sum(score for _, score in results.values()) / len(targets)
                }
            )
        
        return results 