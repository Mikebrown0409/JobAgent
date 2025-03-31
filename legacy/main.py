import os
import json
import argparse
import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
import re
import uuid
import time
import difflib
from crewai import Agent, Task, Crew
from playwright.async_api import async_playwright, Page, Locator, Frame

# Logging setup
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class FrameManager:
    """Manages frame contexts for consistent lookups."""
    def __init__(self, page: Page):
        self.page = page
        self.frames = {}
        self._index_frames()

    def _index_frames(self):
        """Indexes all frames by identifier."""
        self.frames["main"] = self.page
        for frame in self.page.frames:
            identifier = self._get_identifier(frame)
            if identifier != "main":
                self.frames[identifier] = frame
                logger.debug(f"Indexed frame: {identifier}")

    def _get_identifier(self, frame: Frame) -> str:
        """Gets unique frame identifier."""
        url = frame.url if frame and hasattr(frame, 'url') else ""
        if not url or url == "about:blank":
            try:
                # Just use a safe default identifier instead of trying to evaluate JS
                return f"frame_{id(frame)}"
            except Exception:
                pass
        return url if url and url.startswith(("http://", "https://")) else "main"

    def get_context(self, identifier: str) -> Optional[Frame | Page]:
        """Returns frame or page context by identifier."""
        if not identifier or identifier not in self.frames:
            logger.error(f"Frame not found: {identifier}")
            return self.page  # Return main page as fallback
        return self.frames.get(identifier)

class ActionExecutor:
    def __init__(self, page: Page, frame_manager: FrameManager):
        self.page = page
        self.frame_manager = frame_manager

    async def _normalize_value(self, value: str, label: str) -> List[str]:
        """Generates smart variations of the input value based on context."""
        value = value.strip().lower()
        variations = [value]  # Start with full value

        # Strip common prefixes/suffixes
        for prefix in ["university of ", "college of ", "the "]:
            if value.startswith(prefix):
                value = value[len(prefix):]
                variations.append(value)

        # Handle separators and create simplified forms
        parts = re.split(r"[,;\-]\s*", value)
        if len(parts) > 1:
            # Add city/state or main name alone
            variations.append(parts[0].strip())
            variations.append(parts[-1].strip())

        # Initials for schools if multi-word
        if "school" in label.lower() or "university" in label.lower():
            words = value.split()
            if len(words) > 1:
                initials = "".join(w[0] for w in words if w)
                variations.append(initials)

        # Unique, ordered by specificity (full -> simplest)
        return list(dict.fromkeys(variations))

    async def _dismiss_dropdown(self, context: Frame | Page, label: str):
        """Forces dropdown dismissal."""
        try:
            await context.locator("body").click(force=True, timeout=2000)
            await self.page.wait_for_timeout(300)
            logger.debug(f"Dismissed dropdown for '{label}'")
        except Exception as e:
            logger.warning(f"Failed to dismiss dropdown for '{label}': {e}")

    async def execute(self, action: Dict[str, Any]) -> Dict[str, Any]:
        action_type, selector, value, label = action["action_type"], action["selector"], action.get("value"), action["label"]
        frame_id = action.get("frame_identifier", "main")
        context = self.frame_manager.get_context(frame_id)

        if not context:
            return {"success": False, "message": f"Frame not found: {frame_id}"}

        try:
            elem = context.locator(selector)
            await elem.wait_for(state="attached", timeout=20000)
            if action_type != "upload":
                await elem.scroll_into_view_if_needed()
                await self.page.wait_for_timeout(300)
        except Exception as e:
            return {"success": False, "message": f"Failed to locate '{label}' in '{frame_id}': {e}"}

        try:
            if action_type == "select-custom":
                logger.info(f"Handling custom dropdown for '{label}' with value '{value}'")
                await elem.click()
                await self.page.wait_for_timeout(1000)
                options = context.locator("[role='option'], .select2-results__option, [class*='option']").filter(visible=True)
                try:
                    await options.first.wait_for(state="visible", timeout=7000)
                    option_texts = [opt.strip().lower() for opt in await options.all_text_contents() if opt.strip()]
                    variations = await self._normalize_value(value, label)
                except Exception as e:
                    logger.warning(f"Error getting dropdown options for '{label}': {e}")
                    await self._dismiss_dropdown(context, label)
                    return {"success": False, "message": f"Failed to get dropdown options for '{label}': {e}"}

                for val in variations:
                    # Try fuzzy match first
                    best_match = difflib.get_close_matches(val, option_texts, n=1, cutoff=0.7)
                    if best_match:
                        opt = options.filter(has_text=re.compile(f"^{re.escape(best_match[0])}$", re.IGNORECASE)).first
                        await opt.click(timeout=10000)
                        await self._dismiss_dropdown(context, label)
                        return {"success": True, "message": f"Selected '{best_match[0]}' for '{label}'"}
                    
                    # Fallback to substring match
                    for opt_text in option_texts:
                        if val in opt_text:
                            opt = options.filter(has_text=re.compile(f"{re.escape(opt_text)}", re.IGNORECASE)).first
                            await opt.click(timeout=10000)
                            await self._dismiss_dropdown(context, label)
                            return {"success": True, "message": f"Selected '{opt_text}' for '{label}' via substring match"}

                await self._dismiss_dropdown(context, label)
                raise Exception(f"No match for '{value}' in '{label}'. Options: {option_texts}")

            # [Other action types unchanged: fill, select-native, upload, click]
            
        except Exception as e:
            if action_type == "select-custom":
                await self._dismiss_dropdown(context, label)
            return {"success": False, "message": f"Failed '{action_type}' on '{label}': {e}"}

async def extract_form_data(job_url: str) -> Dict[str, Any]:
    """Extracts form elements from the job URL with strategic prioritization."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto(job_url, wait_until="networkidle", timeout=120000)
        frame_manager = FrameManager(page)
        form_elements = []

        # First identify the form and its overall structure
        form_structure = {}
        for identifier, context in frame_manager.frames.items():
            logger.debug(f"Analyzing form structure in context: {identifier}")
            try:
                await context.wait_for_load_state("networkidle", timeout=25000)
                await context.wait_for_timeout(2000)
                
                # Try to identify form sections/groups
                sections = await context.locator("fieldset, .form-section, .application-section, div[role='group']").all()
                for i, section in enumerate(sections):
                    try:
                        section_name = await section.evaluate("""
                            el => {
                                const legend = el.querySelector('legend');
                                const heading = el.querySelector('h1, h2, h3, h4, h5, h6');
                                const label = el.querySelector('label');
                                return (legend?.textContent || heading?.textContent || label?.textContent || '').trim();
                            }
                        """)
                        if section_name:
                            section_id = f"section_{i}"
                            form_structure[section_id] = {
                                "name": section_name,
                                "importance": determine_section_importance(section_name)
                            }
                    except Exception as e:
                        logger.warning(f"Error processing section in {identifier}: {e}")
            except Exception as e:
                logger.warning(f"Failed to analyze form in context {identifier}: {e}")

        for identifier, context in frame_manager.frames.items():
            logger.debug(f"Extracting from context: {identifier}")
            try:
                # Wait for all dynamic content to load
                await context.wait_for_load_state("networkidle", timeout=25000)
                await context.wait_for_timeout(2000)
            except Exception as e:
                logger.warning(f"Failed to load context {identifier}: {e}")

            elements = []
            # Get interactive elements by role for better accessibility support
            for role in ["textbox", "textarea", "checkbox", "radio", "button", "combobox", "listbox"]:
                elements.extend(await context.get_by_role(role).all())
            # Get form elements by tag for better coverage
            for tag in ["select", "input", "textarea", "button"]:
                elements.extend(await context.locator(tag).all())

            for elem in elements:
                try:
                    attrs = await elem.evaluate("""
                        el => {
                            // Get label text using multiple strategies
                            const getLabelText = () => {
                                // Check for aria-label
                                if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
                                
                                // Check for associated label
                                if (el.id) {
                                    const label = document.querySelector(`label[for="${el.id}"]`);
                                    if (label) return label.textContent.trim();
                                }
                                
                                // Check for parent label
                                const parentLabel = el.closest('label');
                                if (parentLabel) {
                                    return parentLabel.textContent.replace(el.value || '', '').trim();
                                }
                                
                                // Check for placeholder
                                if (el.placeholder) return el.placeholder;
                                
                                // Check for neighboring label/text
                                const prevSibling = el.previousElementSibling;
                                if (prevSibling && (prevSibling.tagName === 'LABEL' || 
                                    prevSibling.tagName === 'SPAN' || prevSibling.tagName === 'DIV')) {
                                    return prevSibling.textContent.trim();
                                }
                                
                                // Last resort: find closest text node
                                return el.closest('.form-group, .field-group, .form-field')?.querySelector('label, .label, .field-label')?.textContent?.trim() || 'Unlabeled';
                            };
                            
                            return {
                                id: el.id,
                                name: el.name,
                                type: el.tagName.toLowerCase() === "select" ? "select" : 
                                      (el.getAttribute("role") === "combobox" ? "combobox" : 
                                      (el.type || "text")),
                                label: getLabelText(),
                                placeholder: el.placeholder || '',
                                options: el.tagName.toLowerCase() === "select" ? 
                                         Array.from(el.options).map(o => o.text.trim()) : [],
                                value: el.value || '',
                                required: el.required || el.getAttribute('aria-required') === 'true',
                                disabled: el.disabled || el.getAttribute('aria-disabled') === 'true',
                                hidden: el.hidden || 
                                        window.getComputedStyle(el).display === 'none' || 
                                        window.getComputedStyle(el).visibility === 'hidden',
                                attributes: {
                                    maxlength: el.getAttribute('maxlength'),
                                    min: el.getAttribute('min'),
                                    max: el.getAttribute('max')
                                },
                                fieldset: el.closest('fieldset')?.querySelector('legend')?.textContent?.trim() || '',
                                section: el.closest('section, div[role="group"]')?.querySelector('h1, h2, h3, h4, h5, h6')?.textContent?.trim() || ''
                            };
                        }
                    """)
                    
                    # Skip hidden or disabled elements
                    if attrs["hidden"] or attrs["disabled"]:
                        continue
                        
                    # Create selector with multiple fallbacks
                    selector = None
                    if attrs["id"] and await context.locator(f"#{attrs['id']}").count() == 1:
                        selector = f"#{attrs['id']}"
                    elif attrs["name"]:
                        selector = f"[name='{attrs['name']}']"
                    elif attrs["label"] != "Unlabeled":
                        # Try to use aria-label as selector
                        selector = f"[aria-label='{attrs['label']}']"
                    
                    if not selector:
                        continue
                        
                    # Determine field importance
                    importance = determine_field_importance(attrs["label"], attrs["type"], attrs["required"])
                    
                    # Add to form elements with improved metadata
                    form_elements.append({
                        "label": attrs["label"],
                        "selector": selector,
                        "type": attrs["type"],
                        "options": attrs["options"],
                        "required": attrs["required"],
                        "importance": importance,
                        "placeholder": attrs["placeholder"],
                        "section": attrs["section"] or attrs["fieldset"],
                        "frame_info": {"url": identifier if identifier != "main" else ""}
                    })
                except Exception as e:
                    logger.error(f"Error processing element in {identifier}: {e}")

        # Sort elements by importance and required status
        form_elements.sort(key=lambda x: (0 if x["required"] else 1, 
                                         0 if x["importance"] == "high" else 
                                         1 if x["importance"] == "medium" else 2))

        screenshot = f"extract_{uuid.uuid4().hex[:8]}.png"
        await page.screenshot(path=screenshot, full_page=True)
        await browser.close()
        return {"final_url": page.url, "form_elements": form_elements, "screenshot": screenshot}

def determine_field_importance(label: str, field_type: str, required: bool) -> str:
    """Determine the strategic importance of a field for application success."""
    label_lower = label.lower()
    
    # Always high importance fields
    high_importance_patterns = [
        'name', 'email', 'phone', 'resume', 'cv', 'cover letter', 
        'experience', 'skills', 'education', 'degree', 'university',
        'salary', 'availability', 'start date', 'notice period',
        'portfolio', 'website', 'github', 'linkedin'
    ]
    
    # Medium importance fields
    medium_importance_patterns = [
        'address', 'location', 'city', 'state', 'zip', 'country',
        'reference', 'referral', 'languages', 'certification',
        'work permit', 'visa', 'authorization', 'timezone',
        'social media', 'twitter', 'relocation'
    ]
    
    # Low importance fields
    low_importance_patterns = [
        'gender', 'race', 'ethnicity', 'veteran', 'disability',
        'how did you hear', 'newsletter', 'marketing', 'updates',
        'agree to terms', 'privacy policy', 'additional info'
    ]
    
    # Required fields are always at least medium importance
    if required:
        return "high" if any(pattern in label_lower for pattern in high_importance_patterns) else "medium"
    
    # Check field type - uploads and textareas often contain important information
    if field_type in ['file', 'textarea']:
        return "high"
        
    # Check label patterns
    if any(pattern in label_lower for pattern in high_importance_patterns):
        return "high"
    elif any(pattern in label_lower for pattern in medium_importance_patterns):
        return "medium"
    elif any(pattern in label_lower for pattern in low_importance_patterns):
        return "low"
    
    # Default to medium for unclassified fields
    return "medium"

def determine_section_importance(section_name: str) -> str:
    """Determine the importance of a form section."""
    section_lower = section_name.lower()
    
    high_patterns = [
        'personal', 'profile', 'contact', 'experience', 'education',
        'resume', 'cover', 'skills', 'qualification', 'work'
    ]
    
    medium_patterns = [
        'additional', 'reference', 'preference', 'availability',
        'salary', 'relocation', 'language', 'certification'
    ]
    
    low_patterns = [
        'demographic', 'diversity', 'voluntary', 'terms', 
        'privacy', 'optional', 'marketing', 'newsletter'
    ]
    
    if any(pattern in section_lower for pattern in high_patterns):
        return "high"
    elif any(pattern in section_lower for pattern in medium_patterns):
        return "medium"
    elif any(pattern in section_lower for pattern in low_patterns):
        return "low"
    
    # Default to medium
    return "medium"


def create_mapper_agent() -> Agent:
    """Creates the mapping agent with improved prompt for strategic field prioritization."""
    if not os.environ.get("TOGETHERAI_API_KEY"):
        raise ValueError("TOGETHERAI_API_KEY not set")
    return Agent(
        role="Strategic Form Data Mapper",
        goal="Map profile data to form fields with intelligent prioritization.",
        backstory="""Expert in job application optimization. You understand which fields are most 
                  important for successful applications and how to strategically fill both required and 
                  optional fields to maximize candidate success. You know how to adapt content 
                  based on job context and highlight relevant experience.""",
        llm="together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
        verbose=True,
        max_iter=1
    )

def group_elements_by_frame(elements: List[Dict]) -> Dict[str, List[Dict]]:
    """Groups elements by frame identifier."""
    grouped = {}
    for elem in elements:
        frame_id = elem["frame_info"]["url"] or "main"
        if frame_id not in grouped:
            grouped[frame_id] = []
        elem_copy = elem.copy()
        elem_copy.pop("frame_info")
        grouped[frame_id].append(elem_copy)
    return grouped

def create_task(agent: Agent, objective: str, elements: List[Dict], profile_part: Dict, instructions: str) -> Task:
    """Generic task creator with improved strategy guidance."""
    # Group elements by both frame and importance
    elements_by_frame = group_elements_by_frame(elements)
    
    # Enhanced instructions with strategic guidance
    strategic_instructions = f"""
    {instructions}
    
    Follow these strategic guidelines:
    1. Required fields must be filled first - they are essential for submission
    2. High-importance fields should be filled with detailed, relevant information
    3. Medium-importance fields should be filled if they showcase relevant skills or experience
    4. Low-importance fields can be filled with standard responses or omitted if truly irrelevant
    5. Adapt responses based on job context when possible
    
    For each field, consider:
    - How the information contributes to showcasing relevant qualifications
    - Whether the field provides opportunity to highlight unique value proposition
    - If the field could be used to address potential gaps or concerns
    
    Output Action Format: {{"action_type": "<type>", "selector": "<selector>", "value": "<value>", "label": "<label>", "frame_identifier": "<id>", "importance": "<importance>"}}
    """
    
    return Task(
        description=f"""
        **Objective:** {objective}
        **Form Elements:** {json.dumps(elements_by_frame, indent=2)}
        **Profile:** {json.dumps(profile_part, indent=2)}
        **Instructions:** {strategic_instructions}
        **Output:** JSON list of actions prioritized by importance and strategic value.
        """,
        expected_output="JSON list of actions.",
        agent=agent
    )

def group_elements_by_importance(elements: List[Dict]) -> Dict[str, List[Dict]]:
    """Groups elements by importance level."""
    grouped = {"high": [], "medium": [], "low": []}
    for elem in elements:
        importance = elem.get("importance", "medium")
        grouped[importance].append(elem)
    return grouped

async def map_form_data(form_data: Dict[str, Any], profile: Dict[str, Any]) -> List[Dict]:
    """Maps form data to profile with strategic prioritization."""
    agent = create_mapper_agent()
    
    # Sort and categorize elements
    all_elements = form_data["form_elements"]
    elements_by_importance = group_elements_by_importance(all_elements)
    
    # Create more strategically focused tasks
    tasks = [
        # Critical personal and contact information
        create_task(agent, "Map essential personal data", 
                   [f for f in all_elements if f["required"] or f["importance"] == "high"],
                   profile["personal"], 
                   "Fill required and high-importance fields with accurate personal information."),
        
        # Resume and document uploads - critical for applications
        create_task(agent, "Upload documents and provide experience details", 
                   [f for f in all_elements if f["type"] in ["file", "textarea"] or "experience" in f["label"].lower()],
                   {**profile.get("documents", {}), **profile.get("experience", {})}, 
                   f"Upload resume from {profile.get('resume_path', 'resume.pdf')} and fill experience details with relevant accomplishments."),
        
        # Education and qualifications - high value fields
        create_task(agent, "Provide education and qualifications", 
                   [f for f in all_elements if any(kw in f["label"].lower() for kw in ["education", "degree", "university", "qualification", "certification"])],
                   profile.get("education", {}), 
                   "Present education history highlighting relevant coursework and achievements."),
        
        # Skills and expertise - highlight strengths
        create_task(agent, "Showcase skills and expertise", 
                   [f for f in all_elements if any(kw in f["label"].lower() for kw in ["skill", "expertise", "proficiency", "knowledge", "competency"])],
                   profile.get("skills", {}), 
                   "Highlight skills that match job requirements, prioritizing technical and specialized abilities."),
        
        # Employment preferences - strategic for fit
        create_task(agent, "Provide employment preferences", 
                   [f for f in all_elements if any(kw in f["label"].lower() for kw in ["salary", "compensation", "availability", "relocation", "remote", "start date"])],
                   profile.get("preferences", {}), 
                   "Answer preference questions strategically to show flexibility while maintaining standards."),
        
        # Additional information - complete remaining fields
        create_task(agent, "Complete remaining fields", 
                   [f for f in all_elements if f["importance"] == "medium" and not any(kw in f["label"].lower() 
                     for kw in ["name", "email", "phone", "resume", "education", "skill", "salary", "experience"])],
                   profile, 
                   "Fill remaining medium-importance fields that could strengthen the application."),
        
        # Low priority fields - only if needed for submission
        create_task(agent, "Handle low-priority fields", 
                   [f for f in all_elements if f["importance"] == "low"],
                   {}, 
                   "Complete low-priority fields with standard responses only if required for submission."),
        
        # Submit the application
        create_task(agent, "Identify submission action", 
                   [f for f in all_elements if f["type"] in ["button", "submit"] or "submit" in f["label"].lower()],
                   {}, 
                   "Find and click the submission button after all other fields are completed.")
    ]

    action_plan = []
    for i, task in enumerate(tasks):
        try:
            logger.info(f"Starting task {i+1}/{len(tasks)}: {task.description.splitlines()[0] if task.description else 'Unknown task'}")
            crew = Crew(agents=[agent], tasks=[task], verbose=True)
            result = await crew.kickoff_async()
            
            if not result or not result.tasks_output or not result.tasks_output[0].raw:
                logger.warning(f"Task {i+1} returned no result")
                continue
                
            raw_result = result.tasks_output[0].raw.strip()
            logger.debug(f"Raw result from task {i+1}: {raw_result}")
            
            try:
                actions = json.loads(raw_result)
                logger.info(f"Successfully parsed JSON from task {i+1}")
                
                # Ensure actions are properly formatted
                if isinstance(actions, list):
                    for j, action in enumerate(actions):
                        if not isinstance(action, dict):
                            logger.warning(f"Task {i+1}, action {j+1} is not a dictionary: {action}")
                            continue
                            
                        # Ensure required keys are present
                        if 'action_type' not in action:
                            logger.warning(f"Task {i+1}, action {j+1} missing action_type: {action}")
                            continue
                        
                        # Ensure selector is present
                        if 'selector' not in action:
                            logger.warning(f"Task {i+1}, action {j+1} missing selector: {action}")
                            continue
                            
                        # Ensure label is present and is a string
                        if 'label' not in action:
                            # Try to derive a reasonable label from the action
                            if 'value' in action:
                                action['label'] = f"Field for {action.get('value')}"
                            else:
                                action['label'] = f"{action['action_type']} action for {action['selector']}"
                            logger.warning(f"Task {i+1}, action {j+1} missing label, added default: {action['label']}")
                        elif not isinstance(action['label'], str):
                            action['label'] = str(action['label'])
                            logger.warning(f"Task {i+1}, action {j+1} had non-string label, converted to string: {action['label']}")
                        
                        # Ensure importance is present
                        if 'importance' not in action:
                            action['importance'] = "medium"  # Default importance
                        
                        # Add to action plan if not a duplicate
                        if not any(existing['selector'] == action['selector'] for existing in action_plan):
                            action_plan.append(action)
                            logger.debug(f"Added action: {action}")
                        else:
                            logger.debug(f"Skipped duplicate action for selector: {action['selector']}")
                        
                elif isinstance(actions, dict):
                    # Make a single dict into a proper action
                    action = actions
                    
                    # Ensure required keys are present
                    if 'action_type' not in action:
                        logger.warning(f"Task {i+1} result missing action_type: {action}")
                        continue
                    
                    # Ensure selector is present
                    if 'selector' not in action:
                        logger.warning(f"Task {i+1} result missing selector: {action}")
                        continue
                        
                    # Ensure label is present and is a string
                    if 'label' not in action:
                        # Try to derive a reasonable label from the action
                        if 'value' in action:
                            action['label'] = f"Field for {action.get('value')}"
                        else:
                            action['label'] = f"{action['action_type']} action for {action['selector']}"
                        logger.warning(f"Task {i+1} result missing label, added default: {action['label']}")
                    elif not isinstance(action['label'], str):
                        action['label'] = str(action['label'])
                        logger.warning(f"Task {i+1} result had non-string label, converted to string: {action['label']}")
                    
                    # Ensure importance is present
                    if 'importance' not in action:
                        action['importance'] = "medium"  # Default importance
                    
                    # Add to action plan if not a duplicate
                    if not any(existing['selector'] == action['selector'] for existing in action_plan):
                        action_plan.append(action)
                        logger.debug(f"Added single action: {action}")
                    else:
                        logger.debug(f"Skipped duplicate action for selector: {action['selector']}")
                else:
                    logger.warning(f"Task {i+1} result is neither a list nor a dictionary: {actions}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from task {i+1}: {e}\nRaw text: {raw_result}")
                
        except Exception as e:
            logger.error(f"Error processing task {i+1}: {type(e).__name__} - {e}")
            
        await asyncio.sleep(12)  # Rate limit buffer
    
    # Sort final action plan by importance and type
    # Required fields first, then high importance, then medium, then low
    # Within each importance level, order by field type (personal info first, then uploads, then selections, etc.)
    action_plan.sort(key=lambda x: (
        0 if any(kw in x['label'].lower() for kw in ['required', 'mandatory']) else 1,
        0 if x.get('importance') == 'high' else 1 if x.get('importance') == 'medium' else 2,
        0 if x['action_type'] == 'fill' and any(kw in x['label'].lower() for kw in ['name', 'email', 'phone']) else
        1 if x['action_type'] == 'upload' else
        2 if x['action_type'] in ['select-native', 'select-custom'] else
        3 if x['action_type'] == 'fill' else
        4 if x['action_type'] == 'click' and 'submit' not in x['label'].lower() else
        5  # Submit button should be last
    ))
    
    logger.info(f"Final action plan contains {len(action_plan)} actions")
    return action_plan

async def apply_to_job(job_url: str, user_profile_path: str = "user_profile.json", test_mode: bool = False) -> str:
    """Main orchestration with improved error handling and execution flow."""
    start_time = time.time()
    report_filename = f"report_{uuid.uuid4().hex[:8]}.txt"
    
    try:
        # Extract form data
        logger.info(f"Extracting form data from {job_url}")
        form_data = await extract_form_data(job_url)
        
        # Load and enhance user profile
        logger.info("Loading user profile")
        with open(user_profile_path) as f:
            profile = json.load(f)
        
        # Ensure resume path is absolute
        profile["resume_path"] = os.path.abspath(profile.get("resume_path", "resume.pdf"))
        
        # Enhance profile with additional derived information
        if "personal" in profile and "skills" in profile:
            # Create derived experience highlights from skills and experience
            profile["experience_highlights"] = {
                "highlights": [f"Expert in {skill}" for skill in profile["skills"][:3]] 
                if "skills" in profile and isinstance(profile["skills"], list) else []
            }
        
        # Map form data to profile
        logger.info("Mapping form data to user profile")
        action_plan = await map_form_data(form_data, profile)
        
        # In test mode, skip submission actions
        if test_mode:
            action_plan = [a for a in action_plan if a["action_type"] != "click" or "submit" not in a["label"].lower()]
            logger.info(f"Test mode enabled - will execute {len(action_plan)} actions without submitting")

        # Validate each action to ensure it has required keys
        valid_action_plan = []
        for action in action_plan:
            # Check if action is a valid dictionary with required keys
            if not isinstance(action, dict):
                logger.warning(f"Skipping invalid action (not a dictionary): {action}")
                continue
            
            required_keys = ['action_type', 'selector', 'label']
            missing_keys = [key for key in required_keys if key not in action]
            
            if missing_keys:
                logger.warning(f"Skipping action missing required keys {missing_keys}: {action}")
                continue
            
            # Ensure that label is a string
            if not isinstance(action['label'], str):
                action['label'] = str(action['label'])
                logger.info(f"Converted non-string label to string: {action['label']}")
                
            valid_action_plan.append(action)
        
        if not valid_action_plan:
            return f"Job: {job_url}\nStatus: Failed\nTime: {time.time() - start_time:.2f}s\nError: No valid actions in action plan"
        
        action_plan = valid_action_plan  # Use only valid actions
        
        logger.info(f"Proceeding with {len(action_plan)} valid actions")

        # Execute the action plan
        async with async_playwright() as p:
            # Launch with viewport size that accommodates most forms
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 900},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'
            )
            page = await context.new_page()
            
            # Enable form filling permissions
            await context.grant_permissions(['clipboard-read', 'clipboard-write'])
            
            # Navigate to job page with appropriate timeout
            await page.goto(form_data["final_url"], wait_until="networkidle", timeout=120000)
            
            # Create frame manager and action executor
            frame_manager = FrameManager(page)
            executor = ActionExecutor(page, frame_manager)
            execution_log = []

            # Execute actions with better error handling and progress tracking
            success_count = 0
            failure_count = 0
            
            for idx, action in enumerate(action_plan):
                try:
                    logger.info(f"Executing action {idx+1}/{len(action_plan)}: {action['action_type']} on {action['label']}")
                    
                    # Attempt to execute with retries for flaky elements
                    max_retries = 2
                    retry_count = 0
                    result = None
                    
                    while retry_count <= max_retries:
                        try:
                            result = await executor.execute(action)
                            if result["success"]:
                                break
                            retry_count += 1
                            if retry_count <= max_retries:
                                logger.info(f"Retrying action {idx+1} (attempt {retry_count+1}/{max_retries+1})")
                                await page.wait_for_timeout(1000)  # Wait before retry
                        except Exception as e:
                            retry_count += 1
                            if retry_count <= max_retries:
                                logger.warning(f"Error on attempt {retry_count}/{max_retries+1}: {e}")
                                await page.wait_for_timeout(1000)  # Wait before retry
                            else:
                                raise
                    
                    # If we exhausted retries, set a failure result
                    if not result:
                        result = {"success": False, "message": f"Failed after {max_retries+1} attempts"}
                    
                    # Track execution status
                    execution_log.append({"action": action, "result": result})
                    
                    if result["success"]:
                        success_count += 1
                    else:
                        failure_count += 1
                    
                    # Add a small pause between actions to avoid overwhelming the page
                    await page.wait_for_timeout(500)
                    
                    # If this was a submit button and we're not in test mode, wait for navigation
                    if result["success"] and action["action_type"] == "click" and "submit" in action["label"].lower() and not test_mode:
                        try:
                            logger.info("Waiting for navigation after submit...")
                            await page.wait_for_navigation(timeout=30000)
                        except Exception as e:
                            logger.warning(f"No navigation occurred after submit: {e}")
                    
                except Exception as e:
                    error_msg = f"Error executing action {idx+1}: {type(e).__name__} - {str(e)}"
                    logger.error(error_msg)
                    execution_log.append({"action": action, "result": {"success": False, "message": error_msg}})
                    failure_count += 1

            # Take a final screenshot
            screenshot = f"extract_{uuid.uuid4().hex[:8]}.png"
            await page.screenshot(path=screenshot, full_page=True)
            await browser.close()

        # Generate detailed report
        success_rate = success_count / len(action_plan) * 100 if action_plan else 0
        status = "Completed" if success_rate > 90 else "Partial" if success_rate > 50 else "Failed"
        
        report = (
            f"Job: {job_url}\n"
            f"Status: {status} ({success_count}/{len(action_plan)} actions successful - {success_rate:.1f}%)\n"
            f"Time: {time.time() - start_time:.2f}s\n"
            f"Actions Summary:\n"
            f"  - Total actions: {len(action_plan)}\n"
            f"  - Successful: {success_count}\n"
            f"  - Failed: {failure_count}\n"
            f"Screenshot: {screenshot}\n"
        )
        
        with open(report_filename, "w") as f:
            f.write(report)
            
        return report
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error in apply_to_job: {error_details}")
        report = f"Job: {job_url}\nStatus: Failed ({type(e).__name__})\nTime: {time.time() - start_time:.2f}s\nError: {str(e)}"
        with open(report_filename, "w") as f:
            f.write(report)
        return report

async def main():
    parser = argparse.ArgumentParser(description="Job Application Automation")
    parser.add_argument("--job-url", required=True)
    parser.add_argument("--user-profile", default="user_profile.json")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    print(await apply_to_job(args.job_url, args.user_profile, args.test))

if __name__ == "__main__":
    asyncio.run(main())