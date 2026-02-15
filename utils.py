"""
Utility functions for the Telegram Userbot.

Includes timezone handling (IST), time parsing, validation, and formatting.
"""

from datetime import datetime, timedelta, time
from typing import Tuple, Optional
import pytz
import re

# IST Timezone (Asia/Kolkata)
IST = pytz.timezone('Asia/Kolkata')

def get_ist_now() -> datetime:
    """
    Get current datetime in IST timezone.
    
    Returns:
        Current datetime in IST
    """
    return datetime.now(IST)

def get_ist_date_str() -> str:
    """
    Get current date in IST as YYYY-MM-DD string.
    
    Returns:
        Date string in YYYY-MM-DD format
    """
    return get_ist_now().strftime('%Y-%m-%d')

def get_ist_time() -> time:
    """
    Get current time in IST.
    
    Returns:
        Current time object in IST
    """
    return get_ist_now().time()

def parse_time(time_str: str) -> Optional[time]:
    """
    Parse time string in HH:MM format.
    
    Args:
        time_str: Time string in HH:MM format (e.g., "09:30", "14:00")
        
    Returns:
        time object if valid, None otherwise
    """
    try:
        parts = time_str.strip().split(':')
        if len(parts) != 2:
            return None
        
        hour = int(parts[0])
        minute = int(parts[1])
        
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        
        return time(hour, minute)
    except (ValueError, AttributeError):
        return None

def parse_time_range(range_str: str) -> Optional[Tuple[time, time]]:
    """
    Parse time range string in format HH:MM-HH:MM.
    
    Args:
        range_str: Time range string (e.g., "09:00-17:00", "22:00-06:00")
        
    Returns:
        Tuple of (start_time, end_time) if valid, None otherwise
    """
    try:
        # Remove whitespace
        range_str = range_str.strip()
        
        # Split by dash or hyphen
        parts = re.split(r'[-–—]', range_str)
        if len(parts) != 2:
            return None
        
        start_time = parse_time(parts[0])
        end_time = parse_time(parts[1])
        
        if start_time is None or end_time is None:
            return None
        
        return (start_time, end_time)
    except Exception:
        return None

def is_time_in_range(check_time: time, start_time: time, end_time: time) -> bool:
    """
    Check if a time falls within a time range.
    Handles midnight crossing (e.g., 22:00-06:00).
    
    Args:
        check_time: Time to check
        start_time: Range start time
        end_time: Range end time
        
    Returns:
        True if check_time is within the range, False otherwise
    """
    if start_time <= end_time:
        # Normal range (e.g., 09:00-17:00)
        return start_time <= check_time <= end_time
    else:
        # Crosses midnight (e.g., 22:00-06:00)
        return check_time >= start_time or check_time <= end_time

def format_time_range(start_time: time, end_time: time) -> str:
    """
    Format a time range as HH:MM-HH:MM string.
    
    Args:
        start_time: Start time
        end_time: End time
        
    Returns:
        Formatted time range string
    """
    return f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}"

def get_ist_timestamp() -> datetime:
    """
    Get current timestamp in IST for expiry checks.
    
    Returns:
        Current datetime in IST
    """
    return get_ist_now()

def is_expired(timestamp: datetime, expiry_seconds: int = 60) -> bool:
    """
    Check if a timestamp has expired (IST-based).
    
    Args:
        timestamp: The timestamp to check (should be IST)
        expiry_seconds: Number of seconds until expiry (default 60)
        
    Returns:
        True if expired, False otherwise
    """
    now = get_ist_now()
    # Make timestamp timezone-aware if it isn't
    if timestamp.tzinfo is None:
        timestamp = IST.localize(timestamp)
    
    elapsed = (now - timestamp).total_seconds()
    return elapsed >= expiry_seconds

def get_week_date_range() -> Tuple[str, str]:
    """
    Get the date range for the last 7 days (IST).
    
    Returns:
        Tuple of (start_date, end_date) in YYYY-MM-DD format
    """
    today = get_ist_now().date()
    start_date = today - timedelta(days=6)
    return (start_date.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'))

def validate_time_command_format(command_text: str) -> bool:
    """
    Validate format for custom time commands.
    Expected: HH:MM-HH:MM category
    
    Args:
        command_text: Command text after /custom
        
    Returns:
        True if valid format, False otherwise
    """
    parts = command_text.strip().split()
    if len(parts) != 2:
        return False
    
    time_range = parse_time_range(parts[0])
    return time_range is not None

def format_seconds_to_time(seconds: int) -> str:
    """
    Format seconds into human-readable time string.
    
    Args:
        seconds: Number of seconds
        
    Returns:
        Formatted string (e.g., "2h 30m", "45m", "30s")
    """
    if seconds < 60:
        return f"{seconds}s"
    
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    
    hours = minutes // 60
    remaining_minutes = minutes % 60
    
    if remaining_minutes > 0:
        return f"{hours}h {remaining_minutes}m"
    return f"{hours}h"

def get_time_until_expiry(timestamp: datetime, expiry_seconds: int = 60) -> str:
    """
    Get formatted time remaining until expiry.
    
    Args:
        timestamp: The timestamp (IST)
        expiry_seconds: Expiry duration in seconds
        
    Returns:
        Formatted time remaining (e.g., "45s remaining")
    """
    now = get_ist_now()
    if timestamp.tzinfo is None:
        timestamp = IST.localize(timestamp)
    
    elapsed = (now - timestamp).total_seconds()
    remaining = max(0, expiry_seconds - int(elapsed))
    
    if remaining == 0:
        return "expired"
    
    return f"{remaining}s remaining"
