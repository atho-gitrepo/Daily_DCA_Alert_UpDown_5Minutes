"""
Firebase Client for Trading Bot - HYBRID STRATEGY.
FIXED: Separate collections for active/resolved signals, proper status handling, no expiry.
Version: 3.2.2 - FIXED: Collection name consistency, robust error handling for resolved saves
"""

import json
import logging
import time
from typing import Optional, Dict, Any, List, Union, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
import hashlib
from pathlib import Path
import threading
import pandas as pd
import numpy as np

# Firebase imports
try:
    import firebase_admin
    from firebase_admin import credentials, firestore, storage
    from firebase_admin.firestore import firestore as FirestoreClient
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    logging.warning("Firebase Admin SDK not installed. Firebase features will be disabled.")

# Local imports
from settings import config, Config

# Configure logging
logger = logging.getLogger(__name__)
firebase_logger = logging.getLogger("firebase_client")

EMOJI = {
    "START": "🚀",
    "SUCCESS": "✅",
    "ERROR": "❌",
    "WARNING": "⚠️",
    "INFO": "ℹ️",
    "DEBUG": "🔍",
    "SAVE": "💾",
    "LOAD": "📥",
    "QUERY": "🔍",
    "BACKUP": "📦",
    "SYNC": "🔄",
    "VALIDATE": "✔️",
    "PERFORMANCE": "⚡",
    "CONNECT": "🔌",
    "BATCH": "📋",
    "SNIPER": "🎯",
    "INDEX": "📇",
    "VERSION": "📌",
    "CACHE": "💾",
    "UPDATE": "📝",
    "DELETE": "🗑️",
    "RESULT": "📊",
    "RESTORE": "♻️",
    "ACTIVE": "🔴",
    "RESOLVED": "✅",
    "SCORE": "🎯",
}


# ==================== DATA VALIDATION ====================

class FirebaseValidator:
    """
    ✅ UPDATED v3.2.2: Validate data before saving to Firebase.
    """
    
    REQUIRED_FIELDS = [
        'symbol', 'signal_type', 'entry_price', 'stop_loss', 
        'take_profit', 'confidence', 'status', 'entry_time'
    ]
    
    RECOMMENDED_FIELDS = [
        'total_score', 'quality_score', 'component_scores',
        'bb_position', 'volume_ratio', 'tdi_zone'
    ]
    
    VALID_STATUSES = ['ACTIVE', 'PROFIT', 'LOSS', 'CLOSED', 'PARTIAL_PROFIT', 'PARTIAL_LOSS', 'BREAK_EVEN']
    VALID_SIGNAL_TYPES = ['BUY', 'SELL']
    VALID_ENTRY_TYPES = ['SNIPER', 'HYBRID', 'STANDARD']
    
    VALID_TDI_ZONES = [
        'OVERSOLD', 'SOFT_BUY', 'BUY_ZONE', 'NO_TRADE', 
        'SOFT_SELL', 'OVERBOUGHT', 'NEUTRAL',
        'HARD_BUY', 'HARD_SELL'
    ]
    
    @classmethod
    def validate_signal_data(cls, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate signal data with new fields."""
        errors = []
        warnings = []
        
        for field in cls.REQUIRED_FIELDS:
            if field not in data or data[field] is None:
                errors.append(f"Missing required field: {field}")
        
        for field in cls.RECOMMENDED_FIELDS:
            if field not in data or data[field] is None:
                warnings.append(f"Missing recommended field: {field}")
        
        if data.get('entry_price', 0) <= 0:
            errors.append("entry_price must be > 0")
        if data.get('stop_loss', 0) <= 0:
            errors.append("stop_loss must be > 0")
        if data.get('take_profit', 0) <= 0:
            errors.append("take_profit must be > 0")
        if not 0 < data.get('confidence', 0) <= 1:
            errors.append("confidence must be between 0 and 1")
        
        total_score = data.get('total_score')
        if total_score is not None:
            if not isinstance(total_score, (int, float)) or not 0 <= total_score <= 100:
                errors.append(f"total_score must be 0-100, got {total_score}")
        
        component_scores = data.get('component_scores')
        if component_scores is not None and not isinstance(component_scores, dict):
            errors.append("component_scores must be a dict")
        
        bb_position = data.get('bb_position')
        if bb_position is not None:
            if not isinstance(bb_position, (int, float)) or not 0 <= bb_position <= 1:
                errors.append(f"bb_position must be 0-1, got {bb_position}")
        
        if data.get('signal_type') not in cls.VALID_SIGNAL_TYPES:
            errors.append(f"Invalid signal_type: {data.get('signal_type')}")
        if data.get('status') not in cls.VALID_STATUSES:
            errors.append(f"Invalid status: {data.get('status')}")
        if data.get('entry_type') and data.get('entry_type') not in cls.VALID_ENTRY_TYPES:
            errors.append(f"Invalid entry_type: {data.get('entry_type')}")
        
        tdi_zone = data.get('tdi_zone')
        if tdi_zone and tdi_zone not in cls.VALID_TDI_ZONES:
            warnings.append(f"Unknown TDI zone: {tdi_zone} (will be stored as-is)")
        
        if data.get('signal_type') == 'BUY':
            if data.get('stop_loss', 0) >= data.get('entry_price', 0):
                errors.append("SL must be below entry for BUY")
            if data.get('take_profit', 0) <= data.get('entry_price', 0):
                errors.append("TP must be above entry for BUY")
        elif data.get('signal_type') == 'SELL':
            if data.get('stop_loss', 0) <= data.get('entry_price', 0):
                errors.append("SL must be above entry for SELL")
            if data.get('take_profit', 0) >= data.get('entry_price', 0):
                errors.append("TP must be below entry for SELL")
        
        if warnings:
            firebase_logger.debug(f"{EMOJI['WARNING']} FIREBASE_VALIDATE: Warnings: {warnings}")
        
        return len(errors) == 0, errors


# ==================== CONVERTERS ====================

def convert_to_serializable(obj: Any) -> Any:
    """Convert numpy and pandas types to Python native types."""
    if obj is None:
        return None
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        if np.isnan(obj) or np.isinf(obj):
            return 0.0
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, (pd.Series, pd.DataFrame)):
        if isinstance(obj, pd.Series):
            result = obj.to_dict()
            return {k: convert_to_serializable(v) for k, v in result.items()}
        else:
            return obj.to_dict(orient='records')
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_to_serializable(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return 0.0
        return obj
    else:
        return obj


# ==================== FIREBASE CLIENT ====================

class FirebaseClient:
    """
    ✅ UPDATED v3.2.2: Firebase Firestore client with fixed resolved collection handling.
    """
    
    def __init__(self):
        log_firebase_operation("INIT", "START", emoji=EMOJI['START'])
        
        self.client = None
        self.db = None
        self.bucket = None
        self.initialized = False
        
        # ✅ FIXED: Use consistent collection names
        self.active_collection = "active_signals"
        self.resolved_collection = "resolved_signals"
        self.archive_collection = "archive_signals"
        
        self.metrics = {
            "total_saves": 0,
            "total_loads": 0,
            "total_queries": 0,
            "total_errors": 0,
            "avg_save_time": 0.0,
            "avg_load_time": 0.0,
            "validation_errors": 0,
            "result_saves": 0,
            "active_deletions": 0,
            "restored_signals": 0,
            "resolved_signals": 0,
            "score_fields_saved": 0,
            "score_fields_missing": 0,
            "version_3_2_0_signals": 0,
        }
        
        self.cache = {}
        self.cache_ttl = 300
        self.cache_timestamps = {}
        
        self.stats = {
            "total_active": 0,
            "total_resolved": 0,
            "total_profitable": 0,
            "total_losing": 0,
            "total_break_even": 0,
            "total_high_score": 0,
            "total_medium_score": 0,
            "total_low_score": 0,
        }
        
        self._init_client()
        
        log_firebase_operation("INIT", "SUCCESS", 
                              {"initialized": self.initialized, "version": "3.2.2"},
                              emoji=EMOJI['SUCCESS'])
        firebase_logger.info(f"{EMOJI['SUCCESS']} FIREBASE_INIT v3.2.2: Client {'initialized' if self.initialized else 'not available'}")
        firebase_logger.info(f"{EMOJI['ACTIVE']} Active collection: {self.active_collection}")
        firebase_logger.info(f"{EMOJI['RESOLVED']} Resolved collection: {self.resolved_collection}")
    
    def _init_client(self):
        if not FIREBASE_AVAILABLE:
            firebase_logger.warning(f"{EMOJI['WARNING']} FIREBASE_INIT: Firebase Admin SDK not available")
            return
        
        try:
            creds = config.firebase.credentials
            creds_path = config.firebase.credentials_path
            
            if not creds and not creds_path:
                firebase_logger.warning(f"{EMOJI['WARNING']} FIREBASE_INIT: No credentials provided")
                return
            
            if creds_path and creds_path.exists():
                firebase_logger.info(f"{EMOJI['INFO']} FIREBASE_INIT: Using credentials file: {creds_path}")
                cred = credentials.Certificate(str(creds_path))
            elif creds:
                firebase_logger.info(f"{EMOJI['INFO']} FIREBASE_INIT: Using credentials dictionary")
                cred = credentials.Certificate(creds)
            else:
                firebase_logger.warning(f"{EMOJI['WARNING']} FIREBASE_INIT: No valid credentials found")
                return
            
            if not firebase_admin._apps:
                storage_bucket = None
                if config.firebase.database_url:
                    storage_bucket = config.firebase.database_url.replace('https://', '').replace('.firebaseio.com', '.appspot.com')
                
                firebase_admin.initialize_app(cred, {
                    'databaseURL': config.firebase.database_url,
                    'storageBucket': storage_bucket
                })
                firebase_logger.info(f"{EMOJI['SUCCESS']} FIREBASE_INIT: Firebase app initialized")
            
            self.db = firestore.client()
            self.client = self.db
            
            try:
                self.bucket = storage.bucket()
                firebase_logger.info(f"{EMOJI['SUCCESS']} FIREBASE_INIT: Storage client initialized")
            except Exception as e:
                firebase_logger.debug(f"{EMOJI['INFO']} FIREBASE_INIT: Storage client not available: {e}")
                self.bucket = None
            
            self.initialized = True
            
            firebase_logger.info(f"{EMOJI['SUCCESS']} FIREBASE_INIT: Connected to project")
            
        except Exception as e:
            log_firebase_operation("INIT", "FAILURE", {"error": str(e)}, emoji=EMOJI['ERROR'])
            firebase_logger.error(f"{EMOJI['ERROR']} FIREBASE_INIT: {e}", exc_info=True)
            self.initialized = False
    
    def is_available(self) -> bool:
        return self.initialized and self.db is not None
    
    def _get_active_collection(self):
        if not self.is_available():
            return None
        return self.db.collection(self.active_collection)
    
    def _get_resolved_collection(self):
        if not self.is_available():
            return None
        return self.db.collection(self.resolved_collection)
    
    def _get_archive_collection(self):
        if not self.is_available():
            return None
        return self.db.collection(self.archive_collection)
    
    def _generate_document_id(self, data: Dict[str, Any]) -> str:
        """Generate a consistent document ID."""
        symbol = data.get('symbol', 'UNKNOWN')
        signal_type = data.get('signal_type', 'UNKNOWN')
        
        timestamp_str = data.get('entry_time')
        if timestamp_str:
            try:
                if isinstance(timestamp_str, str):
                    dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    dt = dt.replace(microsecond=0)
                else:
                    dt = datetime.now().replace(microsecond=0)
            except (ValueError, TypeError):
                dt = datetime.now().replace(microsecond=0)
        else:
            dt = datetime.now().replace(microsecond=0)
        
        time_str = dt.strftime('%Y-%m-%dT%H-%M-%S')
        return f"{symbol}_{signal_type}_{time_str}"
    
    def _get_cache_key(self, collection: str, document_id: str) -> str:
        return f"{collection}:{document_id}"
    
    def _is_cache_valid(self, key: str) -> bool:
        if key not in self.cache_timestamps:
            return False
        return time.time() - self.cache_timestamps[key] < self.cache_ttl
    
    def _clear_cache(self):
        self.cache.clear()
        self.cache_timestamps.clear()
    
    # ==================== SAVE SIGNAL ====================
    
    def save_signal(self, signal_data: Dict[str, Any]) -> Optional[str]:
        """Save signal with scoring fields. Returns the document ID on success."""
        start_time = time.time()
        symbol = signal_data.get('symbol', 'UNKNOWN')
        log_firebase_operation("SAVE", "START", {"symbol": symbol}, emoji=EMOJI['SAVE'])
        
        if not self.is_available():
            firebase_logger.warning(f"{EMOJI['WARNING']} FIREBASE_SAVE: Firebase not available")
            return None
        
        try:
            is_valid, errors = FirebaseValidator.validate_signal_data(signal_data)
            if not is_valid:
                self.metrics["validation_errors"] += 1
                firebase_logger.error(f"{EMOJI['ERROR']} FIREBASE_SAVE: Validation failed: {errors}")
                return None
            
            doc_data = convert_to_serializable(signal_data)
            
            if 'status' not in doc_data:
                doc_data['status'] = 'ACTIVE'
            if 'entry_time' not in doc_data:
                doc_data['entry_time'] = datetime.now().isoformat()
            if 'timestamp' not in doc_data:
                doc_data['timestamp'] = datetime.now().isoformat()
            if 'updated_at' not in doc_data:
                doc_data['updated_at'] = datetime.now().isoformat()
            
            doc_data.setdefault('ltf_confirmed', False)
            doc_data.setdefault('ltf_confidence', 0)
            doc_data.setdefault('htf_aligned', False)
            doc_data.setdefault('quality_score', 50)
            doc_data.setdefault('total_score', 0)
            doc_data.setdefault('component_scores', {})
            doc_data.setdefault('bb_position', 0.5)
            doc_data.setdefault('volume_ratio', 1.0)
            doc_data.setdefault('tdi_zone_standardized', doc_data.get('tdi_zone', 'NEUTRAL'))
            doc_data.setdefault('rejection_reason', '')
            doc_data.setdefault('strategy_version', 'v3.2.2-super-tdi-15m')
            
            if doc_data.get('total_score', 0) > 0:
                self.metrics["score_fields_saved"] += 1
                self.metrics["version_3_2_0_signals"] += 1
                
                score = doc_data['total_score']
                if score >= 80:
                    self.stats["total_high_score"] += 1
                elif score >= 65:
                    self.stats["total_medium_score"] += 1
                else:
                    self.stats["total_low_score"] += 1
            else:
                self.metrics["score_fields_missing"] += 1
            
            doc_id = self._generate_document_id(doc_data)
            doc_data['doc_id'] = doc_id
            
            active_collection = self._get_active_collection()
            if not active_collection:
                return None
            
            doc_ref = active_collection.document(doc_id)
            doc_ref.set(doc_data, merge=True)
            
            elapsed = time.time() - start_time
            self.metrics["total_saves"] += 1
            self.metrics["avg_save_time"] = (
                (self.metrics["avg_save_time"] * (self.metrics["total_saves"] - 1) + elapsed) / 
                self.metrics["total_saves"]
            )
            
            self.stats["total_active"] += 1
            
            cache_key = self._get_cache_key(self.active_collection, doc_id)
            self.cache[cache_key] = doc_data
            self.cache_timestamps[cache_key] = time.time()
            
            score_info = f" | Score: {doc_data.get('total_score', 0)}/100" if doc_data.get('total_score', 0) > 0 else ""
            component_info = ""
            if doc_data.get('component_scores'):
                cs = doc_data['component_scores']
                parts = []
                for k in ['ltf', 'tdi', 'bb', 'volume', 'reversal']:
                    if k in cs:
                        parts.append(f"{k}={cs[k]:.0f}")
                if parts:
                    component_info = f" | [{', '.join(parts)}]"
            
            log_firebase_operation("SAVE", "SUCCESS", 
                                  {"doc_id": doc_id, "elapsed_ms": elapsed * 1000},
                                  emoji=EMOJI['SUCCESS'])
            firebase_logger.info(
                f"{EMOJI['SAVE']} FIREBASE_SAVE: {doc_id} | "
                f"Symbol: {symbol} | Status: {doc_data['status']}"
                f"{score_info}{component_info}"
            )
            
            return doc_id
            
        except Exception as e:
            self.metrics["total_errors"] += 1
            log_firebase_operation("SAVE", "FAILURE", {"error": str(e)}, emoji=EMOJI['ERROR'])
            firebase_logger.error(f"{EMOJI['ERROR']} FIREBASE_SAVE: {e}", exc_info=True)
            return None
    
    # ==================== UPDATE SIGNAL STATUS - FIXED v3.2.2 ====================
    
    def update_signal_status(self, doc_id: str, status: Union[str, Any], 
                            update_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        ✅ FIXED v3.2.2: Ensures signal is properly moved to resolved collection.
        """
        log_firebase_operation("UPDATE", "START", 
                              {"doc_id": doc_id, "status": str(status)},
                              emoji=EMOJI['UPDATE'])
        
        if not self.is_available():
            firebase_logger.warning(f"{EMOJI['WARNING']} FIREBASE_UPDATE: Firebase not available")
            return False
        
        if not doc_id:
            firebase_logger.warning(f"{EMOJI['WARNING']} FIREBASE_UPDATE: No doc_id provided")
            return False
        
        try:
            if hasattr(status, 'value'):
                status_str = status.value
            else:
                status_str = str(status)
            
            db = self._get_active_collection()
            if db is None:
                firebase_logger.warning(f"{EMOJI['WARNING']} FIREBASE_UPDATE: Cannot access active collection")
                return False
            
            # Get the active collection reference
            active_collection = self.db.collection(self.active_collection)
            doc_ref = active_collection.document(doc_id)
            snapshot = doc_ref.get()
            
            if not snapshot.exists:
                firebase_logger.warning(f"{EMOJI['WARNING']} FIREBASE_UPDATE: Document {doc_id} not found in active collection")
                # Check if it's already in resolved
                resolved_collection = self.db.collection(self.resolved_collection)
                if resolved_collection:
                    resolved_snapshot = resolved_collection.document(doc_id).get()
                    if resolved_snapshot.exists:
                        firebase_logger.info(f"{EMOJI['INFO']} FIREBASE_UPDATE: Document {doc_id} already in resolved collection")
                        return True
                return False
            
            current_data = snapshot.to_dict()
            
            updates = {
                'status': status_str,
                'updated_at': datetime.now().isoformat()
            }
            
            is_terminal = status_str in ['PROFIT', 'LOSS', 'BREAK_EVEN', 'CLOSED']
            
            if is_terminal:
                updates['exit_time'] = datetime.now().isoformat()
                if update_data:
                    for key in ['exit_price', 'pnl', 'pnl_percent', 'fees', 'bars_held', 'age_minutes', 'total_score']:
                        if key in update_data:
                            updates[key] = update_data[key]
            
            if is_terminal:
                # ✅ FIXED: Save to resolved with proper collection reference
                resolved_data = current_data.copy()
                resolved_data.update(updates)
                resolved_data['resolved_at'] = datetime.now().isoformat()
                resolved_data['original_doc_id'] = doc_id
                
                resolved_data.setdefault('total_score', current_data.get('total_score', 0))
                resolved_data.setdefault('component_scores', current_data.get('component_scores', {}))
                resolved_data.setdefault('bb_position', current_data.get('bb_position', 0.5))
                resolved_data.setdefault('volume_ratio', current_data.get('volume_ratio', 1.0))
                resolved_data.setdefault('strategy_version', current_data.get('strategy_version', 'v3.2.2'))
                
                # ✅ FIXED: Use explicit collection reference
                resolved_collection = self.db.collection(self.resolved_collection)
                resolved_saved = False
                
                try:
                    # Save to resolved collection
                    resolved_doc = resolved_collection.document(doc_id)
                    resolved_doc.set(resolved_data, merge=True)
                    resolved_saved = True
                    
                    self.metrics["resolved_signals"] += 1
                    self.stats["total_resolved"] += 1
                    
                    if status_str == 'PROFIT':
                        self.stats["total_profitable"] += 1
                    elif status_str == 'LOSS':
                        self.stats["total_losing"] += 1
                    elif status_str == 'BREAK_EVEN':
                        self.stats["total_break_even"] += 1
                    
                    score = resolved_data.get('total_score', 0)
                    pnl = updates.get('pnl', 0)
                    
                    firebase_logger.info(
                        f"{EMOJI['RESOLVED']} ✅ FIREBASE_RESOLVED: {doc_id} saved to {self.resolved_collection} | "
                        f"Status: {status_str} | PnL: ${pnl:.2f} | Score: {score}/100"
                    )
                except Exception as resolve_err:
                    firebase_logger.error(f"{EMOJI['ERROR']} FIREBASE_RESOLVE: Failed to save to resolved: {resolve_err}")
                    # Try to create the collection by saving with a dummy document
                    try:
                        # Some Firestore implementations need the collection to exist
                        dummy_ref = resolved_collection.document(f"_dummy_{doc_id}")
                        dummy_ref.set({"temp": True})
                        dummy_ref.delete()
                        # Retry saving
                        resolved_doc = resolved_collection.document(doc_id)
                        resolved_doc.set(resolved_data, merge=True)
                        resolved_saved = True
                        firebase_logger.info(f"{EMOJI['SUCCESS']} FIREBASE_RESOLVE: Retry succeeded for {doc_id}")
                    except Exception as retry_err:
                        firebase_logger.error(f"{EMOJI['ERROR']} FIREBASE_RESOLVE: Retry also failed: {retry_err}")
                
                # ✅ FIXED: Delete from active AFTER resolved save attempt
                delete_success = False
                try:
                    doc_ref.delete()
                    delete_success = True
                    self.metrics["active_deletions"] += 1
                    self.stats["total_active"] = max(0, self.stats["total_active"] - 1)
                    firebase_logger.info(f"{EMOJI['DELETE']} ✅ FIREBASE_DELETE: {doc_id} deleted from {self.active_collection}")
                except Exception as del_err:
                    firebase_logger.error(f"{EMOJI['ERROR']} FIREBASE_DELETE: Failed to delete from active: {del_err}")
                    
                    # Fallback: update the active document with resolved status
                    if not resolved_saved:
                        try:
                            doc_ref.update(updates)
                            firebase_logger.info(f"{EMOJI['UPDATE']} FIREBASE_UPDATE: {doc_id} updated in active (fallback)")
                            delete_success = True
                        except Exception as update_err:
                            firebase_logger.error(f"{EMOJI['ERROR']} FIREBASE_UPDATE: Active update also failed: {update_err}")
                
                # Clear cache
                cache_key = self._get_cache_key(self.active_collection, doc_id)
                if cache_key in self.cache:
                    del self.cache[cache_key]
                    del self.cache_timestamps[cache_key]
                
                # Return True if either resolved save or delete succeeded
                if resolved_saved or delete_success:
                    firebase_logger.info(f"{EMOJI['SUCCESS']} FIREBASE_UPDATE: Signal {doc_id} resolved successfully")
                    return True
                else:
                    firebase_logger.error(f"{EMOJI['ERROR']} FIREBASE_UPDATE: Signal {doc_id} resolution failed")
                    return False
            else:
                # Non-terminal status - just update in active collection
                doc_ref.update(updates)
                firebase_logger.debug(f"{EMOJI['UPDATE']} FIREBASE_UPDATE: {doc_id} -> {status_str}")
                return True
            
        except Exception as e:
            self.metrics["total_errors"] += 1
            log_firebase_operation("UPDATE", "FAILURE", {"error": str(e), "doc_id": doc_id}, emoji=EMOJI['ERROR'])
            firebase_logger.error(f"{EMOJI['ERROR']} FIREBASE_UPDATE: Unexpected error for {doc_id}: {e}", exc_info=True)
            return False
    
    # ==================== GET ACTIVE SIGNALS ====================
    
    def get_active_signals(self) -> Dict[str, Dict[str, Any]]:
        """Get active signals with field defaults."""
        if not self.is_available():
            return {}
        
        try:
            active_collection = self.db.collection(self.active_collection)
            docs = active_collection.where('status', '==', 'ACTIVE').get()
            
            signals = {}
            for doc in docs:
                data = doc.to_dict()
                data['doc_id'] = doc.id
                
                data.setdefault('total_score', 0)
                data.setdefault('component_scores', {})
                data.setdefault('bb_position', 0.5)
                data.setdefault('volume_ratio', 1.0)
                data.setdefault('tdi_zone_standardized', data.get('tdi_zone', 'NEUTRAL'))
                data.setdefault('strategy_version', 'unknown')
                data.setdefault('rejection_reason', '')
                
                signals[doc.id] = data
            
            self.metrics["total_queries"] += 1
            firebase_logger.debug(f"{EMOJI['LOAD']} FIREBASE_LOAD: Found {len(signals)} active signals")
            
            return signals
            
        except Exception as e:
            firebase_logger.error(f"{EMOJI['ERROR']} FIREBASE_QUERY: {e}")
            return {}
    
    # ==================== GET RESOLVED SIGNALS ====================
    
    def get_resolved_signals(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get resolved signals with field defaults."""
        if not self.is_available():
            return []
        
        try:
            resolved_collection = self.db.collection(self.resolved_collection)
            docs = resolved_collection.order_by('resolved_at', direction=firestore.Query.DESCENDING).limit(limit).get()
            
            signals = []
            for doc in docs:
                data = doc.to_dict()
                data['doc_id'] = doc.id
                
                data.setdefault('total_score', 0)
                data.setdefault('component_scores', {})
                data.setdefault('strategy_version', 'unknown')
                
                signals.append(data)
            
            return signals
            
        except Exception as e:
            firebase_logger.error(f"{EMOJI['ERROR']} FIREBASE_QUERY: {e}")
            return []
    
    # ==================== RESTORE SIGNAL ====================
    
    def restore_signal(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Restore a signal from resolved to active."""
        if not self.is_available():
            return None
        
        try:
            resolved_collection = self.db.collection(self.resolved_collection)
            doc_ref = resolved_collection.document(doc_id)
            snapshot = doc_ref.get()
            
            if not snapshot.exists:
                firebase_logger.warning(f"{EMOJI['WARNING']} FIREBASE_RESTORE: Document {doc_id} not found in resolved")
                return None
            
            data = snapshot.to_dict()
            
            data['status'] = 'ACTIVE'
            data['restored_at'] = datetime.now().isoformat()
            data['updated_at'] = datetime.now().isoformat()
            
            data.setdefault('total_score', 0)
            data.setdefault('component_scores', {})
            
            for field in ['resolved_at', 'original_doc_id']:
                if field in data:
                    del data[field]
            
            active_collection = self.db.collection(self.active_collection)
            active_doc = active_collection.document(doc_id)
            active_doc.set(data, merge=True)
            self.metrics["restored_signals"] += 1
            self.stats["total_active"] += 1
            
            score_info = f" | Score: {data.get('total_score', 0)}/100" if data.get('total_score', 0) > 0 else ""
            firebase_logger.info(f"{EMOJI['RESTORE']} FIREBASE_RESTORE: {doc_id} restored{score_info}")
            
            doc_ref.delete()
            self.stats["total_resolved"] -= 1
            
            return data
            
        except Exception as e:
            firebase_logger.error(f"{EMOJI['ERROR']} FIREBASE_RESTORE: {e}")
            return None
    
    # ==================== DELETE SIGNAL ====================
    
    def delete_signal(self, doc_id: str, collection: str = None) -> bool:
        """Delete a signal from a collection."""
        if not self.is_available():
            firebase_logger.warning(f"{EMOJI['WARNING']} FIREBASE_DELETE: Firebase not available")
            return False
        
        if not doc_id:
            firebase_logger.warning(f"{EMOJI['WARNING']} FIREBASE_DELETE: No doc_id provided")
            return False
        
        try:
            if collection == 'active' or collection is None:
                coll = self.db.collection(self.active_collection)
            elif collection == 'resolved':
                coll = self.db.collection(self.resolved_collection)
            elif collection == 'archive':
                coll = self.db.collection(self.archive_collection)
            else:
                firebase_logger.warning(f"{EMOJI['WARNING']} FIREBASE_DELETE: Unknown collection: {collection}")
                return False
            
            doc_ref = coll.document(doc_id)
            
            snapshot = doc_ref.get()
            if not snapshot.exists:
                firebase_logger.warning(f"{EMOJI['WARNING']} FIREBASE_DELETE: Document {doc_id} not found in {collection or 'active'}")
                return False
            
            doc_ref.delete()
            
            cache_key = self._get_cache_key(collection or self.active_collection, doc_id)
            if cache_key in self.cache:
                del self.cache[cache_key]
                del self.cache_timestamps[cache_key]
            
            firebase_logger.info(f"{EMOJI['DELETE']} FIREBASE_DELETE: {doc_id} deleted from {collection or 'active'}")
            return True
            
        except Exception as e:
            firebase_logger.error(f"{EMOJI['ERROR']} FIREBASE_DELETE: Failed to delete {doc_id}: {e}")
            return False
    
    # ==================== GET STATS ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            **self.metrics,
            **self.stats,
            "initialized": self.initialized,
            "version": "3.2.2",
            "active_collection": self.active_collection,
            "resolved_collection": self.resolved_collection,
            "cache_size": len(self.cache),
            "collections": {
                "active": self.active_collection,
                "resolved": self.resolved_collection,
                "archive": self.archive_collection,
            },
        }
    
    def clear_cache(self):
        self._clear_cache()
        firebase_logger.info(f"{EMOJI['CACHE']} FIREBASE_CACHE: Cleared")
    
    def cleanup(self):
        self.clear_cache()


# ------------------- LOGGING HELPER -------------------

def log_firebase_operation(operation: str, status: str, details: Optional[Dict] = None,
                          emoji: str = "", error: Optional[Exception] = None):
    timestamp = datetime.now().isoformat()
    log_message = f"[{timestamp}] {emoji} FIREBASE_{operation}: {status}"
    
    if details:
        safe_details = {}
        for k, v in details.items():
            if isinstance(v, float):
                safe_details[k] = round(v, 4)
            elif isinstance(v, str) and len(v) > 100:
                safe_details[k] = v[:100] + "..."
            else:
                safe_details[k] = v
        log_message += f" | Details: {safe_details}"
    
    if error:
        log_message += f" | Error: {str(error)}"
    
    if status == "FAILURE":
        firebase_logger.error(log_message)
    elif status == "WARNING":
        firebase_logger.warning(log_message)
    else:
        firebase_logger.info(log_message)


# ------------------- Singleton Instance -------------------

firebase_client = FirebaseClient()

__all__ = [
    "firebase_client",
    "FirebaseClient",
    "FirebaseValidator",
    "convert_to_serializable",
]