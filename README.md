# Enterprise Job Application Agent

An AI-powered system for automatically applying to job postings using CrewAI, Playwright, and advanced NLP techniques.

## Project Structure

```
enterprise_job_agent/
├── main.py                 # Entry point and CLI interface
├── config.py              # Configuration and environment settings
├── agents/                # AI Agents using CrewAI
│   ├── __init__.py
│   ├── profile_adapter_agent.py    # Adapts user profiles to job requirements
│   ├── form_analyzer_agent.py      # Analyzes form structure and requirements
│   ├── application_executor_agent.py # Executes form filling operations
│   ├── session_manager_agent.py    # Manages application session state
│   └── error_recovery_agent.py     # Handles error recovery
├── core/                  # Core system components
│   ├── __init__.py
│   ├── action_executor.py          # Executes form actions reliably
│   ├── browser_manager.py          # Manages browser sessions and frames
│   ├── crew_manager.py             # Orchestrates AI agent interactions
│   └── diagnostics_manager.py      # Tracks system performance and issues
└── tools/                 # Specialized tools and utilities
    ├── __init__.py
    ├── data_formatter.py          # Formats data for form submission
    ├── dropdown_matcher.py        # Smart dropdown option matching (70% threshold)
    ├── element_selector.py        # Enhanced element selection
    ├── field_identifier.py        # Form field identification
    └── form_interaction.py        # Form interaction utilities

```

## System Workflow

1. **Initialization** (`main.py`):
   - Loads configuration from `config.py`
   - Initializes core managers and tools
   - Sets up logging and diagnostics

2. **Job Application Process**:
   ```mermaid
   graph TD
      A[main.py] --> B[crew_manager.py]
      B --> C[Session Management]
      B --> D[Form Analysis]
      B --> E[Profile Mapping]
      B --> F[Application Execution]
      
      C --> |session_manager_agent.py| G[Manage Session State]
      D --> |form_analyzer_agent.py| H[Analyze Form Structure]
      E --> |profile_adapter_agent.py| I[Map Profile to Fields]
      F --> |application_executor_agent.py| J[Execute Actions]
      
      G --> |browser_manager.py| K[Browser Control]
      H --> |field_identifier.py| L[Identify Fields]
      I --> |data_formatter.py| M[Format Data]
      J --> |action_executor.py| N[Execute Form Actions]
      
      K --> |element_selector.py| O[Select Elements]
      L --> |dropdown_matcher.py| P[Match Dropdowns]
      M --> |form_interaction.py| Q[Form Interactions]
   ```

3. **Core Components**:
   - `crew_manager.py`: Orchestrates AI agents and their tasks
   - `browser_manager.py`: Handles browser automation using Playwright
   - `action_executor.py`: Executes form actions reliably
   - `diagnostics_manager.py`: Monitors performance and errors

4. **Specialized Agents**:
   - `session_manager_agent.py`: Manages application session state and navigation
   - `application_executor_agent.py`: Executes form filling operations
   - `profile_adapter_agent.py`: Adapts user profiles to job requirements
   - `form_analyzer_agent.py`: Analyzes form structure
   - `error_recovery_agent.py`: Handles error recovery

5. **Tools and Utilities**:
   - `field_identifier.py`: Identifies form field types and requirements
   - `dropdown_matcher.py`: Smart matching for dropdown options (70% threshold)
   - `data_formatter.py`: Formats data for form fields
   - `form_interaction.py`: Handles form interactions reliably
   - `element_selector.py`: Enhanced element selection with smart waiting

## Key Features

- Smart form field identification and mapping
- Reliable dropdown option matching (70% threshold)
- Session state management and navigation
- Comprehensive error handling and recovery
- Detailed diagnostics and logging
- Frame-aware browser automation
- Smart waiting and retry mechanisms

## Configuration

Key settings in `config.py`:
- API credentials and endpoints
- Browser settings
- Rate limiting parameters
- Logging configuration
- Dropdown matching threshold (70%)

## Getting Started

### Prerequisites

- Python 3.9+
- A Gemini API key (can be obtained from Google AI Studio)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/enterprise_job_agent.git
   cd enterprise_job_agent
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up your API key:
   ```bash
   export GEMINI_API_KEY="your_api_key_here"
   ```

### Testing

1. Run the integration tests:
   ```bash
   pytest enterprise_job_agent/tests/test_workflow_integration.py -v
   ```

2. Run a test application (will not actually submit):
   ```bash
   python enterprise_job_agent/main.py test --url "https://job-boards.greenhouse.io/discord/jobs/7845336002"
   ```

### Usage

1. Update your profile in `user_profile.json`:
   ```json
   {
     "name": "Your Name",
     "education": "Your University",
     "experience": "Your Experience"
   }
   ```

2. Run with any supported job board:
   ```bash
   python enterprise_job_agent/main.py apply --url "JOB_URL" [--test-mode]
   ```

## Success Metrics

- Completion Rate: 90%+ successful test applications
- Error Recovery: 80%+ recovery from common errors
- Speed: <2 minutes per form (excluding network delays)
- Reliability: Smart matching for dropdowns with 70% threshold

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- CrewAI framework for multi-agent orchestration
- Google Gemini for AI capabilities
- Playwright for browser automation 