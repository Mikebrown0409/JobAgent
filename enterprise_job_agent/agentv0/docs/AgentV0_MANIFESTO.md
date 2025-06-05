# AgentV0 Manifesto: Automate or Die Trying

## Core Mission
Build the simplest possible AI agent (`AgentV0`) that can successfully submit a job application on a **single target platform** (start: Greenhouse) using a basic user profile. Prove the core concept before adding complexity.

## Guiding Principles
1.  **Speed Over Elegance:** Working code now is better than perfect code later. Prioritize rapid iteration and testing on live job forms.
2.  **Simplicity is Paramount:** Start with the absolute minimum components and logic required. Add complexity *only* when forced by observed failures during testing. Avoid over-engineering and premature abstraction.
3.  **Failure is Data:** Every failed run is a lesson. Log meticulously. Analyze failures to determine the *next specific feature or fix*. The `run_log.jsonl` is your primary feedback loop.
4.  **First Principles:** Question every assumption. Do we *really* need that component? Can we achieve the goal more directly?
5.  **Data-Driven Decisions:** Don't guess. Use logs and test results to justify every new feature or architectural change. If it doesn't demonstrably improve success rate on the target platform, don't build it yet.
6.  **Vertical Slice Focus:** Get the *entire* flow working end-to-end for the simplest case first (e.g., text fields only), then expand capabilities (dropdowns, file uploads) incrementally.

## Success Metric
Consistent (>=80%) successful application submissions on 5+ distinct Greenhouse job postings using a standard test profile. Success means the application reaches the confirmation page *without manual intervention*.

## Mindset
Think like a startup in a garage, not a bureaucratic enterprise. Move fast, break things (in testing), learn, adapt, win.
