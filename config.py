"""
Configuration management for the Telegram Userbot.

Loads and validates all required environment variables from .env file.
No hardcoded credentials - all values must come from environment.
"""

import os
import sys
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

def get_env_var(var_name: str, required: bool = True, default: str = None) -> str:
    """
    Get environment variable with validation.
    
    Args:
        var_name: Name of the environment variable
        required: Whether this variable is required
        default: Default value if not required and not found
        
    Returns:
        The environment variable value
        
    Raises:
        SystemExit: If a required variable is missing
    """
    value = os.getenv(var_name, default)
    
    if required and not value:
        logger.error(f"Missing required environment variable: {var_name}")
        print(f"\n❌ ERROR: Missing required environment variable: {var_name}")
        print(f"Please set {var_name} in your .env file")
        print("See .env.example for reference\n")
        sys.exit(1)
    
    return value

def validate_config():
    """
    Validate all configuration values.
    
    Raises:
        SystemExit: If any validation fails
    """
    errors = []
    
    # Validate API_ID is numeric
    try:
        int(API_ID)
    except ValueError:
        errors.append("API_ID must be a valid integer")
    
    # Validate API_HASH format (should be 32 characters)
    if len(API_HASH) != 32:
        errors.append("API_HASH should be 32 characters long")
    
    # Validate MONGO_URI format
    if not MONGO_URI.startswith(('mongodb://', 'mongodb+srv://')):
        errors.append("MONGO_URI must start with 'mongodb://' or 'mongodb+srv://'")
    
    # Validate DB_NAME is not empty
    if not DB_NAME or DB_NAME.strip() == '':
        errors.append("DB_NAME cannot be empty")
    
    # Validate SESSION_NAME is not empty
    if not SESSION_NAME or SESSION_NAME.strip() == '':
        errors.append("SESSION_NAME cannot be empty")
    
    if errors:
        logger.error("Configuration validation failed")
        print("\n❌ CONFIGURATION ERRORS:")
        for error in errors:
            print(f"  • {error}")
        print("\nPlease fix your .env file and try again")
        print("See .env.example for reference\n")
        sys.exit(1)

# ============= REQUIRED CONFIGURATION =============

# Telegram API Credentials
API_ID = get_env_var('API_ID', required=True)
API_HASH = get_env_var('API_HASH', required=True)

# MongoDB Configuration
MONGO_URI = get_env_var('MONGO_URI', required=True)
DB_NAME = get_env_var('DB_NAME', required=True)

# Session Configuration
SESSION_NAME = get_env_var('SESSION_NAME', required=True)

# ============= OPTIONAL CONFIGURATION =============

# Default auto-reply message (optional - will use safe fallback if not provided)
DEFAULT_MESSAGE = get_env_var(
    'DEFAULT_MESSAGE',
    required=False,
    default="Hey! I'm currently away. I'll get back to you soon 😊"
)

# ============= CONSTANTS =============

# Cooldown between replies to same user (seconds)
REPLY_COOLDOWN_SECONDS = 300  # 5 minutes

# Confirmation expiry time (seconds)
CONFIRMATION_EXPIRY_SECONDS = 60  # 1 minute

# Status check interval (seconds)
STATUS_CHECK_INTERVAL_SECONDS = 30  # 30 seconds

# ============= VALIDATION =============

# Validate configuration on import
validate_config()

logger.info("Configuration loaded and validated successfully")

# Log configuration (without sensitive data)
logger.info(f"DB_NAME: {DB_NAME}")
logger.info(f"SESSION_NAME: {SESSION_NAME}")
logger.info(f"REPLY_COOLDOWN: {REPLY_COOLDOWN_SECONDS}s")
logger.info(f"CONFIRMATION_EXPIRY: {CONFIRMATION_EXPIRY_SECONDS}s")
