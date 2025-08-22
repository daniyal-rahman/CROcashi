"""
Study Card Prompts Loader

This module loads the study card extraction prompts from the markdown file
and provides them in a format suitable for LangExtract.
"""

import os
from pathlib import Path
from typing import Optional

def load_prompts() -> str:
    """
    Load the study card extraction prompts from the markdown file.
    
    Returns:
        The complete prompt text as a string
    """
    # Get the path to the prompts markdown file
    current_dir = Path(__file__).parent
    prompts_file = current_dir / "study_card_prompts.md"
    
    if not prompts_file.exists():
        raise FileNotFoundError(f"Prompts file not found: {prompts_file}")
    
    # Read the prompts
    with open(prompts_file, 'r', encoding='utf-8') as f:
        prompts = f.read()
    
    # Load the JSON schema
    schema_file = current_dir.parent / "study_card.schema.json"
    if schema_file.exists():
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema_json = f.read()
        
        # Replace the placeholder with the actual schema
        prompts = prompts.replace("{{SCHEMA_JSON}}", schema_json)
    
    return prompts

def get_system_header() -> str:
    """
    Get just the system header portion of the prompts.
    
    Returns:
        The system header text
    """
    prompts = load_prompts()
    
    # Extract the system header section
    start_marker = "## System Header"
    end_marker = "## Task Body"
    
    start_idx = prompts.find(start_marker)
    end_idx = prompts.find(end_marker)
    
    if start_idx != -1 and end_idx != -1:
        return prompts[start_idx:end_idx].strip()
    else:
        # Fallback to full prompts if markers not found
        return prompts

def get_task_body() -> str:
    """
    Get just the task body portion of the prompts.
    
    Returns:
        The task body text
    """
    prompts = load_prompts()
    
    # Extract the task body section
    start_marker = "## Task Body"
    
    start_idx = prompts.find(start_marker)
    
    if start_idx != -1:
        return prompts[start_idx:].strip()
    else:
        # Fallback to full prompts if marker not found
        return prompts
