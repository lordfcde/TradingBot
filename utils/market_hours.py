"""
Market Hours Utility
Handles Vietnam stock market trading hours and session checks
"""
from datetime import datetime, time

class MarketHours:
    """Vietnam stock market trading hours"""
    
    # Trading sessions
    MORNING_START = time(9, 0)
    MORNING_END = time(11, 30)
    AFTERNOON_START = time(13, 0)
    AFTERNOON_END = time(15, 0)
    
    # Lunch break
    LUNCH_START = time(11, 30)
    LUNCH_END = time(13, 0)
    
    @staticmethod
    def is_trading_hours(dt: datetime = None) -> bool:
        """Check if current time is within trading hours"""
        if dt is None:
            dt = datetime.now()
        
        current_time = dt.time()
        
        # Check if weekend
        if dt.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        
        # Check morning session
        if MarketHours.MORNING_START <= current_time < MarketHours.MORNING_END:
            return True
        
        # Check afternoon session
        if MarketHours.AFTERNOON_START <= current_time < MarketHours.AFTERNOON_END:
            return True
        
        return False
    
    @staticmethod
    def is_lunch_break(dt: datetime = None) -> bool:
        """Check if current time is lunch break"""
        if dt is None:
            dt = datetime.now()
        
        current_time = dt.time()
        
        # Check if weekday
        if dt.weekday() >= 5:
            return False
        
        return MarketHours.LUNCH_START <= current_time < MarketHours.LUNCH_END
    
    @staticmethod
    def is_market_open(dt: datetime = None) -> bool:
        """Alias for is_trading_hours"""
        return MarketHours.is_trading_hours(dt)
    
    @staticmethod
    def get_session_name(dt: datetime = None) -> str:
        """Get current session name"""
        if dt is None:
            dt = datetime.now()
        
        if dt.weekday() >= 5:
            return "WEEKEND"
        
        current_time = dt.time()
        
        if MarketHours.MORNING_START <= current_time < MarketHours.MORNING_END:
            return "MORNING"
        elif MarketHours.LUNCH_START <= current_time < MarketHours.LUNCH_END:
            return "LUNCH"
        elif MarketHours.AFTERNOON_START <= current_time < MarketHours.AFTERNOON_END:
            return "AFTERNOON"
        else:
            return "CLOSED"
