#!/usr/bin/env python3
"""
Logging Configuration - Simple logging setup
Version: 3.4.6 - FIXED: Simplified, no fancy parts
"""

import os
import sys
import logging
import logging.handlers
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# ========== SIMPLE LOGGER MANAGER ==========
class LoggerManager:
    def __init__(self):
        self._initialized = False
        self._setup_logging()
    
    def _setup_logging(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # Determine log level
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, log_level, logging.INFO)
        
        # Format
        fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        datefmt = '%Y-%m-%d %H:%M:%S'
        formatter = logging.Formatter(fmt, datefmt)
        
        # Root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        
        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Console handler
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(formatter)
        root_logger.addHandler(console)
        
        # File handler with rotation
        try:
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            
            log_file = log_dir / "trading_bot.log"
            file_handler = logging.handlers.RotatingFileHandler(
                filename=log_file,
                maxBytes=10_000_000,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Could not create log file: {e}")
        
        self.logger = root_logger
        self.logger.info("✅ Logging system initialized")
    
    def get_logger(self, name: str) -> logging.Logger:
        return logging.getLogger(name)


# ========== SINGLETON ==========
logger_manager = LoggerManager()

# ========== MAIN LOGGERS ==========
def get_logger(name: str) -> logging.Logger:
    return logger_manager.get_logger(name)

# Create loggers for different modules
main_logger = get_logger("main")
strategy_logger = get_logger("strategy")
ai_logger = get_logger("ai_analyzer")
signal_logger = get_logger("signal_manager")
telegram_logger = get_logger("telegram_bot")
firebase_logger = get_logger("firebase_client")
indicators_logger = get_logger("indicators")
data_logger = get_logger("data_fetcher")

# Backward compatibility
logger = main_logger

__all__ = [
    'logger_manager',
    'logger',
    'main_logger',
    'strategy_logger',
    'ai_logger',
    'signal_logger',
    'telegram_logger',
    'firebase_logger',
    'indicators_logger',
    'data_logger',
    'get_logger',
]