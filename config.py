import os

# Telegram API Credentials
API_ID = 37827563
API_HASH = "abca86f59db00e94244dd14df8259ff0"
BOT_TOKEN = "8611853728:AAFvo4LCgJ2ps5CLkEuqACNCCfG-Ijrsatg"
LOGGER_BOT_TOKEN = "8358380922:AAH0K338z_9nToZRj54Htg_3UHzpH0nFDOM"
BOT_USERNAME = "TecxoAdsBot"
BOT_NAME = "Tecxo Ads 🚀"
LOGGER_BOT_USERNAME = "TecxoAds2bot"

# Admin Settings
ADMIN_ID = 8665539217
ADMIN_USERNAME = "TecxoChat"
ADMIN_IDS = [8665539217]

# Image URLs
START_IMAGE = None
BROADCAST_IMAGE = None
FORCE_JOIN_IMAGE = None

# Force Join Settings
ENABLE_FORCE_JOIN = False
MUST_JOIN_CHANNEL_ID = 0
MUSTJOIN_GROUP_ID = 0
MUST_JOIN_CHANNEL_URL = ""
MUSTJOIN_GROUP_URL = ""

# Channel and Group IDs
SETUP_GROUP_ID = 0
TECH_LOG_CHANNEL_ID = 0
GROUP_ID = 0

# External Links
PRIVACY_POLICY_URL = ""
SUPPORT_GROUP_URL = ""
UPDATES_CHANNEL_URL = ""
GUIDE_URL = ""
PRIVATE_CHANNEL_INVITE = ""

# Encryption Key
ENCRYPTION_KEY = "uJ4XPKoW-bK-5J_bB1PjesbA1DDhBvsql-SEV4Qhmzw="

# Database Configuration
MONGO_URI = "mongodb+srv://kartikx17:wwweeerrr@cluster0.pm7gb82.mongodb.net/?appName=Cluster0"
DB_NAME = "adsbot_db"

# Broadcast Settings
DEFAULT_DELAY = 600
MIN_DELAY = 60
MAX_DELAY = 86400

# OTP Settings
OTP_LENGTH = 5
OTP_EXPIRY = 300

# Logging
LOG_LEVEL = "INFO"
LOG_FILE = "logs/TecxoAds.log"

# Feature Toggles
ENABLE_FORCE_JOIN = False
ENABLE_OTP_VERIFICATION = True
ENABLE_BROADCASTING = True
ENABLE_ANALYTICS = True

# Success Messages
SUCCESS_MESSAGES = {
    "account_added": "Account added successfully!",
    "otp_sent": "OTP sent to your phone number!",
    "broadcast_started": "Broadcast started successfully!",
    "broadcast_completed": "Broadcast completed successfully!",
    "accounts_deleted": "All accounts deleted successfully!"
}

# Error Messages
ERROR_MESSAGES = {
    "account_limit": "You've reached your account limit of 5! Get higher limit contact @TecxoChat",
    "invalid_phone": "Invalid phone number format! Use +1234567890",
    "otp_expired": "OTP has expired. Please restart hosting.",
    "invalid_otp": "Invalid OTP. Please try again.",
    "login_failed": "Failed to login to Telegram account!",
    "no_groups": "No groups found in your account!",
    "no_messages": "No messages found in Saved Messages!",
    "broadcast_limit": "Daily broadcast limit reached! Get higher limit contact @TecxoChat",
    "unauthorized": "You are not authorized to perform this action!",
    "force_join_required": "Join required channels to access this feature!"
}

# Session Storage
SESSION_STORAGE_PATH = "sessions/"
