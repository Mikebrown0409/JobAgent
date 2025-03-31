#!/usr/bin/env python3
"""
Simple test script to test the model without CrewAI.
"""

import os
import sys
import logging
import asyncio
import json
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure path for import resolution
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('simple_test.log')
    ]
)

logger = logging.getLogger(__name__)

async def run_simple_test():
    """Run a simple test with Google's Generative AI model."""
    
    print("🧪 STARTING SIMPLE TEST")
    
    # Get API key from environment
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        # Fall back to a dummy key for testing - NOT RECOMMENDED FOR PRODUCTION
        api_key = "dummy_key_for_testing"
        print("⚠️ Warning: Using dummy API key. Set GEMINI_API_KEY environment variable for real use.")
    
    # Configure Gemini API
    try:
        genai.configure(api_key=api_key)
        
        # Use a known working model
        model_name = "gemini-2.0-flash"
        print(f"🤖 Using model: {model_name}")
        
        # Create Gemini model
        model = genai.GenerativeModel(model_name, 
                                      generation_config={
                                          "temperature": 0.4,
                                          "top_p": 0.95,
                                          "top_k": 40,
                                          "max_output_tokens": 2048,
                                      })
        
        # Test prompt
        prompt = """
        Analyze the following form fields for a job application:
        
        1. Name (Text input, required)
        2. Email (Email input, required)
        3. Resume (File upload, required)
        4. Cover Letter (File upload, optional)
        5. Experience (Dropdown, required)
        
        Provide a structured JSON response with your analysis of each field including:
        - Field importance (high, medium, low)
        - Mapping strategy
        - Required validation
        """
        
        print(f"Sending prompt to Gemini model...")
        
        # Mock response for testing when API key is not available
        if api_key == "dummy_key_for_testing":
            print("🔄 Using mock response since no API key is available")
            mock_response = {
                "fields": [
                    {
                        "name": "Name",
                        "importance": "high",
                        "mapping_strategy": "Direct mapping from user profile",
                        "validation": "Non-empty string"
                    },
                    {
                        "name": "Email",
                        "importance": "high",
                        "mapping_strategy": "Direct mapping from user profile",
                        "validation": "Valid email format"
                    }
                ]
            }
            response_text = json.dumps(mock_response, indent=2)
        else:
            response = model.generate_content(prompt)
            response_text = response.text if response.text else "No response from model"
        
        print("\n✅ MODEL RESPONSE:\n")
        print(response_text)
        
        # Create results directory
        results_dir = os.path.join(current_dir, "test_results/simple_test")
        os.makedirs(results_dir, exist_ok=True)
        
        # Save response
        results_file = os.path.join(results_dir, "model_response.txt")
        with open(results_file, "w") as f:
            f.write(response_text)
        
        print(f"\n📊 Results saved to {results_file}")
        
        return True
    except Exception as e:
        logger.exception("Error in simple test")
        print(f"❌ Test error: {str(e)}")
        return False

def main():
    """Main entry point."""
    try:
        success = asyncio.run(run_simple_test())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️ Test cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error: {e}")
        logger.exception("Unhandled exception")
        sys.exit(1)

if __name__ == "__main__":
    main() 