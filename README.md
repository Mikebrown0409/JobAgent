# Job Application Agent

An AI-powered automated job application system that helps you apply to multiple job postings efficiently.

## Overview

This system uses AI to intelligently identify and fill out job application forms across various job platforms. The agent is designed to adapt to different form layouts and field types, making it more robust than traditional automation scripts that rely on hardcoded selectors.

## Key Features

- **AI-powered field identification**: Uses AI to identify form fields based on their context and labels
- **Adaptive field mapping**: Maps your profile data to the appropriate fields on the form
- **Fallback value generation**: Provides reasonable responses for commonly asked questions not in your profile
- **Batch processing**: Apply to multiple job postings in sequence
- **Detailed logging**: Keeps track of application attempts and results
- **Customizable**: Easily extend to support additional job platforms

## Setup

1. Clone this repository
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create your `profile.json` file with your resume information

## Usage

### Basic Usage

To process all jobs in the jobs.txt file:

```bash
cd agentv0
python process_jobs.py
```

### Command Line Options

The `process_jobs.py` script supports several command line options:

```
usage: process_jobs.py [-h] [--jobs-file JOBS_FILE] [--profile PROFILE] [--headless] [--delay DELAY]
                      [--start-index START_INDEX] [--max-jobs MAX_JOBS] [--retry-failed] [--single-url SINGLE_URL]

Process job applications using main_v0.py

options:
  -h, --help                      show this help message and exit
  --jobs-file JOBS_FILE           Path to the file containing job URLs (default: jobs.txt)
  --profile PROFILE               Path to the profile JSON file (default: profile.json)
  --headless                      Run in headless mode (browser not visible)
  --delay DELAY                   Delay in seconds between processing jobs (default: 5)
  --start-index START_INDEX       Start processing from this index (default: 0)
  --max-jobs MAX_JOBS             Maximum number of jobs to process (default: all)
  --retry-failed                  Retry failed jobs after initial run
  --single-url SINGLE_URL         Process a single URL instead of reading from jobs file
```

### Examples

Process a single job URL:
```bash
python process_jobs.py --single-url "https://jobs.example.com/job/12345"
```

Process jobs in headless mode (browser not visible):
```bash
python process_jobs.py --headless
```

Process 5 jobs starting from the 10th job in the list:
```bash
python process_jobs.py --start-index 10 --max-jobs 5
```

Retry failed jobs automatically:
```bash
python process_jobs.py --retry-failed
```

### Checking Fallback Values

To check what fallback values will be used for common fields:

```bash
python check_fallbacks.py
```

## Project Structure

- `agentv0/main_v0.py` - The main script that orchestrates the job application process
- `agentv0/adaptive_mapper.py` - Maps profile data to form fields and generates fallbacks
- `agentv0/probe_page_structure.py` - Extracts page structure for AI analysis
- `agentv0/strategies/` - Strategy implementations for different job platforms
- `agentv0/process_jobs.py` - Batch processing script for multiple jobs
- `agentv0/check_fallbacks.py` - Utility to check fallback value generation

## Creating Your Profile

Your `profile.json` file should contain your resume information. Here's an example structure:

```json
{
  "basics": {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "123-456-7890",
    "location": {
      "address": "123 Main St",
      "city": "San Francisco",
      "region": "CA",
      "postalCode": "94105",
      "country": "US"
    }
  },
  "work": [
    {
      "company": "Example Corp",
      "position": "Senior Developer",
      "startDate": "2020-01-01",
      "endDate": "Present",
      "summary": "Led development of key features..."
    }
  ],
  "education": [
    {
      "institution": "University of Example",
      "area": "Computer Science",
      "studyType": "Bachelor's",
      "startDate": "2014-09-01",
      "endDate": "2018-05-01"
    }
  ],
  "skills": [
    {
      "name": "JavaScript",
      "level": "Advanced"
    }
  ],
  "languages": [
    {
      "language": "English",
      "fluency": "Native"
    }
  ]
}
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 