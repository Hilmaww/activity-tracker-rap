#!/usr/bin/env python3
"""
Bot management utility script
"""

import sys
import subprocess
import os
from datetime import datetime

def start_bot():
    """Start the Telegram bot service"""
    try:
        subprocess.run(['sudo', 'systemctl', 'start', 'telegram-bot-enom-v0'], check=True)
        print("✅ Telegram bot started successfully")
    except subprocess.CalledProcessError:
        print("❌ Failed to start Telegram bot")

def stop_bot():
    """Stop the Telegram bot service"""
    try:
        subprocess.run(['sudo', 'systemctl', 'stop', 'telegram-bot-enom-v0'], check=True)
        print("✅ Telegram bot stopped successfully")
    except subprocess.CalledProcessError:
        print("❌ Failed to stop Telegram bot")

def restart_bot():
    """Restart the Telegram bot service"""
    try:
        subprocess.run(['sudo', 'systemctl', 'restart', 'telegram-bot-enom-v0'], check=True)
        print("✅ Telegram bot restarted successfully")
    except subprocess.CalledProcessError:
        print("❌ Failed to restart Telegram bot")

def status_bot():
    """Check Telegram bot service status"""
    try:
        subprocess.run(['sudo', 'systemctl', 'status', 'telegram-bot-enom-v0'], check=True)
    except subprocess.CalledProcessError:
        print("❌ Failed to get bot status")

def enable_bot():
    """Enable Telegram bot service to start on boot"""
    try:
        subprocess.run(['sudo', 'systemctl', 'enable', 'telegram-bot-enom-v0'], check=True)
        print("✅ Telegram bot enabled for auto-start")
    except subprocess.CalledProcessError:
        print("❌ Failed to enable Telegram bot")

def logs_bot():
    """Show bot logs"""
    try:
        subprocess.run(['sudo', 'journalctl', '-u', 'telegram-bot-enom-v0', '-f'], check=True)
    except KeyboardInterrupt:
        print("\n📋 Log viewing stopped")
    except subprocess.CalledProcessError:
        print("❌ Failed to show logs")

def main():
    if len(sys.argv) != 2:
        print("Usage: python manage_bot.py {start|stop|restart|status|enable|logs}")
        sys.exit(1)
    
    command = sys.argv[1]
    
    commands = {
        'start': start_bot,
        'stop': stop_bot,
        'restart': restart_bot,
        'status': status_bot,
        'enable': enable_bot,
        'logs': logs_bot
    }
    
    if command in commands:
        commands[command]()
    else:
        print(f"❌ Unknown command: {command}")
        print("Available commands: start, stop, restart, status, enable, logs")
        sys.exit(1)

if __name__ == '__main__':
    main()
