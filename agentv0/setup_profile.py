#!/usr/bin/env python3

import json
import os
import sys
from datetime import datetime

def generate_profile_template():
    """Generate an empty profile template with all required fields."""
    return {
        "basics": {
            "name": "",
            "email": "",
            "phone": "",
            "website": "",
            "summary": "",
            "location": {
                "address": "",
                "city": "",
                "region": "",
                "postalCode": "",
                "country": ""
            }
        },
        "work": [
            {
                "company": "",
                "position": "",
                "website": "",
                "startDate": "",
                "endDate": "",
                "summary": "",
                "highlights": []
            }
        ],
        "education": [
            {
                "institution": "",
                "area": "",
                "studyType": "",
                "startDate": "",
                "endDate": "",
                "gpa": "",
                "courses": []
            }
        ],
        "skills": [
            {
                "name": "",
                "level": "",
                "keywords": []
            }
        ],
        "languages": [
            {
                "language": "",
                "fluency": ""
            }
        ],
        "interests": [
            {
                "name": "",
                "keywords": []
            }
        ],
        "references": [
            {
                "name": "",
                "reference": ""
            }
        ],
        "custom_fields": {
            "linkedin": "",
            "github": "",
            "work_authorization_us": "",
            "visa_sponsorship_required": "",
            "salary_expectation": "",
            "notice_period": "",
            "how_did_you_hear": "",
            "willing_to_relocate": ""
        }
    }

def prompt_basic_info():
    """Prompt for basic information and return a profile dict."""
    profile = generate_profile_template()
    
    print("\n--- Basic Information ---")
    profile["basics"]["name"] = input("Full Name: ").strip()
    profile["basics"]["email"] = input("Email: ").strip()
    profile["basics"]["phone"] = input("Phone: ").strip()
    profile["basics"]["website"] = input("Website (optional): ").strip()
    
    print("\n--- Location ---")
    profile["basics"]["location"]["address"] = input("Address: ").strip()
    profile["basics"]["location"]["city"] = input("City: ").strip()
    profile["basics"]["location"]["region"] = input("State/Province: ").strip()
    profile["basics"]["location"]["postalCode"] = input("Postal Code: ").strip()
    profile["basics"]["location"]["country"] = input("Country: ").strip()
    
    print("\n--- Professional Summary ---")
    profile["basics"]["summary"] = input("Brief Professional Summary: ").strip()
    
    return profile

def prompt_work_experience(profile):
    """Prompt for work experience and add to profile."""
    print("\n--- Work Experience ---")
    profile["work"] = []
    
    add_more = True
    while add_more:
        job = {}
        print("\nEnter work experience (most recent first):")
        job["company"] = input("Company Name: ").strip()
        job["position"] = input("Position Title: ").strip()
        job["website"] = input("Company Website (optional): ").strip()
        job["startDate"] = input("Start Date (YYYY-MM-DD): ").strip()
        job["endDate"] = input("End Date (YYYY-MM-DD or 'Present'): ").strip()
        job["summary"] = input("Job Description: ").strip()
        
        # Add highlights (achievements/responsibilities)
        highlights = []
        print("Enter key achievements/responsibilities (leave blank to finish):")
        while True:
            highlight = input("- ").strip()
            if not highlight:
                break
            highlights.append(highlight)
        job["highlights"] = highlights
        
        profile["work"].append(job)
        
        add_more = input("\nAdd another work experience? (y/n): ").lower().startswith('y')
    
    return profile

def prompt_education(profile):
    """Prompt for education and add to profile."""
    print("\n--- Education ---")
    profile["education"] = []
    
    add_more = True
    while add_more:
        edu = {}
        print("\nEnter education (most recent first):")
        edu["institution"] = input("Institution Name: ").strip()
        edu["area"] = input("Field of Study/Major: ").strip()
        edu["studyType"] = input("Degree (e.g., Bachelor's, Master's): ").strip()
        edu["startDate"] = input("Start Date (YYYY-MM-DD): ").strip()
        edu["endDate"] = input("End Date (YYYY-MM-DD or 'Present'): ").strip()
        edu["gpa"] = input("GPA (optional): ").strip()
        
        # Add courses
        courses = []
        print("Enter relevant courses (leave blank to finish):")
        while True:
            course = input("- ").strip()
            if not course:
                break
            courses.append(course)
        edu["courses"] = courses
        
        profile["education"].append(edu)
        
        add_more = input("\nAdd another education entry? (y/n): ").lower().startswith('y')
    
    return profile

def prompt_skills(profile):
    """Prompt for skills and add to profile."""
    print("\n--- Skills ---")
    profile["skills"] = []
    
    add_more = True
    while add_more:
        skill = {}
        print("\nEnter a skill:")
        skill["name"] = input("Skill Name: ").strip()
        skill["level"] = input("Proficiency Level (e.g., Beginner, Intermediate, Advanced): ").strip()
        
        # Add keywords
        keywords = []
        print("Enter related keywords or tools (leave blank to finish):")
        while True:
            keyword = input("- ").strip()
            if not keyword:
                break
            keywords.append(keyword)
        skill["keywords"] = keywords
        
        profile["skills"].append(skill)
        
        add_more = input("\nAdd another skill? (y/n): ").lower().startswith('y')
    
    return profile

def prompt_languages(profile):
    """Prompt for languages and add to profile."""
    print("\n--- Languages ---")
    profile["languages"] = []
    
    add_more = True
    while add_more:
        lang = {}
        print("\nEnter a language:")
        lang["language"] = input("Language: ").strip()
        lang["fluency"] = input("Fluency (e.g., Native, Fluent, Intermediate, Basic): ").strip()
        
        profile["languages"].append(lang)
        
        add_more = input("\nAdd another language? (y/n): ").lower().startswith('y')
    
    return profile

def prompt_custom_fields(profile):
    """Prompt for custom fields commonly needed in job applications."""
    print("\n--- Additional Job Application Information ---")
    
    profile["custom_fields"]["linkedin"] = input("LinkedIn Profile URL: ").strip()
    profile["custom_fields"]["github"] = input("GitHub Profile URL: ").strip()
    
    auth = input("Are you authorized to work in the United States? (yes/no): ").strip().lower()
    profile["custom_fields"]["work_authorization_us"] = "yes" if auth.startswith('y') else "no"
    
    sponsor = input("Do you require visa sponsorship? (yes/no): ").strip().lower()
    profile["custom_fields"]["visa_sponsorship_required"] = "yes" if sponsor.startswith('y') else "no"
    
    profile["custom_fields"]["salary_expectation"] = input("Salary Expectation: ").strip()
    profile["custom_fields"]["notice_period"] = input("Notice Period (e.g., 2 weeks): ").strip()
    profile["custom_fields"]["how_did_you_hear"] = input("How did you hear about us? (e.g., LinkedIn, Job Board): ").strip()
    
    relocate = input("Are you willing to relocate? (yes/no): ").strip().lower()
    profile["custom_fields"]["willing_to_relocate"] = "yes" if relocate.startswith('y') else "no"
    
    return profile

def setup_profile():
    """Main function to set up a user profile."""
    print("=" * 80)
    print("Profile Setup Assistant".center(80))
    print("=" * 80)
    print("\nThis wizard will help you create a profile.json file for the job application agent.")
    print("Fill in the following information. Press Enter to skip optional fields.")
    
    # Create the full profile by calling each section
    profile = prompt_basic_info()
    profile = prompt_work_experience(profile)
    profile = prompt_education(profile)
    profile = prompt_skills(profile)
    profile = prompt_languages(profile)
    profile = prompt_custom_fields(profile)
    
    # Clean up empty fields
    for section in profile:
        if isinstance(profile[section], list):
            # Remove completely empty list items
            profile[section] = [item for item in profile[section] if any(v for v in item.values() if v)]
            
            # Clean up empty lists within items
            for item in profile[section]:
                for key, value in item.items():
                    if isinstance(value, list) and not value:
                        item[key] = []
    
    # Determine output file path
    output_file = "profile.json"
    if os.path.exists(output_file):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"profile_{timestamp}.json"
        print(f"\nExisting profile.json found. Saving as {output_file} instead.")
    
    # Save the profile to a JSON file
    with open(output_file, 'w') as f:
        json.dump(profile, f, indent=2)
    
    print(f"\nProfile saved to {output_file}!")
    print("\nNext steps:")
    print("1. Review your profile and make any necessary adjustments")
    print("2. Rename the file to 'profile.json' if needed")
    print("3. Run the job application processor with:")
    print("   python process_jobs.py")
    print("\nThanks for using the Profile Setup Assistant!")

if __name__ == "__main__":
    setup_profile() 