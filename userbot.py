"""
Advanced Telegram Userbot with Smart Auto-Reply System.

Features:
- Time-based auto-switching (IST)
- MongoDB persistence
- Predefined categories
- Custom time commands with confirmation system
- Message analytics with IST tracking
- Human-like messages with proper cooldown
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict

from telethon import TelegramClient, events
from telethon.tl.types import User, UserStatusOnline, UserStatusOffline, UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth
from telethon.errors import SessionPasswordNeededError

import config
import categories
from database import Database
from models import TimeRule, PendingConfirmation, BotState, TempState
from utils import (
    get_ist_now, get_ist_time, get_ist_date_str, get_ist_timestamp,
    parse_time_range, format_time_range, is_time_in_range,
    is_expired, get_week_date_range, get_time_until_expiry
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TelegramUserbot:
    """Advanced Telegram Userbot with time-based auto-replies and analytics."""
    
    def __init__(self, database: Database):
        """
        Initialize the userbot client.
        
        Args:
            database: Database instance for persistence
        """
        self.client = TelegramClient(
            session=config.SESSION_NAME,
            api_id=config.API_ID,
            api_hash=config.API_HASH
        )
        
        self.db = database
        
        # State management (loaded from DB on start)
        self.owner_id: Optional[int] = None
        self.auto_reply_enabled: bool = False
        self.custom_rules_enabled: bool = False  # Custom time-based rules toggle (disabled by default)
        self.default_message: str = config.DEFAULT_MESSAGE
        
        # Online status tracking
        self.owner_last_seen: Optional[datetime] = None
        self.owner_actually_online = False
        
        # User reply tracking (cooldown)
        self.recently_replied_users: Dict[int, datetime] = {}
        self.reply_cooldown = config.REPLY_COOLDOWN_SECONDS
        
        # Status check intervals
        self.last_status_check = get_ist_now()
        self.status_check_interval = config.STATUS_CHECK_INTERVAL_SECONDS
        
        # Register event handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all event handlers."""
        
        # Command handler for Saved Messages - ONLY from owner
        @self.client.on(events.NewMessage(pattern=r'^/'))
        async def command_handler(event):
            """Handle commands ONLY from owner in Saved Messages"""
            await self._handle_command(event)
        
        # Auto-reply handler for private messages
        @self.client.on(events.NewMessage(incoming=True))
        async def auto_reply_handler(event):
            """Handle auto-reply for incoming private messages"""
            await self._handle_auto_reply(event)
    
    # ============= STATE MANAGEMENT =============
    
    def _load_state_from_db(self):
        """Load bot state from database."""
        if not self.owner_id:
            return
        
        state = self.db.get_bot_state(self.owner_id)
        if state:
            self.auto_reply_enabled = state.auto_reply_enabled
            self.default_message = state.default_message
            self.custom_rules_enabled = state.custom_rules_enabled
            logger.info("Loaded state from database")
        else:
            # Initialize default state
            self._save_state_to_db()
            logger.info("Initialized default state in database")
    
    def _save_state_to_db(self):
        """Save current state to database."""
        if not self.owner_id:
            return
        
        state = BotState(
            owner_id=self.owner_id,
            auto_reply_enabled=self.auto_reply_enabled,
            default_message=self.default_message,
            custom_rules_enabled=self.custom_rules_enabled
        )
        self.db.save_bot_state(state)
    
    # ============= AUTO-REPLY MESSAGE LOGIC =============
    
    def _get_current_auto_reply_message(self) -> str:
        """
        Get the appropriate auto-reply message based on current time (IST).
        
        Priority:
        1. Temp reply (if active and not expired)
        2. Active time-based rule (if IST time matches AND custom rules enabled)
        3. Default message (from DB or config)
        
        Returns:
            The message to send
        """
        # Check for temp mode first
        temp_state = self.db.get_temp_state(self.owner_id)
        if temp_state and temp_state.temp_active:
            # Check if expired (only if expiry is set)
            if temp_state.temp_expiry:
                current_time = get_ist_now()
                if current_time < temp_state.temp_expiry:
                    # Temp mode is active and not expired
                    message = categories.get_category_message(temp_state.temp_category)
                    logger.debug(f"Using temp reply message for category: {temp_state.temp_category}")
                    return message
                else:
                    # Temp mode expired - auto reset
                    logger.info("Temp mode expired - auto resetting")
                    asyncio.create_task(self._reset_temp_mode())
            else:
                # No expiry set - temp mode is permanently active until manual reset
                message = categories.get_category_message(temp_state.temp_category)
                logger.debug(f"Using temp reply message for category: {temp_state.temp_category}")
                return message
        
        current_time = get_ist_time()
        
        # Check for active time-based rule (only if custom rules are enabled)
        if self.custom_rules_enabled:
            active_rule = self.db.get_active_rule(self.owner_id, current_time)
            if active_rule:
                message = categories.get_category_message(active_rule.category)
                logger.debug(f"Using time-based message for category: {active_rule.category}")
                return message
        
        # Use default message
        logger.debug("Using default message (no active time rule or custom rules disabled)")
        return self.default_message
    
    # ============= COMMAND HANDLER =============
    
    async def _handle_command(self, event):
        """Process commands ONLY from owner in Saved Messages."""
        
        # Get sender
        sender = await event.get_sender()
        if not sender:
            return
        
        # Check if from owner
        if not self._is_owner(sender.id):
            # If it's a private message and auto-reply is enabled, treat as regular message
            if event.is_private and self.auto_reply_enabled:
                event._handled = False  # Let it be handled by auto-reply
            return
        
        # Check if from Saved Messages
        if not await self._is_saved_messages(event):
            return
        
        # Mark as handled
        event._handled = True
        
        # Parse command
        message_text = event.message.message.strip()
        parts = message_text.split(None, 1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else None
        
        # Route to appropriate handler
        command_map = {
            '/start': self._cmd_start,
            '/help': self._cmd_help,
            '/status': self._cmd_status,
            '/on': self._cmd_on,
            '/off': self._cmd_off,
            '/set': self._cmd_set,
            '/custom': self._cmd_custom,
            '/customedit': self._cmd_customedit,
            '/listcustom': self._cmd_listcustom,
            '/removecustom': self._cmd_removecustom,
            '/customremoveall': self._cmd_customremoveall,
            '/customon': self._cmd_customon,
            '/customoff': self._cmd_customoff,
            '/temp': self._cmd_temp,
            '/listtemp': self._cmd_listtemp,
            '/tempreset': self._cmd_tempreset,
            '/confirm': self._cmd_confirm,
            '/cancel': self._cmd_cancel,
            '/stats': self._cmd_stats,
            '/categories': self._cmd_categories,
        }
        
        handler = command_map.get(command)
        if handler:
            await handler(event, arg)
        else:
            await event.reply(f"❌ Unknown command: {command}\n\nUse /help to see available commands.")
    
    # ============= COMMAND IMPLEMENTATIONS =============
    
    async def _cmd_start(self, event, arg):
        """Handle /start command."""
        is_online = await self._is_owner_actually_online()
        status_text = "🟢 Online" if is_online else "🔴 Offline"
        
        # Get current message
        current_msg = self._get_current_auto_reply_message()
        is_default = (current_msg == self.default_message)
        msg_type = "default" if is_default else "time-based"
        
        welcome = f"""
🤖 **Smart Telegram Userbot**

👤 **Owner:** {event.sender.first_name or ''} {event.sender.last_name or ''}
🆔 **ID:** `{self.owner_id}`
📊 **Auto-reply:** {'🟢 Enabled' if self.auto_reply_enabled else '🔴 Disabled'}
🎯 **Custom Rules:** {'🟢 Enabled' if self.custom_rules_enabled else '🔴 Disabled'}
👁️ **Status:** {status_text}

**Current Message ({msg_type}):**
`{current_msg}`

**Key Features:**
✅ Time-based auto-switching (IST)
✅ Message analytics tracking
✅ Confirmation system for safety
✅ Human-like responses

**Quick Commands:**
• `/help` - Full command list
• `/status` - Check your status
• `/custom HH:MM-HH:MM category` - Add time rule
• `/stats today` - View today's stats

⚠️ **Security:** Commands only work in Saved Messages
        """
        
        await event.reply(welcome)
    
    async def _cmd_help(self, event, arg):
        """Handle /help command."""
        help_text = """
📚 **Userbot Command Guide**

**Basic Commands:**
• `/start` - Show welcome message
• `/help` - Show this guide
• `/status` - Check your online status
• `/on` - Enable auto-reply
• `/off` - Disable auto-reply
• `/set <message>` - Set default auto-reply message

**Temporary Reply Mode:**
• `/temp <category>` - Activate temp reply (deactivates all rules)
  Example: `/temp lunch`
• `/listtemp` - Show current temp mode status
• `/tempreset` - Deactivate temp mode & restore saved rules

**Time-Based Auto-Switch (IST):**
• `/custom HH:MM-HH:MM category` - Add time rule
  Example: `/custom 09:00-17:00 work`
  💡 **Tip:** You can add multiple rules for the same category!
• `/customedit <rule_id> HH:MM-HH:MM` - Edit existing rule
  Example: `/customedit a1b2c3d4 08:30-17:30`
• `/listcustom` - List all your time rules (grouped by category)
• `/removecustom <rule_id|category>` - Remove rule(s)
  • `/removecustom a1b2c3d4` - Remove specific rule
  • `/removecustom work` - Remove ALL 'work' rules (⚠️ requires confirmation)
• `/customremoveall` - Remove all rules (⚠️ requires confirmation)
• `/customon` - Enable custom time-based rules
• `/customoff` - Disable custom time-based rules

**Categories:**
• `/categories` - View all available categories

**Analytics:**
• `/stats today` - View today's message stats
• `/stats week` - View last 7 days stats

**Confirmation System:**
• `/confirm` - Confirm pending destructive action
• `/cancel` - Cancel pending action
• ⏱️  Confirmations auto-expire after 1 minute

**How Auto-Reply Works:**
1. When enabled, bot checks your REAL online status
2. If offline, gets appropriate message:
   • Temp reply (if active) OR
   • Active time rule (IST-based) OR
   • Default message (fallback)
3. Sends human-like reply with 5-min cooldown per user
4. Tracks all messages for analytics

**Temp Mode Feature:**
When you activate temp mode with `/temp <category>`:
• All custom time rules are saved and deactivated
• Only the temp category message is used
• To change category, use `/temp <new_category>`
• Use `/tempreset` to restore all saved rules

**Time-Based Switching:**
Bot automatically picks category message based on IST time.
You can add multiple time slots for the same category (e.g., split shifts).
Example: work 09:00-12:00, work 14:00-18:00, work 20:00-22:00
If multiple rules overlap, the first matching rule is used.
Outside time rules, it uses your default message.

**Message Priority:**
1. Temp reply (if active)
2. Active time rule (if IST time matches & custom rules enabled)
3. Default message (set via /set or DB)

⚠️ **Important:** Commands only work in Saved Messages for security.
        """
        
        await event.reply(help_text)
    
    async def _cmd_status(self, event, arg):
        """Handle /status command."""
        is_online = await self._is_owner_actually_online()
        
        # Format last seen
        last_seen_text = ""
        if self.owner_last_seen:
            time_diff = get_ist_now() - self.owner_last_seen
            hours = int(time_diff.total_seconds() // 3600)
            minutes = int((time_diff.total_seconds() % 3600) // 60)
            
            if is_online:
                last_seen_text = "You are currently active"
            else:
                if hours > 0:
                    last_seen_text = f"Last seen {hours}h {minutes}m ago"
                else:
                    last_seen_text = f"Last seen {minutes}m ago"
        
        # Get current message
        current_msg = self._get_current_auto_reply_message()
        is_default = (current_msg == self.default_message)
        
        # Check temp mode
        temp_state = self.db.get_temp_state(self.owner_id)
        temp_info = ""
        msg_type = "Default"
        
        if temp_state and temp_state.temp_active:
            msg_type = f"Temp ({temp_state.temp_category})"
            temp_info = f"\n**Temp Mode:** 🟢 Active (`{temp_state.temp_category}`)"
        else:
            # Get active rule if any
            active_rule = self.db.get_active_rule(self.owner_id, get_ist_time())
            if active_rule and self.custom_rules_enabled:
                msg_type = f"Time-based ({active_rule.category})"
                temp_info = f"\n**Active Rule:** `{active_rule.category}` ({format_time_range(active_rule.start_time, active_rule.end_time)})"
        
        status_icon = "🟢" if is_online else "🔴"
        status_word = "ONLINE" if is_online else "OFFLINE"
        
        status_msg = f"""
{status_icon} **You are {status_word}**

{last_seen_text}

**Auto-reply:** {'🟢 Enabled' if self.auto_reply_enabled else '🔴 Disabled'}
**Custom Rules:** {'🟢 Enabled' if self.custom_rules_enabled else '🔴 Disabled'}
**Current Message:** {msg_type}
`{current_msg}`{temp_info}

**Behavior:**
• Auto-reply: {'Active when you\'re offline' if self.auto_reply_enabled else 'Disabled'}
• Cooldown: {self.reply_cooldown // 60} minutes per user
• Users in cooldown: {len(self.recently_replied_users)}
        """
        
        await event.reply(status_msg)
    
    async def _cmd_on(self, event, arg):
        """Handle /on command."""
        if self.auto_reply_enabled:
            await event.reply("⚠️ Auto-reply is already enabled.")
            return
        
        self.auto_reply_enabled = True
        self.custom_rules_enabled = False  # Disable custom rules by default when enabling auto-reply
        self._save_state_to_db()
        
        current_msg = self._get_current_auto_reply_message()
        
        response = f"""
✅ **Auto-reply ENABLED**

**Current Message (Default):**
`{current_msg}`

The bot will now reply to messages when you're offline using your default message.
💡 Use `/customon` to enable time-based rules if needed.
        """
        
        await event.reply(response)
        logger.info(f"Owner {self.owner_id} enabled auto-reply (custom rules disabled by default)")
    
    async def _cmd_off(self, event, arg):
        """Handle /off command."""
        if not self.auto_reply_enabled:
            await event.reply("⚠️ Auto-reply is already disabled.")
            return
        
        self.auto_reply_enabled = False
        self.custom_rules_enabled = False  # Also disable custom rules when turning off auto-reply
        self._save_state_to_db()
        
        await event.reply("""
🔴 **Auto-reply DISABLED**

The bot will no longer send automatic replies.
Custom rules have also been disabled.

Use `/on` to enable auto-reply again (with default message).
        """)
        
        logger.info(f"Owner {self.owner_id} disabled auto-reply and custom rules")
    
    async def _cmd_set(self, event, arg):
        """Handle /set command."""
        if not arg or arg.strip() == '':
            await event.reply("❌ Please provide a message.\n\nUsage: `/set Your message here`")
            return
        
        # Update default message
        self.default_message = arg.strip()
        self.auto_reply_enabled = True
        self._save_state_to_db()
        
        response = f"""
✅ **Default message set and auto-reply enabled!**

**New Default Message:**
`{self.default_message}`

**Status:** 🟢 Auto-reply ON

This message will be used when no time-based rule is active.
        """
        
        await event.reply(response)
        logger.info(f"Owner {self.owner_id} set default message")
    
    async def _cmd_custom(self, event, arg):
        """Handle /custom HH:MM-HH:MM category command."""
        if not arg:
            await event.reply("""
❌ **Invalid format**

**Usage:** `/custom HH:MM-HH:MM category`

**Example:** `/custom 09:00-17:00 work`

This sets a time rule that automatically uses the category message during specified hours (IST).

💡 **Tip:** You can add multiple time slots for the same category!
Example: `/custom 09:00-12:00 work` and `/custom 14:00-18:00 work`
            """)
            return
        
        parts = arg.strip().split()
        if len(parts) != 2:
            await event.reply("❌ Invalid format. Use: `/custom HH:MM-HH:MM category`")
            return
        
        time_range_str, category = parts
        
        # Validate category
        if not categories.is_valid_category(category):
            await event.reply(f"""
❌ **Invalid category:** `{category}`

Use `/categories` to see all available categories.
            """)
            return
        
        # Parse time range
        time_range = parse_time_range(time_range_str)
        if not time_range:
            await event.reply(f"""
❌ **Invalid time format:** `{time_range_str}`

Time must be in format HH:MM-HH:MM (24-hour format)
Example: 09:00-17:00 or 22:00-06:00
            """)
            return
        
        start_time, end_time = time_range
        
        # Create and save rule
        rule = TimeRule(category=category, start_time=start_time, end_time=end_time)
        success = self.db.add_time_rule(self.owner_id, rule)
        
        if success:
            category_msg = categories.get_category_message(category)
            
            # Check how many rules exist for this category now
            category_rules = self.db.get_time_rules_by_category(self.owner_id, category)
            
            response = f"""
✅ **Time rule added successfully!**

**Category:** `{category}`
**Time:** {format_time_range(start_time, end_time)} IST
**Rule ID:** `{rule.rule_id[:8]}`
**Message:** `{category_msg}`
"""
            
            if len(category_rules) > 1:
                response += f"\n📊 You now have {len(category_rules)} rules for category `{category}`"
            
            response += "\n\nDuring this time, auto-replies will use this category message."
            
            await event.reply(response)
            logger.info(f"Added time rule: {category} {format_time_range(start_time, end_time)} [{rule.rule_id[:8]}]")
        else:
            await event.reply("❌ Failed to save time rule. Please try again.")
    
    async def _cmd_customedit(self, event, arg):
        """Handle /customedit <rule_id> HH:MM-HH:MM command."""
        if not arg:
            await event.reply("""
❌ **Invalid format**

**Usage:** `/customedit <rule_id> HH:MM-HH:MM`

**Example:** `/customedit a1b2c3d4 08:30-17:30`

Use `/listcustom` to see rule IDs.
            """)
            return
        
        parts = arg.strip().split()
        if len(parts) != 2:
            await event.reply("❌ Invalid format. Use: `/customedit <rule_id> HH:MM-HH:MM`")
            return
        
        rule_id_input, time_range_str = parts
        
        # Find the rule by ID (support partial ID)
        rule = self.db.get_time_rule_by_id(self.owner_id, rule_id_input)
        
        if not rule:
            # Try partial match
            all_rules = self.db.get_all_time_rules(self.owner_id)
            matching_rules = [r for r in all_rules if r.rule_id.startswith(rule_id_input)]
            
            if len(matching_rules) == 1:
                rule = matching_rules[0]
            elif len(matching_rules) > 1:
                await event.reply(f"""
❌ **Ambiguous rule ID**

Multiple rules match `{rule_id_input}`:
""" + "\n".join([f"• {r.rule_id[:8]} - {r.category} {format_time_range(r.start_time, r.end_time)}" for r in matching_rules[:5]]) + """

Please provide more characters to uniquely identify the rule.
                """)
                return
            else:
                await event.reply(f"""
❌ **Rule not found**

No time rule found with ID: `{rule_id_input}`

Use `/listcustom` to see all your rules.
                """)
                return
        
        # Parse new time range
        time_range = parse_time_range(time_range_str)
        if not time_range:
            await event.reply(f"""
❌ **Invalid time format:** `{time_range_str}`

Time must be in format HH:MM-HH:MM (24-hour format)
Example: 09:00-17:00 or 22:00-06:00
            """)
            return
        
        start_time, end_time = time_range
        
        # Update rule
        success = self.db.update_time_rule(self.owner_id, rule.rule_id, start_time, end_time)
        
        if success:
            old_range = format_time_range(rule.start_time, rule.end_time)
            new_range = format_time_range(start_time, end_time)
            
            await event.reply(f"""
✅ **Time rule updated!**

**Category:** `{rule.category}`
**Rule ID:** `{rule.rule_id[:8]}`
**Old Time:** {old_range} IST
**New Time:** {new_range} IST

The rule has been updated successfully.
            """)
            logger.info(f"Updated time rule: {rule.rule_id[:8]} ({rule.category}) {old_range} → {new_range}")
        else:
            await event.reply("❌ Failed to update time rule.")
    
    async def _cmd_listcustom(self, event, arg):
        """Handle /listcustom command."""
        rules = self.db.get_all_time_rules(self.owner_id)
        
        if not rules:
            await event.reply("""
📋 **No custom time rules set**

You haven't added any time-based rules yet.

Use `/custom HH:MM-HH:MM category` to add a rule.
Example: `/custom 09:00-17:00 work`

💡 **Tip:** You can add multiple time slots for the same category!
            """)
            return
        
        # Group rules by category
        rules_by_category = {}
        for rule in rules:
            if rule.category not in rules_by_category:
                rules_by_category[rule.category] = []
            rules_by_category[rule.category].append(rule)
        
        # Format rules list
        lines = ["📋 **Your Custom Time Rules (IST):**\n"]
        
        for category in sorted(rules_by_category.keys()):
            category_rules = sorted(rules_by_category[category], key=lambda r: r.start_time)
            count = len(category_rules)
            
            lines.append(f"🔷 **{category}** ({count} rule{'s' if count > 1 else ''})")
            
            for rule in category_rules:
                time_range = format_time_range(rule.start_time, rule.end_time)
                rule_id_short = rule.rule_id[:8]
                lines.append(f"  • {time_range} IST [`{rule_id_short}`]")
            
            lines.append("")
        
        lines.append(f"**Total:** {len(rules)} rule{'s' if len(rules) != 1 else ''}")
        lines.append(f"**Categories:** {len(rules_by_category)}")
        lines.append("\n💡 **Usage:**")
        lines.append("• `/removecustom <rule_id>` - Remove specific rule")
        lines.append("• `/removecustom <category>` - Remove all rules for category")
        lines.append("• `/customedit <rule_id> HH:MM-HH:MM` - Edit rule time")
        
        await event.reply("\n".join(lines))
    
    async def _cmd_removecustom(self, event, arg):
        """Handle /removecustom <rule_id|category> command (requires confirmation)."""
        if not arg:
            await event.reply("""
❌ **Please specify a rule ID or category**

**Usage:**
• `/removecustom <rule_id>` - Remove specific rule
• `/removecustom <category>` - Remove ALL rules for category

**Example:**
• `/removecustom a1b2c3d4` - Remove rule with ID a1b2c3d4
• `/removecustom work` - Remove all 'work' rules

Use `/listcustom` to see rule IDs and categories.
            """)
            return
        
        identifier = arg.strip()
        
        # Check if it's a rule_id (8 characters) or category
        if len(identifier) == 8:
            # Try to find rule by ID
            rule = self.db.get_time_rule_by_id(self.owner_id, identifier)
            
            # If not found, might be searching with partial ID, try to find full ID
            if not rule:
                all_rules = self.db.get_all_time_rules(self.owner_id)
                matching_rules = [r for r in all_rules if r.rule_id.startswith(identifier)]
                
                if len(matching_rules) == 1:
                    rule = matching_rules[0]
                elif len(matching_rules) > 1:
                    await event.reply(f"""
❌ **Ambiguous rule ID**

Multiple rules match `{identifier}`:
""" + "\n".join([f"• {r.rule_id[:8]} - {r.category} {format_time_range(r.start_time, r.end_time)}" for r in matching_rules[:5]]) + """

Please provide more characters to uniquely identify the rule.
                    """)
                    return
            
            if rule:
                # Removing specific rule
                confirmation = PendingConfirmation(
                    action_type='remove_custom',
                    category=rule.category,
                    rule_id=rule.rule_id,
                    timestamp=get_ist_timestamp()
                )
                
                self.db.set_pending_confirmation(self.owner_id, confirmation)
                
                time_range = format_time_range(rule.start_time, rule.end_time)
                
                await event.reply(f"""
⚠️ **Confirmation Required**

You are about to remove this time rule:
**Category:** `{rule.category}`
**Time:** {time_range} IST
**Rule ID:** `{rule.rule_id[:8]}`

**This action cannot be undone.**

Reply with:
• `/confirm` to proceed
• `/cancel` to abort

⏱️  This confirmation expires in 1 minute.
                """)
                
                logger.info(f"Pending confirmation: remove rule '{rule.rule_id[:8]}' ({rule.category})")
                return
        
        # Not a rule ID or rule not found - treat as category
        category = identifier
        rules = self.db.get_time_rules_by_category(self.owner_id, category)
        
        if not rules:
            await event.reply(f"""
❌ **No rules found**

No time rules found for:
• Rule ID: `{identifier}`
• Category: `{category}`

Use `/listcustom` to see all your rules.
            """)
            return
        
        # Removing all rules for a category
        confirmation = PendingConfirmation(
            action_type='remove_custom_category',
            category=category,
            rule_id=None,
            timestamp=get_ist_timestamp()
        )
        
        self.db.set_pending_confirmation(self.owner_id, confirmation)
        
        # Show all rules that will be removed
        rules_list = "\n".join([
            f"  • {format_time_range(r.start_time, r.end_time)} IST [`{r.rule_id[:8]}`]"
            for r in sorted(rules, key=lambda r: r.start_time)
        ])
        
        await event.reply(f"""
⚠️ **Confirmation Required**

You are about to remove **ALL {len(rules)} rule{'s' if len(rules) != 1 else ''}** for category: `{category}`

{rules_list}

**This action cannot be undone.**

Reply with:
• `/confirm` to proceed
• `/cancel` to abort

⏱️  This confirmation expires in 1 minute.
        """)
        
        logger.info(f"Pending confirmation: remove all rules for category '{category}' ({len(rules)} rules)")
    
    async def _cmd_customremoveall(self, event, arg):
        """Handle /customremoveall command (requires confirmation)."""
        rules = self.db.get_all_time_rules(self.owner_id)
        
        if not rules:
            await event.reply("ℹ️ You don't have any custom time rules to remove.")
            return
        
        # Create pending confirmation
        confirmation = PendingConfirmation(
            action_type='remove_all_custom',
            category=None,
            timestamp=get_ist_timestamp()
        )
        
        self.db.set_pending_confirmation(self.owner_id, confirmation)
        
        await event.reply(f"""
⚠️ **DANGER: Confirmation Required**

You are about to remove **ALL {len(rules)} time rules**.

**This action cannot be undone.**

Reply with:
• `/confirm` to proceed
• `/cancel` to abort

⏱️  This confirmation expires in 1 minute.
        """)
        
        logger.info(f"Pending confirmation: remove all custom rules ({len(rules)} rules)")
    
    async def _cmd_confirm(self, event, arg):
        """Handle /confirm command."""
        # Get pending confirmation
        confirmation = self.db.get_pending_confirmation(self.owner_id)
        
        if not confirmation:
            await event.reply("ℹ️ No pending action to confirm.")
            return
        
        # Check if expired
        if is_expired(confirmation.timestamp, config.CONFIRMATION_EXPIRY_SECONDS):
            self.db.clear_pending_confirmation(self.owner_id)
            await event.reply("""
⏱️ **Confirmation Expired**

The pending action has expired. Please try again if needed.
            """)
            logger.info("Confirmation expired")
            return
        
        # Execute the action
        if confirmation.action_type == 'remove_custom':
            # Remove specific rule by ID
            if confirmation.rule_id:
                success = self.db.remove_time_rule_by_id(self.owner_id, confirmation.rule_id)
                if success:
                    await event.reply(f"""
✅ **Time rule removed**

Rule `{confirmation.rule_id[:8]}` from category `{confirmation.category}` has been removed successfully.
                    """)
                    logger.info(f"Removed custom rule: {confirmation.rule_id[:8]} ({confirmation.category})")
                else:
                    await event.reply("❌ Failed to remove time rule.")
            else:
                # Legacy support - shouldn't happen with new system
                await event.reply("❌ Invalid confirmation data.")
        
        elif confirmation.action_type == 'remove_custom_category':
            # Remove all rules for a category
            count = self.db.remove_time_rules_by_category(self.owner_id, confirmation.category)
            if count > 0:
                await event.reply(f"""
✅ **Category rules removed**

Removed {count} rule{'s' if count != 1 else ''} for category `{confirmation.category}`.
                """)
                logger.info(f"Removed all rules for category '{confirmation.category}': {count} total")
            else:
                await event.reply("ℹ️ No rules were found to remove.")
        
        elif confirmation.action_type == 'remove_all_custom':
            count = self.db.remove_all_time_rules(self.owner_id)
            if count > 0:
                await event.reply(f"""
✅ **All time rules removed**

Removed {count} custom time rules.
Your default message will now be used for all auto-replies.
                """)
                logger.info(f"Removed all custom rules: {count} total")
            else:
                await event.reply("ℹ️ No rules were found to remove.")
        
        # Clear confirmation
        self.db.clear_pending_confirmation(self.owner_id)
    
    async def _cmd_cancel(self, event, arg):
        """Handle /cancel command."""
        confirmation = self.db.get_pending_confirmation(self.owner_id)
        
        if not confirmation:
            await event.reply("ℹ️ No pending action to cancel.")
            return
        
        # Clear confirmation
        self.db.clear_pending_confirmation(self.owner_id)
        
        await event.reply("""
🚫 **Action Cancelled**

The pending action has been cancelled. No changes were made.
        """)
        
        logger.info("Confirmation cancelled by user")
    
    async def _cmd_customon(self, event, arg):
        """Handle /customon command - Enable custom time-based rules."""
        # Check if temp mode is active
        temp_state = self.db.get_temp_state(self.owner_id)
        if temp_state and temp_state.temp_active:
            await event.reply(f"""
⚠️ **Cannot Enable Custom Rules**

Temporary reply mode is currently active with category `{temp_state.temp_category}`.

Please run `/tempreset` first to deactivate temp mode before enabling custom rules.
            """)
            logger.info("Blocked /customon - temp mode is active")
            return
        
        if self.custom_rules_enabled:
            await event.reply("""
ℹ️ **Custom Rules Already Enabled**

Time-based custom rules are already active.
            """)
            return
        
        self.custom_rules_enabled = True
        self.db.update_custom_rules_status(self.owner_id, True)  # Save to database
        
        # Get active rules count
        rules = self.db.get_all_time_rules(self.owner_id)
        rules_count = len(rules)
        
        await event.reply(f"""
✅ **Custom Rules Enabled**

Time-based auto-reply rules are now active.
📊 Active rules: {rules_count}

Your bot will now use custom messages based on time ranges when available.
            """)
        
        logger.info(f"Custom rules enabled ({rules_count} rules active)")
    
    async def _cmd_customoff(self, event, arg):
        """Handle /customoff command - Disable custom time-based rules."""
        if not self.custom_rules_enabled:
            await event.reply("""
ℹ️ **Custom Rules Already Disabled**

Time-based custom rules are already inactive.
            """)
            return
        
        self.custom_rules_enabled = False
        self.db.update_custom_rules_status(self.owner_id, False)  # Save to database
        
        await event.reply("""
✅ **Custom Rules Disabled**

Time-based auto-reply rules are now inactive.

Your bot will now use only the default message for all auto-replies.
You can re-enable custom rules with `/customon`.
            """)
        
        logger.info("Custom rules disabled")
    
    async def _cmd_temp(self, event, arg):
        """Handle /temp <category> command - Activate temporary reply mode."""
        if not arg:
            await event.reply("""
❌ **Please specify a category**

**Usage:** `/temp <category>`

**Example:**
• `/temp lunch` - Temporarily use 'lunch' reply
• `/temp meetings` - Temporarily use 'meetings' reply

Use `/categories` to see all available categories.
Use `/listtemp` to check current temp status.
Use `/tempreset` to deactivate temp mode.
            """)
            return
        
        category = arg.strip().lower()
        
        # Validate category
        if not categories.is_valid_category(category):
            await event.reply(f"""
❌ **Invalid category: `{category}`**

Use `/categories` to see all available categories.
            """)
            return
        
        # Get current temp state
        temp_state = self.db.get_temp_state(self.owner_id)
        
        # If temp mode is already active, update category
        if temp_state and temp_state.temp_active:
            # Update to new category
            temp_state.temp_category = category
            temp_state.temp_expiry = None  # No expiry for manually set temp
            
            self.db.save_temp_state(temp_state)
            
            message = categories.get_category_message(category)
            await event.reply(f"""
🔄 **Temp Mode Updated**

**Category:** `{category}`
**Current Message:** {message}

All custom time rules remain deactivated.
Use `/tempreset` to restore normal operation.
            """)
            logger.info(f"Updated temp mode to category: {category}")
            return
        
        # Save current state before activating temp mode
        current_rules = self.db.get_all_time_rules(self.owner_id)
        saved_rules = [rule.to_dict() for rule in current_rules]
        saved_custom_enabled = self.custom_rules_enabled
        
        # Create new temp state
        new_temp_state = TempState(
            owner_id=self.owner_id,
            temp_active=True,
            temp_category=category,
            temp_expiry=None,  # No expiry for manually set temp
            saved_rules=saved_rules,
            saved_custom_enabled=saved_custom_enabled
        )
        
        self.db.save_temp_state(new_temp_state)
        
        # Deactivate custom rules
        if self.custom_rules_enabled:
            self.custom_rules_enabled = False
            self.db.update_custom_rules_status(self.owner_id, False)
        
        message = categories.get_category_message(category)
        
        await event.reply(f"""
✅ **Temp Mode Activated**

**Category:** `{category}`
**Current Message:** {message}

🔒 Custom time rules: Deactivated
📊 Saved {len(saved_rules)} rule(s) for later restoration
💾 Saved custom rules state: {'Enabled' if saved_custom_enabled else 'Disabled'}

Use `/listtemp` to check status.
Use `/tempreset` to restore normal operation.
        """)
        
        logger.info(f"Temp mode activated: {category} (saved {len(saved_rules)} rules, custom_enabled={saved_custom_enabled})")
    
    async def _cmd_listtemp(self, event, arg):
        """Handle /listtemp command - Show temp mode status."""
        temp_state = self.db.get_temp_state(self.owner_id)
        
        if not temp_state or not temp_state.temp_active:
            await event.reply("""
ℹ️ **Temp Mode Inactive**

Temporary reply mode is not currently active.

Use `/temp <category>` to activate temp mode.
            """)
            return
        
        message = categories.get_category_message(temp_state.temp_category)
        
        lines = [
            "📋 **Temp Mode Status**",
            "",
            f"**Status:** 🟢 Active",
            f"**Category:** `{temp_state.temp_category}`",
            f"**Current Message:** {message}",
            "",
            f"💾 **Saved state:**",
            f"• Saved rules: {len(temp_state.saved_rules)}",
            f"• Custom rules were: {'🟢 Enabled' if temp_state.saved_custom_enabled else '🔴 Disabled'}",
            "",
            "💡 **Actions:**",
            "• `/temp <category>` - Change temp category",
            "• `/tempreset` - Deactivate temp mode & restore rules"
        ]
        
        if temp_state.temp_expiry:
            remaining = get_time_until_expiry(temp_state.temp_expiry)
            lines.insert(5, f"⏱️  **Expires in:** {remaining}")
        
        await event.reply("\n".join(lines))
    
    async def _cmd_tempreset(self, event, arg):
        """Handle /tempreset command - Deactivate temp mode and restore saved rules."""
        temp_state = self.db.get_temp_state(self.owner_id)
        
        if not temp_state or not temp_state.temp_active:
            await event.reply("""
ℹ️ **Temp Mode Not Active**

There is no active temp mode to reset.
            """)
            return
        
        await self._reset_temp_mode()
        
        rules_count = len(temp_state.saved_rules)
        
        await event.reply(f"""
✅ **Temp Mode Deactivated**

Temporary reply mode has been deactivated.

🔄 **Restored:**
• {rules_count} custom time rule(s)
• Custom rules: {'🟢 Enabled' if temp_state.saved_custom_enabled else '🔴 Disabled'}

Your bot is back to normal operation.
        """)
        
        logger.info(f"Temp mode reset - restored {rules_count} rules")
    
    async def _reset_temp_mode(self):
        """Internal method to reset temp mode and restore saved state."""
        temp_state = self.db.get_temp_state(self.owner_id)
        
        if not temp_state or not temp_state.temp_active:
            return
        
        # Remove all current time rules (in case any were added during temp mode)
        self.db.remove_all_time_rules(self.owner_id)
        
        # Restore saved rules
        for rule_dict in temp_state.saved_rules:
            rule = TimeRule.from_dict(rule_dict)
            self.db.add_time_rule(self.owner_id, rule)
        
        # Restore custom rules enabled state
        restored_custom_enabled = temp_state.saved_custom_enabled
        self.custom_rules_enabled = restored_custom_enabled
        self.db.update_custom_rules_status(self.owner_id, restored_custom_enabled)
        
        # Clear temp state
        self.db.clear_temp_state(self.owner_id)
        
        logger.info(f"Temp mode reset completed - restored {len(temp_state.saved_rules)} rules, custom_enabled={restored_custom_enabled}")
    
    async def _cmd_stats(self, event, arg):
        """Handle /stats [today|week] command."""
        if not arg:
            arg = "today"
        
        arg = arg.strip().lower()
        
        if arg == "today":
            await self._show_today_stats(event)
        elif arg == "week":
            await self._show_week_stats(event)
        else:
            await event.reply("""
❌ **Invalid argument**

**Usage:**
• `/stats today` - View today's stats
• `/stats week` - View last 7 days stats
            """)
    
    async def _show_today_stats(self, event):
        """Show today's message statistics."""
        today = get_ist_date_str()
        
        # Get summary
        summary = self.db.get_daily_summary(self.owner_id, today)
        top_user = self.db.get_top_user_for_date(self.owner_id, today)
        
        if summary['total_messages'] == 0:
            await event.reply("""
📊 **Today's Stats**

No messages received yet today.
            """)
            return
        
        # Format response
        lines = [
            "📊 **Today's Message Statistics**",
            "",
            f"📅 Date: {today}",
            f"💬 Total Messages: {summary['total_messages']}",
            f"👥 Unique Users: {summary['unique_users']}",
        ]
        
        if top_user:
            lines.append(f"🏆 Top User: `{top_user['user_id']}` ({top_user['count']} messages)")
        
        await event.reply("\n".join(lines))
    
    async def _show_week_stats(self, event):
        """Show last 7 days statistics."""
        start_date, end_date = get_week_date_range()
        
        # Get all stats for the week
        stats = self.db.get_stats_for_date_range(self.owner_id, start_date, end_date)
        
        if not stats:
            await event.reply("""
📊 **Weekly Stats**

No messages received in the last 7 days.
            """)
            return
        
        # Aggregate by date
        daily_totals = {}
        for stat in stats:
            date = stat.date
            daily_totals[date] = daily_totals.get(date, 0) + stat.count
        
        # Calculate totals
        total_messages = sum(daily_totals.values())
        unique_users = len(set(stat.user_id for stat in stats))
        
        # Format response
        lines = [
            "📊 **Last 7 Days Statistics**",
            "",
            f"💬 Total Messages: {total_messages}",
            f"👥 Unique Users: {unique_users}",
            "",
            "📈 **Daily Breakdown:**"
        ]
        
        for date in sorted(daily_totals.keys(), reverse=True):
            count = daily_totals[date]
            lines.append(f"• {date}: {count} messages")
        
        await event.reply("\n".join(lines))
    
    async def _cmd_categories(self, event, arg):
        """Handle /categories command."""
        help_text = categories.get_categories_help_text()
        await event.reply(help_text)
    
    # ============= AUTO-REPLY HANDLER =============
    
    async def _handle_auto_reply(self, event):
        """Handle auto-reply for incoming private messages."""
        
        # Skip if already handled by command handler
        if hasattr(event, '_handled') and event._handled:
            return
        
        # Skip if auto-reply is disabled
        if not self.auto_reply_enabled:
            return
        
        # Check if it's a private message
        if not event.is_private:
            return
        
        # Get sender
        sender = await event.get_sender()
        if not sender:
            return
        
        # Skip bots
        if isinstance(sender, User) and sender.bot:
            logger.debug(f"Ignoring bot: {sender.id}")
            return
        
        # Skip owner messages
        if self._is_owner(sender.id):
            return
        
        # Skip commands
        if event.message.message.startswith('/'):
            return
        
        # Check if we should reply
        should_reply = await self._should_reply_to_user(sender.id)
        if not should_reply:
            return
        
        # Track message for analytics
        self.db.increment_message_count(self.owner_id, sender.id)
        
        # Get appropriate message and send reply
        try:
            message = self._get_current_auto_reply_message()
            await event.reply(message)
            self._mark_user_replied(sender.id)
            logger.info(f"Auto-replied to user {sender.id} with message: {message[:30]}...")
        except Exception as e:
            logger.error(f"Failed to send auto-reply: {e}")
    
    async def _should_reply_to_user(self, user_id: int) -> bool:
        """Determine if we should reply to a user."""
        
        # Check cooldown
        if user_id in self.recently_replied_users:
            last_reply_time = self.recently_replied_users[user_id]
            elapsed = (get_ist_now() - last_reply_time).total_seconds()
            if elapsed < self.reply_cooldown:
                logger.debug(f"User {user_id} in cooldown ({int(elapsed)}s elapsed)")
                return False
        
        # Check if owner is actually online
        is_actually_online = await self._is_owner_actually_online()
        if is_actually_online:
            logger.debug(f"Owner is online, not replying to {user_id}")
            return False
        
        return True
    
    def _mark_user_replied(self, user_id: int):
        """Mark a user as having received a reply."""
        self.recently_replied_users[user_id] = get_ist_now()
        
        # Clean up old entries
        if len(self.recently_replied_users) > 100:
            cutoff = get_ist_now() - timedelta(seconds=self.reply_cooldown)
            self.recently_replied_users = {
                uid: time for uid, time in self.recently_replied_users.items()
                if time > cutoff
            }
    
    async def _is_owner_actually_online(self) -> bool:
        """Check if the owner is actually online (not bot activity)."""
        if not self.owner_id:
            return False
        
        # Rate limiting
        now = get_ist_now()
        elapsed = (now - self.last_status_check).total_seconds()
        if elapsed < self.status_check_interval:
            return self.owner_actually_online
        
        try:
            owner_entity = await self.client.get_entity(self.owner_id)
            
            if hasattr(owner_entity, 'status'):
                status = owner_entity.status
                
                if isinstance(status, UserStatusOnline):
                    self.owner_actually_online = True
                    self.owner_last_seen = now
                    logger.debug("Owner is ONLINE")
                elif isinstance(status, UserStatusOffline):
                    self.owner_actually_online = False
                    self.owner_last_seen = status.was_online
                    logger.debug("Owner is OFFLINE")
                else:
                    self.owner_actually_online = False
            else:
                self.owner_actually_online = False
            
            self.last_status_check = now
            return self.owner_actually_online
        except Exception as e:
            logger.error(f"Failed to check owner status: {e}")
            return False
    
    # ============= HELPER METHODS =============
    
    def _is_owner(self, user_id: int) -> bool:
        """Check if user is the owner."""
        if self.owner_id is None:
            return False
        return user_id == self.owner_id
    
    async def _is_saved_messages(self, event) -> bool:
        """Check if message is from Saved Messages."""
        sender = await event.get_sender()
        return sender and sender.id == event.chat_id
    
    # ============= LIFECYCLE METHODS =============
    
    async def start(self):
        """Start the userbot."""
        logger.info("Starting Advanced Telegram Userbot...")
        
        try:
            # Connect to Telegram
            await self.client.start()
            
            # Get user info
            me = await self.client.get_me()
            logger.info(f"Logged in as: {me.first_name} (ID: {me.id})")
            
            # Set owner ID
            self.owner_id = me.id
            
            # Load state from database
            self._load_state_from_db()
            
            # Check initial online status
            is_online = await self._is_owner_actually_online()
            
            # Print startup info
            print("\n" + "="*60)
            print(f"🤖 Advanced Telegram Userbot Started Successfully!")
            print(f"👤 User: {me.first_name} {me.last_name or ''}")
            print(f"📱 Phone: +{me.phone}")
            print(f"🆔 User ID: {me.id}")
            print(f"🔗 Username: @{me.username or 'N/A'}")
            print(f"👁️  Status: {'🟢 ONLINE' if is_online else '🔴 OFFLINE'}")
            print(f"📊 Auto-reply: {'🟢 Enabled' if self.auto_reply_enabled else '🔴 Disabled'}")
            print("="*60)
            print("\n✨ **Features Active:**")
            print("✅ Time-based auto-switching (IST timezone)")
            print("✅ MongoDB persistence")
            print("✅ Message analytics tracking")
            print("✅ Confirmation system (1-minute expiry)")
            print("✅ Human-like responses with cooldown")
            print("\n📋 **Quick Start:**")
            print("1. Go to your 'Saved Messages' chat")
            print("2. Send /start to see status")
            print("3. Send /help for full command list")
            print("4. Send /custom 09:00-17:00 work to add time rule")
            print("5. Send /stats today to view analytics")
            print("\n⚠️  Commands only work in Saved Messages for security")
            print("="*60 + "\n")
            
            # Run until disconnected
            logger.info("Userbot is now running. Press Ctrl+C to stop.")
            await self.client.run_until_disconnected()
            
        except SessionPasswordNeededError:
            logger.error("Two-factor authentication is enabled")
            print("\n🔐 Two-factor authentication is enabled.")
            password = input("Please enter your 2FA password: ")
            await self.client.start(password=password)
            await self.start()
        except Exception as e:
            logger.error(f"Failed to start userbot: {e}")
            raise
    
    async def stop(self):
        """Stop the userbot."""
        logger.info("Stopping userbot...")
        await self.client.disconnect()
