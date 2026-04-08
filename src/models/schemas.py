from pydantic import BaseModel, Field, validator
from typing import Optional, Literal, Any
from datetime import datetime


OrderType = Literal[
    "BUY",
    "SELL",
    "BUY_LIMIT",
    "SELL_LIMIT",
    "BUY_STOP",
    "SELL_STOP",
    "BUY_STOP_LIMIT",
    "SELL_STOP_LIMIT",
    "LIMIT",   # smart auto-type (server will resolve to buy/sell limit based on ask/bid)
    "MARKET",  # explicit market execution; prefer explicit BUY or SELL instead
]


class BaseResponse(BaseModel):
    success: bool = Field(..., description="Indicates if the operation succeeded.")
    message: Optional[str] = Field(None, description="Optional message or error detail.")


class NewOrderRequest(BaseModel):
    symbol: str = Field(..., example="EURUSD")
    volume: float = Field(..., gt=0, example=0.01)
    order_type: OrderType = Field(..., description="Type of order (BUY/SELL/BUY_LIMIT/.../LIMIT)")
    price: Optional[float] = Field(None, example=1.0850, description="Target price (for pending orders)")
    stop_limit_price: Optional[float] = Field(None, example=1.0840, description="Stop-limit trigger price")
    sl: Optional[float] = Field(None, description="Stop Loss level")
    tp: Optional[float] = Field(None, description="Take Profit level")
    deviation: int = Field(10, description="Max price deviation in points (market orders)")
    comment: Optional[str] = Field(None, description="Client-provided short comment")
    magic: Optional[int] = Field(None, description="Magic number to identify EA/strategy")
    client_id: Optional[str] = Field(None, description="Client correlation id")

    @validator("symbol")
    def symbol_upper(cls, v):
        return v.upper()


class UpdateOrderRequest(BaseModel):
    price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    stop_limit_price: Optional[float] = None
    volume: Optional[float] = None
    deviation: Optional[int] = None
    comment: Optional[str] = None


class RemoveOrderRequest(BaseModel):
    ticket: int = Field(..., description="Ticket of the pending order to remove")


class ClosePositionRequest(BaseModel):
    ticket: int = Field(..., description="Ticket of the position to close")
    volume: Optional[float] = Field(None, description="Partial close volume, omit for full close")


class OrderEntry(BaseModel):
    ticket: Optional[int]
    symbol: Optional[str]
    type: Optional[int]  # change to int
    price: Optional[float]
    volume: Optional[float]
    sl: Optional[float]
    tp: Optional[float]
    time: Optional[int]
    comment: Optional[str]
    raw: Optional[Any]


class PositionEntry(BaseModel):
    ticket: Optional[int]
    symbol: Optional[str]
    type: Optional[int]  # change to int
    volume: Optional[float]
    price_open: Optional[float]
    sl: Optional[float]
    tp: Optional[float]
    time: Optional[int]
    profit: Optional[float]
    comment: Optional[str]
    raw: Optional[Any]


class OrderResponse(BaseResponse):
    ticket: Optional[int] = Field(None, description="Order or position ticket if available")
    symbol: Optional[str] = None
    order_type: Optional[str] = None
    price: Optional[float] = None
    volume: Optional[float] = None
    time_placed: Optional[datetime] = None
    comment: Optional[str] = None
    details: Optional[Any] = None


class OrderListResponse(BaseResponse):
    orders: list[OrderEntry] = Field(default_factory=list)


class PositionListResponse(BaseResponse):
    positions: list[PositionEntry] = Field(default_factory=list)


# ========== Dashboard & Account Schemas ==========

class AccountInfoResponse(BaseResponse):
    login: Optional[int] = None
    name: Optional[str] = None
    server: Optional[str] = None
    currency: Optional[str] = None
    balance: Optional[float] = None
    equity: Optional[float] = None
    margin: Optional[float] = None
    margin_free: Optional[float] = None
    margin_level: Optional[float] = None
    profit: Optional[float] = None
    leverage: Optional[int] = None
    credit: Optional[float] = None


class DashboardData(BaseModel):
    account: Optional[AccountInfoResponse] = None
    positions: list[PositionEntry] = Field(default_factory=list)
    orders: list[OrderEntry] = Field(default_factory=list)
    connected: bool = False
    timestamp: Optional[datetime] = None


# ========== Bot Control Schemas ==========

class BotStrategy(str):
    """Strategy types"""
    MA_CROSSOVER = "ma_crossover"
    RSI = "rsi"
    PRICE_ACTION = "price_action"


class BotConfig(BaseModel):
    enabled: bool = Field(default=False, description="Enable/disable auto-trading")
    symbol: str = Field(default="XAUUSD", description="Trading symbol")
    timeframe: str = Field(default="H1", description="Chart timeframe (M1, M5, M15, H1, H4, D1)")
    strategy: str = Field(default="ensemble", description="Trading strategy type (ma_crossover, rsi, price_action, macd, bollinger, stochastic, ensemble)")
    volume: float = Field(default=0.01, gt=0, description="Trade volume")
    sl_pips: float = Field(default=50, description="Stop loss in pips")
    tp_pips: float = Field(default=100, description="Take profit in pips")
    magic: int = Field(default=123456, description="Magic number for bot trades")
    max_spread: float = Field(default=50, description="Max allowed spread in points")
    max_positions: int = Field(default=1, description="Max concurrent positions")
    trend_filter: bool = Field(default=False, description="Only trade with higher TF trend")
    min_signal_strength: int = Field(default=1, description="Require 1+ confluence factors")
    max_daily_loss: float = Field(default=5.0, description="Max daily loss % of equity")
    trailing_stop: bool = Field(default=True, description="Enable trailing stop")
    trailing_stop_distance: float = Field(default=1.5, description="ATR multiplier for trailing stop")
    breakeven_after_pips: float = Field(default=30.0, description="Move to breakeven after X pips profit")
    use_win_rate_sizing: bool = Field(default=True, description="Dynamic sizing based on win rate")
    # Session Filter
    trade_sessions: list = Field(default_factory=lambda: ["london", "ny"], description="Trading sessions: london, ny, asian, all")
    # Volatility Filter
    min_atr_percent: float = Field(default=0.05, description="Minimum ATR as % of price to trade")
    # Intelligent Features
    adaptive_strategy: bool = Field(default=False, description="Disable adaptive strategy selection to allow all strategies to vote")
    max_drawdown_stop: float = Field(default=10.0, description="Stop trading after X% drawdown")
    consecutive_loss_limit: int = Field(default=3, description="Pause after N consecutive losses")
    circuit_breaker_minutes: int = Field(default=30, description="Circuit breaker pause duration")
    use_correlation_filter: bool = Field(default=False, description="Enable multi-instrument correlation filter")
    use_pullback_entry: bool = Field(default=False, description="Wait for pullback before entry")
    pullback_threshold: float = Field(default=0.002, description="Pullback threshold as % of price")


class BotStatus(BaseModel):
    running: bool = False
    config: BotConfig = Field(default_factory=BotConfig)
    last_check: Optional[datetime] = None
    last_signal: Optional[str] = None
    signal_strength: int = 0
    market_regime: str = "unknown"
    higher_tf_trend: str = "unknown"
    signal_history: list = Field(default_factory=list)
    total_trades_today: int = 0
    pnl_today: float = 0.0
    # Win rate statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 50.0
    # Intelligent Features Status
    strategy_performance: dict = Field(default_factory=dict)
    drawdown_percent: float = 0.0
    consecutive_losses: int = 0
    circuit_breaker_active: bool = False
    pending_signal: Optional[str] = None
    hourly_performance: dict = Field(default_factory=dict)
    daily_performance: dict = Field(default_factory=dict)
    message: Optional[str] = None


class BotControlRequest(BaseModel):
    action: str = Field(..., description="START, STOP, or UPDATE")
    config: Optional[BotConfig] = None