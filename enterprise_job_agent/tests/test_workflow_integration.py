"""Tests for verifying workflow integration of all components."""

import pytest
import asyncio
import json
from typing import Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch
from json import JSONEncoder
from google.auth.credentials import Credentials

from enterprise_job_agent.core.crew_manager import JobApplicationCrew
from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.agents.session_manager_agent import SessionManagerAgent
from enterprise_job_agent.agents.application_executor_agent import ApplicationExecutorAgent
from enterprise_job_agent.agents.profile_adapter_agent import ProfileAdapterAgent

# Create mock credentials
class MockCredentials(Credentials):
    def refresh(self, request):
        pass

    def apply(self, headers, token=None):
        headers['Authorization'] = 'Bearer mock-token'
        return headers

# Mock data for testing
MOCK_FORM_DATA = {
    "fields": {
        "name": {
            "type": "text",
            "required": True,
            "label": "Full Name",
            "selector": "#name"
        },
        "education": {
            "type": "select",
            "required": True,
            "label": "University",
            "selector": "#education",
            "options": ["MIT", "Stanford", "UC Berkeley"]
        }
    }
}

MOCK_USER_PROFILE = {
    "name": "John Doe",
    "education": "MIT"
}

MOCK_JOB_DESCRIPTION = "Software Engineer position at Tech Corp"

class MockLLMEncoder(JSONEncoder):
    """Custom JSON encoder for MockLLM objects."""
    def default(self, obj):
        if isinstance(obj, MockLLM):
            return obj.model_dump()
        return super().default(obj)

class MockLLM:
    def __init__(self, *args, **kwargs):
        self._model = "gemini-pro"
        self._api_key = "mock-api-key"
        self._api_base = "mock-api-base"
        self._base_url = "mock-base-url"
        self._provider = "google"
        self._temperature = 0.7
        self._project = "mock-project"

    def __repr__(self):
        """Return a string representation of the mock object."""
        return f"MockLLM(model={self._model})"

    def __str__(self):
        """Return a string representation of the mock object."""
        return self.__repr__()

    def __getattr__(self, name):
        """Handle attribute access for specific attributes."""
        if name in ["model", "api_key", "api_base", "base_url", "provider", "temperature", "project"]:
            return getattr(self, f"_{name}")
        return super().__getattr__(name)

    def model_dump(self):
        """Return a dictionary with only JSON-serializable values."""
        return {
            "model": self._model,
            "api_key": self._api_key,
            "api_base": self._api_base,
            "base_url": self._base_url,
            "provider": self._provider,
            "temperature": self._temperature,
            "project": self._project
        }

    def mock_invoke(self, messages, *args, **kwargs):
        """Mock the invoke method to return structured responses."""
        # Convert messages to a JSON-serializable format
        if isinstance(messages, (list, tuple)):
            messages = [
                {k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                 for k, v in msg.items()}
                for msg in messages
            ]
        
        # Convert kwargs to JSON-serializable format
        kwargs = {
            k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
            for k, v in kwargs.items()
        }

        last_message = messages[-1]["content"] if messages else ""
        
        if "form analysis" in last_message.lower():
            content = json.dumps({
                "fields": {
                    "name": {
                        "type": "TEXT",
                        "required": True,
                        "importance": 0.8,
                        "label": "Full Name"
                    },
                    "education": {
                        "type": "SELECT",
                        "required": True,
                        "importance": 0.8,
                        "label": "University"
                    }
                },
                "analysis": {
                    "field_count": 2,
                    "required_fields": 2,
                    "optional_fields": 0
                }
            })
        elif "profile mapping" in last_message.lower():
            content = json.dumps({
                "mappings": {
                    "name": "John Doe",
                    "education": "MIT"
                },
                "confidence": 0.9
            })
        else:
            content = "Task completed successfully."

        # Return in LiteLLM format
        return {
            "choices": [{
                "message": {
                    "content": content,
                    "role": "assistant"
                }
            }]
        }

    def completion(self, messages=None, *args, **kwargs):
        """Handle completion requests by directly returning mock responses."""
        return self.mock_invoke(messages or [], *args, **kwargs)

    async def acompletion(self, messages=None, *args, **kwargs):
        """Async version of completion."""
        return self.completion(messages, *args, **kwargs)

    def chat(self, messages=None, *args, **kwargs):
        """Alias for completion."""
        return self.completion(messages, *args, **kwargs)

    async def achat(self, messages=None, *args, **kwargs):
        """Async alias for completion."""
        return await self.acompletion(messages, *args, **kwargs)

# Register the custom encoder
json.JSONEncoder.default = MockLLMEncoder().default

@pytest.fixture
def mock_llm():
    """Mock LLM for testing."""
    llm = MagicMock()
    llm.model = "gemini-pro"
    llm.api_key = "mock-api-key"
    llm.api_base = "mock-api-base"
    llm.base_url = "mock-base-url"
    llm.provider = "google"
    llm.temperature = 0.7
    llm.project = "mock-project"
    llm.completion = mock_completion
    llm.acompletion = mock_acompletion
    llm.__str__ = lambda self: f"MockLLM(model={self.model})"
    llm.__repr__ = lambda self: f"MockLLM(model={self.model})"
    llm.model_dump = lambda: {
        "model": llm.model,
        "api_key": llm.api_key,
        "api_base": llm.api_base,
        "base_url": llm.base_url,
        "provider": llm.provider,
        "temperature": llm.temperature,
        "project": llm.project
    }
    
    # Mock LiteLLM's provider resolution
    with patch("litellm.utils.get_llm_provider", return_value=("google", "gemini-pro")), \
         patch("litellm.completion", side_effect=mock_completion), \
         patch("litellm.acompletion", side_effect=mock_acompletion):
        yield llm

@pytest.fixture
def mock_browser_manager():
    """Mock browser manager for testing."""
    mock = MagicMock()
    mock.navigate = AsyncMock()
    mock.get_frame = AsyncMock(return_value=None)
    mock.close = AsyncMock()
    return mock

@pytest.fixture
def mock_diagnostics_manager():
    """Mock diagnostics manager for testing."""
    mock = MagicMock()
    mock.start_stage = MagicMock()
    mock.end_stage = MagicMock()
    mock.log_error = MagicMock()
    return mock

@pytest.fixture
def job_application_crew(mock_llm, mock_browser_manager, mock_diagnostics_manager):
    """Create a job application crew with mock components."""
    return JobApplicationCrew(
        llm=mock_llm,
        browser_manager=mock_browser_manager,
        diagnostics_manager=mock_diagnostics_manager,
        verbose=True
    )

@pytest.fixture(autouse=True)
def mock_google_auth(monkeypatch):
    def mock_default(*args, **kwargs):
        return MockCredentials(), "mock-project"
    monkeypatch.setattr("google.auth.default", mock_default)

def mock_completion(*args, **kwargs):
    """Mock LiteLLM's completion method."""
    messages = kwargs.get("messages", [])
    last_message = messages[-1]["content"] if messages else ""
    
    if "form analysis" in last_message.lower():
        content = {
            "fields": {
                "name": {
                    "type": "TEXT",
                    "required": True,
                    "importance": 0.8,
                    "label": "Full Name"
                },
                "education": {
                    "type": "SELECT",
                    "required": True,
                    "importance": 0.8,
                    "label": "University"
                }
            },
            "analysis": {
                "field_count": 2,
                "required_fields": 2,
                "optional_fields": 0
            }
        }
    elif "profile mapping" in last_message.lower():
        content = {
            "mappings": {
                "name": "John Doe",
                "education": "MIT"
            },
            "confidence": 0.9
        }
    else:
        content = {
            "stages": [
                {
                    "name": "Form Analysis",
                    "status": "completed",
                    "details": "Successfully analyzed form structure"
                }
            ],
            "success": True,
            "message": "Job application process completed successfully"
        }

    return {
        "choices": [{
            "message": {
                "content": json.dumps(content),
                "role": "assistant"
            }
        }],
        "model": "gemini-pro",
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150
        }
    }

async def mock_acompletion(*args, **kwargs):
    """Async version of mock_completion."""
    return mock_completion(*args, **kwargs)

@pytest.mark.asyncio
async def test_workflow_integration(job_application_crew):
    """Test that all components are properly connected and the workflow executes."""

    # Verify all required agents are initialized
    assert isinstance(job_application_crew.session_manager, SessionManagerAgent)
    assert isinstance(job_application_crew.application_executor, ApplicationExecutorAgent)
    assert isinstance(job_application_crew.profile_adapter, ProfileAdapterAgent)

    # Verify core tools are initialized
    assert job_application_crew.action_executor is not None
    assert job_application_crew.dropdown_matcher is not None

    # Test the complete workflow
    result = await job_application_crew.execute_job_application_process(
        form_data=MOCK_FORM_DATA,
        user_profile=MOCK_USER_PROFILE,
        job_description=MOCK_JOB_DESCRIPTION,
        job_url="https://example.com/job"
    )

    # Verify the result structure
    assert isinstance(result, dict)
    assert "success" in result
    assert "stages" in result

@pytest.mark.asyncio
async def test_error_handling(job_application_crew):
    """Test that errors are properly handled and reported."""

    # Simulate a navigation error
    job_application_crew.browser_manager.navigate.side_effect = Exception("Failed to load page")

    result = await job_application_crew.execute_job_application_process(
        form_data=MOCK_FORM_DATA,
        user_profile=MOCK_USER_PROFILE,
        job_description=MOCK_JOB_DESCRIPTION,
        job_url="https://example.com/job"
    )

    # Verify error handling
    assert isinstance(result, dict)
    assert not result["success"]
    assert "error" in result
    assert "Failed to load page" in result["error"]

@pytest.mark.asyncio
async def test_form_analysis(job_application_crew):
    """Test that form analysis is properly performed."""

    # Create a form analysis task
    task = await job_application_crew.create_form_analysis_task(MOCK_FORM_DATA)

    # Verify task creation
    assert task is not None
    assert task.agent == job_application_crew.agents["form_analyzer"]
    assert task.description is not None
    assert task.expected_output is not None

    # Create and run a crew with just this task
    crew = job_application_crew.create_crew()
    crew.tasks = [task]

    # Run the crew
    results = await job_application_crew._run_crew_async(crew)

    # Verify results
    assert len(results) > 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 