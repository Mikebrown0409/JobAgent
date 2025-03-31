# Job Application Agent

An AI-powered job application agent that can automatically analyze job postings and generate insights, running entirely on local LLMs using Ollama.

## Features

- Extracts and analyzes job postings to provide insights
- Generates tailored cover letters based on job requirements
- Provides application advice for specific job positions
- Runs entirely locally using Ollama LLMs
- Supports the new gemma3:4b model

## Prerequisites

- Python 3.9+
- Ollama installed (https://ollama.com)
- Virtual environment created with required packages

## Setup

1. Make sure you have Ollama installed:
   - Visit https://ollama.com to download and install

2. Pull the gemma3:4b model:
   ```bash
   ollama pull gemma3:4b
   ```

3. Activate the virtual environment:
   ```bash
   source jobagent_venv/bin/activate
   ```

4. Make sure all dependencies are installed:
   ```bash
   pip install ollama playwright beautifulsoup4 requests python-dotenv pydantic
   ```

5. Install Playwright browsers:
   ```bash
   playwright install
   ```

## Usage

### Standalone Job Analysis Tool

To analyze a job posting without the full crewAI setup:

```bash
python job_agent.py "https://boards.greenhouse.io/your_job_url" --model "gemma3:4b"
```

This will:
1. Extract and analyze the job description
2. Generate a cover letter tailored to the position
3. Provide application advice for the specific job
4. Save all information to a JSON file for review

### Full Application Agent

For the full agent that can handle multiple job applications:

```bash
python run_agent.py --job-url "https://boards.greenhouse.io/your_job_url" --model "gemma3:4b"
```

You can also use the simpler standalone implementation via run_agent.py:

```bash
python run_agent.py --standalone --job-url "https://boards.greenhouse.io/your_job_url" --model "gemma3:4b"
```

For more options and details on the full application agent, please refer to the documentation in the `job_application_agent` directory.

## Test Results

We've successfully tested the application with:

1. **Director of Accounting at Veradigm**  
   URL: https://boards.greenhouse.io/embed/job_app?for=allscripts&token=6507210003  
   Result: Successfully analyzed the job posting, extracted requirements, generated a tailored cover letter, and provided application advice.

Some job boards may have different structures, so results may vary depending on the specific job posting.

## Model Recommendations

For a MacBook Air with 8GB RAM, these models work well:
- `gemma3:4b` (newer model with good performance)
- `gemma:2b` (fastest, uses minimal RAM)
- `mistral:7b` (better performance, uses more RAM)
- `llama3:8b` (best performance, requires most RAM)

## Limitations

- Currently only supports Greenhouse.io job boards
- Processing speed depends on your local hardware
- Limited by the capabilities of the local model being used
- Some job postings might not be properly extracted due to different structures

## Project Structure

- `job_agent.py`: Standalone job analysis tool using Ollama
- `run_agent.py`: Main script for the full job application agent
- `job_application_agent/`: Directory containing the full agent implementation
- `jobagent_venv/`: Virtual environment with installed dependencies 

python main.py --job-url "https://job-boards.greenhouse.io/discord/jobs/7845336002" --test