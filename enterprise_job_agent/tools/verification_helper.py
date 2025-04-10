"""Helper class/functions for verifying form interaction outcomes."""

import logging
import difflib
from typing import Optional
from playwright.async_api import Page, Frame
from thefuzz import fuzz # Use thefuzz for potentially better matching

# Import constants using absolute path
from enterprise_job_agent.tools.constants import VERIFICATION_THRESHOLD

logger = logging.getLogger(__name__)

async def verify_selection(frame: Frame, selector: str, expected_value: str, threshold: float = VERIFICATION_THRESHOLD) -> bool:
    """Verify that a dropdown or similar selection was successful.

    Prioritizes checking the input value, then falls back to text content and JS evaluation.
    """
    try:
        # 1. Verify Input Value (Most reliable for inputs/selects)
        if await verify_input_value(frame, selector, expected_value, threshold):
            return True

        # 2. Verify Displayed Text (Fallback for elements showing selection as text)
        element = await frame.query_selector(selector)
        if not element:
            logger.debug(f"VerifySelection: Element {selector} not found for text verification.")
            return False

        displayed_text = await element.text_content()
        if displayed_text:
            displayed_text_lower = displayed_text.strip().lower()
            expected_value_lower = expected_value.lower()
            try:
                similarity = fuzz.ratio(expected_value_lower, displayed_text_lower) / 100.0
            except NameError:
                similarity = difflib.SequenceMatcher(None, expected_value_lower, displayed_text_lower).ratio()

            if similarity >= threshold:
                logger.debug(f"VerifySelection: Displayed text '{displayed_text}' matches '{expected_value}' (Score: {similarity:.3f}, Threshold: {threshold})")
                return True
            else:
                 logger.debug(f"VerifySelection: Displayed text '{displayed_text}' mismatch '{expected_value}' (Score: {similarity:.3f}, Threshold: {threshold})")

        # 3. Try JS Evaluation (For complex widgets or standard selects)
        try:
            selected_value_js = await frame.eval_on_selector(
                selector,
                """(el) => {
                    if (el.tagName === 'SELECT') {
                        const selectedOption = Array.from(el.options).find(o => o.selected);
                        return selectedOption ? (selectedOption.textContent || selectedOption.value) : null;
                    }
                    // Add checks for common custom select patterns if needed
                    // e.g., check data attributes, hidden inputs, aria attributes
                    const dataValue = el.getAttribute('data-value') || el.getAttribute('aria-label');
                    if (dataValue) return dataValue;
                    // Check common text display elements within the component
                    const displayEl = el.querySelector('.selected-text, .selection-display');
                    if (displayEl) return displayEl.textContent;
                    return el.textContent; // Fallback to element's own text
                }""",
                timeout=2000 # Shorter timeout for JS eval
            )

            if selected_value_js:
                selected_value_js_lower = str(selected_value_js).strip().lower()
                expected_value_lower = expected_value.lower()
                try:
                    js_similarity = fuzz.ratio(expected_value_lower, selected_value_js_lower) / 100.0
                except NameError:
                    js_similarity = difflib.SequenceMatcher(None, expected_value_lower, selected_value_js_lower).ratio()

                if js_similarity >= threshold:
                    logger.debug(f"VerifySelection: JS eval found match '{selected_value_js}' for '{expected_value}' (Score: {js_similarity:.3f}, Threshold: {threshold})")
                    return True
                else:
                    logger.debug(f"VerifySelection: JS eval mismatch '{selected_value_js}' vs '{expected_value}' (Score: {js_similarity:.3f}, Threshold: {threshold})")

        except Exception as js_e:
            logger.debug(f"VerifySelection: JS evaluation failed for {selector}: {str(js_e)}")

        # 4. Final Log if all methods failed
        final_value_for_log = await _get_element_value_for_verification(frame, selector)
        logger.warning(f"VerifySelection failed for '{selector}': Expected '{expected_value}', Final value: '{final_value_for_log}'")
        return False

    except Exception as e:
        logger.error(f"VerifySelection: Unexpected error for {selector}: {str(e)}")
        return False

async def verify_input_value(frame_or_page: Page | Frame, selector: str, expected_value: str, threshold: float = VERIFICATION_THRESHOLD) -> bool:
    """Verify the input value of an element against an expected value using fuzzy matching."""
    try:
        current_value = await _get_element_value_for_verification(frame_or_page, selector)
        if current_value is None:
            logger.debug(f"VerifyInputValue: Could not retrieve value for {selector}.")
            return False

        expected_value_lower = expected_value.lower()
        current_value_lower = current_value.lower()

        try:
            similarity = fuzz.ratio(expected_value_lower, current_value_lower) / 100.0
        except NameError:
            logger.warning("VerifyInputValue: 'fuzz' not defined, falling back to difflib.")
            similarity = difflib.SequenceMatcher(None, expected_value_lower, current_value_lower).ratio()

        logger.debug(f"VerifyInputValue: Comparing '{expected_value_lower}' vs '{current_value_lower}' -> Similarity: {similarity:.3f}")

        if similarity >= threshold:
            logger.info(f"VerifyInputValue: Value for {selector} matches '{expected_value}' (Similarity: {similarity:.3f}, Threshold: {threshold})")
            return True
        else:
            logger.debug(f"VerifyInputValue: Match failed for {selector}. Expected='{expected_value}', Got='{current_value}', Score={similarity:.3f}, Threshold={threshold}")
            return False
    except Exception as e:
        logger.error(f"VerifyInputValue: Error during verification for {selector}: {str(e)}")
        return False

async def _get_element_value_for_verification(frame_or_page: Page | Frame, selector: str) -> Optional[str]:
    """Attempts to get the most relevant value (input value or text content) for verification."""
    try:
        element = await frame_or_page.query_selector(selector)
        if not element:
            return None
        # Prioritize input_value as it reflects the actual selected value for inputs/selects
        value = await element.input_value()
        if value is not None:
             return value
        # Fallback to text_content if input_value is None (e.g., for divs displaying selection)
        text = await element.text_content()
        return text.strip() if text else None
    except Exception as e:
         logger.debug(f"_get_element_value: Error getting value for {selector}: {e}")
         return None 