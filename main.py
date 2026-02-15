"""
Main entry point for the Advanced Telegram Userbot.

Initializes database connection and starts the userbot.
"""

import asyncio
import logging
import sys

import config
from database import Database
from userbot import TelegramUserbot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('userbot.log')
    ]
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    
    print("\n" + "="*60)
    print("🚀 Initializing Advanced Telegram Userbot...")
    print("="*60 + "\n")
    
    # Initialize database
    logger.info("Connecting to MongoDB...")
    db = Database(config.MONGO_URI, config.DB_NAME)
    
    try:
        db.connect()
        logger.info("✅ Database connected successfully")
    except Exception as e:
        logger.error(f"❌ Failed to connect to database: {e}")
        print(f"\n❌ DATABASE CONNECTION FAILED: {e}")
        print("\nPlease ensure:")
        print("1. MongoDB is running")
        print("2. MONGO_URI in .env is correct")
        print("3. Network connectivity is available\n")
        sys.exit(1)
    
    # Create userbot instance
    userbot = TelegramUserbot(database=db)
    
    try:
        # Run the userbot
        logger.info("Starting userbot...")
        asyncio.run(userbot.start())
    except KeyboardInterrupt:
        logger.info("Userbot stopped by user (Ctrl+C)")
        print("\n👋 Userbot stopped gracefully.")
    except Exception as e:
        logger.error(f"Userbot crashed: {e}", exc_info=True)
        print(f"\n❌ FATAL ERROR: {e}")
        print("Check userbot.log for details\n")
        sys.exit(1)
    finally:
        # Cleanup
        try:
            logger.info("Cleaning up...")
            asyncio.run(userbot.stop())
            db.disconnect()
            logger.info("✅ Cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


if __name__ == "__main__":
    main()
