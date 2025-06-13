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
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

# Database imports
# We'll remove psycopg2 direct imports as SQLAlchemy handles it
# import psycopg2
# from psycopg2.extras import RealDictCursor
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, aliased # Import aliased for joins with same table
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
    ALARM_BROADCAST_INTERVAL = int(os.getenv('ALARM_BROADCAST_INTERVAL', '4'))

# --- REFACTORED DATABASEMANAGER CLASS ---
class DatabaseManager:
    """Database connection and operations manager using SQLAlchemy ORM"""

    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    @contextmanager # Add this decorator
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
            ).first()

    def get_planned_sites(self, daily_plan_id: int) -> List['PlannedSite']:
        """Get planned sites for a daily plan"""
        with self.get_db() as db_session:
            return db_session.query(PlannedSite).join(Site).filter(
                PlannedSite.daily_plan_id == daily_plan_id
            ).order_by(PlannedSite.visit_order).all()

    def create_daily_plan(self, user_id: int, plan_date: date, sites_data: List[Dict],
                          area_name: str, telegram_message_id: Optional[int] = None) -> Optional['DailyPlan']:
        """Create a new daily plan with sites"""
        with self.get_db() as db_session:
            try:
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

    def update_planned_site_action(self, planned_site_id: int, updated_actions: str) -> bool:
        """Update planned site action"""
        with self.get_db() as db_session:
            try:
                planned_site = db_session.query(PlannedSite).filter(PlannedSite.id == planned_site_id).first()
                if planned_site:
                    planned_site.updated_actions = updated_actions
                    # Assuming marking as completed if action is not 'Not Done Yet'
                    if updated_actions != 'Not Done Yet' and not planned_site.is_completed:
                        planned_site.is_completed = True
                        planned_site.completed_at = datetime.utcnow()
                        # Also update total_sites_completed in DailyPlan
                        if planned_site.daily_plan: # Accessing relationship
                            planned_site.daily_plan.sites_completed += 1

                    db_session.commit()
                    return True
                return False
            except Exception as e:
                db_session.rollback()
                logger.error(f"Error updating planned site action: {e}")
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
        if not area_line.startswith('PLAN '):
            raise ValueError("Plan harus diawali dengan 'PLAN [Tanggal]'")
        date_line = area_line[5:].strip()
        area = lines[1]
        try:
            plan_date = datetime.strptime(date_line, '%d/%m/%Y').date()
        except ValueError:
            raise ValueError("Invalid date format. Use DD/MM/YYYY")

        # Parse sites and assignees
        sites_data = []
        current_assignee = ""

        for line in lines[2:]:
            line = line.lower()
            if line.startswith('bang') or line.startswith('om') or line.startswith('@'):
                # This is an assignee line
                current_assignee = line.lstrip('@').strip().title()

            elif line.startswith('- ') or line.startswith('*') or line.startswith('#') or line.startswith('•'):
                # This is a site action line
                site_line = line[2:].strip()

                # Extract site ID (first word before space or comma)
                site_match = re.match(r'^([A-Z0-9]+)', site_line)
                if not site_match:
                    continue

                site_id = site_match.group(1).upper()

                # Extract actions (everything after site code and location)
                parts = site_line.split(',', 1)
                if len(parts) > 1:
                    actions = parts[1].strip()
                else:
                    # If no comma, take everything after the site code and assumed location
                    words = site_line.split()
                    if len(words) > 2:
                        actions = ' '.join(words[2:])
                    else:
                        actions = "Maintenance"

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
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        # Schedule regular broadcasts
        self.application.job_queue.run_repeating(
            self.broadcast_alarms,
            interval=timedelta(hours=self.config.ALARM_BROADCAST_INTERVAL),
            first=timedelta(minutes=5)
        )

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_message = """
🔧 **BTS Activity Tracker Bot**

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
        help_text = """
🆘 **Help - BTS Activity Tracker Bot**

**Commands:**

📝 `/plan` - Submit daily plan
Format your plan like this:
```
PLAN AREA-NAME
13/06/2025
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
PLAN LABUSEL-PALUTA-PALAS
13/06/2025
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
PLAN AREA-NAME
13/06/2025
Bang @Username
- PSP513 Location, Action description
- PSP567 Location, Action description
```

**Example:**
```
PLAN LABUSEL-PALUTA-PALAS
13/06/2025
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
        # Using ORM method
        plan = self.db.get_user_daily_plan(user.id, today) # Accessing attribute

        if not plan:
            await update.message.reply_text("📋 No plan found for today. Use `/plan` to create one.")
            return

        # Using ORM method
        planned_sites = self.db.get_planned_sites(plan.id) # Accessing attribute

        message = f"📋 **Your Plan for {today.strftime('%d/%m/%Y')}**\n\n"
        message += f"**Status:** {escape_markdown(plan.status.value)}\n\n" # Accessing Enum value and escaping

        for idx, site in enumerate(planned_sites, 1):
            status_emoji = "✅" if site.updated_actions != 'Not Done Yet' else "⏳" # Accessing attribute
            message += f"{status_emoji} **{idx}. {site.site.site_id}** - {escape_markdown(site.site.name)}\n" # Accessing relationship
            message += f"   📍 {escape_markdown(site.site.kabupaten)}\n" # Accessing relationship
            message += f"   🔧 Plan: {escape_markdown(site.planned_actions)}\n"
            message += f"   📝 Status: {escape_markdown(site.updated_actions)}\n"
            if site.assignee:
                message += f"   👤 Assignee: {escape_markdown(site.assignee)}\n"
            message += "\n"

        # Add inline keyboard for updates
        keyboard = [[InlineKeyboardButton("🔄 Update Actions", callback_data=f"update_plan_{plan.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def update_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /update command"""
        user = self.db.get_user_by_telegram_id(update.effective_user.id)
        if not user:
            await update.message.reply_text("❌ You need to register first.")
            return

        today = datetime.now(self.config.JAKARTA_TZ).date()
        plan = self.db.get_user_daily_plan(user.id, today)

        if not plan:
            await update.message.reply_text("📋 No plan found for today. Use `/plan` to create one.")
            return

        planned_sites = self.db.get_planned_sites(plan.id)

        if not planned_sites:
            await update.message.reply_text("❌ No sites found in your plan.")
            return

        # Create inline keyboard with sites
        keyboard = []
        for site in planned_sites:
            status_emoji = "✅" if site.updated_actions != 'Not Done Yet' else "⏳" # Better to check is_completed flag
            keyboard.append([InlineKeyboardButton(
                f"{status_emoji} {site.site.site_id} - {escape_markdown(site.site.name)}", # Accessing relationship
                callback_data=f"update_site_{site.id}"
            )])

        keyboard.append([InlineKeyboardButton("📝 Bulk Update", callback_data=f"bulk_update_{plan.id}")])

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
        await update.message.reply_text(
            "ℹ️ I didn't understand that. Use /help to see available commands."
        )

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
            return

        new_action = update.message.text.strip()

        # Using ORM method
        if self.db.update_planned_site_action(planned_site_id, new_action):
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
            context.user_data['awaiting_site_update'] = True
            context.user_data['updating_site_id'] = planned_site_id

            await query.edit_message_text(
                "📝 **Update Site Action**\n\nPlease send the updated action for this site:",
                parse_mode=ParseMode.MARKDOWN
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