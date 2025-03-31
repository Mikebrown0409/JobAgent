# Job Application Testing

This directory contains tools for testing the Enterprise Job Agent with real job applications in a safe test mode that won't actually submit applications.

## Available Test URLs

The following job applications are available for testing:

1. **Discord**: `https://job-boards.greenhouse.io/discord/jobs/7845336002`
2. **Remote.com**: `https://job-boards.greenhouse.io/remotecom/jobs/6309578003`
3. **Allscripts**: `https://boards.greenhouse.io/embed/job_app?for=allscripts&token=6507210003`

## Test Mode Features

When running in test mode:
- The agent will analyze the job posting and form structure
- All form fields will be identified and categorized
- User profile data will be mapped to appropriate fields
- The agent will simulate filling the form
- Screenshots will be taken of the completed form
- No actual submission will be made

## Test User Profiles

User profiles and documents are stored in the `enterprise_job_agent/test_user/` directory:
- `user_profile.json` - Default user profile
- Resume and cover letter documents

You can create additional profiles in this directory for testing different scenarios.

## Running Tests

### Option 1: Use the unified testing script

This script allows testing any of the predefined job applications:

```bash
# Basic usage
python enterprise_job_agent/test_job_application.py discord

# Show visible browser during test
python enterprise_job_agent/test_job_application.py discord --visible

# Use a custom profile
python enterprise_job_agent/test_job_application.py discord --profile enterprise_job_agent/test_user/custom_profile.json

# For test with more detailed logging
python enterprise_job_agent/test_job_application.py discord --verbose

# Test another job application
python enterprise_job_agent/test_job_application.py remote
python enterprise_job_agent/test_job_application.py allscripts
```

### Option 2: Use the Discord-specific test script

```bash
# Basic usage
python enterprise_job_agent/test_discord.py

# Show visible browser during test
python enterprise_job_agent/test_discord.py --visible

# Use a custom profile
python enterprise_job_agent/test_discord.py --profile enterprise_job_agent/test_user/custom_profile.json
```

### Option 3: Use the main script directly

```bash
# Test with any job URL
python enterprise_job_agent/main.py --job-url "https://job-boards.greenhouse.io/discord/jobs/7845336002" --test --visible
```

## Test Results

Test results are saved to the `enterprise_job_agent/test_results/` directory in a folder named with the job key and timestamp. Each test run creates:

- `results.json`: Complete test results including form analysis, field mappings, and execution details
- `summary.txt`: Overview of the test run with key statistics
- `recovery_info.json` (if errors occurred): Details on any errors and recovery attempts

## Customizing User Profile

The default user profile is loaded from `test_user/user_profile.json`. You can create custom profiles for testing specific scenarios.

## Environment Setup

Make sure you have set up your environment variables:

```bash
# API key for Gemini Flash 2.0
export GEMINI_API_KEY="your_api_key_here"
```

## Common Issues

If you encounter errors during testing:

1. **Browser automation issues**: Try running with `--visible` to see what's happening
2. **Form field mapping failures**: Check if your user profile has all required fields
3. **API rate limits**: Gemini Flash 2.0 has a limit of 60 requests per minute
4. **System permissions**: Ensure your system allows browser automation 