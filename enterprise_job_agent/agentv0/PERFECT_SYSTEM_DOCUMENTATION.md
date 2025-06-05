# AgentV0: System Architecture and Operational Guide (Revised Draft)

## Document Goal
To outline a robust, adaptable, and maintainable architecture for `AgentV0`, enabling reliable web automation, initially focused on job applications, while facilitating future expansion and improvement. This document prioritizes clear component responsibilities, defined interfaces, and best practices in agent design.

## 1. Introduction
*   **Mission:** Develop an intelligent agent capable of autonomously navigating websites and completing complex tasks, starting with accurate and efficient job application submission across various platforms.
*   **Core Philosophy:** Modularity, Separation of Concerns, Robustness, Adaptability, Observability, Testability, Explicit Tool Definitions, Secure & Reliable LLM Integration. Leverage existing libraries and frameworks where beneficial.
*   **Initial Scope:** Target job application platforms (e.g., Greenhouse, Lever, Workday) with an adaptive core design extendable to other web automation tasks.

## 2. Proposed System Architecture

**(Diagram Placeholder: A diagram should illustrate the components below and their primary interactions, emphasizing the flow of control and data, perhaps using a standard agent loop like ReAct or a custom plan-execute model.)**

*   **Orchestrator (`agent_core.py`):** The central brain. Manages the overall task lifecycle (planning, execution, state tracking, error handling). Executes plans by invoking appropriate tools. May implement a reasoning loop (e.g., ReAct: Reason -> Act -> Observe).
*   **Planner (`planner.py`):** (Optional, but recommended for complex tasks) Responsible for breaking down a high-level goal (e.g., "apply to job at URL X using profile Y") into a sequence of actionable steps referencing available tools. Could be LLM-driven or rule-based for simpler flows.
*   **Tool Abstraction Layer / Tool Registry (`tools/base.py`, `tools/registry.py`):** Defines a standard interface for all tools. The Orchestrator interacts with tools *only* through this abstraction. A registry allows dynamic loading/selection of tools.
*   **Tools (`tools/` directory):** Encapsulated capabilities for interacting with the external world or processing data.
    *   **`BrowserTool` (`tools/browser_tool.py`):** The *sole* interface for web browser interactions (using Playwright/Selenium). Exposes high-level, reliable actions like:
        *   `navigate(url: str)`
        *   `find_element(selector: str, timeout: int = 10)`
        *   `click_element(selector: str)`
        *   `fill_text_field(selector: str, text: str)`
        *   `select_dropdown_option(selector: str, option_text: str)`
        *   `upload_file(selector: str, file_path: str)`
        *   `get_text(selector: str) -> str`
        *   `get_html(selector: Optional[str] = None) -> str`
        *   `analyze_page_structure() -> dict`: Invokes the Page Analyzer logic. Returns structured data about forms, fields, buttons.
        *   `check_element_state(selector: str, state: str) -> bool` (e.g., 'visible', 'enabled', 'checked')
        *   `wait_for_navigation()`
        *   `close()`
    *   **`WebSearchTool` (`tools/web_search_tool.py`):** Interface for performing web searches (e.g., using an API like SerpAPI, Google Search).
    *   **(Future Tools):** `FileSystemTool`, `APITool`, `DatabaseTool`, etc.
*   **Memory (`memory/` directory):** Manages state and knowledge.
    *   **`UserProfileStore` (`memory/profile_store.py`):** Loads, validates, and provides access to user profile data (e.g., from `profile.json`). Uses a defined schema (e.g., Pydantic model).
    *   **`WorkingMemory` (`memory/working_memory.py`):** Holds the agent's state *during* a single run: current plan, step results, observations, errors encountered, scratchpad for reasoning.
    *   **`LongTermMemory` (`memory/long_term_memory.py`):** (Optional) Stores persistent knowledge learned across runs (e.g., successful strategies for specific websites, common field mappings, interaction patterns). Could use vector stores or structured databases.
*   **LLM Service (`llm_service.py`):** Centralizes all interactions with Large Language Models (e.g., Gemini). Provides typed inputs/outputs and handles API calls, retries, error handling. Exposes functions like:
    *   `generate_plan(goal: str, available_tools: list) -> Plan`
    *   `choose_next_action(state: WorkingMemory, available_tools: list) -> Action`
    *   `map_profile_to_form(profile_data: dict, form_structure: dict) -> dict`: Takes profile and structured form info (from `BrowserTool.analyze_page_structure`), returns a dictionary mapping *selectors* to *values* or suggests using `generate_text_answer`. **Crucially, does NOT generate interaction code.**
    *   `generate_text_answer(prompt: str, context: dict) -> str`: Generates text for free-form fields based on profile and job context.
*   **Page Analyzer (`page_analyzer.py`):** Logic (potentially invoked by `BrowserTool`) to analyze the current page's DOM. Extracts structured information about forms, input fields (including labels, types, current values, options for selects/radios), buttons, and relevant surrounding text. Aims to provide clean, structured data to the LLM Service or Orchestrator, rather than raw HTML snippets. Handles complexities like iframes or shadow DOMs as needed.
*   **Configuration (`config.py` / `.env`):** Manages all settings (API keys, timeouts, model names, file paths, feature flags). Uses typed settings (e.g., Pydantic's `BaseSettings`) loaded from environment variables and/or config files.
*   **Logging & Observability (`utils/logging_setup.py`):** Configures structured logging (e.g., JSONL to `run_log.jsonl`), integrates with tracing systems (e.g., LangSmith, OpenTelemetry), and potentially gathers metrics.

## 3. Core Component Deep Dive (Illustrative Examples)

*   **Orchestrator (`agent_core.py`):**
    *   Manages the main agent loop (e.g., Plan -> Execute -> Observe -> Update State -> Repeat).
    *   Receives high-level goal. Optionally calls `Planner` to get a `Plan` object.
    *   Iterates through plan steps. For each step:
        *   Identifies the required tool and parameters via `LLMService.choose_next_action` or plan definition.
        *   Invokes the tool via the `ToolRegistry`.
        *   Receives observation/result from the tool.
        *   Updates `WorkingMemory`.
        *   Handles tool errors gracefully (e.g., retry, invoke different tool, ask LLM for alternative, escalate failure).
    *   Determines final success/failure status based on observations and plan completion.
*   **BrowserTool (`tools/browser_tool.py`):**
    *   Initializes and manages the Playwright/Selenium instance.
    *   Implements each high-level action (`click`, `fill`, `scrape`, etc.) using robust browser automation techniques (explicit waits for interactability, error handling for stale elements, retries for common transient issues).
    *   Includes the `analyze_page_structure` method, which processes the DOM (using `Page Analyzer` logic) to return a structured representation (e.g., list of dicts for fields, buttons).
*   **LLM Service (`llm_service.py`):**
    *   Provides clear functions for specific LLM tasks (planning, action selection, data mapping, text generation).
    *   Constructs specific prompts tailored to each task, incorporating relevant context from `WorkingMemory`, `UserProfileStore`, and `Page Analyzer` results.
    *   Parses LLM responses, validates structure (e.g., expecting JSON for mappings), and handles API errors.
    *   **Crucially:** For form filling, the `map_profile_to_form` function should return data like `{'selector': '#first_name', 'value': 'John'}` or `{'selector': 'textarea[name=\"cover_letter\"]', 'action': 'generate_text_answer', 'prompt': 'Generate cover letter...'}`. The Orchestrator then uses this data to call the appropriate `BrowserTool` methods (`fill_text_field`, etc.) or invoke `generate_text_answer`. **Avoids generating and `exec`ing Python snippets.**
*   **Page Analyzer (`page_analyzer.py`):**
    *   Contains logic to parse DOM (obtained via `BrowserTool.get_html()`).
    *   Identifies form elements, heuristics for labels, types (text, email, select, radio, checkbox, textarea, file), options, required status, visibility, etc.
    *   Returns a structured format (e.g., JSON) suitable for the `LLMService.map_profile_to_form` function. Aims to abstract away raw HTML details.

## 4. Data Structures and Formats (Examples)
*   **`profile.json` / `ProfileModel`:** Defined using Pydantic for validation. Structure similar to before but strictly enforced.
*   **`Plan` Object:** Could be a list of `PlanStep` objects, where each step defines `tool_name`, `parameters`, `goal`.
*   **`PageAnalysisResult` (Output of `analyze_page_structure`):** e.g., `[{'selector': '#first_name', 'label': 'First Name', 'type': 'text', 'required': True}, {'selector': 'select#country', 'label': 'Country', 'type': 'select', 'options': ['USA', 'Canada'], 'required': True}, ...]`.
*   **`FieldMappingResult` (Output of `map_profile_to_form`):** e.g., `[{'selector': '#first_name', 'value': 'John'}, {'selector': 'select#country', 'value': 'USA'}, {'selector': '#custom_q1', 'action': 'generate_text_answer', 'prompt': 'Why do you want to work here?'}]`.
*   **`run_log.jsonl` Schema:** Define precise JSON structures for events like `run_start`, `plan_generated`, `action_start`, `action_end` (with tool name, params, result/error), `observation_received`, `llm_request`, `llm_response`, `memory_update`, `run_end`. Include tracing IDs.

## 5. Execution Flow Example (Job Application)
1.  **Goal:** Apply to job at `URL` using `profile.json`.
2.  **Orchestrator:** Receives goal. Loads profile via `UserProfileStore`. Initializes `WorkingMemory`.
3.  **(Optional) Planner:** Generates plan: [`navigate(URL)`, `analyze_page()`, `map_fields()`, `fill_mapped_fields()`, `handle_custom_questions()`, `click_submit()`, `verify_confirmation()`]. Stores plan in `WorkingMemory`.
4.  **Orchestrator (Step 1: Navigate):** Selects `BrowserTool.navigate(url=URL)`. Calls tool. Tool executes Playwright navigation. Returns success/failure. Orchestrator updates `WorkingMemory` with observation (current URL, page state).
5.  **Orchestrator (Step 2: Analyze):** Selects `BrowserTool.analyze_page_structure()`. Tool executes analysis logic (`Page Analyzer`). Returns structured form data. Orchestrator updates `WorkingMemory`.
6.  **Orchestrator (Step 3: Map Fields):** Calls `LLMService.map_profile_to_form(profile_data, form_structure)`. LLM Service constructs prompt, calls API, parses response. Returns mapping result (selector-to-value/action). Orchestrator updates `WorkingMemory`.
7.  **Orchestrator (Step 4: Fill Fields):** Iterates through mapping results. For each:
    *   If `value` exists: Calls `BrowserTool.fill_text_field(selector, value)` (or `select_dropdown_option`, etc.).
    *   If `action` is `generate_text_answer`: Calls `LLMService.generate_text_answer(...)`, gets text, then calls `BrowserTool.fill_text_field(selector, generated_text)`.
    *   Updates `WorkingMemory` with success/failure of each fill attempt. Handles errors (e.g., selector not found -> maybe re-analyze page or skip field).
8.  **Orchestrator (Step 5-N):** Continues executing plan steps (handling custom questions, clicking submit via `BrowserTool.click_element`, checking for confirmation text/elements via `BrowserTool.get_text`/`check_element_state`).
9.  **Orchestrator:** Determines final status based on plan execution and verification step. Logs summary. Calls `BrowserTool.close()`.

## 6. AI Integration (LLM Service)
*   **Clear Roles:** LLMs used for planning, understanding natural language, mapping data based on context, generating human-like text – NOT for generating brittle browser interaction code.
*   **API Key:** Managed via `.env` and `Configuration`.
*   **Prompt Engineering:** Prompts are managed within `LLMService`, incorporating task-specific instructions, context from memory/tools, and desired output format (e.g., JSON schema for mapping).
*   **Error Handling:** Robust handling of API errors, timeouts, rate limits, and unexpected/invalid LLM outputs.
*   **Safety/Security:** Avoids `exec` or similar unsafe practices. Input/output sanitization where necessary. Configurable safety settings for LLM API calls.
*   **Model Selection:** Specified in `Configuration`. Allows experimenting with different models (e.g., `gemini-1.5-flash`, `gpt-4o-mini`) via configuration changes.

## 7. Setup and Operation
*   **Prerequisites:** Python version, Git.
*   **Dependencies:** Managed via `requirements.txt` (or `pyproject.toml` with Poetry/PDM). Likely includes frameworks like `langchain`, `crewai` (optional), `playwright`, `pydantic`, `python-dotenv`, LLM client libraries.
*   **Installation:** Standard Python project setup (`venv`, `pip install`). Requires browser binaries (`playwright install`).
*   **Configuration:** Populate `.env` file (API keys, model names, etc.). Review defaults in `config.py`. Structure `profile.json` according to the defined Pydantic model.
*   **Running:** Command-line interface via `agent_core.py` (or a main script) taking goal, profile path, config overrides. Example: `python agent_core.py --goal "Apply to job at https://example.com/job123" --profile profiles/my_profile.json`

## 8. Logging and Debugging
*   **Structured Logs:** Primary source is `run_log.jsonl`. Allows filtering, querying, and reconstructing agent behavior.
*   **Tracing:** Use tools like LangSmith to visualize the flow of calls between Orchestrator, LLM, and Tools. Essential for debugging complex interactions and LLM reasoning.
*   **Browser State:** `BrowserTool` should log critical state changes and actions. Consider saving screenshots or HTML snapshots on error via Playwright's capabilities.
*   **Common Errors:** Focus on debugging tool failures (invalid selectors, timeouts), LLM parsing issues, planning errors, unexpected website structures. Tracing helps pinpoint where the breakdown occurred.

## 9. Development Practices
*   **Version Control:** Standard Git flow (feature branches, PRs, code reviews).
*   **Coding Standards:** PEP 8, typing (MyPy), formatting (Black), linting (Flake8/Ruff).
*   **Testing:**
    *   **Unit Tests:** Critical for `Tools` (mocking browser interactions), `LLMService` (mocking API calls), `Memory` components, `Configuration`, `Page Analyzer` logic.
    *   **Integration Tests:** Verify interactions between Orchestrator, Tools, and LLM Service using mocked external dependencies (browser, LLM API).
    *   **E2E Tests:** Use sparingly against controlled test environments or specifically chosen live sites known for stability. Focus on verifying core end-to-end flows.

## 10. Conclusion
This revised architecture aims for a more robust, maintainable, and extensible `AgentV0`. By embracing modularity, clear tool abstractions, safer LLM integration, and standard agent design patterns, the system is better positioned to handle the complexities of web automation and evolve beyond its initial job application focus. 