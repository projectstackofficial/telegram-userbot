"""
Data models for the Telegram Userbot.

Defines structures for time-based rules, analytics, and state management.
"""

from dataclasses import dataclass, field
from datetime import time, datetime
from typing import Optional
import uuid

@dataclass
class TimeRule:
    """Represents a time-based auto-switch rule."""
    category: str
    start_time: time
    end_time: time
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def to_dict(self) -> dict:
        """Convert to dictionary for MongoDB storage."""
        return {
            'rule_id': self.rule_id,
            'category': self.category,
            'start_time': self.start_time.strftime('%H:%M'),
            'end_time': self.end_time.strftime('%H:%M')
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TimeRule':
        """Create TimeRule from dictionary."""
        from utils import parse_time
        
        start_time = parse_time(data['start_time'])
        end_time = parse_time(data['end_time'])
        
        if start_time is None or end_time is None:
            raise ValueError("Invalid time format in stored rule")
        
        return cls(
            category=data['category'],
            start_time=start_time,
            end_time=end_time,
            rule_id=data.get('rule_id', str(uuid.uuid4()))  # Generate if missing for backward compatibility
        )

@dataclass
class PendingConfirmation:
    """Represents a pending destructive action requiring confirmation."""
    action_type: str  # 'remove_custom' or 'remove_all_custom'
    category: Optional[str]  # Category to remove (None for remove_all)
    rule_id: Optional[str]  # Specific rule ID to remove (None for category-wide or remove_all)
    timestamp: datetime  # When the action was initiated (IST)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'action_type': self.action_type,
            'category': self.category,
            'rule_id': self.rule_id,
            'timestamp': self.timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'PendingConfirmation':
        """Create PendingConfirmation from dictionary."""
        from utils import IST
        
        timestamp = datetime.fromisoformat(data['timestamp'])
        # Ensure timezone is set
        if timestamp.tzinfo is None:
            timestamp = IST.localize(timestamp)
        
        return cls(
            action_type=data['action_type'],
            category=data.get('category'),
            rule_id=data.get('rule_id'),
            timestamp=timestamp
        )

@dataclass
class MessageStats:
    """Represents message statistics for a user on a specific date."""
    owner_id: int
    user_id: int
    date: str  # YYYY-MM-DD format (IST)
    count: int
    
    def to_dict(self) -> dict:
        """Convert to dictionary for MongoDB storage."""
        return {
            'owner_id': self.owner_id,
            'user_id': self.user_id,
            'date': self.date,
            'count': self.count
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'MessageStats':
        """Create MessageStats from dictionary."""
        return cls(
            owner_id=data['owner_id'],
            user_id=data['user_id'],
            date=data['date'],
            count=data['count']
        )

@dataclass
class BotState:
    """Represents the current state of the userbot."""
    owner_id: int
    auto_reply_enabled: bool
    default_message: str
    custom_rules_enabled: bool = False  # Custom time-based rules toggle
    
    def to_dict(self) -> dict:
        """Convert to dictionary for MongoDB storage."""
        return {
            'owner_id': self.owner_id,
            'auto_reply_enabled': self.auto_reply_enabled,
            'default_message': self.default_message,
            'custom_rules_enabled': self.custom_rules_enabled
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'BotState':
        """Create BotState from dictionary."""
        return cls(
            owner_id=data['owner_id'],
            auto_reply_enabled=data['auto_reply_enabled'],
            default_message=data['default_message'],
            custom_rules_enabled=data.get('custom_rules_enabled', False)  # Default to False for backward compatibility
        )

@dataclass
class TempState:
    """Represents temporary reply state."""
    owner_id: int
    temp_active: bool
    temp_category: Optional[str]
    temp_expiry: Optional[datetime]
    saved_rules: list  # List of TimeRule dicts to restore later
    saved_custom_enabled: bool  # Saved custom_rules_enabled state
    
    def to_dict(self) -> dict:
        """Convert to dictionary for MongoDB storage."""
        return {
            'owner_id': self.owner_id,
            'temp_active': self.temp_active,
            'temp_category': self.temp_category,
            'temp_expiry': self.temp_expiry.isoformat() if self.temp_expiry else None,
            'saved_rules': self.saved_rules,
            'saved_custom_enabled': self.saved_custom_enabled
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TempState':
        """Create TempState from dictionary."""
        from utils import IST
        
        temp_expiry = None
        if data.get('temp_expiry'):
            temp_expiry = datetime.fromisoformat(data['temp_expiry'])
            # Ensure timezone is set
            if temp_expiry.tzinfo is None:
                temp_expiry = IST.localize(temp_expiry)
        
        return cls(
            owner_id=data['owner_id'],
            temp_active=data.get('temp_active', False),
            temp_category=data.get('temp_category'),
            temp_expiry=temp_expiry,
            saved_rules=data.get('saved_rules', []),
            saved_custom_enabled=data.get('saved_custom_enabled', False)
        )
