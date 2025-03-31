#!/usr/bin/env python3
"""
Test script for the Enterprise Job Application Agent on Discord careers site.
"""

import asyncio
import json
import os
import logging
from dotenv import load_dotenv
from pathlib import Path
import fpdf
from langchain.chat_models import ChatOpenAI

# Import required modules
from enterprise_job_agent.main import initialize_llm
from enterprise_job_agent.utils.browser_tools import BrowserManager
from enterprise_job_agent.utils.form_tools import analyze_form
from enterprise_job_agent.utils.profile_data import ProfileManager
from enterprise_job_agent.core.crew_manager import JobApplicationCrew

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('discord_application_test.log')
    ]
)

logger = logging.getLogger(__name__)

# Discord job application URL - Staff Software Engineer, Media Infrastructure
DISCORD_JOB_URL = "https://job-boards.greenhouse.io/discord/jobs/7845336002"

def create_sample_resume(profile, output_path="resume.pdf"):
    """Create a sample resume PDF for testing."""
    logger.info(f"Creating sample resume at {output_path}")
    
    pdf = fpdf.FPDF()
    pdf.add_page()
    
    # Add title
    pdf.set_font("Arial", "B", 16)
    name = f"{profile['personal']['first_name']} {profile['personal']['last_name']}"
    pdf.cell(0, 10, name, ln=True, align="C")
    
    # Add contact info
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 5, f"Email: {profile['personal']['email']}", ln=True, align="C")
    pdf.cell(0, 5, f"Phone: {profile['personal']['phone']}", ln=True, align="C")
    pdf.cell(0, 5, f"Address: {profile['personal']['address']}, {profile['personal']['city']}, {profile['personal']['state']} {profile['personal']['zip']}", ln=True, align="C")
    
    # Experience
    pdf.ln(5)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "PROFESSIONAL EXPERIENCE", ln=True)
    
    pdf.set_font("Arial", "B", 11)
    for exp in profile["experience"]:
        pdf.ln(5)
        pdf.cell(0, 5, f"{exp['company']} - {exp['title']}", ln=True)
        pdf.set_font("Arial", "I", 10)
        pdf.cell(0, 5, f"{exp['start_date']} to {exp['end_date']}", ln=True)
        pdf.set_font("Arial", "", 10)
        # Split description into multiple lines if necessary
        description = exp["description"]
        pdf.multi_cell(0, 5, description)
        pdf.set_font("Arial", "B", 11)
    
    # Education
    pdf.ln(5)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "EDUCATION", ln=True)
    
    for edu in profile["education"]:
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 5, f"{edu['institution']}", ln=True)
        pdf.set_font("Arial", "", 10)
        pdf.cell(0, 5, f"{edu['degree']} in {edu['major']}, GPA: {edu['gpa']}", ln=True)
        pdf.cell(0, 5, f"{edu['start_date']} to {edu['end_date']}", ln=True)
    
    # Skills
    pdf.ln(5)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "SKILLS", ln=True)
    
    pdf.set_font("Arial", "", 10)
    # Group skills into multiple rows
    skills_text = ""
    line_count = 0
    for i, skill in enumerate(profile["skills"]):
        skills_text += skill
        if i < len(profile["skills"]) - 1:
            skills_text += ", "
        line_count += 1
        if line_count >= 8:
            skills_text += "\n"
            line_count = 0
    
    pdf.multi_cell(0, 5, skills_text)
    
    # Save PDF
    pdf.output(output_path)
    logger.info(f"Resume created successfully at {output_path}")
    return output_path

def create_sample_cover_letter(profile, job_title="Staff Software Engineer, Media Infrastructure", output_path="cover_letter.pdf"):
    """Create a sample cover letter PDF for testing."""
    logger.info(f"Creating sample cover letter at {output_path}")
    
    pdf = fpdf.FPDF()
    pdf.add_page()
    
    # Add header
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 5, f"{profile['personal']['first_name']} {profile['personal']['last_name']}", ln=True)
    pdf.cell(0, 5, f"{profile['personal']['address']}", ln=True)
    pdf.cell(0, 5, f"{profile['personal']['city']}, {profile['personal']['state']} {profile['personal']['zip']}", ln=True)
    pdf.cell(0, 5, f"{profile['personal']['email']}", ln=True)
    pdf.cell(0, 5, f"{profile['personal']['phone']}", ln=True)
    
    pdf.ln(10)
    pdf.cell(0, 5, "Discord, Inc.", ln=True)
    pdf.cell(0, 5, "Recruiting Team", ln=True)
    pdf.cell(0, 5, "San Francisco, CA", ln=True)
    
    pdf.ln(10)
    pdf.cell(0, 5, f"RE: Application for {job_title} Position", ln=True)
    
    pdf.ln(5)
    pdf.cell(0, 5, "Dear Discord Hiring Team,", ln=True)
    
    pdf.ln(5)
    pdf.set_font("Arial", "", 10)
    cover_letter_text = (
        "I am writing to express my interest in the Staff Software Engineer, Media Infrastructure position at Discord. "
        "With over 10 years of experience in media systems development and video encoding technologies, I believe my "
        "background aligns perfectly with the needs of your team.\n\n"
        
        "My experience at TechCorp leading the media infrastructure team has given me deep expertise in solving "
        "complex scaling challenges, optimizing video encoding processes, and building systems handling millions "
        "of media assets daily. I've architected solutions that reduced storage costs by 40% while maintaining "
        "high-quality user experiences.\n\n"
        
        "At StreamTech, I developed video encoding pipelines using FFmpeg and built HLS and MPEG-DASH streaming "
        "systems for global content delivery. My work on CDN optimization improved video delivery performance by 35% "
        "globally.\n\n"
        
        "I'm particularly excited about Discord's unique role in the gaming ecosystem. As both a user of Discord "
        "and an engineer passionate about media technologies, I understand how critical fast, reliable video and "
        "image processing is to the platform's user experience.\n\n"
        
        "I look forward to the opportunity to discuss how my background in media infrastructure could contribute to "
        "Discord's continued success and growth.\n\n"
        
        "Thank you for your consideration."
    )
    
    pdf.multi_cell(0, 5, cover_letter_text)
    
    pdf.ln(10)
    pdf.cell(0, 5, "Sincerely,", ln=True)
    pdf.ln(10)
    pdf.cell(0, 5, f"{profile['personal']['first_name']} {profile['personal']['last_name']}", ln=True)
    
    # Save PDF
    pdf.output(output_path)
    logger.info(f"Cover letter created successfully at {output_path}")
    return output_path

async def extract_discord_job_data(headless=False):
    """Extract job data from Discord's career page."""
    browser_manager = BrowserManager(headless=headless)
    
    try:
        # Start browser
        await browser_manager.start()
        
        # Navigate to job URL
        success = await browser_manager.navigate(DISCORD_JOB_URL)
        if not success:
            logger.error(f"Failed to navigate to {DISCORD_JOB_URL}")
            return {}
        
        # Extract job details
        job_details = await browser_manager.extract_job_details()
        
        # Find the apply button and click
        page = await browser_manager.get_page()
        apply_button = page.get_by_role("button", name="Apply")
        
        # Take screenshot before applying
        await browser_manager.take_screenshot("discord_job_posting.png")
        
        if await apply_button.count() > 0:
            # Click the apply button to get to application form
            await apply_button.click()
            
            # Wait for the application form to load
            await page.wait_for_load_state("networkidle")
            
            # Take screenshot of the application form
            await browser_manager.take_screenshot("discord_application_form.png")
            
            # Analyze form structure using the standalone function
            form_structure = await analyze_form(page)
            
            return {
                "job_details": job_details,
                "form_structure": form_structure,
                "screenshot_path": "discord_application_form.png"
            }
        else:
            logger.error("Could not find apply button on Discord job posting")
            return {
                "job_details": job_details,
                "error": "Apply button not found"
            }
            
    finally:
        # Close browser
        await browser_manager.close()

async def main():
    """Run the Discord job application test."""
    # Load environment variables
    load_dotenv()
    
    # Get API key
    api_key = os.getenv("TOGETHERAI_API_KEY")
    if not api_key:
        logger.error("No API key found. Set TOGETHERAI_API_KEY in .env file.")
        return
    
    # Initialize LLM
    # Using ChatOpenAI instead of Together to avoid integration issues
    llm = ChatOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-3.5-turbo",
        temperature=0.7
    )
    
    # Create output directory for test files
    output_dir = Path("test_outputs")
    output_dir.mkdir(exist_ok=True)
    
    # Load user profile
    profile_path = os.path.join(os.path.dirname(__file__), "test_profile.json")
    if not os.path.exists(profile_path):
        logger.error(f"Profile file not found: {profile_path}")
        logger.info("Creating a sample profile for testing...")
        
        # Create a sample profile - update to better match Staff Software Engineer role
        sample_profile = {
            "personal": {
                "first_name": "Alex",
                "last_name": "Johnson",
                "email": "alex.johnson@example.com",
                "phone": "+1 (555) 123-4567",
                "address": "123 Tech Lane",
                "city": "San Francisco",
                "state": "CA",
                "zip": "94105",
                "country": "United States"
            },
            "education": [
                {
                    "institution": "Stanford University",
                    "degree": "Master of Science",
                    "major": "Computer Science",
                    "gpa": "3.8",
                    "start_date": "2012-09-01",
                    "end_date": "2014-06-15"
                },
                {
                    "institution": "University of California, Berkeley",
                    "degree": "Bachelor of Science",
                    "major": "Computer Engineering",
                    "gpa": "3.7",
                    "start_date": "2008-09-01",
                    "end_date": "2012-05-20"
                }
            ],
            "experience": [
                {
                    "company": "TechCorp Inc.",
                    "title": "Staff Software Engineer",
                    "start_date": "2018-07-01",
                    "end_date": "Present",
                    "description": "Led media infrastructure team handling video encoding and processing at scale. Architected systems processing millions of videos daily. Implemented advanced compression techniques reducing storage costs by 40%."
                },
                {
                    "company": "StreamTech",
                    "title": "Senior Software Engineer",
                    "start_date": "2014-08-01",
                    "end_date": "2018-06-30",
                    "description": "Developed video encoding pipelines using FFmpeg and proprietary tools. Built HLS and MPEG-DASH streaming systems. Optimized CDN delivery for global content distribution."
                },
                {
                    "company": "MediaSoft",
                    "title": "Software Engineer",
                    "start_date": "2011-06-01",
                    "end_date": "2014-07-30",
                    "description": "Worked on video transcoding systems, implementing H.264 and VP9 codecs. Built distributed media processing systems handling 100K+ daily uploads."
                }
            ],
            "skills": [
                "Rust", "C++", "Python", "FFmpeg", "Video Encoding", "HLS", "MPEG-DASH",
                "H.264", "H.265/HEVC", "VP9", "AV1", "Distributed Systems", "Redis",
                "CDN Technologies", "Fastly", "Cloudflare", "Video Optimization",
                "GraphQL", "REST", "gRPC", "AWS", "GCP", "Terraform", "DevOps"
            ],
            "documents": {
                "resume_path": str(output_dir / "resume.pdf"),
                "cover_letter_path": str(output_dir / "cover_letter.pdf")
            }
        }
        
        with open(profile_path, "w") as f:
            json.dump(sample_profile, f, indent=2)
            
        logger.info(f"Sample profile created at {profile_path}")
    
    profile_manager = ProfileManager(profile_path)
    user_profile = profile_manager.get_profile()
    
    # Create sample resume and cover letter
    resume_path = create_sample_resume(user_profile, output_path=str(output_dir / "resume.pdf"))
    cover_letter_path = create_sample_cover_letter(user_profile, output_path=str(output_dir / "cover_letter.pdf"))
    
    # Update profile with actual paths - use the correct profile structure
    user_profile["resume_path"] = resume_path
    user_profile["cover_letter_path"] = cover_letter_path
    
    # Extract Discord job data
    logger.info("Extracting Discord job data...")
    job_data = await extract_discord_job_data(headless=False)
    
    if not job_data or "error" in job_data:
        logger.error("Failed to extract Discord job data")
        return
    
    # Initialize job application crew
    logger.info("Initializing job application crew...")
    crew_manager = JobApplicationCrew(
        llm=llm,
        verbose=True
    )
    
    # Execute job application process in test mode
    logger.info("Starting job application process (TEST MODE)...")
    result = await crew_manager.execute_job_application_process(
        form_data=job_data["form_structure"],
        user_profile=user_profile,
        job_description=job_data["job_details"],
        test_mode=True  # Test mode - no actual submission
    )
    
    # Save results
    with open(str(output_dir / "discord_application_result.json"), "w") as f:
        json.dump(result, f, indent=2)
    
    logger.info(f"Test completed {'successfully' if result['success'] else 'with errors'}")
    logger.info(f"Results saved to {output_dir / 'discord_application_result.json'}")

if __name__ == "__main__":
    asyncio.run(main()) 