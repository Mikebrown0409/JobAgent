# AgentV0: Initial Architecture

## Goal
A minimal, flat structure focused on executing the MVP task. Avoid sub-directories and complex class hierarchies initially.

## Proposed Structure (`AgentV0/`)
```
AgentV0/
├── main_v0.py              # Entry point, orchestrates the flow
├── browser_controller.py   # Handles Playwright setup, navigation, basic element finding
├── form_mapper.py          # Maps profile keys to form field selectors (uses rules + Gemini)
├── action_taker.py         # Executes simple Playwright actions (fill, select, upload)
├── profile.json            # Sample user profile data
├── requirements.txt        # Dependencies (playwright, google-generativeai, crewai[optional])
└── run_log.jsonl           # Structured output log (append mode)
```

## Core Components & Responsibilities

1.  **`main_v0.py`**
    *   Parses command-line arguments (URL, profile path).
    *   Initializes `BrowserController`.
    *   Calls `BrowserController` to navigate and find basic fields.
    *   Loads `profile.json`.
    *   Calls `FormMapper` to get the field mappings.
    *   Calls `ActionTaker` sequentially for each mapped field to perform actions.
    *   Handles basic start/end logging to `run_log.jsonl`.
    *   Cleans up browser session.

2.  **`browser_controller.py`**
    *   Contains functions to:
        *   `launch_browser()`: Start Playwright, return page object.
        *   `navigate_to(page, url)`: Go to the target URL.
        *   `find_basic_fields(page)`: Locate `input[type=text/email/tel]`, `select`, `input[type=file]`. Return a list of dictionaries, each containing selector, label text, element type. (Keep selectors simple, e.g., CSS).
        *   `close_browser(browser)`: Shut down Playwright.
    *   *Initially, no complex frame handling. Assume main frame.*

3.  **`form_mapper.py`**
    *   Contains function: `map_profile_to_fields(profile_data, detected_fields)`
    *   Applies simple rule-based matching first (label contains "name", type is "email", etc.).
    *   If rules are insufficient, prepares a prompt for Gemini including profile keys and detected field details (labels, types, selectors).
    *   Parses Gemini's response.
    *   Returns a dictionary mapping profile keys to field selectors (e.g., `{"full_name": "#input_id_1", "email": "[name=email]"}`).
    *   Logs its decisions and confidence.

4.  **`action_taker.py`**
    *   Contains functions like:
        *   `fill_field(page, selector, value)`
        *   `select_option(page, selector, value)` (exact match)
        *   `upload_file(page, selector, file_path)`
        *   `click_button(page, selector)`
    *   Each function attempts the Playwright action and returns `True` on success, `False` on failure (catching basic exceptions).
    *   Logs the action attempt and outcome.

## Data Flow (Simplified)
`main_v0` -> `browser_controller.find_basic_fields` -> `main_v0` -> `form_mapper.map_profile_to_fields` -> `main_v0` -> `action_taker.fill/select/upload` (repeatedly) -> `main_v0` logs final status.

## Dependencies
*   Playwright for browser interaction.
*   `google-generativeai` for Gemini access (in `form_mapper`).
*   CrewAI is *optional* for MVP. If used, `main_v0` might instantiate a simple Crew with agents wrapping `form_mapper` and `action_taker` logic, but keep it minimal.

## Evolution Strategy
*Resist adding new files or classes.* First, try expanding functions within existing files. Only refactor into new modules when a single file becomes unwieldy (>200 lines) or a clear, reusable component emerges *based on proven need*. Add iframe handling to `browser_controller` only when tests fail due to elements in frames. Add fuzzy matching to `action_taker` only when exact `select_option` fails repeatedly.
