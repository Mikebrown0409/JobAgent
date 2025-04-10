# Enterprise Job Agent - Development Checklist

**Objective:** Build a state-of-the-art AI agent for reliable, automated job applications across diverse platforms, capable of adapting to various form structures and edge cases.

**Guiding Principle:** Follow `ProjectRules.mdc` - focus on minimal, effective changes, iterative testing, and **leveraging AI for robust adaptation and decision-making.**

---

## Completed Milestones

*   **[X] Project Structure:** Core directories (`agents`, `core`, `tests`, `tools`) and entry point (`main.py`).
*   **[X] Configuration & Logging:** Setup for arguments, LLM selection, API keys, and logging.
*   **[X] CrewAI Integration:** Basic agent roles established (`FormAnalyzerAgent`, `ProfileAdapterAgent`, `ErrorRecoveryAgent`, etc.) within `CrewManager`.
*   **[X] Basic Browser Control:** `BrowserManager` for core Playwright tasks.
*   **[X] Initial Form Parsing:** Basic analysis of form elements.
*   **[X] Frame Management:** Consolidated frame handling.
*   **[X] Basic Testing:** Initial test files created.
*   **[X] LLM Abstraction:** `GeminiWrapper` for CrewAI.
*   **[X] Interaction Logic:** Initial implementation for text fields, basic selects, clicks, file uploads, and complex dropdowns (within `ActionExecutor`, `FormInteraction`, `DropdownMatcher`).

---

## Analysis Summary & Revised Strategy

**Findings:**
*   **Complexity:** `ActionExecutor` has grown excessively complex (3000+ lines) with deeply nested logic, numerous specialized handlers (Greenhouse, field types), and extensive rule-based fallbacks. This makes maintenance difficult and hinders adaptability.
*   **AI Underutilization:** Core action execution relies heavily on traditional automation (selectors, string matching, hardcoded variants). AI/LLM capabilities are not fully leveraged for dynamic strategy selection, semantic matching in dropdowns/typeaheads, or adaptive error recovery during execution.
*   **Hardcoding:** Reliance on predefined variants (`_generate_school_variants`, etc.) and platform-specific code limits adaptability.

**Revised Strategy:**
1.  **Refactor for Simplicity:** Break down monolithic components like `ActionExecutor` into smaller, manageable modules.
2.  **Deep AI Integration:** Embed AI/LLM decision-making directly into the action execution loop for choosing interaction strategies, performing semantic matching, and handling errors adaptively.
3.  **Iterative Implementation:** Apply changes incrementally, starting with refactoring, then integrating AI for specific actions, testing thoroughly at each stage.

---

## Revised Development Plan

### Phase 1: Refactoring & Foundational Improvements

*Goal: Simplify the core execution logic and improve the quality of information available to the agents.*

*   [X] **Refactor `ActionExecutor`:**
    *   [X] Decomposed `ActionExecutor` into smaller, specialized handlers (e.g., `TextActionHandler`, `SelectActionHandler`, `TypeaheadActionHandler`, `FileUploadHandler`, `ClickActionHandler`).
    *   [X] Centralized common logic (frame retrieval, selector sanitization, basic interaction calls via `FormInteraction`).
    *   [X] Move platform-specific logic (e.g., Greenhouse) into separate strategy modules/classes. *(Implemented for FileUploadHandler using Strategy Pattern)*
*   [X] **Refactor & Remove `DropdownMatcher`:**
    *   [X] Simplify variant generation (`generate_text_variants`, `_add_*_variants`). Rely more on normalization and semantic matching (Phase 2) rather than exhaustive rule-based variants.
    *   [X] Evaluate the effectiveness vs. complexity of the current `learned_patterns` mechanism. *(Removed learned_patterns)*
    *   [X] Replaced all usages with `ActionStrategySelector` and removed the file.
*   [X] **Enhance `FormAnalyzerAgent`:**
    *   [X] Ensure it reliably identifies not just `field_purpose` but also the *widget type* (e.g., standard `<select>`, custom JS dropdown, autocomplete input) by leveraging DOM structure, attributes, and potentially LLM analysis snippets. *(Added widget_type classification via DOM analysis)*
    *   [ ] Improve label association logic for complex layouts. *(Current JS logic seems okay, pending further testing)*
*   [X] **Refine Selector Strategy:**
    *   [X] Implement more robust default selector generation (e.g., using Playwright's best practices, relative locators, text selectors) possibly guided by `FormAnalyzerAgent`'s output. *(Integrated ElementSelector.generate_stable_selector into FormAnalyzerAgent)*

### Phase 2: AI Integration - Core Execution Strategy & Matching

*Goal: Replace complex rule-based logic with AI-driven decision-making for core interactions.*

*   [X] **Implement "Action Strategy Agent/Task":**
    *   [X] Design an LLM agent/task (potentially within `CrewManager` or called by the refactored action handlers) responsible for choosing the *best* interaction method. *(Implemented as ActionStrategySelector helper class)*
    *   [X] Input: Target element details (from `FormAnalyzerAgent`, including widget type), desired value, current context.
    *   [X] Output: Recommended strategy (e.g., "use `fill`", "use `select_option`", "click-scrape-match", "type-select-from-suggestions"). *(Implemented via LLM call in ActionStrategySelector)*
    *   [X] Refined `ActionStrategySelector` implementation (LLM calls, parsing, initialization).
*   [X] **Integrate AI for Select/Typeahead Matching:**
    *   [X] Use the LLM (within the Strategy Agent or a dedicated task) to perform semantic matching between the desired value and scraped dropdown/typeahead options. *(Added find_best_match_semantic to ActionStrategySelector)*
    *   [X] This should reduce reliance on `DropdownMatcher`'s complex variant generation and similarity scoring. *(Replaced DropdownMatcher calls in Select/Typeahead handlers)*
*   [X] **Apply Strategy Agent:**
    *   [X] Modify the refactored `SelectActionHandler` and `TypeaheadActionHandler` to consult the Strategy Agent to determine *how* to perform the selection/typeahead interaction. *(Text, Select, Typeahead handlers now use ActionStrategySelector)*
    *   [ ] Start with select/typeahead, then potentially expand to clicks (e.g., choosing between direct click, JS click, or text-based click).
*   **Refine Interaction Logic for Efficiency & Intelligence:**
    *   [ ] **Prioritize Scraped Options:** Modify `TextActionHandler` to check for `element_data['options']` first. If available, call a new `FormInteraction.select_option_from_list` method to perform matching against the *scraped* list, bypassing the LLM (`ActionStrategySelector`).
    *   [ ] **Implement `FormInteraction.select_option_from_list`:** Create method using `difflib` to match `value` against the provided `available_options`.
    *   [ ] **Conditional LLM Call:** Only call `ActionStrategySelector` if scraped options are *not* available and the widget is complex (e.g., `autocomplete`).
    *   [ ] **Smarter Dynamic Autocomplete:** Refactor `FormInteraction.type_and_select_fuzzy` to use strategic typing (filter live dropdown), match against *visible* options, and make it the primary dynamic selection strategy.
    *   [ ] **Mandatory Dropdown Dismissal:** Add explicit dropdown dismissal (e.g., `frame.press("body", "Escape")`) after successful selections in `FormInteraction` methods.
    *   [ ] **Refactor `FormInteraction.py`:** Consolidate common logic (finding/clicking options, fuzzy matching) into helper methods; move magic numbers (timeouts, thresholds) to config/constants; simplify `_try_click_option` and `_verify_selection`.
    *   [X] **Graceful File Handling:** `FileUploadHandler` returns `True` if `file_path` is empty. *(Added check)*

### Phase 3: AI Integration - Error Recovery & Learning

*Goal: Make error handling more adaptive and enable the system to learn from experience.*

*   [X] **Enhance `ErrorRecoveryAgent`:**
    *   [X] Provide the agent with more context upon failure (error message, relevant DOM snippet, attempted action, current state). *(Context added in _handle_error)*
    *   [X] Enable the agent to use the LLM to analyze the failure and propose *specific, alternative* strategies (e.g., "try different selector", "use keyboard nav", "try JS click") instead of generic retries. *(Recovery plan generated and execution attempted)*
*   [X] **Implement Structured Outcome Logging:**
    *   [X] Define and implement a robust way to log application attempt outcomes (URL, success/fail, field-level errors, strategies used, recovery attempts). Store this data persistently (e.g., file, simple DB). *(Implemented logging to run_outcomes.jsonl)*
*   [X] **Develop Feedback Mechanism:**
    *   [X] Use logged outcomes to refine agent performance. Examples:
        *   Fine-tune prompts for the Strategy Agent or `FormAnalyzerAgent` based on common failures.
        *   Provide examples of past successes/failures as context to agents.
        *   (Advanced) Potentially adjust internal logic/thresholds based on performance patterns.
        * *(Added feedback_suggestions to run_outcomes.jsonl)*

### Phase 4: Testing & Refinement

*Goal: Ensure the refactored and AI-enhanced agent is reliable and performant.*

*   [ ] **Expand Test Coverage:** Create comprehensive tests using `test_job_application.py` and potentially new files for:
    *   Each refactored action handler.
    *   AI-driven strategy selection and matching logic.
    *   Error recovery scenarios.
    *   Real-world forms from target platforms (Greenhouse, Workday, Lever, Ashby, etc.).
*   [ ] **Performance Analysis:** Measure execution time and identify bottlenecks, particularly LLM inference latency. Optimize prompts and interaction flows.
*   [ ] **Reliability Testing:** Run the agent against a diverse set of job applications to assess success rate and identify remaining edge cases.

---
*Last Updated: (Leave blank for now)* 