"""
Reward Calculation System for Reinforcement Learning
Implements sophisticated reward functions for trading
"""

import numpy as np
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class RewardCalculator:
    """Advanced Reward Calculation for RL Trading"""
    
    def __init__(
        self,
        risk_free_rate: float = 0.02,  # Annual risk-free rate
        trading_days_per_year: int = 252,
        max_drawdown_threshold: float = 0.15,  # 15% max drawdown
        consecutive_loss_penalty: float = 0.5,
        win_streak_bonus: float = 0.3,
        sharpe_threshold: float = 1.0,
        profit_factor_target: float = 1.5
    ):
        self.risk_free_rate = risk_free_rate
        self.trading_days_per_year = trading_days_per_year
        self.max_drawdown_threshold = max_drawdown_threshold
        self.consecutive_loss_penalty = consecutive_loss_penalty
        self.win_streak_bonus = win_streak_bonus
        self.sharpe_threshold = sharpe_threshold
        self.profit_factor_target = profit_factor_target
        
        # Reward tracking
        self.rewards_history = []
        self.pnl_history = []
        self.drawdown_history = []
        
        logger.info("Reward Calculator initialized")
    
    def calculate_reward(
        self,
        action: str,
        pnl: float,
        balance: float,
        drawdown: float,
        consecutive_wins: int,
        consecutive_losses: int,
        trade_duration: Optional[float] = None,
        volatility: Optional[float] = None,
        spread_cost: Optional[float] = None,
        position_size: Optional[float] = None
    ) -> Dict[str, Any]:
        """Calculate comprehensive reward for trading action"""
        
        reward_components = {}
        
        # 1. Base P&L Reward
        pnl_reward = self._calculate_pnl_reward(pnl, balance)
        reward_components['pnl_reward'] = pnl_reward
        
        # 2. Risk-Adjusted Reward
        risk_reward = self._calculate_risk_adjusted_reward(pnl, drawdown, volatility)
        reward_components['risk_reward'] = risk_reward
        
        # 3. Transaction Cost Penalty
        cost_penalty = self._calculate_transaction_penalty(spread_cost, position_size)
        reward_components['cost_penalty'] = cost_penalty
        
        # 4. Time-Based Reward
        time_reward = self._calculate_time_reward(trade_duration)
        reward_components['time_reward'] = time_reward
        
        # 5. Streak Bonus/Penalty
        streak_reward = self._calculate_streak_reward(consecutive_wins, consecutive_losses)
        reward_components['streak_reward'] = streak_reward
        
        # 6. Drawdown Penalty
        drawdown_penalty = self._calculate_drawdown_penalty(drawdown)
        reward_components['drawdown_penalty'] = drawdown_penalty
        
        # 7. Action-Specific Rewards
        action_reward = self._calculate_action_reward(action, pnl)
        reward_components['action_reward'] = action_reward
        
        # 8. Volatility Adjustment
        volatility_adjustment = self._calculate_volatility_adjustment(pnl, volatility)
        reward_components['volatility_adjustment'] = volatility_adjustment
        
        # Calculate total reward
        total_reward = sum(reward_components.values())
        reward_components['total_reward'] = total_reward
        
        # Track history
        self.rewards_history.append(total_reward)
        self.pnl_history.append(pnl)
        self.drawdown_history.append(drawdown)
        
        # Keep only recent history
        max_history = 1000
        if len(self.rewards_history) > max_history:
            self.rewards_history = self.rewards_history[-max_history:]
            self.pnl_history = self.pnl_history[-max_history:]
            self.drawdown_history = self.drawdown_history[-max_history:]
        
        return reward_components
    
    def _calculate_pnl_reward(self, pnl: float, balance: float) -> float:
        """Calculate base P&L reward"""
        # Scale P&L by account size for normalization
        scaled_pnl = pnl / balance if balance > 0 else pnl
        
        # Apply sigmoid to bound extreme values
        reward = np.tanh(scaled_pnl * 10)  # Scale and bound
        
        return reward
    
    def _calculate_risk_adjusted_reward(self, pnl: float, drawdown: float, volatility: Optional[float]) -> float:
        """Calculate risk-adjusted reward using Sortino-like ratio"""
        
        # Base risk adjustment based on drawdown
        if drawdown > 0.05:  # 5% drawdown
            risk_multiplier = 0.5
        elif drawdown > 0.10:  # 10% drawdown
            risk_multiplier = 0.3
        elif drawdown > 0.15:  # 15% drawdown
            risk_multiplier = 0.1
        else:
            risk_multiplier = 1.0
        
        # Volatility adjustment (if available)
        if volatility is not None and volatility > 0:
            # Higher volatility = higher risk, lower reward
            vol_adjustment = 1.0 / (1.0 + volatility)
            risk_multiplier *= vol_adjustment
        
        return pnl * risk_multiplier
    
    def _calculate_transaction_penalty(self, spread_cost: Optional[float], position_size: Optional[float]) -> float:
        """Calculate transaction cost penalty"""
        if spread_cost is None or position_size is None:
            return 0.0
        
        total_cost = spread_cost * position_size
        
        # Penalize high transaction costs
        penalty = -total_cost * 2  # Double the cost as penalty
        
        return penalty
    
    def _calculate_time_reward(self, trade_duration: Optional[float]) -> float:
        """Calculate time-based reward for trade duration"""
        if trade_duration is None:
            return 0.0
        
        # Optimal trading duration (in hours)
        optimal_min = 0.5  # 30 minutes
        optimal_max = 24.0  # 24 hours
        
        if optimal_min <= trade_duration <= optimal_max:
            # Bonus for optimal duration
            return 0.1
        elif trade_duration < optimal_min:
            # Penalty for too short (overtrading)
            return -0.05
        elif trade_duration > optimal_max * 2:
            # Penalty for too long (undertrading)
            return -0.1
        else:
            return 0.0
    
    def _calculate_streak_reward(self, consecutive_wins: int, consecutive_losses: int) -> float:
        """Calculate streak-based reward"""
        
        # Win streak bonus
        if consecutive_wins >= 3:
            win_bonus = self.win_streak_bonus * (consecutive_wins - 2)
        else:
            win_bonus = 0.0
        
        # Loss streak penalty
        if consecutive_losses >= 3:
            loss_penalty = -self.consecutive_loss_penalty * (consecutive_losses - 2)
        else:
            loss_penalty = 0.0
        
        return win_bonus + loss_penalty
    
    def _calculate_drawdown_penalty(self, drawdown: float) -> float:
        """Calculate drawdown penalty"""
        
        if drawdown <= 0.02:  # 2% drawdown
            return 0.0
        elif drawdown <= 0.05:  # 5% drawdown
            return -0.1
        elif drawdown <= 0.10:  # 10% drawdown
            return -0.3
        elif drawdown <= 0.15:  # 15% drawdown
            return -0.5
        else:
            # Severe drawdown penalty
            return -1.0
    
    def _calculate_action_reward(self, action: str, pnl: float) -> float:
        """Calculate action-specific rewards"""
        
        if action in ['BUY', 'SELL']:
            # Opening position - small cost
            return -0.01
        
        elif action in ['CLOSE_LONG', 'CLOSE_SHORT']:
            # Closing position - reward based on P&L
            if pnl > 0:
                return 0.05  # Small bonus for profitable close
            else:
                return -0.02  # Small penalty for losing close
        
        elif action == 'HOLD':
            # Holding - small penalty to encourage action
            return -0.005
        
        return 0.0
    
    def _calculate_volatility_adjustment(self, pnl: float, volatility: Optional[float]) -> float:
        """Calculate volatility adjustment for reward"""
        
        if volatility is None or volatility <= 0:
            return 0.0
        
        # Adjust reward based on volatility
        # High volatility: reduce reward (riskier)
        # Low volatility: increase reward (safer)
        
        if volatility > 0.02:  # High volatility
            adjustment = -abs(pnl) * 0.2
        elif volatility > 0.01:  # Medium volatility
            adjustment = -abs(pnl) * 0.1
        else:  # Low volatility
            adjustment = abs(pnl) * 0.05
        
        return adjustment
    
    def calculate_sharpe_ratio_reward(self, returns: list, risk_free_rate: Optional[float] = None) -> float:
        """Calculate reward based on Sharpe ratio"""
        
        if len(returns) < 2:
            return 0.0
        
        returns_array = np.array(returns)
        
        if risk_free_rate is None:
            risk_free_rate = self.risk_free_rate
        
        # Calculate excess returns
        excess_returns = returns_array - (risk_free_rate / self.trading_days_per_year)
        
        # Calculate Sharpe ratio
        if np.std(excess_returns) == 0:
            return 0.0
        
        sharpe = np.mean(excess_returns) / np.std(excess_returns)
        
        # Reward based on Sharpe ratio
        if sharpe > self.sharpe_threshold:
            return 0.2
        elif sharpe > 0.5:
            return 0.1
        elif sharpe > 0:
            return 0.05
        else:
            return -0.1
    
    def calculate_profit_factor_reward(self, gross_wins: float, gross_losses: float) -> float:
        """Calculate reward based on profit factor"""
        
        if gross_losses == 0:
            if gross_wins > 0:
                return 0.3  # Perfect profit factor
            else:
                return 0.0
        
        profit_factor = gross_wins / abs(gross_losses)
        
        # Reward based on profit factor
        if profit_factor > self.profit_factor_target:
            return 0.2
        elif profit_factor > 1.2:
            return 0.1
        elif profit_factor > 1.0:
            return 0.05
        else:
            return -0.1
    
    def get_reward_statistics(self) -> Dict[str, Any]:
        """Get reward statistics"""
        
        if not self.rewards_history:
            return {
                'mean_reward': 0.0,
                'std_reward': 0.0,
                'min_reward': 0.0,
                'max_reward': 0.0,
                'recent_mean': 0.0,
                'trend': 'stable'
            }
        
        rewards_array = np.array(self.rewards_history)
        
        # Overall statistics
        mean_reward = np.mean(rewards_array)
        std_reward = np.std(rewards_array)
        min_reward = np.min(rewards_array)
        max_reward = np.max(rewards_array)
        
        # Recent statistics (last 50 rewards)
        recent_rewards = rewards_array[-50:] if len(rewards_array) >= 50 else rewards_array
        recent_mean = np.mean(recent_rewards)
        
        # Trend analysis
        if len(recent_rewards) >= 10:
            recent_trend = np.mean(recent_rewards[-10:]) - np.mean(recent_rewards[-20:-10]) if len(recent_rewards) >= 20 else 0
            if recent_trend > 0.01:
                trend = 'improving'
            elif recent_trend < -0.01:
                trend = 'declining'
            else:
                trend = 'stable'
        else:
            trend = 'insufficient_data'
        
        return {
            'mean_reward': mean_reward,
            'std_reward': std_reward,
            'min_reward': min_reward,
            'max_reward': max_reward,
            'recent_mean': recent_mean,
            'trend': trend,
            'total_rewards': len(self.rewards_history),
            'last_reward': self.rewards_history[-1] if self.rewards_history else 0.0
        }
    
    def reset_history(self):
        """Reset reward history"""
        self.rewards_history.clear()
        self.pnl_history.clear()
        self.drawdown_history.clear()
        logger.info("Reward history reset")
    
    def get_recent_rewards(self, count: int = 10) -> list:
        """Get recent rewards"""
        return self.rewards_history[-count:] if len(self.rewards_history) >= count else self.rewards_history
    
    def save_reward_history(self, filepath: str):
        """Save reward history to file"""
        try:
            import json
            data = {
                'rewards': self.rewards_history,
                'pnl': self.pnl_history,
                'drawdown': self.drawdown_history,
                'timestamp': datetime.now().isoformat()
            }
            
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Reward history saved to {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to save reward history: {e}")


class MultiObjectiveRewardCalculator(RewardCalculator):
    """Multi-objective reward calculator for complex trading strategies"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Objective weights
        self.objective_weights = {
            'profit': 0.4,      # Profit maximization
            'risk': 0.3,        # Risk minimization
            'consistency': 0.2,   # Consistency preference
            'efficiency': 0.1      # Trading efficiency
        }
    
    def calculate_multi_objective_reward(
        self,
        profit_objective: float,
        risk_objective: float,
        consistency_objective: float,
        efficiency_objective: float,
        **kwargs
    ) -> Dict[str, Any]:
        """Calculate multi-objective reward"""
        
        # Normalize objectives to [0, 1] range
        normalized_profit = self._normalize_objective(profit_objective, higher_is_better=True)
        normalized_risk = self._normalize_objective(risk_objective, higher_is_better=False)
        normalized_consistency = self._normalize_objective(consistency_objective, higher_is_better=True)
        normalized_efficiency = self._normalize_objective(efficiency_objective, higher_is_better=True)
        
        # Weighted combination
        total_reward = (
            self.objective_weights['profit'] * normalized_profit +
            self.objective_weights['risk'] * normalized_risk +
            self.objective_weights['consistency'] * normalized_consistency +
            self.objective_weights['efficiency'] * normalized_efficiency
        )
        
        return {
            'profit_component': normalized_profit * self.objective_weights['profit'],
            'risk_component': normalized_risk * self.objective_weights['risk'],
            'consistency_component': normalized_consistency * self.objective_weights['consistency'],
            'efficiency_component': normalized_efficiency * self.objective_weights['efficiency'],
            'total_reward': total_reward,
            'objectives': {
                'profit': normalized_profit,
                'risk': normalized_risk,
                'consistency': normalized_consistency,
                'efficiency': normalized_efficiency
            }
        }
    
    def _normalize_objective(self, value: float, higher_is_better: bool = True) -> float:
        """Normalize objective value to [0, 1] range"""
        
        # Simple normalization using sigmoid
        if higher_is_better:
            return 1.0 / (1.0 + np.exp(-value))
        else:
            return 1.0 / (1.0 + np.exp(value))
    
    def update_objective_weights(self, weights: Dict[str, float]):
        """Update objective weights"""
        total_weight = sum(weights.values())
        
        if total_weight == 0:
            logger.warning("Sum of objective weights cannot be zero")
            return
        
        # Normalize weights
        self.objective_weights = {
            key: weight / total_weight for key, weight in weights.items()
        }
        
        logger.info(f"Objective weights updated: {self.objective_weights}")
