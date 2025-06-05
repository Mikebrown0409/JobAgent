# AgentV0: AI (Gemini/CrewAI) Integration Guidelines

## Principle: AI Augments, It Doesn't Command (Initially)
Use AI for specific, well-defined tasks where its pattern matching or language understanding capabilities provide a clear advantage over simple rules, primarily in mapping and potentially later in error analysis. Avoid using AI for core browser control or execution logic in V0.

## Gemini Usage (`form_mapper.py`)

1.  **Clear Task Definition:** The primary task for Gemini is: "Given this user profile data [keys/values] and these detected form fields [details: label, type, selector, nearby text], provide the best mapping from profile keys to field selectors."
2.  **Context is Key:** Provide Gemini with relevant context for each field:
    *   Visible label text.
    *   `name` and `id` attributes.
    *   HTML element type (`input`, `select`, `textarea`).
    *   Input type attribute (`text`, `email`, `tel`, `file`).
    *   Potentially surrounding text content if the label is missing or ambiguous.
3.  **Structured Input/Output:** Send the request in a structured format (e.g., JSON) and request the response in a predictable format (e.g., JSON mapping `profile_key` to `selector`).
4.  **Rule-Based Pre-processing:** Apply simple, deterministic rules *before* calling Gemini. If "Email" field has `type="email"`, map it directly. Only send ambiguous or unmapped fields to Gemini.
5.  **Log AI Interaction:** Log the exact prompt sent to Gemini, the raw response received, and the final mapping chosen (which might differ if you apply post-processing rules or confidence thresholds).
6.  **No State:** Treat each Gemini call as stateless initially. Don't rely on it remembering previous interactions within the same form.
7.  **Cost/Latency:** Be mindful of API calls. Use Gemini judiciously, primarily when rules fail.

## CrewAI Usage (Optional for V0)

*If* CrewAI is used, keep it extremely simple:

1.  **Minimal Agents:** Define only 2-3 core agents initially:
    *   `FieldScannerAgent`: Wraps `browser_controller.find_basic_fields`.
    *   `MappingAgent`: Wraps `form_mapper.py` logic (rules + Gemini call).
    *   `ExecutionAgent`: Wraps `action_taker.py` logic.
2.  **Simple Process:** Define a sequential `Crew` process: Scan -> Map -> Execute.
3.  **Data Passing:** Pass data explicitly between agents (detected fields list, profile data, mapping dictionary).
4.  **No Complex Orchestration:** Avoid delegation, complex tool usage, or conversational flows between agents in V0. Use CrewAI purely as a structural organizer for the linear V0 workflow.
5.  **Focus:** The goal is *not* to build a complex multi-agent system *yet*. It's to structure the core V0 tasks slightly more formally if `main_v0.py` becomes too procedural. If `main_v0.py` remains clear and manageable, CrewAI might be unnecessary overhead for V0.

## Future AI Integration (Post-MVP)

*   **Error Analysis:** Use Gemini to analyze patterns in `run_log.jsonl` across multiple failed runs to suggest root causes (e.g., "Selector `X` frequently fails on pages with dynamic IDs").
*   **Adaptive Mapping:** Fine-tune mapping prompts based on previous successes/failures for similar fields.
*   **Strategy Selection:** For complex fields (e.g., typeaheads), use Gemini to suggest an *interaction strategy* (e.g., "type slowly", "click exact match", "press down arrow then enter").
*   **Self-Correction:** Agents could potentially propose fixes to their own logic or selectors based on failure analysis (Requires careful implementation).

**V0 Constraint:** Keep AI usage strictly confined to `form_mapper.py` for field mapping assistance. All other logic is explicit Python and Playwright calls.
