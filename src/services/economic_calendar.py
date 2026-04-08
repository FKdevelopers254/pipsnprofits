"""
Economic Calendar Service
Filters trading during high-impact economic news events
"""

import logging
import aiohttp
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NewsEvent:
    """Economic news event data structure"""
    time: datetime
    country: str
    event: str
    impact: str  # High, Medium, Low
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None


class EconomicCalendar:
    """
    Economic Calendar service for filtering trades during news events
    """
    
    def __init__(self):
        self.cache_events: List[NewsEvent] = []
        self.cache_expiry: Optional[datetime] = None
        self.cache_duration_hours = 4  # Refresh cache every 4 hours
        self.high_impact_minutes_before = 30  # Avoid trading X minutes before high impact
        self.high_impact_minutes_after = 30  # Avoid trading X minutes after high impact
        self.medium_impact_minutes = 15  # Avoid trading around medium impact
        
    async def get_news_events(self, days_ahead: int = 7) -> List[NewsEvent]:
        """
        Fetch economic news events from API or use cached data
        
        Args:
            days_ahead: Number of days ahead to fetch events
            
        Returns:
            List of NewsEvent objects
        """
        now = datetime.now(timezone.utc)
        
        # Check if cache is still valid
        if (self.cache_events and self.cache_expiry and 
            now < self.cache_expiry):
            return self.cache_events
        
        try:
            # For demo purposes, create mock high-impact events
            # In production, integrate with real  
            events = await self._fetch_mock_events(days_ahead)
            
            # Update cache
            self.cache_events = events
            self.cache_expiry = now + timedelta(hours=self.cache_duration_hours)
            
            logger.info("Economic calendar updated: %d events cached", len(events))
            return events
            
        except Exception as e:
            logger.exception("Error fetching economic calendar: %s", e)
            return self.cache_events or []
    
    async def _fetch_mock_events(self, days_ahead: int) -> List[NewsEvent]:
        """
        Mock economic events for demonstration
        In production, replace with real API call to:
        - ForexFactory API
        - DailyFX API  
        - Investing.com API
        """
        now = datetime.now(timezone.utc)
        events = []
        
        # Sample high-impact events (mock data)
        high_impact_events = [
            "FOMC Interest Rate Decision",
            "CPI Data Release", 
            "Non-Farm Payrolls",
            "GDP Growth Rate",
            "Unemployment Rate",
            "Retail Sales",
            "PMI Manufacturing",
            "Consumer Confidence"
        ]
        
        medium_impact_events = [
            "ADP Employment",
            "Building Permits",
            "Trade Balance",
            "Core PCE Price Index"
        ]
        
        # Generate mock events for the next few days
        for day in range(days_ahead):
            event_date = now + timedelta(days=day)
            
            # Add 1-2 high impact events per day
            for i in range(2):
                event_time = event_date.replace(
                    hour=13 + i * 4,  # Spread events throughout the day
                    minute=30,
                    second=0,
                    microsecond=0
                )
                
                events.append(NewsEvent(
                    time=event_time,
                    country="USD",
                    event=high_impact_events[i % len(high_impact_events)],
                    impact="High"
                ))
            
            # Add medium impact events
            for i in range(1):
                event_time = event_date.replace(
                    hour=10 + i * 3,
                    minute=0,
                    second=0,
                    microsecond=0
                )
                
                events.append(NewsEvent(
                    time=event_time,
                    country="USD", 
                    event=medium_impact_events[i % len(medium_impact_events)],
                    impact="Medium"
                ))
        
        return events
    
    async def should_avoid_trading(self, symbol: str = "XAUUSD") -> tuple[bool, Optional[str]]:
        """
        Check if trading should be avoided due to upcoming news
        
        Args:
            symbol: Trading symbol (used to determine relevant currency)
            
        Returns:
            Tuple of (should_avoid, reason)
        """
        try:
            now = datetime.now(timezone.utc)
            events = await self.get_news_events()
            
            # Filter events relevant to the symbol
            relevant_events = self._filter_relevant_events(events, symbol)
            
            for event in relevant_events:
                minutes_until = (event.time - now).total_seconds() / 60
                minutes_since = (now - event.time).total_seconds() / 60
                
                # Check if we're too close to a high-impact event
                if event.impact == "High":
                    if abs(minutes_until) <= self.high_impact_minutes_before:
                        return True, f"High impact news in {abs(int(minutes_until))}min: {event.event}"
                    elif abs(minutes_since) <= self.high_impact_minutes_after:
                        return True, f"High impact news {abs(int(minutes_since))}min ago: {event.event}"
                
                # Check medium impact events
                elif event.impact == "Medium":
                    if abs(minutes_until) <= self.medium_impact_minutes:
                        return True, f"Medium impact news in {abs(int(minutes_until))}min: {event.event}"
                    elif abs(minutes_since) <= self.medium_impact_minutes:
                        return True, f"Medium impact news {abs(int(minutes_since))}min ago: {event.event}"
            
            return False, None
            
        except Exception as e:
            logger.exception("Error checking news filter: %s", e)
            return False, None
    
    def _filter_relevant_events(self, events: List[NewsEvent], symbol: str) -> List[NewsEvent]:
        """
        Filter events relevant to the trading symbol
        
        Args:
            events: All news events
            symbol: Trading symbol
            
        Returns:
            Filtered list of relevant events
        """
        relevant_currencies = set()
        
        # Map symbols to relevant currencies
        symbol_currency_map = {
            "XAUUSD": {"USD"},
            "EURUSD": {"EUR", "USD"},
            "GBPUSD": {"GBP", "USD"},
            "USDJPY": {"USD", "JPY"},
            "AUDUSD": {"AUD", "USD"},
            "USDCAD": {"USD", "CAD"},
            "NZDUSD": {"NZD", "USD"},
            "USDCHF": {"USD", "CHF"}
        }
        
        relevant_currencies = symbol_currency_map.get(symbol, {"USD"})
        
        # Filter events by relevant currencies
        filtered_events = []
        for event in events:
            if event.country in relevant_currencies:
                filtered_events.append(event)
        
        return filtered_events
    
    def get_upcoming_events(self, symbol: str = "XAUUSD", hours_ahead: int = 24) -> List[Dict[str, Any]]:
        """
        Get upcoming news events for display
        
        Args:
            symbol: Trading symbol
            hours_ahead: Hours to look ahead
            
        Returns:
            List of event dictionaries
        """
        try:
            now = datetime.now(timezone.utc)
            events = asyncio.run(self.get_news_events())
            relevant_events = self._filter_relevant_events(events, symbol)
            
            upcoming_events = []
            for event in relevant_events:
                hours_until = (event.time - now).total_seconds() / 3600
                
                if 0 <= hours_until <= hours_ahead:
                    upcoming_events.append({
                        "time": event.time.strftime("%Y-%m-%d %H:%M UTC"),
                        "country": event.country,
                        "event": event.event,
                        "impact": event.impact,
                        "hours_until": round(hours_until, 1)
                    })
            
            # Sort by time
            upcoming_events.sort(key=lambda x: x["hours_until"])
            
            return upcoming_events
            
        except Exception as e:
            logger.exception("Error getting upcoming events: %s", e)
            return []


# Singleton instance
economic_calendar = EconomicCalendar()
