#!/usr/bin/env python3
"""
Telegram Bot for BTS Activity Tracker
Integrates with Flask web application and PostgreSQL database
"""

import os
import sys
import logging
import asyncio
import re
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from contextlib import contextmanager
import pytz
from dotenv import load_dotenv

# Telegram bot imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode, ChatAction # Import ChatAction
from telegram.helpers import escape_markdown

# Database imports
# We'll remove psycopg2 direct imports as SQLAlchemy handles it
# import psycopg2
# from psycopg2.extras import RealDictCursor
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, aliased, joinedload # Import aliased for joins with same table
from sqlalchemy import func, case # For aggregation and conditional expressions

# Import your models
# IMPORTANT: Adjust this import based on your actual project structure.
# If `db` is from a Flask app instance, you might need to import `app` and then `app.db`
# or pass the `db` instance to DatabaseManager.
# For simplicity, I'm assuming your models are directly importable.
from app.models import (
    User, DailyPlan, PlannedSite, Site, Ticket, TicketStatus, ProblemCategory, EnomAssignee,
    TicketAction, PlanStatus, PlanComment, AlarmCategory, AlarmStatus, AlarmRecord, AlarmRemark,
    TelegramSession, TelegramBroadcast
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('/var/log/enom_tracker/telegram_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BotConfig:
    """Configuration class for the bot"""
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    DATABASE_URL = os.getenv('SQLALCHEMY_DATABASE_URI')
    AUTHORIZED_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID')  # Your telegram group ID
    ADMIN_USER_IDS = [int(x) for x in os.getenv('ADMIN_USER_IDS', '').split(',') if x]

    # Timezone
    JAKARTA_TZ = pytz.timezone('Asia/Jakarta')

    # Broadcast intervals (in hours)
    ALARM_BROADCAST_INTERVAL = int(os.getenv('ALARM_BROADCAST_INTERVAL', '7'))

# --- REFACTORED DATABASEMANAGER CLASS ---
class DatabaseManager:
    """Database connection and operations manager using SQLAlchemy ORM"""

    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    @contextmanager
    def get_db(self):
        """Dependency to get a DB session"""
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def get_user_by_telegram_id(self, telegram_id: int) -> Optional['User']: # Use string literal for type hint if 'User' is not imported yet
        """Get user by telegram ID"""
        with self.get_db() as db_session:
            return db_session.query(User).filter(User.telegram_id == telegram_id).first()

    def register_telegram_user(self, telegram_id: int, username: str, telegram_username: str, full_name: str) -> bool:
        """Register or update telegram user info"""
        with self.get_db() as db_session:
            try:
                user = db_session.query(User).filter(User.username == username).first()
                if user:
                    user.telegram_id = telegram_id
                    user.telegram_username = telegram_username
                    user.telegram_full_name = full_name
                    user.updated_at = datetime.utcnow()
                    db_session.commit()
                    return True
                return False
            except Exception as e:
                db_session.rollback()
                logger.error(f"Error registering telegram user: {e}")
                return False

    def get_user_daily_plan(self, user_id: int, plan_date: date) -> Optional['DailyPlan']:
        """Get user's daily plan for specific date"""
        with self.get_db() as db_session:
            return db_session.query(DailyPlan).filter(
                DailyPlan.enom_user_id == user_id,
                DailyPlan.plan_date == plan_date
            ).options(joinedload(DailyPlan.planned_sites).joinedload(PlannedSite.site)).first() # Eager load sites

    def get_planned_sites(self, daily_plan_id: int) -> List['PlannedSite']:
        """Get planned sites for a daily plan with eager loading of Site."""
        with self.get_db() as db_session:
            # Add .options(joinedload(PlannedSite.site)) to eager load the 'site' relationship
            return db_session.query(PlannedSite).options(joinedload(PlannedSite.site)).filter(
                PlannedSite.daily_plan_id == daily_plan_id
            ).order_by(PlannedSite.visit_order).all()

    def get_planned_site_by_id(self, planned_site_id: int) -> Optional['PlannedSite']:
        """Get a single planned site by ID with eager loading of Site and DailyPlan."""
        with self.get_db() as db_session:
            return db_session.query(PlannedSite).options(
                joinedload(PlannedSite.site),
                joinedload(PlannedSite.daily_plan)
            ).filter(PlannedSite.id == planned_site_id).first()


    def create_daily_plan(self, user_id: int, plan_date: date, sites_data: List[Dict],
                          area_name: str, telegram_message_id: Optional[int] = None) -> Optional['DailyPlan']:
        """Create a new daily plan with sites"""
        with self.get_db() as db_session:
            try:
                # Check if a plan already exists for this user and date
                existing_plan = db_session.query(DailyPlan).filter(
                    DailyPlan.enom_user_id == user_id,
                    DailyPlan.plan_date == plan_date
                ).first()
                if existing_plan:
                    logger.warning(f"Plan already exists for user {user_id} on {plan_date}. Aborting creation.")
                    return None # Indicate that creation failed because plan exists

                total_sites = len(sites_data)

                # Create the DailyPlan record
                new_plan = DailyPlan(
                    enom_user_id=user_id,
                    plan_date=plan_date,
                    status=PlanStatus.SUBMITTED, # Set to SUBMITTED here
                    created_at=datetime.utcnow(),
                    telegram_created=True,
                    telegram_message_id=telegram_message_id,
                    area_name=area_name,
                    total_sites_planned=total_sites,
                    sites_completed=0 # Initially 0
                )
                db_session.add(new_plan)
                db_session.flush() # Flush to get the new_plan.id before adding planned_sites

                # Add planned sites
                for idx, site_data in enumerate(sites_data, 1):
                    # Fetch Site object by site_id
                    site = db_session.query(Site).filter(Site.site_id == site_data['site_id']).first()
                    if not site:
                        logger.warning(f"Site {site_data['site_id']} not found for daily plan. Skipping.")
                        continue # Skip this site if not found

                    new_planned_site = PlannedSite(
                        daily_plan_id=new_plan.id,
                        site_id=site.id, # Use the actual Site ID from the fetched Site object
                        planned_actions=site_data['actions'],
                        visit_order=idx,
                        assignee=site_data.get('assignee', ''),
                        estimated_duration=site_data.get('duration', 60)
                    )
                    db_session.add(new_planned_site)

                db_session.commit()
                # Refresh the object to get all default values set by DB (like updated_at)
                db_session.refresh(new_plan)
                return new_plan # Return the created plan object
            except Exception as e:
                db_session.rollback()
                logger.error(f"Error creating daily plan: {e}")
                return None

    def add_planned_site_to_plan(self, plan_id: int, site_id_str: str, actions: str, assignee: str) -> Optional['PlannedSite']:
        """Add a new planned site to an existing daily plan."""
        with self.get_db() as db_session:
            try:
                plan = db_session.query(DailyPlan).filter(DailyPlan.id == plan_id).first()
                site = db_session.query(Site).filter(Site.site_id == site_id_str).first()

                if not plan:
                    logger.warning(f"Daily plan {plan_id} not found for adding site.")
                    return None
                if not site:
                    logger.warning(f"Site {site_id_str} not found for adding to plan {plan_id}.")
                    return None

                # Determine the next visit order
                max_order = db_session.query(func.max(PlannedSite.visit_order)).filter(PlannedSite.daily_plan_id == plan_id).scalar() or 0
                next_order = max_order + 1

                new_planned_site = PlannedSite(
                    daily_plan_id=plan.id,
                    site_id=site.id,
                    planned_actions=actions,
                    visit_order=next_order,
                    assignee=assignee,
                    estimated_duration=60, # Default duration
                    updated_actions='Not Done Yet', # Default status
                    is_completed=False
                )
                db_session.add(new_planned_site)

                # Update total sites count on the plan
                plan.total_sites_planned += 1

                db_session.commit()
                db_session.refresh(new_planned_site)
                db_session.refresh(plan) # Refresh plan to get updated counts
                return new_planned_site
            except Exception as e:
                db_session.rollback()
                logger.error(f"Error adding planned site to plan {plan_id}: {e}")
                return None

    def update_planned_site_details(self, planned_site_id: int, new_site_id_str: str, new_actions: str, new_assignee: str) -> Optional['PlannedSite']:
        """Update the site, actions, and assignee for an existing planned site."""
        with self.get_db() as db_session:
            try:
                planned_site = db_session.query(PlannedSite).filter(PlannedSite.id == planned_site_id).first()
                if not planned_site:
                    logger.warning(f"Planned site {planned_site_id} not found for update.")
                    return None

                site = db_session.query(Site).filter(Site.site_id == new_site_id_str).first()
                if not site:
                    logger.warning(f"New site {new_site_id_str} not found for updating planned site {planned_site_id}.")
                    return None

                # Store old completion status before changing site/details
                old_is_completed = planned_site.is_completed

                planned_site.site_id = site.id
                planned_site.planned_actions = new_actions
                planned_site.assignee = new_assignee
                # Reset status when changing site/details
                planned_site.updated_actions = 'Not Done Yet'
                planned_site.is_completed = False
                planned_site.completed_at = None

                # If the site was previously completed, decrement the plan's completed count
                if old_is_completed and planned_site.daily_plan:
                     planned_site.daily_plan.sites_completed -= 1
                     # Revert plan status if needed
                     if planned_site.daily_plan.status == PlanStatus.APPROVED:
                          planned_site.daily_plan.status = PlanStatus.SUBMITTED


                db_session.commit()
                db_session.refresh(planned_site)
                if planned_site.daily_plan:
                    db_session.refresh(planned_site.daily_plan) # Refresh plan to get updated counts
                return planned_site
            except Exception as e:
                db_session.rollback()
                logger.error(f"Error updating planned site {planned_site_id} details: {e}")
                return None

    def delete_planned_site(self, planned_site_id: int) -> bool:
        """Delete a planned site and update the daily plan counts."""
        with self.get_db() as db_session:
            try:
                planned_site = db_session.query(PlannedSite).filter(PlannedSite.id == planned_site_id).first()
                if not planned_site:
                    logger.warning(f"Planned site {planned_site_id} not found for deletion.")
                    return False

                plan = planned_site.daily_plan # Get the related plan

                # Decrement counts *before* deleting the object
                if plan:
                    plan.total_sites_planned -= 1
                    if planned_site.is_completed:
                        plan.sites_completed -= 1
                    # Revert plan status if needed
                    if plan.status == PlanStatus.APPROVED and plan.sites_completed < plan.total_sites_planned:
                         plan.status = PlanStatus.SUBMITTED


                db_session.delete(planned_site)
                db_session.commit()

                # Re-fetch the plan to ensure counts are updated in the object
                if plan:
                    db_session.refresh(plan)

                return True
            except Exception as e:
                db_session.rollback()
                logger.error(f"Error deleting planned site {planned_site_id}: {e}")
                return False


    def update_planned_site_action(self, planned_site_id: int, updated_actions: str) -> bool:
        """Update planned site action text and potentially completion status."""
        with self.get_db() as db_session:
            try:
                planned_site = db_session.query(PlannedSite).filter(PlannedSite.id == planned_site_id).first()
                if planned_site:
                    # Store the old completion status
                    old_is_completed = planned_site.is_completed

                    planned_site.updated_actions = updated_actions

                    # Determine new completion status based on the text
                    # If text is 'Not Done Yet', mark as not completed
                    # Otherwise, mark as completed
                    new_is_completed = (updated_actions != 'Not Done Yet')

                    # Update completion status and count only if it changes
                    if new_is_completed != old_is_completed:
                        planned_site.is_completed = new_is_completed
                        if planned_site.daily_plan: # Accessing relationship
                            if new_is_completed:
                                planned_site.daily_plan.sites_completed += 1
                                planned_site.completed_at = datetime.utcnow()
                            else:
                                planned_site.daily_plan.sites_completed -= 1
                                planned_site.completed_at = None # Clear completed_at if marked not completed

                            # Update plan status if all sites are completed
                            if planned_site.daily_plan.sites_completed >= planned_site.daily_plan.total_sites_planned:
                                planned_site.daily_plan.status = PlanStatus.APPROVED # Or another appropriate status
                            elif planned_site.daily_plan.status == PlanStatus.APPROVED:
                                # If a site is marked not completed, revert status from APPROVED
                                planned_site.daily_plan.status = PlanStatus.SUBMITTED


                    db_session.commit()
                    return True
                return False
            except Exception as e:
                db_session.rollback()
                logger.error(f"Error updating planned site action: {e}")
                return False

    def mark_planned_site_completed(self, planned_site_id: int) -> bool:
        """Mark a planned site as completed."""
        with self.get_db() as db_session:
            try:
                planned_site = db_session.query(PlannedSite).filter(PlannedSite.id == planned_site_id).first()
                if planned_site and not planned_site.is_completed:
                    planned_site.is_completed = True
                    planned_site.completed_at = datetime.utcnow()
                    # Keep existing updated_actions or set a default? Let's keep existing unless it was 'Not Done Yet'
                    if planned_site.updated_actions == 'Not Done Yet':
                         planned_site.updated_actions = 'Completed'

                    if planned_site.daily_plan:
                        planned_site.daily_plan.sites_completed += 1
                        # Update plan status if all sites are completed
                        if planned_site.daily_plan.sites_completed >= planned_site.daily_plan.total_sites_planned:
                            planned_site.daily_plan.status = PlanStatus.APPROVED

                    db_session.commit()
                    return True
                return False # Already completed or not found
            except Exception as e:
                db_session.rollback()
                logger.error(f"Error marking planned site completed: {e}")
                return False

    def mark_planned_site_not_completed(self, planned_site_id: int) -> bool:
        """Mark a planned site as not completed."""
        with self.get_db() as db_session:
            try:
                planned_site = db_session.query(PlannedSite).filter(PlannedSite.id == planned_site_id).first()
                if planned_site and planned_site.is_completed:
                    planned_site.is_completed = False
                    planned_site.completed_at = None
                    # Keep existing updated_actions or set a default? Let's set to 'Not Done Yet'
                    planned_site.updated_actions = 'Not Done Yet'

                    if planned_site.daily_plan:
                        planned_site.daily_plan.sites_completed -= 1
                        # If plan was APPROVED and a site is marked not completed, revert status
                        if planned_site.daily_plan.status == PlanStatus.APPROVED:
                             planned_site.daily_plan.status = PlanStatus.SUBMITTED

                    db_session.commit()
                    return True
                return False # Already not completed or not found
            except Exception as e:
                db_session.rollback()
                logger.error(f"Error marking planned site not completed: {e}")
                return False


    def get_site_by_site_id(self, site_id_str: str) -> Optional['Site']:
        """Get site by site_id string"""
        with self.get_db() as db_session:
            return db_session.query(Site).filter(Site.site_id == site_id_str).first()

    def get_active_alarms(self) -> List['AlarmRecord']:
        """Get active alarm records"""
        with self.get_db() as db_session:
            return db_session.query(AlarmRecord).join(Site).filter(
                AlarmRecord.status.in_([AlarmStatus.OPEN, AlarmStatus.ACKNOWLEDGED, AlarmStatus.SCHEDULED]),
                AlarmRecord.is_deleted == False
            ).order_by(AlarmRecord.priority_score.desc(), AlarmRecord.created_at.desc()).limit(50).all()

    def get_daily_plan_by_id(self, plan_id: int) -> Optional['DailyPlan']:
        """Get daily plan by ID with eager loading of sites and user."""
        with self.get_db() as db_session:
            return db_session.query(DailyPlan).options(
                joinedload(DailyPlan.planned_sites).joinedload(PlannedSite.site),
                joinedload(DailyPlan.enom_user)
            ).filter(DailyPlan.id == plan_id).first()

    def get_all_daily_plans_for_date(self, plan_date: date) -> List['DailyPlan']:
        """Get all daily plans for a specific date with eager loading."""
        with self.get_db() as db_session:
            # Filter for 'enom' role users' plans
            return db_session.query(DailyPlan).join(User).options(
                joinedload(DailyPlan.planned_sites).joinedload(PlannedSite.site),
                joinedload(DailyPlan.enom_user)
            ).filter(
                DailyPlan.plan_date == plan_date,
                User.role == 'enom'
            ).all()

# --- END REFACTORED DATABASEMANAGER CLASS ---


class PlanParser:
    """Parser for daily plan text format"""
    @staticmethod
    def parse_plan_text(plan_text: str) -> Tuple[str, date, List[Dict]]:
        """
        Parse plan text format:
        PLAN 13/06/2025
        LABUSEL-PALUTA-PALAS

        Bang @Ansor TS Paluta @~Junaidi
        - PSP513 Dolok, Replace ML6651 Link To PSP330
        - PSP567 Rendaman Dolok,  Clearing Cell Down, Cek Power dan Optik
        """
        lines = [line.strip() for line in plan_text.strip().split('\n') if line.strip()]

        if len(lines) < 3:
            raise ValueError("Invalid plan format. Minimum 3 lines required.")

        # Extract area
        area_line = lines[0]
        if not area_line.lower().startswith('plan'):
            raise ValueError("Plan harus diawali dengan 'Plan [Tanggal]'")
        # Use regex to extract date after "PLAN " case-insensitively, supporting DD/MM/YYYY or DD-MM-YYYY
        date_match = re.match(r'^PLAN\s+(\d{2}[-/]\d{2}[-/]\d{4})', area_line, re.IGNORECASE)
        if not date_match:
             raise ValueError("Invalid date format in PLAN line. Use DD/MM/YYYY or DD-MM-YYYY")
        date_line = date_match.group(1)

        area = lines[1]
        try:
            # Try parsing with '/' first, then '-'
            try:
                plan_date = datetime.strptime(date_line, '%d/%m/%Y').date()
            except ValueError:
                plan_date = datetime.strptime(date_line, '%d-%m-%Y').date()
        except ValueError:
            raise ValueError("Invalid date format. Use DD/MM/YYYY or DD-MM-YYYY")


        # Parse sites and assignees
        sites_data = []
        current_assignee = ""

        for line in lines[2:]:
            line_lower = line.lower() # Convert line to lowercase for initial checks
            if line_lower.startswith('bang') or line_lower.startswith('om') or line_lower.startswith('@'):
                # This is an assignee line
                assignee_name = line.strip() # Start with the original line, stripped of outer whitespace

                # Use slicing to remove specific word prefixes ("Bang ", "Om ").
                # This handles case-insensitivity on the check but removes the exact prefix length.
                if assignee_name.lower().startswith('bang '):
                    assignee_name = assignee_name[len('Bang '):].strip()
                elif assignee_name.lower().startswith('om '):
                    assignee_name = assignee_name[len('Om '):].strip()

                # Now, remove leading '@' and '~' characters. lstrip is suitable for single leading characters.
                assignee_name = assignee_name.lstrip('@').lstrip('~').strip()

                # Convert to title case for consistent formatting
                current_assignee = assignee_name.title()

            elif line_lower.startswith('- ') or line_lower.startswith('*') or line_lower.startswith('#') or line_lower.startswith('•'):
                # This is a site action line
                # Remove the bullet point and any following whitespace/invisible characters
                if line_lower.startswith('-'):
                    site_line = line[1:].strip()
                elif line_lower.startswith('*'):
                    site_line = line[1:].strip()
                elif line_lower.startswith('#'):
                    site_line = line[1:].strip()
                elif line_lower.startswith('•'):
                    site_line = line[1:].strip()

                # Remove any remaining invisible characters at the beginning
                site_line = re.sub(r'^[\s\u200b\u200c\u200d\u2060\ufeff]+', '', site_line)

                # Extract site ID (first word before space or comma)
                site_match = re.match(r'^([A-Za-z0-9]+)', site_line)
                if not site_match:
                    # If no site ID found, skip this line
                    continue

                site_id = site_match.group(1).upper() # Site ID should always be uppercase

                # Extract actions (everything after site code and location)
                # Find the first comma, or the second space after the site ID
                parts = site_line.split(',', 1)
                if len(parts) > 1:
                    actions = parts[1].strip()
                else:
                    # If no comma, try to infer actions after the first two words (site ID and assumed location)
                    words = site_line.split()
                    if len(words) > 2:
                        actions = ' '.join(words[2:]).strip()
                    else:
                        actions = "Maintenance" # Default action if nothing else is specified

                sites_data.append({
                    'site_id': site_id,
                    'actions': actions,
                    'assignee': current_assignee,
                    'duration': 60  # Default duration
                })

        return area, plan_date, sites_data


class TelegramBot:
    """Main Telegram Bot class"""

    def __init__(self):
        self.config = BotConfig()
        self.db = DatabaseManager(self.config.DATABASE_URL)

        # Build application
        self.application = Application.builder().token(self.config.TELEGRAM_TOKEN).build()

        # Register handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register all command and message handlers"""

        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("register", self.register_command))
        self.application.add_handler(CommandHandler("plan", self.plan_command))
        self.application.add_handler(CommandHandler("myplan", self.my_plan_command))
        self.application.add_handler(CommandHandler("update", self.update_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("alarms", self.alarms_command))

        # Callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

        # Message handlers
        # Add filters for specific states if needed, otherwise handle in handle_message
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        # Schedule regular broadcasts
        self.application.job_queue.run_repeating(
            self.broadcast_alarms,
            interval=timedelta(hours=self.config.ALARM_BROADCAST_INTERVAL),
            first=timedelta(minutes=5)
        )

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        welcome_message = """
🔧 **PATARO Bot**

Welcome! This bot helps manage daily plans and site activities.

**Available Commands:**
/help - Show all commands
/register - Register your telegram account
/plan - Submit daily plan
/myplan - View your current plan
/update - Update site actions
/status - Show your status
/alarms - View active alarms

To get started, use /register to link your account.
        """
        await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        help_text = """
🆘 **Help - PATARO Bot**

**Commands:**

📝 `/plan` - Submit daily plan
Format your plan like this:
```
PLAN DD/MM/YYYY
CLUSTER-NAME

Bang @Username
- PSP513 Location, Action description
- PSP567 Location, Action description
```

📋 `/myplan` - View your current daily plan

🔄 `/update` - Update site actions
You can update individual sites or bulk update

📊 `/status` - Show your current status and statistics

🚨 `/alarms` - View active site alarms

⚙️ `/register username` - Register your telegram account
Replace 'username' with your system username

**Plan Format Example:**
```
PLAN 13/06/2025
LABUSEL-PALUTA-PALAS

Bang @Ansor TS Paluta @~Junaidi 
- PSP513 Dolok, Replace ML6651 Link To PSP330
- PSP567 Rendaman Dolok, Clearing Cell Down, Cek Power dan Optik
```
Need more help? Contact your administrator.
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

    async def register_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /register command"""
        if not context.args:
            await update.message.reply_text(
                "Please provide your username: `/register your_username`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        username = context.args[0]
        telegram_id = update.effective_user.id
        telegram_username = update.effective_user.username or ""
        full_name = update.effective_user.full_name or ""

        # Using ORM method
        success = self.db.register_telegram_user(telegram_id, username, telegram_username, full_name)

        if success:
            await update.message.reply_text(
                f"✅ Successfully registered! Your account '{username}' is now linked to this Telegram account."
            )
        else:
            await update.message.reply_text(
                f"❌ Registration failed. Username '{username}' not found or already linked to another Telegram account."
            )

    async def plan_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /plan command"""
        # Using ORM method
        user = self.db.get_user_by_telegram_id(update.effective_user.id)
        if not user:
            await update.message.reply_text(
                "❌ You need to register first. Use `/register your_username`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if user.role != 'enom': # Accessing attribute directly
            await update.message.reply_text("❌ Only ENOM users can submit daily plans.")
            return

        await update.message.reply_text(
            """📝 **Submit Daily Plan**

Please send your daily plan in the following format:

```
PLAN 13/06/2025
AREA-NAME
Bang @Username
- PSP513 Location, Action description
- PSP567 Location, Action description
```

**Example:**
```
PLAN 13/06/2025
LABUSEL-PALUTA-PALAS
Bang @Ansor TS Paluta @~Junaidi 
- PSP513 Dolok, Replace ML6651 Link To PSP330
- PSP567 Rendaman Dolok, Clearing Cell Down, Cek Power dan Optik
```

Send your plan in the next message.""",
            parse_mode=ParseMode.MARKDOWN
        )

        # Store state for next message
        context.user_data['awaiting_plan'] = True

    async def my_plan_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /myplan command"""
        user = self.db.get_user_by_telegram_id(update.effective_user.id)
        if not user:
            await update.message.reply_text("❌ You need to register first. Use `/register your_username`")
            return

        today = datetime.now(self.config.JAKARTA_TZ).date()

        if user.role == 'enom':
            # Show only the user's own plan
            plan = self.db.get_user_daily_plan(user.id, today)

            if not plan:
                await update.message.reply_text("📋 No plan found for today. Use `/plan` to create one.")
                return

            planned_sites = plan.planned_sites # Access relationship directly due to eager loading

            message = f"📋 **Your Plan for {today.strftime('%d/%m/%Y')}**\n\n"
            message += f"**Status:** {escape_markdown(plan.status.value)}\n"
            message += f"**Progress:** {plan.sites_completed}/{plan.total_sites_planned} sites completed ({plan.completion_percentage:.1f}%)\n\n"

            if planned_sites:
                message += f"📍 **Sites:**\n"
                for idx, site in enumerate(planned_sites, 1):
                    status_emoji = "✅" if site.is_completed else "⏳" # Use is_completed flag
                    message += f"{status_emoji} **{idx}. {escape_markdown(site.site.site_id)}** - {escape_markdown(site.site.name)}\n"
                    message += f"   📍 {escape_markdown(site.site.kabupaten)}\n"
                    message += f"   🔧 Plan: {escape_markdown(site.planned_actions)}\n"
                    message += f"   📝 Status: {escape_markdown(str(site.updated_actions or 'Not Done Yet'))}\n" # Ensure 'Not Done Yet' is shown if null/empty
                    if site.assignee:
                        message += f"   👤 Assignee: {escape_markdown(site.assignee)}\n"
                    message += "\n"
            else:
                 message += "No sites planned for today.\n\n"


            # Add inline keyboard for updates - only for the plan owner
            keyboard = [[InlineKeyboardButton("🔄 Update Actions", callback_data=f"update_plan_{plan.id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

        elif user.role == 'tsel':
            # Show all ENOM users' plans for today
            all_plans = self.db.get_all_daily_plans_for_date(today)

            if not all_plans:
                await update.message.reply_text(f"📋 No ENOM plans found for today, {today.strftime('%d/%m/%Y')}.")
                return

            message = f"📋 **All ENOM Plans for {today.strftime('%d/%m/%Y')}**\n\n"

            for plan in all_plans:
                # Ensure plan.enom_user is loaded and exists
                if plan.enom_user:
                    escaped_username = escape_markdown(plan.enom_user.username)
                    escaped_plan_status = escape_markdown(plan.status.value)
                    message += f"👤 **{escaped_username}**\n"
                    message += f"Status: {escaped_plan_status} | Progress: {plan.sites_completed}/{plan.total_sites_planned} ({plan.completion_percentage:.1f}%)\n\n"
                else:
                     # Handle case where user relationship might be broken (shouldn't happen with FK)
                     message += f"👤 **Unknown User (Plan ID: {plan.id})**\n"
                     message += f"Status: {escape_markdown(plan.status.value)} | Progress: {plan.sites_completed}/{plan.total_sites_planned} ({plan.completion_percentage:.1f}%)\n\n"


            message += "Use `/update` to see sites you can update (if any)." # TSEL users might update tickets, not plans directly via this view

            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

        else:
             await update.message.reply_text("❌ Your role does not have access to view plans.")


    async def update_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /update command"""
        # This command is primarily for ENOM users to update their own plan sites.
        # TSEL users might use a different flow to update tickets/alarms.
        # For now, let's keep this focused on ENOM plan updates.
        user = self.db.get_user_by_telegram_id(update.effective_user.id)
        if not user:
            await update.message.reply_text("❌ You need to register first.")
            return

        if user.role != 'enom':
             await update.message.reply_text("❌ Only ENOM users can use the `/update` command for plans.")
             return

        today = datetime.now(self.config.JAKARTA_TZ).date()
        plan = self.db.get_user_daily_plan(user.id, today)

        if not plan:
            await update.message.reply_text("📋 No plan found for today. Use `/plan` to create one.")
            return

        planned_sites = plan.planned_sites # Access relationship directly due to eager loading

        if not planned_sites:
            await update.message.reply_text("❌ No sites found in your plan.")
            return

        # Create inline keyboard with sites
        keyboard = []
        for site in planned_sites:
            status_emoji = "✅" if site.is_completed else "⏳" # Use is_completed flag
            keyboard.append([InlineKeyboardButton(
                f"{status_emoji} {escape_markdown(site.site.site_id)} - {escape_markdown(site.site.name)}",
                callback_data=f"update_site_{site.id}"
            )])

        # Bulk update is not implemented yet, keep it commented or remove
        # keyboard.append([InlineKeyboardButton("📝 Bulk Update", callback_data=f"bulk_update_{plan.id}")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🔄 **Update Site Actions**\n\nSelect a site to update or choose bulk update:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        user = self.db.get_user_by_telegram_id(update.effective_user.id)
        if not user:
            await update.message.reply_text("❌ You need to register first.")
            return

        today = datetime.now(self.config.JAKARTA_TZ).date()
        plan = self.db.get_user_daily_plan(user.id, today)

        # Escape potentially problematic user data
        escaped_username = escape_markdown(user.username)
        escaped_role = escape_markdown(user.role.upper()) # Role might also have special chars

        message = f"📊 **Status for {escaped_username}**\n\n"
        message += f"👤 **Role:** {escaped_role}\n"
        message += f"📅 **Date:** {today.strftime('%d/%m/%Y')}\n\n"

        if plan:
            planned_sites = self.db.get_planned_sites(plan.id)
            # You already have sites_completed field on DailyPlan for easier access
            completed = plan.sites_completed # Directly use the field
            total = plan.total_sites_planned # Directly use the field

            # Escape plan status
            escaped_plan_status = escape_markdown(plan.status.value) # Accessing Enum value

            message += f"📋 **Today's Plan:** {escaped_plan_status}\n"
            message += f"✅ **Progress:** {completed}/{total} sites completed\n"

            if total > 0:
                percentage = plan.completion_percentage # Use the @property
                message += f"📈 **Completion:** {percentage:.1f}%\n"
        else:
            message += "📋 **Today's Plan:** No plan submitted\n"

        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

    async def alarms_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /alarms command"""
        alarms = self.db.get_active_alarms()

        if not alarms:
            await update.message.reply_text("✅ No active alarms found.")
            return

        message = "🚨 **Active Alarms**\n\n"

        for alarm in alarms[:10]:  # Limit to 10 alarms
            created_time = alarm.created_at_jakarta.strftime('%d/%m %H:%M') if alarm.created_at else 'Unknown'
            message += f"⚠️ **{escape_markdown(alarm.site.site_id)}** ({escape_markdown(alarm.site.kabupaten)})\n"
            message += f"   🏷️ {escape_markdown(alarm.category.value)} | ⏰ {(datetime.now(self.config.JAKARTA_TZ) - alarm.created_at_jakarta).total_seconds() / 3600:.1f}h ago\n" # Use Jakarta timezone for calculation
            message += f"   📋 {escape_markdown(alarm.description[:80])}{'...' if len(alarm.description) > 80 else ''}\n"
            message += f"   📊 Priority: {alarm.priority_score}\n\n"

        if len(alarms) > 10:
            message += f"... and {len(alarms) - 10} more alarms."

        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages"""

        # Check if user is awaiting plan submission
        if context.user_data.get('awaiting_plan'):
            await self.process_plan_submission(update, context)
            return

        # Check if user is awaiting site update
        if context.user_data.get('awaiting_site_update'):
            await self.process_site_update(update, context)
            return

        # Default response
        # await update.message.reply_text(
        #     "ℹ️ I didn't understand that. Use /help to see available commands."
        # )

    async def process_plan_submission(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process plan submission"""
        user = self.db.get_user_by_telegram_id(update.effective_user.id)
        if not user:
            await update.message.reply_text("❌ You need to register first.")
            return

        try:
            # Parse the plan text
            area, plan_date, sites_data = PlanParser.parse_plan_text(update.message.text)

            # --- Start: Show parsed data to user ---
            parsed_message = f"📝 **Parsed Plan Data:**\n\n"
            parsed_message += f"🏢 **Area:** {escape_markdown(area)}\n"
            parsed_message += f"📅 **Date:** {plan_date.strftime('%d/%m/%Y')}\n\n"
            parsed_message += f"📍 **Sites:**\n"

            if sites_data:
                for idx, site_data in enumerate(sites_data, 1):
                    parsed_message += f"{idx}. **{escape_markdown(site_data.get('site_id', 'N/A'))}**\n"
                    parsed_message += f"   🔧 Action: {escape_markdown(site_data.get('actions', 'N/A'))}\n"
                    if site_data.get('assignee'):
                         parsed_message += f"   👤 Assignee: {escape_markdown(site_data['assignee'])}\n"
                    # Duration is not typically shown in this summary, but can be added if needed
                parsed_message += "\nIs this correct? Proceeding to validate sites..."
            else:
                parsed_message += "No sites found in the parsed plan."

            await update.message.reply_text(parsed_message, parse_mode=ParseMode.MARKDOWN)
            # --- End: Show parsed data to user ---


            # Validate and get site IDs from database
            validated_sites_data = [] # Changed name to avoid confusion with ORM objects
            missing_sites = []

            for site_data in sites_data:
                # Using ORM method to get site object
                site_obj = self.db.get_site_by_site_id(site_data['site_id'])
                if site_obj:
                    validated_sites_data.append({ # Store original dict for create_daily_plan
                        'site_id': site_obj.site_id, # Pass site_id string to create_daily_plan which then looks up the site.id
                        'actions': site_data['actions'],
                        'assignee': site_data['assignee'],
                        'duration': site_data['duration']
                    })
                else:
                    missing_sites.append(site_data['site_id'])

            if missing_sites:
                await update.message.reply_text(
                    f"⚠️ **Warning:** The following sites were not found in database:\n" +
                    "\n".join(f"• {escape_markdown(site)}" for site in missing_sites) + # Escape missing sites
                    f"\n\nProceeding with {len(validated_sites_data)} valid sites."
                )

            if not validated_sites_data:
                await update.message.reply_text("❌ No valid sites found in your plan.")
                return

            # Create the daily plan using the ORM method
            created_plan = self.db.create_daily_plan(
                user.id, # Pass user ID directly
                plan_date,
                validated_sites_data,
                area,
                update.message.message_id
            )

            if created_plan: # Check if an object was returned
                await update.message.reply_text(
                    f"✅ **Plan submitted successfully!**\n\n" +
                    f"📅 Date: {created_plan.plan_date.strftime('%d/%m/%Y')}\n" + # Access properties
                    f"🏢 Area: {escape_markdown(created_plan.area_name)}\n" + # Access properties and escape
                    f"📍 Sites: {created_plan.total_sites_planned} sites planned\n\n" + # Access properties
                    "Use `/myplan` to view your plan or `/update` to update site actions."
                )
            else:
                await update.message.reply_text("❌ Failed to create plan. Please try again.")

        except ValueError as e:
            await update.message.reply_text(f"❌ **Plan format error:** {escape_markdown(str(e))}") # Escape error message
        except Exception as e:
            logger.error(f"Error processing plan submission: {e}")
            await update.message.reply_text("❌ An error occurred while processing your plan.")

        finally:
            # Clear the awaiting state
            context.user_data['awaiting_plan'] = False

    async def process_site_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process site action update"""
        planned_site_id = context.user_data.get('updating_site_id')
        if not planned_site_id:
            # This might happen if the bot restarts or state is lost
            await update.message.reply_text("❌ Update session expired. Please use `/update` again.")
            # Clear the awaiting state just in case
            context.user_data['awaiting_site_update'] = False
            context.user_data['updating_site_id'] = None
            return

        new_action = update.message.text.strip()

        # Using ORM method
        if self.db.update_planned_site_action(planned_site_id, new_action):
            # Fetch the updated planned site to show details in confirmation
            with self.db.get_db() as db_session:
                 updated_site = db_session.query(PlannedSite).options(joinedload(PlannedSite.site)).filter(PlannedSite.id == planned_site_id).first()
                 if updated_site:
                     message = f"✅ Site action updated successfully!\n\n"
                     message += f"📍 **{escape_markdown(updated_site.site.site_id)}** - {escape_markdown(updated_site.site.name)}\n"
                     message += f"📝 New action: {escape_markdown(new_action)}\n"
                     message += f"Status: {'Completed' if updated_site.is_completed else 'Not Done Yet'}"
                     await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
                 else:
                     await update.message.reply_text(f"✅ Site action updated successfully!\n\n📝 New action: {escape_markdown(new_action)}")
        else:
            await update.message.reply_text("❌ Failed to update site action.")

        # Clear the awaiting state
        context.user_data['awaiting_site_update'] = False
        context.user_data['updating_site_id'] = None

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button callbacks"""
        query = update.callback_query
        await query.answer()

        data = query.data

        if data.startswith('update_site_'):
            planned_site_id = int(data.split('_')[2])

            # Optional: Check if the user clicking is the plan owner or authorized
            user = self.db.get_user_by_telegram_id(update.effective_user.id)
            if not user:
                 await query.edit_message_text("❌ You need to register first.")
                 return

            with self.db.get_db() as db_session:
                 planned_site = db_session.query(PlannedSite).options(joinedload(PlannedSite.daily_plan)).filter(PlannedSite.id == planned_site_id).first()
                 if not planned_site:
                      await query.edit_message_text("❌ Planned site not found.")
                      return
                 if planned_site.daily_plan.enom_user_id != user.id:
                      await query.edit_message_text("❌ You can only update sites in your own plan.")
                      return


            context.user_data['awaiting_site_update'] = True
            context.user_data['updating_site_id'] = planned_site_id

            # Fetch the planned site details to show in the message
            planned_site = self.db.get_planned_site_by_id(planned_site_id)

            if planned_site:
                site_id = planned_site.site.site_id if planned_site.site else "Unknown Site"
                site_name = planned_site.site.name if planned_site.site else "No Name"
                assignee = planned_site.assignee or "Unassigned"
                status = "✅ Completed" if planned_site.is_completed else "⏳ Not Done Yet"

                await query.edit_message_text(
                    f"📝 **Update Site Action for {escape_markdown(site_id)} - {escape_markdown(site_name)}**\n\n"
                    f"Current Action: {escape_markdown(planned_site.updated_actions or 'Not Set')}\n"
                    f"Assignee: {escape_markdown(assignee)}\n"
                    f"Status: {status}\n\n"
                    "Send the new action text for this site.",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text("❌ Planned site not found.")

        elif data.startswith('update_plan_'):
            plan_id = int(data.split('_')[2])

            # Retrieve the plan and its sites
            plan = self.db.get_daily_plan_by_id(plan_id)

            if not plan:
                await query.edit_message_text("❌ Daily plan not found.")
                return

            # Check if the user clicking is the plan owner
            user = self.db.get_user_by_telegram_id(update.effective_user.id)
            if not user or plan.enom_user_id != user.id:
                 await query.edit_message_text("❌ You can only update your own plan.")
                 return

            planned_sites = plan.planned_sites # Access relationship directly due to eager loading

            if not planned_sites:
                await query.edit_message_text("❌ No sites found in this plan.")
                return

            # Create inline keyboard with sites for this specific plan
            keyboard = []
            for site in planned_sites:
                status_emoji = "✅" if site.is_completed else "⏳" # Use is_completed flag
                keyboard.append([InlineKeyboardButton(
                    f"{status_emoji} {escape_markdown(site.site.site_id)} - {escape_markdown(site.site.name)}",
                    callback_data=f"update_site_{site.id}"
                )])

            # Bulk update is not implemented yet, keep it commented or remove
            # keyboard.append([InlineKeyboardButton("📝 Bulk Update", callback_data=f"bulk_update_{plan.id}")])

            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"🔄 **Update Actions for Plan {plan.plan_date.strftime('%d/%m/%Y')}**\n\nSelect a site to update:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )


        elif data.startswith('bulk_update_'):
            plan_id = int(data.split('_')[2])
            # Implementation for bulk update would be more complex
            await query.edit_message_text(
                "📝 **Bulk Update**\n\nBulk update feature is coming soon. Please use individual site updates for now."
            )

    async def broadcast_alarms(self, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast active alarms to the group"""
        if not self.config.AUTHORIZED_GROUP_ID:
            return

        try:
            alarms = self.db.get_active_alarms()

            if not alarms:
                # Send test message when no alarms (for testing purposes)
                test_message = f"""
🔔 **Alarm Broadcast Test** - {datetime.now(self.config.JAKARTA_TZ).strftime('%d/%m/%Y %H:%M WIB')}

~ Buah Jambu Buah Kendondong, Gaskan FU Case Ini Dong ~

✅ **System Status:** All clear - No active alarms detected.

🔍 **Monitoring:**
• Total sites monitored: Active monitoring
• Last check: {datetime.now(self.config.JAKARTA_TZ).strftime('%H:%M WIB')}
• Next broadcast: {(datetime.now(self.config.JAKARTA_TZ) + timedelta(hours=self.config.ALARM_BROADCAST_INTERVAL)).strftime('%H:%M WIB')}

This is a scheduled test broadcast to ensure the alarm system is functioning correctly.
                """
                await context.bot.send_message(
                    chat_id=self.config.AUTHORIZED_GROUP_ID,
                    text=test_message,
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Send alarm broadcast
            current_time = datetime.now(self.config.JAKARTA_TZ)
            message = f"🚨 **ALARM BROADCAST** - {current_time.strftime('%d/%m/%Y %H:%M WIB')}\n\n"

            # Group alarms by priority
            high_priority = [a for a in alarms if a.priority_score >= 8] # Access attribute
            medium_priority = [a for a in alarms if 5 <= a.priority_score < 8]
            low_priority = [a for a in alarms if a.priority_score < 5]

            if high_priority:
                message += "🔴 **HIGH PRIORITY ALARMS**\n"
                for alarm in high_priority[:5]:  # Limit to 5 per category
                    # Use the @property created_at_jakarta for consistent timezone handling
                    age_hours = (current_time - alarm.created_at_jakarta).total_seconds() / 3600
                    message += f"⚠️ **{escape_markdown(alarm.site.site_id)}** ({escape_markdown(alarm.site.kabupaten)})\n" # Access relationships and escape
                    message += f"   🏷️ {escape_markdown(alarm.category.value)} | ⏰ {age_hours:.1f}h ago\n"
                    message += f"   📋 {escape_markdown(alarm.description[:80])}{'...' if len(alarm.description) > 80 else ''}\n\n"

            if medium_priority:
                message += "🟡 **MEDIUM PRIORITY ALARMS**\n"
                for alarm in medium_priority[:3]:
                    age_hours = (current_time - alarm.created_at_jakarta).total_seconds() / 3600
                    message += f"⚠️ **{escape_markdown(alarm.site.site_id)}** ({escape_markdown(alarm.site.kabupaten)})\n"
                    message += f"   🏷️ {escape_markdown(alarm.category.value)} | ⏰ {age_hours:.1f}h ago\n\n"

            if low_priority:
                message += f"🟢 **LOW PRIORITY:** {len(low_priority)} additional alarms\n\n"

            message += f"📊 **Total Active Alarms:** {len(alarms)}\n"
            message += f"🔄 **Next Broadcast:** {(current_time + timedelta(hours=self.config.ALARM_BROADCAST_INTERVAL)).strftime('%H:%M WIB')}\n\n"
            message += "Use `/alarms` command to view detailed alarm information."

            await context.bot.send_message(
                chat_id=self.config.AUTHORIZED_GROUP_ID,
                text=message,
                parse_mode=ParseMode.MARKDOWN
            )

        except Exception as e:
            logger.error(f"Error in alarm broadcast: {e}")

    def run(self):
        """Run the bot"""
        logger.info("Starting Telegram Bot...")
        self.application.run_polling(drop_pending_updates=True)

def main():
    """Main function"""
    if not BotConfig.TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        sys.exit(1)

    if not BotConfig.DATABASE_URL:
        logger.error("SQLALCHEMY_DATABASE_URI not found in environment variables")
        sys.exit(1)

    bot = TelegramBot()

    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()