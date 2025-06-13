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
import pytz
from dotenv import load_dotenv

# Telegram bot imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown # Import this!

# Database imports
import psycopg2
from psycopg2.extras import RealDictCursor
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

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

class DatabaseManager:
    """Database connection and operations manager"""
    
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def get_connection(self):
        """Get database connection"""
        return psycopg2.connect(BotConfig.DATABASE_URL)
    
    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict]:
        """Get user by telegram ID"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM users WHERE telegram_id = %s
                    """, (telegram_id,))
                    user_data = cur.fetchone()
                    return dict(user_data) if user_data else None
        except Exception as e:
            logger.error(f"Error getting user by telegram ID: {e}")
            return None
    
    def register_telegram_user(self, telegram_id: int, username: str, telegram_username:str, full_name: str) -> bool:
        """Register or update telegram user info"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE users 
                        SET telegram_id = %s, telegram_username = %s, telegram_full_name = %s, updated_at = %s
                        WHERE username = %s
                    """, (telegram_id, telegram_username, full_name, datetime.utcnow(), username))
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Error registering telegram user: {e}")
            return False
    
    def get_user_daily_plan(self, user_id: int, plan_date: date) -> Optional[Dict]:
        """Get user's daily plan for specific date"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT dp.*, u.username 
                        FROM daily_plans dp
                        JOIN users u ON dp.enom_user_id = u.id
                        WHERE dp.enom_user_id = %s AND dp.plan_date = %s
                    """, (user_id, plan_date))
                    result = cur.fetchone()
                    return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting daily plan: {e}")
            return None
    
    def get_planned_sites(self, daily_plan_id: int) -> List[Dict]:
        """Get planned sites for a daily plan"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT ps.*, s.site_id, s.name as site_name, s.kabupaten
                        FROM planned_sites ps
                        JOIN sites s ON ps.site_id = s.id
                        WHERE ps.daily_plan_id = %s
                        ORDER BY ps.visit_order
                    """, (daily_plan_id,))
                    return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error getting planned sites: {e}")
            return []
    
    def create_daily_plan(self, user_id: int, plan_date: date, sites_data: List[Dict]) -> bool:
        """Create a new daily plan with sites"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Create daily plan
                    cur.execute("""
                        INSERT INTO daily_plans (enom_user_id, plan_date, status, created_at)
                        VALUES (%s, %s, 'DRAFT', %s)
                        RETURNING id
                    """, (user_id, plan_date, datetime.utcnow()))
                    
                    daily_plan_id = cur.fetchone()[0]
                    
                    # Add planned sites
                    for idx, site_data in enumerate(sites_data, 1):
                        cur.execute("""
                            INSERT INTO planned_sites 
                            (daily_plan_id, site_id, planned_actions, visit_order, assignee, estimated_duration)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            daily_plan_id,
                            site_data['site_id'],
                            site_data['actions'],
                            idx,
                            site_data.get('assignee', ''),
                            site_data.get('duration', 60)
                        ))
                    
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Error creating daily plan: {e}")
            return False
    
    def update_planned_site_action(self, planned_site_id: int, updated_actions: str) -> bool:
        """Update planned site action"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE planned_sites 
                        SET updated_actions = %s
                        WHERE id = %s
                    """, (updated_actions, planned_site_id))
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating planned site action: {e}")
            return False
    
    def get_site_by_site_id(self, site_id: str) -> Optional[Dict]:
        """Get site by site_id"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM sites WHERE site_id = %s", (site_id,))
                    result = cur.fetchone()
                    return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting site: {e}")
            return None
    
    def get_active_alarms(self) -> List[Dict]:
        """Get active alarm records"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT ar.*, s.site_id, s.name as site_name, s.kabupaten
                        FROM alarm_records ar
                        JOIN sites s ON ar.site_id = s.id
                        WHERE ar.status IN ('OPEN', 'ACKNOWLEDGED', 'SCHEDULED') 
                        AND ar.is_deleted = FALSE
                        ORDER BY ar.priority_score DESC, ar.created_at DESC
                        LIMIT 50
                    """)
                    return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error getting active alarms: {e}")
            return []

class PlanParser:
    """Parser for daily plan text format"""
    
    @staticmethod
    def parse_plan_text(plan_text: str) -> Tuple[str, date, List[Dict]]:
        """
        Parse plan text format:
        PLAN LABUSEL-PALUTA-PALAS
        13/06/2025
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
            raise ValueError("First line must start with 'PLAN '")
        area = area_line[5:].strip()
        
        # Extract date
        date_line = lines[1]
        try:
            plan_date = datetime.strptime(date_line, '%d/%m/%Y').date()
        except ValueError:
            raise ValueError("Invalid date format. Use DD/MM/YYYY")
        
        # Parse sites and assignees
        sites_data = []
        current_assignee = ""
        
        for line in lines[2:]:
            if line.startswith('Bang @') or line.startswith('@'):
                # This is an assignee line
                current_assignee = line
            elif line.startswith('- '):
                # This is a site action line
                site_line = line[2:].strip()
                
                # Extract site ID (first word before space or comma)
                site_match = re.match(r'^([A-Z0-9]+)', site_line)
                if not site_match:
                    continue
                
                site_code = site_match.group(1)
                
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
                    'site_code': site_code,
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
        user = self.db.get_user_by_telegram_id(update.effective_user.id)
        if not user:
            await update.message.reply_text(
                "❌ You need to register first. Use `/register your_username`", 
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        if user['role'] != 'enom':
            await update.message.reply_text("❌ Only ENOM users can submit daily plans.")
            return
        
        await update.message.reply_text(
            """📝 **Submit Daily Plan**

Please send your daily plan in the following format:

```
PLAN AREA-NAME
DD/MM/YYYY
Bang @Username
- SITE001 Location, Action description
- SITE002 Location, Action description
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
        plan = self.db.get_user_daily_plan(user['id'], today)
        
        if not plan:
            await update.message.reply_text("📋 No plan found for today. Use `/plan` to create one.")
            return
        
        planned_sites = self.db.get_planned_sites(plan['id'])
        
        message = f"📋 **Your Plan for {today.strftime('%d/%m/%Y')}**\n\n"
        message += f"**Status:** {plan['status']}\n\n"
        
        for idx, site in enumerate(planned_sites, 1):
            status_emoji = "✅" if site['updated_actions'] != 'Not Done Yet' else "⏳"
            message += f"{status_emoji} **{idx}. {site['site_id']}** - {site['site_name']}\n"
            message += f"   📍 {site['kabupaten']}\n"
            message += f"   🔧 Plan: {site['planned_actions']}\n"
            message += f"   📝 Status: {site['updated_actions']}\n"
            if site['assignee']:
                message += f"   👤 Assignee: {site['assignee']}\n"
            message += "\n"
        
        # Add inline keyboard for updates
        keyboard = [[InlineKeyboardButton("🔄 Update Actions", callback_data=f"update_plan_{plan['id']}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    async def update_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /update command"""
        user = self.db.get_user_by_telegram_id(update.effective_user.id)
        if not user:
            await update.message.reply_text("❌ You need to register first.")
            return
        
        today = datetime.now(self.config.JAKARTA_TZ).date()
        plan = self.db.get_user_daily_plan(user['id'], today)
        
        if not plan:
            await update.message.reply_text("📋 No plan found for today. Use `/plan` to create one.")
            return
        
        planned_sites = self.db.get_planned_sites(plan['id'])
        
        if not planned_sites:
            await update.message.reply_text("❌ No sites found in your plan.")
            return
        
        # Create inline keyboard with sites
        keyboard = []
        for site in planned_sites:
            status_emoji = "✅" if site['updated_actions'] != 'Not Done Yet' else "⏳"
            keyboard.append([InlineKeyboardButton(
                f"{status_emoji} {site['site_id']} - {site['site_name']}", 
                callback_data=f"update_site_{site['id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("📝 Bulk Update", callback_data=f"bulk_update_{plan['id']}")])
        
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
        plan = self.db.get_user_daily_plan(user['id'], today)

        # Escape potentially problematic user data
        escaped_username = escape_markdown(user['username'])
        escaped_role = escape_markdown(user['role'].upper()) # Role might also have special chars

        message = f"📊 **Status for {escaped_username}**\n\n"
        message += f"👤 **Role:** {escaped_role}\n"
        message += f"📅 **Date:** {today.strftime('%d/%m/%Y')}\n\n"

        if plan:
            planned_sites = self.db.get_planned_sites(plan['id'])
            completed = sum(1 for site in planned_sites if site['updated_actions'] != 'Not Done Yet')
            total = len(planned_sites)
            
            # Escape plan status
            escaped_plan_status = escape_markdown(plan['status'])

            message += f"📋 **Today's Plan:** {escaped_plan_status}\n"
            message += f"✅ **Progress:** {completed}/{total} sites completed\n"

            if total > 0:
                percentage = (completed / total) * 100
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
            created_time = alarm['created_at'].strftime('%d/%m %H:%M') if alarm['created_at'] else 'Unknown'
            message += f"⚠️ **{alarm['site_id']}** - {alarm['site_name']}\n"
            message += f"   📍 {alarm['kabupaten']}\n"
            message += f"   🏷️ {alarm['category']}\n"
            message += f"   📋 {alarm['description'][:100]}{'...' if len(alarm['description']) > 100 else ''}\n"
            message += f"   📅 {created_time}\n"
            message += f"   📊 Priority: {alarm['priority_score']}\n\n"
        
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
            
            # Validate and get site IDs from database
            validated_sites = []
            missing_sites = []
            
            for site_data in sites_data:
                site = self.db.get_site_by_site_id(site_data['site_code'])
                if site:
                    validated_sites.append({
                        'site_id': site['id'],
                        'actions': site_data['actions'],
                        'assignee': site_data['assignee'],
                        'duration': site_data['duration']
                    })
                else:
                    missing_sites.append(site_data['site_code'])
            
            if missing_sites:
                await update.message.reply_text(
                    f"⚠️ **Warning:** The following sites were not found in database:\n" +
                    "\n".join(f"• {site}" for site in missing_sites) +
                    f"\n\nProceeding with {len(validated_sites)} valid sites."
                )
            
            if not validated_sites:
                await update.message.reply_text("❌ No valid sites found in your plan.")
                return
            
            # Create the daily plan
            success = self.db.create_daily_plan(user['id'], plan_date, validated_sites)
            
            if success:
                await update.message.reply_text(
                    f"✅ **Plan submitted successfully!**\n\n" +
                    f"📅 Date: {plan_date.strftime('%d/%m/%Y')}\n" +
                    f"🏢 Area: {area}\n" +
                    f"📍 Sites: {len(validated_sites)} sites planned\n\n" +
                    "Use `/myplan` to view your plan or `/update` to update site actions."
                )
            else:
                await update.message.reply_text("❌ Failed to create plan. Please try again.")
        
        except ValueError as e:
            await update.message.reply_text(f"❌ **Plan format error:** {str(e)}")
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
        
        if self.db.update_planned_site_action(planned_site_id, new_action):
            await update.message.reply_text(f"✅ Site action updated successfully!\n\n📝 New action: {new_action}")
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
            high_priority = [a for a in alarms if a['priority_score'] >= 8]
            medium_priority = [a for a in alarms if 5 <= a['priority_score'] < 8]
            low_priority = [a for a in alarms if a['priority_score'] < 5]
            
            if high_priority:
                message += "🔴 **HIGH PRIORITY ALARMS**\n"
                for alarm in high_priority[:5]:  # Limit to 5 per category
                    age_hours = (current_time - alarm['created_at'].replace(tzinfo=self.config.JAKARTA_TZ)).total_seconds() / 3600
                    message += f"⚠️ **{alarm['site_id']}** ({alarm['kabupaten']})\n"
                    message += f"   🏷️ {alarm['category']} | ⏰ {age_hours:.1f}h ago\n"
                    message += f"   📋 {alarm['description'][:80]}{'...' if len(alarm['description']) > 80 else ''}\n\n"
            
            if medium_priority:
                message += "🟡 **MEDIUM PRIORITY ALARMS**\n"
                for alarm in medium_priority[:3]:
                    age_hours = (current_time - alarm['created_at'].replace(tzinfo=self.config.JAKARTA_TZ)).total_seconds() / 3600
                    message += f"⚠️ **{alarm['site_id']}** ({alarm['kabupaten']})\n"
                    message += f"   🏷️ {alarm['category']} | ⏰ {age_hours:.1f}h ago\n\n"
            
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