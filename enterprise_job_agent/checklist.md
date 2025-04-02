# Enterprise Job Agent - Development Checklist

**Objective:** Build a state-of-the-art AI agent for reliable, automated job applications across diverse platforms.

**Guiding Principle:** Follow `ProjectRules.mdc` - focus on minimal, effective changes and iterative testing.

---

## Completed Milestones

*   **[X] Project Structure:** Core directories (`agents`, `core`, `tests`, `utils`) and entry point (`main.py`) established.
*   **[X] Configuration & Logging:** Setup for command-line arguments, LLM selection (OpenAI, Gemini, Together), API keys, and file/console logging.
*   **[X] CrewAI Integration:** CrewAI framework implemented with distinct agent roles:
    *   `FormAnalyzerAgent`
    *   `ProfileAdapterAgent`
    *   `FieldMapperAgent` (within `CrewManager`)
    *   `ApplicationExecutorAgent`
    *   `SubmissionAgent` (within `CrewManager`)
    *   `ErrorRecoveryAgent`
*   **[X] Basic Browser Control:** `BrowserManager` created for fundamental Playwright tasks (start, navigate, screenshot, basic frame access, basic field filling).
*   **[X] Initial Form Parsing:** `JobExtractor` implemented to perform basic analysis of form elements (`input`, `select`, `textarea`, `button`, `iframe`).
*   **[X] Advanced Frame Concept:** `AdvancedFrameManager` developed for more sophisticated iframe mapping and cross-frame element searching.
*   **[X] Basic Testing:** Initial test files (`test_simple.py`, `test_discord.py`, `test_job_application.py`) created.
*   **[X] LLM Abstraction:** `GeminiWrapper` created for CrewAI compatibility.

---

## Next Steps: Enhancing Robustness and Reliability

This section outlines the key tasks needed to move the agent towards production readiness, addressing the 5 main areas identified in the project review.

### 1. Enhance Web Interaction Robustness (`BrowserManager`)

*Goal: Ensure the agent can reliably interact with complex and non-standard web form elements found in real-world job applications.*

*   [ ] **Implement Custom Dropdown Handler:** Add logic to `BrowserManager` to handle non-`<select>` dropdowns (click-to-open, wait for options, locate by text/fuzzy match, click option, dismiss dropdown).
*   [ ] **Implement Date Picker Handler:** Add logic for common date picker interactions.
*   [ ] **Implement File Upload Handler:** Ensure reliable handling of various file input types and validation.
*   [ ] **Implement Checkbox/Radio Group Handler:** Add logic for accurately selecting options within groups, especially with complex labels or structures.
*   [ ] **Refine Selector Strategy:** Move beyond basic ID/name/class selectors. Integrate more robust Playwright locators (text, relative positioning, attribute filters) potentially guided by LLM analysis.
*   [ ] **Test Interactions:** Create specific tests using `test_job_application.py` or dedicated files for interactions with known complex elements on target sites (e.g., Greenhouse, Workday, Lever).

### 2. Refine Execution Model

*Goal: Ensure the LLM-generated execution plan is reliably parsed, executed, and includes robust error handling during the process.*

*   [ ] **Implement Execution Plan Parser:** Develop the code (likely in `main.py` or `CrewManager`) that reads the JSON output from `ApplicationExecutorAgent` and translates it into sequential `BrowserManager` actions.
*   [ ] **Add In-Execution Error Handling:** Implement try/catch blocks around individual plan steps. On failure, trigger the `ErrorRecoveryAgent` or implement specific retry logic for common issues (e.g., element not found, stale element).
*   [ ] **Validate Execution Logic:** Test the execution loop thoroughly, ensuring correct sequencing, data application, and handling of the `test_mode` flag.
*   [ ] **Evaluate Hybrid Execution:** Consider if specific complex interactions (like dropdowns) should use dedicated Python functions called by the execution loop, rather than relying solely on the LLM plan for low-level details.

### 3. Consolidate Frame Management

*Goal: Simplify the codebase and ensure consistent, reliable handling of iframes.*

*   [ ] **Decision Point:** Choose between `BrowserManager.get_frame` and `AdvancedFrameManager` as the single source of truth for frame handling. The `AdvancedFrameManager` seems more capable.
*   [ ] **Refactor:** Update all code that interacts with frames to use the chosen, consolidated system (likely integrating `AdvancedFrameManager`'s capabilities into or alongside `BrowserManager`).
*   [ ] **Remove Redundancy:** Delete the unused frame management code path.
*   [ ] **Test Frame Interactions:** Verify robust frame identification and interaction, especially on multi-iframe sites (like embedded Greenhouse forms).

### 4. Improve Form Analysis (`JobExtractor`)

*Goal: Increase the accuracy and completeness of the initial form structure analysis.*

*   [ ] **Enhance Element Detection:** Improve `analyze_form` to identify form elements beyond basic tags, potentially looking for ARIA roles or common patterns used in frameworks.
*   [ ] **Improve Label Association:** Implement more robust logic to connect labels to fields, handling complex layouts (e.g., nested divs, labels wrapping inputs).
*   [ ] **Explore LLM-Assisted Analysis:** Experiment with sending snippets of form HTML to the LLM *during* extraction to help identify field purpose, requirements, or type when standard attributes are missing.
*   [ ] **Add Analysis Tests:** Create tests specifically for `JobExtractor` using saved HTML from complex real-world forms.

### 5. Implement Learning/Feedback Loop

*Goal: Enable the agent to learn from past successes and failures to improve future performance.*

*   [ ] **Design Outcome Storage:** Define a simple format/database to log key details of application attempts (URL, success/failure, specific field errors, `ErrorRecoveryAgent` suggestions).
*   [ ] **Integrate Feedback into Mapping:** Explore how stored outcomes (e.g., "mapping X to field Y failed on site Z") can inform future decisions by `ProfileAdapterAgent` or `FieldMapperAgent`.
*   [ ] **Integrate Feedback into Execution:** Consider if patterns of execution errors can adjust strategies (e.g., adding delays, trying alternative selectors).
*   [ ] **Define Strategy:** Start with simple feedback mechanisms (e.g., logging common errors) and iterate towards more complex learning.

---
*Last Updated: (Update date after applying changes)* 