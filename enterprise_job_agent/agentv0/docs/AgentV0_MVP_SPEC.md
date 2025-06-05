# AgentV0: Minimum Viable Product Specification

## Objective
Successfully apply to a job posting on `boards.greenhouse.io` using data from a provided `profile.json`.

## Inputs
1.  `target_url`: A URL pointing to a specific job posting on `boards.greenhouse.io`.
2.  `profile_path`: Path to a `profile.json` file.

## `profile.json` Structure (Initial)
```json
{
  "full_name": "Test User",
  "email": "test@example.com",
  "phone": "123-456-7890",
  "resume_path": "/path/to/dummy_resume.pdf",
  // Add other common fields *only* as required by initial test failures
  "linkedin_url": "https://linkedin.com/in/testuser"
}
```

## Core Functionality (MVP)
1.  **Launch Browser:** Initialize Playwright, navigate to `target_url`.
2.  **Identify Basic Fields:** Detect visible `input[type="text"]`, `input[type="email"]`, `input[type="tel"]`, and `select` elements within the main page content. (Ignore iframes initially unless absolutely necessary for basic info).
3.  **Map Profile to Fields:**
    *   Use a combination of:
        *   Exact label matching (case-insensitive).
        *   Keyword matching in labels/names (e.g., "name", "email", "phone").
        *   Element type hints (e.g., `type="email"`).
    *   Use Gemini (`form_mapper.py`) as a fallback or for confirmation, logging its reasoning.
    *   Log the final mapping decision for each profile key.
4.  **Execute Actions:**
    *   **Text Input:** Fill detected text/email/tel fields using `page.fill()`.
    *   **Select Dropdown:** Select option by *exact text match* using `page.select_option()`.
    *   **File Upload:** Handle basic `input[type="file"]` for the resume using `page.set_input_files()`.
    *   **(Optional MVP Extension):** Basic button click for "Submit" identified by common text patterns ("Submit", "Apply").
5.  **Logging:** Generate `run_log.jsonl` with structured entries for: run start/end, URL, profile used, fields detected, mapping decisions (profile key -> field selector + confidence/reason), actions attempted (fill, select, click) + success/failure status, final run outcome (success/failure + reason).

## Out of Scope for MVP
*   Complex field types (typeahead, rich text, custom widgets).
*   Iframe handling (unless basic info is inside one).
*   Complex dropdown logic (fuzzy matching, dynamic loading).
*   Multi-page forms.
*   Error recovery beyond logging the failure.
*   Sophisticated AI strategy selection.
*   Configuration files (`config.py`). Hardcode initial values.

## Acceptance Criteria
The agent successfully submits applications to >= 5 different Greenhouse job postings without errors, populating at least Name, Email, Phone, and Resume fields correctly, reaching the confirmation step. All actions and mappings must be logged clearly in `run_log.jsonl`.
