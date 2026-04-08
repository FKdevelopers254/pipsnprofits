"""
Trading Environment for Reinforcement Learning
Interfaces with MT5 and provides environment for RL agent
"""

import asyncio
import numpy as np
from typing import Tuple, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from src.services.mt5_service import mt5_manager
from src.services.chart_service import chart_data_service
from src.services.performance_analytics import performance_analytics

logger = logging.getLogger(__name__)

class TradingEnvironment:
    """Trading Environment for RL Agent"""
    
    def __init__(
        self,
        symbol: str = "XAUUSD",
        timeframe: str = "H1",
        initial_balance: float = 10000.0,
        max_position_size: float = 0.1,
        max_positions: int = 1,
        spread_cost: float = 0.0002,
        commission_per_lot: float = 7.0
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.max_position_size = max_position_size
        self.max_positions = max_positions
        self.spread_cost = spread_cost
        self.commission_per_lot = commission_per_lot
        
        # Trading state
        self.positions = []
        self.closed_trades = []
        self.current_step = 0
        self.episode_step = 0
        self.max_episode_steps = 1000  # Max steps per episode
        
        # Performance tracking
        self.total_pnl = 0.0
        self.max_drawdown = 0.0
        self.peak_balance = initial_balance
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        
        # State configuration
        self.state_size = 50  # Will be calculated based on features
        self.action_size = 5  # HOLD, BUY, SELL, CLOSE_LONG, CLOSE_SHORT
        
        # Action mapping
        self.action_map = {
            0: 'HOLD',
            1: 'BUY',
            2: 'SELL', 
            3: 'CLOSE_LONG',
            4: 'CLOSE_SHORT'
        }
        
        logger.info(f"Trading Environment initialized for {symbol} {timeframe}")
    
    def reset(self) -> np.ndarray:
        """Reset environment for new episode"""
        self.current_balance = self.initial_balance
        self.positions = []
        self.closed_trades = []
        self.episode_step = 0
        self.total_pnl = 0.0
        self.max_drawdown = 0.0
        self.peak_balance = self.initial_balance
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        
        # Get initial state
        initial_state = self._get_current_state()
        
        logger.info(f"Environment reset. Initial state shape: {initial_state.shape}")
        return initial_state
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict[str, Any]]:
        """Execute action and return new state, reward, done, info"""
        
        action_name = self.action_map.get(action, 'HOLD')
        logger.debug(f"Step {self.episode_step}: Executing {action_name} (action={action})")
        
        # Execute action
        reward = 0.0
        info = {
            'action': action_name,
            'action_id': action,
            'step': self.episode_step,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            if action_name == 'HOLD':
                reward = self._handle_hold()
            
            elif action_name == 'BUY':
                reward = self._handle_buy(info)
            
            elif action_name == 'SELL':
                reward = self._handle_sell(info)
            
            elif action_name == 'CLOSE_LONG':
                reward = self._handle_close_long(info)
            
            elif action_name == 'CLOSE_SHORT':
                reward = self._handle_close_short(info)
            
            # Update positions and calculate unrealized P&L
            self._update_positions()
            
            # Get new state
            next_state = self._get_current_state()
            
            # Check if episode is done
            done = self._is_episode_done()
            
            # Update episode step
            self.episode_step += 1
            self.current_step += 1
            
            # Add additional info
            info.update({
                'balance': self.current_balance,
                'total_pnl': self.total_pnl,
                'positions': len(self.positions),
                'max_drawdown': self.max_drawdown,
                'consecutive_wins': self.consecutive_wins,
                'consecutive_losses': self.consecutive_losses,
                'done': done
            })
            
            logger.debug(f"Step result: reward={reward:.4f}, done={done}, balance={self.current_balance:.2f}")
            
            return next_state, reward, done, info
            
        except Exception as e:
            logger.error(f"Error executing action {action_name}: {e}")
            # Return penalty for failed action
            return self._get_current_state(), -1.0, True, {'error': str(e)}
    
    def _handle_hold(self) -> float:
        """Handle HOLD action - small penalty for inaction"""
        # Small penalty for holding to encourage action
        return -0.001
    
    def _handle_buy(self, info: Dict) -> float:
        """Handle BUY action"""
        if len(self.positions) >= self.max_positions:
            # Penalty for trying to open too many positions
            return -0.5
        
        # Check if we already have a long position
        long_positions = [p for p in self.positions if p['type'] == 'BUY']
        if long_positions:
            # Penalty for duplicate position type
            return -0.2
        
        try:
            # Get current price
            current_price = self._get_current_price()
            if not current_price:
                return -0.1
            
            # Calculate position size (simplified - fixed size for now)
            position_size = self.max_position_size
            
            # Calculate transaction costs
            spread_cost = self.spread_cost * position_size
            commission_cost = self.commission_per_lot * position_size
            total_cost = spread_cost + commission_cost
            
            # Create position
            position = {
                'type': 'BUY',
                'volume': position_size,
                'open_price': current_price,
                'open_time': datetime.now(),
                'spread_cost': spread_cost,
                'commission_cost': commission_cost,
                'total_cost': total_cost
            }
            
            self.positions.append(position)
            
            # Immediate cost penalty
            reward = -total_cost
            
            info['position_opened'] = True
            info['open_price'] = current_price
            info['position_size'] = position_size
            info['transaction_cost'] = total_cost
            
            logger.info(f"BUY position opened: {position_size} lots at {current_price}")
            
            return reward
            
        except Exception as e:
            logger.error(f"Error opening BUY position: {e}")
            return -0.5
    
    def _handle_sell(self, info: Dict) -> float:
        """Handle SELL action"""
        if len(self.positions) >= self.max_positions:
            return -0.5
        
        # Check if we already have a short position
        short_positions = [p for p in self.positions if p['type'] == 'SELL']
        if short_positions:
            return -0.2
        
        try:
            current_price = self._get_current_price()
            if not current_price:
                return -0.1
            
            position_size = self.max_position_size
            
            spread_cost = self.spread_cost * position_size
            commission_cost = self.commission_per_lot * position_size
            total_cost = spread_cost + commission_cost
            
            position = {
                'type': 'SELL',
                'volume': position_size,
                'open_price': current_price,
                'open_time': datetime.now(),
                'spread_cost': spread_cost,
                'commission_cost': commission_cost,
                'total_cost': total_cost
            }
            
            self.positions.append(position)
            
            reward = -total_cost
            
            info['position_opened'] = True
            info['open_price'] = current_price
            info['position_size'] = position_size
            info['transaction_cost'] = total_cost
            
            logger.info(f"SELL position opened: {position_size} lots at {current_price}")
            
            return reward
            
        except Exception as e:
            logger.error(f"Error opening SELL position: {e}")
            return -0.5
    
    def _handle_close_long(self, info: Dict) -> float:
        """Handle CLOSE_LONG action"""
        long_positions = [p for p in self.positions if p['type'] == 'BUY']
        
        if not long_positions:
            # Penalty for trying to close non-existent position
            return -0.3
        
        # Close the oldest long position
        position = long_positions[0]
        return self._close_position(position, info)
    
    def _handle_close_short(self, info: Dict) -> float:
        """Handle CLOSE_SHORT action"""
        short_positions = [p for p in self.positions if p['type'] == 'SELL']
        
        if not short_positions:
            return -0.3
        
        # Close the oldest short position
        position = short_positions[0]
        return self._close_position(position, info)
    
    def _close_position(self, position: Dict, info: Dict) -> float:
        """Close a position and calculate reward"""
        try:
            current_price = self._get_current_price()
            if not current_price:
                return -0.1
            
            # Calculate P&L
            if position['type'] == 'BUY':
                pnl = (current_price - position['open_price']) * position['volume']
            else:  # SELL
                pnl = (position['open_price'] - current_price) * position['volume']
            
            # Subtract transaction costs
            net_pnl = pnl - position['total_cost']
            
            # Update balance
            self.current_balance += net_pnl
            self.total_pnl += net_pnl
            
            # Update consecutive wins/losses
            if net_pnl > 0:
                self.consecutive_wins += 1
                self.consecutive_losses = 0
            else:
                self.consecutive_losses += 1
                self.consecutive_wins = 0
            
            # Track drawdown
            if self.current_balance > self.peak_balance:
                self.peak_balance = self.current_balance
            drawdown = (self.peak_balance - self.current_balance) / self.peak_balance
            self.max_drawdown = max(self.max_drawdown, drawdown)
            
            # Store closed trade
            closed_trade = {
                **position,
                'close_price': current_price,
                'close_time': datetime.now(),
                'pnl': net_pnl,
                'gross_pnl': pnl,
                'duration': (datetime.now() - position['open_time']).total_seconds() / 3600  # hours
            }
            
            self.closed_trades.append(closed_trade)
            self.positions.remove(position)
            
            # Calculate reward
            reward = self._calculate_reward(net_pnl, closed_trade)
            
            info['position_closed'] = True
            info['close_price'] = current_price
            info['pnl'] = net_pnl
            info['gross_pnl'] = pnl
            info['duration_hours'] = closed_trade['duration']
            info['consecutive_wins'] = self.consecutive_wins
            info['consecutive_losses'] = self.consecutive_losses
            
            logger.info(f"Position closed: {position['type']} P&L={net_pnl:.2f}, Reward={reward:.4f}")
            
            return reward
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return -0.5
    
    def _calculate_reward(self, net_pnl: float, trade: Dict) -> float:
        """Calculate reward for closed position"""
        # Base reward from P&L
        reward = net_pnl * 100  # Scale P&L
        
        # Risk adjustment
        if self.max_drawdown > 0.05:  # 5% drawdown
            reward *= 0.5  # Penalize high drawdown
        
        # Duration bonus/penalty
        duration = trade['duration_hours']
        if 1 <= duration <= 24:  # Ideal duration
            reward *= 1.1
        elif duration > 48:  # Too long
            reward *= 0.8
        
        # Consecutive wins bonus
        if self.consecutive_wins > 2:
            reward *= 1.2
        
        # Consecutive losses penalty
        if self.consecutive_losses > 3:
            reward *= 0.7
        
        return reward
    
    def _update_positions(self):
        """Update unrealized P&L for open positions"""
        current_price = self._get_current_price()
        if not current_price:
            return
        
        for position in self.positions:
            if position['type'] == 'BUY':
                position['unrealized_pnl'] = (current_price - position['open_price']) * position['volume']
            else:  # SELL
                position['unrealized_pnl'] = (position['open_price'] - current_price) * position['volume']
    
    def _get_current_price(self) -> Optional[float]:
        """Get current market price"""
        try:
            # Get latest candle from chart service
            chart_data = chart_data_service.get_chart_data()
            if chart_data and chart_data.get('candles'):
                latest_candle = chart_data['candles'][-1]
                return latest_candle['close']
            
            # Fallback to MT5
            if mt5_manager._initialized:
                tick = mt5_manager.symbol_info_tick(self.symbol)
                if tick:
                    return tick.bid
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting current price: {e}")
            return None
    
    def _get_current_state(self) -> np.ndarray:
        """Get current state representation"""
        try:
            # Get chart data
            chart_data = chart_data_service.get_chart_data()
            candles = chart_data.get('candles', []) if chart_data else []
            
            # Get technical indicators
            indicators = chart_data.get('indicators', {})
            
            # Build state vector
            state_features = []
            
            # 1. Price features (last 10 candles)
            if len(candles) >= 10:
                recent_candles = candles[-10:]
                for candle in recent_candles:
                    # Normalize prices (relative to current price)
                    current_price = recent_candles[-1]['close']
                    state_features.extend([
                        (candle['open'] - current_price) / current_price,
                        (candle['high'] - current_price) / current_price,
                        (candle['low'] - current_price) / current_price,
                        (candle['close'] - current_price) / current_price,
                        candle['volume'] / (max([c['volume'] for c in recent_candles]) + 1e-8)
                    ])
            else:
                # Pad with zeros if not enough data
                state_features.extend([0.0] * 50)
            
            # 2. Technical indicators (if available)
            if indicators:
                # Moving averages
                ma20 = indicators.get('ma20', [])[-10:] if indicators.get('ma20') else []
                ma50 = indicators.get('ma50', [])[-10:] if indicators.get('ma50') else []
                
                if ma20 and ma50:
                    state_features.extend([
                        (ma20[-1] - candles[-1]['close']) / candles[-1]['close'],
                        (ma50[-1] - candles[-1]['close']) / candles[-1]['close'],
                        (ma20[-1] - ma50[-1]) / ma50[-1] if ma50[-1] != 0 else 0
                    ])
                else:
                    state_features.extend([0.0, 0.0, 0.0])
                
                # RSI
                rsi = indicators.get('rsi', [])[-10:] if indicators.get('rsi') else []
                if rsi:
                    state_features.extend([
                        (rsi[-1] - 50) / 50,  # Normalize RSI
                        np.mean(rsi[-5:]) / 100 if len(rsi) >= 5 else 0.5
                    ])
                else:
                    state_features.extend([0.0, 0.0])
                
                # Bollinger Bands
                bb = indicators.get('bollinger', {})
                if bb and all(k in bb for k in ['upper', 'middle', 'lower']):
                    current_price = candles[-1]['close']
                    bb_position = (current_price - bb['lower'][-1]) / (bb['upper'][-1] - bb['lower'][-1] + 1e-8)
                    state_features.extend([bb_position])
                else:
                    state_features.extend([0.5])
            
            # 3. Portfolio features
            state_features.extend([
                len(self.positions) / self.max_positions,  # Position utilization
                self.total_pnl / self.initial_balance,  # Total P&L relative
                self.max_drawdown,  # Max drawdown
                self.consecutive_wins / 10,  # Consecutive wins (normalized)
                self.consecutive_losses / 10,  # Consecutive losses (normalized)
            ])
            
            # 4. Time features
            now = datetime.now()
            state_features.extend([
                now.hour / 24,  # Hour of day
                now.weekday() / 6,  # Day of week
                1.0 if 9 <= now.hour <= 16 else 0.0,  # Trading session
            ])
            
            # Convert to numpy array and ensure fixed size
            state_array = np.array(state_features, dtype=np.float32)
            
            # Pad or truncate to fixed size
            if len(state_array) < self.state_size:
                state_array = np.pad(state_array, (0, self.state_size - len(state_array)))
            elif len(state_array) > self.state_size:
                state_array = state_array[:self.state_size]
            
            return state_array
            
        except Exception as e:
            logger.error(f"Error getting current state: {e}")
            return np.zeros(self.state_size, dtype=np.float32)
    
    def _is_episode_done(self) -> bool:
        """Check if episode should end"""
        # End conditions:
        # 1. Max steps reached
        if self.episode_step >= self.max_episode_steps:
            return True
        
        # 2. Account blown (more than 50% loss)
        if self.current_balance < self.initial_balance * 0.5:
            return True
        
        # 3. Maximum drawdown exceeded
        if self.max_drawdown > 0.2:  # 20% drawdown
            return True
        
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get environment statistics"""
        return {
            'current_balance': self.current_balance,
            'initial_balance': self.initial_balance,
            'total_pnl': self.total_pnl,
            'total_return': (self.current_balance - self.initial_balance) / self.initial_balance,
            'max_drawdown': self.max_drawdown,
            'peak_balance': self.peak_balance,
            'open_positions': len(self.positions),
            'closed_trades': len(self.closed_trades),
            'consecutive_wins': self.consecutive_wins,
            'consecutive_losses': self.consecutive_losses,
            'episode_step': self.episode_step,
            'total_steps': self.current_step,
            'win_rate': self._calculate_win_rate(),
            'avg_trade_pnl': self._calculate_avg_trade_pnl(),
            'sharpe_ratio': self._calculate_sharpe_ratio()
        }
    
    def _calculate_win_rate(self) -> float:
        """Calculate win rate"""
        if not self.closed_trades:
            return 0.0
        
        winning_trades = [t for t in self.closed_trades if t['pnl'] > 0]
        return len(winning_trades) / len(self.closed_trades)
    
    def _calculate_avg_trade_pnl(self) -> float:
        """Calculate average trade P&L"""
        if not self.closed_trades:
            return 0.0
        
        return np.mean([t['pnl'] for t in self.closed_trades])
    
    def _calculate_sharpe_ratio(self) -> float:
        """Calculate Sharpe ratio"""
        if len(self.closed_trades) < 2:
            return 0.0
        
        pnls = [t['pnl'] for t in self.closed_trades]
        if np.std(pnls) == 0:
            return 0.0
        
        return np.mean(pnls) / np.std(pnls)
