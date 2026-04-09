import os

os.makedirs("logs", exist_ok=True)
import logging
from datetime import datetime, timedelta
import pymongo
from pymongo.errors import ConnectionFailure, OperationFailure
import config
from bson.objectid import ObjectId
import time
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/TecxoAds.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EnhancedDatabaseManager:
    def __init__(self):
        self.client = None
        self.db = None
        self._init_db()
        self._load_persistent_globals()

    def _init_db(self):
        max_retries = 3
        retry_delay = 1
        for attempt in range(max_retries):
            try:
                self.client = pymongo.MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000, tlsInsecure=True)
                self.client.admin.command('ping')
                self.db = self.client[config.DB_NAME]
                logger.info("MongoDB initialized successfully")

                def ensure_index(collection, key, **kwargs):
                    index_key = key if isinstance(key, list) else [(key, pymongo.ASCENDING)]
                    index_name = "_".join(f"{k}_{v}" for k, v in index_key)
                    index_retry_delay = 1
                    for index_attempt in range(3):
                        try:
                            existing_indexes = collection.index_information()
                            if index_name in existing_indexes:
                                existing_unique = existing_indexes[index_name].get('unique', False)
                                desired_unique = kwargs.get('unique', False)
                                if existing_unique != desired_unique:
                                    collection.drop_index(index_name)
                                    logger.info(f"Dropped conflicting index {index_name} on {collection.name}")
                                else:
                                    logger.info(f"Index {index_name} on {collection.name} already exists with correct specs")
                                    return
                            collection.create_index(key, name=index_name, **kwargs)
                            logger.info(f"Created index {index_name} on {collection.name}")
                            return
                        except OperationFailure as e:
                            logger.error(f"Failed to create index {index_name} on {collection.name} (attempt {index_attempt + 1}): {e}")
                            if index_attempt < 2:
                                time.sleep(index_retry_delay)
                                index_retry_delay *= 2
                            else:
                                raise

                ensure_index(self.db.users, "user_id", unique=True)
                ensure_index(self.db.accounts, [("user_id", pymongo.ASCENDING), ("phone_number", pymongo.ASCENDING)])
                ensure_index(self.db.ad_messages, "user_id")
                ensure_index(self.db.ad_delays, "user_id", unique=True)
                ensure_index(self.db.broadcast_states, "user_id", unique=True)
                ensure_index(self.db.target_groups, [("user_id", pymongo.ASCENDING), ("group_id", pymongo.ASCENDING)])
                ensure_index(self.db.analytics, "user_id", unique=True)
                ensure_index(self.db.broadcast_logs, "user_id")
                ensure_index(self.db.broadcast_activity, "user_id")
                ensure_index(self.db.temp_data, [("user_id", pymongo.ASCENDING), ("key", pymongo.ASCENDING)], unique=True)
                ensure_index(self.db.logger_status, "user_id", unique=True)
                ensure_index(self.db.logger_failures, "user_id")
                return
            except ConnectionFailure as e:
                logger.error(f"MongoDB connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"Max retries reached for MongoDB connection. Check MONGO_URI in config.py.")
                    raise
            except OperationFailure as e:
                logger.error(f"Failed to initialize MongoDB: {e}. Ensure MONGO_URI credentials and database name are correct.")
                if "bad auth" in str(e).lower():
                    logger.error("Authentication failed. Verify username, password, and database name in MONGO_URI.")
                raise
            except Exception as e:
                logger.error(f"Unexpected error during MongoDB init: {e}")
                raise

    def _load_persistent_globals(self):
        try:
            ad_msgs = self.db.ad_messages.find({}, {"user_id": 1, "message": 1})
            for doc in ad_msgs:
                logger.info(f"Loaded ad msg for {doc['user_id']}")
            delays = self.db.ad_delays.find({}, {"user_id": 1, "delay": 1})
            for doc in delays:
                logger.info(f"Loaded delay {doc['delay']}s for {doc['user_id']}")
            states = self.db.broadcast_states.find({}, {"user_id": 1, "paused": 1, "running": 1})
            for doc in states:
                logger.info(f"Loaded broadcast state for {doc['user_id']}: running={doc.get('running', False)}")
            logger_statuses = self.db.logger_status.find({}, {"user_id": 1, "is_active": 1})
            for doc in logger_statuses:
                logger.info(f"Loaded logger status for {doc['user_id']}: is_active={doc.get('is_active', False)}")
        except Exception as e:
            logger.error(f"Failed to load persistent globals: {e}")

    def create_user(self, user_id, username, first_name):
        try:
            self.db.users.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "username": username or "Unknown",
                        "first_name": first_name or "User",
                        "last_interaction": datetime.now()
                    },
                    "$setOnInsert": {
                        "created_at": datetime.now(),
                        "accounts_limit": 5,
                        "has_joined_vouch": False,
                        "state": "",
                        "user_id": user_id
                    }
                },
                upsert=True
            )
            logger.info(f"User created/updated: {user_id}")
        except Exception as e:
            logger.error(f"Failed to create user {user_id}: {e}")
            raise

    def get_user(self, user_id):
        try:
            user = self.db.users.find_one({"user_id": user_id})
            return user if user else None
        except Exception as e:
            logger.error(f"Failed to get user {user_id}: {e}")
            return None

    def update_user_last_interaction(self, user_id):
        try:
            self.db.users.update_one(
                {"user_id": user_id},
                {"$set": {"last_interaction": datetime.now()}}
            )
        except Exception as e:
            logger.error(f"Failed to update last interaction for {user_id}: {e}")
            raise

    def has_vouch_sent(self, user_id):
        try:
            user = self.db.users.find_one({"user_id": user_id}, {"has_joined_vouch": 1})
            return user.get("has_joined_vouch", False) if user else False
        except Exception as e:
            logger.error(f"Failed to check vouch status for {user_id}: {e}")
            return False

    def set_vouch_sent(self, user_id):
        try:
            self.db.users.update_one(
                {"user_id": user_id},
                {"$set": {"has_joined_vouch": True}}
            )
            logger.info(f"Vouch marked as sent for {user_id}")
        except Exception as e:
            logger.error(f"Failed to set vouch sent for {user_id}: {e}")
            raise

    def get_user_accounts(self, user_id):
        try:
            return list(self.db.accounts.find({"user_id": user_id}))
        except Exception as e:
            logger.error(f"Failed to get accounts for {user_id}: {e}")
            return []

    def get_user_accounts_count(self, user_id):
        try:
            return self.db.accounts.count_documents({"user_id": user_id})
        except Exception as e:
            logger.error(f"Failed to count accounts for {user_id}: {e}")
            return 0

    def add_user_account(self, user_id, phone_number, session_string, **kwargs):
        try:
            user = self.get_user(user_id)
            if not user:
                logger.warning(f"User {user_id} not found")
                return False
            accounts_count = self.get_user_accounts_count(user_id)
            limit = user.get("accounts_limit", 5)
            if isinstance(limit, str) and limit.lower() == "unlimited":
                limit = 999
            else:
                try:
                    limit = int(limit)
                except (TypeError, ValueError):
                    limit = 5
            if accounts_count >= limit:
                logger.warning(f"Account limit exceeded for {user_id}: {accounts_count}/{limit}")
                return False
            first_name = kwargs.get('first_name', '')
            last_name = kwargs.get('last_name', '')
            self.db.accounts.insert_one({
                "user_id": user_id,
                "phone_number": phone_number,
                "session_string": session_string,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
                "created_at": datetime.now()
            })
            logger.info(f"Account added for user {user_id}: {phone_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to add account for {user_id}: {e}")
            return False

    def delete_user_account(self, user_id, account_id):
        try:
            result = self.db.accounts.delete_one({"user_id": user_id, "_id": ObjectId(account_id)})
            if result.deleted_count > 0:
                logger.info(f"Account {account_id} deleted for user {user_id}")
                return True
            else:
                logger.warning(f"No account found with ID {account_id} for user {user_id}")
                return False
        except Exception as e:
            logger.error(f"Failed to delete account {account_id} for user {user_id}: {e}")
            raise

    def delete_all_user_accounts(self, user_id):
        try:
            result = self.db.accounts.delete_many({"user_id": user_id})
            deleted_count = result.deleted_count
            logger.info(f"Deleted {deleted_count} accounts for user {user_id}")
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to delete all accounts for {user_id}: {e}")
            raise

    def deactivate_account(self, account_id):
        try:
            self.db.accounts.update_one(
                {"_id": ObjectId(account_id)},
                {"$set": {"is_active": False, "updated_at": datetime.now()}}
            )
            logger.info(f"Deactivated account {account_id}")
        except Exception as e:
            logger.error(f"Failed to deactivate account {account_id}: {e}")
            raise

    def get_user_ad_messages(self, user_id):
        try:
            return list(self.db.ad_messages.find({"user_id": user_id}, sort=[("created_at", -1)]))
        except Exception as e:
            logger.error(f"Failed to get ad messages for {user_id}: {e}")
            return []

    def add_user_ad_message(self, user_id, message, created_at):
        try:
            self.db.ad_messages.update_one(
                {"user_id": user_id},
                {"$set": {"message": message, "created_at": created_at, "updated_at": datetime.now()}},
                upsert=True
            )
            logger.info(f"Ad message added for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to add ad message for {user_id}: {e}")
            raise

    def get_user_ad_delay(self, user_id):
        try:
            doc = self.db.ad_delays.find_one({"user_id": user_id}, {"delay": 1})
            return doc.get("delay", 300) if doc else 300
        except Exception as e:
            logger.error(f"Failed to get ad delay for {user_id}: {e}")
            return 300

    def set_user_ad_delay(self, user_id, delay):
        try:
            self.db.ad_delays.update_one(
                {"user_id": user_id},
                {"$set": {"delay": delay, "updated_at": datetime.now()}},
                upsert=True
            )
            logger.info(f"Ad delay set for {user_id}: {delay}s")
        except Exception as e:
            logger.error(f"Failed to set ad delay for {user_id}: {e}")
            raise

    def get_broadcast_state(self, user_id):
        try:
            doc = self.db.broadcast_states.find_one({"user_id": user_id}, {"running": 1, "paused": 1})
            return doc if doc else {"running": False, "paused": False}
        except Exception as e:
            logger.error(f"Failed to get broadcast state for {user_id}: {e}")
            return {"running": False, "paused": False}

    def set_broadcast_state(self, user_id, running=False, paused=False):
        try:
            self.db.broadcast_states.update_one(
                {"user_id": user_id},
                {"$set": {"running": running, "paused": paused, "updated_at": datetime.now()}},
                upsert=True
            )
            logger.info(f"Broadcast state updated for {user_id}: running={running}, paused={paused}")
        except Exception as e:
            logger.error(f"Failed to set broadcast state for {user_id}: {e}")
            raise

    def increment_broadcast_cycle(self, user_id):
        try:
            self.db.analytics.update_one(
                {"user_id": user_id},
                {"$inc": {"total_cycles": 1}, "$set": {"updated_at": datetime.now()}},
                upsert=True
            )
            logger.info(f"Incremented broadcast cycle for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to increment broadcast cycle for {user_id}: {e}")
            raise

    def get_target_groups(self, user_id):
        try:
            return list(self.db.target_groups.find({"user_id": user_id}))
        except Exception as e:
            logger.error(f"Failed to get target groups for {user_id}: {e}")
            return []

    def add_target_group(self, user_id, group_id, group_name):
        try:
            self.db.target_groups.update_one(
                {"user_id": user_id, "group_id": group_id},
                {"$set": {"group_name": group_name, "created_at": datetime.now(), "updated_at": datetime.now()}},
                upsert=True
            )
            logger.info(f"Target group {group_name} added for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to add target group for {user_id}: {e}")
            raise

    def get_user_analytics(self, user_id):
        try:
            stats = self.db.analytics.find_one({"user_id": user_id})
            return stats if stats else {"total_broadcasts": 0, "total_sent": 0, "total_failed": 0, "total_cycles": 0, "vouch_successes": 0, "vouch_failures": 0}
        except Exception as e:
            logger.error(f"Failed to get analytics for {user_id}: {e}")
            return {"total_broadcasts": 0, "total_sent": 0, "total_failed": 0, "total_cycles": 0, "vouch_successes": 0, "vouch_failures": 0}

    def increment_broadcast_stats(self, user_id, success, group_id=None, account_id=None):
        try:
            update = {
                "$inc": {"total_sent" if success else "total_failed": 1, "total_broadcasts": 1},
                "$set": {"updated_at": datetime.now()}
            }
            if group_id:
                update["$inc"][f"groups.{group_id}.sent" if success else f"groups.{group_id}.failed"] = 1
            if account_id:
                update["$inc"][f"accounts.{account_id}.sent" if success else f"accounts.{account_id}.failed"] = 1
            self.db.analytics.update_one({"user_id": user_id}, update, upsert=True)
            logger.info(f"Updated broadcast stats for user {user_id}: {'success' if success else 'failure'}")
        except Exception as e:
            logger.error(f"Failed to update broadcast stats for {user_id}: {e}")
            raise

    def increment_vouch_success(self, channel_id):
        try:
            self.db.analytics.update_one(
                {"channel_id": channel_id},
                {"$inc": {"vouch_successes": 1}, "$set": {"updated_at": datetime.now()}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Failed to increment vouch success for {channel_id}: {e}")
            raise

    def increment_vouch_failure(self, channel_id, error):
        try:
            self.db.analytics.update_one(
                {"channel_id": channel_id},
                {"$inc": {"vouch_failures": 1}, "$set": {"updated_at": datetime.now(), "last_error": str(error)}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Failed to increment vouch failure for {channel_id}: {e}")
            raise

    def log_broadcast(self, user_id, message, accounts_count, groups_count, sent_count, failed_count, status):
        try:
            self.db.broadcast_logs.insert_one({
                "user_id": user_id, "message": message, "accounts_count": accounts_count,
                "groups_count": groups_count, "sent_count": sent_count, "failed_count": failed_count,
                "status": status, "created_at": datetime.now(), "updated_at": datetime.now()
            })
            logger.info(f"Broadcast logged for user {user_id}: {status}")
        except Exception as e:
            logger.error(f"Failed to log broadcast for {user_id}: {e}")
            raise

    def update_broadcast_log(self, user_id, sent_count, failed_count, status):
        try:
            self.db.broadcast_logs.update_one(
                {"user_id": user_id, "status": "running"},
                {"$set": {"sent_count": sent_count, "failed_count": failed_count, "status": status, "updated_at": datetime.now()}}
            )
        except Exception as e:
            logger.error(f"Failed to update broadcast log for {user_id}: {e}")
            raise

    def log_broadcast_activity(self, user_id, sent_count, failed_count):
        try:
            self.db.broadcast_activity.insert_one({
                "user_id": user_id, "sent_count": sent_count,
                "failed_count": failed_count, "timestamp": datetime.now()
            })
        except Exception as e:
            logger.error(f"Failed to log broadcast activity for {user_id}: {e}")
            raise

    def get_all_users(self, page=0, limit=0):
        try:
            if limit == 0:
                return list(self.db.users.find({}))
            skip = page * limit
            return list(self.db.users.find({}).skip(skip).limit(limit))
        except Exception as e:
            logger.error(f"Failed to get all users: {e}")
            return []

    def get_admin_stats(self):
        try:
            total_users = self.db.users.count_documents({})
            total_accounts = self.db.accounts.count_documents({})
            analytics_result = list(self.db.analytics.aggregate([{"$group": {"_id": None, "total_sent": {"$sum": "$total_sent"}, "total_failed": {"$sum": "$total_failed"}, "total_broadcasts": {"$sum": "$total_broadcasts"}}}]))
            analytics_stats = analytics_result[0] if analytics_result else {"total_sent": 0, "total_failed": 0, "total_broadcasts": 0}
            vouch_result = list(self.db.analytics.aggregate([{"$group": {"_id": None, "vouch_successes": {"$sum": "$vouch_successes"}, "vouch_failures": {"$sum": "$vouch_failures"}}}]))
            vouch_stats = vouch_result[0] if vouch_result else {"vouch_successes": 0, "vouch_failures": 0}
            active_logger_users = self.db.logger_status.count_documents({"is_active": True})
            return {"total_users": total_users, "total_forwards": analytics_stats["total_sent"], "total_accounts": total_accounts, "active_logger_users": active_logger_users, "vouch_successes": vouch_stats["vouch_successes"], "vouch_failures": vouch_stats["vouch_failures"], "total_broadcasts": analytics_stats["total_broadcasts"], "total_failed": analytics_stats["total_failed"]}
        except Exception as e:
            logger.error(f"Failed to get admin stats: {e}")
            return {"total_users": 0, "total_forwards": 0, "total_accounts": 0, "active_logger_users": 0, "vouch_successes": 0, "vouch_failures": 0, "total_broadcasts": 0, "total_failed": 0}

    def set_user_state(self, user_id, state):
        try:
            self.db.users.update_one({"user_id": user_id}, {"$set": {"state": state, "updated_at": datetime.now()}})
            logger.info(f"Set user state for {user_id}: {state}")
        except Exception as e:
            logger.error(f"Failed to set user state for {user_id}: {e}")
            raise

    def get_user_state(self, user_id):
        try:
            user = self.db.users.find_one({"user_id": user_id}, {"state": 1})
            return user.get("state", "") if user else ""
        except Exception as e:
            logger.error(f"Failed to get user state for {user_id}: {e}")
            return ""

    def set_temp_data(self, user_id, data):
        try:
            self.db.temp_data.update_one(
                {"user_id": user_id, "key": "session"},
                {"$set": {"value": data, "updated_at": datetime.now()}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Failed to set temp data for user {user_id}: {e}")
            raise

    def get_temp_data(self, user_id):
        try:
            doc = self.db.temp_data.find_one({"user_id": user_id, "key": "session"}, {"value": 1})
            return doc.get("value") if doc else None
        except Exception as e:
            logger.error(f"Failed to get temp data for user {user_id}: {e}")
            return None

    def set_user_temp_data(self, user_id, key, value):
        try:
            self.db.temp_data.update_one(
                {"user_id": user_id, "key": key},
                {"$set": {"value": json.dumps(value), "updated_at": datetime.now()}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Failed to set temp data for user {user_id}, key: {key}: {e}")
            raise

    def get_user_temp_data(self, user_id, key):
        try:
            doc = self.db.temp_data.find_one({"user_id": user_id, "key": key}, {"value": 1})
            return json.loads(doc.get("value")) if doc and doc.get("value") else None
        except Exception as e:
            logger.error(f"Failed to get temp data for user {user_id}, key: {key}: {e}")
            return None

    def set_logger_status(self, user_id, is_active=True):
        try:
            self.db.logger_status.update_one(
                {"user_id": user_id},
                {"$set": {"is_active": is_active, "updated_at": datetime.now()}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Failed to set logger status for {user_id}: {e}")
            raise

    def get_logger_status(self, user_id):
        try:
            doc = self.db.logger_status.find_one({"user_id": user_id}, {"is_active": 1})
            return doc.get("is_active", False) if doc else False
        except Exception as e:
            logger.error(f"Failed to get logger status for {user_id}: {e}")
            return False

    def log_logger_failure(self, user_id, error):
        try:
            self.db.logger_failures.insert_one({"user_id": user_id, "error": str(error), "timestamp": datetime.now()})
        except Exception as e:
            logger.error(f"Failed to log logger failure for {user_id}: {e}")
            raise

    def get_logger_failures(self, user_id):
        try:
            return list(self.db.logger_failures.find({"user_id": user_id}))
        except Exception as e:
            logger.error(f"Failed to get logger failures for {user_id}: {e}")
            return []

    def close(self):
        try:
            if self.client:
                self.client.close()
                logger.info("MongoDB connection closed")
        except Exception as e:
            logger.error(f"Failed to close MongoDB connection: {e}")
            raise
