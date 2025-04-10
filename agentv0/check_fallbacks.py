#!/usr/bin/env python3

import json
import os
import sys
from adaptive_mapper import AdaptiveFieldMapper

def check_fallbacks(profile_path):
    """
    Check if fallback values are working properly by loading a profile
    and testing a set of common field keys that might be missing.
    """
    print("Checking fallback value generation...")
    
    # Load the profile
    try:
        with open(profile_path, 'r') as f:
            profile_data = json.load(f)
    except Exception as e:
        print(f"Error loading profile from {profile_path}: {e}")
        return
    
    # Initialize the mapper
    mapper = AdaptiveFieldMapper(profile_data)
    
    # List of common field keys to test
    test_fields = [
        # Common job application fields
        {"key": "salary_expectation", "context": "what is your salary expectation"},
        {"key": "notice_period", "context": "what is your notice period"},
        {"key": "how_did_you_hear", "context": "how did you hear about this position"},
        {"key": "salary_requirements", "context": "please share your salary requirements"},
        {"key": "willing_to_relocate", "context": "are you willing to relocate"},
        {"key": "require_sponsorship", "context": "do you require sponsorship"},
        {"key": "authorized_to_work", "context": "are you authorized to work in the United States"},
        
        # EEO fields
        {"key": "gender", "context": "for EEO compliance, please indicate your gender"},
        {"key": "race", "context": "for EEO compliance, please indicate your race or ethnicity"},
        {"key": "veteran_status", "context": "for EEO compliance, please indicate your veteran status"},
        {"key": "disability_status", "context": "for EEO compliance, please indicate your disability status"},
    ]
    
    print("\nTesting fallback value generation for common fields:")
    print("-" * 80)
    print(f"{'Field Key':<30} | {'Context':<35} | {'Fallback Value':<20}")
    print("-" * 80)
    
    for field in test_fields:
        key = field["key"]
        context = field["context"]
        
        # Check if the key exists in the profile
        profile_value = mapper.get_value_for_key(key)
        
        # If not in profile, get fallback value
        if profile_value is None:
            fallback = mapper.generate_fallback_value(key, context)
            status = f"{fallback}"
        else:
            status = f"In profile: {profile_value}"
        
        print(f"{key:<30} | {context[:35]:<35} | {status:<20}")
    
    print("-" * 80)
    print("\nFallback check complete. Make sure values are appropriate for your job applications.")
    print("If any fields are missing fallbacks that should have them, update the AdaptiveFieldMapper class.")

if __name__ == "__main__":
    # Get profile path
    if len(sys.argv) > 1:
        profile_path = sys.argv[1]
    else:
        profile_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profile.json")
    
    check_fallbacks(profile_path) 