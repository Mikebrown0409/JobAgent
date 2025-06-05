# Job Application Agent 2.0

An AI-powered automated job application system that intelligently applies to job postings across various platforms. This is a completely refactored and cleaned up version with modern architecture, robust error handling, and enhanced AI integration.

## 🚀 Key Features

- **AI-Powered Intelligence**: Uses Google Gemini for intelligent form analysis, field mapping, and error recovery
- **Adaptive Form Filling**: Automatically adapts to different job platforms and form structures
- **Robust Error Handling**: Advanced error recovery with AI-driven alternative strategies
- **Modern Architecture**: Clean, modular design following best practices
- **Comprehensive Logging**: Detailed execution tracking and debugging capabilities
- **Type Safety**: Full type hints and Pydantic validation
- **Async Support**: Efficient asynchronous execution

## 📋 Requirements

- Python 3.8+
- Google Gemini API key
- Chrome/Chromium browser (installed automatically with Playwright)

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd job_application_agent
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Setup environment**
   ```bash
   cp env.example .env
   # Edit .env and add your Google API key
   ```

5. **Create your profile**
   ```bash
   cp data/profiles/sample_profile.json profile.json
   # Edit profile.json with your information
   ```

## 🚀 Quick Start

### Basic Usage

```bash
python main.py --url "https://jobs.example.com/job/123"
```

### With Custom Profile

```bash
python main.py --url "https://greenhouse.io/job/456" --profile my_profile.json
```

### Debug Mode

```bash
python main.py --url "https://lever.co/job/789" --debug --no-headless
```

## 📖 Command Line Options

```
usage: main.py [-h] --url URL [--profile PROFILE] [--headless] [--no-headless]
               [--output-dir OUTPUT_DIR] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
               [--debug] [--config-file CONFIG_FILE]

AI-powered Job Application Agent

required arguments:
  --url URL                     URL of the job posting to apply for

optional arguments:
  --profile PROFILE             Path to the user profile JSON file (default: profile.json)
  --headless                    Run browser in headless mode (no UI)
  --no-headless                 Run browser with visible UI
  --output-dir OUTPUT_DIR       Directory to save execution results (default: results)
  --log-level LEVEL             Set logging level (default: INFO)
  --debug                       Enable debug mode (verbose logging, save screenshots)
  --config-file CONFIG_FILE     Path to configuration file (.env format)
```

## 📁 Project Structure

```
job_application_agent/
├── README.md                     # This file
├── requirements.txt              # Dependencies
├── main.py                       # Main entry point
├── env.example                   # Environment template
├── 
├── core/                         # Core agent implementation
│   ├── agent.py                  # Main agent orchestrator
│   ├── config.py                 # Configuration management
│   ├── llm_service.py            # AI/LLM integration
│   └── memory/                   # State management
│       ├── profile_store.py      # User profile handling
│       └── working_memory.py     # Runtime state
│
├── tools/                        # Tool implementations
│   ├── browser_tool.py           # Browser automation
│   └── registry.py               # Tool registry
│
├── utils/                        # Utility functions
│   └── logging_setup.py          # Logging configuration
│
├── data/                         # Data and profiles
│   └── profiles/                 # Profile templates
│       └── sample_profile.json   # Example profile
│
├── tests/                        # Test suite
├── docs/                         # Documentation
├── logs/                         # Runtime logs
└── results/                      # Execution results
```

## 👤 Profile Configuration

Create a `profile.json` file with your information:

```json
{
  "basics": {
    "name": "Your Name",
    "email": "your.email@example.com",
    "phone": "+1-555-123-4567",
    "location": {
      "city": "San Francisco",
      "region": "CA",
      "country": "US"
    },
    "summary": "Your professional summary...",
    "linkedin": "https://linkedin.com/in/yourprofile",
    "github": "https://github.com/yourusername"
  },
  "work": [
    {
      "company": "Company Name",
      "position": "Your Position",
      "startDate": "2021-01-01",
      "endDate": "Present",
      "summary": "What you did there..."
    }
  ],
  "education": [
    {
      "institution": "University Name",
      "area": "Computer Science",
      "studyType": "Bachelor's",
      "startDate": "2018-09-01",
      "endDate": "2022-05-01"
    }
  ],
  "skills": [
    {
      "name": "Python",
      "level": "Advanced",
      "keywords": ["Django", "Flask", "FastAPI"]
    }
  ]
}
```

## ⚙️ Configuration

The agent uses environment variables for configuration. Key settings:

```bash
# Required
GOOGLE_API_KEY=your_api_key_here

# Browser settings
BROWSER_HEADLESS=true
BROWSER_TIMEOUT=30000

# Agent behavior
MAX_RETRIES=3
ENABLE_ERROR_RECOVERY=true
ENABLE_AI_STRATEGY=true

# Debugging
DEBUG_MODE=false
SAVE_SCREENSHOTS=false
LOG_LEVEL=INFO
```

## 🔍 How It Works

1. **Planning**: AI analyzes the goal and generates an execution plan
2. **Navigation**: Browser navigates to the job posting URL
3. **Analysis**: Page structure is analyzed to identify forms and fields
4. **Mapping**: AI maps your profile data to form fields intelligently
5. **Filling**: Forms are filled using adaptive strategies
6. **Submission**: Application is submitted with verification
7. **Recovery**: If errors occur, AI suggests alternative approaches

## 📊 Results and Logging

- **Execution Results**: Saved as JSON files in the `results/` directory
- **Logs**: Detailed logs saved in the `logs/` directory
- **Screenshots**: Optional screenshots saved on errors (debug mode)
- **Success Metrics**: Detailed execution statistics and error analysis

## 🧪 Testing

Run the test suite:

```bash
pytest tests/
```

Run with coverage:

```bash
pytest tests/ --cov=job_application_agent
```

## 🐛 Troubleshooting

### Common Issues

1. **Browser fails to start**
   - Ensure Playwright is installed: `playwright install chromium`
   - Try running with `--no-headless` to see browser

2. **API errors**
   - Verify your Google API key is correct
   - Check API quotas and billing

3. **Form filling failures**
   - Enable debug mode: `--debug --no-headless`
   - Check logs for specific error details

### Debug Mode

Enable comprehensive debugging:

```bash
python main.py --url "https://example.com/job" --debug --no-headless
```

This will:
- Show browser window
- Enable verbose logging
- Save screenshots on errors
- Save HTML snapshots

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

If you encounter issues:

1. Check the troubleshooting section
2. Review logs in the `logs/` directory
3. Enable debug mode for more details
4. Open an issue with detailed error information

## 🔄 Migration from v1

If you're migrating from the old version:

1. Update your profile to the new JSON schema
2. Install new dependencies
3. Update environment configuration
4. Use the new command line interface

The new version is not backward compatible but provides much better reliability and features.

---

**Note**: This agent is for educational and personal use. Always respect website terms of service and rate limits when using automated tools. 