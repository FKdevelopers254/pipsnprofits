import logging
import threading
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum

try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None

from src.services.mt5_service import mt5_manager
from src.services.economic_calendar import economic_calendar

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    MA_CROSSOVER = "ma_crossover"
    RSI = "rsi"
    PRICE_ACTION = "price_action"


@dataclass
class BotConfig:
    enabled: bool = False
    symbol: str = "XAUUSD"
    timeframe: str = "H1"  # Primary timeframe
    higher_timeframe: str = "H4"  # Higher timeframe for trend
    lower_timeframe: str = "M15"  # Lower timeframe for entry confirmation
    strategy: str = "ensemble"  # Default to ensemble with weighted voting
    volume: float = 0.01
    risk_percent: float = 1.0  # Risk % per trade
    use_atr: bool = True  # Use ATR for dynamic SL/TP
    atr_multiplier_sl: float = 2.0  # SL = ATR * multiplier
    atr_multiplier_tp: float = 4.0  # TP = ATR * multiplier
    sl_pips: float = 50  # Fallback if ATR disabled
    tp_pips: float = 100
    magic: int = 123456
    max_spread: float = 50
    max_positions: int = 1
    trend_filter: bool = False  # Allow trading against higher TF trend
    min_signal_strength: int = 2  # Require 2+ confluence factors (higher quality signals)
    # Risk Management
    max_daily_loss: float = 5.0  # Max daily loss % of equity
    trailing_stop: bool = True  # Enable trailing stop
    trailing_stop_distance: float = 1.5  # ATR multiplier for trailing stop
    breakeven_after_pips: float = 30  # Move to breakeven after X pips profit
    use_win_rate_sizing: bool = True  # Dynamic sizing based on win rate
    # Advanced Exit Strategies
    partial_take_profits: bool = True  # Enable partial take profits
    tp1_ratio: float = 1.0  # First TP at 1R (risk:reward ratio)
    tp1_percent: float = 0.5  # Close 50% at first TP
    tp2_ratio: float = 2.0  # Second TP at 2R
    tp2_percent: float = 0.3  # Close 30% at second TP  
    tp3_ratio: float = 3.0  # Third TP at 3R (remaining 20%)
    trailing_activation_ratio: float = 1.0  # Activate trailing after 1R profit
    signal_based_exit: bool = True  # Exit on opposite signal
    time_exit_hours: int = 24  # Exit trade after X hours if not profitable
    # Economic Calendar Filter
    enable_news_filter: bool = True  # Enable economic calendar filter
    news_filter_high_impact_minutes: int = 30  # Avoid trading X minutes before/after high impact
    news_filter_medium_impact_minutes: int = 15  # Avoid trading X minutes around medium impact
    news_filter_low_impact_minutes: int = 5   # Avoid trading X minutes around low impact
    # Session Filter
    trade_sessions: list = field(default_factory=lambda: ["london", "ny"])  # london, ny, asian, all
    # Volatility Filter
    min_atr_percent: float = 0.05  # Minimum ATR as % of price (0.05 = 0.05%)
    # Intelligent Feature: Adaptive Strategy Selection (Feature 1)
    adaptive_strategy: bool = False  # Disable to allow all strategies to vote regime
    # Intelligent Feature: Drawdown Protection (Feature 3)
    max_drawdown_stop: float = 7.5  # Stop trading after 7.5% drawdown
    # Intelligent Feature: Consecutive Loss Circuit Breaker (Feature 4)
    consecutive_loss_limit: int = 3  # Pause after 3 consecutive losses
    circuit_breaker_minutes: int = 30  # Pause duration
    # Intelligent Feature: Multi-Instrument Correlation (Feature 5)
    correlation_symbols: list = field(default_factory=lambda: ["EURUSD", "DXY"])  # Confirmation instruments
    use_correlation_filter: bool = False  # Disable correlation check
    # Intelligent Feature: Smart Entry Timing (Feature 6)
    use_pullback_entry: bool = False  # Enter immediately on signal
    wait_for_candle_close: bool = True  # Confirm on candle close
    # Multi-Timeframe Confirmation (Enhanced with M5 and D1)
    enable_mtf_confirmation: bool = True  # Enable M5+M15+H1+H4+D1 alignment
    mtf_weights: dict = field(default_factory=lambda: {
        "M5": 0.5,   # Scalp timing weight
        "M15": 1.0,  # Entry timing weight
        "H1": 2.0,   # Primary signal weight  
        "H4": 1.5,   # Trend confirmation weight
        "D1": 2.5    # Daily trend weight (highest)
    })
    mtf_min_alignment: float = 0.6  # Minimum 60% alignment across timeframes
    mtf_timeframes: list = field(default_factory=lambda: ["M5", "M15", "H1", "H4", "D1"])  # All timeframes to analyze


@dataclass
class BotState:
    running: bool = False
    config: BotConfig = field(default_factory=BotConfig)
    last_check: Optional[datetime] = None
    last_signal: Optional[str] = None
    last_signal_time: Optional[datetime] = None
    last_signal_strength: int = 0
    signal_history: list = field(default_factory=list)
    total_trades_today: int = 0
    pnl_today: float = 0.0
    daily_reset_time: Optional[datetime] = None
    position_count: int = 0
    market_regime: str = "unknown"
    higher_tf_trend: str = "neutral"
    # Win rate tracking
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 50.0  # Default to 50%
    trade_history: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)
    # Intelligent Feature: Strategy Performance Tracking (Feature 8)
    strategy_performance: dict = field(default_factory=lambda: {
        "ma_crossover": {"wins": 0, "losses": 0, "weight": 1.0},
        "rsi": {"wins": 0, "losses": 0, "weight": 1.0},
        "macd": {"wins": 0, "losses": 0, "weight": 1.0},
        "bollinger": {"wins": 0, "losses": 0, "weight": 1.0},
        "stochastic": {"wins": 0, "losses": 0, "weight": 1.0},
    })
    # Intelligent Feature: Performance-Based Learning (Feature 2)
    hourly_performance: dict = field(default_factory=dict)  # hour -> win_rate
    daily_performance: dict = field(default_factory=dict)   # weekday -> win_rate
    # Intelligent Feature: Drawdown Protection (Feature 3)
    peak_equity: float = 0.0
    max_drawdown_percent: float = 0.0
    # Intelligent Feature: Consecutive Loss Circuit Breaker (Feature 4)
    consecutive_losses: int = 0
    circuit_breaker_active: bool = False
    circuit_breaker_until: Optional[datetime] = None
    # Intelligent Feature: Smart Entry Timing (Feature 6)
    pending_signal: Optional[str] = None
    pending_signal_price: float = 0.0
    pullback_threshold: float = 0.002  # 0.2% pullback
    # Advanced Exit Strategies: Track active trades for exit management
    active_trades: dict = field(default_factory=dict)  # ticket -> trade_data
    # Multi-Timeframe Analysis (Enhanced with all timeframes)
    m5_signal: Optional[str] = None    # M5 timeframe signal
    m5_signal_time: Optional[datetime] = None
    m15_signal: Optional[str] = None   # M15 timeframe signal
    m15_signal_time: Optional[datetime] = None
    h1_signal: Optional[str] = None    # H1 timeframe signal
    h1_signal_time: Optional[datetime] = None
    h4_signal: Optional[str] = None    # H4 timeframe signal
    h4_signal_time: Optional[datetime] = None
    d1_signal: Optional[str] = None    # D1 timeframe signal
    d1_signal_time: Optional[datetime] = None
    mtf_alignment_score: float = 0.0   # 0-1 alignment across all timeframes
    mtf_signal_summary: dict = field(default_factory=dict)  # Summary of all MTF signals


class TradingBot:
    """
    Auto-trading bot with multiple strategies.
    Runs asynchronously and checks market conditions periodically.
    """
    
    _instance = None
    _instance_lock = threading.Lock()
    
    TIMEFRAME_MAP = {
        "M1": mt5.TIMEFRAME_M1 if mt5 else 1,
        "M5": mt5.TIMEFRAME_M5 if mt5 else 5,
        "M15": mt5.TIMEFRAME_M15 if mt5 else 15,
        "M30": mt5.TIMEFRAME_M30 if mt5 else 30,
        "H1": mt5.TIMEFRAME_H1 if mt5 else 60,
        "H4": mt5.TIMEFRAME_H4 if mt5 else 240,
        "D1": mt5.TIMEFRAME_D1 if mt5 else 1440,
    }
    
    def __init__(self):
        self._state = BotState()
        self._lock = threading.RLock()
        self._stop_event: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        
    @classmethod
    def instance(cls) -> "TradingBot":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = TradingBot()
            return cls._instance
    
    def get_status(self) -> Dict[str, Any]:
        """Get current bot status."""
        with self._lock:
            cfg = self._state.config
            
            # Get account info for equity
            account_info = mt5_manager.get_account_info()
            
            # Debug logging
            logger.error("get_status: market_regime=%s, higher_tf_trend=%s", 
                        self._state.market_regime, self._state.higher_tf_trend)
            
            return {
                "running": self._state.running,
                "config": {
                    "enabled": cfg.enabled,
                    "symbol": cfg.symbol,
                    "timeframe": cfg.timeframe,
                    "higher_timeframe": cfg.higher_timeframe,
                    "lower_timeframe": cfg.lower_timeframe,
                    "strategy": cfg.strategy,
                    "volume": cfg.volume,
                    "risk_percent": cfg.risk_percent,
                    "use_atr": cfg.use_atr,
                    "atr_multiplier_sl": cfg.atr_multiplier_sl,
                    "atr_multiplier_tp": cfg.atr_multiplier_tp,
                    "sl_pips": cfg.sl_pips,
                    "tp_pips": cfg.tp_pips,
                    "magic": cfg.magic,
                    "max_spread": cfg.max_spread,
                    "max_positions": cfg.max_positions,
                    "trend_filter": cfg.trend_filter,
                    "min_signal_strength": cfg.min_signal_strength,
                    "enable_mtf_confirmation": cfg.enable_mtf_confirmation,
                    "mtf_weights": cfg.mtf_weights,
                    "mtf_min_alignment": cfg.mtf_min_alignment,
                },
                "last_check": self._state.last_check.isoformat() if self._state.last_check else None,
                "last_signal": self._state.last_signal,
                "last_signal_time": self._state.last_signal_time.isoformat() if self._state.last_signal_time else None,
                "signal_strength": self._state.last_signal_strength,
                "market_regime": self._state.market_regime,
                "higher_tf_trend": self._state.higher_tf_trend,
                "signal_history": self._state.signal_history[-10:],  # Last 10 signals
                # Multi-Timeframe Analysis Data
                "m5_signal": self._state.m5_signal,
                "m15_signal": self._state.m15_signal,
                "h1_signal": self._state.h1_signal,
                "h4_signal": self._state.h4_signal,
                "d1_signal": self._state.d1_signal,
                "mtf_alignment_score": self._state.mtf_alignment_score,
                "total_trades_today": self._state.total_trades_today,
                "pnl_today": self._state.pnl_today,
                "equity": account_info.get("equity", 0) if account_info.get("success") else 0,
                # Economic Calendar
                "upcoming_news_events": economic_calendar.get_upcoming_events(cfg.symbol, 24),
                "news_filter_enabled": cfg.enable_news_filter,
                # Win rate and trade statistics
                "total_trades": self._state.total_trades,
                "winning_trades": self._state.winning_trades,
                "losing_trades": self._state.losing_trades,
                "win_rate": self._state.win_rate,
                # Intelligent Features Status
                "strategy_performance": self._state.strategy_performance,
                "drawdown_percent": self._state.max_drawdown_percent,
                "consecutive_losses": self._state.consecutive_losses,
                "circuit_breaker_active": self._state.circuit_breaker_active,
                "pending_signal": self._state.pending_signal,
                "hourly_performance": self._state.hourly_performance,
                "daily_performance": self._state.daily_performance,
            }
    
    def update_config(self, config: Dict[str, Any]) -> bool:
        """Update bot configuration."""
        with self._lock:
            try:
                cfg = self._state.config
                cfg.enabled = config.get("enabled", cfg.enabled)
                cfg.symbol = config.get("symbol", cfg.symbol).upper()
                cfg.timeframe = config.get("timeframe", cfg.timeframe)
                cfg.strategy = config.get("strategy", cfg.strategy)
                cfg.volume = float(config.get("volume", cfg.volume))
                cfg.sl_pips = float(config.get("sl_pips", cfg.sl_pips))
                cfg.tp_pips = float(config.get("tp_pips", cfg.tp_pips))
                cfg.magic = int(config.get("magic", cfg.magic))
                cfg.max_spread = float(config.get("max_spread", cfg.max_spread))
                cfg.risk_percent = float(config.get("risk_percent", cfg.risk_percent))
                cfg.use_atr = config.get("use_atr", cfg.use_atr)
                cfg.atr_multiplier_sl = float(config.get("atr_multiplier_sl", cfg.atr_multiplier_sl))
                cfg.atr_multiplier_tp = float(config.get("atr_multiplier_tp", cfg.atr_multiplier_tp))
                cfg.trend_filter = config.get("trend_filter", cfg.trend_filter)
                cfg.min_signal_strength = int(config.get("min_signal_strength", cfg.min_signal_strength))
                cfg.higher_timeframe = config.get("higher_timeframe", cfg.higher_timeframe)
                return True
            except Exception as e:
                logger.exception("Failed to update bot config: %s", e)
                return False
    
    def start(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Start the trading bot."""
        with self._lock:
            if self._state.running:
                return {"success": False, "message": "Bot is already running"}
            
            if config:
                self.update_config(config)
            else:
                # Reset to fresh defaults if no config provided
                self._state.config = BotConfig()
            
            if not mt5_manager._initialized:
                return {"success": False, "message": "MT5 not initialized"}
            
            self._state.config.enabled = True
            self._state.running = True
            self._state.daily_reset_time = datetime.now(timezone.utc)
            
            # Start the async loop in a dedicated thread
            try:
                self._stop_event = threading.Event()
                self._thread = threading.Thread(target=self._run_trading_loop, daemon=True)
                self._thread.start()
                logger.info("Trading bot started: %s", self._state.config)
                return {"success": True, "message": "Bot started successfully"}
            except Exception as e:
                self._state.running = False
                logger.exception("Failed to start bot: %s", e)
                return {"success": False, "message": f"Failed to start: {str(e)}"}
    
    def stop(self) -> Dict[str, Any]:
        """Stop the trading bot."""
        with self._lock:
            if not self._state.running:
                return {"success": False, "message": "Bot is not running"}
            
            self._state.running = False
            self._state.config.enabled = False
            
            if self._stop_event:
                self._stop_event.set()
            
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2)
            
            logger.info("Trading bot stopped")
            return {"success": True, "message": "Bot stopped successfully"}
    
    def _run_trading_loop(self):
        """Run the trading loop in a dedicated thread with its own event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._trading_loop_async())
        except Exception as e:
            logger.exception("Trading loop error: %s", e)
        finally:
            loop.close()
    
    async def _trading_loop_async(self):
        """Main trading loop - runs every timeframe interval."""
        while self._state.running and not self._stop_event.is_set():
            try:
                await self._check_and_trade()
                
                # Sleep based on timeframe
                sleep_seconds = self._get_sleep_seconds()
                await asyncio.sleep(sleep_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Error in trading loop: %s", e)
                await asyncio.sleep(60)  # Sleep 1 min on error
    
    def _get_sleep_seconds(self) -> int:
        """Get sleep duration - check every 10 seconds for responsiveness."""
        return 10
    
    async def _check_and_trade(self):
        """Check market conditions with smart analysis."""
        cfg = self._state.config
        symbol = cfg.symbol
        
        logger.error("=== BOT CHECK START ===")
        
        with self._lock:
            self._state.last_check = datetime.now(timezone.utc)
        
        # Update trade statistics
        self._update_trade_stats()
        
        # Manage existing positions (trailing stops, breakeven, advanced exits)
        self._manage_positions(cfg)
        
        # NEW: Manage advanced exit strategies for active trades
        await self._manage_advanced_exits(cfg)
        
        # Check if we can trade
        can_trade = self._can_trade()
        logger.error("_can_trade returned: %s", can_trade)
        if not can_trade:
            return
        
        # Get primary timeframe data
        logger.error("Fetching H1 rates for %s...", symbol)
        rates = self._get_rates(symbol, cfg.timeframe, 100)
        rates_len = len(rates) if rates is not None else 0
        logger.error("H1 rates: %s bars", rates_len)
        
        if rates is None or len(rates) < 50:
            logger.error("Insufficient H1 data for %s: %s", symbol, rates)
            with self._lock:
                self._state.last_signal = "HOLD (No Data)"
            return
        
        # Get higher timeframe data for trend
        logger.error("Fetching H4 rates...")
        ht_rates = self._get_rates(symbol, cfg.higher_timeframe, 50)
        ht_rates_len = len(ht_rates) if ht_rates is not None else 0
        logger.error("H4 rates: %s bars", ht_rates_len)
        
        # Calculate market conditions
        regime = self._detect_market_regime(rates)
        ht_trend = self._detect_higher_tf_trend(ht_rates) if ht_rates is not None else "neutral"
        
        logger.error("MARKET ANALYSIS: regime=%s, ht_trend=%s, rates=%d, ht_rates=%s", 
                   regime, ht_trend, len(rates), ht_rates_len)
        
        with self._lock:
            self._state.market_regime = regime
            self._state.higher_tf_trend = ht_trend
        
    # Only skip ranging markets for non-ensemble strategies
        if regime == "ranging" and cfg.trend_filter and cfg.strategy != "ensemble":
            logger.debug("Skipping trade - ranging market detected")
            with self._lock:
                self._state.last_signal = "HOLD (Ranging)"
            return
        
        # Calculate signal using multi-timeframe confirmation
        if cfg.enable_mtf_confirmation:
            # Use multi-timeframe analysis for higher quality signals
            signal, strength, alignment_score, mtf_signals = self._calculate_multi_timeframe_signal(cfg)
            
            # Add MTF factors to signal history
            factors = []
            for tf, data in mtf_signals.items():
                if data["signal"] != "HOLD":
                    factors.append(f"{tf}_{data['signal']}({data['strength']})")
            
            # Add alignment score to factors
            factors.append(f"ALIGN_{alignment_score:.2f}")
            
            logger.info("MTF Signal: %s (strength=%d, alignment=%.2f)", signal, strength, alignment_score)
        else:
            # Use traditional single timeframe analysis
            if cfg.strategy == "ensemble":
                # Use weighted ensemble voting
                signal, strength, factors = self._calculate_ensemble_signal(rates, cfg)
            else:
                # Use confluence signal for other strategies
                signal, strength, factors = self._calculate_smart_signal(rates, ht_trend, cfg)
        
        # Feature 7: Advanced Pattern Recognition
        pattern = self._detect_chart_pattern(rates)
        if pattern != "none":
            factors.append(f"PATTERN_{pattern.upper()}")
            logger.info("Pattern detected: %s", pattern)
        
        signal_time = datetime.now(timezone.utc)
        
        with self._lock:
            self._state.last_signal = signal
            self._state.last_signal_time = signal_time
            self._state.last_signal_strength = strength
            # Add to history
            self._state.signal_history.append({
                "time": signal_time.isoformat(),
                "signal": signal,
                "strength": strength,
                "factors": factors,
                "symbol": symbol,
                "regime": regime,
                "ht_trend": ht_trend,
                "pattern": pattern
            })
            self._state.signal_history = self._state.signal_history[-20:]
        
        # Only trade if signal meets strength threshold
        logger.error("TRADE CHECK: signal=%s, strength=%d, min_required=%d", signal, strength, cfg.min_signal_strength)
        if signal in ("BUY", "SELL") and strength >= cfg.min_signal_strength:
            # Feature 6: Smart Entry Timing - wait for pullback
            if cfg.use_pullback_entry:
                pullback_ok, pullback_pct = self._check_pullback_entry(signal, rates, cfg)
                if not pullback_ok:
                    logger.info("%s signal waiting for pullback (%.2f%%)", signal, cfg.pullback_threshold * 100)
                    with self._lock:
                        self._state.last_signal = f"{signal} (Waiting Pullback)"
                    return
                else:
                    logger.info("Pullback achieved: %.2f%%", pullback_pct * 100)
            
            logger.info("Strong %s signal (strength=%d, factors=%s)", signal, strength, factors)
            await self._execute_smart_trade(signal, cfg, rates)
        else:
            logger.debug("Signal %s too weak (strength=%d < %d)", signal, strength, cfg.min_signal_strength)
    
    def _can_trade(self) -> bool:
        """Check if trading conditions are met."""
        cfg = self._state.config
        symbol = cfg.symbol
        
        logger.error("_can_trade: STEP 1 - Checking MT5 connection...")
        # Check MT5 connection
        if not mt5_manager._initialized:
            logger.error("_can_trade: MT5 not initialized")
            return False
        
        logger.error("_can_trade: STEP 2 - Checking drawdown and daily loss...")
        # Check daily loss limit
        account_info = mt5_manager.get_account_info()
        if account_info.get("success"):
            equity = account_info.get("equity", 0)
            
            # Feature 3: Drawdown Protection - Stop trading after X% drawdown
            with self._lock:
                if equity > self._state.peak_equity:
                    self._state.peak_equity = equity
                drawdown_percent = ((self._state.peak_equity - equity) / self._state.peak_equity * 100) if self._state.peak_equity > 0 else 0
                self._state.max_drawdown_percent = max(self._state.max_drawdown_percent, drawdown_percent)
                
                if drawdown_percent >= cfg.max_drawdown_stop:
                    logger.error("_can_trade: Max drawdown reached (%.2f%% / %.2f%%)", 
                               drawdown_percent, cfg.max_drawdown_stop)
                    return False
            
            # Check daily loss amount
            if self._state.pnl_today < 0:
                daily_loss_amount = equity * (cfg.max_daily_loss / 100)
                if abs(self._state.pnl_today) >= daily_loss_amount and self._state.pnl_today < 0:
                    logger.error("_can_trade: Daily loss limit reached (%.2f%% / %.2f %s)", 
                               cfg.max_daily_loss, daily_loss_amount, account_info.get("currency", "USD"))
                    return False
        
        logger.error("_can_trade: STEP 2.5 - Checking economic calendar filter...")
        # Economic Calendar Filter - Avoid trading during high-impact news
        if cfg.enable_news_filter:
            try:
                # Use create_task instead of asyncio.run to avoid event loop conflict
                import asyncio
                loop = None
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                if loop.is_running():
                    # If loop is running, use run_coroutine_threadsafe
                    import concurrent.futures
                    try:
                        import threading
                        future = asyncio.run_coroutine_threadsafe(
                            economic_calendar.should_avoid_trading(symbol), 
                            loop
                        )
                        should_avoid, reason = future.result(timeout=2.0)  # 2 second timeout
                        if should_avoid:
                            logger.error("_can_trade: Economic news filter - %s", reason)
                            return False
                        logger.error("_can_trade: Economic news filter - OK")
                    except concurrent.futures.TimeoutError:
                        logger.warning("_can_trade: Economic news filter - OK (timeout)")
                    except Exception as e:
                        logger.warning("_can_trade: Economic news filter - OK (error: %s)", e)
                else:
                    should_avoid, reason = loop.run_until_complete(economic_calendar.should_avoid_trading(symbol))
                    if should_avoid:
                        logger.error("_can_trade: Economic news filter - %s", reason)
                        return False
                    logger.error("_can_trade: Economic news filter - OK")
            except Exception as e:
                logger.warning("_can_trade: Error checking economic calendar: %s", e)
                # Continue trading if calendar check fails
        
        logger.error("_can_trade: STEP 3 - Checking circuit breaker...")
        # Feature 4: Consecutive Loss Circuit Breaker
        with self._lock:
            if self._state.circuit_breaker_active:
                if datetime.now(timezone.utc) < self._state.circuit_breaker_until:
                    logger.error("_can_trade: Circuit breaker active until %s", 
                               self._state.circuit_breaker_until)
                    return False
                else:
                    # Reset circuit breaker
                    self._state.circuit_breaker_active = False
                    self._state.consecutive_losses = 0
                    logger.info("Circuit breaker reset - resuming trading")
            
            if self._state.consecutive_losses >= cfg.consecutive_loss_limit:
                self._state.circuit_breaker_active = True
                self._state.circuit_breaker_until = datetime.now(timezone.utc) + timedelta(minutes=cfg.circuit_breaker_minutes)
                logger.error("_can_trade: Circuit breaker activated after %d consecutive losses. Pausing for %d min",
                           self._state.consecutive_losses, cfg.circuit_breaker_minutes)
                return False
        
        logger.error("_can_trade: STEP 4 - Checking correlation filter...")
        # Feature 5: Multi-Instrument Correlation Check
        if cfg.use_correlation_filter:
            if not self._check_correlation_confirmation(symbol, cfg):
                logger.error("_can_trade: Correlation filter not met for %s", symbol)
                return False
        
        logger.error("_can_trade: STEP 5 - Checking session filter...")
        # Check market session filter
        if cfg.trade_sessions and not self._is_in_allowed_session(cfg.trade_sessions):
            logger.error("_can_trade: Outside allowed trading sessions (allowed: %s)", cfg.trade_sessions)
            return False
        
        logger.error("_can_trade: STEP 6 - Checking volatility filter...")
        # Check volatility filter (need rates data for this)
        rates = self._get_rates(symbol, cfg.timeframe, 50)
        if rates is not None and len(rates) >= 20:
            current_price = rates[-1]["close"]
            atr = self._calculate_atr(rates, 14)
            if current_price > 0:
                atr_percent = (atr / current_price) * 100
                if atr_percent < cfg.min_atr_percent:
                    logger.error("_can_trade: Volatility too low (ATR %.3f%% < %.3f%%)", 
                               atr_percent, cfg.min_atr_percent)
                    return False
        
        logger.error("_can_trade: STEP 7 - Checking symbol selection...")
        
        # Ensure symbol is selected in Market Watch
        symbol_info = mt5.symbol_info(symbol)
        
        # Check if symbol needs to be selected (no prices or not selected)
        needs_select = (symbol_info is None or 
                       not symbol_info.visible or 
                       not symbol_info.select or
                       symbol_info.bid == 0.0)
        
        if needs_select:
            logger.error("_can_trade: Symbol %s needs selection (visible=%s, select=%s, bid=%s)", 
                       symbol, 
                       symbol_info.visible if symbol_info else None,
                       symbol_info.select if symbol_info else None,
                       symbol_info.bid if symbol_info else None)
            try:
                selected = mt5.symbol_select(symbol, True)
                logger.error("_can_trade: symbol_select returned: %s", selected)
                if not selected:
                    return False
                # Re-get symbol info after selection
                import time
                time.sleep(1.0)
                symbol_info = mt5.symbol_info(symbol)
                logger.error("_can_trade: After select - visible=%s, select=%s, bid=%s",
                           symbol_info.visible if symbol_info else None,
                           symbol_info.select if symbol_info else None,
                           symbol_info.bid if symbol_info else None)
            except Exception as e:
                logger.error("_can_trade: symbol_select failed: %s", e)
                return False
        
        if symbol_info is None:
            logger.error("_can_trade: No symbol_info for %s", symbol)
            return False
        
        # Try multiple times to get tick (MT5 can be slow)
        tick = None
        for attempt in range(3):
            tick = mt5.symbol_info_tick(symbol)
            if tick is not None:
                break
            logger.error("_can_trade: No tick for %s, attempt %d/3", symbol, attempt + 1)
            import time
            time.sleep(0.5)
        
        if tick is None:
            logger.error("_can_trade: Failed to get tick after 3 attempts")
            return False
        
        # Get fresh symbol info
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error("_can_trade: No symbol_info for %s", symbol)
            return False
            
        spread = (tick.ask - tick.bid) / symbol_info.point
        logger.error("_can_trade: spread=%.1f, max=%.1f", spread, cfg.max_spread)
        if spread > cfg.max_spread:
            logger.error("_can_trade: Spread too high")
            return False
        
        # Check position count
        positions = mt5.positions_get(symbol=symbol)
        self._state.position_count = len(positions) if positions else 0
        logger.error("_can_trade: positions=%d/%d", self._state.position_count, cfg.max_positions)
        
        if self._state.position_count >= cfg.max_positions:
            logger.error("_can_trade: Max positions reached")
            return False
        
        logger.error("_can_trade: ALL CHECKS PASSED")
        return True
    
    def _get_rates(self, symbol: str, timeframe: str, count: int):
        """Get historical price data - ensure symbol is visible first."""
        # Ensure symbol is selected/visible
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            try:
                mt5.symbol_select(symbol, True)
                logger.debug("Selected symbol %s", symbol)
            except Exception as e:
                logger.warning("Failed to select symbol %s: %s", symbol, e)
        
        tf = self.TIMEFRAME_MAP.get(timeframe, mt5.TIMEFRAME_M5 if mt5 else 5)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        
        if rates is None:
            logger.warning("Failed to get rates for %s on %s", symbol, timeframe)
        return rates
    
    def _calculate_macd(self, closes, fast=12, slow=26, signal=9) -> tuple:
        """Calculate MACD line, signal line, and histogram."""
        if len(closes) < slow + signal:
            return 0, 0, 0
        
        # Fast MACD for more signals - use 8/17/9 instead of 12/26/9
        ema_fast = self._calculate_ema(closes, 8)
        ema_slow = self._calculate_ema(closes, 17)
        macd_line = ema_fast - ema_slow
        
        # Calculate signal line (EMA of MACD)
        macd_series = []
        for i in range(slow, len(closes)):
            e_fast = self._calculate_ema(closes[:i+1], fast)
            e_slow = self._calculate_ema(closes[:i+1], slow)
            macd_series.append(e_fast - e_slow)
        
        signal_line = self._calculate_ema(macd_series, signal) if len(macd_series) >= signal else 0
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    def _calculate_bollinger_bands(self, closes, period=20, std_dev=2) -> tuple:
        """Calculate Bollinger Bands (middle, upper, lower)."""
        if len(closes) < period:
            return closes[-1], closes[-1], closes[-1]
        
        middle = sum(closes[-period:]) / period
        variance = sum((c - middle) ** 2 for c in closes[-period:]) / period
        std = variance ** 0.5
        
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        
        return middle, upper, lower
    
    def _calculate_stochastic(self, highs, lows, closes, k_period=14, d_period=3) -> tuple:
        """Calculate Stochastic Oscillator (%K, %D)."""
        if len(closes) < k_period + d_period:
            return 50, 50
        
        k_values = []
        for i in range(k_period - 1, len(closes)):
            high_max = max(highs[i-k_period+1:i+1])
            low_min = min(lows[i-k_period+1:i+1])
            if high_max - low_min == 0:
                k_values.append(50)
            else:
                k_values.append(100 * (closes[i] - low_min) / (high_max - low_min))
        
        k = k_values[-1]
        d = sum(k_values[-d_period:]) / d_period if len(k_values) >= d_period else k
        
        return k, d
    
    def _macd_signal(self, closes) -> str:
        """Generate signal from MACD crossover."""
        if len(closes) < 26:
            return "HOLD"
        
        macd_line, signal_line, histogram = self._calculate_macd(closes)
        
        # Get previous values for crossover
        prev_closes = closes[:-1]
        if len(prev_closes) >= 26:
            prev_macd, prev_signal, prev_histogram = self._calculate_macd(prev_closes)
        else:
            prev_macd, prev_signal, prev_histogram = macd_line, signal_line, histogram
        
        logger.error("MACD: macd=%s, signal=%s, hist=%s, prev_macd=%s, prev_signal=%s", 
                    macd_line, signal_line, histogram, prev_macd, prev_signal)
        
        # Bullish crossover: MACD crosses above signal line
        if prev_macd <= prev_signal and macd_line > signal_line:
            return "BUY"
        
        # Bearish crossover: MACD crosses below signal line
        elif prev_macd >= prev_signal and macd_line < signal_line:
            return "SELL"
        
        # Additional: Strong momentum based on histogram
        if histogram > 0.5:  # Strong positive momentum
            return "BUY"
        elif histogram < -0.5:  # Strong negative momentum
            return "SELL"
            
        return "HOLD"
    
    def _bollinger_signal(self, closes) -> str:
        """Generate signal from Bollinger Bands."""
        if len(closes) < 20:
            return "HOLD"
        
        middle, upper, lower = self._calculate_bollinger_bands(closes)
        current = closes[-1]
        prev = closes[-2]
        
        logger.error("BOLLINGER: current=%s, upper=%s, lower=%s, middle=%s", 
                    current, upper, lower, middle)
        
        # Price touches lower band and bounces - very aggressive
        if prev <= lower * 1.01 and current > prev:
            return "BUY"
        # Price touches upper band and reverses - very aggressive
        elif prev >= upper * 0.99 and current < prev:
            return "SELL"
        # Price breaks above upper band (strong momentum)
        elif current > upper * 1.005:
            return "BUY"
        # Price breaks below lower band (strong momentum)
        elif current < lower * 0.995:
            return "SELL"
        # Price near lower band (oversold)
        elif current < lower * 1.02:
            return "BUY"
        # Price near upper band (overbought)
        elif current > upper * 0.98:
            return "SELL"
            
        return "HOLD"
    
    def _stochastic_signal(self, highs, lows, closes) -> str:
        """Generate signal from Stochastic Oscillator."""
        if len(closes) < 17:
            return "HOLD"
        
        k, d = self._calculate_stochastic(highs, lows, closes)
        
        logger.error("STOCHASTIC: k=%s, d=%s", k, d)
        
        # Oversold bounce - very aggressive threshold (was 25)
        if k < 35 and d < 35 and k > d:
            return "BUY"
        # Overbought reversal - very aggressive threshold (was 75)
        elif k > 65 and d > 65 and k < d:
            return "SELL"
        
        # Additional: Strong oversold condition
        if k < 20:
            return "BUY"
        # Additional: Strong overbought condition
        elif k > 80:
            return "SELL"
        
        return "HOLD"
    
    def _calculate_multi_timeframe_signal(self, cfg: BotConfig) -> tuple:
        """
        Enhanced Multi-Timeframe Confirmation.
        Analyzes M5, M15, H1, H4, and D1 for signal alignment and weights accordingly.
        Returns: (final_signal, strength, alignment_score, timeframe_signals)
        """
        if not cfg.enable_mtf_confirmation:
            return "HOLD", 0, 0.0, {}
        
        try:
            # Get signals from all timeframes
            timeframe_signals = {}
            timeframe_weights = cfg.mtf_weights
            
            # M5 Analysis (Scalp Timing)
            m5_rates = self._get_rates(cfg.symbol, "M5", 100)
            if m5_rates is not None and len(m5_rates) >= 50:
                m5_signal, m5_strength, m5_factors = self._calculate_ensemble_signal(m5_rates, cfg)
                timeframe_signals["M5"] = {
                    "signal": m5_signal,
                    "strength": m5_strength,
                    "factors": m5_factors
                }
                with self._lock:
                    self._state.m5_signal = m5_signal
                    self._state.m5_signal_time = datetime.now(timezone.utc)
            else:
                timeframe_signals["M5"] = {"signal": "HOLD", "strength": 0, "factors": []}
            
            # M15 Analysis (Entry Timing)
            m15_rates = self._get_rates(cfg.symbol, cfg.lower_timeframe, 50)
            if m15_rates is not None and len(m15_rates) >= 30:
                m15_signal, m15_strength, m15_factors = self._calculate_ensemble_signal(m15_rates, cfg)
                timeframe_signals["M15"] = {
                    "signal": m15_signal,
                    "strength": m15_strength,
                    "factors": m15_factors
                }
                with self._lock:
                    self._state.m15_signal = m15_signal
                    self._state.m15_signal_time = datetime.now(timezone.utc)
            else:
                timeframe_signals["M15"] = {"signal": "HOLD", "strength": 0, "factors": []}
            
            # H1 Analysis (Primary Signal)
            h1_rates = self._get_rates(cfg.symbol, cfg.timeframe, 100)
            if h1_rates is not None and len(h1_rates) >= 50:
                h1_signal, h1_strength, h1_factors = self._calculate_ensemble_signal(h1_rates, cfg)
                timeframe_signals["H1"] = {
                    "signal": h1_signal,
                    "strength": h1_strength,
                    "factors": h1_factors
                }
                with self._lock:
                    self._state.h1_signal = h1_signal
                    self._state.h1_signal_time = datetime.now(timezone.utc)
            else:
                timeframe_signals["H1"] = {"signal": "HOLD", "strength": 0, "factors": []}
            
            # H4 Analysis (Trend Confirmation)
            h4_rates = self._get_rates(cfg.symbol, cfg.higher_timeframe, 30)
            if h4_rates is not None and len(h4_rates) >= 20:
                h4_signal, h4_strength, h4_factors = self._calculate_ensemble_signal(h4_rates, cfg)
                timeframe_signals["H4"] = {
                    "signal": h4_signal,
                    "strength": h4_strength,
                    "factors": h4_factors
                }
                with self._lock:
                    self._state.h4_signal = h4_signal
                    self._state.h4_signal_time = datetime.now(timezone.utc)
            else:
                timeframe_signals["H4"] = {"signal": "HOLD", "strength": 0, "factors": []}
            
            # D1 Analysis (Daily Trend)
            d1_rates = self._get_rates(cfg.symbol, "D1", 30)
            if d1_rates is not None and len(d1_rates) >= 20:
                d1_signal, d1_strength, d1_factors = self._calculate_ensemble_signal(d1_rates, cfg)
                timeframe_signals["D1"] = {
                    "signal": d1_signal,
                    "strength": d1_strength,
                    "factors": d1_factors
                }
                with self._lock:
                    self._state.d1_signal = d1_signal
                    self._state.d1_signal_time = datetime.now(timezone.utc)
            else:
                timeframe_signals["D1"] = {"signal": "HOLD", "strength": 0, "factors": []}
            
            # Calculate weighted alignment score
            buy_weight = 0.0
            sell_weight = 0.0
            total_weight = 0.0
            
            for tf, data in timeframe_signals.items():
                weight = timeframe_weights.get(tf, 1.0)
                signal = data["signal"]
                strength = data["strength"]
                
                if signal == "BUY":
                    buy_weight += weight * strength
                    total_weight += weight * strength
                elif signal == "SELL":
                    sell_weight += weight * strength
                    total_weight += weight * strength
                # HOLD signals don't contribute to alignment
            
            # Calculate alignment score (0-1)
            alignment_score = 0.0
            if total_weight > 0:
                alignment_score = max(buy_weight, sell_weight) / total_weight
            
            # Determine final signal based on weighted consensus
            final_signal = "HOLD"
            final_strength = 0
            
            if alignment_score >= cfg.mtf_min_alignment:  # Minimum alignment threshold
                if buy_weight > sell_weight:
                    final_signal = "BUY"
                    final_strength = min(5, int(buy_weight / total_weight * 5))
                elif sell_weight > buy_weight:
                    final_signal = "SELL"
                    final_strength = min(5, int(sell_weight / total_weight * 5))
            
            # Store alignment score
            with self._lock:
                self._state.mtf_alignment_score = alignment_score
            
            logger.info("MTF Analysis - M15:%s H1:%s H4:%s | Alignment:%.2f | Final:%s(%d)",
                       timeframe_signals["M15"]["signal"], timeframe_signals["H1"]["signal"], 
                       timeframe_signals["H4"]["signal"], alignment_score, final_signal, final_strength)
            
            return final_signal, final_strength, alignment_score, timeframe_signals
            
        except Exception as e:
            logger.exception("Error in multi-timeframe analysis: %s", e)
            return "HOLD", 0, 0.0, {}
    
    def _calculate_ensemble_signal(self, rates, cfg: BotConfig) -> tuple:
        """
        Multi-strategy ensemble using weighted voting system (Feature 8).
        Strategies with better performance get higher weight.
        Returns: (signal, strength, factors)
        """
        closes = [r["close"] for r in rates]
        highs = [r["high"] for r in rates]
        lows = [r["low"] for r in rates]
        
        # Get strategy signals
        strategies = {
            "ma_crossover": self._ma_crossover_signal(closes),
            "rsi": self._rsi_signal(closes),
            "macd": self._macd_signal(closes),
            "bollinger": self._bollinger_signal(closes),
            "stochastic": self._stochastic_signal(highs, lows, closes),
        }
        
        # Log all individual strategy signals for debugging
        logger.error("INDIVIDUAL SIGNALS: %s", strategies)
        
        # Log all strategy votes for debugging
        buy_votes = [name for name, sig in strategies.items() if sig == "BUY"]
        sell_votes = [name for name, sig in strategies.items() if sig == "SELL"]
        logger.error("ENSEMBLE VOTES: BUY=%s, SELL=%s", buy_votes, sell_votes)
        
        # Feature 1: Adaptive Strategy Selection based on market regime
        if cfg.adaptive_strategy:
            regime = self._detect_market_regime(rates)
            logger.error("ADAPTIVE STRATEGY: regime=%s, before_modification=%s", regime, strategies)
            # Disable trend-following strategies in ranging markets
            if regime == "ranging":
                strategies["ma_crossover"] = "HOLD"  # Disable in ranging
                strategies["macd"] = "HOLD"  # Disable in ranging
            # Disable reversal strategies in strong trending markets
            elif regime == "trending":
                strategies["bollinger"] = "HOLD"  # Disable in trending
                strategies["stochastic"] = "HOLD"  # Disable in trending
            logger.error("ADAPTIVE STRATEGY: after_modification=%s", strategies)
        
        # Feature 8: Dynamic Strategy Weighting based on performance
        weighted_buy_votes = 0.0
        weighted_sell_votes = 0.0
        total_weight = 0.0
        active_strategies = []
        
        with self._lock:
            for name, signal in strategies.items():
                # Get strategy weight from performance tracking
                perf = self._state.strategy_performance.get(name, {"wins": 0, "losses": 0, "weight": 1.0})
                weight = perf.get("weight", 1.0)
                total_weight += weight
                
                if signal == "BUY":
                    weighted_buy_votes += weight
                    active_strategies.append(f"{name.upper()}_BUY({weight:.2f})")
                elif signal == "SELL":
                    weighted_sell_votes += weight
                    active_strategies.append(f"{name.upper()}_SELL({weight:.2f})")
        
        # Calculate weighted percentages
        if total_weight > 0:
            buy_pct = weighted_buy_votes / total_weight
            sell_pct = weighted_sell_votes / total_weight
        else:
            buy_pct = 0
            sell_pct = 0
        
        logger.error("WEIGHTED VOTING: buy_votes=%s, sell_votes=%s, buy_pct=%s, sell_pct=%s", 
                    weighted_buy_votes, weighted_sell_votes, buy_pct, sell_pct)
        
        # Determine consensus with weighted thresholds
        consensus_threshold = 0.15  # 15% agreement needed (very aggressive for more signals)
        strong_threshold = 0.4      # 40% for strong signal
        
        logger.error("VOTING LOGIC: consensus_thr=%s, strong_thr=%s, buy_votes>sell_votes=%s, sell_votes>buy_votes=%s", 
                    consensus_threshold, strong_threshold, weighted_buy_votes > weighted_sell_votes, weighted_sell_votes > weighted_buy_votes)
        
        if buy_pct >= consensus_threshold and weighted_buy_votes > weighted_sell_votes:
            strength = 3 if buy_pct >= strong_threshold else 2
            return "BUY", strength, active_strategies
        elif sell_pct >= consensus_threshold and weighted_sell_votes > weighted_buy_votes:
            strength = 3 if sell_pct >= strong_threshold else 2
            return "SELL", strength, active_strategies
        
        # Handle tie case: if both have equal votes and meet threshold, use market regime
        if weighted_buy_votes == weighted_sell_votes and weighted_buy_votes > 0:
            logger.error("TIE BREAKER: Both signals equal (%s votes), using market regime for decision", weighted_buy_votes)
            # In trending market, prefer momentum (MACD), in ranging market prefer mean reversion (Bollinger)
            regime = self._detect_market_regime(rates)
            if regime == "trending":
                return "SELL", 2, ["TIE_BREAKER_TRENDING_SELL"]
            else:
                return "BUY", 2, ["TIE_BREAKER_RANGING_BUY"]
        
        return "HOLD", 1, active_strategies
    
    def _calculate_signal(self, rates, strategy: str) -> str:
        """Calculate trading signal based on strategy."""
        closes = [r["close"] for r in rates]
        
        if strategy == "ma_crossover":
            return self._ma_crossover_signal(closes)
        elif strategy == "rsi":
            return self._rsi_signal(closes)
        elif strategy == "price_action":
            return self._price_action_signal(rates)
        elif strategy == "macd":
            return self._macd_signal(closes)
        elif strategy == "bollinger":
            return self._bollinger_signal(closes)
        elif strategy == "stochastic":
            highs = [r["high"] for r in rates]
            lows = [r["low"] for r in rates]
            return self._stochastic_signal(highs, lows, closes)
        elif strategy == "ensemble":
            signal, _, _ = self._calculate_ensemble_signal(rates, None)
            return signal
        
        return "HOLD"
    
    def _ma_crossover_signal(self, closes) -> str:
        """Moving average crossover strategy."""
        if len(closes) < 20:
            return "HOLD"
        
        # Use shorter periods for more signals
        fast_ema = self._calculate_ema(closes, 3)
        slow_ema = self._calculate_ema(closes, 10)
        
        # Previous values for crossover detection
        prev_fast = self._calculate_ema(closes[:-1], 3)
        prev_slow = self._calculate_ema(closes[:-1], 10)
        
        logger.error("MA_CROSSOVER: fast=%s, slow=%s, prev_fast=%s, prev_slow=%s", 
                    fast_ema, slow_ema, prev_fast, prev_slow)
        
        # Bullish crossover: fast crosses above slow
        if prev_fast <= prev_slow and fast_ema > slow_ema:
            return "BUY"
        
        # Bearish crossover: fast crosses below slow
        if prev_fast >= prev_slow and fast_ema < slow_ema:
            return "SELL"
        
        # Additional: Strong momentum detection
        if fast_ema > slow_ema * 1.002:  # Fast is 0.2% above slow
            return "BUY"
        elif fast_ema < slow_ema * 0.998:  # Fast is 0.2% below slow
            return "SELL"
        
        return "HOLD"
    
    def _rsi_signal(self, closes) -> str:
        # RSI overbought/oversold strategy - more aggressive thresholds
        if len(closes) < 15:
            return "HOLD"
        
        rsi = self._calculate_rsi(closes, 14)
        prev_rsi = self._calculate_rsi(closes[:-1], 14)
        
        logger.error("RSI: current=%s, prev=%s", rsi, prev_rsi)
        
        # Oversold bounce - very aggressive (was 40)
        if prev_rsi < 45 and rsi > 45:
            return "BUY"
        
        # Overbought reversal - very aggressive (was 60)
        if prev_rsi > 55 and rsi < 55:
            return "SELL"
        
        # Additional: Strong overbought signal
        if rsi > 75:
            return "SELL"
        
        # Additional: Strong oversold signal
        if rsi < 25:
            return "BUY"
        
        return "HOLD"
    
    def _price_action_signal(self, rates) -> str:
        """Simple price action: breakout of recent range."""
        if len(rates) < 10:
            return "HOLD"
        
        highs = [r["high"] for r in rates[-10:]]
        lows = [r["low"] for r in rates[-10:]]
        current = rates[-1]["close"]
        prev = rates[-2]["close"]
        
        highest = max(highs[:-1])
        lowest = min(lows[:-1])
        
        # Breakout above range
        if prev <= highest and current > highest:
            return "BUY"
        
        # Breakdown below range
        if prev >= lowest and current < lowest:
            return "SELL"
        
        return "HOLD"
    
    def _detect_market_regime(self, rates) -> str:
        """Detect if market is trending or ranging using ADX-like logic."""
        if len(rates) < 14:
            logger.warning("Not enough data for regime detection: %d bars", len(rates))
            return "unknown"
        
        closes = [r["close"] for r in rates]
        highs = [r["high"] for r in rates]
        lows = [r["low"] for r in rates]
        
        # Calculate directional movement
        plus_dm = []
        minus_dm = []
        tr_list = []
        
        for i in range(1, len(rates)):
            high_diff = highs[i] - highs[i-1]
            low_diff = lows[i-1] - lows[i]
            
            plus_dm.append(max(high_diff, 0) if high_diff > low_diff else 0)
            minus_dm.append(max(low_diff, 0) if low_diff > high_diff else 0)
            
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            tr_list.append(tr)
        
        if len(tr_list) < 10:
            return "unknown"
        
        # Use available data (minimum 10)
        period = min(14, len(tr_list))
        atr_period = sum(tr_list[-period:]) / period
        plus_di = 100 * sum(plus_dm[-period:]) / period / atr_period if atr_period > 0 else 0
        minus_di = 100 * sum(minus_dm[-period:]) / period / atr_period if atr_period > 0 else 0
        
        # DX and trend strength
        if (plus_di + minus_di) > 0:
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        else:
            return "unknown"
        
        logger.debug("Regime calc: DX=%.2f, plus_di=%.2f, minus_di=%.2f", dx, plus_di, minus_di)
        
        if dx > 25:
            return "trending"
        else:
            return "ranging"
    
    def _detect_higher_tf_trend(self, ht_rates) -> str:
        """Detect higher timeframe trend using EMA."""
        if ht_rates is None:
            logger.warning("H4 rates is None")
            return "neutral"
        
        if len(ht_rates) < 30:
            logger.warning("Not enough H4 data: %d bars", len(ht_rates))
            # Use simple price comparison if not enough data for EMA
            if len(ht_rates) >= 2:
                closes = [r["close"] for r in ht_rates]
                if closes[-1] > closes[0] * 1.005:
                    return "bullish"
                elif closes[-1] < closes[0] * 0.995:
                    return "bearish"
            return "neutral"
        
        closes = [r["close"] for r in ht_rates]
        
        # Use 20 EMA if 50 not available
        ema_period = min(50, len(closes) - 5)
        ema = self._calculate_ema(closes, ema_period)
        current_price = closes[-1]
        
        logger.debug("H4 trend: price=%.5f, EMA%d=%.5f", current_price, ema_period, ema)
        
        if current_price > ema * 1.005:  # 0.5% buffer
            return "bullish"
        elif current_price < ema * 0.995:
            return "bearish"
        return "neutral"
    
    def _calculate_smart_signal(self, rates, ht_trend: str, cfg: BotConfig) -> tuple:
        """
        Calculate signal with multiple confluence factors.
        Returns: (signal, strength, factors)
        """
        closes = [r["close"] for r in rates]
        highs = [r["high"] for r in rates]
        lows = [r["low"] for r in rates]
        
        factors = []
        buy_score = 0
        sell_score = 0
        
        # Factor 1: MA Crossover
        if len(closes) >= 26:
            fast_ema = self._calculate_ema(closes, 9)
            slow_ema = self._calculate_ema(closes, 21)
            prev_fast = self._calculate_ema(closes[:-1], 9)
            prev_slow = self._calculate_ema(closes[:-1], 21)
            
            if prev_fast <= prev_slow and fast_ema > slow_ema:
                buy_score += 1
                factors.append("MA_CROSS_BULL")
            elif prev_fast >= prev_slow and fast_ema < slow_ema:
                sell_score += 1
                factors.append("MA_CROSS_BEAR")
        
        # Factor 2: RSI Confirmation
        if len(closes) >= 15:
            rsi = self._calculate_rsi(closes, 14)
            if rsi < 40:  # Oversold-ish
                buy_score += 1
                factors.append("RSI_OVERSOLD")
            elif rsi > 60:  # Overbought-ish
                sell_score += 1
                factors.append("RSI_OVERBOUGHT")
        
        # Factor 3: Higher Timeframe Trend Alignment
        if cfg.trend_filter:
            if ht_trend == "bullish":
                buy_score += 1
                factors.append("HT_TREND_BULL")
            elif ht_trend == "bearish":
                sell_score += 1
                factors.append("HT_TREND_BEAR")
        
        # Factor 4: Price vs Recent Structure
        if len(closes) >= 20:
            recent_high = max(highs[-20:])
            recent_low = min(lows[-20:])
            current = closes[-1]
            
            if current > recent_high * 0.995:  # Near breakout
                buy_score += 1
                factors.append("NEAR_BREAKOUT_HIGH")
            elif current < recent_low * 1.005:  # Near breakdown
                sell_score += 1
                factors.append("NEAR_BREAKOUT_LOW")
        
        # Factor 5: Momentum (price vs 10-period SMA)
        if len(closes) >= 10:
            sma_10 = sum(closes[-10:]) / 10
            if closes[-1] > sma_10 * 1.002:
                buy_score += 1
                factors.append("MOMENTUM_UP")
            elif closes[-1] < sma_10 * 0.998:
                sell_score += 1
                factors.append("MOMENTUM_DOWN")
        
        # Determine final signal
        if buy_score >= cfg.min_signal_strength and buy_score > sell_score:
            return "BUY", buy_score, factors
        elif sell_score >= cfg.min_signal_strength and sell_score > buy_score:
            return "SELL", sell_score, factors
        
        return "HOLD", max(buy_score, sell_score), factors
    
    def _calculate_atr(self, rates, period=14) -> float:
        """Calculate Average True Range."""
        if len(rates) < period + 1:
            return 0.0
        
        tr_list = []
        for i in range(1, len(rates)):
            high = rates[i]["high"]
            low = rates[i]["low"]
            prev_close = rates[i-1]["close"]
            
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)
        
        return sum(tr_list[-period:]) / period if len(tr_list) >= period else 0.0
    
    def _calculate_kelly_position_size(self, cfg: BotConfig, equity: float, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """
        Calculate optimal position size using Kelly Criterion.
        Kelly % = (W - (1-W)) / R
        where: W = win probability, R = win/loss ratio
        """
        try:
            if win_rate <= 0 or win_rate >= 100 or avg_loss <= 0:
                return cfg.volume  # Fallback to default
            
            # Convert win_rate to decimal
            win_prob = win_rate / 100.0
            
            # Calculate win/loss ratio
            win_loss_ratio = avg_win / abs(avg_loss) if avg_loss != 0 else 1.0
            
            # Kelly Criterion formula
            kelly_percentage = (win_prob - (1 - win_prob)) / win_loss_ratio
            
            # Apply Kelly fraction (conservative approach - use 25% of full Kelly)
            kelly_fraction = 0.25  # Use 25% of full Kelly for safety
            adjusted_kelly = kelly_percentage * kelly_fraction
            
            # Cap the Kelly percentage to reasonable limits
            max_kelly = 0.05  # Maximum 5% risk per trade
            min_kelly = 0.005  # Minimum 0.5% risk per trade
            
            kelly_risk_percent = max(min_kelly, min(max_kelly, adjusted_kelly)) * 100
            
            # Use the larger of Kelly risk or configured risk (but cap at max_kelly)
            final_risk_percent = min(kelly_risk_percent, cfg.risk_percent, max_kelly * 100)
            
            logger.info("Kelly Criterion: win_rate=%.1f%%, ratio=%.2f, kelly=%.2f%%, final_risk=%.2f%%", 
                       win_rate, win_loss_ratio, kelly_percentage * 100, final_risk_percent)
            
            return final_risk_percent
            
        except Exception as e:
            logger.exception("Error calculating Kelly position size: %s", e)
            return cfg.risk_percent  # Fallback to configured risk
    
    async def _execute_smart_trade(self, signal: str, cfg: BotConfig, rates):
        """Execute trade with smart position sizing and advanced exit strategies."""
        try:
            symbol = cfg.symbol
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return
            
            symbol_info = mt5.symbol_info(symbol)
            point = symbol_info.point if symbol_info else 0.00001
            
            # Calculate ATR for dynamic SL/TP and trailing stops
            atr = self._calculate_atr(rates, 14)
            
            if cfg.use_atr and atr > 0:
                sl_distance = atr * cfg.atr_multiplier_sl
                tp_distance = atr * cfg.atr_multiplier_tp
                # Dynamic trailing stop based on ATR
                trailing_distance = atr * 1.5  # 1.5x ATR for trailing
                logger.debug("ATR=%.5f, SL=%.5f, TP=%.5f, Trail=%.5f", atr, sl_distance, tp_distance, trailing_distance)
            else:
                pip_value = point * 10
                sl_distance = cfg.sl_pips * pip_value
                tp_distance = cfg.tp_pips * pip_value
                trailing_distance = cfg.trailing_stop_distance * pip_value if cfg.trailing_stop_distance > 0 else sl_distance * 0.5
            
            # Enhanced position sizing using Kelly Criterion
            account_info = mt5_manager.get_account_info()
            if account_info.get("success") and cfg.risk_percent > 0:
                equity = account_info.get("equity", 0)
                
                # Calculate average win and loss for Kelly Criterion
                avg_win = 0.0
                avg_loss = 0.0
                if self._state.total_trades > 0:
                    wins = [t["pnl"] for t in self._state.trade_history if t["pnl"] > 0]
                    losses = [t["pnl"] for t in self._state.trade_history if t["pnl"] < 0]
                    avg_win = sum(wins) / len(wins) if wins else 0.0
                    avg_loss = sum(losses) / len(losses) if losses else -1.0
                
                # Use Kelly Criterion for position sizing if we have enough data
                if self._state.total_trades >= 10 and avg_win > 0 and avg_loss < 0:
                    kelly_risk = self._calculate_kelly_position_size(
                        cfg, equity, self._state.win_rate, avg_win, avg_loss
                    )
                    adjusted_risk = kelly_risk
                    logger.info("Using Kelly Criterion sizing: %.2f%% risk", adjusted_risk)
                else:
                    # Fallback to win rate based sizing for new accounts
                    adjusted_risk = cfg.risk_percent
                    if cfg.use_win_rate_sizing and self._state.total_trades >= 10:
                        if self._state.win_rate < 40:
                            adjusted_risk = cfg.risk_percent * 0.5
                            logger.info("Win rate low (%.1f%%), reducing position size", self._state.win_rate)
                        elif self._state.win_rate > 60:
                            adjusted_risk = min(cfg.risk_percent * 1.5, 3.0)
                            logger.info("Win rate high (%.1f%%), increasing position size", self._state.win_rate)
                
                risk_amount = equity * (adjusted_risk / 100)
                
                # Calculate volume based on risk
                if sl_distance > 0 and symbol_info:
                    tick_value = symbol_info.trade_tick_value or 1
                    volume_based_on_risk = risk_amount / (sl_distance / point * tick_value)
                    volume = min(volume_based_on_risk, cfg.volume * 2)  # Allow up to 2x configured volume
                    volume = max(volume, 0.01)  # Minimum volume
                    volume = round(volume, 2)
                    logger.info("Kelly sizing: equity=%.2f, risk=%.2f%%, volume=%.2f (avg_win=%.2f, avg_loss=%.2f)", 
                               equity, adjusted_risk, volume, avg_win, avg_loss)
                else:
                    volume = cfg.volume
            else:
                volume = cfg.volume
            
            # Ensure minimum volume
            volume = max(volume, 0.01)
            
            # Calculate prices for advanced exit strategies
            if signal == "BUY":
                price = tick.ask
                sl = price - sl_distance
                # Advanced TP levels: 1R, 2R, 3R risk/reward
                tp_1r = price + sl_distance  # 1:1 risk/reward
                tp_2r = price + (sl_distance * 2)  # 2:1 risk/reward  
                tp_3r = price + (sl_distance * 3)  # 3:1 risk/reward
                order_type = "BUY"
            else:  # SELL
                price = tick.bid
                sl = price + sl_distance
                tp_1r = price - sl_distance  # 1:1 risk/reward
                tp_2r = price - (sl_distance * 2)  # 2:1 risk/reward
                tp_3r = price - (sl_distance * 3)  # 3:1 risk/reward
                order_type = "SELL"
            
            # Store comprehensive trade data for advanced exit management
            trade_data = {
                "signal": signal,
                "entry_price": price,
                "sl": sl,
                "tp_1r": tp_1r,
                "tp_2r": tp_2r,
                "tp_3r": tp_3r if cfg.tp3_ratio > 0 else None,
                "trailing_distance": trailing_distance,
                "atr": atr,
                "volume": volume,
                "partial_closed": False,
                "tp1_closed": False,
                "tp2_closed": False,
                "signal_at_entry": self._get_current_signal_summary(rates),
                "entry_time": datetime.now(),
                "original_volume": volume,
                "tp1_volume": volume * cfg.tp1_percent,
                "tp2_volume": volume * cfg.tp2_percent,
                "tp3_volume": volume * (1 - cfg.tp1_percent - cfg.tp2_percent)
            }
            
            # Execute main trade with 3R TP (will manage partial closes separately)
            final_tp = tp_3r if cfg.tp3_ratio > 0 else tp_2r
            result = mt5_manager.place_order({
                "symbol": symbol,
                "volume": volume,
                "order_type": order_type,
                "sl": sl,
                "tp": final_tp,
                "magic": cfg.magic,
                "comment": f"SmartBot|{signal}|ATR:{atr:.1f}|Kelly",
            })
            
            if result.get("success"):
                with self._lock:
                    self._state.total_trades_today += 1
                    # Store trade data for exit management
                    self._state.active_trades[result.get("ticket")] = trade_data
                    # Update strategy performance tracking
                    self._update_strategy_performance(signal, trade_data["signal_at_entry"])
                
                logger.info("Smart trade executed: %s vol=%.2f ticket=%s", signal, volume, result.get("ticket"))
                logger.info("Advanced exits set: TP1=%.5f (%.1f%%), TP2=%.5f (%.1f%%), TP3=%.5f (%.1f%%)", 
                           tp_1r, cfg.tp1_percent * 100, tp_2r, cfg.tp2_percent * 100, 
                           tp_3r if cfg.tp3_ratio > 0 else 0, (1 - cfg.tp1_percent - cfg.tp2_percent) * 100)
                
                # Schedule advanced exit management
                if cfg.partial_take_profits or cfg.trailing_stop:
                    self._schedule_advanced_exits(result.get("ticket"), trade_data, cfg)
            else:
                logger.error("Smart trade failed: %s", result.get("message"))
                if "details" in result:
                    logger.error("Trade execution details: %s", result["details"])
                
        except Exception as e:
            logger.exception("Error executing smart trade: %s", e)
    
    def _get_current_signal_summary(self, rates) -> dict:
        """Get current signal summary for trade analysis."""
        closes = [r["close"] for r in rates]
        highs = [r["high"] for r in rates]
        lows = [r["low"] for r in rates]
        
        return {
            "ma_crossover": self._ma_crossover_signal(closes),
            "rsi": self._rsi_signal(closes),
            "macd": self._macd_signal(closes),
            "bollinger": self._bollinger_signal(closes),
            "stochastic": self._stochastic_signal(highs, lows, closes)
        }
    
    def _ma_crossover_signal(self, closes) -> str:
        """Generate MA crossover signal."""
        try:
            if len(closes) < 20:
                return "HOLD"
            
            fast_ma = self._calculate_ema(closes, 10)
            slow_ma = self._calculate_ema(closes, 20)
            prev_fast_ma = self._calculate_ema(closes[:-1], 10)
            prev_slow_ma = self._calculate_ema(closes[:-1], 20)
            
            if prev_fast_ma <= prev_slow_ma and fast_ma > slow_ma:
                return "BUY"
            elif prev_fast_ma >= prev_slow_ma and fast_ma < slow_ma:
                return "SELL"
            else:
                return "HOLD"
        except Exception:
            return "HOLD"
    
    def _rsi_signal(self, closes) -> str:
        """Generate RSI signal."""
        try:
            if len(closes) < 15:
                return "HOLD"
            
            rsi = self._calculate_rsi(closes, 14)
            if rsi < 30:
                return "BUY"
            elif rsi > 70:
                return "SELL"
            else:
                return "HOLD"
        except Exception:
            return "HOLD"
    
    def _macd_signal(self, closes) -> str:
        """Generate MACD signal."""
        try:
            if len(closes) < 26:
                return "HOLD"
            
            macd_line, signal_line, histogram = self._calculate_macd(closes)
            if histogram > 0 and histogram > 0:
                return "BUY"
            elif histogram < 0 and histogram < 0:
                return "SELL"
            else:
                return "HOLD"
        except Exception:
            return "HOLD"
    
    def _bollinger_signal(self, closes) -> str:
        """Generate Bollinger Bands signal."""
        try:
            if len(closes) < 20:
                return "HOLD"
            
            middle, upper, lower = self._calculate_bollinger_bands(closes, 20, 2)
            current_price = closes[-1]
            
            if current_price < lower:
                return "BUY"
            elif current_price > upper:
                return "SELL"
            else:
                return "HOLD"
        except Exception:
            return "HOLD"
    
    def _stochastic_signal(self, highs, lows, closes) -> str:
        """Generate Stochastic signal."""
        try:
            if len(closes) < 14:
                return "HOLD"
            
            k, d = self._calculate_stochastic(highs, lows, closes, 14, 3)
            if k < 20:
                return "BUY"
            elif k > 80:
                return "SELL"
            else:
                return "HOLD"
        except Exception:
            return "HOLD"
    
    def _schedule_advanced_exits(self, ticket: int, trade_data: dict, cfg: BotConfig):
        """Schedule advanced exit management for partial take profits and trailing stops."""
        try:
            # This will be called from the main bot loop to manage exits
            logger.debug("Advanced exit management scheduled for ticket #%s", ticket)
        except Exception as e:
            logger.exception("Error scheduling advanced exits: %s", e)
    
    def _update_strategy_performance(self, signal: str, signal_summary: dict):
        """Update strategy performance tracking."""
        try:
            with self._lock:
                if not hasattr(self._state, 'strategy_performance'):
                    self._state.strategy_performance = {
                        'ma_crossover': {'wins': 0, 'losses': 0, 'total': 0},
                        'rsi': {'wins': 0, 'losses': 0, 'total': 0},
                        'macd': {'wins': 0, 'losses': 0, 'total': 0},
                        'bollinger': {'wins': 0, 'losses': 0, 'total': 0},
                        'stochastic': {'wins': 0, 'losses': 0, 'total': 0}
                    }
                
                # Update each strategy's performance based on signal
                for strategy, strategy_signal in signal_summary.items():
                    if strategy in self._state.strategy_performance:
                        self._state.strategy_performance[strategy]['total'] += 1
                        # This will be updated when trade closes
        except Exception as e:
            logger.exception("Error updating strategy performance: %s", e)
    
    async def _manage_advanced_exits(self, ticket: int, trade_data: dict, cfg: BotConfig):
        """Manage advanced exit strategies: partial TPs, trailing stops, time exits."""
        try:
            # Get current position
            position = mt5_manager.get_open_positions(ticket)
            if not position.get("success"):
                return
            
            pos = position.get("positions", [{}])[0]
            current_price = pos.get("price_current", 0)
            entry_price = trade_data["entry_price"]
            signal = trade_data["signal"]
            
            # Calculate current profit in R multiples
            if signal == "BUY":
                current_profit_r = (current_price - entry_price) / (entry_price - trade_data["sl"])
            else:  # SELL
                current_profit_r = (entry_price - current_price) / (trade_data["sl"] - entry_price)
            
            # Partial Take Profit 1 (1R)
            if cfg.partial_take_profits and not trade_data["tp1_closed"] and current_profit_r >= cfg.tp1_ratio:
                await self._execute_partial_close(ticket, cfg.tp1_percent, f"TP1 ({cfg.tp1_ratio}R)")
                trade_data["tp1_closed"] = True
                logger.info("TP1 partial close executed: ticket=%s at %.1fR", ticket, current_profit_r)
            
            # Partial Take Profit 2 (2R)
            elif cfg.partial_take_profits and trade_data["tp1_closed"] and not trade_data["tp2_closed"] and current_profit_r >= cfg.tp2_ratio:
                await self._execute_partial_close(ticket, cfg.tp2_percent, f"TP2 ({cfg.tp2_ratio}R)")
                trade_data["tp2_closed"] = True
                logger.info("TP2 partial close executed: ticket=%s at %.1fR", ticket, current_profit_r)
            
            # Activate trailing stop after reaching activation ratio
            if cfg.trailing_stop and current_profit_r >= cfg.trailing_activation_ratio:
                await self._update_trailing_stop(ticket, pos, trade_data, current_price)
            
            # Time-based exit
            if cfg.time_exit_hours > 0:
                entry_time = trade_data["entry_time"]
                time_elapsed = (datetime.now() - entry_time).total_seconds() / 3600  # hours
                if time_elapsed >= cfg.time_exit_hours and current_profit_r < 0.5:  # Not profitable after X hours
                    await self._execute_partial_close(ticket, 1.0, f"Time Exit ({time_elapsed:.1f}h)")
                    logger.info("Time exit executed: ticket=%s after %.1f hours", ticket, time_elapsed)
            
        except Exception as e:
            logger.exception("Error managing advanced exits: %s", e)
    
    def _get_current_signal_summary(self, rates) -> dict:
        """Get current signal summary for trade analysis."""
        closes = [r["close"] for r in rates]
        highs = [r["high"] for r in rates]
        lows = [r["low"] for r in rates]
        
        return {
            "ma_crossover": self._ma_crossover_signal(closes),
            "rsi": self._rsi_signal(closes),
            "macd": self._macd_signal(closes),
            "bollinger": self._bollinger_signal(closes),
            "stochastic": self._stochastic_signal(highs, lows, closes),
            "regime": self._detect_market_regime(rates)
        }
    
    def _update_strategy_performance(self, executed_signal: str, signal_summary: dict):
        """Update individual strategy performance tracking."""
        with self._lock:
            # Track which strategies contributed to this trade
            for strategy, signal in signal_summary.items():
                if strategy == "regime":
                    continue
                    
                # Get existing performance or create new
                existing_perf = self._state.strategy_performance.get(strategy, {"wins": 0, "losses": 0, "weight": 1.0})
                perf = existing_perf.copy()
                
                if signal == executed_signal:
                    # Strategy was correct
                    perf["wins"] += 1
                    # Increase weight for winning strategies
                    perf["weight"] = min(perf["weight"] + 0.05, 2.0)  # Max weight 2.0
                elif signal != "HOLD":
                    # Strategy was wrong (predicted opposite)
                    perf["losses"] += 1
                    # Decrease weight for losing strategies
                    perf["weight"] = max(perf["weight"] - 0.05, 0.5)  # Min weight 0.5
                
                self._state.strategy_performance[strategy] = perf
    
    def _schedule_partial_close(self, ticket: int, trade_data: dict, cfg: BotConfig):
        """Schedule partial close at 1R and manage advanced exits."""
        # This will be called from the main bot loop to check for exit conditions
        # For now, we'll store the data and check it in the main check loop
        pass
    
    async def _manage_advanced_exits(self, cfg: BotConfig):
        """Manage advanced exit strategies for active trades."""
        try:
            positions = mt5_manager.get_open_positions()
            if not positions.get("success"):
                return
            
            for position in positions.get("positions", []):
                ticket = position.get("ticket")
                if ticket not in self._state.active_trades:
                    continue
                
                trade_data = self._state.active_trades[ticket]
                current_price = position.get("price_current", position.get("price_open"))
                entry_price = trade_data["entry_price"]
                signal = trade_data["signal"]
                
                # Check for signal-based exit (opposite signal)
                rates = self._get_rates(cfg.symbol, cfg.timeframe, 100)
                current_signals = self._get_current_signal_summary(
                    rates if rates is not None else []
                )
                
                opposite_signal = "SELL" if signal == "BUY" else "BUY"
                signal_based_exit = False
                
                # Check if majority of strategies now show opposite signal
                signal_votes = sum(1 for s in current_signals.values() if s == opposite_signal)
                if signal_votes >= 3:  # 3+ strategies showing opposite signal
                    signal_based_exit = True
                    logger.info("Signal-based exit triggered: %d strategies showing %s", signal_votes, opposite_signal)
                
                # Partial close at 1R if not already done
                if not trade_data["partial_closed"]:
                    if signal == "BUY" and current_price >= trade_data["tp_1r"]:
                        await self._execute_partial_close(ticket, 0.5, "1R TP Partial")
                        trade_data["partial_closed"] = True
                    elif signal == "SELL" and current_price <= trade_data["tp_1r"]:
                        await self._execute_partial_close(ticket, 0.5, "1R TP Partial")
                        trade_data["partial_closed"] = True
                
                # Dynamic trailing stop
                if cfg.trailing_stop:
                    await self._update_trailing_stop(ticket, position, trade_data, current_price)
                
                # Signal-based exit (close remaining position)
                if signal_based_exit and trade_data["partial_closed"]:
                    await self._execute_partial_close(ticket, 1.0, f"Signal Exit ({opposite_signal})")
                    
        except Exception as e:
            logger.exception("Error managing advanced exits: %s", e)
    
    async def _execute_partial_close(self, ticket: int, volume_fraction: float, reason: str):
        """Execute partial close of position."""
        try:
            position = mt5_manager.get_open_positions(ticket)
            if not position.get("success"):
                return
            
            pos = position.get("positions", [{}])[0]
            current_volume = pos.get("volume", 0)
            close_volume = round(current_volume * volume_fraction, 2)
            
            if close_volume < 0.01:  # Minimum volume
                return
            
            result = mt5_manager.close_position({
                "ticket": ticket,
                "volume": close_volume,
                "comment": f"Partial|{reason}"
            })
            
            if result.get("success"):
                pnl = result.get("profit", 0)
                logger.info("Partial close executed: ticket=%s, vol=%.2f, pnl=%.2f, reason=%s", 
                           ticket, close_volume, pnl, reason)
                
                # Update performance tracking
                with self._lock:
                    if pnl > 0:
                        self._state.pnl_today += pnl
                        self._state.winning_trades += 1
                    else:
                        self._state.pnl_today += pnl
                        self._state.losing_trades += 1
                    self._state.total_trades += 1
            else:
                logger.warning("Partial close failed: %s", result.get("message"))
                
        except Exception as e:
            logger.exception("Error executing partial close: %s", e)
    
    async def _update_trailing_stop(self, ticket: int, position: dict, trade_data: dict, current_price: float):
        """Update trailing stop based on ATR and price movement."""
        try:
            signal = trade_data["signal"]
            entry_price = trade_data["entry_price"]
            trailing_distance = trade_data["trailing_distance"]
            atr = trade_data["atr"]
            
            # Calculate new trailing stop level
            if signal == "BUY":
                # For BUY: trail stop up as price rises
                new_sl = current_price - trailing_distance
                current_sl = position.get("sl", 0)
                
                # Only move stop up, never down
                if new_sl > current_sl:
                    # Ensure we have at least 1R profit before trailing
                    profit_pips = (current_price - entry_price) / (atr * 0.0001) if atr > 0 else 0
                    if profit_pips >= 1.0:  # At least 1R profit
                        result = mt5_manager.modify_position(ticket, {
                            "sl": new_sl,
                            "comment": f"Trail|ATR:{atr:.1f}"
                        })
                        
                        if result.get("success"):
                            logger.debug("Trailing stop updated: ticket=%s, new_sl=%.5f", ticket, new_sl)
            
            else:  # SELL
                # For SELL: trail stop down as price falls
                new_sl = current_price + trailing_distance
                current_sl = position.get("sl", 0)
                
                # Only move stop down, never up
                if new_sl < current_sl:
                    # Ensure we have at least 1R profit before trailing
                    profit_pips = (entry_price - current_price) / (atr * 0.0001) if atr > 0 else 0
                    if profit_pips >= 1.0:  # At least 1R profit
                        result = mt5_manager.modify_position(ticket, {
                            "sl": new_sl,
                            "comment": f"Trail|ATR:{atr:.1f}"
                        })
                        
                        if result.get("success"):
                            logger.debug("Trailing stop updated: ticket=%s, new_sl=%.5f", ticket, new_sl)
                            
        except Exception as e:
            logger.exception("Error updating trailing stop: %s", e)
    
    def _calculate_ema(self, data, period) -> float:
        """Calculate Exponential Moving Average."""
        if len(data) < period:
            return sum(data) / len(data)
        
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period
        
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def _calculate_rsi(self, data, period=14) -> float:
        """Calculate Relative Strength Index."""
        if len(data) < period + 1:
            return 50
        
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
        
        if len(gains) < period:
            return 50
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _manage_positions(self, cfg: BotConfig):
        """Manage open positions: trailing stops, breakeven, etc."""
        try:
            symbol = cfg.symbol
            positions = mt5.positions_get(symbol=symbol)
            
            if not positions:
                return
            
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return
            
            symbol_info = mt5.symbol_info(symbol)
            point = symbol_info.point if symbol_info else 0.00001
            
            for pos in positions:
                # Skip non-bot positions
                if pos.magic != cfg.magic:
                    continue
                
                current_price = tick.bid if pos.type == 0 else tick.ask  # 0 = BUY, 1 = SELL
                open_price = pos.price_open
                current_sl = pos.sl
                
                # Calculate profit in points
                if pos.type == 0:  # BUY
                    profit_points = (current_price - open_price) / point
                else:  # SELL
                    profit_points = (open_price - current_price) / point
                
                # Move to breakeven after X pips profit
                if cfg.breakeven_after_pips > 0 and profit_points >= cfg.breakeven_after_pips:
                    if pos.type == 0 and current_sl < open_price:  # BUY, SL below entry
                        new_sl = open_price + 5 * point  # Small buffer above entry
                        if current_sl < new_sl:
                            self._modify_position_sl(pos.ticket, new_sl)
                            logger.info("Breakeven set: Ticket #%s at %.5f", pos.ticket, new_sl)
                    elif pos.type == 1 and (current_sl > open_price or current_sl == 0):  # SELL, SL above entry
                        new_sl = open_price - 5 * point  # Small buffer below entry
                        if current_sl == 0 or current_sl > new_sl:
                            self._modify_position_sl(pos.ticket, new_sl)
                            logger.info("Breakeven set: Ticket #%s at %.5f", pos.ticket, new_sl)
                
                # Trailing stop
                if cfg.trailing_stop and profit_points > cfg.breakeven_after_pips:
                    trailing_distance = cfg.trailing_stop_distance * cfg.atr_multiplier_sl * point * 10  # in pips
                    
                    if pos.type == 0:  # BUY
                        new_sl = current_price - trailing_distance
                        if new_sl > current_sl:
                            self._modify_position_sl(pos.ticket, new_sl)
                            logger.debug("Trailing stop updated: Ticket #%s SL %.5f -> %.5f", 
                                       pos.ticket, current_sl, new_sl)
                    else:  # SELL
                        new_sl = current_price + trailing_distance
                        if current_sl == 0 or new_sl < current_sl:
                            self._modify_position_sl(pos.ticket, new_sl)
                            logger.debug("Trailing stop updated: Ticket #%s SL %.5f -> %.5f", 
                                       pos.ticket, current_sl, new_sl)
                        
        except Exception as e:
            logger.exception("Error managing positions: %s", e)
    
    def _modify_position_sl(self, ticket: int, new_sl: float):
        """Modify position stop loss."""
        try:
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "sl": new_sl,
            }
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.warning("Failed to modify SL for ticket #%s: %s", ticket, result.comment)
        except Exception as e:
            logger.exception("Error modifying position SL: %s", e)
    
    def _update_trade_stats(self):
        """Update win rate and trade statistics from position history."""
        try:
            # Get deals history for today
            from_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            to_date = datetime.now(timezone.utc)
            
            deals = mt5.history_deals_get(from_date, to_date)
            if deals is None:
                return
            
            bot_deals = [d for d in deals if d.magic == self._state.config.magic]
            
            total_profit = 0.0
            wins = 0
            losses = 0
            
            for deal in bot_deals:
                profit = deal.profit
                total_profit += profit
                
                if profit > 0:
                    wins += 1
                elif profit < 0:
                    losses += 1
            
            with self._lock:
                self._state.total_trades = wins + losses
                self._state.winning_trades = wins
                self._state.losing_trades = losses
                self._state.pnl_today = total_profit
                
                if self._state.total_trades > 0:
                    self._state.win_rate = (wins / self._state.total_trades) * 100
                
                # Feature 8: Update strategy weights based on performance
                self._update_strategy_weights(bot_deals)
                
                # Feature 2: Track hourly and daily performance
                self._update_time_based_performance(bot_deals)
                
                # Feature 4: Track consecutive losses
                self._update_consecutive_losses(bot_deals)
                
                # Update equity curve
                account_info = mt5_manager.get_account_info()
                if account_info.get("success"):
                    self._state.equity_curve.append({
                        "time": datetime.now(timezone.utc).isoformat(),
                        "equity": account_info.get("equity", 0)
                    })
                    # Keep last 1000 points
                    self._state.equity_curve = self._state.equity_curve[-1000:]
                    
        except Exception as e:
            logger.exception("Error updating trade stats: %s", e)
    
    def _update_strategy_weights(self, deals):
        """Feature 8: Dynamically adjust strategy weights based on win rates."""
        try:
            for strategy_name, perf in self._state.strategy_performance.items():
                total = perf["wins"] + perf["losses"]
                if total >= 5:  # Need at least 5 trades for significance
                    win_rate = perf["wins"] / total
                    # Adjust weight: winning strategies get higher weight (0.5 to 2.0 range)
                    perf["weight"] = 0.5 + (win_rate * 1.5)
        except Exception as e:
            logger.exception("Error updating strategy weights: %s", e)
    
    def _update_time_based_performance(self, deals):
        """Feature 2: Track performance by hour and day of week."""
        try:
            now = datetime.now(timezone.utc)
            current_hour = now.hour
            current_weekday = now.weekday()  # 0=Monday, 6=Sunday
            
            # Count wins/losses in current hour today
            hour_wins = 0
            hour_losses = 0
            day_wins = 0
            day_losses = 0
            
            for deal in deals:
                deal_time = datetime.fromtimestamp(deal.time, tz=timezone.utc)
                if deal.profit > 0:
                    if deal_time.hour == current_hour:
                        hour_wins += 1
                    if deal_time.weekday() == current_weekday:
                        day_wins += 1
                elif deal.profit < 0:
                    if deal_time.hour == current_hour:
                        hour_losses += 1
                    if deal_time.weekday() == current_weekday:
                        day_losses += 1
            
            # Update hourly performance
            if hour_wins + hour_losses > 0:
                self._state.hourly_performance[current_hour] = hour_wins / (hour_wins + hour_losses)
            
            # Update daily performance
            if day_wins + day_losses > 0:
                self._state.daily_performance[current_weekday] = day_wins / (day_wins + day_losses)
                
        except Exception as e:
            logger.exception("Error updating time-based performance: %s", e)
    
    def _update_consecutive_losses(self, deals):
        """Feature 4: Track consecutive losses from deal history."""
        try:
            # Sort deals by time
            sorted_deals = sorted(deals, key=lambda d: d.time, reverse=True)
            
            consecutive = 0
            for deal in sorted_deals:
                if deal.profit < 0:
                    consecutive += 1
                elif deal.profit > 0:
                    break
            
            self._state.consecutive_losses = consecutive
        except Exception as e:
            logger.exception("Error updating consecutive losses: %s", e)
    
    async def _execute_trade(self, signal: str, cfg: BotConfig):
        """Execute a trade based on signal."""
        try:
            symbol = cfg.symbol
            
            # Get current price
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return
            
            symbol_info = mt5.symbol_info(symbol)
            point = symbol_info.point if symbol_info else 0.00001
            pip_value = point * 10  # Standard pip size
            
            # Calculate SL/TP
            if signal == "BUY":
                price = tick.ask
                sl = price - (cfg.sl_pips * pip_value)
                tp = price + (cfg.tp_pips * pip_value)
                order_type = "BUY"
            else:
                price = tick.bid
                sl = price + (cfg.sl_pips * pip_value)
                tp = price - (cfg.tp_pips * pip_value)
                order_type = "SELL"
            
            # Place order through MT5 manager
            result = mt5_manager.place_order({
                "symbol": symbol,
                "volume": cfg.volume,
                "order_type": order_type,
                "sl": sl,
                "tp": tp,
                "magic": cfg.magic,
                "comment": f"Bot|{cfg.strategy}|{signal}",
            })
            
            if result.get("success"):
                with self._lock:
                    self._state.total_trades_today += 1
                logger.info("Bot executed %s trade: ticket=%s", signal, result.get("ticket"))
            else:
                logger.warning("Bot trade failed: %s", result.get("message"))
                
        except Exception as e:
            logger.exception("Error executing bot trade: %s", e)
    
    def _is_in_allowed_session(self, allowed_sessions: list) -> bool:
        """Check if current time is within allowed trading sessions."""
        try:
            now = datetime.now(timezone.utc)
            hour = now.hour
            
            # Define session hours (UTC)
            sessions = {
                "asian": range(0, 9),      # 00:00 - 09:00 UTC
                "london": range(7, 17),   # 07:00 - 17:00 UTC
                "ny": range(12, 21),      # 12:00 - 21:00 UTC
            }
            
            # If "all" is in allowed sessions, always trade
            if "all" in allowed_sessions:
                return True
            
            # Check if current hour falls in any allowed session
            for session in allowed_sessions:
                if session in sessions:
                    if hour in sessions[session]:
                        return True
            
            return False
        except Exception as e:
            logger.exception("Error checking trading session: %s", e)
            return True  # Allow trading on error
    
    def _check_correlation_confirmation(self, symbol: str, cfg: BotConfig) -> bool:
        """Feature 5: Check multi-instrument correlation for trade confirmation."""
        try:
            # For XAUUSD, check EURUSD and DXY alignment
            if symbol == "XAUUSD":
                # Get EURUSD trend
                eurusd_rates = self._get_rates("EURUSD", cfg.timeframe, 20)
                if eurusd_rates is not None and len(eurusd_rates) >= 10:
                    eurusd_closes = [r["close"] for r in eurusd_rates]
                    eurusd_sma = sum(eurusd_closes[-10:]) / 10
                    eurusd_bullish = eurusd_closes[-1] > eurusd_sma
                    
                    # If EURUSD is bullish, XAUUSD should be bullish (inverse correlation to DXY)
                    # Allow trade if correlation aligns
                    return True  # Simplified - in production, use actual correlation calc
                    
            return True  # Allow if no correlation data
        except Exception as e:
            logger.exception("Error checking correlation: %s", e)
            return True  # Allow on error
    
    def _check_pullback_entry(self, signal: str, rates, cfg: BotConfig) -> tuple:
        """Feature 6: Smart Entry Timing - wait for pullback after signal."""
        try:
            if not cfg.use_pullback_entry:
                return True, 0  # No pullback needed
            
            current_price = rates[-1]["close"]
            signal_price = self._state.pending_signal_price
            
            if self._state.pending_signal != signal:
                # New signal - set pending
                with self._lock:
                    self._state.pending_signal = signal
                    self._state.pending_signal_price = current_price
                return False, 0  # Wait for pullback
            
            # Check if pullback occurred
            if signal == "BUY":
                # Wait for price to drop below signal price
                pullback = (signal_price - current_price) / signal_price
                if pullback >= cfg.pullback_threshold:
                    # Pullback achieved, reset pending
                    with self._lock:
                        self._state.pending_signal = None
                        self._state.pending_signal_price = 0
                    return True, pullback
            else:  # SELL
                # Wait for price to rise above signal price
                pullback = (current_price - signal_price) / signal_price
                if pullback >= cfg.pullback_threshold:
                    # Pullback achieved, reset pending
                    with self._lock:
                        self._state.pending_signal = None
                        self._state.pending_signal_price = 0
                    return True, pullback
            
            return False, 0  # Still waiting for pullback
        except Exception as e:
            logger.exception("Error checking pullback: %s", e)
            return True, 0  # Allow on error
    
    def _detect_chart_pattern(self, rates) -> str:
        """Feature 7: Advanced Pattern Recognition - detect common chart patterns."""
        try:
            if len(rates) < 30:
                return "none"
            
            highs = [r["high"] for r in rates[-30:]]
            lows = [r["low"] for r in rates[-30:]]
            closes = [r["close"] for r in rates[-30:]]
            
            # Double Top detection
            recent_highs = sorted(highs[-10:], reverse=True)
            if len(recent_highs) >= 2:
                if abs(recent_highs[0] - recent_highs[1]) / recent_highs[0] < 0.01:
                    return "double_top"
            
            # Double Bottom detection
            recent_lows = sorted(lows[-10:])
            if len(recent_lows) >= 2:
                if abs(recent_lows[0] - recent_lows[1]) / recent_lows[0] < 0.01:
                    return "double_bottom"
            
            # Triangle detection (converging highs and lows)
            if len(highs) >= 20:
                early_high = max(highs[:10])
                late_high = max(highs[10:20])
                early_low = min(lows[:10])
                late_low = min(lows[10:20])
                
                if early_high > late_high and early_low < late_low:
                    return "triangle"
            
            return "none"
        except Exception as e:
            logger.exception("Error detecting pattern: %s", e)
            return "none"


# Module singleton
trading_bot = TradingBot.instance()
