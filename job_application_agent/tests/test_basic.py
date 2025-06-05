"""
Basic functionality tests for the Job Application Agent.
"""

import pytest
import asyncio
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch

# Import the components we want to test
from job_application_agent.core.config import Config
from job_application_agent.core.memory.profile_store import ProfileStore
from job_application_agent.core.memory.working_memory import WorkingMemory
from job_application_agent.tools.registry import ToolRegistry
from job_application_agent.agent import EnterpriseJobApplicationAgent


@pytest.fixture
def sample_config():
    """Create a sample configuration for testing."""
    return Config(
        headless=True,
        google_api_key="test_key",
        profile_path="data/profiles/sample_profile.json",
        enable_ai_content=False,  # Disable AI for tests
        enable_semantic_analysis=False
    )


@pytest.fixture
def sample_profile_data():
    """Create sample profile data for testing."""
    return {
        "basics": {
            "name": "John Doe",
            "email": "john.doe@example.com",
            "phone": "+1-555-0123",
            "location": {
                "city": "San Francisco",
                "region": "CA",
                "country": "US",
                "postalCode": "94105"
            },
            "summary": "Experienced software engineer with expertise in Python and web development."
        },
        "work": [
            {
                "company": "Tech Corp",
                "position": "Senior Software Engineer",
                "startDate": "2020-01-01",
                "endDate": "2023-12-31",
                "summary": "Led development of web applications using Python and React."
            }
        ],
        "education": [
            {
                "institution": "University of Technology",
                "area": "Computer Science",
                "studyType": "Bachelor of Science",
                "startDate": "2016-09-01",
                "endDate": "2020-05-31"
            }
        ],
        "skills": [
            {"name": "Python", "level": "Expert"},
            {"name": "JavaScript", "level": "Advanced"},
            {"name": "React", "level": "Advanced"}
        ]
    }


@pytest.fixture
def temp_profile_file(sample_profile_data):
    """Create a temporary profile file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_profile_data, f)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


def test_config_creation(sample_config):
    """Test that configuration can be created and accessed."""
    assert sample_config.headless is True
    assert sample_config.google_api_key == "test_key"
    assert sample_config.profile_path == "data/profiles/sample_profile.json"


def test_config_from_env():
    """Test configuration creation from environment variables."""
    with patch.dict('os.environ', {
        'JOB_AGENT_HEADLESS': 'false',
        'JOB_AGENT_GOOGLE_API_KEY': 'env_test_key',
        'JOB_AGENT_LOG_LEVEL': 'DEBUG'
    }):
        config = Config.from_env()
        assert config.headless is False
        assert config.google_api_key == 'env_test_key'
        assert config.log_level == 'DEBUG'


def test_profile_store_loading(temp_profile_file, sample_profile_data):
    """Test that profile store can load and access profile data."""
    profile_store = ProfileStore(temp_profile_file)
    
    # Test basic access methods
    assert profile_store.get_name() == "John Doe"
    assert profile_store.get_email() == "john.doe@example.com"
    assert profile_store.get_phone() == "+1-555-0123"
    
    # Test location data
    location = profile_store.get_location()
    assert location['city'] == "San Francisco"
    assert location['region'] == "CA"
    
    # Test work experience
    work = profile_store.get_work_experience()
    assert len(work) == 1
    assert work[0]['company'] == "Tech Corp"
    
    # Test education
    education = profile_store.get_education()
    assert len(education) == 1
    assert education[0]['institution'] == "University of Technology"


def test_working_memory():
    """Test working memory functionality."""
    memory = WorkingMemory()
    
    # Test setting and getting context
    memory.set_context('test_key', 'test_value')
    assert memory.get_context('test_key') == 'test_value'
    
    # Test clearing memory
    memory.clear()
    assert memory.get_context('test_key') is None


def test_tool_registry():
    """Test tool registry functionality."""
    registry = ToolRegistry()
    
    # Test registering a tool
    mock_tool = Mock()
    registry.register_tool('test_tool', mock_tool)
    
    # Test getting a tool
    retrieved_tool = registry.get_tool('test_tool')
    assert retrieved_tool == mock_tool
    
    # Test listing tools
    tools = registry.list_tools()
    assert 'test_tool' in tools


@pytest.mark.asyncio
async def test_agent_initialization(sample_config, temp_profile_file):
    """Test that the agent can be initialized properly."""
    # Update config to use temp profile
    sample_config.profile_path = temp_profile_file
    
    agent = EnterpriseJobApplicationAgent(sample_config)
    
    # Test that components are initialized
    assert agent.config == sample_config
    assert agent.profile_store is not None
    assert agent.working_memory is not None
    assert agent.browser_tool is not None
    assert agent.tool_registry is not None
    
    # Test that tools are registered
    tools = agent.tool_registry.list_tools()
    expected_tools = ['navigate', 'analyze_page', 'fill_application', 'submit_application', 'verify_submission']
    for tool in expected_tools:
        assert tool in tools
    
    # Cleanup
    await agent.close()


def test_config_validation():
    """Test configuration validation."""
    # Test valid temperature
    config = Config(llm_temperature=0.5)
    assert config.llm_temperature == 0.5
    
    # Test invalid temperature should raise error
    with pytest.raises(ValueError):
        Config(llm_temperature=3.0)
    
    # Test valid log level
    config = Config(log_level="INFO")
    assert config.log_level == "INFO"
    
    # Test invalid log level should raise error
    with pytest.raises(ValueError):
        Config(log_level="INVALID")


if __name__ == "__main__":
    pytest.main([__file__]) 