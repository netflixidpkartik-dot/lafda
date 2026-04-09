import os

# Telegram API Credentials
API_ID = 
API_HASH = ""
BOT_TOKEN = ""
LOGGER_BOT_TOKEN = ""
BOT_USERNAME = "TecxoAdsBot"
BOT_NAME = "Tecxo Ads 🚀"
LOGGER_BOT_USERNAME = "TecxoAds2bot"

# Admin Settings
ADMIN_ID = 5067554174
ADMIN_USERNAME = "TecxoChat"
ADMIN_IDS = [7671963315]

# Image URLs #must change 
START_IMAGE = "https://graph.org/file/9878e0f9785f390f5b5a3-2ae056edc4003b40e2.jpg" 
BROADCAST_IMAGE = "https://graph.org/file/9878e0f9785f390f5b5a3-2ae056edc4003b40e2.jpg"
FORCE_JOIN_IMAGE = "https://graph.org/file/9878e0f9785f390f5b5a3-2ae056edc4003b40e2.jpg"

# Force Join Settings
ENABLE_FORCE_JOIN = True
MUST_JOIN_CHANNEL_ID = -1002036215454  # Updated to actual channel ID
MUSTJOIN_GROUP_ID = -1002221607042    # Updated to actual group ID
MUST_JOIN_CHANNEL_URL = "https://t.me/+AAVFZPpltJg2ZDNl"  # Channel invite link or can be use public link t.me/{username} 
MUSTJOIN_GROUP_URL = "https://t.me/+jh5--7I9GRxiNjhl"    # Group invite link

# Channel and Group IDs
SETUP_GROUP_ID = -1002945751584
TECH_LOG_CHANNEL_ID = -1002945751584
GROUP_ID = -1002221607042 # Private group chat ID for ad skipping

# External Links
PRIVACY_POLICY_URL = "https://t.me/TecxoOrg"
SUPPORT_GROUP_URL = "https://t.me/TecxoChat"
UPDATES_CHANNEL_URL = "https://t.me/Tecxo"
GUIDE_URL = "https://t.me/TecxoAds/6"  # guide channel bna k usme video upload krne k baad uska link change krdena 
PRIVATE_CHANNEL_INVITE = "https://t.me/TecxoAds"

# Encryption Key
ENCRYPTION_KEY = "RnVa0xtPfK1pm3qu_POAvFI9qkSyISKFShE37_JSQ2w="

# Database Configuration
MONGO_URI = os.getenv(
    "MONGO_URI",
    ""  # use own dont use this one is confedintial
)
DB_NAME = "adsbot_db"

# Broadcast Settings
DEFAULT_DELAY = 600
MIN_DELAY = 60
MAX_DELAY = 86400

# OTP Settings
OTP_LENGTH = 5
OTP_EXPIRY = 300

# Logging Configuration
LOG_LEVEL = "INFO"
LOG_FILE = "logs/TecxoAds.log"

# Feature Toggles
ENABLE_FORCE_JOIN = True
ENABLE_OTP_VERIFICATION = True
ENABLE_BROADCASTING = True
ENABLE_ANALYTICS = True

# Success Messages
SUCCESS_MESSAGES = {
    "account_added": "Account added successfully!",
    "otp_sent": "OTP sent to your phone number!",
    "broadcast_started": "Broadcast started successfully!",
    "broadcast_completed": "Broadcast completed successfully!",
    "accounts_deleted": "All accounts deleted successfully!"  # Added for delete all accounts
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
