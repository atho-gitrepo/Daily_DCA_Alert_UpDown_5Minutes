"""
MongoDB Client for Trading Bot - SUPER TDI + SUPER BOLLINGER BANDS STRATEGY.
ALIGNED: Super TDI + Super BB strategy with condition tracking.
Version: 3.4.1 - ALIGNED: Super TDI + Super BB strategy support
"""

import os
import logging
import json
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from urllib.parse import quote_plus
import time

# MongoDB imports
try:
    from pymongo import MongoClient, ASCENDING, DESCENDING
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, DuplicateKeyError, OperationFailure, ConfigurationError
    MONGODB_AVAILABLE = True
except ImportError as e:
    MONGODB_AVAILABLE = False
    logging.warning(f"pymongo not available: {e}")

# Local imports
from settings import config

# Configure logging
logger = logging.getLogger(__name__)
mongo_logger = logging.getLogger("mongodb")

EMOJI = {
    "START": "🚀",
    "SUCCESS": "✅",
    "ERROR": "❌",
    "WARNING": "⚠️",
    "INFO": "ℹ️",
    "DEBUG": "🔍",
    "DB": "💾",
    "SAVE": "💾",
    "DELETE": "🗑️",
    "UPDATE": "🔄",
    "FIND": "🔍",
    "INDEX": "📊",
    "AUTH": "🔐",
    "RAILWAY": "🚂",
    "ACTIVE": "🔴",
    "RESOLVED": "✅",
    "TDI": "📈",
    "BB": "📊",
    "CONDITION": "✅",
}


class MongoDBClient:
    """
    MongoDB Client for Super TDI + Super Bollinger Bands strategy.
    Supports condition tracking and cheat sheet storage.
    """

    def __init__(self):
        self.client = None
        self.db = None
        self.initialized = False
        self.version = "3.4.0"
        self._connected = False
        self._last_error = None
        self._connection_attempts = 0

        # Collection names
        self.ACTIVE_COLLECTION = "active_signals"
        self.RESOLVED_COLLECTION = "resolved_signals"
        self.SIGNALS_COLLECTION = "signals"  # Archive/backup collection
        self.STATS_COLLECTION = "bot_stats"
        self.ERRORS_COLLECTION = "errors"

        # Metrics
        self.metrics = {
            "active_deletions": 0,
            "active_updates": 0,
            "resolved_saves": 0,
            "archive_saves": 0,
            "errors": 0,
            "signals_saved": 0,
        }

        self._initialize()

    def _initialize(self):
        """Initialize MongoDB connection."""
        try:
            mongo_logger.info(f"{EMOJI['START']} MONGODB_INIT: START")
            mongo_logger.info(f"{EMOJI['RAILWAY']} MONGODB_INIT: Running on Railway")

            self.mongo_uri = self._get_mongo_uri()

            if not self.mongo_uri:
                mongo_logger.warning(f"{EMOJI['WARNING']} MONGODB_INIT: No MongoDB URI found. Running in memory-only mode.")
                self.initialized = False
                return

            self.db_name = self._get_db_name()

            redacted_uri = self._redact_uri(self.mongo_uri)
            mongo_logger.info(f"{EMOJI['INFO']} MONGODB_INIT: Connecting to {redacted_uri}")
            mongo_logger.info(f"{EMOJI['INFO']} MONGODB_INIT: Database: {self.db_name}")

            self._connect()
            self._create_indexes()

            self.initialized = True
            self._connected = True

            mongo_logger.info(f"{EMOJI['SUCCESS']} MONGODB_INIT: Connected to MongoDB")
            mongo_logger.info(f"{EMOJI['DB']} Database: {self.db_name}")
            mongo_logger.info(f"{EMOJI['SUCCESS']} MONGODB_INIT v{self.version}: Client initialized")
            mongo_logger.info(f"{EMOJI['DELETE']} Active signals will be COMPLETELY DELETED when resolved")

        except OperationFailure as e:
            error_msg = str(e)
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_INIT: Authentication failed - {error_msg}")
            self.initialized = False
            self._connected = False
            self._last_error = error_msg

        except ConnectionFailure as e:
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_INIT: Connection failed - {e}")
            self.initialized = False
            self._connected = False
            self._last_error = str(e)

        except ServerSelectionTimeoutError as e:
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_INIT: Server selection timeout - {e}")
            self.initialized = False
            self._connected = False
            self._last_error = str(e)

        except Exception as e:
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_INIT: Failed - {e}")
            self.initialized = False
            self._connected = False
            self._last_error = str(e)

    def _redact_uri(self, uri: str) -> str:
        """Redact sensitive parts of URI for logging."""
        if not uri:
            return "None"
        import re
        redacted = re.sub(r'://[^@]+@', '://***:***@', uri)
        return redacted

    def _get_mongo_uri(self) -> str:
        """Get MongoDB URI from environment or config."""
        mongo_uri = None

        env_vars = [
            'MONGODB_URI',
            'MONGODB_URL',
            'MONGO_URI',
            'MONGO_URL',
            'RAILWAY_MONGODB_URI',
            'RAILWAY_MONGODB_URL'
        ]

        for var in env_vars:
            value = os.environ.get(var)
            if value:
                mongo_uri = value
                mongo_logger.debug(f"{EMOJI['DEBUG']} Found {var}")
                break

        if not mongo_uri:
            try:
                mongo_uri = getattr(config, 'mongodb_uri', None)
                if mongo_uri:
                    mongo_logger.debug(f"{EMOJI['DEBUG']} Found in config.mongodb_uri")
            except:
                pass

        if not mongo_uri:
            mongo_uri = self._build_uri_from_components()

        if mongo_uri:
            mongo_logger.info(f"{EMOJI['INFO']} MONGODB URI found: {self._redact_uri(mongo_uri)}")
        else:
            mongo_logger.warning(f"{EMOJI['WARNING']} MONGODB URI not found")

        return mongo_uri

    def _build_uri_from_components(self) -> Optional[str]:
        """Build MongoDB URI from individual components."""
        try:
            host = os.environ.get('MONGODB_HOST', os.environ.get('MONGO_HOST', 'mongodb.railway.internal'))
            port = os.environ.get('MONGODB_PORT', os.environ.get('MONGO_PORT', '27017'))
            user = os.environ.get('MONGODB_USER', os.environ.get('MONGO_USER'))
            password = os.environ.get('MONGODB_PASSWORD', os.environ.get('MONGO_PASS'))
            db_name = self._get_db_name()

            if not host:
                return None

            if 'railway.internal' in host:
                mongo_logger.info(f"{EMOJI['RAILWAY']} Using Railway internal host: {host}")

            if user and password:
                encoded_user = quote_plus(user)
                encoded_password = quote_plus(password)

                if '.mongodb.net' in host:
                    return f"mongodb+srv://{encoded_user}:{encoded_password}@{host}/{db_name}?retryWrites=true&w=majority"
                else:
                    return f"mongodb://{encoded_user}:{encoded_password}@{host}:{port}/{db_name}?authSource=admin&retryWrites=true&w=majority"
            elif user:
                return f"mongodb://{quote_plus(user)}@{host}:{port}/{db_name}?authSource=admin"
            else:
                return f"mongodb://{host}:{port}/{db_name}"

        except Exception as e:
            mongo_logger.warning(f"{EMOJI['WARNING']} MONGODB_INIT: Failed to build URI from components: {e}")
            return None

    def _get_db_name(self) -> str:
        """Get database name from environment or config."""
        db_name = os.environ.get('MONGODB_DB', os.environ.get('MONGO_DB'))

        if not db_name:
            try:
                db_name = getattr(config, 'mongodb_db_name', 'trading_bot_dca')
            except:
                db_name = 'trading_bot_dca'

        return db_name

    def _connect(self):
        """Connect to MongoDB with retry logic."""
        if not MONGODB_AVAILABLE:
            raise ImportError("pymongo not available")

        max_retries = 5
        retry_delay = 3

        mongo_logger.info(f"{EMOJI['INFO']} Attempting to connect to MongoDB (max {max_retries} retries)...")

        for attempt in range(max_retries):
            try:
                self._connection_attempts += 1

                if 'railway.internal' in self.mongo_uri:
                    mongo_logger.info(f"{EMOJI['RAILWAY']} Connecting to Railway internal MongoDB...")

                self.client = MongoClient(
                    self.mongo_uri,
                    serverSelectionTimeoutMS=15000,
                    connectTimeoutMS=15000,
                    socketTimeoutMS=15000,
                    maxPoolSize=50,
                    minPoolSize=5,
                    retryWrites=True,
                    w='majority',
                    tlsAllowInvalidCertificates=True,
                    tlsAllowInvalidHostnames=True,
                )

                self.client.admin.command('ping')

                self.db = self.client[self.db_name]

                collections = self.db.list_collection_names()
                mongo_logger.info(f"{EMOJI['DEBUG']} Available collections: {collections}")

                mongo_logger.info(f"{EMOJI['SUCCESS']} Connected to MongoDB on attempt {attempt + 1}")
                return

            except OperationFailure as e:
                error_msg = str(e)
                if 'Authentication failed' in error_msg or 'auth failed' in error_msg.lower():
                    mongo_logger.error(f"{EMOJI['AUTH']} Authentication failed - check username/password")
                    mongo_logger.error(f"{EMOJI['AUTH']} URI: {self._redact_uri(self.mongo_uri)}")
                    raise
                elif attempt < max_retries - 1:
                    mongo_logger.warning(f"{EMOJI['RETRY']} Operation failed, retrying in {retry_delay}s: {e}")
                    time.sleep(retry_delay)
                else:
                    raise

            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    mongo_logger.warning(f"{EMOJI['RETRY']} Connection attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    mongo_logger.error(f"{EMOJI['ERROR']} All connection attempts failed")
                    raise

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    mongo_logger.warning(f"{EMOJI['RETRY']} Attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    raise

    def _create_indexes(self):
        """Create necessary indexes for performance."""
        try:
            if self.db is None:
                return

            # Active signals indexes
            active_collection = self.db[self.ACTIVE_COLLECTION]
            active_collection.create_index([("symbol", ASCENDING)])
            active_collection.create_index([("status", ASCENDING)])
            active_collection.create_index([("entry_time", DESCENDING)])
            active_collection.create_index([("symbol", ASCENDING), ("status", ASCENDING)])

            # New: Index for conditions tracking
            active_collection.create_index([("conditions_met", ASCENDING)])
            active_collection.create_index([("signal_strength", ASCENDING)])

            # Resolved signals indexes
            resolved_collection = self.db[self.RESOLVED_COLLECTION]
            resolved_collection.create_index([("symbol", ASCENDING)])
            resolved_collection.create_index([("status", ASCENDING)])
            resolved_collection.create_index([("exit_time", DESCENDING)])
            resolved_collection.create_index([("symbol", ASCENDING), ("status", ASCENDING)])

            # Signals archive indexes
            signals_collection = self.db[self.SIGNALS_COLLECTION]
            signals_collection.create_index([("symbol", ASCENDING), ("signal_type", ASCENDING)])
            signals_collection.create_index([("timestamp", DESCENDING)])

            # New: Index for strategy version
            signals_collection.create_index([("strategy_version", ASCENDING)])

            mongo_logger.info(f"{EMOJI['INDEX']} MONGODB: Indexes created")

        except OperationFailure as e:
            mongo_logger.warning(f"{EMOJI['WARNING']} MONGODB: Index creation failed - {e}")
        except Exception as e:
            mongo_logger.warning(f"{EMOJI['WARNING']} MONGODB: Index creation failed - {e}")

    def is_available(self) -> bool:
        """Check if MongoDB is available."""
        if not self._connected or self.client is None or self.db is None:
            return False

        try:
            self.client.admin.command('ping')
            return True
        except:
            return False

    def is_initialized(self) -> bool:
        """Check if MongoDB is initialized."""
        return self.initialized and self.is_available()

    def get_last_error(self) -> Optional[str]:
        """Get the last error that occurred."""
        return self._last_error

    def get_connection_status(self) -> Dict[str, Any]:
        """Get detailed connection status."""
        return {
            "initialized": self.initialized,
            "connected": self._connected,
            "available": self.is_available(),
            "db_name": self.db_name if hasattr(self, 'db_name') else None,
            "last_error": self._last_error,
            "version": self.version,
            "connection_attempts": self._connection_attempts,
            "uri_configured": bool(hasattr(self, 'mongo_uri') and self.mongo_uri),
            "metrics": self.metrics,
        }

    def get_collection(self, collection_name: str):
        """Get a collection by name."""
        if not self.is_available():
            return None
        return self.db[collection_name]

    # ==================== SIGNAL OPERATIONS ====================

    def save_signal(self, signal_data: Dict[str, Any]) -> Optional[str]:
        """
        Save signal to ACTIVE collection and archive.
        Supports Super TDI + Super BB strategy fields.
        """
        if not self.is_available():
            mongo_logger.warning(f"{EMOJI['WARNING']} MONGODB_SAVE: Not available")
            return None

        try:
            # Add timestamps
            signal_data['created_at'] = datetime.now().isoformat()
            signal_data['updated_at'] = datetime.now().isoformat()
            signal_data['strategy_version'] = "3.4.0"
            signal_data['strategy_name'] = "Super TDI + Super Bollinger Bands"

            # Ensure condition fields are present
            condition_fields = [
                'conditions_met', 'conditions_total',
                'condition_1_tdi_zone', 'condition_2_tdi_cross',
                'condition_3_bb_touch', 'condition_4_candles_shrinking',
                'condition_5_reversal_confirm'
            ]
            for field in condition_fields:
                if field not in signal_data:
                    signal_data[field] = 0 if field == 'conditions_met' else False

            if '_id' not in signal_data:
                signal_data['_id'] = self._generate_id(signal_data)

            doc_id = signal_data['_id']

            # PRIMARY: Save to ACTIVE collection
            active_collection = self.db[self.ACTIVE_COLLECTION]
            result = active_collection.update_one(
                {'_id': doc_id},
                {'$set': signal_data},
                upsert=True
            )

            if result.acknowledged:
                self.metrics["signals_saved"] += 1
                mongo_logger.info(f"{EMOJI['ACTIVE']} MONGODB_SAVE: Saved signal to {self.ACTIVE_COLLECTION}: {doc_id}")
                mongo_logger.debug(f"  Conditions: {signal_data.get('conditions_met', 0)}/{signal_data.get('conditions_total', 5)}")
            else:
                mongo_logger.warning(f"{EMOJI['WARNING']} MONGODB_SAVE: Failed to save to {self.ACTIVE_COLLECTION}")
                return None

            # SECONDARY: Archive to signals collection
            try:
                signals_collection = self.db[self.SIGNALS_COLLECTION]
                signals_collection.update_one(
                    {'_id': doc_id},
                    {'$set': signal_data},
                    upsert=True
                )
                self.metrics["archive_saves"] += 1
                mongo_logger.debug(f"{EMOJI['DB']} MONGODB_SAVE: Archived to {self.SIGNALS_COLLECTION}: {doc_id}")
            except Exception as e:
                mongo_logger.warning(f"{EMOJI['WARNING']} MONGODB_SAVE: Failed to archive: {e}")

            return doc_id

        except Exception as e:
            self.metrics["errors"] += 1
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_SAVE: Failed - {e}")
            return None

    def get_signal(self, doc_id: str, collection: str = None) -> Optional[Dict]:
        """Get a signal by document ID from specified collection."""
        if not self.is_available():
            return None

        try:
            if collection is None or collection == self.ACTIVE_COLLECTION:
                active_collection = self.db[self.ACTIVE_COLLECTION]
                signal = active_collection.find_one({'_id': doc_id})
                if signal:
                    signal['_id'] = str(signal['_id'])
                    return signal

            if collection is None or collection == self.RESOLVED_COLLECTION:
                resolved_collection = self.db[self.RESOLVED_COLLECTION]
                signal = resolved_collection.find_one({'_id': doc_id})
                if signal:
                    signal['_id'] = str(signal['_id'])
                    return signal

            if collection is None or collection == self.SIGNALS_COLLECTION:
                signals_collection = self.db[self.SIGNALS_COLLECTION]
                signal = signals_collection.find_one({'_id': doc_id})
                if signal:
                    signal['_id'] = str(signal['_id'])
                    return signal

            return None

        except Exception as e:
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_GET: Failed - {e}")
            return None

    def get_active_signals(self, limit: int = 100) -> Dict[str, Dict]:
        """Get all active signals from ACTIVE collection."""
        if not self.is_available():
            return {}

        try:
            active_collection = self.db[self.ACTIVE_COLLECTION]
            signals = active_collection.find(
                {'status': {'$ne': 'RESOLVED'}},
                limit=limit
            ).sort('entry_time', DESCENDING)

            result = {}
            for signal in signals:
                doc_id = str(signal['_id'])
                signal['_id'] = doc_id
                result[doc_id] = signal

            mongo_logger.debug(f"{EMOJI['ACTIVE']} MONGODB_GET_ACTIVE: Found {len(result)} active signals")
            return result

        except Exception as e:
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_GET_ACTIVE: Failed - {e}")
            return {}

    def get_active_signals_by_conditions(self, min_conditions: int = 3) -> List[Dict]:
        """
        Get active signals that meet minimum condition threshold.
        Super TDI + Super BB specific.
        """
        if not self.is_available():
            return []

        try:
            active_collection = self.db[self.ACTIVE_COLLECTION]
            signals = active_collection.find({
                'status': 'ACTIVE',
                'conditions_met': {'$gte': min_conditions}
            }).sort('conditions_met', DESCENDING)

            result = []
            for signal in signals:
                signal['_id'] = str(signal['_id'])
                result.append(signal)

            mongo_logger.debug(f"Found {len(result)} signals with {min_conditions}+ conditions")
            return result

        except Exception as e:
            mongo_logger.error(f"Error getting signals by conditions: {e}")
            return []

    def get_resolved_signals(self, limit: int = 100) -> Dict[str, Dict]:
        """Get resolved signals from RESOLVED collection."""
        if not self.is_available():
            return {}

        try:
            resolved_collection = self.db[self.RESOLVED_COLLECTION]
            signals = resolved_collection.find({}, limit=limit).sort('exit_time', DESCENDING)

            result = {}
            for signal in signals:
                doc_id = str(signal['_id'])
                signal['_id'] = doc_id
                result[doc_id] = signal

            mongo_logger.debug(f"{EMOJI['RESOLVED']} MONGODB_GET_RESOLVED: Found {len(result)} resolved signals")
            return result

        except Exception as e:
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_GET_RESOLVED: Failed - {e}")
            return {}

    def update_signal_status(self, doc_id: str, status: str, update_data: Dict[str, Any]) -> bool:
        """
        Complete deletion from active collection when resolved.

        - For terminal status (PROFIT/LOSS/BREAK_EVEN):
          1. Save to resolved collection
          2. COMPLETELY DELETE from active collection
          3. Archive to signals collection
        - For non-terminal: Update in active collection
        """
        if not self.is_available():
            return False

        try:
            active_collection = self.db[self.ACTIVE_COLLECTION]
            signal = active_collection.find_one({'_id': doc_id})

            if not signal:
                mongo_logger.warning(f"{EMOJI['WARNING']} MONGODB_UPDATE: Signal {doc_id} not found in {self.ACTIVE_COLLECTION}")
                resolved_collection = self.db[self.RESOLVED_COLLECTION]
                if resolved_collection.find_one({'_id': doc_id}):
                    mongo_logger.info(f"{EMOJI['INFO']} MONGODB_UPDATE: Signal {doc_id} already in resolved")
                    return True
                return False

            signal_data = signal.copy()
            if '_id' in signal_data:
                del signal_data['_id']

            signal_data.update(update_data)
            signal_data['status'] = status
            signal_data['updated_at'] = datetime.now().isoformat()

            terminal_statuses = ['PROFIT', 'LOSS', 'BREAK_EVEN', 'CLOSED']

            if status in terminal_statuses:
                # ===== STEP 1: SAVE TO RESOLVED COLLECTION =====
                signal_data['resolved_at'] = datetime.now().isoformat()
                signal_data['original_doc_id'] = doc_id

                resolved_collection = self.db[self.RESOLVED_COLLECTION]
                resolved_result = resolved_collection.update_one(
                    {'_id': doc_id},
                    {'$set': signal_data},
                    upsert=True
                )

                if resolved_result.acknowledged:
                    self.metrics["resolved_saves"] += 1
                    mongo_logger.info(f"{EMOJI['RESOLVED']} MONGODB_UPDATE: Signal {doc_id} saved to {self.RESOLVED_COLLECTION} ({status})")
                    mongo_logger.debug(f"  Conditions: {signal_data.get('conditions_met', 0)}/{signal_data.get('conditions_total', 5)}")
                else:
                    mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_UPDATE: Failed to save {doc_id} to resolved")
                    return False

                # ===== STEP 2: COMPLETELY DELETE FROM ACTIVE COLLECTION =====
                delete_result = active_collection.delete_one({'_id': doc_id})

                if delete_result.deleted_count > 0:
                    self.metrics["active_deletions"] += 1
                    mongo_logger.info(f"{EMOJI['DELETE']} ✅ MONGODB_DELETE: COMPLETELY DELETED {doc_id} from {self.ACTIVE_COLLECTION}")
                else:
                    mongo_logger.warning(f"{EMOJI['WARNING']} MONGODB_DELETE: Failed to delete {doc_id} from active (may already be deleted)")

                # ===== STEP 3: UPDATE ARCHIVE =====
                try:
                    signals_collection = self.db[self.SIGNALS_COLLECTION]
                    signals_collection.update_one(
                        {'_id': doc_id},
                        {'$set': signal_data},
                        upsert=True
                    )
                    self.metrics["archive_saves"] += 1
                    mongo_logger.debug(f"{EMOJI['DB']} MONGODB_UPDATE: Archived {doc_id} to {self.SIGNALS_COLLECTION}")
                except Exception as e:
                    mongo_logger.warning(f"{EMOJI['WARNING']} MONGODB_UPDATE: Failed to archive: {e}")

                return True

            else:
                # ===== NON-TERMINAL: Update in active collection =====
                result = active_collection.update_one(
                    {'_id': doc_id},
                    {'$set': signal_data}
                )

                if result.modified_count > 0:
                    self.metrics["active_updates"] += 1
                    mongo_logger.debug(f"{EMOJI['UPDATE']} MONGODB_UPDATE: Updated signal {doc_id} in {self.ACTIVE_COLLECTION}")
                    return True
                else:
                    mongo_logger.warning(f"{EMOJI['WARNING']} MONGODB_UPDATE: No changes to {doc_id}")
                    return False

        except Exception as e:
            self.metrics["errors"] += 1
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_UPDATE: Failed - {e}")
            return False

    def move_to_resolved(self, doc_id: str, signal_data: Dict[str, Any]) -> bool:
        """Move a signal to resolved collection and delete from active."""
        if not self.is_available():
            return False

        try:
            if '_id' not in signal_data:
                signal_data['_id'] = doc_id

            signal_data['resolved_at'] = datetime.now().isoformat()
            signal_data['strategy_version'] = "3.4.0"

            # Save to resolved
            resolved_collection = self.db[self.RESOLVED_COLLECTION]
            resolved_result = resolved_collection.update_one(
                {'_id': doc_id},
                {'$set': signal_data},
                upsert=True
            )

            if resolved_result.acknowledged:
                self.metrics["resolved_saves"] += 1
                mongo_logger.info(f"{EMOJI['RESOLVED']} MONGODB_MOVE: Signal {doc_id} saved to resolved")

                # Delete from active
                active_collection = self.db[self.ACTIVE_COLLECTION]
                delete_result = active_collection.delete_one({'_id': doc_id})

                if delete_result.deleted_count > 0:
                    self.metrics["active_deletions"] += 1
                    mongo_logger.info(f"{EMOJI['DELETE']} ✅ MONGODB_DELETE: COMPLETELY DELETED {doc_id} from active")
                else:
                    mongo_logger.warning(f"{EMOJI['WARNING']} MONGODB_DELETE: Failed to delete {doc_id} from active")

                return True

            return False

        except Exception as e:
            self.metrics["errors"] += 1
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_MOVE: Failed - {e}")
            return False

    def delete_signal(self, doc_id: str, collection: str = None) -> bool:
        """Delete a signal from specified collection."""
        if not self.is_available():
            return False

        try:
            if collection == 'active' or collection is None:
                coll = self.db[self.ACTIVE_COLLECTION]
            elif collection == 'resolved':
                coll = self.db[self.RESOLVED_COLLECTION]
            elif collection == 'archive':
                coll = self.db[self.SIGNALS_COLLECTION]
            else:
                mongo_logger.warning(f"{EMOJI['WARNING']} MONGODB_DELETE: Unknown collection: {collection}")
                return False

            result = coll.delete_one({'_id': doc_id})

            if result.deleted_count > 0:
                if collection == 'active' or collection is None:
                    self.metrics["active_deletions"] += 1
                mongo_logger.info(f"{EMOJI['DELETE']} MONGODB_DELETE: Deleted {doc_id} from {collection or 'active'}")
                return True
            else:
                mongo_logger.debug(f"{EMOJI['DEBUG']} MONGODB_DELETE: Document {doc_id} not found in {collection or 'active'}")
                return False

        except Exception as e:
            self.metrics["errors"] += 1
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_DELETE: Failed - {e}")
            return False

    def cleanup_orphaned_active_signals(self) -> int:
        """Clean up orphaned active signals that should have been deleted."""
        if not self.is_available():
            return 0

        try:
            active_collection = self.db[self.ACTIVE_COLLECTION]
            terminal_statuses = ['PROFIT', 'LOSS', 'BREAK_EVEN', 'CLOSED', 'RESOLVED']

            orphaned = active_collection.find({'status': {'$in': terminal_statuses}})
            orphaned_list = list(orphaned)
            deleted_count = 0

            for signal in orphaned_list:
                doc_id = signal.get('_id')
                if doc_id:
                    result = active_collection.delete_one({'_id': doc_id})
                    if result.deleted_count > 0:
                        deleted_count += 1
                        self.metrics["active_deletions"] += 1
                        mongo_logger.info(f"{EMOJI['DELETE']} Cleaned up orphaned signal: {doc_id} (status: {signal.get('status')})")

            if deleted_count > 0:
                mongo_logger.info(f"{EMOJI['SUCCESS']} Cleaned up {deleted_count} orphaned active signals")

            return deleted_count

        except Exception as e:
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_CLEANUP: Failed - {e}")
            return 0

    # ==================== SUPER TDI + SUPER BB STATS ====================

    def get_strategy_stats(self) -> Dict[str, Any]:
        """Get Super TDI + Super BB specific statistics."""
        if not self.is_available():
            return {}

        try:
            active_collection = self.db[self.ACTIVE_COLLECTION]

            # Count signals by condition level
            signals_by_conditions = {}
            for i in range(1, 6):
                count = active_collection.count_documents({
                    'status': 'ACTIVE',
                    'conditions_met': i
                })
                signals_by_conditions[f"{i}_conditions"] = count

            # Count by signal strength
            hard_count = active_collection.count_documents({
                'status': 'ACTIVE',
                'signal_strength': 'HARD'
            })
            soft_count = active_collection.count_documents({
                'status': 'ACTIVE',
                'signal_strength': 'SOFT'
            })

            # Count by AI decision
            ai_approved = active_collection.count_documents({
                'status': 'ACTIVE',
                'ai_decision': 'APPROVE'
            })
            ai_rejected = active_collection.count_documents({
                'status': 'ACTIVE',
                'ai_decision': 'REJECT'
            })

            return {
                'active_signals': active_collection.count_documents({'status': 'ACTIVE'}),
                'signals_by_conditions': signals_by_conditions,
                'hard_signals': hard_count,
                'soft_signals': soft_count,
                'ai_approved': ai_approved,
                'ai_rejected': ai_rejected,
                'total_saved': self.metrics.get('signals_saved', 0),
            }

        except Exception as e:
            mongo_logger.error(f"Error getting strategy stats: {e}")
            return {}

    # ==================== STATS OPERATIONS ====================

    def save_stats(self, stats: Dict[str, Any]) -> bool:
        """Save bot statistics."""
        if not self.is_available():
            return False

        try:
            collection = self.db[self.STATS_COLLECTION]
            stats['updated_at'] = datetime.now().isoformat()
            stats['strategy_version'] = "3.4.0"
            stats['strategy_name'] = "Super TDI + Super Bollinger Bands"

            result = collection.update_one(
                {'_id': 'bot_stats'},
                {'$set': stats},
                upsert=True
            )

            return result.acknowledged

        except Exception as e:
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_STATS_SAVE: Failed - {e}")
            return False

    def get_stats(self) -> Dict:
        """Get bot statistics."""
        if not self.is_available():
            return {}

        try:
            collection = self.db[self.STATS_COLLECTION]
            stats = collection.find_one({'_id': 'bot_stats'})

            if stats:
                stats['_id'] = str(stats['_id'])
                return stats

            return {}

        except Exception as e:
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_STATS_GET: Failed - {e}")
            return {}

    # ==================== ERROR LOGGING ====================

    def log_error(self, error_data: Dict[str, Any]) -> bool:
        """Log an error to MongoDB."""
        if not self.is_available():
            return False

        try:
            collection = self.db[self.ERRORS_COLLECTION]
            error_data['timestamp'] = datetime.now().isoformat()
            error_data['strategy_version'] = "3.4.0"

            result = collection.insert_one(error_data)
            return result.acknowledged

        except Exception as e:
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_ERROR_LOG: Failed - {e}")
            return False

    # ==================== UTILITY METHODS ====================

    def _generate_id(self, data: Dict[str, Any]) -> str:
        """Generate a unique ID for a signal."""
        symbol = data.get('symbol', 'UNKNOWN')
        signal_type = data.get('signal_type', 'UNKNOWN')
        timestamp = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
        return f"{symbol}_{signal_type}_{timestamp}"

    def get_collection_stats(self, collection_name: str) -> Dict:
        """Get statistics for a collection."""
        if not self.is_available():
            return {}

        try:
            collection = self.db[collection_name]
            count = collection.count_documents({})

            return {
                'name': collection_name,
                'count': count,
                'exists': True
            }

        except Exception as e:
            mongo_logger.error(f"{EMOJI['ERROR']} MONGODB_COLLECTION_STATS: Failed - {e}")
            return {'name': collection_name, 'count': 0, 'exists': False}

    def cleanup(self):
        """Clean up MongoDB connection."""
        if self.client:
            self.client.close()
            mongo_logger.info(f"{EMOJI['STOP']} MONGODB: Connection closed")

    def __del__(self):
        """Destructor to ensure connection is closed."""
        self.cleanup()


# Create singleton instance
mongodb_client = MongoDBClient()

# Export for compatibility with existing code
firebase_client = mongodb_client

__all__ = [
    'mongodb_client',
    'firebase_client',
    'MongoDBClient',
]
