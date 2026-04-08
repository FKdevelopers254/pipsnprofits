"""
Backtesting Router - API endpoints for backtesting functionality
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel
import uuid
import logging

from ..models.schemas import BaseResponse
from ..services.backtesting_engine import BacktestingEngine, BacktestConfig, run_sample_backtest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/backtesting", tags=["backtesting"])

# Store running backtests
running_backtests: Dict[str, Dict] = {}


class BacktestRequest(BaseModel):
    """Request model for running backtest"""
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    start_date: datetime
    end_date: datetime
    initial_balance: float = 10000.0
    commission_per_lot: float = 7.0
    spread_points: float = 17.0
    leverage: int = 100


class BacktestStatusResponse(BaseResponse):
    """Response model for backtest status"""
    backtest_id: str
    status: str  # "running", "completed", "failed"
    progress: float  # 0-100
    current_step: str
    results: Optional[Dict[str, Any]] = None


@router.post("/run", response_model=BaseResponse)
async def run_backtest(request: BacktestRequest, background_tasks: BackgroundTasks):
    """Run a backtest in the background"""
    try:
        # Generate unique ID for this backtest
        backtest_id = str(uuid.uuid4())
        
        # Create backtest config
        config = BacktestConfig(
            start_date=request.start_date,
            end_date=request.end_date,
            initial_balance=request.initial_balance,
            commission_per_lot=request.commission_per_lot,
            spread_points=request.spread_points,
            leverage=request.leverage
        )
        
        # Initialize backtest status
        running_backtests[backtest_id] = {
            "status": "running",
            "progress": 0.0,
            "current_step": "Initializing...",
            "results": None,
            "config": config,
            "request": request
        }
        
        # Start backtest in background
        background_tasks.add_task(
            _run_backtest_background,
            backtest_id,
            config,
            request.symbol,
            request.timeframe
        )
        
        return BaseResponse(
            success=True,
            message=f"Backtest started with ID: {backtest_id}",
            details={"backtest_id": backtest_id}
        )
        
    except Exception as e:
        logger.error(f"Error starting backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{backtest_id}", response_model=BacktestStatusResponse)
async def get_backtest_status(backtest_id: str):
    """Get status of a running backtest"""
    if backtest_id not in running_backtests:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    backtest_info = running_backtests[backtest_id]
    
    return BacktestStatusResponse(
        success=True,
        backtest_id=backtest_id,
        status=backtest_info["status"],
        progress=backtest_info["progress"],
        current_step=backtest_info["current_step"],
        results=backtest_info["results"]
    )


@router.get("/results/{backtest_id}")
async def get_backtest_results(backtest_id: str):
    """Get detailed results of a completed backtest"""
    if backtest_id not in running_backtests:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    backtest_info = running_backtests[backtest_id]
    
    if backtest_info["status"] != "completed":
        raise HTTPException(status_code=400, detail="Backtest not completed yet")
    
    return BaseResponse(
        success=True,
        message="Backtest results retrieved",
        details=backtest_info["results"]
    )


@router.get("/list")
async def list_backtests():
    """List all backtests (running and completed)"""
    backtest_list = []
    
    for backtest_id, info in running_backtests.items():
        backtest_list.append({
            "backtest_id": backtest_id,
            "status": info["status"],
            "progress": info["progress"],
            "symbol": info["request"].symbol,
            "timeframe": info["request"].timeframe,
            "start_date": info["request"].start_date.isoformat(),
            "end_date": info["request"].end_date.isoformat()
        })
    
    return BaseResponse(
        success=True,
        message="Backtest list retrieved",
        details={"backtests": backtest_list}
    )


@router.delete("/{backtest_id}")
async def delete_backtest(backtest_id: str):
    """Delete a backtest and its results"""
    if backtest_id not in running_backtests:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    if running_backtests[backtest_id]["status"] == "running":
        raise HTTPException(status_code=400, detail="Cannot delete running backtest")
    
    del running_backtests[backtest_id]
    
    return BaseResponse(
        success=True,
        message="Backtest deleted successfully"
    )


@router.post("/sample", response_model=BaseResponse)
async def run_sample_backtest_endpoint():
    """Run a sample backtest for demonstration"""
    try:
        # Run sample backtest
        results = run_sample_backtest()
        
        return BaseResponse(
            success=True,
            message="Sample backtest completed",
            details={
                "total_trades": results.total_trades,
                "win_rate": results.win_rate,
                "net_profit": results.net_profit,
                "profit_factor": results.profit_factor,
                "max_drawdown_percent": results.max_drawdown_percent
            }
        )
        
    except Exception as e:
        logger.error(f"Error running sample backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _run_backtest_background(backtest_id: str, config: BacktestConfig, 
                                 symbol: str, timeframe: str):
    """Run backtest in background task"""
    try:
        # Update status
        running_backtests[backtest_id]["current_step"] = "Loading historical data..."
        running_backtests[backtest_id]["progress"] = 10.0
        
        # Create engine and run backtest
        engine = BacktestingEngine(config)
        
        running_backtests[backtest_id]["current_step"] = "Calculating indicators..."
        running_backtests[backtest_id]["progress"] = 30.0
        
        results = engine.run_backtest(symbol, timeframe)
        
        running_backtests[backtest_id]["current_step"] = "Calculating results..."
        running_backtests[backtest_id]["progress"] = 90.0
        
        # Save results
        filepath = engine.save_results(results)
        
        # Prepare results data
        results_data = {
            "summary": {
                "total_trades": results.total_trades,
                "winning_trades": results.winning_trades,
                "losing_trades": results.losing_trades,
                "win_rate": results.win_rate,
                "net_profit": results.net_profit,
                "gross_profit": results.gross_profit,
                "gross_loss": results.gross_loss,
                "profit_factor": results.profit_factor,
                "max_drawdown": results.max_drawdown,
                "max_drawdown_percent": results.max_drawdown_percent,
                "sharpe_ratio": results.sharpe_ratio,
                "avg_trade": results.avg_trade,
                "largest_win": results.largest_win,
                "largest_loss": results.largest_loss,
                "avg_win": results.avg_win,
                "avg_loss": results.avg_loss,
                "recovery_factor": results.recovery_factor
            },
            "monthly_returns": results.monthly_returns,
            "filepath": filepath,
            "equity_curve_points": len(results.equity_curve)
        }
        
        # Update final status
        running_backtests[backtest_id]["status"] = "completed"
        running_backtests[backtest_id]["progress"] = 100.0
        running_backtests[backtest_id]["current_step"] = "Completed"
        running_backtests[backtest_id]["results"] = results_data
        
        logger.info(f"Backtest {backtest_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Backtest {backtest_id} failed: {e}")
        running_backtests[backtest_id]["status"] = "failed"
        running_backtests[backtest_id]["current_step"] = f"Failed: {str(e)}"
