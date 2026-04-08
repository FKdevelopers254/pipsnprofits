"""
Backtesting Engine for Historical Strategy Validation
Provides comprehensive backtesting capabilities for trading strategies
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import logging
from pathlib import Path
import MetaTrader5 as mt5

# Try relative import, fallback to absolute for standalone execution
try:
    from ..services.mt5_service import MT5Manager
except ImportError:
    MT5Manager = None

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for backtesting parameters"""
    start_date: datetime
    end_date: datetime
    initial_balance: float = 10000.0
    commission_per_lot: float = 7.0  # Commission per standard lot
    spread_points: float = 17.0  # Average spread in points
    slippage_points: float = 2.0  # Slippage in points
    leverage: int = 100
    margin_call_level: float = 50.0  # Margin call at 50%
    stop_out_level: float = 20.0  # Stop out at 20%
    # Enhanced strategy parameters
    use_kelly_criterion: bool = True
    kelly_fraction: float = 0.25  # 25% of full Kelly
    enable_mtf_confirmation: bool = True
    mtf_timeframes: List[str] = None
    mtf_weights: Dict[str, float] = None
    enable_advanced_exits: bool = True
    partial_take_profits: bool = True
    tp1_percent: float = 0.5
    tp2_percent: float = 0.3
    tp3_percent: float = 0.2
    enable_news_filter: bool = False  # Disabled for backtesting
    risk_percent: float = 1.0
    max_positions: int = 1
    
    def __post_init__(self):
        if self.mtf_timeframes is None:
            self.mtf_timeframes = ['M5', 'M15', 'H1', 'H4', 'D1']
        if self.mtf_weights is None:
            self.mtf_weights = {'M5': 0.5, 'M15': 1.0, 'H1': 2.0, 'H4': 1.5, 'D1': 2.5}


@dataclass
class Trade:
    """Represents a single trade in backtest"""
    ticket: int
    symbol: str
    type: str  # BUY or SELL
    volume: float
    open_time: datetime
    open_price: float
    close_time: Optional[datetime] = None
    close_price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    commission: float = 0.0
    swap: float = 0.0
    profit: float = 0.0
    closed: bool = False
    close_reason: str = ""  # SL, TP, SIGNAL, END


@dataclass
class BacktestResult:
    """Results of backtesting run"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    net_profit: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    max_drawdown: float
    max_drawdown_percent: float
    sharpe_ratio: float
    avg_trade: float
    largest_win: float
    largest_loss: float
    avg_win: float
    avg_loss: float
    recovery_factor: float
    trades: List[Trade]
    equity_curve: List[Tuple[datetime, float]]
    monthly_returns: Dict[str, float]


class BacktestingEngine:
    """Main backtesting engine class"""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.trades: List[Trade] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.current_balance = config.initial_balance
        self.current_equity = config.initial_balance
        self.ticket_counter = 1
        
    def load_historical_data(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Load historical data from MT5"""
        logger.info(f"Loading historical data for {symbol} {timeframe}")
        
        try:
            # Initialize MT5 if not already done
            if not mt5.initialize():
                logger.error("MT5 initialize failed")
                return self._generate_sample_data(symbol, timeframe)
            
            # Convert timeframe string to MT5 constant
            tf_map = {
                'M1': mt5.TIMEFRAME_M1,
                'M5': mt5.TIMEFRAME_M5,
                'M15': mt5.TIMEFRAME_M15,
                'M30': mt5.TIMEFRAME_M30,
                'H1': mt5.TIMEFRAME_H1,
                'H4': mt5.TIMEFRAME_H4,
                'D1': mt5.TIMEFRAME_D1
            }
            
            mt5_tf = tf_map.get(timeframe, mt5.TIMEFRAME_H1)
            
            # Get date range for MT5
            utc_from = self.config.start_date
            utc_to = self.config.end_date
            
            # Request historical data
            rates = mt5.copy_rates_range(symbol, mt5_tf, utc_from, utc_to)
            
            if rates is None or len(rates) == 0:
                logger.error(f"No data retrieved for {symbol} {timeframe}")
                return self._generate_sample_data(symbol, timeframe)
            
            # Convert to DataFrame
            data = pd.DataFrame(rates)
            data['time'] = pd.to_datetime(data['time'], unit='s')
            
            logger.info(f"Loaded {len(data)} bars for {symbol} {timeframe}")
            return data
            
        except Exception as e:
            logger.error(f"Error loading MT5 data: {e}")
            return self._generate_sample_data(symbol, timeframe)
        finally:
            mt5.shutdown()
    
    def _generate_sample_data(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Generate sample data as fallback"""
        logger.info(f"Generating sample data for {symbol} {timeframe}")
        
        # Calculate number of data points
        date_range = pd.date_range(self.config.start_date, self.config.end_date, freq='h')
        n_points = len(date_range)
        
        # Generate more realistic price data
        base_price = 4570.0  # Gold base price
        price_changes = np.random.normal(0, 10, n_points).cumsum()
        prices = base_price + price_changes
        
        # Generate OHLC from close prices
        data = pd.DataFrame({
            'time': date_range,
            'open': prices + np.random.normal(0, 2, n_points),
            'high': prices + np.abs(np.random.normal(5, 3, n_points)),
            'low': prices - np.abs(np.random.normal(5, 3, n_points)),
            'close': prices,
            'volume': np.random.randint(100, 1000, n_points),
            'spread': np.random.normal(self.config.spread_points, 5, n_points)
        })
        
        # Ensure OHLC relationships
        data['high'] = np.maximum(data['high'], np.maximum(data['open'], data['close']))
        data['low'] = np.minimum(data['low'], np.minimum(data['open'], data['close']))
        
        return data
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators for strategy"""
        # Moving Averages
        data['ma_fast'] = data['close'].rolling(window=10).mean()
        data['ma_slow'] = data['close'].rolling(window=20).mean()
        
        # RSI
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        data['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        exp1 = data['close'].ewm(span=12).mean()
        exp2 = data['close'].ewm(span=26).mean()
        data['macd'] = exp1 - exp2
        data['macd_signal'] = data['macd'].ewm(span=9).mean()
        data['macd_hist'] = data['macd'] - data['macd_signal']
        
        # Bollinger Bands
        data['bb_middle'] = data['close'].rolling(window=20).mean()
        bb_std = data['close'].rolling(window=20).std()
        data['bb_upper'] = data['bb_middle'] + (bb_std * 2)
        data['bb_lower'] = data['bb_middle'] - (bb_std * 2)
        
        # Stochastic
        low_min = data['low'].rolling(window=14).min()
        high_max = data['high'].rolling(window=14).max()
        data['stoch_k'] = 100 * (data['close'] - low_min) / (high_max - low_min)
        data['stoch_d'] = data['stoch_k'].rolling(window=3).mean()
        
        # ATR
        high_low = data['high'] - data['low']
        high_close = np.abs(data['high'] - data['close'].shift())
        low_close = np.abs(data['low'] - data['close'].shift())
        true_range = np.maximum(high_low, np.maximum(high_close, low_close))
        data['atr'] = true_range.rolling(window=14).mean()
        
        return data
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate trading signals based on strategy"""
        signals = pd.DataFrame(index=data.index)
        
        # MA Crossover
        signals['ma_signal'] = 0
        signals.loc[data['ma_fast'] > data['ma_slow'], 'ma_signal'] = 1
        signals.loc[data['ma_fast'] < data['ma_slow'], 'ma_signal'] = -1
        
        # RSI
        signals['rsi_signal'] = 0
        signals.loc[data['rsi'] < 30, 'rsi_signal'] = 1  # Oversold
        signals.loc[data['rsi'] > 70, 'rsi_signal'] = -1  # Overbought
        
        # MACD
        signals['macd_signal'] = 0
        signals.loc[(data['macd'] > data['macd_signal']) & 
                   (data['macd_hist'] > 0), 'macd_signal'] = 1
        signals.loc[(data['macd'] < data['macd_signal']) & 
                   (data['macd_hist'] < 0), 'macd_signal'] = -1
        
        # Bollinger Bands
        signals['bb_signal'] = 0
        signals.loc[data['close'] < data['bb_lower'], 'bb_signal'] = 1
        signals.loc[data['close'] > data['bb_upper'], 'bb_signal'] = -1
        
        # Stochastic
        signals['stoch_signal'] = 0
        signals.loc[data['stoch_k'] < 20, 'stoch_signal'] = 1
        signals.loc[data['stoch_k'] > 80, 'stoch_signal'] = -1
        
        # Ensemble signal (majority vote)
        signal_columns = ['ma_signal', 'rsi_signal', 'macd_signal', 'bb_signal', 'stoch_signal']
        signals['ensemble_signal'] = signals[signal_columns].sum(axis=1)
        
        return signals
    
    def calculate_kelly_position_size(self, equity: float, win_rate: float, 
                                   avg_win: float, avg_loss: float) -> float:
        """Calculate optimal position size using Kelly Criterion"""
        if not self.config.use_kelly_criterion or win_rate <= 0 or avg_loss >= 0:
            return 0.01  # Default position size
        
        # Calculate win/loss ratio
        win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 1.0
        
        # Kelly formula: f = (p * b - q) / b
        # where p = win probability, q = loss probability, b = win/loss ratio
        kelly_fraction = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        
        # Apply safety fraction (typically 25-50% of full Kelly)
        kelly_fraction *= self.config.kelly_fraction
        
        # Cap position size to reasonable limits
        kelly_fraction = max(0.01, min(kelly_fraction, 0.05))  # 1% to 5% max
        
        # Calculate position size based on risk amount
        risk_amount = equity * self.config.risk_percent / 100
        position_size = risk_amount / 1000  # Simplified calculation
        
        # Apply Kelly adjustment
        position_size *= kelly_fraction * 10  # Scale factor
        
        return max(0.01, min(position_size, 1.0))  # Min 0.01, max 1.0 lots
    
    def calculate_mtf_signals(self, symbol: str, current_time: datetime) -> Dict[str, str]:
        """Calculate multi-timeframe signals"""
        if not self.config.enable_mtf_confirmation:
            return {}
        
        mtf_signals = {}
        
        for tf in self.config.mtf_timeframes:
            try:
                # Load data for this timeframe
                tf_data = self.load_historical_data(symbol, tf)
                tf_data = self.calculate_indicators(tf_data)
                tf_signals = self.generate_signals(tf_data)
                
                if not tf_signals.empty:
                    current_signal = tf_signals.iloc[-1]['ensemble_signal']
                    if current_signal >= 2:
                        mtf_signals[tf] = 'BUY'
                    elif current_signal <= -2:
                        mtf_signals[tf] = 'SELL'
                    else:
                        mtf_signals[tf] = 'HOLD'
                else:
                    mtf_signals[tf] = 'HOLD'
                    
            except Exception as e:
                logger.warning(f"Error calculating {tf} signal: {e}")
                mtf_signals[tf] = 'HOLD'
        
        return mtf_signals
    
    def calculate_mtf_alignment_score(self, mtf_signals: Dict[str, str]) -> float:
        """Calculate weighted MTF alignment score"""
        if not mtf_signals:
            return 0.0
        
        buy_score = 0.0
        sell_score = 0.0
        
        for tf, signal in mtf_signals.items():
            weight = self.config.mtf_weights.get(tf, 1.0)
            
            if signal == 'BUY':
                buy_score += weight
            elif signal == 'SELL':
                sell_score += weight
        
        total_score = buy_score + sell_score
        if total_score == 0:
            return 0.0
        
        # Return alignment score (0-1)
        return max(buy_score, sell_score) / total_score
    
    def open_trade(self, signal: str, price: float, time: datetime, 
                   sl: Optional[float] = None, tp: Optional[float] = None,
                   signal_strength: int = 1, mtf_signals: Dict[str, str] = None) -> Optional[Trade]:
        """Open a new trade with enhanced position sizing"""
        
        # Calculate position size using Kelly Criterion
        closed_trades = [t for t in self.trades if t.closed]
        if closed_trades:
            win_rate = len([t for t in closed_trades if t.profit > 0]) / len(closed_trades)
            avg_win = np.mean([t.profit for t in closed_trades if t.profit > 0])
            avg_loss = np.mean([t.profit for t in closed_trades if t.profit < 0])
        else:
            win_rate = 0.5  # Default assumption
            avg_win = 100.0
            avg_loss = -50.0
        
        volume = self.calculate_kelly_position_size(self.current_equity, win_rate, avg_win, avg_loss)
        
        if volume <= 0:
            return None
        
        # Calculate commission
        commission = volume * self.config.commission_per_lot
        
        # Create trade with enhanced metadata
        trade = Trade(
            ticket=self.ticket_counter,
            symbol="XAUUSD",
            type=signal,
            volume=volume,
            open_time=time,
            open_price=price,
            sl=sl,
            tp=tp,
            commission=commission
        )
        
        # Store additional data for advanced exits
        if self.config.enable_advanced_exits:
            trade.mtf_signals = mtf_signals or {}
            trade.signal_strength = signal_strength
            trade.original_volume = volume
            trade.tp1_closed = False
            trade.tp2_closed = False
            trade.tp3_closed = False
        
        self.trades.append(trade)
        self.ticket_counter += 1
        
        # Update balance (deduct commission)
        self.current_balance -= commission
        
        logger.info(f"Trade {trade.ticket} opened: {signal} {volume:.2f} @ {price:.2f}")
        return trade
    
    def close_trade(self, trade: Trade, close_price: float, 
                   close_time: datetime, close_reason: str) -> None:
        """Close an existing trade"""
        if trade.closed:
            return
        
        trade.close_price = close_price
        trade.close_time = close_time
        trade.close_reason = close_reason
        
        # Calculate profit
        if trade.type == "BUY":
            profit = (close_price - trade.open_price) * trade.volume * 100
        else:
            profit = (trade.open_price - close_price) * trade.volume * 100
        
        trade.profit = profit
        
        # Update balance
        self.current_balance += profit
        trade.closed = True
        
        logger.info(f"Trade {trade.ticket} closed: {profit:.2f} ({close_reason})")
    
    def update_trades(self, current_time: datetime, current_price: float,
                     data_slice: pd.DataFrame, symbol: str) -> None:
        """Update open trades and check for exit conditions"""
        for trade in self.trades:
            if trade.closed:
                continue
            
            # Check SL/TP
            if trade.type == "BUY":
                if trade.sl and current_price <= trade.sl:
                    self.close_trade(trade, trade.sl, current_time, "SL")
                    continue
                elif trade.tp and current_price >= trade.tp:
                    self.close_trade(trade, trade.tp, current_time, "TP")
                    continue
            else:  # SELL
                if trade.sl and current_price >= trade.sl:
                    self.close_trade(trade, trade.sl, current_time, "SL")
                    continue
                elif trade.tp and current_price <= trade.tp:
                    self.close_trade(trade, trade.tp, current_time, "TP")
                    continue
            
            # Advanced exit management
            if self.config.enable_advanced_exits and hasattr(trade, 'original_volume'):
                self._manage_advanced_exits(trade, current_price, current_time)
            
            # Check signal-based exit
            if not trade.closed and len(data_slice) > 1:
                # Get current signals
                signals = self.generate_signals(data_slice)
                current_signal = signals.iloc[-1]['ensemble_signal']
                
                opposite_signal = -1 if trade.type == "BUY" else 1
                if current_signal <= opposite_signal:
                    self.close_trade(trade, current_price, current_time, "SIGNAL")
    
    def _manage_advanced_exits(self, trade: Trade, current_price: float, current_time: datetime):
        """Manage advanced exit strategies: partial take profits"""
        if not hasattr(trade, 'original_volume'):
            return
        
        entry_price = trade.open_price
        sl_price = trade.sl
        
        # Calculate risk in points
        if trade.type == "BUY":
            risk_points = entry_price - sl_price
            current_profit_points = current_price - entry_price
        else:  # SELL
            risk_points = sl_price - entry_price
            current_profit_points = entry_price - current_price
        
        if risk_points <= 0:
            return
        
        # Calculate profit in R multiples
        profit_r = current_profit_points / risk_points
        
        # Partial Take Profit 1 (1R)
        if profit_r >= 1.0 and not trade.tp1_closed and self.config.partial_take_profits:
            tp1_volume = trade.original_volume * self.config.tp1_percent
            self._partial_close(trade, current_price, current_time, tp1_volume, "TP1")
            trade.tp1_closed = True
        
        # Partial Take Profit 2 (2R)
        elif profit_r >= 2.0 and not trade.tp2_closed and self.config.partial_take_profits:
            tp2_volume = trade.original_volume * self.config.tp2_percent
            self._partial_close(trade, current_price, current_time, tp2_volume, "TP2")
            trade.tp2_closed = True
        
        # Partial Take Profit 3 (3R)
        elif profit_r >= 3.0 and not trade.tp3_closed and self.config.partial_take_profits:
            tp3_volume = trade.original_volume * self.config.tp3_percent
            self._partial_close(trade, current_price, current_time, tp3_volume, "TP3")
            trade.tp3_closed = True
    
    def _partial_close(self, trade: Trade, close_price: float, close_time: datetime, 
                      volume: float, reason: str) -> None:
        """Execute partial close of a trade"""
        # Calculate profit for partial close
        if trade.type == "BUY":
            profit = (close_price - trade.open_price) * volume * 100
        else:
            profit = (trade.open_price - close_price) * volume * 100
        
        # Update balance
        self.current_balance += profit
        
        # Update trade volume
        trade.volume -= volume
        
        # Calculate commission for partial close
        partial_commission = volume * self.config.commission_per_lot
        self.current_balance -= partial_commission
        trade.commission += partial_commission
        
        logger.info(f"Trade {trade.ticket} partial close: {volume:.2f} @ {close_price:.2f}, profit: ${profit:.2f} ({reason})")
        
        # If volume is very small, close completely
        if trade.volume < 0.01:
            self.close_trade(trade, close_price, close_time, f"{reason}_FINAL")
    
    def calculate_equity(self, current_price: float) -> None:
        """Calculate current equity including open positions"""
        open_profit = 0.0
        for trade in self.trades:
            if not trade.closed:
                if trade.type == "BUY":
                    profit = (current_price - trade.open_price) * trade.volume * 100
                else:
                    profit = (trade.open_price - current_price) * trade.volume * 100
                open_profit += profit
        
        self.current_equity = self.current_balance + open_profit
    
    def run_backtest(self, symbol: str = "XAUUSD", timeframe: str = "H1") -> BacktestResult:
        """Run the complete enhanced backtest"""
        logger.info(f"Starting enhanced backtest for {symbol} {timeframe}")
        
        # Load and prepare data
        data = self.load_historical_data(symbol, timeframe)
        data = self.calculate_indicators(data)
        signals = self.generate_signals(data)
        
        # Initialize equity curve
        self.equity_curve.append((data.iloc[0]['time'], self.current_equity))
        
        # Run through data
        for i in range(50, len(data)):  # Start after indicator warmup
            current_time = data.iloc[i]['time']
            current_price = data.iloc[i]['close']
            
            # Get data slice for signal calculation
            data_slice = data.iloc[max(0, i-100):i+1]
            
            # Check for new signals with MTF confirmation
            if i > 0:
                prev_signal = signals.iloc[i-1]['ensemble_signal']
                current_signal = signals.iloc[i]['ensemble_signal']
                
                # Signal strength
                signal_strength = abs(current_signal)
                
                # Multi-timeframe analysis
                mtf_signals = self.calculate_mtf_signals(symbol, current_time)
                mtf_alignment = self.calculate_mtf_alignment_score(mtf_signals)
                
                # Enhanced entry logic
                if current_signal >= 2 and prev_signal < 2:  # BUY signal
                    # Check MTF alignment
                    if mtf_alignment >= 0.6 or not self.config.enable_mtf_confirmation:
                        atr = data.iloc[i]['atr']
                        sl = current_price - (atr * 2)
                        tp = current_price + (atr * 4)
                        
                        # Check position limits
                        open_trades = [t for t in self.trades if not t.closed]
                        if len(open_trades) < self.config.max_positions:
                            self.open_trade("BUY", current_price, current_time, sl, tp, 
                                           signal_strength, mtf_signals)
                
                elif current_signal <= -2 and prev_signal > -2:  # SELL signal
                    # Check MTF alignment
                    if mtf_alignment >= 0.6 or not self.config.enable_mtf_confirmation:
                        atr = data.iloc[i]['atr']
                        sl = current_price + (atr * 2)
                        tp = current_price - (atr * 4)
                        
                        # Check position limits
                        open_trades = [t for t in self.trades if not t.closed]
                        if len(open_trades) < self.config.max_positions:
                            self.open_trade("SELL", current_price, current_time, sl, tp, 
                                           signal_strength, mtf_signals)
            
            # Update existing trades
            self.update_trades(current_time, current_price, data_slice, symbol)
            
            # Calculate equity
            self.calculate_equity(current_price)
            
            # Record equity curve
            if i % 10 == 0:  # Record every 10 bars
                self.equity_curve.append((current_time, self.current_equity))
        
        # Close any remaining open trades
        final_price = data.iloc[-1]['close']
        final_time = data.iloc[-1]['time']
        for trade in self.trades:
            if not trade.closed:
                self.close_trade(trade, final_price, final_time, "END")
        
        # Calculate results
        return self.calculate_results()
    
    def calculate_results(self) -> BacktestResult:
        """Calculate backtest results and statistics"""
        closed_trades = [t for t in self.trades if t.closed]
        
        if not closed_trades:
            return BacktestResult(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, [], [])
        
        # Basic statistics
        total_trades = len(closed_trades)
        winning_trades = len([t for t in closed_trades if t.profit > 0])
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        
        # Profit metrics
        profits = [t.profit for t in closed_trades]
        gross_profit = sum(p for p in profits if p > 0)
        gross_loss = sum(p for p in profits if p < 0)
        net_profit = sum(profits)
        profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else float('inf')
        
        # Trade statistics
        avg_trade = net_profit / total_trades if total_trades > 0 else 0
        largest_win = max(profits) if profits else 0
        largest_loss = min(profits) if profits else 0
        avg_win = gross_profit / winning_trades if winning_trades > 0 else 0
        avg_loss = gross_loss / losing_trades if losing_trades > 0 else 0
        
        # Drawdown calculation
        equity_values = [eq[1] for eq in self.equity_curve]
        peak = equity_values[0]
        max_drawdown = 0
        max_drawdown_percent = 0
        
        for equity in equity_values:
            if equity > peak:
                peak = equity
            drawdown = peak - equity
            drawdown_percent = (drawdown / peak) * 100 if peak > 0 else 0
            max_drawdown = max(max_drawdown, drawdown)
            max_drawdown_percent = max(max_drawdown_percent, drawdown_percent)
        
        # Sharpe ratio (simplified)
        if len(equity_values) > 1:
            returns = [(equity_values[i] - equity_values[i-1]) / equity_values[i-1] 
                      for i in range(1, len(equity_values)) if equity_values[i-1] > 0]
            if returns:
                avg_return = np.mean(returns)
                std_return = np.std(returns)
                sharpe_ratio = avg_return / std_return * np.sqrt(252) if std_return > 0 else 0
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0
        
        # Recovery factor
        recovery_factor = net_profit / max_drawdown if max_drawdown > 0 else float('inf')
        
        # Monthly returns
        monthly_returns = {}
        for time, equity in self.equity_curve:
            month_key = time.strftime("%Y-%m")
            if month_key not in monthly_returns:
                monthly_returns[month_key] = []
            monthly_returns[month_key].append(equity)
        
        # Calculate monthly returns
        for month in monthly_returns:
            if len(monthly_returns[month]) > 1:
                start_eq = monthly_returns[month][0]
                end_eq = monthly_returns[month][-1]
                monthly_returns[month] = ((end_eq - start_eq) / start_eq) * 100
            else:
                monthly_returns[month] = 0
        
        return BacktestResult(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            net_profit=net_profit,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            max_drawdown_percent=max_drawdown_percent,
            sharpe_ratio=sharpe_ratio,
            avg_trade=avg_trade,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_win=avg_win,
            avg_loss=avg_loss,
            recovery_factor=recovery_factor,
            trades=closed_trades,
            equity_curve=self.equity_curve,
            monthly_returns=monthly_returns
        )
    
    def save_results(self, results: BacktestResult, filename: str = None) -> str:
        """Save backtest results to file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"backtest_results_{timestamp}.json"
        
        # Convert trades to serializable format
        trades_data = []
        for trade in results.trades:
            trades_data.append({
                'ticket': trade.ticket,
                'symbol': trade.symbol,
                'type': trade.type,
                'volume': trade.volume,
                'open_time': trade.open_time.isoformat(),
                'open_price': trade.open_price,
                'close_time': trade.close_time.isoformat() if trade.close_time else None,
                'close_price': trade.close_price,
                'sl': trade.sl,
                'tp': trade.tp,
                'commission': trade.commission,
                'profit': trade.profit,
                'close_reason': trade.close_reason
            })
        
        # Prepare results data
        results_data = {
            'config': {
                'start_date': self.config.start_date.isoformat(),
                'end_date': self.config.end_date.isoformat(),
                'initial_balance': self.config.initial_balance,
                'commission_per_lot': self.config.commission_per_lot,
                'spread_points': self.config.spread_points
            },
            'summary': {
                'total_trades': results.total_trades,
                'winning_trades': results.winning_trades,
                'losing_trades': results.losing_trades,
                'win_rate': results.win_rate,
                'net_profit': results.net_profit,
                'gross_profit': results.gross_profit,
                'gross_loss': results.gross_loss,
                'profit_factor': results.profit_factor,
                'max_drawdown': results.max_drawdown,
                'max_drawdown_percent': results.max_drawdown_percent,
                'sharpe_ratio': results.sharpe_ratio,
                'avg_trade': results.avg_trade,
                'largest_win': results.largest_win,
                'largest_loss': results.largest_loss,
                'avg_win': results.avg_win,
                'avg_loss': results.avg_loss,
                'recovery_factor': results.recovery_factor
            },
            'trades': trades_data,
            'equity_curve': [(t.isoformat(), e) for t, e in results.equity_curve],
            'monthly_returns': results.monthly_returns
        }
        
        # Save to file
        import json
        filepath = Path("backtest_results") / filename
        filepath.parent.mkdir(exist_ok=True)
        
        with open(filepath, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        logger.info(f"Backtest results saved to {filepath}")
        return str(filepath)


def run_sample_backtest():
    """Run a sample backtest with enhanced features"""
    config = BacktestConfig(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 3, 31),
        initial_balance=10000.0,
        use_kelly_criterion=True,
        kelly_fraction=0.25,
        enable_mtf_confirmation=True,
        enable_advanced_exits=True,
        partial_take_profits=True,
        tp1_percent=0.5,
        tp2_percent=0.3,
        tp3_percent=0.2,
        risk_percent=1.0,
        max_positions=1
    )
    
    engine = BacktestingEngine(config)
    results = engine.run_backtest()
    
    # Print results
    print(f"""
    Enhanced Backtest Results Summary:
    =================================
    Configuration:
    - Kelly Criterion: {config.use_kelly_criterion}
    - MTF Confirmation: {config.enable_mtf_confirmation}
    - Advanced Exits: {config.enable_advanced_exits}
    - Partial TPs: {config.partial_take_profits}
    
    Performance:
    - Total Trades: {results.total_trades}
    - Win Rate: {results.win_rate:.2f}%
    - Net Profit: ${results.net_profit:.2f}
    - Profit Factor: {results.profit_factor:.2f}
    - Max Drawdown: {results.max_drawdown_percent:.2f}%
    - Sharpe Ratio: {results.sharpe_ratio:.2f}
    - Average Trade: ${results.avg_trade:.2f}
    - Recovery Factor: {results.recovery_factor:.2f}
    
    Trade Statistics:
    - Winning Trades: {results.winning_trades}
    - Losing Trades: {results.losing_trades}
    - Largest Win: ${results.largest_win:.2f}
    - Largest Loss: ${results.largest_loss:.2f}
    - Average Win: ${results.avg_win:.2f}
    - Average Loss: ${results.avg_loss:.2f}
    """)
    
    # Save results
    filepath = engine.save_results(results)
    print(f"Results saved to: {filepath}")
    
    return results


if __name__ == "__main__":
    run_sample_backtest()
