"""
RL Trading API Router
Provides endpoints for RL trading system management
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import asyncio
import logging
from datetime import datetime

from src.services.rl_trader import ReinforcementLearningTrader, get_rl_trader, start_rl_training, start_rl_live_trading, stop_rl_live_trading

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rl", tags=["reinforcement-learning"])

# Pydantic models for request/response
class RLTrainingRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    episodes: int = 100
    learning_rate: Optional[float] = None
    epsilon: Optional[float] = None

class RLLiveTradingRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    decision_interval_minutes: int = 5
    confidence_threshold: float = 0.7

class RLConfigRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    training_mode: bool = True
    max_positions: int = 1
    position_size: float = 0.01

# Global RL trader instance
rl_trader_instance: Optional[ReinforcementLearningTrader] = None
training_task: Optional[asyncio.Task] = None
live_trading_task: Optional[asyncio.Task] = None

@router.get("/status")
async def get_rl_status():
    """Get RL system status"""
    global rl_trader_instance
    
    try:
        if rl_trader_instance is None:
            return {
                "status": "not_initialized",
                "message": "RL system not initialized",
                "timestamp": datetime.now().isoformat()
            }
        
        stats = rl_trader_instance.get_performance_stats()
        
        return {
            "status": "active",
            "is_training": training_task is not None and not training_task.done(),
            "is_live_trading": live_trading_task is not None and not live_trading_task.done(),
            "performance": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting RL status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/initialize")
async def initialize_rl_system(config: RLConfigRequest):
    """Initialize RL trading system"""
    global rl_trader_instance
    
    try:
        # Stop existing tasks
        await stop_current_tasks()
        
        # Create new RL trader
        rl_trader_instance = ReinforcementLearningTrader(
            symbol=config.symbol,
            timeframe=config.timeframe,
            training_mode=config.training_mode
        )
        
        logger.info(f"RL system initialized for {config.symbol} {config.timeframe}")
        
        return {
            "status": "initialized",
            "symbol": config.symbol,
            "timeframe": config.timeframe,
            "training_mode": config.training_mode,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error initializing RL system: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/training/start")
async def start_training(request: RLTrainingRequest, background_tasks: BackgroundTasks):
    """Start RL training"""
    global rl_trader_instance, training_task
    
    try:
        # Stop existing training
        if training_task and not training_task.done():
            training_task.cancel()
        
        # Initialize trader if needed
        if rl_trader_instance is None or rl_trader_instance.symbol != request.symbol:
            rl_trader_instance = ReinforcementLearningTrader(
                symbol=request.symbol,
                timeframe=request.timeframe,
                training_mode=True
            )
        
        # Update hyperparameters if provided
        if request.learning_rate is not None:
            rl_trader_instance.agent.learning_rate = request.learning_rate
        if request.epsilon is not None:
            rl_trader_instance.agent.epsilon = request.epsilon
        
        # Start training in background
        async def training_task_func():
            try:
                results = await rl_trader_instance.train(num_episodes=request.episodes)
                logger.info(f"Training completed: {results}")
                return results
            except Exception as e:
                logger.error(f"Training error: {e}")
                raise e
        
        training_task = asyncio.create_task(training_task_func())
        
        return {
            "status": "training_started",
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "episodes": request.episodes,
            "task_id": id(training_task),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error starting training: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/training/stop")
async def stop_training():
    """Stop current training"""
    global training_task
    
    try:
        if training_task and not training_task.done():
            training_task.cancel()
            logger.info("Training stopped by user request")
            return {
                "status": "training_stopped",
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "status": "no_active_training",
                "timestamp": datetime.now().isoformat()
            }
        
    except Exception as e:
        logger.error(f"Error stopping training: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/live/start")
async def start_live_trading(request: RLLiveTradingRequest):
    """Start RL live trading"""
    global rl_trader_instance, live_trading_task
    
    try:
        # Stop existing live trading
        if live_trading_task and not live_trading_task.done():
            live_trading_task.cancel()
        
        # Initialize trader if needed
        if rl_trader_instance is None or rl_trader_instance.symbol != request.symbol:
            rl_trader_instance = ReinforcementLearningTrader(
                symbol=request.symbol,
                timeframe=request.timeframe,
                training_mode=False
            )
        
        # Update configuration
        rl_trader_instance.decision_interval = datetime.timedelta(minutes=request.decision_interval_minutes)
        
        # Start live trading in background
        async def live_trading_task_func():
            try:
                await rl_trader_instance.start_live_trading()
            except Exception as e:
                logger.error(f"Live trading error: {e}")
                raise e
        
        live_trading_task = asyncio.create_task(live_trading_task_func())
        
        return {
            "status": "live_trading_started",
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "decision_interval_minutes": request.decision_interval_minutes,
            "confidence_threshold": request.confidence_threshold,
            "task_id": id(live_trading_task),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error starting live trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/live/stop")
async def stop_live_trading():
    """Stop RL live trading"""
    global rl_trader_instance, live_trading_task
    
    try:
        if rl_trader_instance:
            rl_trader_instance.stop_live_trading()
        
        if live_trading_task and not live_trading_task.done():
            live_trading_task.cancel()
        
        logger.info("Live trading stopped by user request")
        
        return {
            "status": "live_trading_stopped",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error stopping live trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/performance")
async def get_rl_performance():
    """Get RL performance statistics"""
    global rl_trader_instance
    
    try:
        if rl_trader_instance is None:
            raise HTTPException(status_code=404, detail="RL system not initialized")
        
        stats = rl_trader_instance.get_performance_stats()
        
        return {
            "performance": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting RL performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/model/info")
async def get_model_info():
    """Get model information"""
    global rl_trader_instance
    
    try:
        if rl_trader_instance is None:
            raise HTTPException(status_code=404, detail="RL system not initialized")
        
        agent_stats = rl_trader_instance.agent.get_training_stats()
        memory_stats = rl_trader_instance.memory.get_stats()
        
        return {
            "model_info": {
                "symbol": rl_trader_instance.symbol,
                "timeframe": rl_trader_instance.timeframe,
                "training_mode": rl_trader_instance.training_mode,
                "state_size": rl_trader_instance.agent.state_size,
                "action_size": rl_trader_instance.agent.action_size,
                "current_episode": rl_trader_instance.current_episode,
                "total_episodes": rl_trader_instance.total_episodes
            },
            "agent_stats": agent_stats,
            "memory_stats": memory_stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting model info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/model/save")
async def save_model(filepath: Optional[str] = None):
    """Save RL model"""
    global rl_trader_instance
    
    try:
        if rl_trader_instance is None:
            raise HTTPException(status_code=404, detail="RL system not initialized")
        
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"models/rl_model_{rl_trader_instance.symbol}_{rl_trader_instance.timeframe}_{timestamp}.pth"
        
        rl_trader_instance.save_model(filepath)
        
        return {
            "status": "model_saved",
            "filepath": filepath,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error saving model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/model/load")
async def load_model(filepath: str):
    """Load RL model"""
    global rl_trader_instance
    
    try:
        if rl_trader_instance is None:
            # Initialize with default settings
            rl_trader_instance = ReinforcementLearningTrader(training_mode=False)
        
        rl_trader_instance.load_model(filepath)
        
        return {
            "status": "model_loaded",
            "filepath": filepath,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error loading model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/decisions/recent")
async def get_recent_decisions(count: int = 10):
    """Get recent RL trading decisions"""
    global rl_trader_instance
    
    try:
        if rl_trader_instance is None:
            raise HTTPException(status_code=404, detail="RL system not initialized")
        
        # Get recent decisions from environment
        env_stats = rl_trader_instance.environment.get_stats()
        
        # This would need to be implemented in the environment
        # For now, return placeholder data
        decisions = [
            {
                "timestamp": datetime.now().isoformat(),
                "action": "HOLD",
                "confidence": 0.85,
                "reward": 0.01,
                "state_summary": "Neutral market conditions"
            }
        ]
        
        return {
            "decisions": decisions[:count],
            "total_decisions": len(decisions),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting recent decisions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/training/history")
async def get_training_history():
    """Get training history"""
    global rl_trader_instance
    
    try:
        if rl_trader_instance is None:
            raise HTTPException(status_code=404, detail="RL system not initialized")
        
        training_stats = rl_trader_instance.training_stats
        
        return {
            "training_history": {
                "episode_rewards": rl_trader_instance.episode_rewards,
                "episode_lengths": rl_trader_instance.episode_lengths,
                "evaluation_scores": rl_trader_instance.evaluation_scores,
                "best_evaluation_score": rl_trader_instance.best_evaluation_score,
                "current_episode": rl_trader_instance.current_episode,
                "total_episodes": rl_trader_instance.total_episodes
            },
            "statistics": training_stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting training history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/evaluate")
async def evaluate_model(episodes: int = 10):
    """Evaluate RL model performance"""
    global rl_trader_instance
    
    try:
        if rl_trader_instance is None:
            raise HTTPException(status_code=404, detail="RL system not initialized")
        
        # Run evaluation
        evaluation_score = await rl_trader_instance.evaluate_agent(num_episodes=episodes)
        
        return {
            "evaluation_score": evaluation_score,
            "episodes": episodes,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error evaluating model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def stop_current_tasks():
    """Stop all current RL tasks"""
    global training_task, live_trading_task
    
    try:
        if training_task and not training_task.done():
            training_task.cancel()
            try:
                await training_task
            except asyncio.CancelledError:
                pass
        
        if live_trading_task and not live_trading_task.done():
            if rl_trader_instance:
                rl_trader_instance.stop_live_trading()
            live_trading_task.cancel()
            try:
                await live_trading_task
            except asyncio.CancelledError:
                pass
        
        logger.info("All RL tasks stopped")
        
    except Exception as e:
        logger.error(f"Error stopping tasks: {e}")

# Cleanup on shutdown
async def cleanup_rl_tasks():
    """Cleanup RL tasks on shutdown"""
    await stop_current_tasks()
