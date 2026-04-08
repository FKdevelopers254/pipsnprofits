import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import statistics
import json

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetrics:
    """Enhanced performance metrics data structure"""
    # Basic metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    
    # Advanced metrics
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    avg_trade_duration: float = 0.0
    
    # Session performance
    london_session_pnl: float = 0.0
    ny_session_pnl: float = 0.0
    asian_session_pnl: float = 0.0
    
    # Strategy performance
    strategy_performance: Dict[str, Dict[str, Any]] = None
    
    # Time-based performance
    daily_pnl_history: List[Dict[str, Any]] = None
    hourly_performance: Dict[int, Dict[str, Any]] = None
    
    # Risk metrics
    risk_reward_ratio: float = 0.0
    avg_risk_per_trade: float = 0.0
    volatility_adjusted_returns: float = 0.0

class PerformanceAnalytics:
    """Enhanced performance analytics service"""
    
    def __init__(self):
        self._trade_history: deque = deque(maxlen=1000)  # Last 1000 trades
        self._daily_pnl: Dict[str, float] = defaultdict(float)
        self._hourly_stats: Dict[int, List[float]] = defaultdict(list)
        self._session_stats: Dict[str, List[float]] = defaultdict(list)
        self._strategy_stats: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._equity_curve: List[Tuple[datetime, float]] = []
        self._peak_equity: float = 0.0
        self._current_drawdown: float = 0.0
        self._current_equity: float = 0.0
        
    def add_trade(self, trade_data: Dict[str, Any]):
        """Add a completed trade to analytics"""
        try:
            trade = {
                'timestamp': trade_data.get('timestamp', datetime.now()),
                'symbol': trade_data.get('symbol', 'XAUUSD'),
                'type': trade_data.get('type', 'BUY'),
                'volume': trade_data.get('volume', 0.01),
                'entry_price': trade_data.get('entry_price', 0.0),
                'exit_price': trade_data.get('exit_price', 0.0),
                'pnl': trade_data.get('pnl', 0.0),
                'duration_minutes': trade_data.get('duration_minutes', 0),
                'session': trade_data.get('session', 'unknown'),
                'strategy': trade_data.get('strategy', 'ensemble'),
                'signal_strength': trade_data.get('signal_strength', 0),
                'mtf_alignment': trade_data.get('mtf_alignment', 0.0),
                'pattern': trade_data.get('pattern', 'none'),
                'risk_reward': trade_data.get('risk_reward', 1.0)
            }
            
            self._trade_history.append(trade)
            self._update_daily_pnl(trade)
            self._update_hourly_stats(trade)
            self._update_session_stats(trade)
            self._update_strategy_stats(trade)
            self._update_equity_curve(trade['pnl'])
            
            logger.info(f"Trade added to analytics: {trade['type']} {trade['symbol']} PnL: ${trade['pnl']:.2f}")
            
        except Exception as e:
            logger.error(f"Error adding trade to analytics: {e}")
    
    def _update_daily_pnl(self, trade: Dict[str, Any]):
        """Update daily P&L tracking"""
        date_str = trade['timestamp'].strftime('%Y-%m-%d')
        self._daily_pnl[date_str] += trade['pnl']
    
    def _update_hourly_stats(self, trade: Dict[str, Any]):
        """Update hourly performance statistics"""
        hour = trade['timestamp'].hour
        self._hourly_stats[hour].append(trade['pnl'])
    
    def _update_session_stats(self, trade: Dict[str, Any]):
        """Update session-based performance"""
        session = trade['session']
        self._session_stats[session].append(trade['pnl'])
    
    def _update_strategy_stats(self, trade: Dict[str, Any]):
        """Update strategy-specific performance"""
        strategy = trade['strategy']
        self._strategy_stats[strategy].append(trade)
    
    def _update_equity_curve(self, pnl: float):
        """Update equity curve and drawdown calculations"""
        self._current_equity += pnl
        timestamp = datetime.now()
        self._equity_curve.append((timestamp, self._current_equity))
        
        # Update peak equity and drawdown
        if self._current_equity > self._peak_equity:
            self._peak_equity = self._current_equity
            self._current_drawdown = 0.0
        else:
            self._current_drawdown = self._peak_equity - self._current_equity
    
    def calculate_metrics(self, days: int = 30) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics"""
        try:
            if not self._trade_history:
                return PerformanceMetrics()
            
            # Filter trades by date range
            cutoff_date = datetime.now() - timedelta(days=days)
            recent_trades = [t for t in self._trade_history if t['timestamp'] > cutoff_date]
            
            if not recent_trades:
                return PerformanceMetrics()
            
            metrics = PerformanceMetrics()
            
            # Basic metrics
            metrics.total_trades = len(recent_trades)
            pnls = [t['pnl'] for t in recent_trades]
            metrics.total_pnl = sum(pnls)
            
            winning_trades = [t for t in recent_trades if t['pnl'] > 0]
            losing_trades = [t for t in recent_trades if t['pnl'] < 0]
            
            metrics.winning_trades = len(winning_trades)
            metrics.losing_trades = len(losing_trades)
            metrics.win_rate = (metrics.winning_trades / metrics.total_trades * 100) if metrics.total_trades > 0 else 0
            
            # Advanced metrics
            if winning_trades:
                metrics.avg_win = statistics.mean([t['pnl'] for t in winning_trades])
                metrics.largest_win = max([t['pnl'] for t in winning_trades])
            
            if losing_trades:
                metrics.avg_loss = statistics.mean([t['pnl'] for t in losing_trades])
                metrics.largest_loss = min([t['pnl'] for t in losing_trades])
            
            # Profit factor
            total_wins = sum([t['pnl'] for t in winning_trades])
            total_losses = abs(sum([t['pnl'] for t in losing_trades]))
            metrics.profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
            
            # Risk reward ratio
            if metrics.avg_loss != 0:
                metrics.risk_reward_ratio = abs(metrics.avg_win / metrics.avg_loss)
            
            # Sharpe ratio (simplified)
            if len(pnls) > 1:
                returns_std = statistics.stdev(pnls)
                avg_return = statistics.mean(pnls)
                metrics.sharpe_ratio = avg_return / returns_std if returns_std > 0 else 0
            
            # Max drawdown
            metrics.max_drawdown = self._current_drawdown
            if self._peak_equity > 0:
                metrics.max_drawdown_percent = (metrics.max_drawdown / self._peak_equity * 100)
            
            # Consecutive wins/losses
            metrics.consecutive_wins = self._calculate_max_consecutive(recent_trades, True)
            metrics.consecutive_losses = self._calculate_max_consecutive(recent_trades, False)
            
            # Average trade duration
            durations = [t['duration_minutes'] for t in recent_trades if t['duration_minutes'] > 0]
            if durations:
                metrics.avg_trade_duration = statistics.mean(durations)
            
            # Session performance
            metrics.london_session_pnl = sum([t['pnl'] for t in recent_trades if t['session'] == 'london'])
            metrics.ny_session_pnl = sum([t['pnl'] for t in recent_trades if t['session'] == 'ny'])
            metrics.asian_session_pnl = sum([t['pnl'] for t in recent_trades if t['session'] == 'asian'])
            
            # Strategy performance
            metrics.strategy_performance = self._calculate_strategy_performance(recent_trades)
            
            # Time-based performance
            metrics.daily_pnl_history = self._get_daily_pnl_history(days)
            metrics.hourly_performance = self._calculate_hourly_performance()
            
            # Risk metrics
            metrics.avg_risk_per_trade = statistics.mean([abs(t['pnl']) for t in recent_trades])
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")
            return PerformanceMetrics()
    
    def _calculate_max_consecutive(self, trades: List[Dict], wins: bool) -> int:
        """Calculate maximum consecutive wins or losses"""
        max_consecutive = 0
        current_consecutive = 0
        
        for trade in trades:
            if (wins and trade['pnl'] > 0) or (not wins and trade['pnl'] < 0):
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        return max_consecutive
    
    def _calculate_strategy_performance(self, trades: List[Dict]) -> Dict[str, Dict[str, Any]]:
        """Calculate performance by strategy"""
        strategy_perf = {}
        
        for strategy, strategy_trades in self._strategy_stats.items():
            if not strategy_trades:
                continue
                
            recent_strategy_trades = [t for t in strategy_trades 
                                    if t['timestamp'] > datetime.now() - timedelta(days=30)]
            
            if recent_strategy_trades:
                pnls = [t['pnl'] for t in recent_strategy_trades]
                wins = [t for t in recent_strategy_trades if t['pnl'] > 0]
                
                strategy_perf[strategy] = {
                    'total_trades': len(recent_strategy_trades),
                    'win_rate': (len(wins) / len(recent_strategy_trades) * 100) if recent_strategy_trades else 0,
                    'total_pnl': sum(pnls),
                    'avg_pnl': statistics.mean(pnls) if pnls else 0,
                    'profit_factor': self._calculate_profit_factor(pnls)
                }
        
        return strategy_perf
    
    def _calculate_profit_factor(self, pnls: List[float]) -> float:
        """Calculate profit factor for a list of P&L values"""
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        
        total_wins = sum(wins)
        total_losses = abs(sum(losses))
        
        return total_wins / total_losses if total_losses > 0 else float('inf')
    
    def _get_daily_pnl_history(self, days: int) -> List[Dict[str, Any]]:
        """Get daily P&L history for the specified period"""
        history = []
        cutoff_date = datetime.now() - timedelta(days=days)
        
        for date_str in sorted(self._daily_pnl.keys()):
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            if date_obj >= cutoff_date:
                history.append({
                    'date': date_str,
                    'pnl': self._daily_pnl[date_str],
                    'cumulative': sum([self._daily_pnl[d] for d in sorted(self._daily_pnl.keys()) 
                                      if d <= date_str])
                })
        
        return history
    
    def _calculate_hourly_performance(self) -> Dict[int, Dict[str, Any]]:
        """Calculate performance by hour of day"""
        hourly_perf = {}
        
        for hour, pnls in self._hourly_stats.items():
            if pnls:
                wins = [p for p in pnls if p > 0]
                hourly_perf[hour] = {
                    'total_trades': len(pnls),
                    'win_rate': (len(wins) / len(pnls) * 100) if pnls else 0,
                    'avg_pnl': statistics.mean(pnls),
                    'total_pnl': sum(pnls)
                }
        
        return hourly_perf
    
    def get_equity_curve_data(self) -> List[Dict[str, Any]]:
        """Get equity curve data for charting"""
        return [
            {'timestamp': timestamp.isoformat(), 'equity': equity}
            for timestamp, equity in self._equity_curve
        ]
    
    def get_session_performance(self) -> Dict[str, Dict[str, Any]]:
        """Get session-based performance metrics"""
        session_perf = {}
        
        for session, pnls in self._session_stats.items():
            if pnls:
                wins = [p for p in pnls if p > 0]
                session_perf[session] = {
                    'total_pnl': sum(pnls),
                    'win_rate': (len(wins) / len(pnls) * 100) if pnls else 0,
                    'avg_pnl': statistics.mean(pnls),
                    'total_trades': len(pnls)
                }
        
        return session_perf

# Global analytics instance
performance_analytics = PerformanceAnalytics()
