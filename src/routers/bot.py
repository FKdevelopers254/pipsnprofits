import logging
from fastapi import APIRouter, HTTPException
from src.models.schemas import BotStatus, BotControlRequest, BotConfig
from src.services.bot_service import trading_bot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bot", tags=["Trading Bot"])


@router.get("/status", response_model=BotStatus)
def get_bot_status():
    """Get current bot status and configuration."""
    try:
        status = trading_bot.get_status()
        return BotStatus(
            running=status["running"],
            config=BotConfig(**status["config"]),
            last_check=status["last_check"],
            last_signal=status["last_signal"],
            signal_strength=status.get("signal_strength", 0),
            market_regime=status.get("market_regime", "unknown"),
            higher_tf_trend=status.get("higher_tf_trend", "unknown"),
            signal_history=status.get("signal_history", []),
            total_trades_today=status["total_trades_today"],
            pnl_today=status["pnl_today"],
            # Win rate statistics
            total_trades=status.get("total_trades", 0),
            winning_trades=status.get("winning_trades", 0),
            losing_trades=status.get("losing_trades", 0),
            win_rate=status.get("win_rate", 50.0),
            message="Bot status retrieved"
        )
    except Exception as e:
        logger.exception("Error getting bot status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/control", response_model=BotStatus)
def control_bot(req: BotControlRequest):
    """
    Control the trading bot: START, STOP, or UPDATE config.
    
    - START: Begin auto-trading with optional config
    - STOP: Stop auto-trading
    - UPDATE: Update configuration without changing state
    """
    try:
        action = req.action.upper()
        
        if action == "START":
            config_dict = req.config.model_dump() if req.config else None
            result = trading_bot.start(config_dict)
            if not result.get("success"):
                raise HTTPException(status_code=400, detail=result.get("message"))
                
        elif action == "STOP":
            result = trading_bot.stop()
            if not result.get("success"):
                raise HTTPException(status_code=400, detail=result.get("message"))
                
        elif action == "UPDATE":
            if req.config:
                success = trading_bot.update_config(req.config.model_dump())
                if not success:
                    raise HTTPException(status_code=400, detail="Failed to update config")
        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}. Use START, STOP, or UPDATE")
        
        # Return updated status
        status = trading_bot.get_status()
        return BotStatus(
            running=status["running"],
            config=BotConfig(**status["config"]),
            last_check=status["last_check"],
            last_signal=status["last_signal"],
            signal_strength=status.get("signal_strength", 0),
            market_regime=status.get("market_regime", "unknown"),
            higher_tf_trend=status.get("higher_tf_trend", "unknown"),
            signal_history=status.get("signal_history", []),
            total_trades_today=status["total_trades_today"],
            pnl_today=status["pnl_today"],
            # Win rate statistics
            total_trades=status.get("total_trades", 0),
            winning_trades=status.get("winning_trades", 0),
            losing_trades=status.get("losing_trades", 0),
            win_rate=status.get("win_rate", 50.0),
            message=f"Bot {action.lower()} successful"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error controlling bot: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config", response_model=BotStatus)
def update_config(config: BotConfig):
    """Update bot configuration."""
    try:
        success = trading_bot.update_config(config.model_dump())
        if not success:
            raise HTTPException(status_code=400, detail="Failed to update configuration")
        
        status = trading_bot.get_status()
        return BotStatus(
            running=status["running"],
            config=BotConfig(**status["config"]),
            last_check=status["last_check"],
            last_signal=status["last_signal"],
            signal_strength=status.get("signal_strength", 0),
            market_regime=status.get("market_regime", "unknown"),
            higher_tf_trend=status.get("higher_tf_trend", "unknown"),
            signal_history=status.get("signal_history", []),
            total_trades_today=status["total_trades_today"],
            pnl_today=status["pnl_today"],
            # Win rate statistics
            total_trades=status.get("total_trades", 0),
            winning_trades=status.get("winning_trades", 0),
            losing_trades=status.get("losing_trades", 0),
            win_rate=status.get("win_rate", 50.0),
            message="Configuration updated"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating config: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
