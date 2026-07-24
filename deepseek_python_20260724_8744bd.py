import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    GUILD_ID = int(os.getenv('GUILD_ID'))
    CATEGORY_ID = int(os.getenv('CATEGORY_ID'))
    STAFF_ROLE_ID = int(os.getenv('STAFF_ROLE_ID'))
    LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID'))
    TICKET_LIFETIME_HOURS = int(os.getenv('TICKET_LIFETIME_HOURS', 10))
    
    # Цвета для embed
    COLORS = {
        'success': 0x00ff00,
        'error': 0xff0000,
        'info': 0x3498db,
        'warning': 0xffa500
    }