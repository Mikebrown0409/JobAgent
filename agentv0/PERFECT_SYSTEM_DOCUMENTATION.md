# AgentV0: System Architecture and Operational Guide (Version: Perfect)

## Document Goal
To provide a complete, crystal-clear, and perfectly accurate understanding of the `AgentV0` system for developers, testers, and operators. This document leaves no ambiguity and explains every facet of the system's design, implementation, and operation.

## 1. Introduction
*   **Mission:** Define `AgentV0`'s core purpose – flawless, autonomous job application submission, embodying 100% accuracy and success.
*   **Philosophy:** Emphasize the design principles – perfection, correctness, robustness, adaptability, comprehensive logging, graceful error handling.
*   **Scope:** Target platforms (Greenhouse, Lever, adaptive design for future platforms).

## 2. System Architecture
*   **Visual Diagram:** A clear diagram illustrating all components (`.py` files, `.json`, `.env`) and their primary interactions/data flow.
*   **File Manifest:** List every file in the `AgentV0` directory and subdirectories, providing a one-sentence summary of its role (matching the "perfect prompt" structure).

## 3. Core Component Deep Dive
*(Dedicated section for each `.py` file)*
*   **`main_v0.py` (Orchestrator):** Purpose. Detailed explanation of the main execution flow (argument parsing, setup sequence, loading profile/config, browser launch, navigation, scraping, strategy selection, mapper injection, initial apply click, main processing loop logic, pre-submit steps, final submission attempt, *verified* success check logic via `check_submission_success`, status determination, comprehensive summary logging, cleanup). Key functions explained.
*   **`browser_controller.py` (Playwright Interface):** Purpose. Explanation of browser launch/setup (including specific stealth options). Navigation logic (`navigate_to`). Job detail scraping methods (`scrape_job_details`). Meticulous breakdown of the `check_submission_success` function's verification patterns (text, URL, elements). Browser cleanup (`close_browser`). Necessary helper functions. Emphasis on visibility/readiness checks for all interactions.
*   **`probe_page_structure.py` (DOM Analyzer):** Purpose. Detailed explanation of `probe_page_for_llm` (initial apply click, DOM traversal strategy, element identification criteria, comprehensive context extraction for each element - selector, tag, attributes, label heuristics, role, options, surrounding text, visibility/enabled status). Filtering logic. Exact JSON output format specified. Error handling.
*   **`adaptive_mapper.py` (Data & AI Logic):** Purpose. Breakdown of `AdaptiveFieldMapper`. Detailed explanation of `get_value_for_key` (search order, alias handling via `field_mappings.json`, composite fields, recursion prevention via copied stacks). Full explanation of `_generate_default_value` (default logic rules, AI trigger conditions). Detailed explanation of `_generate_ai_answer` (*including the full Gemini prompt template*, context usage, API interaction, safety settings, error handling). Explanation of `_get_eeo_formatted_value` mapping logic. Key cleaning logic (`re.sub`).
*   **`action_taker.py` (Reliable Actions):** Purpose. Explanation of each action function (`fill_field`, `select_option`, `upload_file`, `click_button`, `check_checkbox`). Detail the underlying Playwright calls, explicit waits, robust error handling (try-except blocks), clear logging, and success/failure return values. Mention inclusion of small random delays.
*   **`config.py` (Configuration):** Purpose. List and explain every constant defined (e.g., `MAX_FIELD_PROCESSING_PASSES`, `LOG_DIR`, `RUN_LOG_FILE`, timeouts, model names). Explain default values.
*   **`utils.py` (Utilities):** Purpose. Explanation of each utility function (`load_profile`, `setup_logging`, `append_log`, `generate_run_id`). Detail the exact logging configuration (levels, handlers, formatters including `JsonlFormatter`).
*   **`strategy_factory.py` (Strategy Selection):** Purpose. Explanation of `get_strategy` logic (platform detection defaulting to 'adaptive', class instantiation).
*   **`strategies/base_strategy.py` (Interface):** Purpose. Explanation of the `BaseApplicationStrategy` abstract class and the precise signature (including type hints) of each abstract method.
*   **`strategies/adaptive_strategy.py` (Core AI Strategy):** Purpose. Detailed breakdown of `find_fields` (probing call, AI mapping call via `_call_gemini_for_fields`, selector validation/correction, excluding processed selectors). Explanation of `_call_gemini_for_fields` (*including the full Gemini prompt template*). Detailed breakdown of `handle_field` logic (type inference, routing to actions/AI snippet execution). Explanation of `_get_ai_interaction_snippet` (*including the full Gemini prompt template with detailed instructions for radio/select*, API call, snippet cleaning/validation, `exec` usage and safety). Explanation of `perform_initial_apply_click` and `perform_pre_submit_steps`.

## 4. Data Structures and Formats
*   **`profile.json` Schema:** Define the complete, expected JSON structure with explanations for each key/section (basics, location, work, education, skills, online_presence, eeo, authorization, custom_questions, preferences, other). Provide example values.
*   **`field_mappings.json` Schema:** Explain the optional `{"alias": "standard_key"}` format.
*   **`probe_page_for_llm` Output:** Define the exact JSON structure (list of element context dictionaries) returned by the page probe, specifying all potential keys.
*   **`run_log.jsonl` Schema:** Define the precise JSON structure for *every* log entry type (run_start, navigation, scrape_details, probe_start, probe_result, field_mapping_start, field_mapping_result, field_attempt, action_success, action_failure, ai_snippet_request, ai_snippet_result, ai_snippet_exec_start, ai_snippet_exec_result, ai_answer_request, ai_answer_result, submit_attempt, submit_result, confirmation_check_start, confirmation_check_result, run_summary). Specify all standard fields (timestamp, level, message, run_id) and event-specific data.

## 5. Execution Flow
*   **End-to-End Walkthrough:** A detailed step-by-step narrative tracing a typical successful application run, explicitly showing how control and data pass between components and functions.
*   **Error Handling Flow:** Illustrate how specific errors (navigation fail, probe fail, mapping fail, action fail, submit fail, confirmation fail, AI API errors) are caught, logged (including specific log messages/structures), and how they impact the final run status.

## 6. AI Integration (Gemini)
*   **Overview:** Explain the specific, distinct roles of Gemini (field-to-selector mapping, interaction snippet generation, open-ended answer generation).
*   **API Key:** How to set `GEMINI_API_KEY` in `.env`.
*   **Mapping (`_call_gemini_for_fields`):** Provide the *exact, complete prompt template* used. Explain expected JSON input/output. Detail error handling.
*   **Interaction (`_get_ai_interaction_snippet`):** Provide the *exact, complete prompt template* used. Explain element context input and Python snippet output. Detail error handling.
*   **Answer Generation (`_generate_ai_answer`):** Provide the *exact, complete prompt template* used. Explain profile/job context input and text output. Detail error handling.
*   **Safety Settings:** List the configured safety settings used for API calls.
*   **Model Selection:** Specify the Gemini model(s) used (e.g., `gemini-1.5-flash`).

## 7. Setup and Operation
*   **Prerequisites:** Required Python version.
*   **Dependencies:** List all required Python packages (`requirements.txt`).
*   **Installation:** Step-by-step instructions (`git clone`, `cd AgentV0`, `python -m venv venv`, `source venv/bin/activate` or `venv\Scripts\activate`, `pip install -r requirements.txt`, Playwright browsers `playwright install`).
*   **Configuration:** How to create and populate `.env`. Explain `config.py` options. How to structure `profile.json`. How to optionally use `field_mappings.json`.
*   **Running the Agent:** Exact command-line syntax for `main_v0.py` with all arguments explained. Example command.

## 8. Logging and Debugging
*   **Log Locations:** Explain the purpose of console output, the detailed run log file in `logs/`, and the structured `run_log.jsonl`.
*   **Interpreting `run_log.jsonl`:** Detailed guide on how to query and analyze the structured log file to understand agent behavior and pinpoint failures. Provide examples of tracing a field interaction or identifying the root cause of a run failure using the log events.
*   **Common Errors:** List common failure points (invalid selectors, element timeouts, unexpected page structure, AI errors, missing profile data, confirmation failures) and specific troubleshooting steps for each.

## 9. Development Practices
*   **Version Control:** Recommended Git workflow (e.g., feature branches, PRs).
*   **Coding Standards:** Adherence to PEP 8. Use of linters (e.g., Flake8, Black) and formatters recommended.
*   **Testing:** Strategy for testing (mention unit/integration tests for utilities/mapper logic, and the primary focus on end-to-end testing via `main_v0.py` against live sites).

## 10. Conclusion
*   Recap of the system's capabilities and its commitment to achieving perfect, autonomous job application submission. 