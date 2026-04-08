"""
State Representation for Reinforcement Learning
Creates comprehensive market state vectors for RL agent
"""

import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class StateBuilder:
    """Builds comprehensive state representations for RL trading"""
    
    def __init__(
        self,
        lookback_periods: List[int] = [5, 10, 20, 50],
        include_time_features: bool = True,
        include_portfolio_features: bool = True,
        include_market_features: bool = True,
        normalize_features: bool = True
    ):
        self.lookback_periods = lookback_periods
        self.include_time_features = include_time_features
        self.include_portfolio_features = include_portfolio_features
        self.include_market_features = include_market_features
        self.normalize_features = normalize_features
        
        # Feature indices for debugging
        self.feature_indices = {}
        current_index = 0
        
        logger.info(f"State Builder initialized with lookback periods: {lookback_periods}")
    
    def build_state(
        self,
        price_data: List[Dict],
        indicators: Dict[str, List],
        portfolio_data: Dict[str, Any],
        market_data: Optional[Dict[str, Any]] = None
    ) -> np.ndarray:
        """Build comprehensive state vector"""
        
        state_features = []
        current_index = 0
        
        try:
            # 1. Price Features
            price_features = self._build_price_features(price_data)
            state_features.extend(price_features)
            self._register_feature_range('price_features', current_index, len(price_features))
            current_index += len(price_features)
            
            # 2. Technical Indicator Features
            indicator_features = self._build_indicator_features(indicators)
            state_features.extend(indicator_features)
            self._register_feature_range('indicator_features', current_index, len(indicator_features))
            current_index += len(indicator_features)
            
            # 3. Portfolio Features
            if self.include_portfolio_features:
                portfolio_features = self._build_portfolio_features(portfolio_data)
                state_features.extend(portfolio_features)
                self._register_feature_range('portfolio_features', current_index, len(portfolio_features))
                current_index += len(portfolio_features)
            
            # 4. Market Features
            if self.include_market_features and market_data:
                market_features = self._build_market_features(market_data)
                state_features.extend(market_features)
                self._register_feature_range('market_features', current_index, len(market_features))
                current_index += len(market_features)
            
            # 5. Time Features
            if self.include_time_features:
                time_features = self._build_time_features()
                state_features.extend(time_features)
                self._register_feature_range('time_features', current_index, len(time_features))
                current_index += len(time_features)
            
            # Convert to numpy array
            state_array = np.array(state_features, dtype=np.float32)
            
            # Handle NaN values
            state_array = np.nan_to_num(state_array, nan=0.0, posinf=1.0, neginf=-1.0)
            
            # Normalize features if requested
            if self.normalize_features:
                state_array = self._normalize_state(state_array)
            
            return state_array
            
        except Exception as e:
            logger.error(f"Error building state: {e}")
            return np.zeros(50, dtype=np.float32)  # Default state size
    
    def _build_price_features(self, price_data: List[Dict]) -> List[float]:
        """Build price-based features"""
        
        if not price_data:
            return [0.0] * (4 * len(self.lookback_periods))
        
        features = []
        current_price = price_data[-1]['close']
        
        for period in self.lookback_periods:
            if len(price_data) >= period:
                recent_data = price_data[-period:]
                
                # Price changes
                opens = [c['open'] for c in recent_data]
                highs = [c['high'] for c in recent_data]
                lows = [c['low'] for c in recent_data]
                closes = [c['close'] for c in recent_data]
                
                # Relative price changes
                price_change = (closes[-1] - closes[0]) / closes[0] if closes[0] != 0 else 0
                
                # Volatility (standard deviation of returns)
                returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
                volatility = np.std(returns) if len(returns) > 1 else 0
                
                # Price position within range
                price_range = max(highs) - min(lows)
                price_position = (current_price - min(lows)) / price_range if price_range > 0 else 0.5
                
                # Momentum
                momentum = (closes[-1] - closes[-min(5, len(closes)-1)]) / closes[-min(5, len(closes)-1)] if len(closes) > 1 else 0
                
                features.extend([price_change, volatility, price_position, momentum])
            else:
                # Pad with zeros if not enough data
                features.extend([0.0, 0.0, 0.0, 0.0])
        
        return features
    
    def _build_indicator_features(self, indicators: Dict[str, List]) -> List[float]:
        """Build technical indicator features"""
        
        features = []
        
        # Moving Averages
        for ma_name in ['ma20', 'ma50', 'ma200']:
            ma_values = indicators.get(ma_name, [])
            if ma_values and len(ma_values) >= 5:
                current_ma = ma_values[-1]
                # Recent values for trend
                recent_ma = ma_values[-5:]
                ma_trend = (recent_ma[-1] - recent_ma[0]) / recent_ma[0] if recent_ma[0] != 0 else 0
                ma_position = (ma_values[-1] - ma_values[-min(20, len(ma_values)-1)]) / ma_values[-min(20, len(ma_values)-1)] if len(ma_values) > 20 and ma_values[-min(20, len(ma_values)-1)] != 0 else 0
                
                features.extend([ma_trend, ma_position])
            else:
                features.extend([0.0, 0.0])
        
        # RSI
        rsi_values = indicators.get('rsi', [])
        if rsi_values and len(rsi_values) >= 5:
            current_rsi = rsi_values[-1]
            rsi_change = current_rsi - rsi_values[-min(5, len(rsi_values)-1)] if len(rsi_values) > 1 else 0
            rsi_overbought = 1.0 if current_rsi > 70 else 0.0
            rsi_oversold = 1.0 if current_rsi < 30 else 0.0
            
            features.extend([current_rsi/50, rsi_change/50, rsi_overbought, rsi_oversold])
        else:
            features.extend([0.0, 0.0, 0.0, 0.0])
        
        # MACD
        macd_data = indicators.get('macd', {})
        if macd_data and all(k in macd_data for k in ['macd', 'signal', 'histogram']):
            macd_line = macd_data['macd'][-5:] if len(macd_data['macd']) >= 5 else []
            signal_line = macd_data['signal'][-5:] if len(macd_data['signal']) >= 5 else []
            histogram = macd_data['histogram'][-5:] if len(macd_data['histogram']) >= 5 else []
            
            if macd_line and signal_line and histogram:
                macd_trend = (macd_line[-1] - macd_line[0]) / abs(macd_line[0]) if macd_line[0] != 0 else 0
                macd_cross = 1.0 if (macd_line[-1] > signal_line[-1]) != (macd_line[-2] > signal_line[-2]) else 0.0
                macd_divergence = histogram[-1] if histogram else 0.0
                
                features.extend([macd_trend, macd_cross, macd_divergence])
            else:
                features.extend([0.0, 0.0, 0.0])
        else:
            features.extend([0.0, 0.0, 0.0])
        
        # Bollinger Bands
        bb_data = indicators.get('bollinger', {})
        if bb_data and all(k in bb_data for k in ['upper', 'middle', 'lower']):
            upper = bb_data['upper'][-5:] if len(bb_data['upper']) >= 5 else []
            middle = bb_data['middle'][-5:] if len(bb_data['middle']) >= 5 else []
            lower = bb_data['lower'][-5:] if len(bb_data['lower']) >= 5 else []
            
            if upper and middle and lower:
                bb_width = (upper[-1] - lower[-1]) / middle[-1] if middle[-1] != 0 else 0
                bb_position = (middle[-1] - lower[-1]) / (upper[-1] - lower[-1]) if (upper[-1] - lower[-1]) != 0 else 0.5
                bb_squeeze = 1.0 if bb_width < 0.02 else 0.0  # Narrow bands
                
                features.extend([bb_width, bb_position, bb_squeeze])
            else:
                features.extend([0.0, 0.0, 0.0])
        else:
            features.extend([0.0, 0.0, 0.0])
        
        return features
    
    def _build_portfolio_features(self, portfolio_data: Dict[str, Any]) -> List[float]:
        """Build portfolio-related features"""
        
        features = []
        
        # Position information
        open_positions = portfolio_data.get('open_positions', 0)
        max_positions = portfolio_data.get('max_positions', 1)
        position_utilization = open_positions / max_positions
        
        # P&L information
        total_pnl = portfolio_data.get('total_pnl', 0.0)
        initial_balance = portfolio_data.get('initial_balance', 10000.0)
        pnl_ratio = total_pnl / initial_balance
        
        # Drawdown information
        max_drawdown = portfolio_data.get('max_drawdown', 0.0)
        current_drawdown = portfolio_data.get('current_drawdown', 0.0)
        
        # Consecutive trades
        consecutive_wins = portfolio_data.get('consecutive_wins', 0)
        consecutive_losses = portfolio_data.get('consecutive_losses', 0)
        
        # Risk metrics
        win_rate = portfolio_data.get('win_rate', 0.0)
        avg_trade_pnl = portfolio_data.get('avg_trade_pnl', 0.0)
        sharpe_ratio = portfolio_data.get('sharpe_ratio', 0.0)
        
        features.extend([
            position_utilization,
            pnl_ratio,
            max_drawdown,
            current_drawdown,
            consecutive_wins / 10,  # Normalize
            consecutive_losses / 10,  # Normalize
            win_rate,
            avg_trade_pnl / 100,  # Normalize
            sharpe_ratio / 5,  # Normalize (typical Sharpe range 0-5)
        ])
        
        return features
    
    def _build_market_features(self, market_data: Dict[str, Any]) -> List[float]:
        """Build market condition features"""
        
        features = []
        
        # Spread information
        current_spread = market_data.get('spread', 0.0)
        avg_spread = market_data.get('avg_spread', 0.0)
        spread_ratio = current_spread / avg_spread if avg_spread > 0 else 1.0
        
        # Volume information
        current_volume = market_data.get('volume', 0.0)
        avg_volume = market_data.get('avg_volume', 1.0)
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        # Volatility
        current_volatility = market_data.get('volatility', 0.0)
        avg_volatility = market_data.get('avg_volatility', 0.01)
        volatility_ratio = current_volatility / avg_volatility if avg_volatility > 0 else 1.0
        
        # Market session
        current_hour = datetime.now().hour
        is_london_session = 1.0 if 8 <= current_hour <= 16 else 0.0
        is_ny_session = 1.0 if 13 <= current_hour <= 22 else 0.0
        is_asian_session = 1.0 if 0 <= current_hour <= 7 else 0.0
        
        # Market regime
        market_regime = market_data.get('market_regime', 'unknown')
        regime_trending = 1.0 if market_regime == 'trending' else 0.0
        regime_ranging = 1.0 if market_regime == 'ranging' else 0.0
        regime_volatile = 1.0 if market_regime == 'volatile' else 0.0
        
        features.extend([
            spread_ratio,
            volume_ratio,
            volatility_ratio,
            is_london_session,
            is_ny_session,
            is_asian_session,
            regime_trending,
            regime_ranging,
            regime_volatile
        ])
        
        return features
    
    def _build_time_features(self) -> List[float]:
        """Build time-based features"""
        
        features = []
        
        now = datetime.now()
        
        # Time of day (cyclical encoding)
        hour_sin = np.sin(2 * np.pi * now.hour / 24)
        hour_cos = np.cos(2 * np.pi * now.hour / 24)
        
        # Day of week (cyclical encoding)
        day_sin = np.sin(2 * np.pi * now.weekday() / 7)
        day_cos = np.cos(2 * np.pi * now.weekday() / 7)
        
        # Month of year (cyclical encoding)
        month_sin = np.sin(2 * np.pi * now.month / 12)
        month_cos = np.cos(2 * np.pi * now.month / 12)
        
        # Trading session
        is_trading_hours = 1.0 if 8 <= now.hour <= 22 else 0.0
        
        # Day type (weekday/weekend)
        is_weekday = 1.0 if now.weekday() < 5 else 0.0
        
        features.extend([
            hour_sin, hour_cos,
            day_sin, day_cos,
            month_sin, month_cos,
            is_trading_hours,
            is_weekday
        ])
        
        return features
    
    def _normalize_state(self, state_array: np.ndarray) -> np.ndarray:
        """Normalize state features"""
        
        try:
            # Avoid division by zero
            non_zero_indices = np.where(state_array != 0)[0]
            
            if len(non_zero_indices) > 0:
                # Z-score normalization for non-zero features
                mean_val = np.mean(state_array[non_zero_indices])
                std_val = np.std(state_array[non_zero_indices])
                
                if std_val > 0:
                    normalized = (state_array - mean_val) / std_val
                    # Clip extreme values
                    normalized = np.clip(normalized, -3, 3)
                else:
                    normalized = state_array
            else:
                normalized = state_array
            
            return normalized
            
        except Exception as e:
            logger.error(f"Error normalizing state: {e}")
            return state_array
    
    def _register_feature_range(self, feature_type: str, start_index: int, length: int):
        """Register feature range for debugging"""
        self.feature_indices[feature_type] = {
            'start': start_index,
            'end': start_index + length - 1,
            'length': length
        }
    
    def get_feature_info(self) -> Dict[str, Any]:
        """Get information about features"""
        
        total_features = sum(info['length'] for info in self.feature_indices.values())
        
        return {
            'feature_indices': self.feature_indices,
            'total_features': total_features,
            'lookback_periods': self.lookback_periods,
            'include_time_features': self.include_time_features,
            'include_portfolio_features': self.include_portfolio_features,
            'include_market_features': self.include_market_features,
            'normalize_features': self.normalize_features
        }
    
    def explain_state(self, state_array: np.ndarray, top_k: int = 5) -> List[Dict[str, Any]]:
        """Explain which features are most influential in current state"""
        
        explanations = []
        
        # Find features with highest absolute values
        abs_features = np.abs(state_array)
        top_indices = np.argsort(abs_features)[-top_k:][::-1]  # Top k in descending order
        
        for i, idx in enumerate(top_indices):
            feature_name = self._get_feature_name(idx)
            feature_value = state_array[idx]
            importance = abs_features[idx] / np.max(abs_features) if np.max(abs_features) > 0 else 0
            
            explanations.append({
                'rank': i + 1,
                'index': idx,
                'feature_name': feature_name,
                'value': float(feature_value),
                'importance': float(importance),
                'interpretation': self._interpret_feature(feature_name, feature_value)
            })
        
        return explanations
    
    def _get_feature_name(self, index: int) -> str:
        """Get feature name by index"""
        
        for feature_type, info in self.feature_indices.items():
            if info['start'] <= index <= info['end']:
                return f"{feature_type}_{index - info['start']}"
        
        return f"unknown_{index}"
    
    def _interpret_feature(self, feature_name: str, value: float) -> str:
        """Interpret feature value"""
        
        if 'price_change' in feature_name:
            if value > 0.01:
                return "Strong upward price movement"
            elif value > 0.005:
                return "Moderate upward price movement"
            elif value < -0.01:
                return "Strong downward price movement"
            elif value < -0.005:
                return "Moderate downward price movement"
            else:
                return "Price stability"
        
        elif 'rsi' in feature_name:
            if value > 1.4:
                return "Overbought condition"
            elif value < 0.6:
                return "Oversold condition"
            else:
                return "Neutral RSI"
        
        elif 'position_utilization' in feature_name:
            if value > 0.8:
                return "High position utilization"
            elif value > 0.5:
                return "Moderate position utilization"
            else:
                return "Low position utilization"
        
        elif 'drawdown' in feature_name:
            if value > 0.1:
                return "High drawdown risk"
            elif value > 0.05:
                return "Moderate drawdown risk"
            else:
                return "Low drawdown risk"
        
        elif 'volatility' in feature_name:
            if value > 1.5:
                return "High volatility"
            elif value > 1.0:
                return "Moderate volatility"
            else:
                return "Low volatility"
        
        else:
            return f"Feature value: {value:.3f}"


class StateHistory:
    """Manages state history for pattern recognition"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.state_history = []
        self.timestamp_history = []
    
    def add_state(self, state: np.ndarray, timestamp: Optional[datetime] = None):
        """Add state to history"""
        
        if timestamp is None:
            timestamp = datetime.now()
        
        self.state_history.append(state.copy())
        self.timestamp_history.append(timestamp)
        
        # Maintain maximum history
        if len(self.state_history) > self.max_history:
            self.state_history.pop(0)
            self.timestamp_history.pop(0)
    
    def get_recent_states(self, count: int = 10) -> List[np.ndarray]:
        """Get recent states"""
        
        recent_count = min(count, len(self.state_history))
        return self.state_history[-recent_count:]
    
    def detect_patterns(self, window_size: int = 50) -> Dict[str, Any]:
        """Detect patterns in state history"""
        
        if len(self.state_history) < window_size:
            return {'patterns': [], 'similarities': []}
        
        patterns = []
        current_window = self.state_history[-window_size:]
        
        # Look for similar patterns in history
        for i in range(len(self.state_history) - window_size):
            historical_window = self.state_history[i:i + window_size]
            
            # Calculate similarity (cosine similarity)
            similarity = self._calculate_similarity(current_window, historical_window)
            
            if similarity > 0.8:  # High similarity threshold
                patterns.append({
                    'start_index': i,
                    'similarity': similarity,
                    'timestamp': self.timestamp_history[i],
                    'next_outcome': self._get_next_outcome(i + window_size)
                })
        
        # Sort by similarity
        patterns.sort(key=lambda x: x['similarity'], reverse=True)
        
        return {
            'patterns': patterns[:5],  # Top 5 most similar patterns
            'pattern_count': len(patterns),
            'current_window_size': window_size
        }
    
    def _calculate_similarity(self, window1: List[np.ndarray], window2: List[np.ndarray]) -> float:
        """Calculate similarity between two state windows"""
        
        try:
            # Flatten windows for comparison
            flat1 = np.array([state.flatten() for state in window1])
            flat2 = np.array([state.flatten() for state in window2])
            
            # Calculate cosine similarity
            dot_product = np.dot(flat1.flatten(), flat2.flatten())
            norm1 = np.linalg.norm(flat1.flatten())
            norm2 = np.linalg.norm(flat2.flatten())
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            return similarity
            
        except Exception as e:
            logger.error(f"Error calculating similarity: {e}")
            return 0.0
    
    def _get_next_outcome(self, index: int) -> Optional[str]:
        """Get outcome after a specific state index"""
        
        if index + 1 >= len(self.state_history):
            return None
        
        # Simple outcome based on next state change
        if index + 1 < len(self.state_history):
            current_state = self.state_history[index]
            next_state = self.state_history[index + 1]
            
            # Calculate state change magnitude
            state_change = np.linalg.norm(next_state - current_state)
            
            if state_change > 0.1:
                return "significant_change"
            elif state_change > 0.05:
                return "moderate_change"
            else:
                return "minor_change"
        
        return None
