# AgentV0: AI Development Protocol - Build Fast, Learn Faster

## Rule 1: Test First, Test Always
- **Target:** Use **live** Greenhouse job postings for all testing. Static HTML files are insufficient. Pick 5 diverse postings as your initial test suite.
- **Execution:** Every code change MUST be followed by running the agent against the test suite.
- **Goal:** Achieve successful submission on all test URLs.

## Rule 2: Log Everything That Matters
- **Output:** The `run_log.jsonl` file is critical. Every run MUST append structured logs.
- **Content:** Log inputs (URL, profile keys), detected fields (selectors, labels), mapping decisions (which key maps to which selector, *why* - rule or AI, confidence), actions attempted (fill, select, click), action outcomes (success/failure + error message if any), final run status.
- **Analysis:** Failed runs MUST be analyzed primarily through the logs. Identify the *exact point of failure*.

## Rule 3: Failures Dictate Priorities
- **Identify Bottleneck:** What is the *most common* cause of failure across the test suite according to the logs? (e.g., mapping error for 'location', failure to select dropdown option, element not found).
- **Smallest Fix:** Implement the *simplest possible change* to address that specific bottleneck.
    - Mapping error? -> Refine rules in `form_mapper` or improve the Gemini prompt.
    - Select error? -> Check if exact match failed; consider adding simple normalization (lowercase) before trying fuzzy matching.
    - Element not found? -> Improve selector robustness in `browser_controller` or check for iframes.
- **Re-Test:** Immediately run the test suite again. Did the fix work? Did it break something else?

## Rule 4: No Premature Optimization or Abstraction
- **Resist Complexity:** Do NOT add new classes, files, error handling, or features unless a test failure *proves* it is necessary for the MVP.
- **Refactor Later:** If code becomes repetitive or hard to manage *after* achieving MVP success, *then* consider refactoring based on proven patterns.
- **Example:** Don't build a generic `DropdownHandler` class. If `select_option` fails, modify it directly in `action_taker.py` first (e.g., add a try-except or simple text normalization). Only extract if multiple complex dropdown scenarios emerge later.

## Rule 5: Use AI Intelligently, Not Blindly
- **Mapping:** Use Gemini (`form_mapper`) primarily for ambiguous field mappings where simple rules fail. Always log its suggestion and the final chosen mapping.
- **Strategy (Future):** Do NOT use AI for action *strategy* selection in V0. Stick to direct Playwright calls (`fill`, `select_option`).
- **Analysis (Future):** Consider using AI later to *analyze* `run_log.jsonl` patterns to suggest improvements, but the core V0 logic should be explicit.

## Rule 6: Stick to the Stack
- **Core:** Playwright, Python, `google-generativeai`.
- **Optional:** CrewAI for basic orchestration if it simplifies `main_v0`.
- **No New Dependencies:** Do not add other libraries unless fundamentally required and justified by test failures (e.g., a fuzzy matching library if simple normalization fails for dropdowns).

## Workflow Cycle
1. Write/Modify Code (Smallest change possible).
2. Run Test Suite (5+ live Greenhouse URLs).
3. Analyze `run_log.jsonl` for failures.
4. Identify primary bottleneck.
5. Implement smallest fix (Rule 4).
6. Repeat.
