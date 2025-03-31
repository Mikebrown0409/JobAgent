# JobAgent

An advanced AI-powered job application agent that automatically fills out and submits job applications.

## Overview

JobAgent is a state-of-the-art AI agent designed to automate the job application process. It leverages a multi-agent architecture using the CrewAI framework and Google's Gemini API to analyze job postings, extract form structures, map user profile data to application fields, and handle the submission process intelligently.

## Features

- **Automated Form Analysis**: Intelligently analyzes job application forms to identify required fields, form structure, and submission requirements.
- **Profile Mapping**: Maps user profile data to application fields with high precision.
- **Test Mode**: Simulates the application process without actually submitting, for testing and verification.
- **Multi-Agent Architecture**: Uses specialized AI agents for different aspects of the job application process.
- **Advanced Error Recovery**: Identifies and recovers from common form submission errors.

## Getting Started

### Prerequisites

- Python 3.9+
- A Gemini API key (can be obtained from Google AI Studio)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Mikebrown0409/JobAgent.git
   cd JobAgent
   ```

2. Create a virtual environment:
   ```bash
   python -m venv jobagent_venv
   source jobagent_venv/bin/activate  # On Windows: jobagent_venv\Scripts\activate
   ```

3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up your API key:
   ```bash
   export GEMINI_API_KEY="your_api_key_here"
   ```

### Usage

1. Update your profile in `enterprise_job_agent/test_user/user_profile.json`

2. Run a test application (will not actually submit):
   ```bash
   python enterprise_job_agent/test_job_application.py discord --visible
   ```

3. Run with any supported job board:
   ```bash
   python enterprise_job_agent/test_job_application.py [job_type] --visible
   ```
   Where `job_type` can be discord, google, microsoft, etc. (see config.py for all supported job boards)

## Configuration

You can customize the agent by modifying the following files:
- `enterprise_job_agent/config.py`: Job URLs and application settings
- `enterprise_job_agent/test_user/user_profile.json`: Your personal profile data

## Project Structure

- `enterprise_job_agent/`: Main package
  - `agents/`: Specialized AI agents
  - `core/`: Core functionality modules
  - `utils/`: Utility functions and helpers
  - `test_job_application.py`: Main test script
  - `main.py`: Core application logic

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- CrewAI framework for multi-agent orchestration
- Google Gemini for AI capabilities
- Playwright for browser automation 