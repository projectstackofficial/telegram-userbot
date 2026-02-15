"""
Predefined auto-reply categories for the Telegram Userbot.

These categories are used internally for time-based auto-switching.
Each message is crafted to be human-like with a maximum of 2 emojis.
"""

# Predefined categories with human-like messages
CATEGORIES = {
    # General Status
    "away": "Hey! I'm currently away from my phone. I'll get back to you soon 😊",
    "busy": "I'm a bit busy right now, but I'll reply as soon as I can 🙏",
    "offline": "I'm offline at the moment. Will catch up with you later!",
    
    # Work & Productivity
    "work": "I'm working right now. I'll respond once I'm free ⚡",
    "study": "I'm studying at the moment. Will get back to you later 📚",
    "meetings": "I'm in meetings right now. I'll reply as soon as they're done!",
    "focus": "I'm in deep focus mode. Will respond when I'm done 🎯",
    "dnd": "Please don't disturb right now. I'll get back to you soon!",
    
    # Personal Activities
    "sleep": "I'm sleeping right now. I'll reply when I wake up 😴",
    "lunch": "I'm having lunch. Will get back to you shortly!",
    "gym": "I'm at the gym right now. Will reply once I'm done 💪",
    "fresh": "I'm freshening up. Will respond in a bit!",
    
    # Travel & Movement
    "driving": "I'm driving at the moment. I'll text you once I'm parked 🚗",
    "travel": "I'm traveling right now. Will reply when I can!",
    "family": "I'm spending time with family. Will catch up with you later 🏡",
    "vacation": "I'm on vacation! I'll reply when I get a chance 🌴"
}

def get_category_message(category: str) -> str:
    """
    Get the message for a specific category.
    
    Args:
        category: The category name
        
    Returns:
        The auto-reply message for that category
        
    Raises:
        ValueError: If category doesn't exist
    """
    if category not in CATEGORIES:
        raise ValueError(f"Category '{category}' does not exist")
    return CATEGORIES[category]

def is_valid_category(category: str) -> bool:
    """
    Check if a category is valid.
    
    Args:
        category: The category name to validate
        
    Returns:
        True if valid, False otherwise
    """
    return category in CATEGORIES

def get_all_categories() -> dict:
    """
    Get all available categories with their messages.
    
    Returns:
        Dictionary of all categories
    """
    return CATEGORIES.copy()

def get_categories_list() -> list:
    """
    Get a list of all category names.
    
    Returns:
        List of category names
    """
    return list(CATEGORIES.keys())

def get_categories_help_text() -> str:
    """
    Generate a formatted help text showing all categories.
    
    Returns:
        Formatted string with all categories
    """
    lines = ["📋 **Available Categories:**\n"]
    
    # Group categories by type
    groups = {
        "General": ["away", "busy", "offline"],
        "Work & Productivity": ["work", "study", "meetings", "focus", "dnd"],
        "Personal": ["sleep", "lunch", "gym", "fresh"],
        "Travel & Movement": ["driving", "travel", "family", "vacation"]
    }
    
    for group_name, categories in groups.items():
        lines.append(f"\n**{group_name}:**")
        for cat in categories:
            if cat in CATEGORIES:
                lines.append(f"• `{cat}` - {CATEGORIES[cat]}")
    
    lines.append("\n*Note: These categories are read-only and used for time-based switching.*")
    
    return "\n".join(lines)
