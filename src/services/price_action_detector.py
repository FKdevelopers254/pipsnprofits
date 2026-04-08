"""
Advanced Price Action Detection Service
Detects FVG, Supply/Demand zones, BOS, and CHoCH patterns
"""

import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class FairValueGap:
    """Fair Value Gap data structure"""
    type: str  # 'bullish' or 'bearish'
    start_time: datetime
    end_time: datetime
    top_price: float
    bottom_price: float
    is_inverse: bool
    is_filled: bool
    candles_since: int
    index: int

@dataclass
class SupplyDemandZone:
    """Supply/Demand zone data structure"""
    type: str  # 'supply' or 'demand'
    start_time: datetime
    end_time: Optional[datetime]
    base_price: float
    top_price: float
    bottom_price: float
    is_active: bool
    touches: int
    index: int
    timeframe: str

@dataclass
class BreakOfStructure:
    """Break of Structure / Change of Character data structure"""
    type: str  # 'bos' or 'choch'
    direction: str  # 'bullish' or 'bearish'
    time: datetime
    price: float
    previous_swing: float
    index: int
    timeframe: str
    strength: float = 50.0  # 0-100 strength score
    break_magnitude: float = 0.0  # Price distance of break
    volume_confirmed: bool = False  # Whether volume supports the break
    order_block_index: Optional[int] = None  # Index of associated order block
    fvg_confluence: bool = False  # Whether CHoCH aligns with FVG
    fvg_aligned_indices: List[int] = None  # Indices of aligned FVGs
    confluence_score: float = 0.0  # Combined score of all confluences (0-100)

    def __post_init__(self):
        if self.fvg_aligned_indices is None:
            self.fvg_aligned_indices = []

@dataclass
class OrderBlock:
    """Order Block - institutional order zone causing reversal"""
    type: str  # 'bullish' or 'bearish'
    start_time: datetime
    index: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    strength: float  # 0-100 based on candle characteristics
    is_active: bool
    timeframe: str

@dataclass
class LiquiditySweep:
    """Liquidity Sweep - stop hunt before reversal"""
    type: str  # 'high' or 'low' (which side was swept)
    direction: str  # 'bullish' or 'bearish' (reversal direction)
    time: datetime
    sweep_price: float  # The extreme price that swept liquidity
    swing_price: float  # The swing high/low that was swept
    choch_index: int  # Index of associated CHoCH
    index: int  # Index of sweep candle
    strength: float  # 0-100 based on sweep quality
    timeframe: str

@dataclass
class TradeSuggestion:
    """Trade suggestion based on CHoCH confluence"""
    type: str  # 'buy' or 'sell'
    choch_index: int  # Index of triggering CHoCH
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    confluence_score: float
    reasons: List[str]  # Why this trade is suggested
    timeframe: str
    timestamp: datetime
    urgency: str  # 'immediate', 'watch', 'low' based on confluence score


class PriceActionDetector:
    """Detects advanced price action patterns"""
    
    def __init__(self, min_fvg_size: float = 0.1, zone_lookback: int = 50):
        self.min_fvg_size = min_fvg_size
        self.zone_lookback = zone_lookback
        self.fvgs: List[FairValueGap] = []
        self.zones: List[SupplyDemandZone] = []
        self.bos_points: List[BreakOfStructure] = []
        self.order_blocks: List[OrderBlock] = []
        self.liquidity_sweeps: List[LiquiditySweep] = []
        self.trade_suggestions: List[TradeSuggestion] = []
        
    def detect_all_patterns(self, candles: List[Dict], timeframe: str = "H1") -> Dict[str, Any]:
        """Detect all price action patterns and generate trade suggestions"""
        
        # Detect FVGs
        self.fvgs = self.detect_fair_value_gaps(candles)
        
        # Detect Supply/Demand zones
        self.zones = self.detect_supply_demand_zones(candles, timeframe)
        
        # Detect BOS and CHoCH (with order block and liquidity sweep detection)
        self.bos_points, self.order_blocks, self.liquidity_sweeps = self.detect_structure_with_sweeps(candles, timeframe)
        
        # Generate trade suggestions based on high-confluence CHoCH patterns
        self.trade_suggestions = self.generate_trade_suggestions(candles, timeframe)
        
        # Get swing points for structure visualization
        swing_points = self._find_swing_points(candles)
        
        return {
            'fvgs': self.fvgs,
            'zones': self.zones,
            'bos': self.bos_points,
            'order_blocks': self.order_blocks,
            'liquidity_sweeps': self.liquidity_sweeps,
            'trade_suggestions': self.trade_suggestions,
            'swing_points': swing_points,
            'summary': {
                'fvg_count': len(self.fvgs),
                'active_fvgs': len([f for f in self.fvgs if not f.is_filled]),
                'supply_zones': len([z for z in self.zones if z.type == 'supply' and z.is_active]),
                'demand_zones': len([z for z in self.zones if z.type == 'demand' and z.is_active]),
                'bos_count': len([b for b in self.bos_points if b.type == 'bos']),
                'choch_count': len([b for b in self.bos_points if b.type == 'choch']),
                'order_blocks': len(self.order_blocks),
                'active_obs': len([ob for ob in self.order_blocks if ob.is_active]),
                'liquidity_sweeps': len(self.liquidity_sweeps),
                'trade_suggestions': len(self.trade_suggestions),
                'high_urgency_alerts': len([t for t in self.trade_suggestions if t.urgency == 'immediate']),
                'swing_highs': len([s for s in swing_points if s['type'] == 'high']),
                'swing_lows': len([s for s in swing_points if s['type'] == 'low']),
                'trend_strength': self._calculate_trend_strength(candles),
                'trend_direction': self._determine_trend_direction(candles)
            }
        }
    
    def detect_fair_value_gaps(self, candles: List[Dict]) -> List[FairValueGap]:
        """Detect Fair Value Gaps (FVG) - both regular and inverse"""
        fvgs = []
        
        if len(candles) < 3:
            return fvgs
        
        for i in range(2, len(candles)):
            prev2 = candles[i-2]  # Candle 2 candles ago
            prev1 = candles[i-1]    # Previous candle
            current = candles[i]    # Current candle
            
            # Bullish FVG: Current low > prev1 high
            if current['low'] > prev1['high']:
                gap_size = current['low'] - prev1['high']
                if gap_size >= self.min_fvg_size:
                    fvg = FairValueGap(
                        type='bullish',
                        start_time=prev1['time'],
                        end_time=current['time'],
                        top_price=current['low'],
                        bottom_price=prev1['high'],
                        is_inverse=False,
                        is_filled=self._is_fvg_filled(fvgs, current['low'], prev1['high'], i, candles),
                        candles_since=i - (i-2),
                        index=i
                    )
                    fvgs.append(fvg)
            
            # Bearish FVG: Current high < prev1 low
            elif current['high'] < prev1['low']:
                gap_size = prev1['low'] - current['high']
                if gap_size >= self.min_fvg_size:
                    fvg = FairValueGap(
                        type='bearish',
                        start_time=prev1['time'],
                        end_time=current['time'],
                        top_price=prev1['low'],
                        bottom_price=current['high'],
                        is_inverse=False,
                        is_filled=self._is_fvg_filled(fvgs, prev1['low'], current['high'], i, candles),
                        candles_since=i - (i-2),
                        index=i
                    )
                    fvgs.append(fvg)
            
            # Inverse FVG detection
            # Inverse Bullish FVG: prev2 low > prev1 high (bearish gap becomes support)
            if prev2['low'] > prev1['high']:
                # Check if this was a bearish gap that's now being reclaimed
                gap_size = prev2['low'] - prev1['high']
                if gap_size >= self.min_fvg_size:
                    # Check if current candle is filling/reclaiming this gap
                    if current['close'] > prev2['low'] or current['high'] > prev1['high']:
                        fvg = FairValueGap(
                            type='bullish',
                            start_time=prev1['time'],
                            end_time=current['time'],
                            top_price=prev2['low'],
                            bottom_price=prev1['high'],
                            is_inverse=True,
                            is_filled=True,  # Being filled now
                            candles_since=2,
                            index=i
                        )
                        fvgs.append(fvg)
            
            # Inverse Bearish FVG: prev2 high < prev1 low (bullish gap becomes resistance)
            elif prev2['high'] < prev1['low']:
                gap_size = prev1['low'] - prev2['high']
                if gap_size >= self.min_fvg_size:
                    # Check if current candle is filling/reclaiming this gap
                    if current['close'] < prev2['high'] or current['low'] < prev1['low']:
                        fvg = FairValueGap(
                            type='bearish',
                            start_time=prev1['time'],
                            end_time=current['time'],
                            top_price=prev1['low'],
                            bottom_price=prev2['high'],
                            is_inverse=True,
                            is_filled=True,  # Being filled now
                            candles_since=2,
                            index=i
                        )
                        fvgs.append(fvg)
        
        return fvgs
    
    def _is_fvg_filled(self, existing_fvgs: List[FairValueGap], top: float, bottom: float, 
                       current_idx: int, candles: List[Dict]) -> bool:
        """Check if an FVG has been filled by subsequent price action"""
        for candle in candles[current_idx+1:]:
            # For bullish FVG, check if price comes back down into the gap
            if candle['low'] <= top and candle['high'] >= bottom:
                return True
        return False
    
    def detect_supply_demand_zones(self, candles: List[Dict], timeframe: str = "H1") -> List[SupplyDemandZone]:
        """Detect Supply and Demand zones using price action"""
        zones = []
        
        if len(candles) < 5:
            return zones
        
        # Find swing highs and lows
        swing_points = self._find_swing_points(candles)
        
        for i, point in enumerate(swing_points):
            idx = point['index']
            if idx < 3 or idx >= len(candles) - 3:
                continue
            
            if point['type'] == 'high':
                # Check for supply zone formation
                # Strong rejection from high with follow-through
                if self._is_supply_zone(candles, idx):
                    zone = SupplyDemandZone(
                        type='supply',
                        start_time=candles[idx]['time'],
                        end_time=None,
                        base_price=point['price'],
                        top_price=point['price'] * 1.002,  # Small buffer above
                        bottom_price=min(candles[idx]['open'], candles[idx]['close']),
                        is_active=True,
                        touches=0,
                        index=idx,
                        timeframe=timeframe
                    )
                    zones.append(zone)
            
            elif point['type'] == 'low':
                # Check for demand zone formation
                # Strong rejection from low with follow-through
                if self._is_demand_zone(candles, idx):
                    zone = SupplyDemandZone(
                        type='demand',
                        start_time=candles[idx]['time'],
                        end_time=None,
                        base_price=point['price'],
                        top_price=max(candles[idx]['open'], candles[idx]['close']),
                        bottom_price=point['price'] * 0.998,  # Small buffer below
                        is_active=True,
                        touches=0,
                        index=idx,
                        timeframe=timeframe
                    )
                    zones.append(zone)
        
        # Update zone status based on price action
        zones = self._update_zone_status(zones, candles)
        
        return zones
    
    def _find_swing_points(self, candles: List[Dict]) -> List[Dict]:
        """Find swing highs and lows in price data"""
        swing_points = []
        
        for i in range(2, len(candles) - 2):
            prev2 = candles[i-2]
            prev1 = candles[i-1]
            current = candles[i]
            next1 = candles[i+1]
            next2 = candles[i+2]
            
            # Swing High: Current high > prev1 high and prev2 high, and > next1 high and next2 high
            if (current['high'] > prev1['high'] and 
                current['high'] > prev2['high'] and
                current['high'] > next1['high'] and 
                current['high'] > next2['high']):
                swing_points.append({
                    'type': 'high',
                    'price': current['high'],
                    'index': i,
                    'time': current['time']
                })
            
            # Swing Low: Current low < prev1 low and prev2 low, and < next1 low and next2 low
            elif (current['low'] < prev1['low'] and 
                  current['low'] < prev2['low'] and
                  current['low'] < next1['low'] and 
                  current['low'] < next2['low']):
                swing_points.append({
                    'type': 'low',
                    'price': current['low'],
                    'index': i,
                    'time': current['time']
                })
        
        return swing_points
    
    def _is_supply_zone(self, candles: List[Dict], idx: int) -> bool:
        """Check if current candle forms a supply zone"""
        if idx < 1 or idx >= len(candles) - 1:
            return False
        
        current = candles[idx]
        prev = candles[idx-1]
        next_candle = candles[idx+1]
        
        # Criteria for supply zone:
        # 1. Strong bullish candle followed by strong rejection
        # 2. Or consolidation at highs followed by breakdown
        
        # Check for strong rejection (long upper wick)
        body_size = abs(current['close'] - current['open'])
        upper_wick = current['high'] - max(current['open'], current['close'])
        
        if upper_wick > body_size * 1.5:  # Long upper wick
            # Check if next candle confirms rejection
            if next_candle['close'] < current['close']:
                return True
        
        # Check for double top or lower high pattern
        if idx >= 2:
            prev2 = candles[idx-2]
            if current['high'] <= prev2['high'] and current['high'] > prev['high']:
                # Lower high or double top
                return True
        
        return False
    
    def _is_demand_zone(self, candles: List[Dict], idx: int) -> bool:
        """Check if current candle forms a demand zone"""
        if idx < 1 or idx >= len(candles) - 1:
            return False
        
        current = candles[idx]
        prev = candles[idx-1]
        next_candle = candles[idx+1]
        
        # Criteria for demand zone:
        # 1. Strong bearish candle followed by strong rejection
        # 2. Or consolidation at lows followed by breakout
        
        # Check for strong rejection (long lower wick)
        body_size = abs(current['close'] - current['open'])
        lower_wick = min(current['open'], current['close']) - current['low']
        
        if lower_wick > body_size * 1.5:  # Long lower wick
            # Check if next candle confirms rejection
            if next_candle['close'] > current['close']:
                return True
        
        # Check for double bottom or higher low pattern
        if idx >= 2:
            prev2 = candles[idx-2]
            if current['low'] >= prev2['low'] and current['low'] < prev['low']:
                # Higher low or double bottom
                return True
        
        return False
    
    def _update_zone_status(self, zones: List[SupplyDemandZone], candles: List[Dict]) -> List[SupplyDemandZone]:
        """Update zone status based on price action"""
        updated_zones = []
        
        for zone in zones:
            if zone.index >= len(candles):
                continue
            
            # Count touches and check if zone is broken
            touches = 0
            for i in range(zone.index + 1, len(candles)):
                candle = candles[i]
                
                # Check if price touches the zone
                if zone.type == 'supply':
                    if candle['high'] >= zone.bottom_price and candle['low'] <= zone.top_price:
                        touches += 1
                    # Check if zone is broken (price closes above supply zone)
                    if candle['close'] > zone.top_price * 1.005:  # 0.5% buffer
                        zone.is_active = False
                        zone.end_time = candle['time']
                        break
                
                elif zone.type == 'demand':
                    if candle['low'] <= zone.top_price and candle['high'] >= zone.bottom_price:
                        touches += 1
                    # Check if zone is broken (price closes below demand zone)
                    if candle['close'] < zone.bottom_price * 0.995:  # 0.5% buffer
                        zone.is_active = False
                        zone.end_time = candle['time']
                        break
            
            zone.touches = touches
            updated_zones.append(zone)
        
        return updated_zones
    
    def detect_break_of_structure(self, candles: List[Dict], timeframe: str = "H1") -> List[BreakOfStructure]:
        """Detect Break of Structure (BOS) and Change of Character (CHoCH) with strength analysis"""
        bos_points = []
        
        if len(candles) < 10:
            return bos_points
        
        # Find swing points for structure analysis
        swing_points = self._find_swing_points(candles)
        
        if len(swing_points) < 3:
            return bos_points
        
        # Analyze structure breaks
        for i in range(2, len(swing_points)):
            current_swing = swing_points[i]
            prev_swing = swing_points[i-1]
            prev2_swing = swing_points[i-2]
            
            # Get candle data for analysis
            current_candle = candles[current_swing['index']]
            
            # Determine market structure
            if prev_swing['type'] == 'high' and prev2_swing['type'] == 'low':
                # Bullish structure: higher highs, higher lows expected
                
                # BOS: Price breaks above previous swing high
                if current_swing['type'] == 'high':
                    break_magnitude = abs(current_swing['price'] - prev_swing['price'])
                    strength = self._calculate_break_strength(
                        candles, current_swing['index'], prev_swing['index'], 
                        'bullish', break_magnitude
                    )
                    
                    if current_swing['price'] > prev_swing['price']:
                        bos = BreakOfStructure(
                            type='bos',
                            direction='bullish',
                            time=current_candle['time'],
                            price=current_swing['price'],
                            previous_swing=prev_swing['price'],
                            index=current_swing['index'],
                            timeframe=timeframe,
                            strength=strength,
                            break_magnitude=break_magnitude,
                            volume_confirmed=strength > 60
                        )
                        bos_points.append(bos)
                    
                    # CHoCH: Price fails to make higher high, makes lower high
                    elif current_swing['price'] < prev_swing['price']:
                        bos = BreakOfStructure(
                            type='choch',
                            direction='bearish',
                            time=current_candle['time'],
                            price=current_swing['price'],
                            previous_swing=prev_swing['price'],
                            index=current_swing['index'],
                            timeframe=timeframe,
                            strength=strength,
                            break_magnitude=break_magnitude,
                            volume_confirmed=strength > 60
                        )
                        bos_points.append(bos)
            
            elif prev_swing['type'] == 'low' and prev2_swing['type'] == 'high':
                # Bearish structure: lower lows, lower highs expected
                
                # BOS: Price breaks below previous swing low
                if current_swing['type'] == 'low':
                    break_magnitude = abs(current_swing['price'] - prev_swing['price'])
                    strength = self._calculate_break_strength(
                        candles, current_swing['index'], prev_swing['index'],
                        'bearish', break_magnitude
                    )
                    
                    if current_swing['price'] < prev_swing['price']:
                        bos = BreakOfStructure(
                            type='bos',
                            direction='bearish',
                            time=current_candle['time'],
                            price=current_swing['price'],
                            previous_swing=prev_swing['price'],
                            index=current_swing['index'],
                            timeframe=timeframe,
                            strength=strength,
                            break_magnitude=break_magnitude,
                            volume_confirmed=strength > 60
                        )
                        bos_points.append(bos)
                    
                    # CHoCH: Price fails to make lower low, makes higher low
                    elif current_swing['price'] > prev_swing['price']:
                        bos = BreakOfStructure(
                            type='choch',
                            direction='bullish',
                            time=current_candle['time'],
                            price=current_swing['price'],
                            previous_swing=prev_swing['price'],
                            index=current_swing['index'],
                            timeframe=timeframe,
                            strength=strength,
                            break_magnitude=break_magnitude,
                            volume_confirmed=strength > 60
                        )
                        bos_points.append(bos)
        
        return bos_points
    
    def _calculate_break_strength(self, candles: List[Dict], break_idx: int, 
                                   swing_idx: int, direction: str, magnitude: float) -> float:
        """Calculate the strength of a structure break (0-100)"""
        if break_idx >= len(candles) or swing_idx >= len(candles):
            return 50.0
        
        strength = 50.0  # Base strength
        
        # 1. Momentum factor (0-30 points)
        break_candle = candles[break_idx]
        body_size = abs(break_candle['close'] - break_candle['open'])
        range_size = break_candle['high'] - break_candle['low']
        
        if range_size > 0:
            momentum = (body_size / range_size) * 30
            strength += momentum
        
        # 2. Volume confirmation (0-25 points)
        if 'volume' in break_candle and break_idx > 0:
            current_vol = break_candle['volume']
            # Compare to average of last 5 candles
            start_idx = max(0, break_idx - 5)
            avg_volume = sum(candles[j].get('volume', 0) for j in range(start_idx, break_idx)) / max(1, break_idx - start_idx)
            
            if avg_volume > 0:
                vol_ratio = current_vol / avg_volume
                if vol_ratio > 2.0:
                    strength += 25  # Very high volume
                elif vol_ratio > 1.5:
                    strength += 15  # Above average
                elif vol_ratio > 1.0:
                    strength += 5   # Normal
        
        # 3. Break magnitude (0-25 points)
        # Larger breaks = stronger signals
        if break_idx > 0:
            avg_range = sum(candles[j]['high'] - candles[j]['low'] 
                          for j in range(max(0, break_idx-10), break_idx)) / 10
            if avg_range > 0:
                magnitude_score = min(25, (magnitude / avg_range) * 10)
                strength += magnitude_score
        
        # 4. Follow-through (0-20 points)
        if break_idx < len(candles) - 1:
            next_candle = candles[break_idx + 1]
            if direction == 'bullish' and next_candle['close'] > break_candle['close']:
                strength += 20
            elif direction == 'bearish' and next_candle['close'] < break_candle['close']:
                strength += 20
        
        return min(100, max(0, strength))
    
    def detect_structure_with_sweeps(self, candles: List[Dict], timeframe: str = "H1") -> Tuple[List[BreakOfStructure], List[OrderBlock], List[LiquiditySweep]]:
        """Detect BOS/CHoCH with Order Blocks, Liquidity Sweeps, and FVG Confluence - Smart Money Concept"""
        bos_points = []
        order_blocks = []
        liquidity_sweeps = []
        
        if len(candles) < 10:
            return bos_points, order_blocks, liquidity_sweeps
        
        # Find swing points for structure analysis
        swing_points = self._find_swing_points(candles)
        
        if len(swing_points) < 3:
            return bos_points, order_blocks, liquidity_sweeps
        
        # Detect FVGs for confluence analysis
        fvgs = self.detect_fair_value_gaps(candles)
        active_fvgs = [f for f in fvgs if not f.is_filled]
        
        # Analyze structure breaks
        for i in range(2, len(swing_points)):
            current_swing = swing_points[i]
            prev_swing = swing_points[i-1]
            prev2_swing = swing_points[i-2]
            
            current_candle = candles[current_swing['index']]
            
            # Determine market structure
            if prev_swing['type'] == 'high' and prev2_swing['type'] == 'low':
                # Bullish structure: higher highs, higher lows expected
                
                if current_swing['type'] == 'high':
                    break_magnitude = abs(current_swing['price'] - prev_swing['price'])
                    strength = self._calculate_break_strength(
                        candles, current_swing['index'], prev_swing['index'], 
                        'bullish', break_magnitude
                    )
                    
                    # Check for liquidity sweep before bearish CHoCH
                    sweep = None
                    ob_index = None
                    fvg_aligned = []
                    confluence_score = strength
                    
                    if current_swing['price'] < prev_swing['price']:
                        # Bearish CHoCH - check for sweep of previous swing high
                        sweep = self._detect_liquidity_sweep(
                            candles, current_swing['index'], prev_swing['index'], 
                            prev_swing['price'], 'high', 'bearish'
                        )
                        if sweep:
                            liquidity_sweeps.append(sweep)
                            confluence_score += 15  # Liquidity sweep adds confluence
                        
                        # Find bearish order block
                        ob_index = self._find_order_block(
                            candles, current_swing['index'], prev_swing['index'], 'bearish'
                        )
                        if ob_index is not None:
                            ob = self._create_order_block(candles, ob_index, 'bearish', timeframe)
                            if ob:
                                order_blocks.append(ob)
                                confluence_score += 10  # Order block adds confluence
                        
                        # Check FVG confluence - look for bearish FVGs near CHoCH
                        fvg_aligned = self._check_fvg_confluence(
                            active_fvgs, current_swing['price'], 'bearish'
                        )
                        if fvg_aligned:
                            confluence_score += 20  # FVG alignment adds significant confluence
                    
                    if current_swing['price'] > prev_swing['price']:
                        # Bullish BOS
                        bos = BreakOfStructure(
                            type='bos', direction='bullish',
                            time=current_candle['time'], price=current_swing['price'],
                            previous_swing=prev_swing['price'],
                            index=current_swing['index'], timeframe=timeframe,
                            strength=strength, break_magnitude=break_magnitude,
                            volume_confirmed=strength > 60, order_block_index=None,
                            fvg_confluence=False, fvg_aligned_indices=[],
                            confluence_score=strength
                        )
                        bos_points.append(bos)
                    elif current_swing['price'] < prev_swing['price']:
                        # Bearish CHoCH with confluence data
                        bos = BreakOfStructure(
                            type='choch', direction='bearish',
                            time=current_candle['time'], price=current_swing['price'],
                            previous_swing=prev_swing['price'],
                            index=current_swing['index'], timeframe=timeframe,
                            strength=strength, break_magnitude=break_magnitude,
                            volume_confirmed=strength > 60, order_block_index=ob_index,
                            fvg_confluence=len(fvg_aligned) > 0,
                            fvg_aligned_indices=fvg_aligned,
                            confluence_score=min(100, confluence_score)
                        )
                        bos_points.append(bos)
            
            elif prev_swing['type'] == 'low' and prev2_swing['type'] == 'high':
                # Bearish structure: lower lows, lower highs expected
                
                if current_swing['type'] == 'low':
                    break_magnitude = abs(current_swing['price'] - prev_swing['price'])
                    strength = self._calculate_break_strength(
                        candles, current_swing['index'], prev_swing['index'],
                        'bearish', break_magnitude
                    )
                    
                    # Check for liquidity sweep before bullish CHoCH
                    sweep = None
                    ob_index = None
                    fvg_aligned = []
                    confluence_score = strength
                    
                    if current_swing['price'] > prev_swing['price']:
                        # Bullish CHoCH - check for sweep of previous swing low
                        sweep = self._detect_liquidity_sweep(
                            candles, current_swing['index'], prev_swing['index'],
                            prev_swing['price'], 'low', 'bullish'
                        )
                        if sweep:
                            liquidity_sweeps.append(sweep)
                            confluence_score += 15  # Liquidity sweep adds confluence
                        
                        # Find bullish order block
                        ob_index = self._find_order_block(
                            candles, current_swing['index'], prev_swing['index'], 'bullish'
                        )
                        if ob_index is not None:
                            ob = self._create_order_block(candles, ob_index, 'bullish', timeframe)
                            if ob:
                                order_blocks.append(ob)
                                confluence_score += 10  # Order block adds confluence
                        
                        # Check FVG confluence - look for bullish FVGs near CHoCH
                        fvg_aligned = self._check_fvg_confluence(
                            active_fvgs, current_swing['price'], 'bullish'
                        )
                        if fvg_aligned:
                            confluence_score += 20  # FVG alignment adds significant confluence
                    
                    if current_swing['price'] < prev_swing['price']:
                        # Bearish BOS
                        bos = BreakOfStructure(
                            type='bos', direction='bearish',
                            time=current_candle['time'], price=current_swing['price'],
                            previous_swing=prev_swing['price'],
                            index=current_swing['index'], timeframe=timeframe,
                            strength=strength, break_magnitude=break_magnitude,
                            volume_confirmed=strength > 60, order_block_index=None,
                            fvg_confluence=False, fvg_aligned_indices=[],
                            confluence_score=strength
                        )
                        bos_points.append(bos)
                    elif current_swing['price'] > prev_swing['price']:
                        # Bullish CHoCH with confluence data
                        bos = BreakOfStructure(
                            type='choch', direction='bullish',
                            time=current_candle['time'], price=current_swing['price'],
                            previous_swing=prev_swing['price'],
                            index=current_swing['index'], timeframe=timeframe,
                            strength=strength, break_magnitude=break_magnitude,
                            volume_confirmed=strength > 60, order_block_index=ob_index,
                            fvg_confluence=len(fvg_aligned) > 0,
                            fvg_aligned_indices=fvg_aligned,
                            confluence_score=min(100, confluence_score)
                        )
                        bos_points.append(bos)
        
        return bos_points, order_blocks, liquidity_sweeps
    
    def _detect_liquidity_sweep(self, candles: List[Dict], choch_idx: int, swing_idx: int,
                                  swing_price: float, sweep_type: str, direction: str) -> Optional[LiquiditySweep]:
        """Detect if price swept liquidity before CHoCH reversal"""
        # Look back 3 candles before the CHoCH
        search_start = max(0, choch_idx - 3)
        
        for i in range(search_start, choch_idx):
            if i >= len(candles):
                continue
            
            candle = candles[i]
            
            if sweep_type == 'high':
                # Check if candle wick swept above previous swing high
                if candle['high'] > swing_price:
                    # Calculate sweep quality
                    sweep_distance = candle['high'] - swing_price
                    range_size = candle['high'] - candle['low']
                    
                    # Quality factors:
                    # 1. Wick rejection (close back below sweep level)
                    rejection = candle['close'] < swing_price
                    # 2. Sweep magnitude (not too shallow, not too deep)
                    optimal_sweep = 0.5 <= (sweep_distance / max(range_size, 0.0001)) <= 2.0
                    
                    if rejection:
                        strength = 60 + (25 if optimal_sweep else 0)
                        if 'volume' in candle and candle['volume'] > 0:
                            avg_vol = sum(candles[j].get('volume', 0) for j in range(max(0, i-3), i)) / 3
                            if candle['volume'] > avg_vol * 1.3:
                                strength += 15
                        
                        return LiquiditySweep(
                            type='high',
                            direction='bearish',
                            time=candle['time'],
                            sweep_price=candle['high'],
                            swing_price=swing_price,
                            choch_index=choch_idx,
                            index=i,
                            strength=min(100, strength),
                            timeframe=candles[0].get('timeframe', 'H1')
                        )
            
            elif sweep_type == 'low':
                # Check if candle wick swept below previous swing low
                if candle['low'] < swing_price:
                    sweep_distance = swing_price - candle['low']
                    range_size = candle['high'] - candle['low']
                    
                    rejection = candle['close'] > swing_price
                    optimal_sweep = 0.5 <= (sweep_distance / max(range_size, 0.0001)) <= 2.0
                    
                    if rejection:
                        strength = 60 + (25 if optimal_sweep else 0)
                        if 'volume' in candle and candle['volume'] > 0:
                            avg_vol = sum(candles[j].get('volume', 0) for j in range(max(0, i-3), i)) / 3
                            if candle['volume'] > avg_vol * 1.3:
                                strength += 15
                        
                        return LiquiditySweep(
                            type='low',
                            direction='bullish',
                            time=candle['time'],
                            sweep_price=candle['low'],
                            swing_price=swing_price,
                            choch_index=choch_idx,
                            index=i,
                            strength=min(100, strength),
                            timeframe=candles[0].get('timeframe', 'H1')
                        )
        
        return None
    
    def _find_order_block(self, candles: List[Dict], choch_idx: int, swing_idx: int, direction: str) -> Optional[int]:
        """Find the last opposing candle before CHoCH that acts as order block"""
        # Look back up to 5 candles before the swing high/low
        search_start = max(0, swing_idx - 5)
        search_end = swing_idx
        
        best_ob_idx = None
        best_strength = 0
        
        for i in range(search_end - 1, search_start - 1, -1):
            if i >= len(candles):
                continue
                
            candle = candles[i]
            body_size = abs(candle['close'] - candle['open'])
            range_size = candle['high'] - candle['low']
            
            if direction == 'bearish':
                # Bearish order block: last bullish candle before bearish CHoCH
                if candle['close'] > candle['open']:  # Bullish candle
                    # Calculate OB strength based on body/range ratio and volume
                    strength = (body_size / max(range_size, 0.0001)) * 50
                    if 'volume' in candle:
                        avg_vol = sum(candles[j].get('volume', 0) for j in range(max(0, i-3), i)) / 3
                        if avg_vol > 0 and candle['volume'] > avg_vol * 1.2:
                            strength += 25
                    
                    if strength > best_strength:
                        best_strength = strength
                        best_ob_idx = i
            
            elif direction == 'bullish':
                # Bullish order block: last bearish candle before bullish CHoCH
                if candle['close'] < candle['open']:  # Bearish candle
                    strength = (body_size / max(range_size, 0.0001)) * 50
                    if 'volume' in candle:
                        avg_vol = sum(candles[j].get('volume', 0) for j in range(max(0, i-3), i)) / 3
                        if avg_vol > 0 and candle['volume'] > avg_vol * 1.2:
                            strength += 25
                    
                    if strength > best_strength:
                        best_strength = strength
                        best_ob_idx = i
        
        return best_ob_idx
    
    def _create_order_block(self, candles: List[Dict], ob_idx: int, direction: str, timeframe: str) -> Optional[OrderBlock]:
        """Create OrderBlock object from candle data"""
        if ob_idx >= len(candles):
            return None
            
        candle = candles[ob_idx]
        
        # Calculate strength
        body_size = abs(candle['close'] - candle['open'])
        range_size = candle['high'] - candle['low']
        strength = min(100, (body_size / max(range_size, 0.0001)) * 50 + 20)
        
        return OrderBlock(
            type=direction,
            start_time=candle['time'],
            index=ob_idx,
            open=candle['open'],
            high=candle['high'],
            low=candle['low'],
            close=candle['close'],
            volume=candle.get('volume', 0),
            strength=strength,
            is_active=True,
            timeframe=timeframe
        )
    
    def _check_fvg_confluence(self, fvgs: List[FairValueGap], choch_price: float, direction: str) -> List[int]:
        """Check if CHoCH aligns with any FVGs for confluence"""
        aligned_indices = []
        
        for fvg in fvgs:
            # Check if FVG is relevant to the direction
            if direction == 'bearish':
                # For bearish CHoCH, look for bearish FVGs (price should be at top of FVG)
                # or any FVG that acts as resistance
                if fvg.top_price >= choch_price >= fvg.bottom_price:
                    # CHoCH price is within FVG zone - strong confluence
                    aligned_indices.append(fvg.index)
                elif abs(fvg.top_price - choch_price) < abs(choch_price * 0.001):  # Within 0.1%
                    # CHoCH price is very close to FVG top
                    aligned_indices.append(fvg.index)
            
            elif direction == 'bullish':
                # For bullish CHoCH, look for bullish FVGs (price should be at bottom of FVG)
                # or any FVG that acts as support
                if fvg.top_price >= choch_price >= fvg.bottom_price:
                    # CHoCH price is within FVG zone - strong confluence
                    aligned_indices.append(fvg.index)
                elif abs(fvg.bottom_price - choch_price) < abs(choch_price * 0.001):  # Within 0.1%
                    # CHoCH price is very close to FVG bottom
                    aligned_indices.append(fvg.index)
        
        return aligned_indices
    
    def generate_trade_suggestions(self, candles: List[Dict], timeframe: str = "H1") -> List[TradeSuggestion]:
        """Generate trade suggestions based on high-confluence CHoCH patterns"""
        suggestions = []
        
        if len(candles) < 5:
            return suggestions
        
        # Only consider recent CHoCH patterns (last 10 candles)
        recent_choch = [b for b in self.bos_points 
                       if b.type == 'choch' 
                       and b.index >= len(candles) - 10]
        
        for choch in recent_choch:
            confluence_score = choch.confluence_score
            
            # Only generate suggestions for high confluence setups
            if confluence_score < 70:
                continue
            
            is_bullish = choch.direction == 'bullish'
            reasons = []
            
            # Build reasons list
            if choch.order_block_index is not None:
                reasons.append(f"Order Block at index {choch.order_block_index}")
            if choch.fvg_confluence:
                reasons.append(f"FVG alignment ({len(choch.fvg_aligned_indices)} gaps)")
            if choch.volume_confirmed:
                reasons.append("Volume confirmed")
            
            # Check for liquidity sweep
            sweep = next((s for s in self.liquidity_sweeps if s.choch_index == choch.index), None)
            if sweep:
                reasons.append(f"Liquidity sweep detected ({sweep.type})")
            
            # Calculate trade levels
            entry_price = choch.price
            
            # Stop loss: below/above relevant structure level
            if is_bullish:
                # For buy: stop below swing low or sweep low
                if sweep:
                    stop_loss = min(sweep.sweep_price * 0.998, choch.previous_swing * 0.995)
                else:
                    stop_loss = choch.previous_swing * 0.995
                # Take profit: 2:1 R:R minimum, look for next supply zone
                risk = abs(entry_price - stop_loss)
                take_profit = entry_price + (risk * 2.5)
            else:
                # For sell: stop above swing high or sweep high
                if sweep:
                    stop_loss = max(sweep.sweep_price * 1.002, choch.previous_swing * 1.005)
                else:
                    stop_loss = choch.previous_swing * 1.005
                # Take profit: 2:1 R:R minimum
                risk = abs(stop_loss - entry_price)
                take_profit = entry_price - (risk * 2.5)
            
            # Calculate R:R ratio
            risk_reward = abs(take_profit - entry_price) / abs(entry_price - stop_loss)
            
            # Determine urgency
            if confluence_score >= 85 and risk_reward >= 2.0:
                urgency = 'immediate'
            elif confluence_score >= 75:
                urgency = 'watch'
            else:
                urgency = 'low'
            
            suggestion = TradeSuggestion(
                type='buy' if is_bullish else 'sell',
                choch_index=choch.index,
                entry_price=round(entry_price, 2),
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
                risk_reward=round(risk_reward, 2),
                confluence_score=round(confluence_score, 1),
                reasons=reasons,
                timeframe=timeframe,
                timestamp=choch.time,
                urgency=urgency
            )
            suggestions.append(suggestion)
        
        # Sort by confluence score (highest first)
        suggestions.sort(key=lambda x: x.confluence_score, reverse=True)
        return suggestions
    
    def get_nearest_zones(self, current_price: float, count: int = 3) -> Dict[str, List[SupplyDemandZone]]:
        """Get nearest supply and demand zones to current price"""
        supply_zones = [z for z in self.zones if z.type == 'supply' and z.is_active]
        demand_zones = [z for z in self.zones if z.type == 'demand' and z.is_active]
        
        # Sort by distance to current price
        supply_zones.sort(key=lambda z: abs(z.base_price - current_price))
        demand_zones.sort(key=lambda z: abs(z.base_price - current_price))
        
        return {
            'supply': supply_zones[:count],
            'demand': demand_zones[:count]
        }
    
    def get_active_fvgs(self, current_price: float = None) -> List[FairValueGap]:
        """Get active (unfilled) FVGs"""
        active = [f for f in self.fvgs if not f.is_filled]
        
        if current_price:
            # Sort by proximity to current price
            active.sort(key=lambda f: min(abs(f.top_price - current_price), 
                                        abs(f.bottom_price - current_price)))
        
        return active
    
    def get_recent_bos(self, count: int = 5) -> List[BreakOfStructure]:
        """Get recent BOS/CHoCH points"""
        return sorted(self.bos_points, key=lambda b: b.time, reverse=True)[:count]

    def _calculate_trend_strength(self, candles: List[Dict]) -> float:
        """Calculate trend strength score (0-100) based on ADX-like calculation"""
        if len(candles) < 20:
            return 50.0  # Neutral if not enough data
        
        try:
            # Calculate +DM and -DM (Directional Movement)
            plus_dm = []
            minus_dm = []
            tr_values = []  # True Range
            
            for i in range(1, len(candles)):
                current = candles[i]
                previous = candles[i-1]
                
                # +DM = current high - previous high (if positive and > -DM)
                up_move = current['high'] - previous['high']
                down_move = previous['low'] - current['low']
                
                if up_move > down_move and up_move > 0:
                    plus_dm.append(up_move)
                else:
                    plus_dm.append(0)
                
                # -DM = previous low - current low (if positive and > +DM)
                if down_move > up_move and down_move > 0:
                    minus_dm.append(down_move)
                else:
                    minus_dm.append(0)
                
                # True Range
                tr = max(
                    current['high'] - current['low'],
                    abs(current['high'] - previous['close']),
                    abs(current['low'] - previous['close'])
                )
                tr_values.append(tr)
            
            # Calculate smoothed values (14-period)
            period = min(14, len(plus_dm))
            smoothed_plus_dm = sum(plus_dm[-period:])
            smoothed_minus_dm = sum(minus_dm[-period:])
            smoothed_tr = sum(tr_values[-period:])
            
            if smoothed_tr == 0:
                return 50.0
            
            # Calculate +DI and -DI
            plus_di = (smoothed_plus_dm / smoothed_tr) * 100
            minus_di = (smoothed_minus_dm / smoothed_tr) * 100
            
            # Calculate DX and ADX
            dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
            
            # Return trend strength (0-100)
            return min(100, max(0, dx))
            
        except Exception as e:
            logger.error(f"Error calculating trend strength: {e}")
            return 50.0
    
    def _determine_trend_direction(self, candles: List[Dict]) -> str:
        """Determine trend direction based on higher highs/lows structure"""
        if len(candles) < 10:
            return 'neutral'
        
        try:
            # Get recent swing points
            recent_candles = candles[-20:]  # Last 20 candles
            
            # Count higher highs and higher lows vs lower highs and lower lows
            highs = [c['high'] for c in recent_candles]
            lows = [c['low'] for c in recent_candles]
            
            # Check for higher highs and higher lows (uptrend)
            hh_count = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i-1])
            hl_count = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i-1])
            
            # Check for lower highs and lower lows (downtrend)
            lh_count = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i-1])
            ll_count = sum(1 for i in range(1, len(lows)) if lows[i] < lows[i-1])
            
            # Determine direction
            if hh_count > len(highs) * 0.6 and hl_count > len(lows) * 0.5:
                return 'bullish'
            elif lh_count > len(highs) * 0.6 and ll_count > len(lows) * 0.5:
                return 'bearish'
            else:
                return 'neutral'
                
        except Exception as e:
            logger.error(f"Error determining trend direction: {e}")
            return 'neutral'


# Global detector instance
price_action_detector = PriceActionDetector()


def analyze_price_action(candles: List[Dict], timeframe: str = "H1") -> Dict[str, Any]:
    """Analyze candles for all price action patterns"""
    return price_action_detector.detect_all_patterns(candles, timeframe)


def get_price_action_summary(current_price: float) -> Dict[str, Any]:
    """Get summary of current price action near price"""
    zones = price_action_detector.get_nearest_zones(current_price)
    fvgs = price_action_detector.get_active_fvgs(current_price)
    recent_bos = price_action_detector.get_recent_bos()
    
    return {
        'nearest_supply': zones['supply'][0].base_price if zones['supply'] else None,
        'nearest_demand': zones['demand'][0].base_price if zones['demand'] else None,
        'active_fvg_count': len(fvgs),
        'recent_structure_breaks': len(recent_bos),
        'current_structure': 'bullish' if any(b.direction == 'bullish' for b in recent_bos[:1]) else 'bearish'
    }
