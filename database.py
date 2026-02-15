"""
MongoDB database operations for the Telegram Userbot.

Handles all database interactions with proper error handling and atomic operations.
UPDATED: Now supports multiple time rules for the same category using rule_id.
"""

import logging
from typing import Optional, List, Dict
from datetime import time

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, OperationFailure

from models import TimeRule, PendingConfirmation, MessageStats, BotState, TempState
from utils import get_ist_date_str

logger = logging.getLogger(__name__)

class Database:
    """MongoDB database manager for userbot state and analytics."""
    
    def __init__(self, mongo_uri: str, db_name: str):
        """
        Initialize database connection.
        
        Args:
            mongo_uri: MongoDB connection URI
            db_name: Database name
        """
        self.client = None
        self.db = None
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        
    def connect(self):
        """Establish connection to MongoDB."""
        try:
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            # Test connection
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            
            # Create indexes
            self._create_indexes()
            
            logger.info(f"Connected to MongoDB: {self.db_name}")
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    def _create_indexes(self):
        """Create database indexes for optimal performance."""
        try:
            # Time rules - UPDATED: Use rule_id for uniqueness instead of category
            # This allows multiple time rules for the same category
            self.db.time_rules.create_index([('owner_id', ASCENDING), ('rule_id', ASCENDING)], unique=True)
            # Additional index for querying by category
            self.db.time_rules.create_index([('owner_id', ASCENDING), ('category', ASCENDING)])
            
            # Message stats - composite index for queries
            self.db.message_stats.create_index([('owner_id', ASCENDING), ('date', DESCENDING)])
            self.db.message_stats.create_index([('owner_id', ASCENDING), ('user_id', ASCENDING), ('date', ASCENDING)])
            
            # Bot state - one document per owner
            self.db.bot_state.create_index([('owner_id', ASCENDING)], unique=True)
            
            # Pending confirmations - one per owner
            self.db.pending_confirmations.create_index([('owner_id', ASCENDING)], unique=True)
            
            # Temp state - one per owner
            self.db.temp_state.create_index([('owner_id', ASCENDING)], unique=True)
            
            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")
    
    def disconnect(self):
        """Close database connection."""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")
    
    # ============= BOT STATE OPERATIONS =============
    
    def get_bot_state(self, owner_id: int) -> Optional[BotState]:
        """Get bot state for owner."""
        try:
            doc = self.db.bot_state.find_one({'owner_id': owner_id})
            if doc:
                return BotState.from_dict(doc)
            return None
        except Exception as e:
            logger.error(f"Failed to get bot state: {e}")
            return None
    
    def save_bot_state(self, state: BotState) -> bool:
        """Save bot state (upsert)."""
        try:
            self.db.bot_state.update_one(
                {'owner_id': state.owner_id},
                {'$set': state.to_dict()},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save bot state: {e}")
            return False
    
    def update_auto_reply_status(self, owner_id: int, enabled: bool) -> bool:
        """Update only the auto-reply enabled status."""
        try:
            result = self.db.bot_state.update_one(
                {'owner_id': owner_id},
                {'$set': {'auto_reply_enabled': enabled}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update auto-reply status: {e}")
            return False
    
    def update_default_message(self, owner_id: int, message: str) -> bool:
        """Update only the default message."""
        try:
            result = self.db.bot_state.update_one(
                {'owner_id': owner_id},
                {'$set': {'default_message': message}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update default message: {e}")
            return False
    
    def update_custom_rules_status(self, owner_id: int, enabled: bool) -> bool:
        """Update only the custom_rules_enabled status."""
        try:
            result = self.db.bot_state.update_one(
                {'owner_id': owner_id},
                {'$set': {'custom_rules_enabled': enabled}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update custom rules status: {e}")
            return False
    
    # ============= TEMP STATE OPERATIONS =============
    
    def get_temp_state(self, owner_id: int) -> Optional[TempState]:
        """Get temp state for owner."""
        try:
            doc = self.db.temp_state.find_one({'owner_id': owner_id})
            if doc:
                return TempState.from_dict(doc)
            return None
        except Exception as e:
            logger.error(f"Failed to get temp state: {e}")
            return None
    
    def save_temp_state(self, state: TempState) -> bool:
        """Save temp state (upsert)."""
        try:
            self.db.temp_state.update_one(
                {'owner_id': state.owner_id},
                {'$set': state.to_dict()},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save temp state: {e}")
            return False
    
    def clear_temp_state(self, owner_id: int) -> bool:
        """Clear temp state."""
        try:
            self.db.temp_state.delete_one({'owner_id': owner_id})
            return True
        except Exception as e:
            logger.error(f"Failed to clear temp state: {e}")
            return False
    
    # ============= TIME RULES OPERATIONS =============
    
    def add_time_rule(self, owner_id: int, rule: TimeRule) -> bool:
        """Add a new time-based rule (allows multiple rules per category)."""
        try:
            doc = rule.to_dict()
            doc['owner_id'] = owner_id
            
            # Insert new rule (rule_id ensures uniqueness)
            self.db.time_rules.insert_one(doc)
            logger.info(f"Added time rule: {rule.category} [{rule.rule_id[:8]}...]")
            return True
        except Exception as e:
            logger.error(f"Failed to add time rule: {e}")
            return False
    
    def get_time_rule_by_id(self, owner_id: int, rule_id: str) -> Optional[TimeRule]:
        """Get a specific time rule by rule_id."""
        try:
            doc = self.db.time_rules.find_one({'owner_id': owner_id, 'rule_id': rule_id})
            if doc:
                return TimeRule.from_dict(doc)
            return None
        except Exception as e:
            logger.error(f"Failed to get time rule: {e}")
            return None
    
    def get_time_rules_by_category(self, owner_id: int, category: str) -> List[TimeRule]:
        """Get all time rules for a specific category."""
        try:
            docs = self.db.time_rules.find({'owner_id': owner_id, 'category': category})
            return [TimeRule.from_dict(doc) for doc in docs]
        except Exception as e:
            logger.error(f"Failed to get time rules for category: {e}")
            return []
    
    def get_all_time_rules(self, owner_id: int) -> List[TimeRule]:
        """Get all time rules for owner."""
        try:
            docs = self.db.time_rules.find({'owner_id': owner_id})
            return [TimeRule.from_dict(doc) for doc in docs]
        except Exception as e:
            logger.error(f"Failed to get time rules: {e}")
            return []
    
    def update_time_rule(self, owner_id: int, rule_id: str, start_time: time, end_time: time) -> bool:
        """Update a specific time rule's time range."""
        try:
            result = self.db.time_rules.update_one(
                {'owner_id': owner_id, 'rule_id': rule_id},
                {'$set': {
                    'start_time': start_time.strftime('%H:%M'),
                    'end_time': end_time.strftime('%H:%M')
                }}
            )
            if result.modified_count > 0:
                logger.info(f"Updated time rule: {rule_id[:8]}...")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to update time rule: {e}")
            return False
    
    def remove_time_rule_by_id(self, owner_id: int, rule_id: str) -> bool:
        """Remove a specific time rule by rule_id."""
        try:
            result = self.db.time_rules.delete_one({'owner_id': owner_id, 'rule_id': rule_id})
            if result.deleted_count > 0:
                logger.info(f"Removed time rule: {rule_id[:8]}...")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to remove time rule: {e}")
            return False
    
    def remove_time_rules_by_category(self, owner_id: int, category: str) -> int:
        """Remove all time rules for a specific category. Returns count of deleted rules."""
        try:
            result = self.db.time_rules.delete_many({'owner_id': owner_id, 'category': category})
            count = result.deleted_count
            logger.info(f"Removed {count} time rules for category: {category}")
            return count
        except Exception as e:
            logger.error(f"Failed to remove time rules for category: {e}")
            return 0
    
    def remove_all_time_rules(self, owner_id: int) -> int:
        """Remove all time rules for owner. Returns count of deleted rules."""
        try:
            result = self.db.time_rules.delete_many({'owner_id': owner_id})
            count = result.deleted_count
            logger.info(f"Removed {count} time rules")
            return count
        except Exception as e:
            logger.error(f"Failed to remove all time rules: {e}")
            return 0
    
    def get_active_rule(self, owner_id: int, current_time: time) -> Optional[TimeRule]:
        """Get the active rule for current time (IST). Returns first matching rule if multiple overlap."""
        from utils import is_time_in_range
        
        rules = self.get_all_time_rules(owner_id)
        for rule in rules:
            if is_time_in_range(current_time, rule.start_time, rule.end_time):
                return rule
        return None
    
    # ============= PENDING CONFIRMATIONS =============
    
    def set_pending_confirmation(self, owner_id: int, confirmation: PendingConfirmation) -> bool:
        """Set a pending confirmation (replaces existing)."""
        try:
            doc = confirmation.to_dict()
            doc['owner_id'] = owner_id
            
            self.db.pending_confirmations.update_one(
                {'owner_id': owner_id},
                {'$set': doc},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Failed to set pending confirmation: {e}")
            return False
    
    def get_pending_confirmation(self, owner_id: int) -> Optional[PendingConfirmation]:
        """Get pending confirmation for owner."""
        try:
            doc = self.db.pending_confirmations.find_one({'owner_id': owner_id})
            if doc:
                return PendingConfirmation.from_dict(doc)
            return None
        except Exception as e:
            logger.error(f"Failed to get pending confirmation: {e}")
            return None
    
    def clear_pending_confirmation(self, owner_id: int) -> bool:
        """Clear pending confirmation."""
        try:
            self.db.pending_confirmations.delete_one({'owner_id': owner_id})
            return True
        except Exception as e:
            logger.error(f"Failed to clear pending confirmation: {e}")
            return False
    
    # ============= MESSAGE ANALYTICS =============
    
    def increment_message_count(self, owner_id: int, user_id: int, date: Optional[str] = None) -> bool:
        """Increment message count for a user on a specific date (IST)."""
        try:
            if date is None:
                date = get_ist_date_str()
            
            self.db.message_stats.update_one(
                {
                    'owner_id': owner_id,
                    'user_id': user_id,
                    'date': date
                },
                {
                    '$inc': {'count': 1},
                    '$setOnInsert': {
                        'owner_id': owner_id,
                        'user_id': user_id,
                        'date': date
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Failed to increment message count: {e}")
            return False
    
    def get_stats_for_date(self, owner_id: int, date: str) -> List[MessageStats]:
        """Get message statistics for a specific date."""
        try:
            docs = self.db.message_stats.find({'owner_id': owner_id, 'date': date})
            return [MessageStats.from_dict(doc) for doc in docs]
        except Exception as e:
            logger.error(f"Failed to get stats for date: {e}")
            return []
    
    def get_stats_for_date_range(self, owner_id: int, start_date: str, end_date: str) -> List[MessageStats]:
        """Get message statistics for a date range."""
        try:
            docs = self.db.message_stats.find({
                'owner_id': owner_id,
                'date': {'$gte': start_date, '$lte': end_date}
            }).sort('date', DESCENDING)
            return [MessageStats.from_dict(doc) for doc in docs]
        except Exception as e:
            logger.error(f"Failed to get stats for date range: {e}")
            return []
    
    def get_daily_summary(self, owner_id: int, date: str) -> Dict:
        """Get aggregated summary for a specific date."""
        try:
            pipeline = [
                {'$match': {'owner_id': owner_id, 'date': date}},
                {'$group': {
                    '_id': None,
                    'total_messages': {'$sum': '$count'},
                    'unique_users': {'$sum': 1}
                }}
            ]
            
            result = list(self.db.message_stats.aggregate(pipeline))
            if result:
                return {
                    'total_messages': result[0]['total_messages'],
                    'unique_users': result[0]['unique_users']
                }
            return {'total_messages': 0, 'unique_users': 0}
        except Exception as e:
            logger.error(f"Failed to get daily summary: {e}")
            return {'total_messages': 0, 'unique_users': 0}
    
    def get_top_user_for_date(self, owner_id: int, date: str) -> Optional[Dict]:
        """Get the user with most messages for a specific date."""
        try:
            doc = self.db.message_stats.find_one(
                {'owner_id': owner_id, 'date': date},
                sort=[('count', DESCENDING)]
            )
            if doc:
                return {'user_id': doc['user_id'], 'count': doc['count']}
            return None
        except Exception as e:
            logger.error(f"Failed to get top user: {e}")
            return None
