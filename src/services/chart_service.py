import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import statistics

from src.services.price_action_detector import price_action_detector, analyze_price_action
from src.services.mt5_service import mt5_manager

logger = logging.getLogger(__name__)

# Timeframe mapping for MT5
TF_MAP = {
    'M1': 1,
    'M5': 5,
    'M15': 15,
    'M30': 30,
    'H1': 60,
    'H4': 240,
    'D1': 1440,
}

class ChartDataService:
    """Real-time chart data service for live price updates and technical indicators"""
    
    def __init__(self):
        self.candles = []
        self.volume = []
        self.indicators = {
            'ma20': [],
            'ma50': [],
            'ma200': [],
            'rsi': [],
            'macd': {'line': [], 'signal': [], 'histogram': []},
            'bb': {'upper': [], 'middle': [], 'lower': []}
        }
        self.trades = []
        self.levels = []
        self.price_action = {
            'fvgs': [],
            'zones': [],
            'bos': [],
            'summary': {}
        }
        self.current_price = 0.0
        self.symbol = 'XAUUSD'
        self.timeframe = 'H1'
        self.max_candles = 500
        self.subscribers = []
        
    def subscribe(self, callback):
        """Subscribe to real-time updates"""
        self.subscribers.append(callback)
    
    def unsubscribe(self, callback):
        """Unsubscribe from real-time updates"""
        if callback in self.subscribers:
            self.subscribers.remove(callback)
    
    def notify_subscribers(self, data):
        """Notify all subscribers of new data"""
        for callback in self.subscribers:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Error notifying subscriber: {e}")
    
    def add_candle(self, candle_data: Dict[str, Any]):
        """Add new candle and update indicators"""
        try:
            # Validate candle data
            required_fields = ['time', 'open', 'high', 'low', 'close', 'volume']
            for field in required_fields:
                if field not in candle_data:
                    logger.error(f"Missing required field in candle data: {field}")
                    return
            
            # Add candle
            self.candles.append(candle_data)
            
            # Keep only last N candles
            if len(self.candles) > self.max_candles:
                self.candles.pop(0)
            
            # Update current price
            self.current_price = candle_data['close']
            
            # Calculate technical indicators
            self._update_indicators()
            
            # Notify subscribers
            chart_data = self.get_chart_data()
            self.notify_subscribers(chart_data)
            
            logger.debug(f"Added candle: {candle_data['time']} - {candle_data['close']}")
            
        except Exception as e:
            logger.error(f"Error adding candle: {e}")
    
    def _update_indicators(self):
        """Calculate all technical indicators"""
        try:
            if len(self.candles) < 20:
                return  # Not enough data for indicators
            
            closes = [c['close'] for c in self.candles]
            highs = [c['high'] for c in self.candles]
            lows = [c['low'] for c in self.candles]
            volumes = [c['volume'] for c in self.candles]
            
            # Moving Averages
            self.indicators['ma20'] = self._calculate_sma(closes, 20)
            self.indicators['ma50'] = self._calculate_sma(closes, 50)
            self.indicators['ma200'] = self._calculate_sma(closes, 200)
            
            # RSI
            self.indicators['rsi'] = self._calculate_rsi(closes, 14)
            
            # MACD
            macd_data = self._calculate_macd(closes, 12, 26, 9)
            self.indicators['macd'] = macd_data
            
            # Bollinger Bands
            bb_data = self._calculate_bollinger_bands(closes, 20, 2)
            self.indicators['bb'] = bb_data
            
            # Volume data
            self.volume = volumes[-len(self.candles):]
            
            # Price Action Detection
            self._update_price_action()
            
        except Exception as e:
            logger.error(f"Error updating indicators: {e}")
    
    def _update_price_action(self):
        """Detect price action patterns"""
        try:
            if len(self.candles) >= 10:
                patterns = analyze_price_action(self.candles, self.timeframe)
                
                # Convert dataclass objects to dicts for JSON serialization
                self.price_action = {
                    'fvgs': [
                        {
                            'type': fvg.type,
                            'start_time': fvg.start_time.isoformat() if hasattr(fvg.start_time, 'isoformat') else str(fvg.start_time),
                            'end_time': fvg.end_time.isoformat() if hasattr(fvg.end_time, 'isoformat') else str(fvg.end_time),
                            'top_price': fvg.top_price,
                            'bottom_price': fvg.bottom_price,
                            'is_inverse': fvg.is_inverse,
                            'is_filled': fvg.is_filled,
                            'candles_since': fvg.candles_since,
                            'index': fvg.index
                        }
                        for fvg in patterns['fvgs']
                    ],
                    'zones': [
                        {
                            'type': zone.type,
                            'start_time': zone.start_time.isoformat() if hasattr(zone.start_time, 'isoformat') else str(zone.start_time),
                            'end_time': zone.end_time.isoformat() if hasattr(zone.end_time, 'isoformat') else str(zone.end_time) if zone.end_time else None,
                            'base_price': zone.base_price,
                            'top_price': zone.top_price,
                            'bottom_price': zone.bottom_price,
                            'is_active': zone.is_active,
                            'touches': zone.touches,
                            'index': zone.index,
                            'timeframe': zone.timeframe
                        }
                        for zone in patterns['zones']
                    ],
                    'bos': [
                        {
                            'type': bos.type,
                            'direction': bos.direction,
                            'time': bos.time.isoformat() if hasattr(bos.time, 'isoformat') else str(bos.time),
                            'price': bos.price,
                            'previous_swing': bos.previous_swing,
                            'index': bos.index,
                            'timeframe': bos.timeframe,
                            'strength': getattr(bos, 'strength', 50.0),
                            'break_magnitude': getattr(bos, 'break_magnitude', 0.0),
                            'volume_confirmed': getattr(bos, 'volume_confirmed', False),
                            'order_block_index': getattr(bos, 'order_block_index', None),
                            'fvg_confluence': getattr(bos, 'fvg_confluence', False),
                            'fvg_aligned_indices': getattr(bos, 'fvg_aligned_indices', []),
                            'confluence_score': getattr(bos, 'confluence_score', 0.0)
                        }
                        for bos in patterns['bos']
                    ],
                    'order_blocks': [
                        {
                            'type': ob.type,
                            'start_time': ob.start_time.isoformat() if hasattr(ob.start_time, 'isoformat') else str(ob.start_time),
                            'index': ob.index,
                            'open': ob.open,
                            'high': ob.high,
                            'low': ob.low,
                            'close': ob.close,
                            'volume': ob.volume,
                            'strength': ob.strength,
                            'is_active': ob.is_active,
                            'timeframe': ob.timeframe
                        }
                        for ob in patterns.get('order_blocks', [])
                    ],
                    'liquidity_sweeps': [
                        {
                            'type': ls.type,
                            'direction': ls.direction,
                            'time': ls.time.isoformat() if hasattr(ls.time, 'isoformat') else str(ls.time),
                            'sweep_price': ls.sweep_price,
                            'swing_price': ls.swing_price,
                            'choch_index': ls.choch_index,
                            'index': ls.index,
                            'strength': ls.strength,
                            'timeframe': ls.timeframe
                        }
                        for ls in patterns.get('liquidity_sweeps', [])
                    ],
                    'trade_suggestions': [
                        {
                            'type': ts.type,
                            'choch_index': ts.choch_index,
                            'entry_price': ts.entry_price,
                            'stop_loss': ts.stop_loss,
                            'take_profit': ts.take_profit,
                            'risk_reward': ts.risk_reward,
                            'confluence_score': ts.confluence_score,
                            'reasons': ts.reasons,
                            'timeframe': ts.timeframe,
                            'timestamp': ts.timestamp.isoformat() if hasattr(ts.timestamp, 'isoformat') else str(ts.timestamp),
                            'urgency': ts.urgency
                        }
                        for ts in patterns.get('trade_suggestions', [])
                    ],
                    'swing_points': patterns.get('swing_points', []),
                    'summary': patterns['summary']
                }
                
                logger.debug(f"Price action updated: {patterns['summary']}")
                
        except Exception as e:
            logger.error(f"Error updating price action: {e}")
    
    def _calculate_sma(self, data: List[float], period: int) -> List[float]:
        """Calculate Simple Moving Average"""
        if len(data) < period:
            return [None] * len(data)
        
        sma = []
        for i in range(len(data)):
            if i < period - 1:
                sma.append(None)
            else:
                avg = statistics.mean(data[i-period+1:i+1])
                sma.append(avg)
        
        return sma
    
    def _calculate_ema(self, data: List[float], period: int) -> List[float]:
        """Calculate Exponential Moving Average"""
        if len(data) < period:
            return [None] * len(data)
        
        multiplier = 2 / (period + 1)
        ema = [data[0]]  # Start with SMA
        
        for i in range(1, len(data)):
            ema.append((data[i] * multiplier) + (ema[-1] * (1 - multiplier)))
        
        return ema
    
    def _calculate_rsi(self, data: List[float], period: int = 14) -> List[float]:
        """Calculate Relative Strength Index"""
        if len(data) < period + 1:
            return [None] * len(data)
        
        rsi = [None] * period
        gains = []
        losses = []
        
        for i in range(1, len(data)):
            change = data[i] - data[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        for i in range(period, len(gains)):
            avg_gain = statistics.mean(gains[i-period+1:i+1])
            avg_loss = statistics.mean(losses[i-period+1:i+1])
            
            if avg_loss == 0:
                rsi.append(100)
            else:
                rs = avg_gain / avg_loss
                rsi_value = 100 - (100 / (1 + rs))
                rsi.append(rsi_value)
        
        return rsi
    
    def _calculate_macd(self, data: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, List[float]]:
        """Calculate MACD indicator"""
        if len(data) < slow:
            return {'line': [], 'signal': [], 'histogram': []}
        
        ema_fast = self._calculate_ema(data, fast)
        ema_slow = self._calculate_ema(data, slow)
        
        macd_line = [fast - slow for fast, slow in zip(ema_fast, ema_slow)]
        macd_signal = self._calculate_ema([x for x in macd_line if x is not None], signal)
        macd_histogram = []
        
        # Align arrays and calculate histogram
        signal_offset = len(macd_line) - len(macd_signal)
        for i in range(len(macd_line)):
            if i >= signal_offset:
                histogram_val = macd_line[i] - macd_signal[i - signal_offset]
                macd_histogram.append(histogram_val)
            else:
                macd_histogram.append(0)
        
        return {
            'line': macd_line,
            'signal': macd_signal + [None] * signal_offset,
            'histogram': macd_histogram
        }
    
    def _calculate_bollinger_bands(self, data: List[float], period: int = 20, std_dev: float = 2) -> Dict[str, List[float]]:
        """Calculate Bollinger Bands"""
        if len(data) < period:
            return {'upper': [], 'middle': [], 'lower': []}
        
        upper = []
        middle = self._calculate_sma(data, period)
        lower = []
        
        for i in range(period - 1, len(data)):
            window = data[i-period+1:i+1]
            avg = statistics.mean(window)
            std = statistics.stdev(window)
            
            upper.append(avg + (std_dev * std))
            lower.append(avg - (std_dev * std))
        
        return {
            'upper': [None] * (period - 1) + upper,
            'middle': middle,
            'lower': [None] * (period - 1) + lower
        }
    
    def add_trade(self, trade_data: Dict[str, Any]):
        """Add trade marker to chart"""
        try:
            # Find corresponding candle index
            trade_time = trade_data.get('time', datetime.now())
            
            # Find closest candle
            candle_index = None
            for i, candle in enumerate(self.candles):
                if abs((candle['time'] - trade_time).total_seconds()) < 3600:  # Within 1 hour
                    candle_index = i
                    break
            
            if candle_index is not None:
                trade_data['candleIndex'] = candle_index
                self.trades.append(trade_data)
                
                # Notify subscribers
                chart_data = self.get_chart_data()
                self.notify_subscribers(chart_data)
                
                logger.info(f"Added trade marker: {trade_data.get('type')} at {trade_data.get('price')}")
            
        except Exception as e:
            logger.error(f"Error adding trade: {e}")
    
    def add_level(self, level_data: Dict[str, Any]):
        """Add price level (SL/TP) to chart"""
        try:
            self.levels.append(level_data)
            
            # Keep only last 10 levels
            if len(self.levels) > 10:
                self.levels.pop(0)
            
            # Notify subscribers
            chart_data = self.get_chart_data()
            self.notify_subscribers(chart_data)
            
        except Exception as e:
            logger.error(f"Error adding level: {e}")
    
    def get_chart_data(self) -> Dict[str, Any]:
        """Get current chart data for frontend"""
        return {
            'candles': self.candles[-100:],  # Last 100 candles for display
            'volume': self.volume[-100:],
            'indicators': self.indicators,
            'trades': self.trades,
            'levels': self.levels,
            'priceAction': self.price_action,
            'currentPrice': self.current_price,
            'timeframe': self.timeframe,
            'symbol': self.symbol,
            'timestamp': datetime.now().isoformat()
        }
    
    def set_timeframe(self, timeframe: str):
        """Change chart timeframe and fetch historical candles from MT5"""
        old_timeframe = self.timeframe
        self.timeframe = timeframe
        self.candles.clear()
        self.volume.clear()
        self.trades.clear()
        self.levels.clear()
        
        # Reset indicators
        self.indicators = {
            'ma20': [],
            'ma50': [],
            'ma200': [],
            'rsi': [],
            'macd': {'line': [], 'signal': [], 'histogram': []},
            'bb': {'upper': [], 'middle': [], 'lower': []}
        }
        
        # Fetch candles for new timeframe
        self.fetch_historical_candles()
        
        logger.info(f"Chart timeframe changed from {old_timeframe} to {timeframe}")
    
    def fetch_historical_candles(self, count: int = 100):
        """Fetch historical candles from MT5 for current timeframe"""
        try:
            if not mt5_manager._initialized:
                logger.warning("MT5 not initialized, cannot fetch candles")
                return
            
            tf_const = TF_MAP.get(self.timeframe)
            if not tf_const:
                logger.error(f"Invalid timeframe: {self.timeframe}")
                return
            
            # Get candles from MT5
            rates = mt5_manager.mt5.copy_rates_from_pos(self.symbol, tf_const, 0, count)
            
            if rates is None or len(rates) == 0:
                logger.warning(f"No candles returned for {self.symbol} {self.timeframe}")
                return
            
            # Convert numpy array to list of dicts and store
            for bar in rates:
                candle_data = {
                    'time': datetime.fromtimestamp(int(bar['time'])),
                    'open': float(bar['open']),
                    'high': float(bar['high']),
                    'low': float(bar['low']),
                    'close': float(bar['close']),
                    'volume': int(bar['tick_volume'])
                }
                self.candles.append(candle_data)
            
            # Update current price
            if self.candles:
                self.current_price = self.candles[-1]['close']
            
            # Calculate indicators
            self._update_indicators()
            
            logger.info(f"Fetched {len(self.candles)} candles for {self.symbol} {self.timeframe}")
            
        except Exception as e:
            logger.error(f"Error fetching historical candles: {e}")
    
    def clear_data(self):
        """Clear all chart data"""
        self.candles.clear()
        self.volume.clear()
        self.trades.clear()
        self.levels.clear()
        self.current_price = 0.0
        
        # Reset indicators
        self.indicators = {
            'ma20': [],
            'ma50': [],
            'ma200': [],
            'rsi': [],
            'macd': {'line': [], 'signal': [], 'histogram': []},
            'bb': {'upper': [], 'middle': [], 'lower': []}
        }
        
        logger.info("Chart data cleared")

# Global chart data service instance
chart_data_service = ChartDataService()
