import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from src.models.schemas import (
    AccountInfoResponse,
    DashboardData,
    PositionEntry,
    OrderEntry,
)
from src.services.mt5_service import mt5_manager
from src.services.performance_analytics import performance_analytics
from src.services.chart_service import chart_data_service
from src.services.price_action_detector import price_action_detector, analyze_price_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


@router.get("/account", response_model=AccountInfoResponse)
def get_account_info():
    """Get account information: balance, equity, margin, etc."""
    try:
        res = mt5_manager.get_account_info()
        if not res.get("success", False):
            return AccountInfoResponse(
                success=False,
                message=res.get("message", "Failed to get account info")
            )
        return AccountInfoResponse(
            success=True,
            message=res.get("message"),
            login=res.get("login"),
            name=res.get("name"),
            server=res.get("server"),
            currency=res.get("currency"),
            balance=res.get("balance"),
            equity=res.get("equity"),
            margin=res.get("margin"),
            margin_free=res.get("margin_free"),
            margin_level=res.get("margin_level"),
            profit=res.get("profit"),
            leverage=res.get("leverage"),
            credit=res.get("credit"),
        )
    except Exception as e:
        logger.exception("Error in /account: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data", response_model=DashboardData)
def get_dashboard_data(
    symbol: Optional[str] = Query(None, description="Optional symbol to filter positions/orders")
):
    """Get full dashboard data: account + positions + orders."""
    try:
        # Get account info
        acc_res = mt5_manager.get_account_info()
        account = None
        if acc_res.get("success"):
            account = AccountInfoResponse(
                success=True,
                login=acc_res.get("login"),
                name=acc_res.get("name"),
                server=acc_res.get("server"),
                currency=acc_res.get("currency"),
                balance=acc_res.get("balance"),
                equity=acc_res.get("equity"),
                margin=acc_res.get("margin"),
                margin_free=acc_res.get("margin_free"),
                margin_level=acc_res.get("margin_level"),
                profit=acc_res.get("profit"),
                leverage=acc_res.get("leverage"),
                credit=acc_res.get("credit"),
            )

        # Get positions
        pos_res = mt5_manager.get_open_positions(symbol)
        positions = []
        if pos_res.get("success"):
            positions = [PositionEntry(**p) for p in pos_res.get("positions", [])]

        # Get orders
        ord_res = mt5_manager.get_open_orders(symbol)
        orders = []
        if ord_res.get("success"):
            orders = [OrderEntry(**o) for o in ord_res.get("orders", [])]

        return DashboardData(
            account=account,
            positions=positions,
            orders=orders,
            connected=mt5_manager._initialized,
            timestamp=datetime.now(timezone.utc)
        )
    except Exception as e:
        logger.exception("Error in /data: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
def get_performance_metrics(days: int = Query(30, description="Number of days to analyze")):
    """Get enhanced performance metrics and analytics."""
    try:
        metrics = performance_analytics.calculate_metrics(days)
        equity_curve = performance_analytics.get_equity_curve_data()
        session_perf = performance_analytics.get_session_performance()
        
        return {
            "success": True,
            "metrics": {
                "basic": {
                    "total_trades": metrics.total_trades,
                    "winning_trades": metrics.winning_trades,
                    "losing_trades": metrics.losing_trades,
                    "win_rate": metrics.win_rate,
                    "total_pnl": metrics.total_pnl,
                    "realized_pnl": metrics.realized_pnl,
                    "unrealized_pnl": metrics.unrealized_pnl
                },
                "advanced": {
                    "profit_factor": metrics.profit_factor,
                    "sharpe_ratio": metrics.sharpe_ratio,
                    "max_drawdown": metrics.max_drawdown,
                    "max_drawdown_percent": metrics.max_drawdown_percent,
                    "avg_win": metrics.avg_win,
                    "avg_loss": metrics.avg_loss,
                    "largest_win": metrics.largest_win,
                    "largest_loss": metrics.largest_loss,
                    "consecutive_wins": metrics.consecutive_wins,
                    "consecutive_losses": metrics.consecutive_losses,
                    "avg_trade_duration": metrics.avg_trade_duration
                },
                "risk": {
                    "risk_reward_ratio": metrics.risk_reward_ratio,
                    "avg_risk_per_trade": metrics.avg_risk_per_trade,
                    "volatility_adjusted_returns": metrics.volatility_adjusted_returns
                },
                "sessions": {
                    "london_pnl": metrics.london_session_pnl,
                    "ny_pnl": metrics.ny_session_pnl,
                    "asian_pnl": metrics.asian_session_pnl
                }
            },
            "equity_curve": equity_curve,
            "session_performance": session_perf,
            "strategy_performance": metrics.strategy_performance or {},
            "daily_pnl_history": metrics.daily_pnl_history or [],
            "hourly_performance": metrics.hourly_performance or {},
            "analysis_period_days": days
        }
    except Exception as e:
        logger.exception("Error in /performance: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/summary")
def get_performance_summary():
    """Get quick performance summary for dashboard overview."""
    try:
        metrics = performance_analytics.calculate_metrics(7)  # Last 7 days
        
        return {
            "success": True,
            "summary": {
                "daily_pnl": metrics.total_pnl,
                "win_rate": metrics.win_rate,
                "total_trades": metrics.total_trades,
                "profit_factor": metrics.profit_factor,
                "max_drawdown": metrics.max_drawdown_percent,
                "sharpe_ratio": metrics.sharpe_ratio,
                "consecutive_wins": metrics.consecutive_wins,
                "consecutive_losses": metrics.consecutive_losses,
                "risk_reward_ratio": metrics.risk_reward_ratio
            }
        }
    except Exception as e:
        logger.exception("Error in /performance/summary: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/performance/trade")
def add_trade_to_performance(trade_data: dict):
    """Add a completed trade to performance analytics."""
    try:
        # Ensure required fields
        required_fields = ['pnl', 'type', 'entry_price']
        for field in required_fields:
            if field not in trade_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Add timestamp if not provided
        if 'timestamp' not in trade_data:
            trade_data['timestamp'] = datetime.now()
        
        performance_analytics.add_trade(trade_data)
        
        return {
            "success": True,
            "message": "Trade added to performance analytics"
        }
    except Exception as e:
        logger.exception("Error in /performance/trade: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chart/data")
def get_chart_data(timeframe: str = Query("H1", description="Chart timeframe")):
    """Get real-time chart data with technical indicators."""
    try:
        # Set timeframe if different
        if timeframe != chart_data_service.timeframe:
            chart_data_service.set_timeframe(timeframe)
        
        # Get chart data
        data = chart_data_service.get_chart_data()
        
        return {
            "success": True,
            "data": data
        }
    except Exception as e:
        logger.exception("Error in /chart/data: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chart/subscribe")
def subscribe_to_chart_updates():
    """Subscribe to real-time chart updates (WebSocket endpoint placeholder)."""
    return {
        "success": True,
        "message": "Real-time subscription endpoint",
        "note": "WebSocket implementation needed for true real-time updates"
    }


@router.post("/chart/trade")
def add_trade_to_chart(trade_data: dict):
    """Add trade marker to chart."""
    try:
        # Add timestamp if not provided
        if 'time' not in trade_data:
            from datetime import datetime
            trade_data['time'] = datetime.now()
        
        chart_data_service.add_trade(trade_data)
        
        return {
            "success": True,
            "message": "Trade added to chart"
        }
    except Exception as e:
        logger.exception("Error in /chart/trade: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chart/level")
def add_level_to_chart(level_data: dict):
    """Add price level (SL/TP) to chart."""
    try:
        chart_data_service.add_level(level_data)
        
        return {
            "success": True,
            "message": "Level added to chart"
        }
    except Exception as e:
        logger.exception("Error in /chart/level: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chart/timeframe")
def change_chart_timeframe(timeframe: str):
    """Change chart timeframe."""
    try:
        chart_data_service.set_timeframe(timeframe)
        
        return {
            "success": True,
            "message": f"Timeframe changed to {timeframe}",
            "data": chart_data_service.get_chart_data()
        }
    except Exception as e:
        logger.exception("Error in /chart/timeframe: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ui", response_class=HTMLResponse)
def dashboard_ui():
    """Serve the futuristic trading dashboard HTML."""
    return HTMLResponse(content=_DASHBOARD_HTML, status_code=200)


_DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MT5 Trading Bot | Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            /* Dark theme (default) */
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a2e;
            --bg-grid-line: rgba(0, 212, 255, 0.03);
            --text-primary: #ffffff;
            --text-secondary: #94a3b8;
            --border-color: #2d2d44;
            --accent-cyan: #00d4ff;
            --accent-purple: #7c3aed;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --accent-orange: #f59e0b;
            --card-hover-shadow: rgba(0, 212, 255, 0.1);
            --table-hover-bg: rgba(0, 212, 255, 0.05);
            --session-badge-bg: rgba(255, 255, 255, 0.1);
            --heat-cell-bg: rgba(255, 255, 255, 0.05);
        }

        [data-theme="light"] {
            --bg-primary: #f8fafc;
            --bg-secondary: #f1f5f9;
            --bg-card: #ffffff;
            --bg-grid-line: rgba(0, 212, 255, 0.08);
            --text-primary: #0f172a;
            --text-secondary: #64748b;
            --border-color: #e2e8f0;
            --accent-cyan: #0891b2;
            --accent-purple: #7c3aed;
            --accent-green: #059669;
            --accent-red: #dc2626;
            --accent-orange: #d97706;
            --card-hover-shadow: rgba(0, 212, 255, 0.15);
            --table-hover-bg: rgba(0, 212, 255, 0.08);
            --session-badge-bg: rgba(0, 0, 0, 0.08);
            --heat-cell-bg: rgba(0, 0, 0, 0.05);
        }

        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
        }

        /* Animated background grid */
        .bg-grid {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-image: 
                linear-gradient(var(--bg-grid-line) 1px, transparent 1px),
                linear-gradient(90deg, var(--bg-grid-line) 1px, transparent 1px);
            background-size: 50px 50px;
            pointer-events: none;
            z-index: 0;
        }

        .bg-glow {
            position: fixed;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle at 30% 70%, rgba(124, 58, 237, 0.15) 0%, transparent 50%),
                        radial-gradient(circle at 70% 30%, rgba(0, 212, 255, 0.1) 0%, transparent 50%);
            pointer-events: none;
            z-index: 0;
            animation: glowRotate 30s linear infinite;
        }

        @keyframes glowRotate {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .container {
            position: relative;
            z-index: 1;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        /* Header */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 30px;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo-icon {
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-purple));
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 20px;
        }

        .logo h1 {
            font-size: 24px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--text-primary), var(--accent-cyan));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .status-indicator {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: var(--bg-card);
            border-radius: 20px;
            border: 1px solid var(--border-color);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--accent-green);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .status-text {
            font-size: 14px;
            color: var(--text-secondary);
        }

        /* Grid Layout */
        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            transition: all 0.3s ease;
        }

        .card:hover {
            border-color: var(--accent-cyan);
            box-shadow: 0 0 30px var(--card-hover-shadow);
        }

        .card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
        }

        .card-title {
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-secondary);
        }

        .card-icon {
            width: 36px;
            height: 36px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
        }

        .card-value {
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 8px;
        }

        .card-subtitle {
            font-size: 14px;
            color: var(--text-secondary);
        }

        /* Card variations */
        .card-balance .card-icon { background: rgba(16, 185, 129, 0.2); color: var(--accent-green); }
        .card-equity .card-icon { background: rgba(0, 212, 255, 0.2); color: var(--accent-cyan); }
        .card-margin .card-icon { background: rgba(245, 158, 11, 0.2); color: var(--accent-orange); }
        .card-profit .card-icon { background: rgba(239, 68, 68, 0.2); }

        .positive { color: var(--accent-green); }
        .negative { color: var(--accent-red); }

        /* Bot Control Card */
        .bot-control {
            grid-column: span 2;
        }

        @media (max-width: 768px) {
            .bot-control { grid-column: span 1; }
        }

        .bot-status {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
        }

        .bot-toggle {
            position: relative;
            width: 60px;
            height: 32px;
        }

        .bot-toggle input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .toggle-slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: var(--bg-secondary);
            border-radius: 32px;
            transition: 0.3s;
            border: 2px solid var(--border-color);
        }

        .toggle-slider:before {
            position: absolute;
            content: "";
            height: 24px;
            width: 24px;
            left: 2px;
            bottom: 2px;
            background: white;
            border-radius: 50%;
            transition: 0.3s;
        }

        input:checked + .toggle-slider {
            background: var(--accent-green);
            border-color: var(--accent-green);
        }

        input:checked + .toggle-slider:before {
            transform: translateX(28px);
        }

        .bot-state {
            font-size: 18px;
            font-weight: 600;
        }

        .bot-config {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 16px;
            margin-top: 20px;
        }

        .config-item {
            background: var(--bg-secondary);
            padding: 12px 16px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }

        .config-label {
            font-size: 12px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }

        .config-value {
            font-size: 16px;
            font-weight: 600;
        }

        /* Tables */
        .table-container {
            overflow-x: auto;
            margin-top: 20px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        th {
            text-align: left;
            padding: 12px;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-secondary);
            border-bottom: 1px solid var(--border-color);
        }

        td {
            padding: 12px;
            border-bottom: 1px solid var(--border-color);
            font-size: 14px;
        }

        tr:hover td {
            background: var(--table-hover-bg);
        }

        .badge {
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }

        .badge-buy {
            background: rgba(16, 185, 129, 0.2);
            color: var(--accent-green);
        }

        .badge-sell {
            background: rgba(239, 68, 68, 0.2);
            color: var(--accent-red);
        }

        .badge-pending {
            background: rgba(245, 158, 11, 0.2);
            color: var(--accent-orange);
        }

        /* Full width cards */
        .positions-card {
            grid-column: span 2;
        }

        @media (max-width: 768px) {
            .positions-card { grid-column: span 1; }
        }

        /* Chart Styles */
        .indicator-btn {
            background: var(--bg-secondary);
            color: var(--text-secondary);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 10px;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .indicator-btn:hover {
            background: var(--accent-cyan);
            color: var(--bg-primary);
            transform: translateY(-1px);
        }

        .indicator-btn.active {
            background: var(--accent-cyan);
            color: var(--bg-primary);
            border-color: var(--accent-cyan);
        }

        .chart-control-btn {
            background: var(--bg-secondary);
            color: var(--text-secondary);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            padding: 6px 10px;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .chart-control-btn:hover {
            background: var(--accent-purple);
            color: var(--bg-primary);
            transform: scale(1.05);
        }

        #timeframeSelector {
            min-width: 60px;
        }

        #chartInfo {
            backdrop-filter: blur(4px);
            border: 1px solid var(--accent-cyan);
        }

        /* Responsive */
        @media (max-width: 768px) {
            .dashboard-grid {
                grid-template-columns: 1fr;
            }
            
            header {
                flex-direction: column;
                gap: 16px;
                text-align: center;
            }
            
            .card-value {
                font-size: 24px;
            }
            
            .bot-config {
                grid-template-columns: 1fr;
            }
        }

        /* Loading animation */
        .skeleton {
            background: linear-gradient(90deg, var(--bg-secondary) 25%, var(--border-color) 50%, var(--bg-secondary) 75%);
            background-size: 200% 100%;
            animation: shimmer 1.5s infinite;
            border-radius: 4px;
        }

        @keyframes shimmer {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }

        /* Connection error overlay */
        .error-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(10, 10, 15, 0.95);
            display: none;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            gap: 20px;
            z-index: 1000;
        }

        .error-overlay.active {
            display: flex;
        }

        .error-icon {
            font-size: 64px;
        }

        .retry-btn {
            padding: 12px 32px;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-purple));
            border: none;
            border-radius: 8px;
            color: white;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }

        .retry-btn:hover {
            transform: scale(1.05);
        }

        /* Theme Toggle Button */
        .theme-toggle {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 50%;
            width: 40px;
            height: 40px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            transition: all 0.3s ease;
        }

        .theme-toggle:hover {
            border-color: var(--accent-cyan);
            box-shadow: 0 0 15px var(--card-hover-shadow);
        }

        /* Light theme specific adjustments */
        [data-theme="light"] .bg-glow {
            opacity: 0.5;
        }

        [data-theme="light"] .error-overlay {
            background: rgba(248, 250, 252, 0.95);
        }

        /* Real-time Notifications */
        .notification-panel {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            max-width: 400px;
            pointer-events: none;
        }

        .notification-panel > * {
            pointer-events: auto;
            margin-bottom: 10px;
            animation: slideInRight 0.3s ease-out;
        }

        .trade-notification {
            background: linear-gradient(135deg, rgba(34, 197, 94, 0.9), rgba(16, 185, 129, 0.9));
            border: 1px solid rgba(34, 197, 94, 0.3);
            border-radius: 12px;
            padding: 15px;
            color: white;
            backdrop-filter: blur(10px);
            box-shadow: 0 8px 32px rgba(34, 197, 94, 0.3);
        }

        .trade-notification-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
            font-weight: bold;
        }

        .trade-action.buy {
            background: rgba(34, 197, 94, 0.2);
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 12px;
        }

        .trade-action.sell {
            background: rgba(239, 68, 68, 0.2);
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 12px;
        }

        .trade-symbol {
            background: rgba(59, 130, 246, 0.2);
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 12px;
        }

        .trade-volume {
            background: rgba(168, 85, 247, 0.2);
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 12px;
        }

        .trade-notification-body {
            display: flex;
            justify-content: space-between;
            font-size: 11px;
            opacity: 0.9;
        }

        .alert-notification {
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.9), rgba(37, 99, 235, 0.9));
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 12px;
            padding: 15px;
            color: white;
            backdrop-filter: blur(10px);
            box-shadow: 0 8px 32px rgba(59, 130, 246, 0.3);
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .alert-notification.warning {
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.9), rgba(217, 119, 6, 0.9));
            border-color: rgba(245, 158, 11, 0.3);
            box-shadow: 0 8px 32px rgba(245, 158, 11, 0.3);
        }

        .alert-notification.error {
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.9), rgba(220, 38, 38, 0.9));
            border-color: rgba(239, 68, 68, 0.3);
            box-shadow: 0 8px 32px rgba(239, 68, 68, 0.3);
        }

        .alert-notification.success {
            background: linear-gradient(135deg, rgba(34, 197, 94, 0.9), rgba(16, 185, 129, 0.9));
            border-color: rgba(34, 197, 94, 0.3);
            box-shadow: 0 8px 32px rgba(34, 197, 94, 0.3);
        }

        .alert-icon {
            font-size: 20px;
            flex-shrink: 0;
        }

        .alert-content {
            flex: 1;
        }

        .alert-message {
            font-weight: 500;
            margin-bottom: 4px;
        }

        .alert-time {
            font-size: 11px;
            opacity: 0.8;
        }

        /* Connection Status */
        .connection-status {
            position: fixed;
            top: 20px;
            left: 20px;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            z-index: 1000;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .connection-status.connected {
            background: rgba(34, 197, 94, 0.8);
            border-color: rgba(34, 197, 94, 0.3);
            box-shadow: 0 4px 16px rgba(34, 197, 94, 0.3);
        }

        .connection-status.disconnected {
            background: rgba(239, 68, 68, 0.8);
            border-color: rgba(239, 68, 68, 0.3);
            box-shadow: 0 4px 16px rgba(239, 68, 68, 0.3);
        }

        /* Real-time Chart Indicator */
        .realtime-indicator {
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 10px;
            font-weight: bold;
            z-index: 100;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .realtime-indicator.active {
            background: rgba(34, 197, 94, 0.8);
            border-color: rgba(34, 197, 94, 0.3);
            box-shadow: 0 2px 8px rgba(34, 197, 94, 0.3);
            animation: pulse 2s infinite;
        }

        .realtime-indicator.inactive {
            background: rgba(239, 68, 68, 0.8);
            border-color: rgba(239, 68, 68, 0.3);
            box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3);
        }

        /* Trade Alert Notifications */
        .trade-alerts-container {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 1000;
            display: flex;
            flex-direction: column;
            gap: 10px;
            max-width: 320px;
        }

        .trade-alert-toast {
            background: rgba(17, 24, 39, 0.95);
            border: 2px solid;
            border-radius: 12px;
            padding: 16px;
            backdrop-filter: blur(10px);
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
            animation: slideIn 0.3s ease-out;
        }

        .trade-alert-toast.immediate {
            border-color: #dc2626;
            box-shadow: 0 10px 40px rgba(220, 38, 38, 0.3);
        }

        .trade-alert-toast.watch {
            border-color: #ea580c;
            box-shadow: 0 10px 40px rgba(234, 88, 12, 0.3);
        }

        .trade-alert-toast.low {
            border-color: #6b7280;
        }

        .alert-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 12px;
        }

        .alert-icon {
            font-size: 20px;
        }

        .alert-type {
            font-weight: bold;
            font-size: 14px;
            color: #f9fafb;
            flex: 1;
        }

        .alert-score {
            background: rgba(220, 38, 38, 0.8);
            color: white;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }

        .alert-levels {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            margin-bottom: 12px;
            font-size: 12px;
        }

        .alert-levels div {
            background: rgba(55, 65, 81, 0.5);
            padding: 8px;
            border-radius: 6px;
            text-align: center;
            color: #e5e7eb;
        }

        .alert-reasons {
            font-size: 11px;
            color: #9ca3af;
            line-height: 1.4;
            padding-top: 8px;
            border-top: 1px solid rgba(75, 85, 99, 0.3);
        }

        @keyframes slideIn {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }

        /* Toast Notifications */
        .toast {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0, 0, 0, 0.9);
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 14px;
            z-index: 10000;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            animation: slideUp 0.3s ease-out;
        }

        .toast.success {
            background: rgba(34, 197, 94, 0.9);
            border-color: rgba(34, 197, 94, 0.3);
        }

        .toast.error {
            background: rgba(239, 68, 68, 0.9);
            border-color: rgba(239, 68, 68, 0.3);
        }

        .toast.warning {
            background: rgba(245, 158, 11, 0.9);
            border-color: rgba(245, 158, 11, 0.3);
        }

        .toast.info {
            background: rgba(59, 130, 246, 0.9);
            border-color: rgba(59, 130, 246, 0.3);
        }

        /* Performance Stats */
        .performance-stats {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 10px;
            font-family: monospace;
            z-index: 1000;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        /* Animations */
        @keyframes slideInRight {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }

        @keyframes slideUp {
            from {
                transform: translate(-50%, 100%);
                opacity: 0;
            }
            to {
                transform: translate(-50%, 0);
                opacity: 1;
            }
        }

        @keyframes pulse {
            0%, 100% {
                opacity: 1;
            }
            50% {
                opacity: 0.7;
            }
        }

        @keyframes fadeOut {
            from {
                opacity: 1;
            }
            to {
                opacity: 0;
            }
        }

        /* Responsive */
        @media (max-width: 768px) {
            .notification-panel {
                right: 10px;
                left: 10px;
                max-width: none;
            }

            .connection-status {
                top: auto;
                bottom: 20px;
                left: 10px;
            }

            .performance-stats {
                display: none;
            }
        }
    </style>
</head>
<body>
    <div class="bg-grid"></div>
    <div class="bg-glow"></div>
    
    <!-- Connection Status Indicator -->
    <div id="connection-status" class="connection-status disconnected">🔴 Offline</div>

    <div class="container">
        <header>
            <div class="logo">
                <div class="logo-icon">MT5</div>
                <h1>Quantum Trader</h1>
            </div>
            <div style="display: flex; align-items: center; gap: 12px;">
                <button id="themeToggle" class="theme-toggle" onclick="toggleTheme()" title="Toggle Dark/Light Mode">
                    <span id="themeIcon">🌙</span>
                </button>
                <div class="status-indicator">
                    <div class="status-dot" id="connStatus"></div>
                    <span class="status-text" id="connText">Connected</span>
                </div>
            </div>
        </header>

        <div class="dashboard-grid">
            <!-- Account Cards -->
            <div class="card card-balance">
                <div class="card-header">
                    <span class="card-title">Balance</span>
                    <div class="card-icon">💰</div>
                </div>
                <div class="card-value" id="balance">--</div>
                <div class="card-subtitle" id="currency">USD Account</div>
            </div>

            <div class="card card-equity">
                <div class="card-header">
                    <span class="card-title">Equity</span>
                    <div class="card-icon">📊</div>
                </div>
                <div class="card-value" id="equity">--</div>
                <div class="card-subtitle" id="marginLevel">Margin Level: --</div>
            </div>

            <div class="card card-margin">
                <div class="card-header">
                    <span class="card-title">Used Margin</span>
                    <div class="card-icon">⚡</div>
                </div>
                <div class="card-value" id="margin">--</div>
                <div class="card-subtitle" id="freeMargin">Free: --</div>
            </div>

            <div class="card card-profit">
                <div class="card-header">
                    <span class="card-title">Today's P&L</span>
                    <div class="card-icon">📈</div>
                </div>
                <div class="card-value" id="profit">--</div>
                <div class="card-subtitle">Realized + Unrealized</div>
            </div>

            <!-- Advanced TradingView-style Chart -->
            <div class="card" style="grid-column: span 3;">
                <div class="card-header">
                    <span class="card-title">📈 Live Price Chart</span>
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <div id="chart-realtime-status" class="realtime-indicator inactive">🔴 Polling</div>
                        <!-- Timeframe Switcher -->
                        <select id="timeframeSelector" style="background: var(--bg-secondary); color: var(--text-primary); border: 1px solid var(--border-color); border-radius: 4px; padding: 4px 8px; font-size: 12px;">
                            <option value="M5">M5</option>
                            <option value="M15">M15</option>
                            <option value="H1" selected>H1</option>
                            <option value="H4">H4</option>
                            <option value="D1">D1</option>
                        </select>
                        <!-- Indicator Toggles -->
                        <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                            <button id="toggleMA" class="indicator-btn active" data-indicator="ma" title="Moving Averages">MA</button>
                            <button id="toggleRSI" class="indicator-btn" data-indicator="rsi" title="RSI">RSI</button>
                            <button id="toggleMACD" class="indicator-btn" data-indicator="macd" title="MACD">MACD</button>
                            <button id="toggleBB" class="indicator-btn" data-indicator="bollinger" title="Bollinger Bands">BB</button>
                            <button id="toggleVolume" class="indicator-btn active" data-indicator="volume" title="Volume">VOL</button>
                            <button id="toggleCHoCH" class="indicator-btn active" data-indicator="choch" title="Change of Character">CHoCH</button>
                            <button id="toggleBOS" class="indicator-btn active" data-indicator="bos" title="Break of Structure">BOS</button>
                            <button id="toggleFVG" class="indicator-btn active" data-indicator="fvg" title="Fair Value Gaps">FVG</button>
                            <button id="toggleFibonacci" class="indicator-btn" data-indicator="fibonacci" title="Fibonacci Levels">📐</button>
                            <button id="toggleVolumeProfile" class="indicator-btn" data-indicator="volumeProfile" title="Volume Profile">📊</button>
                            <button id="toggleMultiTimeframe" class="indicator-btn" data-indicator="multiTimeframe" title="Multi-Timeframe">📈</button>
                        </div>
                    </div>
                </div>
                <div style="height: 400px; position: relative; background: var(--bg-secondary); border-radius: 8px; margin-top: 12px;">
                    <canvas id="tradingChart" style="width: 100%; height: 100%; cursor: crosshair;"></canvas>
                    
                    <!-- Chart Info Overlay -->
                    <div id="chartInfo" style="position: absolute; top: 10px; left: 10px; background: rgba(0, 0, 0, 0.8); color: white; padding: 8px 12px; border-radius: 4px; font-size: 11px; display: none;">
                        <div style="font-weight: bold; color: var(--accent-cyan); margin-bottom: 4px;" id="chartTimeframe">--</div>
                        <div id="chartPrice">--</div>
                        <div id="chartTime">--</div>
                        <div id="chartChange">--</div>
                    </div>
                </div>
                
                <!-- Chart Controls -->
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px; padding: 0 8px;">
                    <div style="display: flex; gap: 12px; font-size: 11px;">
                        <span style="color: var(--text-secondary);">Current: <span id="currentPrice" style="color: var(--text-primary); font-weight: 600;">--</span></span>
                        <span style="color: var(--text-secondary);">Change: <span id="priceChange" style="font-weight: 600;">--</span></span>
                        <span style="color: var(--text-secondary);">Volume: <span id="currentVolume" style="font-weight: 600;">--</span></span>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button id="zoomIn" class="chart-control-btn" title="Zoom In">➕</button>
                        <button id="zoomOut" class="chart-control-btn" title="Zoom Out">➖</button>
                        <button id="resetChart" class="chart-control-btn" title="Reset View">🔄</button>
                    </div>
                </div>
                
                <!-- CHoCH Analysis Panel (Below Chart) -->
                <div id="chochAnalysisPanel" style="display: none; margin-top: 12px; padding: 12px; background: var(--bg-secondary); border-radius: 8px; border: 2px solid var(--accent-cyan);">
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;">
                        <!-- CHoCH Analysis -->
                        <div style="padding: 12px; background: rgba(15, 23, 42, 0.95); border-radius: 6px; border: 2px solid var(--accent-cyan);">
                            <div style="font-weight: bold; color: #fbbf24; margin-bottom: 8px; font-size: 14px;">📊 CHoCH ANALYSIS</div>
                            <div id="chochPhase" style="font-weight: bold; font-size: 18px; color: var(--accent-cyan); margin-bottom: 6px;">NEUTRAL</div>
                            <div id="chochPrediction" style="font-size: 14px; color: #ffffff; margin-bottom: 8px;">--</div>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <div style="flex: 1; height: 8px; background: rgba(255,255,255,0.2); border-radius: 4px; overflow: hidden;">
                                    <div id="chochConfidenceBar" style="height: 100%; width: 50%; background: linear-gradient(90deg, #1e40af, #3b82f6); border-radius: 4px;"></div>
                                </div>
                                <span id="chochConfidence" style="font-weight: bold; color: #fbbf24; font-size: 14px;">50%</span>
                            </div>
                        </div>
                        
                        <!-- Position Sizing -->
                        <div style="padding: 12px; background: rgba(15, 23, 42, 0.95); border-radius: 6px; border: 2px solid var(--accent-purple);">
                            <div style="font-weight: bold; color: #fbbf24; margin-bottom: 8px; font-size: 14px;">📐 POSITION</div>
                            <div style="display: flex; align-items: baseline; gap: 8px; margin-bottom: 6px;">
                                <span id="positionLots" style="font-weight: bold; font-size: 24px; color: var(--accent-purple);">0.00</span>
                                <span style="color: #94a3b8; font-size: 12px;">lots</span>
                            </div>
                            <div id="positionSL" style="font-size: 13px; color: #ffffff; margin-bottom: 4px;">SL: --p</div>
                            <div id="positionRisk" style="font-size: 13px; color: #ffffff;">Risk: $--</div>
                        </div>
                        
                        <!-- Tracker -->
                        <div style="padding: 12px; background: rgba(15, 23, 42, 0.95); border-radius: 6px; border: 2px solid var(--accent-green);">
                            <div style="font-weight: bold; color: #94a3b8; margin-bottom: 8px; font-size: 14px;">📈 TRACKER</div>
                            <div style="display: flex; gap: 16px; margin-bottom: 8px;">
                                <span id="trackerWins" style="font-weight: bold; font-size: 16px; color: #22c55e;">0W</span>
                                <span id="trackerLosses" style="font-weight: bold; font-size: 16px; color: #ef4444;">0L</span>
                                <span id="trackerAccuracy" style="font-weight: bold; font-size: 20px; margin-left: auto; color: #22c55e;">0%</span>
                            </div>
                            <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden; margin-bottom: 8px;">
                                <div id="trackerBar" style="height: 100%; width: 0%; background: linear-gradient(90deg, #22c55e 70%, #ef4444 70%); border-radius: 3px;"></div>
                            </div>
                            <!-- Recent Predictions -->
                            <div id="recentPredictions" style="display: flex; gap: 4px; flex-wrap: wrap; font-size: 11px; max-height: 40px; overflow-y: auto;">
                                <span style="color: #64748b;">Recent: </span>
                            </div>
                        </div>
                        
                        <!-- Status -->
                        <div id="projectionStatus" style="padding: 12px; background: rgba(34, 197, 94, 0.2); border-radius: 6px; border: 2px solid #22c55e; display: flex; flex-direction: column; justify-content: center; align-items: center;">
                            <div style="font-weight: bold; font-size: 18px; color: #22c55e; margin-bottom: 4px;">✓ ON TRACK</div>
                            <div id="currentPriceDisplay" style="font-size: 14px; color: #ffffff;">Price: --</div>
                        </div>
                    </div>
                </div>
                </div>
            </div>

            <!-- Signal Strength Meter -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Signal Strength</span>
                    <div class="card-icon">📊</div>
                </div>
                <div style="margin-top: 16px;">
                    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                        <span style="font-size: 12px; color: var(--text-secondary);">BUY</span>
                        <div style="flex: 1; height: 8px; background: var(--bg-secondary); border-radius: 4px; overflow: hidden;">
                            <div id="buyStrength" style="height: 100%; width: 0%; background: linear-gradient(90deg, var(--accent-green), #10b981); transition: width 0.3s ease;"></div>
                        </div>
                        <span id="buyPercent" style="font-size: 12px; color: var(--accent-green); font-weight: 600;">0%</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span style="font-size: 12px; color: var(--text-secondary);">SELL</span>
                        <div style="flex: 1; height: 8px; background: var(--bg-secondary); border-radius: 4px; overflow: hidden;">
                            <div id="sellStrength" style="height: 100%; width: 0%; background: linear-gradient(90deg, var(--accent-red), #ef4444); transition: width 0.3s ease;"></div>
                        </div>
                        <span id="sellPercent" style="font-size: 12px; color: var(--accent-red); font-weight: 600;">0%</span>
                    </div>
                </div>
                <div style="margin-top: 12px; padding: 8px; background: var(--bg-secondary); border-radius: 6px; text-align: center;">
                    <div id="signalDirection" style="font-size: 14px; font-weight: 600; color: var(--text-secondary);">NEUTRAL</div>
                </div>
            </div>

            <!-- Multi-Timeframe Analysis -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Multi-Timeframe</span>
                    <div class="card-icon">⏰</div>
                </div>
                <div style="text-align: center; margin: 12px 0;">
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px;">
                        <div style="text-align: center;">
                            <div style="font-size: 10px; color: var(--text-secondary); margin-bottom: 2px;">M15</div>
                            <div id="m15Signal" style="font-weight: 700; color: var(--text-secondary); font-size: 12px;">--</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="font-size: 10px; color: var(--text-secondary); margin-bottom: 2px;">H1</div>
                            <div id="h1Signal" style="font-weight: 700; color: var(--text-secondary); font-size: 12px;">--</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="font-size: 10px; color: var(--text-secondary); margin-bottom: 2px;">H4</div>
                            <div id="h4Signal" style="font-weight: 700; color: var(--text-secondary); font-size: 12px;">--</div>
                        </div>
                    </div>
                    <div style="margin: 8px 0;">
                        <div style="font-size: 10px; color: var(--text-secondary); margin-bottom: 4px;">Alignment Score</div>
                        <div style="display: flex; align-items: center; justify-content: center;">
                            <div style="width: 100px; height: 8px; background: var(--bg-secondary); border-radius: 4px; overflow: hidden; margin-right: 8px;">
                                <div id="mtfAlignmentBar" style="width: 0%; height: 100%; background: linear-gradient(90deg, var(--accent-red), var(--accent-orange), var(--accent-green));"></div>
                            </div>
                            <span id="mtfAlignmentScore" style="font-size: 11px; font-weight: 700; color: var(--text-secondary);">0%</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Bot Control -->
            <div class="card bot-control">
                <div class="card-header">
                    <span class="card-title">Auto Trading Bot</span>
                    <div class="card-icon">🤖</div>
                </div>
                <div class="bot-status">
                    <label class="bot-toggle">
                        <input type="checkbox" id="botToggle">
                        <span class="toggle-slider"></span>
                    </label>
                    <span class="bot-state" id="botState">Stopped</span>
                </div>
                <div class="bot-config">
                    <div class="config-item">
                        <div class="config-label">Symbol</div>
                        <div class="config-value" id="botSymbol">XAUUSD</div>
                    </div>
                    <div class="config-item">
                        <div class="config-label">Strategy</div>
                        <div class="config-value" id="botStrategy">MA Crossover</div>
                    </div>
                    <div class="config-item">
                        <div class="config-label">Timeframe</div>
                        <select id="botTimeframe" style="background: var(--bg-secondary); color: var(--text-primary); border: 1px solid var(--border-color); border-radius: 6px; padding: 8px 12px; font-size: 14px; font-weight: 500; cursor: pointer; outline: none; transition: all 0.2s ease;" onmouseover="this.style.borderColor='var(--accent-cyan)'" onmouseout="this.style.borderColor='var(--border-color)'">
                            <option value="M5">M5 (5 min)</option>
                            <option value="M15">M15 (15 min)</option>
                            <option value="H1" selected>H1 (1 hour)</option>
                            <option value="H4">H4 (4 hour)</option>
                        </select>
                    </div>
                    <div class="config-item">
                        <div class="config-label">Volume</div>
                        <div class="config-value" id="botVolume">0.01</div>
                    </div>
                </div>
                
                <!-- Signal Display -->
                <div class="signal-section" style="margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--border-color);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                        <span class="card-title">Current Signal</span>
                        <span id="lastCheckTime" style="font-size: 12px; color: var(--text-secondary);">--</span>
                    </div>
                    <div class="signal-display" id="signalDisplay" style="display: flex; align-items: center; gap: 16px; margin-bottom: 20px;">
                        <div class="signal-badge" id="signalBadge" style="padding: 16px 32px; border-radius: 12px; font-size: 24px; font-weight: 700; text-transform: uppercase; background: var(--bg-secondary); color: var(--text-secondary); border: 2px solid var(--border-color);">
                            WAITING
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 4px;">
                            <div class="signal-info" id="signalInfo" style="font-size: 14px; color: var(--text-secondary);">Bot not running</div>
                            <div id="signalStrength" style="font-size: 12px; color: var(--text-secondary);">Strength: --</div>
                        </div>
                    </div>
                    
                    <!-- Market Analysis -->
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 16px; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                        <div>
                            <div style="font-size: 10px; color: var(--text-secondary); text-transform: uppercase;">Market Regime</div>
                            <div id="marketRegime" style="font-size: 14px; font-weight: 600; color: var(--accent-cyan);">--</div>
                        </div>
                        <div>
                            <div style="font-size: 10px; color: var(--text-secondary); text-transform: uppercase;">H4 Trend</div>
                            <div id="higherTfTrend" style="font-size: 14px; font-weight: 600; color: var(--accent-purple);">--</div>
                        </div>
                    </div>
                    
                    <!-- Signal History -->
                    <div class="signal-history">
                        <div class="card-title" style="margin-bottom: 12px;">Recent Signals</div>
                        <div id="signalHistoryList" style="display: flex; flex-wrap: wrap; gap: 8px; max-height: 80px; overflow-y: auto;">
                            <span style="color: var(--text-secondary); font-size: 12px;">No signals yet</span>
                        </div>
                    </div>
                    
                    <!-- Trade Stats -->
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-color);">
                        <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                            <div style="font-size: 20px; font-weight: 700; color: var(--accent-cyan);" id="tradesToday">0</div>
                            <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Trades Today</div>
                        </div>
                        <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                            <div style="font-size: 20px; font-weight: 700; color: var(--accent-green);" id="pnlToday">$0.00</div>
                            <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">P&L Today</div>
                        </div>
                        <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                            <div style="font-size: 20px; font-weight: 700; color: var(--accent-purple);" id="positionsOpen">0</div>
                            <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Positions Open</div>
                        </div>
                    </div>
                    
                    <!-- Win Rate Stats -->
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 12px;">
                        <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                            <div style="font-size: 24px; font-weight: 700; color: var(--accent-green);" id="winRate">50.0%</div>
                            <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Win Rate</div>
                        </div>
                        <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                            <div style="font-size: 14px; font-weight: 600; color: var(--text-secondary);" id="winLossStats">0W / 0L (0 total)</div>
                            <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Wins / Losses</div>
                        </div>
                    </div>
                    
                    <!-- Intelligent Features Status (Collapsible) -->
                    <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border-color);">
                        <div style="display: flex; justify-content: space-between; align-items: center; cursor: pointer;" onclick="toggleIntelligentFeatures()">
                            <div class="card-title" style="font-size: 12px; text-transform: uppercase; color: var(--text-secondary);">
                                Intelligent Features 🤖
                            </div>
                            <div id="featuresToggle" style="font-size: 16px; color: var(--text-secondary); transition: transform 0.2s;">▼</div>
                        </div>
                        
                        <div id="intelligentFeaturesContent" style="margin-top: 12px; display: block;">
                            <!-- Pattern Detection Display -->
                            <div id="patternDisplay" style="display: none; margin-bottom: 12px; padding: 8px 12px; background: rgba(139, 92, 246, 0.2); border: 1px solid var(--accent-purple); border-radius: 8px; font-size: 12px; color: var(--accent-purple);">
                                📊 Pattern: <span id="patternName" style="font-weight: 600;">--</span>
                            </div>
                        
                        <!-- Session Filter Status -->
                        <div style="margin-bottom: 12px;">
                            <div style="font-size: 10px; color: var(--text-secondary); margin-bottom: 4px; text-transform: uppercase;">Active Sessions</div>
                            <div id="sessionStatus" style="display: flex; gap: 4px; flex-wrap: wrap;">
                                <span class="session-badge" id="sessionLondon" style="padding: 2px 6px; border-radius: 4px; font-size: 10px; background: rgba(255,255,255,0.1); color: var(--text-secondary);">London</span>
                                <span class="session-badge" id="sessionNY" style="padding: 2px 6px; border-radius: 4px; font-size: 10px; background: rgba(255,255,255,0.1); color: var(--text-secondary);">NY</span>
                                <span class="session-badge" id="sessionAsian" style="padding: 2px 6px; border-radius: 4px; font-size: 10px; background: rgba(255,255,255,0.1); color: var(--text-secondary);">Asian</span>
                            </div>
                        </div>
                        
                        <!-- Hourly Win Rate Heatmap -->
                        <div style="margin-bottom: 12px;">
                            <div style="font-size: 10px; color: var(--text-secondary); margin-bottom: 4px; text-transform: uppercase;">Best Hours (Win Rate)</div>
                            <div id="hourlyHeatmap" style="display: grid; grid-template-columns: repeat(12, 1fr); gap: 2px; font-size: 9px;">
                                <!-- Hours 0-11 -->
                                <div class="heat-cell" data-hour="0" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">0</div>
                                <div class="heat-cell" data-hour="1" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">1</div>
                                <div class="heat-cell" data-hour="2" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">2</div>
                                <div class="heat-cell" data-hour="3" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">3</div>
                                <div class="heat-cell" data-hour="4" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">4</div>
                                <div class="heat-cell" data-hour="5" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">5</div>
                                <div class="heat-cell" data-hour="6" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">6</div>
                                <div class="heat-cell" data-hour="7" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">7</div>
                                <div class="heat-cell" data-hour="8" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">8</div>
                                <div class="heat-cell" data-hour="9" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">9</div>
                                <div class="heat-cell" data-hour="10" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">10</div>
                                <div class="heat-cell" data-hour="11" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">11</div>
                            </div>
                            <div id="hourlyHeatmap2" style="display: grid; grid-template-columns: repeat(12, 1fr); gap: 2px; font-size: 9px; margin-top: 2px;">
                                <!-- Hours 12-23 -->
                                <div class="heat-cell" data-hour="12" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">12</div>
                                <div class="heat-cell" data-hour="13" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">13</div>
                                <div class="heat-cell" data-hour="14" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">14</div>
                                <div class="heat-cell" data-hour="15" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">15</div>
                                <div class="heat-cell" data-hour="16" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">16</div>
                                <div class="heat-cell" data-hour="17" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">17</div>
                                <div class="heat-cell" data-hour="18" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">18</div>
                                <div class="heat-cell" data-hour="19" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">19</div>
                                <div class="heat-cell" data-hour="20" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">20</div>
                                <div class="heat-cell" data-hour="21" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">21</div>
                                <div class="heat-cell" data-hour="22" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">22</div>
                                <div class="heat-cell" data-hour="23" style="text-align: center; padding: 3px 2px; border-radius: 3px; background: rgba(255,255,255,0.05); color: var(--text-secondary);">23</div>
                            </div>
                        </div>
                        
                        <!-- Circuit Breaker Alert -->
                        <div id="circuitBreakerAlert" style="display: none; padding: 8px 12px; background: rgba(239, 68, 68, 0.2); border: 1px solid var(--accent-red); border-radius: 8px; margin-bottom: 12px; font-size: 12px; color: var(--accent-red); font-weight: 600;">
                            ⚠️ CIRCUIT BREAKER ACTIVE - Trading Paused
                        </div>
                        
                        <!-- Pending Signal Alert -->
                        <div id="pendingSignalAlert" style="display: none; padding: 8px 12px; background: rgba(245, 158, 11, 0.2); border: 1px solid var(--accent-orange); border-radius: 8px; margin-bottom: 12px; font-size: 12px; color: var(--accent-orange);">
                            ⏳ Waiting for pullback before entry...
                        </div>
                        
                        <!-- Smart Stats Grid -->
                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px;">
                            <div class="stat-box" style="text-align: center; padding: 8px; background: var(--bg-secondary); border-radius: 6px;">
                                <div style="font-size: 16px; font-weight: 700; color: var(--accent-cyan);" id="drawdownPercent">0.0%</div>
                                <div style="font-size: 10px; color: var(--text-secondary);">Drawdown</div>
                            </div>
                            <div class="stat-box" style="text-align: center; padding: 8px; background: var(--bg-secondary); border-radius: 6px;">
                                <div style="font-size: 16px; font-weight: 700; color: var(--accent-purple);" id="consecutiveLosses">0</div>
                                <div style="font-size: 10px; color: var(--text-secondary);">Consec. Losses</div>
                            </div>
                            <div class="stat-box" style="text-align: center; padding: 8px; background: var(--bg-secondary); border-radius: 6px;">
                                <div style="font-size: 14px; font-weight: 600; color: var(--accent-green);" id="adaptiveStatus">ON</div>
                                <div style="font-size: 10px; color: var(--text-secondary);">Adaptive</div>
                            </div>
                        </div>
                        
                        <!-- Strategy Weights -->
                        <div style="margin-top: 8px;">
                            <div style="font-size: 10px; color: var(--text-secondary); margin-bottom: 6px; text-transform: uppercase;">Strategy Weights</div>
                            <div id="strategyWeights" style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; font-size: 10px;">
                                <div style="text-align: center; padding: 4px; background: rgba(16, 185, 129, 0.1); border-radius: 4px;">
                                    <div style="color: var(--text-secondary);">MA</div>
                                    <div style="font-weight: 600; color: var(--accent-green);" id="weightMA">1.0</div>
                                </div>
                                <div style="text-align: center; padding: 4px; background: rgba(16, 185, 129, 0.1); border-radius: 4px;">
                                    <div style="color: var(--text-secondary);">RSI</div>
                                    <div style="font-weight: 600; color: var(--accent-green);" id="weightRSI">1.0</div>
                                </div>
                                <div style="text-align: center; padding: 4px; background: rgba(16, 185, 129, 0.1); border-radius: 4px;">
                                    <div style="color: var(--text-secondary);">MACD</div>
                                    <div style="font-weight: 600; color: var(--accent-green);" id="weightMACD">1.0</div>
                                </div>
                                <div style="text-align: center; padding: 4px; background: rgba(16, 185, 129, 0.1); border-radius: 4px;">
                                    <div style="color: var(--text-secondary);">BB</div>
                                    <div style="font-weight: 600; color: var(--accent-green);" id="weightBB">1.0</div>
                                </div>
                                <div style="text-align: center; padding: 4px; background: rgba(16, 185, 129, 0.1); border-radius: 4px;">
                                    <div style="color: var(--text-secondary);">STOCH</div>
                                    <div style="font-weight: 600; color: var(--accent-green);" id="weightSTOCH">1.0</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Enhanced Performance Analytics -->
            <div class="card" style="grid-column: span 2;">
                <div class="card-header">
                    <span class="card-title">📊 Enhanced Performance Analytics</span>
                    <div class="card-icon">📈</div>
                </div>
                <div style="margin-top: 16px;">
                    <!-- Performance Summary Grid -->
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin-bottom: 20px;">
                        <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px; border: 1px solid var(--border-color);">
                            <div style="font-size: 18px; font-weight: 700; color: var(--accent-green);" id="perfProfitFactor">--</div>
                            <div style="font-size: 10px; color: var(--text-secondary); text-transform: uppercase;">Profit Factor</div>
                        </div>
                        <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px; border: 1px solid var(--border-color);">
                            <div style="font-size: 18px; font-weight: 700; color: var(--accent-cyan);" id="perfSharpeRatio">--</div>
                            <div style="font-size: 10px; color: var(--text-secondary); text-transform: uppercase;">Sharpe Ratio</div>
                        </div>
                        <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px; border: 1px solid var(--border-color);">
                            <div style="font-size: 18px; font-weight: 700; color: var(--accent-orange);" id="perfRiskReward">--</div>
                            <div style="font-size: 10px; color: var(--text-secondary); text-transform: uppercase;">R:R Ratio</div>
                        </div>
                        <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px; border: 1px solid var(--border-color);">
                            <div style="font-size: 18px; font-weight: 700; color: var(--accent-purple);" id="perfAvgWin">--</div>
                            <div style="font-size: 10px; color: var(--text-secondary); text-transform: uppercase;">Avg Win</div>
                        </div>
                        <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px; border: 1px solid var(--border-color);">
                            <div style="font-size: 18px; font-weight: 700; color: var(--accent-red);" id="perfAvgLoss">--</div>
                            <div style="font-size: 10px; color: var(--text-secondary); text-transform: uppercase;">Avg Loss</div>
                        </div>
                        <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px; border: 1px solid var(--border-color);">
                            <div style="font-size: 18px; font-weight: 700; color: var(--accent-cyan);" id="perfConsecWins">--</div>
                            <div style="font-size: 10px; color: var(--text-secondary); text-transform: uppercase;">Consec Wins</div>
                        </div>
                    </div>

                    <!-- Session Performance -->
                    <div style="margin-bottom: 20px;">
                        <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; text-transform: uppercase; font-weight: 600;">Session Performance</div>
                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
                            <div style="text-align: center; padding: 10px; background: linear-gradient(135deg, rgba(0, 212, 255, 0.1), rgba(124, 58, 237, 0.1)); border-radius: 8px; border: 1px solid var(--border-color);">
                                <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 4px;">🇬🇧 London</div>
                                <div style="font-size: 16px; font-weight: 700; color: var(--accent-cyan);" id="londonPnL">+$0.00</div>
                            </div>
                            <div style="text-align: center; padding: 10px; background: linear-gradient(135deg, rgba(0, 212, 255, 0.1), rgba(124, 58, 237, 0.1)); border-radius: 8px; border: 1px solid var(--border-color);">
                                <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 4px;">🇺🇸 New York</div>
                                <div style="font-size: 16px; font-weight: 700; color: var(--accent-cyan);" id="nyPnL">+$0.00</div>
                            </div>
                            <div style="text-align: center; padding: 10px; background: linear-gradient(135deg, rgba(0, 212, 255, 0.1), rgba(124, 58, 237, 0.1)); border-radius: 8px; border: 1px solid var(--border-color);">
                                <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 4px;">🇯🇵 Asian</div>
                                <div style="font-size: 16px; font-weight: 700; color: var(--accent-cyan);" id="asianPnL">+$0.00</div>
                            </div>
                        </div>
                    </div>

                    <!-- Advanced Metrics -->
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                        <!-- Drawdown Chart -->
                        <div style="background: var(--bg-secondary); border-radius: 8px; padding: 12px; border: 1px solid var(--border-color);">
                            <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; text-transform: uppercase;">Drawdown Analysis</div>
                            <div style="text-align: center; padding: 8px;">
                                <div style="font-size: 24px; font-weight: 700; color: var(--accent-red);" id="maxDrawdownAmount">--</div>
                                <div style="font-size: 12px; color: var(--text-secondary);">Maximum Drawdown</div>
                                <div style="margin-top: 8px; height: 40px; background: var(--bg-primary); border-radius: 4px; position: relative; overflow: hidden;">
                                    <div id="drawdownBar" style="height: 100%; width: 0%; background: linear-gradient(90deg, var(--accent-red), rgba(239, 68, 68, 0.3)); transition: width 0.5s ease; border-radius: 4px;"></div>
                                </div>
                            </div>
                        </div>

                        <!-- Trade Duration -->
                        <div style="background: var(--bg-secondary); border-radius: 8px; padding: 12px; border: 1px solid var(--border-color);">
                            <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; text-transform: uppercase;">Trade Duration</div>
                            <div style="text-align: center; padding: 8px;">
                                <div style="font-size: 24px; font-weight: 700; color: var(--accent-purple);" id="avgTradeDuration">--</div>
                                <div style="font-size: 12px; color: var(--text-secondary);">Average Minutes</div>
                                <div style="margin-top: 8px; display: flex; justify-content: space-around; font-size: 10px;">
                                    <div>
                                        <div style="color: var(--accent-green); font-weight: 600;" id="longestWin">--</div>
                                        <div style="color: var(--text-secondary);">Longest Win</div>
                                    </div>
                                    <div>
                                        <div style="color: var(--accent-red); font-weight: 600;" id="longestLoss">--</div>
                                        <div style="color: var(--text-secondary);">Longest Loss</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Positions -->
            <div class="card positions-card">
                <div class="card-header">
                    <span class="card-title">Open Positions</span>
                    <div class="card-icon">🎯</div>
                </div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Type</th>
                                <th>Volume</th>
                                <th>Open Price</th>
                                <th>SL / TP</th>
                                <th>P&L</th>
                            </tr>
                        </thead>
                        <tbody id="positionsTable">
                            <tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">No open positions</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Pending Orders -->
            <div class="card positions-card">
                <div class="card-header">
                    <span class="card-title">Pending Orders</span>
                    <div class="card-icon">⏳</div>
                </div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Ticket</th>
                                <th>Symbol</th>
                                <th>Type</th>
                                <th>Volume</th>
                                <th>Price</th>
                                <th>SL / TP</th>
                            </tr>
                        </thead>
                        <tbody id="ordersTable">
                            <tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">No pending orders</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Strategy Performance Heatmap -->
            <div class="card" style="grid-column: span 2;">
                <div class="card-header">
                    <span class="card-title">Strategy Performance Heatmap</span>
                    <div class="card-icon">🔥</div>
                </div>
                <div style="margin-top: 12px;">
                    <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px;">
                        <div class="strategy-tile" id="strategyMA" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px; border: 2px solid var(--border-color);">
                            <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px;">MA</div>
                            <div style="font-size: 16px; font-weight: 700; color: var(--text-primary);" id="maSignal">HOLD</div>
                            <div style="font-size: 10px; color: var(--text-secondary); margin-top: 4px;">0%</div>
                            <div style="height: 4px; background: var(--bg-secondary); border-radius: 2px; margin-top: 6px; overflow: hidden;">
                                <div style="height: 100%; width: 0%; background: var(--accent-green); transition: width 0.3s ease;" id="maPerformance"></div>
                            </div>
                        </div>
                        <div class="strategy-tile" id="strategyRSI" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px; border: 2px solid var(--border-color);">
                            <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px;">RSI</div>
                            <div style="font-size: 16px; font-weight: 700; color: var(--text-primary);" id="rsiSignal">HOLD</div>
                            <div style="font-size: 10px; color: var(--text-secondary); margin-top: 4px;">0%</div>
                            <div style="height: 4px; background: var(--bg-secondary); border-radius: 2px; margin-top: 6px; overflow: hidden;">
                                <div style="height: 100%; width: 0%; background: var(--accent-green); transition: width 0.3s ease;" id="rsiPerformance"></div>
                            </div>
                        </div>
                        <div class="strategy-tile" id="strategyMACD" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px; border: 2px solid var(--border-color);">
                            <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px;">MACD</div>
                            <div style="font-size: 16px; font-weight: 700; color: var(--text-primary);" id="macdSignal">HOLD</div>
                            <div style="font-size: 10px; color: var(--text-secondary); margin-top: 4px;">0%</div>
                            <div style="height: 4px; background: var(--bg-secondary); border-radius: 2px; margin-top: 6px; overflow: hidden;">
                                <div style="height: 100%; width: 0%; background: var(--accent-green); transition: width 0.3s ease;" id="macdPerformance"></div>
                            </div>
                        </div>
                        <div class="strategy-tile" id="strategyBB" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px; border: 2px solid var(--border-color);">
                            <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px;">BB</div>
                            <div style="font-size: 16px; font-weight: 700; color: var(--text-primary);" id="bbSignal">HOLD</div>
                            <div style="font-size: 10px; color: var(--text-secondary); margin-top: 4px;">0%</div>
                            <div style="height: 4px; background: var(--bg-secondary); border-radius: 2px; margin-top: 6px; overflow: hidden;">
                                <div style="height: 100%; width: 0%; background: var(--accent-green); transition: width 0.3s ease;" id="bbPerformance"></div>
                            </div>
                        </div>
                        <div class="strategy-tile" id="strategySTOCH" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px; border: 2px solid var(--border-color);">
                            <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px;">STOCH</div>
                            <div style="font-size: 16px; font-weight: 700; color: var(--text-primary);" id="stochSignal">HOLD</div>
                            <div style="font-size: 10px; color: var(--text-secondary); margin-top: 4px;">0%</div>
                            <div style="height: 4px; background: var(--bg-secondary); border-radius: 2px; margin-top: 6px; overflow: hidden;">
                                <div style="height: 100%; width: 0%; background: var(--accent-green); transition: width 0.3s ease;" id="stochPerformance"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Enhanced Trade History -->
            <div class="card" style="grid-column: span 3;">
                <div class="card-header">
                    <span class="card-title">Trade History</span>
                    <div class="card-icon">📜</div>
                </div>
                <!-- Performance Analytics Summary -->
                <div id="performanceSummary" style="margin-bottom: 16px;">
                    <!-- Performance metrics will be inserted here -->
                </div>
                <div class="table-container" style="margin-top: 12px;">
                    <table style="font-size: 12px;">
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Signal</th>
                                <th>Entry</th>
                                <th>Exit</th>
                                <th>P&L</th>
                                <th>Notes</th>
                            </tr>
                        </thead>
                        <tbody id="tradeHistoryTable">
                            <tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">No trades yet today</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <div class="error-overlay" id="errorOverlay">
        <div class="error-icon">⚠️</div>
        <h2>Connection Lost</h2>
        <p>Unable to connect to MT5 trading server</p>
        <button class="retry-btn" onclick="location.reload()">Reconnect</button>
    </div>

    <!-- Reinforcement Learning Dashboard -->
    <div class="container" style="margin-top: 20px;">
        <div class="card" style="grid-column: span 3;">
            <div class="card-header">
                <span class="card-title">🧠 Reinforcement Learning Trading</span>
                <div class="card-icon">🤖</div>
            </div>
            
            <!-- RL Configuration -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 20px;">
                <div>
                    <label style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; display: block;">Symbol</label>
                    <select id="rl-symbol-select" style="width: 100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-primary);">
                        <option value="XAUUSD">XAUUSD</option>
                        <option value="EURUSD">EURUSD</option>
                        <option value="GBPUSD">GBPUSD</option>
                    </select>
                </div>
                <div>
                    <label style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; display: block;">Timeframe</label>
                    <select id="rl-timeframe-select" style="width: 100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-primary);">
                        <option value="M1">M1</option>
                        <option value="M5">M5</option>
                        <option value="M15">M15</option>
                        <option value="H1" selected>H1</option>
                        <option value="H4">H4</option>
                        <option value="D1">D1</option>
                    </select>
                </div>
            </div>

            <!-- RL Status -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 20px;">
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-status" class="status-warning">Not Initialized</div>
                    <div style="font-size: 10px; color: var(--text-secondary); margin-top: 4px;">System Status</div>
                </div>
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-training-status" class="status-warning">Not Training</div>
                    <div style="font-size: 10px; color: var(--text-secondary); margin-top: 4px;">Training Status</div>
                </div>
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-live-status" class="status-warning">Not Trading</div>
                    <div style="font-size: 10px; color: var(--text-secondary); margin-top: 4px;">Live Trading</div>
                </div>
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-model-status" class="status-warning">No Model</div>
                    <div style="font-size: 10px; color: var(--text-secondary); margin-top: 4px;">Model Status</div>
                </div>
            </div>

            <!-- RL Controls -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 20px;">
                <div>
                    <button id="rl-init-btn" class="btn btn-primary" style="width: 100%;">Initialize RL System</button>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                    <button id="rl-training-start-btn" class="btn btn-success" style="font-size: 12px;">Start Training</button>
                    <button id="rl-training-stop-btn" class="btn btn-secondary" style="font-size: 12px;">Stop Training</button>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                    <button id="rl-live-start-btn" class="btn btn-success" style="font-size: 12px;">Start Live</button>
                    <button id="rl-live-stop-btn" class="btn btn-secondary" style="font-size: 12px;">Stop Live</button>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                    <button id="rl-model-save-btn" class="btn btn-primary" style="font-size: 12px;">Save Model</button>
                    <button id="rl-model-load-btn" class="btn btn-primary" style="font-size: 12px;">Load Model</button>
                </div>
            </div>

            <!-- RL Training Parameters -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 20px;">
                <div>
                    <label style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; display: block;">Training Episodes</label>
                    <input type="number" id="rl-training-episodes" value="100" min="10" max="10000" style="width: 100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-primary);">
                </div>
                <div>
                    <label style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; display: block;">Learning Rate</label>
                    <input type="number" id="rl-learning-rate" value="0.001" min="0.0001" max="0.1" step="0.0001" style="width: 100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-primary);">
                </div>
                <div>
                    <label style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; display: block;">Epsilon</label>
                    <input type="number" id="rl-epsilon" value="1.0" min="0.0" max="1.0" step="0.01" style="width: 100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-primary);">
                </div>
                <div>
                    <label style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; display: block;">Decision Interval (min)</label>
                    <input type="number" id="rl-decision-interval" value="5" min="1" max="60" style="width: 100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-primary);">
                </div>
                <div>
                    <label style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; display: block;">Confidence Threshold</label>
                    <input type="number" id="rl-confidence-threshold" value="0.7" min="0.1" max="1.0" step="0.1" style="width: 100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-primary);">
                </div>
                <div>
                    <button id="rl-evaluate-btn" class="btn btn-primary" style="width: 100%;">Evaluate Model</button>
                </div>
            </div>

            <!-- RL Performance Metrics -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin-bottom: 20px;">
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-current-episode" style="font-size: 16px; font-weight: 600; color: var(--accent-cyan);">0</div>
                    <div style="font-size: 10px; color: var(--text-secondary);">Current Episode</div>
                </div>
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-total-episodes" style="font-size: 16px; font-weight: 600; color: var(--accent-purple);">0</div>
                    <div style="font-size: 10px; color: var(--text-secondary);">Total Episodes</div>
                </div>
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-avg-reward" style="font-size: 16px; font-weight: 600; color: var(--accent-green);">0.0000</div>
                    <div style="font-size: 10px; color: var(--text-secondary);">Avg Reward</div>
                </div>
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-best-eval-score" style="font-size: 16px; font-weight: 600; color: var(--accent-orange);">0.0000</div>
                    <div style="font-size: 10px; color: var(--text-secondary);">Best Eval Score</div>
                </div>
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-epsilon" style="font-size: 16px; font-weight: 600; color: var(--accent-red);">1.0000</div>
                    <div style="font-size: 10px; color: var(--text-secondary);">Epsilon</div>
                </div>
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-training-steps" style="font-size: 16px; font-weight: 600; color: var(--accent-blue);">0</div>
                    <div style="font-size: 10px; color: var(--text-secondary);">Training Steps</div>
                </div>
            </div>

            <!-- RL Trading Performance -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px;">
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-balance" style="font-size: 16px; font-weight: 600; color: var(--accent-green);">0.00</div>
                    <div style="font-size: 10px; color: var(--text-secondary);">Balance</div>
                </div>
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-total-pnl" style="font-size: 16px; font-weight: 600; color: var(--accent-cyan);">0.00</div>
                    <div style="font-size: 10px; color: var(--text-secondary);">Total P&L</div>
                </div>
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-win-rate" style="font-size: 16px; font-weight: 600; color: var(--accent-purple);">0.0%</div>
                    <div style="font-size: 10px; color: var(--text-secondary);">Win Rate</div>
                </div>
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-max-drawdown" style="font-size: 16px; font-weight: 600; color: var(--accent-red);">0.0%</div>
                    <div style="font-size: 10px; color: var(--text-secondary);">Max Drawdown</div>
                </div>
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-open-positions" style="font-size: 16px; font-weight: 600; color: var(--accent-orange);">0</div>
                    <div style="font-size: 10px; color: var(--text-secondary);">Open Positions</div>
                </div>
                <div class="stat-box" style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                    <div id="rl-avg-loss" style="font-size: 16px; font-weight: 600; color: var(--accent-blue);">0.000000</div>
                    <div style="font-size: 10px; color: var(--text-secondary);">Avg Loss</div>
                </div>
            </div>

            <!-- RL Evaluation Status -->
            <div style="margin-top: 16px; padding: 12px; background: var(--bg-secondary); border-radius: 8px; border: 1px solid var(--border-color);">
                <div id="rl-evaluation-status" class="status-warning">Not Evaluated</div>
            </div>
        </div>
    </div>

    <script src="/static/js/trading-chart.js"></script>
    <script src="/static/js/realtime-client.js"></script>
    <script src="/static/js/rl-dashboard.js"></script>
    <script>
        const API_BASE = window.location.origin;
        let botEnabled = false;
        let botConfig = {
            enabled: false,
            symbol: 'XAUUSD',
            strategy: 'ensemble',
            timeframe: 'H1',
            volume: 0.01,
            sl_pips: 50,
            tp_pips: 100
        };

        // Format currency
        function formatCurrency(value, currency = 'USD') {
            if (value === null || value === undefined) return '--';
            return new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: currency,
                minimumFractionDigits: 2
            }).format(value);
        }

        // Format number
        function formatNumber(value, decimals = 2) {
            if (value === null || value === undefined) return '--';
            return value.toFixed(decimals);
        }

        // Update account cards
        function updateAccount(data) {
            if (!data.account) return;
            
            const acc = data.account;
            document.getElementById('balance').textContent = formatCurrency(acc.balance, acc.currency);
            document.getElementById('equity').textContent = formatCurrency(acc.equity, acc.currency);
            document.getElementById('margin').textContent = formatCurrency(acc.margin, acc.currency);
            document.getElementById('profit').textContent = formatCurrency(acc.profit, acc.currency);
            
            const accountName = acc.name ? `${acc.name} - ` : '';
            document.getElementById('currency').textContent = `${accountName}${acc.currency} Account #${acc.login}`;
            document.getElementById('marginLevel').textContent = `Margin Level: ${formatNumber(acc.margin_level, 2)}%`;
            document.getElementById('freeMargin').textContent = `Free: ${formatCurrency(acc.margin_free, acc.currency)}`;
            
            // Color code profit
            const profitEl = document.getElementById('profit');
            profitEl.className = 'card-value ' + (acc.profit >= 0 ? 'positive' : 'negative');
        }

        // Update positions table
        function updatePositions(positions) {
            const tbody = document.getElementById('positionsTable');
            if (!positions || positions.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">No open positions</td></tr>';
                return;
            }

            tbody.innerHTML = positions.map(p => {
                const profitClass = (p.profit || 0) >= 0 ? 'positive' : 'negative';
                const typeClass = p.type === 0 ? 'badge-buy' : 'badge-sell';
                const typeText = p.type === 0 ? 'BUY' : 'SELL';
                
                return `<tr>
                    <td><strong>${p.symbol}</strong></td>
                    <td><span class="badge ${typeClass}">${typeText}</span></td>
                    <td>${formatNumber(p.volume, 2)}</td>
                    <td>${formatNumber(p.price_open, 5)}</td>
                    <td>${formatNumber(p.sl, 5)} / ${formatNumber(p.tp, 5)}</td>
                    <td class="${profitClass}">${formatCurrency(p.profit)}</td>
                </tr>`;
            }).join('');
        }

        // Update orders table
        function updateOrders(orders) {
            const tbody = document.getElementById('ordersTable');
            if (!orders || orders.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">No pending orders</td></tr>';
                return;
            }

            const typeNames = { 2: 'BUY LIMIT', 3: 'SELL LIMIT', 4: 'BUY STOP', 5: 'SELL STOP' };
            
            tbody.innerHTML = orders.map(o => {
                return `<tr>
                    <td>#${o.ticket}</td>
                    <td><strong>${o.symbol}</strong></td>
                    <td><span class="badge badge-pending">${typeNames[o.type] || o.type}</span></td>
                    <td>${formatNumber(o.volume, 2)}</td>
                    <td>${formatNumber(o.price, 5)}</td>
                    <td>${formatNumber(o.sl, 5)} / ${formatNumber(o.tp, 5)}</td>
                </tr>`;
            }).join('');
        }

        // Fetch dashboard data
        async function fetchDashboard() {
            try {
                const response = await fetch(`${API_BASE}/api/v1/dashboard/data`);
                if (!response.ok) throw new Error('Failed to fetch');
                
                const data = await response.json();
                
                if (!data.connected) {
                    document.getElementById('errorOverlay').classList.add('active');
                    return;
                }
                
                document.getElementById('errorOverlay').classList.remove('active');
                document.getElementById('connStatus').style.background = 'var(--accent-green)';
                
                updateAccount(data);
                updatePositions(data.positions);
                updateOrders(data.orders);
            } catch (err) {
                console.error('Dashboard fetch error:', err);
                document.getElementById('connStatus').style.background = 'var(--accent-red)';
            }
        }

        // Bot toggle handler
        document.getElementById('botToggle').addEventListener('change', async (e) => {
            const action = e.target.checked ? 'START' : 'STOP';
            const newState = e.target.checked;
            
            try {
                const response = await fetch(`${API_BASE}/api/v1/bot/control`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: action })
                });
                
                const result = await response.json();
                
                if (!response.ok || !result.success) {
                    e.target.checked = !newState;
                    const msg = result.detail || result.message || 'Unknown error';
                    alert('Failed to ' + (newState ? 'start' : 'stop') + ' bot: ' + msg);
                    return;
                }
                
                botEnabled = newState;
                document.getElementById('botState').textContent = botEnabled ? 'Running' : 'Stopped';
                document.getElementById('botState').style.color = botEnabled ? 'var(--accent-green)' : 'var(--accent-red)';
                
            } catch (err) {
                console.error('Bot control error:', err);
                e.target.checked = !newState;
                alert('Connection error: ' + err.message);
            }
        });

        // Update signal display
        function updateSignal(status) {
            const badge = document.getElementById('signalBadge');
            const info = document.getElementById('signalInfo');
            const lastCheck = document.getElementById('lastCheckTime');
            const strengthEl = document.getElementById('signalStrength');
            const regimeEl = document.getElementById('marketRegime');
            const trendEl = document.getElementById('higherTfTrend');
            
            if (!status.running) {
                badge.textContent = 'WAITING';
                badge.style.background = 'var(--bg-secondary)';
                badge.style.color = 'var(--text-secondary)';
                badge.style.borderColor = 'var(--border-color)';
                info.textContent = 'Bot not running';
                strengthEl.textContent = 'Strength: --';
                regimeEl.textContent = '--';
                trendEl.textContent = '--';
                lastCheck.textContent = '--';
                return;
            }
            
            const signal = status.last_signal || 'HOLD';
            badge.textContent = signal;
            
            // Update strength
            const strength = status.signal_strength || 0;
            strengthEl.textContent = `Strength: ${strength}/5`;
            
            // Update market regime
            const regime = status.market_regime || 'unknown';
            regimeEl.textContent = regime.toUpperCase();
            regimeEl.style.color = regime === 'trending' ? 'var(--accent-green)' : 
                                   regime === 'ranging' ? 'var(--accent-orange)' : 'var(--text-secondary)';
            
            // Update H4 trend
            const htTrend = status.higher_tf_trend || 'unknown';
            trendEl.textContent = htTrend.toUpperCase();
            trendEl.style.color = htTrend === 'bullish' ? 'var(--accent-green)' : 
                                 htTrend === 'bearish' ? 'var(--accent-red)' : 'var(--text-secondary)';
            
            if (signal === 'BUY') {
                badge.style.background = 'rgba(16, 185, 129, 0.2)';
                badge.style.color = 'var(--accent-green)';
                badge.style.borderColor = 'var(--accent-green)';
                badge.style.boxShadow = '0 0 20px rgba(16, 185, 129, 0.3)';
                info.textContent = `🟢 Strong BUY (strength: ${strength})`;
            } else if (signal === 'SELL') {
                badge.style.background = 'rgba(239, 68, 68, 0.2)';
                badge.style.color = 'var(--accent-red)';
                badge.style.borderColor = 'var(--accent-red)';
                badge.style.boxShadow = '0 0 20px rgba(239, 68, 68, 0.3)';
                info.textContent = `🔴 Strong SELL (strength: ${strength})`;
            } else {
                badge.style.background = 'var(--bg-secondary)';
                badge.style.color = 'var(--text-secondary)';
                badge.style.borderColor = 'var(--border-color)';
                badge.style.boxShadow = 'none';
                info.textContent = signal.includes('Ranging') ? '📊 Skipped: Ranging market' : '⏳ No signal';
            }
            
            if (status.last_check) {
                const checkTime = new Date(status.last_check);
                lastCheck.textContent = 'Last check: ' + checkTime.toLocaleTimeString();
            }
        }

        // Update signal history
        function updateSignalHistory(history) {
            const container = document.getElementById('signalHistoryList');
            if (!history || history.length === 0) {
                container.innerHTML = '<span style="color: var(--text-secondary); font-size: 12px;">No signals yet</span>';
                return;
            }
            
            container.innerHTML = history.slice().reverse().map(h => {
                const time = new Date(h.time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
                let color = 'var(--text-secondary)';
                if (h.signal === 'BUY') color = 'var(--accent-green)';
                if (h.signal === 'SELL') color = 'var(--accent-red)';
                if (h.signal === 'HOLD') color = 'var(--accent-orange)';
                
                return `<span style="padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; background: rgba(255,255,255,0.05); color: ${color}; border: 1px solid ${color};">${h.signal} ${time}</span>`;
            }).join('');
        }

        // Update intelligent features display
        function updateIntelligentFeatures(status) {
            // Get config first (used by session filter)
            const config = status.config || {};
            
            // Pattern detection display
            const patternDisplay = document.getElementById('patternDisplay');
            const patternName = document.getElementById('patternName');
            const lastSignal = status.signal_history?.[0];
            if (lastSignal && lastSignal.pattern && lastSignal.pattern !== 'none') {
                patternDisplay.style.display = 'block';
                patternName.textContent = lastSignal.pattern.replace(/_/g, ' ').toUpperCase();
            } else {
                patternDisplay.style.display = 'none';
            }
            
            // Session filter status
            const sessions = config.trade_sessions || [];
            const londonEl = document.getElementById('sessionLondon');
            const nyEl = document.getElementById('sessionNY');
            const asianEl = document.getElementById('sessionAsian');
            
            function setSessionStatus(el, active) {
                if (active) {
                    el.style.background = 'rgba(16, 185, 129, 0.3)';
                    el.style.color = 'var(--accent-green)';
                    el.style.fontWeight = '600';
                } else {
                    el.style.background = 'rgba(255,255,255,0.05)';
                    el.style.color = 'var(--text-secondary)';
                    el.style.fontWeight = '400';
                }
            }
            
            setSessionStatus(londonEl, sessions.includes('london'));
            setSessionStatus(nyEl, sessions.includes('ny'));
            setSessionStatus(asianEl, sessions.includes('asian'));
            
            // Hourly win rate heatmap
            const hourlyPerf = status.hourly_performance || {};
            document.querySelectorAll('.heat-cell').forEach(cell => {
                const hour = parseInt(cell.dataset.hour);
                const winRate = hourlyPerf[hour];
                
                if (winRate === undefined || winRate === null) {
                    cell.style.background = 'rgba(255,255,255,0.05)';
                    cell.style.color = 'var(--text-secondary)';
                } else if (winRate >= 0.6) {
                    cell.style.background = 'rgba(16, 185, 129, 0.4)';
                    cell.style.color = 'var(--accent-green)';
                    cell.style.fontWeight = '600';
                } else if (winRate >= 0.4) {
                    cell.style.background = 'rgba(245, 158, 11, 0.3)';
                    cell.style.color = 'var(--accent-orange)';
                } else {
                    cell.style.background = 'rgba(239, 68, 68, 0.3)';
                    cell.style.color = 'var(--accent-red)';
                }
            });
            
            // Circuit breaker alert
            const circuitAlert = document.getElementById('circuitBreakerAlert');
            if (status.circuit_breaker_active) {
                circuitAlert.style.display = 'block';
            } else {
                circuitAlert.style.display = 'none';
            }
            
            // Pending signal alert
            const pendingAlert = document.getElementById('pendingSignalAlert');
            if (status.pending_signal && status.pending_signal.includes('Waiting')) {
                pendingAlert.style.display = 'block';
            } else {
                pendingAlert.style.display = 'none';
            }
            
            // Drawdown
            const drawdown = status.drawdown_percent || 0;
            document.getElementById('drawdownPercent').textContent = drawdown.toFixed(1) + '%';
            document.getElementById('drawdownPercent').style.color = 
                drawdown > 5 ? 'var(--accent-red)' : 
                drawdown > 2 ? 'var(--accent-orange)' : 'var(--accent-green)';
            
            // Consecutive losses
            const consecLosses = status.consecutive_losses || 0;
            document.getElementById('consecutiveLosses').textContent = consecLosses;
            document.getElementById('consecutiveLosses').style.color = 
                consecLosses >= 2 ? 'var(--accent-red)' : 'var(--accent-purple)';
            
            // Adaptive status (config already declared at top)
            document.getElementById('adaptiveStatus').textContent = 
                config.adaptive_strategy ? 'ON' : 'OFF';
            document.getElementById('adaptiveStatus').style.color = 
                config.adaptive_strategy ? 'var(--accent-green)' : 'var(--text-secondary)';
            
            // Strategy weights with color coding
            const perf = status.strategy_performance || {};
            
            function updateWeight(id, strategyKey) {
                const weight = perf[strategyKey]?.weight || 1.0;
                const el = document.getElementById(id);
                el.textContent = weight.toFixed(2);
                // Color: green > 1.0 (winning), red < 1.0 (losing), gray = 1.0 (neutral)
                if (weight > 1.0) {
                    el.style.color = 'var(--accent-green)';
                    el.parentElement.style.background = 'rgba(16, 185, 129, 0.2)';
                } else if (weight < 1.0) {
                    el.style.color = 'var(--accent-red)';
                    el.parentElement.style.background = 'rgba(239, 68, 68, 0.2)';
                } else {
                    el.style.color = 'var(--text-secondary)';
                    el.parentElement.style.background = 'rgba(255,255,255,0.05)';
                }
            }
            
            updateWeight('weightMA', 'ma_crossover');
            updateWeight('weightRSI', 'rsi');
            updateWeight('weightMACD', 'macd');
            updateWeight('weightBB', 'bollinger');
            updateWeight('weightSTOCH', 'stochastic');
        }
        
        // NEW: Update P&L Chart
        let pnlChart = null;
        let pnlData = [];
        let maxEquity = 100000; // Starting equity

        function initPnLChart() {
            const canvas = document.getElementById('pnlChart');
            if (!canvas) return;
            
            const ctx = canvas.getContext('2d');
            canvas.width = canvas.offsetWidth;
            canvas.height = canvas.offsetHeight;
            
            pnlChart = {
                ctx: ctx,
                width: canvas.width,
                height: canvas.height,
                data: []
            };
        }

        function updatePnLChart(status) {
            if (!pnlChart) return;
            
            const equity = status.equity || 100000;
            const pnl = status.pnl_today || 0;
            const timestamp = new Date();
            
            // Initialize with starting equity if empty
            if (pnlData.length === 0) {
                pnlData.push({
                    time: new Date(timestamp.getTime() - 60000), // 1 minute ago
                    equity: 100000,
                    pnl: 0
                });
            }
            
            // Add new data point
            pnlData.push({
                time: timestamp,
                equity: equity,
                pnl: pnl
            });
            
            // Keep only last 50 data points
            if (pnlData.length > 50) {
                pnlData.shift();
            }
            
            // Update max equity for scaling
            maxEquity = Math.max(maxEquity, equity);
            
            // Draw chart
            drawPnLChart();
            
            // Update stats
            document.getElementById('dailyPnL').textContent = formatCurrency(pnl);
            const drawdown = ((maxEquity - equity) / maxEquity * 100).toFixed(1);
            document.getElementById('maxDrawdown').textContent = drawdown + '%';
        }

        function drawPnLChart() {
            if (!pnlChart || pnlData.length < 2) return;
            
            const { ctx, width, height } = pnlChart;
            const padding = 20;
            const chartWidth = width - padding * 2;
            const chartHeight = height - padding * 2;
            
            // Clear canvas
            ctx.clearRect(0, 0, width, height);
            
            // Get current equity for color determination
            const currentEquity = pnlData[pnlData.length - 1].equity;
            
            // Calculate min/max for scaling
            const minEquity = Math.min(...pnlData.map(d => d.equity));
            const maxEquity = Math.max(...pnlData.map(d => d.equity));
            const equityRange = maxEquity - minEquity || 1;
            
            // Draw grid lines
            ctx.strokeStyle = 'rgba(255,255,255,0.1)';
            ctx.lineWidth = 1;
            for (let i = 0; i <= 4; i++) {
                const y = padding + (chartHeight / 4) * i;
                ctx.beginPath();
                ctx.moveTo(padding, y);
                ctx.lineTo(width - padding, y);
                ctx.stroke();
            }
            
            // Draw equity line
            ctx.strokeStyle = currentEquity >= 100000 ? '#10b981' : '#ef4444';
            ctx.lineWidth = 2;
            ctx.beginPath();
            
            pnlData.forEach((point, index) => {
                const x = padding + (chartWidth / (pnlData.length - 1)) * index;
                const y = padding + chartHeight - ((point.equity - minEquity) / equityRange) * chartHeight;
                
                if (index === 0) {
                    ctx.moveTo(x, y);
                } else {
                    ctx.lineTo(x, y);
                }
            });
            
            ctx.stroke();
            
            // Draw zero line (reference at 100000)
            const zeroY = padding + chartHeight - ((100000 - minEquity) / equityRange) * chartHeight;
            ctx.strokeStyle = 'rgba(255,255,255,0.3)';
            ctx.lineWidth = 1;
            ctx.setLineDash([5, 5]);
            ctx.beginPath();
            ctx.moveTo(padding, zeroY);
            ctx.lineTo(width - padding, zeroY);
            ctx.stroke();
            ctx.setLineDash([]);
            
            // Draw current value label
            ctx.fillStyle = currentEquity >= 100000 ? '#10b981' : '#ef4444';
            ctx.font = '12px monospace';
            ctx.fillText(formatCurrency(currentEquity), width - padding - 60, padding + 15);
        }

        // NEW: Update Signal Strength Meter
        function updateSignalStrengthMeter(status) {
            const buyStrength = document.getElementById('buyStrength');
            const sellStrength = document.getElementById('sellStrength');
            const buyPercent = document.getElementById('buyPercent');
            const sellPercent = document.getElementById('sellPercent');
            const signalDirection = document.getElementById('signalDirection');
            
            // Get ensemble voting data from logs (we'll simulate this)
            const lastSignal = status.last_signal || 'HOLD';
            const signalStrength = status.signal_strength || 0;
            
            // Simulate buy/sell percentages based on signal
            let buyPct = 0, sellPct = 0;
            if (lastSignal === 'BUY') {
                buyPct = signalStrength * 20; // 20% per strength point
                sellPct = 5;
            } else if (lastSignal === 'SELL') {
                sellPct = signalStrength * 20;
                buyPct = 5;
            } else {
                buyPct = sellPct = 10; // Neutral
            }
            
            // Update meters
            buyStrength.style.width = buyPct + '%';
            sellStrength.style.width = sellPct + '%';
            buyPercent.textContent = buyPct + '%';
            sellPercent.textContent = sellPct + '%';
            
            // Update direction
            if (buyPct > sellPct) {
                signalDirection.textContent = 'BUY PRESSURE';
                signalDirection.style.color = 'var(--accent-green)';
            } else if (sellPct > buyPct) {
                signalDirection.textContent = 'SELL PRESSURE';
                signalDirection.style.color = 'var(--accent-red)';
            } else {
                signalDirection.textContent = 'BALANCED';
                signalDirection.style.color = 'var(--text-secondary)';
            }
        }

        // NEW: Update Multi-Timeframe Analysis Display
        function updateMultiTimeframeDisplay(status) {
            const m15El = document.getElementById('m15Signal');
            const h1El = document.getElementById('h1Signal');
            const h4El = document.getElementById('h4Signal');
            const alignmentBar = document.getElementById('mtfAlignmentBar');
            const alignmentScore = document.getElementById('mtfAlignmentScore');
            
            // Extract MTF signals from signal history factors
            let m15Signal = '--';
            let h1Signal = '--';
            let h4Signal = '--';
            
            if (status.signal_history && status.signal_history.length > 0) {
                const latestSignal = status.signal_history[0];
                const factors = latestSignal.factors || [];
                
                // Parse MTF signals from factors
                factors.forEach(factor => {
                    if (factor.startsWith('M15_')) {
                        m15Signal = factor.substring(4, factor.indexOf('('));
                    } else if (factor.startsWith('H1_')) {
                        h1Signal = factor.substring(3, factor.indexOf('('));
                    } else if (factor.startsWith('H4_')) {
                        h4Signal = factor.substring(3, factor.indexOf('('));
                    }
                });
            }
            
            // Update signal displays
            if (m15El) {
                m15El.textContent = m15Signal;
                m15El.style.color = m15Signal === 'BUY' ? 'var(--accent-green)' : 
                                   m15Signal === 'SELL' ? 'var(--accent-red)' : 'var(--text-secondary)';
            }
            
            if (h1El) {
                h1El.textContent = h1Signal;
                h1El.style.color = h1Signal === 'BUY' ? 'var(--accent-green)' : 
                                   h1Signal === 'SELL' ? 'var(--accent-red)' : 'var(--text-secondary)';
            }
            
            if (h4El) {
                h4El.textContent = h4Signal;
                h4El.style.color = h4Signal === 'BUY' ? 'var(--accent-green)' : 
                                   h4Signal === 'SELL' ? 'var(--accent-red)' : 'var(--text-secondary)';
            }
            
            // Update alignment score
            const alignment = status.mtf_alignment_score || 0;
            const alignmentPercent = Math.round(alignment * 100);
            
            if (alignmentBar) {
                alignmentBar.style.width = alignmentPercent + '%';
            }
            
            if (alignmentScore) {
                alignmentScore.textContent = alignmentPercent + '%';
                alignmentScore.style.color = alignment > 0.7 ? 'var(--accent-green)' : 
                                           alignment > 0.4 ? 'var(--accent-orange)' : 'var(--accent-red)';
            }
        } // NEW: Update Strategy Performance Heatmap
        function updateStrategyHeatmap(status) {
            // Get real strategy performance from bot service
            const strategyPerf = status.strategy_performance || {};
            
            // Map strategy names
            const strategyMap = {
                'ma_crossover': 'MA',
                'rsi': 'RSI', 
                'macd': 'MACD',
                'bollinger': 'BB',
                'stochastic': 'STOCH'
            };
            
            // Update each strategy tile with real data
            Object.keys(strategyMap).forEach(key => {
                const shortName = strategyMap[key];
                const perf = strategyPerf[key] || { wins: 0, losses: 0, weight: 1.0 };
                const tile = document.getElementById('strategy' + shortName);
                const signalEl = document.getElementById(shortName.toLowerCase() + 'Signal');
                const perfEl = document.getElementById(shortName.toLowerCase() + 'Performance');
                
                if (tile && signalEl && perfEl) {
                    // Calculate win rate and performance
                    const totalTrades = perf.wins + perf.losses;
                    const winRate = totalTrades > 0 ? (perf.wins / totalTrades * 100) : 50;
                    const weight = perf.weight || 1.0;
                    
                    // Determine signal based on recent signal history
                    const lastSignal = status.signal_history?.[0];
                    let currentSignal = 'HOLD';
                    
                    // This would ideally come from real-time strategy signals
                    // For now, we'll simulate based on last signal and performance
                    if (lastSignal) {
                        if (winRate > 60 && weight > 1.0) {
                            currentSignal = lastSignal.signal || 'HOLD';
                        } else if (winRate < 40 && weight < 1.0) {
                            currentSignal = 'HOLD'; // Poor performing strategies stay on hold
                        } else {
                            currentSignal = lastSignal.signal || 'HOLD';
                        }
                    }
                    
                    // Update signal display
                    signalEl.textContent = currentSignal;
                    
                    // Update colors based on signal
                    if (currentSignal === 'BUY') {
                        signalEl.style.color = 'var(--accent-green)';
                        tile.style.borderColor = 'var(--accent-green)';
                    } else if (currentSignal === 'SELL') {
                        signalEl.style.color = 'var(--accent-red)';
                        tile.style.borderColor = 'var(--accent-red)';
                    } else {
                        signalEl.style.color = 'var(--text-secondary)';
                        tile.style.borderColor = 'var(--border-color)';
                    }
                    
                    // Update performance bar
                    perfEl.style.width = winRate + '%';
                    perfEl.style.background = winRate > 60 ? 'var(--accent-green)' : 
                                              winRate > 40 ? 'var(--accent-orange)' : 'var(--accent-red)';
                    
                    // Update percentage text
                    const pctText = tile.querySelector('div:nth-child(3)');
                    if (pctText) {
                        pctText.textContent = winRate.toFixed(0) + '%';
                        pctText.style.color = winRate > 60 ? 'var(--accent-green)' : 
                                           winRate > 40 ? 'var(--accent-orange)' : 'var(--accent-red)';
                    }
                    
                    // Update weight indicator
                    const weightIndicator = tile.querySelector('div:nth-child(4)');
                    if (weightIndicator) {
                        weightIndicator.title = `Weight: ${weight.toFixed(2)} | Wins: ${perf.wins} | Losses: ${perf.losses}`;
                    }
                }
            });
        }

        // NEW: Update Enhanced Trade History with Performance Analytics
        let tradeHistoryData = [];
        let performanceAnalytics = {
            totalTrades: 0,
            winningTrades: 0,
            losingTrades: 0,
            totalPnL: 0,
            bestTrade: 0,
            worstTrade: 0,
            avgWin: 0,
            avgLoss: 0,
            profitFactor: 0,
            sharpeRatio: 0,
            hourlyPerformance: {},
            sessionPerformance: {},
            exitReasons: {}
        };

        function updateTradeHistory(status) {
            // Add new trade when signal changes and position is opened
            const lastSignal = status.last_signal;
            const positions = status.positions || [];
            
            if (lastSignal !== 'HOLD' && positions.length > 0) {
                const newPosition = positions[positions.length - 1];
                
                // Check if this is a new trade
                const existingTrade = tradeHistoryData.find(t => t.ticket === newPosition.ticket);
                if (!existingTrade) {
                    const trade = {
                        time: new Date(),
                        signal: lastSignal,
                        entry: newPosition.price_open,
                        exit: '--',
                        pnl: newPosition.profit || 0,
                        notes: `${newPosition.type === 0 ? 'BUY' : 'SELL'} @ ${newPosition.price_open}`,
                        ticket: newPosition.ticket,
                        exitReason: 'Open',
                        partialCloses: [],
                        maxProfit: 0,
                        maxLoss: 0,
                        session: getCurrentTradingSession(),
                        hour: new Date().getHours()
                    };
                    tradeHistoryData.push(trade);
                    
                    // Update performance analytics
                    updatePerformanceAnalytics(trade);
                } else {
                    // Update existing trade
                    existingTrade.pnl = newPosition.profit || 0;
                    existingTrade.maxProfit = Math.max(existingTrade.maxProfit, newPosition.profit || 0);
                    existingTrade.maxLoss = Math.min(existingTrade.maxLoss, newPosition.profit || 0);
                    
                    // Check for exit conditions
                    if (newPosition.profit < -50 || newPosition.profit > 100) {
                        existingTrade.exit = newPosition.price_current || '--';
                        existingTrade.exitReason = determineExitReason(newPosition);
                        existingTrade.notes += ` | Closed at ${newPosition.price_current} (${existingTrade.exitReason})`;
                        
                        // Update final analytics
                        finalizeTradeAnalytics(existingTrade);
                    }
                }
            }
            
            // Keep only last 20 trades for better performance
            if (tradeHistoryData.length > 20) {
                tradeHistoryData.shift();
            }
            
            // Update table
            const tbody = document.getElementById('tradeHistoryTable');
            if (tradeHistoryData.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">No trades yet today</td></tr>';
                return;
            }
            
            tbody.innerHTML = tradeHistoryData.slice().reverse().map(trade => {
                const time = trade.time.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                const signalClass = trade.signal === 'BUY' ? 'badge-buy' : 'badge-sell';
                const pnlClass = trade.pnl >= 0 ? 'positive' : 'negative';
                const exitReasonColor = getExitReasonColor(trade.exitReason);
                
                return `<tr>
                    <td>${time}</td>
                    <td><span class="badge ${signalClass}">${trade.signal}</span></td>
                    <td>${formatNumber(trade.entry, 5)}</td>
                    <td>${trade.exit}</td>
                    <td class="${pnlClass}">${formatCurrency(trade.pnl)}</td>
                    <td style="font-size: 10px; color: var(--text-secondary);">
                        <div>${trade.notes}</div>
                        <div style="color: ${exitReasonColor}; font-weight: 600;">${trade.exitReason}</div>
                    </td>
                </tr>`;
            }).join('');
            
            // Update performance analytics display
            updatePerformanceDisplay();
        }

        function getCurrentTradingSession() {
            const hour = new Date().getHours();
            if (hour >= 8 && hour < 17) return 'London';
            if (hour >= 13 && hour < 22) return 'NY';
            if (hour >= 0 && hour < 9) return 'Asian';
            return 'Off Hours';
        }

        function determineExitReason(position) {
            const pnl = position.profit || 0;
            if (pnl > 50) return '1R TP Hit';
            if (pnl > 100) return '2R TP Hit';
            if (pnl < -30) return 'Stop Loss';
            if (position.comment && position.comment.includes('Partial')) return 'Partial Close';
            if (position.comment && position.comment.includes('Signal')) return 'Signal Exit';
            if (position.comment && position.comment.includes('Trail')) return 'Trailing Stop';
            return 'Manual Close';
        }

        function getExitReasonColor(reason) {
            switch(reason) {
                case '1R TP Hit': return 'var(--accent-green)';
                case '2R TP Hit': return 'var(--accent-green)';
                case 'Stop Loss': return 'var(--accent-red)';
                case 'Partial Close': return 'var(--accent-orange)';
                case 'Signal Exit': return 'var(--accent-cyan)';
                case 'Trailing Stop': return 'var(--accent-purple)';
                default: return 'var(--text-secondary)';
            }
        }

        function updatePerformanceAnalytics(trade) {
            performanceAnalytics.totalTrades++;
            performanceAnalytics.totalPnL += trade.pnl;
            
            if (trade.pnl > 0) {
                performanceAnalytics.winningTrades++;
                performanceAnalytics.bestTrade = Math.max(performanceAnalytics.bestTrade, trade.pnl);
                performanceAnalytics.avgWin = (performanceAnalytics.avgWin * (performanceAnalytics.winningTrades - 1) + trade.pnl) / performanceAnalytics.winningTrades;
            } else {
                performanceAnalytics.losingTrades++;
                performanceAnalytics.worstTrade = Math.min(performanceAnalytics.worstTrade, trade.pnl);
                performanceAnalytics.avgLoss = (performanceAnalytics.avgLoss * (performanceAnalytics.losingTrades - 1) + trade.pnl) / performanceAnalytics.losingTrades;
            }
            
            // Track exit reasons
            performanceAnalytics.exitReasons[trade.exitReason] = (performanceAnalytics.exitReasons[trade.exitReason] || 0) + 1;
            
            // Track session performance
            const session = trade.session;
            if (!performanceAnalytics.sessionPerformance[session]) {
                performanceAnalytics.sessionPerformance[session] = { wins: 0, losses: 0, pnl: 0 };
            }
            if (trade.pnl > 0) {
                performanceAnalytics.sessionPerformance[session].wins++;
            } else {
                performanceAnalytics.sessionPerformance[session].losses++;
            }
            performanceAnalytics.sessionPerformance[session].pnl += trade.pnl;
            
            // Track hourly performance
            const hour = trade.hour;
            if (!performanceAnalytics.hourlyPerformance[hour]) {
                performanceAnalytics.hourlyPerformance[hour] = { wins: 0, losses: 0, pnl: 0 };
            }
            if (trade.pnl > 0) {
                performanceAnalytics.hourlyPerformance[hour].wins++;
            } else {
                performanceAnalytics.hourlyPerformance[hour].losses++;
            }
            performanceAnalytics.hourlyPerformance[hour].pnl += trade.pnl;
        }

        function finalizeTradeAnalytics(trade) {
            // Calculate profit factor
            const totalWins = performanceAnalytics.avgWin * performanceAnalytics.winningTrades;
            const totalLosses = Math.abs(performanceAnalytics.avgLoss * performanceAnalytics.losingTrades);
            performanceAnalytics.profitFactor = totalLosses > 0 ? totalWins / totalLosses : 0;
            
            // Calculate Sharpe ratio (simplified)
            const avgReturn = performanceAnalytics.totalPnL / performanceAnalytics.totalTrades;
            const returns = tradeHistoryData.map(t => t.pnl);
            const stdDev = Math.sqrt(returns.reduce((sq, n) => sq + Math.pow(n - avgReturn, 2), 0) / performanceAnalytics.totalTrades);
            performanceAnalytics.sharpeRatio = stdDev > 0 ? avgReturn / stdDev : 0;
        }

        function updatePerformanceDisplay() {
            // Update performance summary in the UI
            const perfSummary = document.getElementById('performanceSummary');
            if (perfSummary) {
                const winRate = performanceAnalytics.totalTrades > 0 ? 
                    (performanceAnalytics.winningTrades / performanceAnalytics.totalTrades * 100).toFixed(1) : 0;
                
                perfSummary.innerHTML = `
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; font-size: 11px;">
                        <div style="text-align: center; padding: 8px; background: var(--bg-secondary); border-radius: 6px;">
                            <div style="color: var(--text-secondary);">Win Rate</div>
                            <div style="font-weight: 700; color: var(--accent-green);">${winRate}%</div>
                        </div>
                        <div style="text-align: center; padding: 8px; background: var(--bg-secondary); border-radius: 6px;">
                            <div style="color: var(--text-secondary);">Profit Factor</div>
                            <div style="font-weight: 700; color: var(--accent-cyan);">${performanceAnalytics.profitFactor.toFixed(2)}</div>
                        </div>
                        <div style="text-align: center; padding: 8px; background: var(--bg-secondary); border-radius: 6px;">
                            <div style="color: var(--text-secondary);">Best Hour</div>
                            <div style="font-weight: 700; color: var(--accent-orange);">${getBestHour()}</div>
                        </div>
                        <div style="text-align: center; padding: 8px; background: var(--bg-secondary); border-radius: 6px;">
                            <div style="color: var(--text-secondary);">Best Session</div>
                            <div style="font-weight: 700; color: var(--accent-purple);">${getBestSession()}</div>
                        </div>
                    </div>
                `;
            }
        }

        function getBestHour() {
            let bestHour = 0;
            let bestPnL = -Infinity;
            for (const [hour, data] of Object.entries(performanceAnalytics.hourlyPerformance)) {
                if (data.pnl > bestPnL) {
                    bestPnL = data.pnl;
                    bestHour = parseInt(hour);
                }
            }
            return bestHour > 0 ? `${bestHour}:00` : 'N/A';
        }

        function getBestSession() {
            let bestSession = 'None';
            let bestPnL = -Infinity;
            for (const [session, data] of Object.entries(performanceAnalytics.sessionPerformance)) {
                if (data.pnl > bestPnL) {
                    bestPnL = data.pnl;
                    bestSession = session;
                }
            }
            return bestSession;
        }
        
        // Toggle intelligent features section
        function toggleIntelligentFeatures() {
            const content = document.getElementById('intelligentFeaturesContent');
            const toggle = document.getElementById('featuresToggle');
            if (content.style.display === 'none') {
                content.style.display = 'block';
                toggle.style.transform = 'rotate(0deg)';
            } else {
                content.style.display = 'none';
                toggle.style.transform = 'rotate(-90deg)';
            }
        }

        // Update trade stats
        function updateTradeStats(status, positions) {
            document.getElementById('tradesToday').textContent = status.total_trades_today || 0;
            document.getElementById('pnlToday').textContent = formatCurrency(status.pnl_today || 0);
            document.getElementById('positionsOpen').textContent = positions ? positions.length : 0;
            
            // Update win rate
            const winRate = status.win_rate || 50.0;
            const totalTrades = status.total_trades || 0;
            document.getElementById('winRate').textContent = winRate.toFixed(1) + '%';
            document.getElementById('winLossStats').textContent = 
                `${status.winning_trades || 0}W / ${status.losing_trades || 0}L (${totalTrades} total)`;
            
            // Color code P&L
            const pnlEl = document.getElementById('pnlToday');
            pnlEl.style.color = (status.pnl_today || 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
            
            // Color code win rate
            const winRateEl = document.getElementById('winRate');
            winRateEl.style.color = winRate >= 50 ? 'var(--accent-green)' : 'var(--accent-orange)';
        }

        // Fetch bot status
        async function fetchBotStatus() {
            try {
                const response = await fetch(`${API_BASE}/api/v1/bot/status`);
                const status = await response.json();
                
                botEnabled = status.running;
                document.getElementById('botToggle').checked = botEnabled;
                document.getElementById('botState').textContent = botEnabled ? 'Running' : 'Stopped';
                document.getElementById('botState').style.color = botEnabled ? 'var(--accent-green)' : 'var(--accent-red)';
                
                // Update signal display
                updateSignal(status);
                updateSignalHistory(status.signal_history);
                updateIntelligentFeatures(status);
                
                // NEW: Update enhanced UI components
                updatePnLChart(status);
                updateSignalStrengthMeter(status);
                updateMultiTimeframeDisplay(status);
                updateStrategyHeatmap(status);
                updateTradeHistory(status);
                
                // Get positions for stats
                const dashResponse = await fetch(`${API_BASE}/api/v1/dashboard/data`);
                const dashData = await dashResponse.json();
                updateTradeStats(status, dashData.positions);
                
                if (status.config) {
                    botConfig = status.config;
                    document.getElementById('botSymbol').textContent = botConfig.symbol;
                    document.getElementById('botStrategy').textContent = botConfig.strategy.replace('_', ' ').toUpperCase();
                    document.getElementById('botTimeframe').value = botConfig.timeframe; // Set dropdown value
                    document.getElementById('botVolume').textContent = botConfig.volume;
                }
            } catch (err) {
                console.error('Bot status error:', err);
            }
        }

        // Timeframe change handler
        async function onTimeframeChange() {
            const newTimeframe = document.getElementById('botTimeframe').value;
            console.log('Changing timeframe to:', newTimeframe);
            
            try {
                const response = await fetch(`${API_BASE}/api/v1/bot/config`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ timeframe: newTimeframe })
                });
                
                if (!response.ok) {
                    throw new Error('Failed to update timeframe');
                }
                
                console.log('Timeframe updated successfully');
            } catch (err) {
                console.error('Timeframe update error:', err);
            }
        }

        // Add event listener for timeframe change
        document.addEventListener('DOMContentLoaded', function() {
            const timeframeSelect = document.getElementById('botTimeframe');
            if (timeframeSelect) {
                timeframeSelect.addEventListener('change', onTimeframeChange);
            }
        });

        // Theme Toggle Functionality
        function initTheme() {
            const savedTheme = localStorage.getItem('dashboard-theme') || 'dark';
            document.documentElement.setAttribute('data-theme', savedTheme);
            updateThemeIcon(savedTheme);
        }

        function toggleTheme() {
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('dashboard-theme', newTheme);
            updateThemeIcon(newTheme);
        }

        function updateThemeIcon(theme) {
            const icon = document.getElementById('themeIcon');
            icon.textContent = theme === 'dark' ? '☀️' : '🌙';
        }

        // Initialize theme on load
        initTheme();

        // Initialize P&L chart
        initPnLChart();

        // Enhanced Performance Analytics
        async function fetchEnhancedPerformance() {
            try {
                const response = await fetch(`${API_BASE}/api/v1/dashboard/performance?days=30`);
                const data = await response.json();
                
                if (data.success) {
                    updateEnhancedPerformanceDisplay(data);
                }
            } catch (error) {
                console.error('Error fetching enhanced performance:', error);
            }
        }

        function updateEnhancedPerformanceDisplay(data) {
            const metrics = data.metrics;
            
            // Update basic metrics
            updateElement('perfProfitFactor', metrics.advanced.profit_factor?.toFixed(2) || '--');
            updateElement('perfSharpeRatio', metrics.advanced.sharpe_ratio?.toFixed(2) || '--');
            updateElement('perfRiskReward', metrics.risk.risk_reward_ratio?.toFixed(2) || '--');
            updateElement('perfAvgWin', formatCurrency(metrics.advanced.avg_win || 0));
            updateElement('perfAvgLoss', formatCurrency(metrics.advanced.avg_loss || 0));
            updateElement('perfConsecWins', metrics.advanced.consecutive_wins || '--');
            
            // Update session performance
            updateElement('londonPnL', formatCurrency(metrics.sessions.london_pnl || 0));
            updateElement('nyPnL', formatCurrency(metrics.sessions.ny_pnl || 0));
            updateElement('asianPnL', formatCurrency(metrics.sessions.asian_pnl || 0));
            
            // Update drawdown
            const maxDD = metrics.advanced.max_drawdown_percent || 0;
            updateElement('maxDrawdownAmount', `${maxDD.toFixed(2)}%`);
            const drawdownBar = document.getElementById('drawdownBar');
            if (drawdownBar) {
                drawdownBar.style.width = `${Math.min(maxDD * 10, 100)}%`;
            }
            
            // Update trade duration
            const avgDuration = metrics.advanced.avg_trade_duration || 0;
            updateElement('avgTradeDuration', `${avgDuration.toFixed(0)} min`);
            updateElement('longestWin', `${metrics.advanced.largest_win > 0 ? '+' : ''}${formatCurrency(metrics.advanced.largest_win || 0)}`);
            updateElement('longestLoss', formatCurrency(metrics.advanced.largest_loss || 0));
        }

        // Trading Chart Initialization
        let tradingChart = null;
        let chartUpdateInterval = null;

        function initializeTradingChart() {
            try {
                tradingChart = new TradingChart('tradingChart', {
                    width: 800,
                    height: 400,
                    backgroundColor: 'var(--bg-secondary)',
                    gridColor: 'rgba(255, 255, 255, 0.1)',
                    textColor: 'var(--text-primary)',
                    upColor: '#22c55e',
                    downColor: '#ef4444',
                    volumeColor: 'rgba(34, 197, 94, 0.6)',
                    maColors: ['#06b6d4', '#f59e0b', '#a855f7']
                });

                // Setup chart event handlers
                setupChartEvents();
                
                // Start real-time updates
                startChartUpdates();
                
                console.log('Trading chart initialized successfully');
            } catch (error) {
                console.error('Error initializing trading chart:', error);
            }
        }

        function setupChartEvents() {
            // Timeframe selector
            const timeframeSelector = document.getElementById('timeframeSelector');
            if (timeframeSelector) {
                timeframeSelector.addEventListener('change', (e) => {
                    changeChartTimeframe(e.target.value);
                });
            }

            // Indicator toggles
            const indicatorButtons = document.querySelectorAll('.indicator-btn');
            indicatorButtons.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const indicator = e.target.dataset.indicator;
                    toggleIndicator(indicator);
                });
            });

            // Chart controls
            const zoomInBtn = document.getElementById('zoomIn');
            const zoomOutBtn = document.getElementById('zoomOut');
            const resetBtn = document.getElementById('resetChart');

            if (zoomInBtn) zoomInBtn.addEventListener('click', () => tradingChart.zoom(-1));
            if (zoomOutBtn) zoomOutBtn.addEventListener('click', () => tradingChart.zoom(1));
            if (resetBtn) resetBtn.addEventListener('click', resetChartView);
        }

        function toggleIndicator(indicator) {
            if (!tradingChart) return;
            
            tradingChart.toggleIndicator(indicator);
            
            // Update button state
            const btn = document.querySelector(`[data-indicator="${indicator}"]`);
            if (btn) {
                btn.classList.toggle('active');
            }
        }

        function changeChartTimeframe(timeframe) {
            fetch(`${API_BASE}/api/v1/dashboard/chart/timeframe`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ timeframe: timeframe })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success && tradingChart) {
                    tradingChart.setTimeframe(timeframe);
                    updateChartInfo(data.data);
                }
            })
            .catch(error => console.error('Error changing timeframe:', error));
        }

        function resetChartView() {
            if (tradingChart) {
                tradingChart.viewport.startIndex = 0;
                tradingChart.viewport.endIndex = 100;
                tradingChart.viewport.candleWidth = 8;
                tradingChart.draw();
            }
        }

        function startChartUpdates() {
            // Fetch initial chart data
            fetchChartData();
            
            // Update every 2 seconds
            chartUpdateInterval = setInterval(fetchChartData, 2000);
            
            // Listen for trade alerts from chart
            document.addEventListener('tradeAlert', function(e) {
                showTradeAlert(e.detail);
            });
        }
        
        function showTradeAlert(alert) {
            // Create toast notification for high-confluence trade setup
            const toast = document.createElement('div');
            toast.className = `trade-alert-toast ${alert.urgency}`;
            toast.innerHTML = `
                <div class="alert-header">
                    <span class="alert-icon">${alert.type === 'buy' ? '🟢' : '🔴'}</span>
                    <span class="alert-type">${alert.type.toUpperCase()} SIGNAL</span>
                    <span class="alert-score">Score: ${alert.score}</span>
                </div>
                <div class="alert-levels">
                    <div>Entry: ${alert.entry}</div>
                    <div>SL: ${alert.stop}</div>
                    <div>TP: ${alert.target} (${alert.rr}:1)</div>
                </div>
                <div class="alert-reasons">${alert.reasons.join(' • ')}</div>
            `;
            
            // Add to container
            let container = document.getElementById('tradeAlerts');
            if (!container) {
                container = document.createElement('div');
                container.id = 'tradeAlerts';
                container.className = 'trade-alerts-container';
                document.body.appendChild(container);
            }
            
            container.appendChild(toast);
            
            // Auto-remove after 10 seconds
            setTimeout(() => {
                toast.remove();
            }, 10000);
            
            // Also log to console
            console.log('🎯 Trade Alert:', alert);
        }

        function fetchChartData() {
            fetch(`${API_BASE}/api/v1/dashboard/chart/data`)
                .then(response => response.json())
                .then(data => {
                    if (data.success && tradingChart) {
                        tradingChart.updateData(data.data);
                        updateChartInfo(data.data);
                        updateCurrentPrice(data.data.currentPrice);
                    }
                })
                .catch(error => console.error('Error fetching chart data:', error));
        }

        function updateChartInfo(chartData) {
            const chartInfo = document.getElementById('chartInfo');
            if (!chartInfo || !chartData.candles || chartData.candles.length === 0) {
                if (chartInfo) chartInfo.style.display = 'none';
                return;
            }

            const lastCandle = chartData.candles[chartData.candles.length - 1];
            if (!lastCandle) return;

            const price = lastCandle.close;
            const change = lastCandle.close - lastCandle.open;
            const changePercent = (change / lastCandle.open) * 100;
            const time = new Date(lastCandle.time).toLocaleTimeString();
            const timeframe = chartData.timeframe || 'H1';

            document.getElementById('chartTimeframe').textContent = timeframe;
            document.getElementById('chartPrice').textContent = price.toFixed(2);
            document.getElementById('chartTime').textContent = time;
            document.getElementById('chartChange').textContent = `${changePercent >= 0 ? '+' : ''}${changePercent.toFixed(2)}%`;
            document.getElementById('chartChange').style.color = changePercent >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
            
            chartInfo.style.display = 'block';
        }

        function updateCurrentPrice(price) {
            const currentPriceEl = document.getElementById('currentPrice');
            if (currentPriceEl) {
                currentPriceEl.textContent = price.toFixed(2);
            }
        }

        function addTradeToChart(tradeData) {
            fetch(`${API_BASE}/api/v1/dashboard/chart/trade`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(tradeData)
            })
            .then(response => response.json())
            .then(data => {
                console.log('Trade added to chart:', data);
            })
            .catch(error => console.error('Error adding trade to chart:', error));
        }

        function addLevelToChart(levelData) {
            fetch(`${API_BASE}/api/v1/dashboard/chart/level`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(levelData)
            })
            .then(response => response.json())
            .then(data => {
                console.log('Level added to chart:', data);
            })
            .catch(error => console.error('Error adding level to chart:', error));
        }

        // Real-time WebSocket Event Handlers
        function setupRealtimeEventHandlers() {
            if (!window.realtimeClient) {
                console.error('Realtime client not available');
                return;
            }
            
            // Handle price updates
            window.realtimeClient.on('price_update', (data) => {
                console.log('📈 Real-time price update:', data);
                // Price updates are handled automatically by the client
            });
            
            // Handle chart updates
            window.realtimeClient.on('chart_update', (data) => {
                console.log('📊 Real-time chart update:', data);
                // Chart updates are handled automatically by the client
            });
            
            // Handle trade updates
            window.realtimeClient.on('trade_update', (data) => {
                console.log('💼 Real-time trade update:', data);
                // Trade updates are handled automatically by the client
            });
            
            // Handle analytics updates
            window.realtimeClient.on('analytics_update', (data) => {
                console.log('📈 Real-time analytics update:', data);
                // Analytics updates are handled automatically by the client
            });
            
            // Handle trade notifications
            window.realtimeClient.on('trade_notification', (data) => {
                console.log('🔔 Trade notification:', data);
                // Show enhanced trade notification
                showEnhancedTradeNotification(data.data);
            });
            
            // Handle alerts
            window.realtimeClient.on('alert', (data) => {
                console.log('🚨 Alert:', data);
                // Show enhanced alert notification
                showEnhancedAlert(data);
            });
            
            // Handle connection status
            window.realtimeClient.on('connection_status', (data) => {
                console.log('🔌 Connection status:', data);
                updateConnectionStatus(data.connected);
            });
            
            // Handle initial data
            window.realtimeClient.on('initial_chart_data', (data) => {
                console.log('📊 Initial chart data received');
                if (window.tradingChart) {
                    window.tradingChart.setData(data.data);
                }
            });
            
            console.log('✅ Real-time event handlers setup complete');
        }
        
        // Show enhanced trade notification
        function showEnhancedTradeNotification(tradeData) {
            const action = tradeData.action.toUpperCase();
            const symbol = tradeData.symbol;
            const volume = tradeData.volume;
            const result = tradeData.result;
            
            if (result.success) {
                // Create detailed notification
                const notification = document.createElement('div');
                notification.className = 'trade-notification success';
                notification.innerHTML = `
                    <div class="trade-notification-header">
                        <span class="trade-action ${action.toLowerCase()}">${action}</span>
                        <span class="trade-symbol">${symbol}</span>
                        <span class="trade-volume">${volume}</span>
                    </div>
                    <div class="trade-notification-body">
                        <span class="trade-price">Price: ${result.price || 'N/A'}</span>
                        <span class="trade-ticket">Ticket: ${result.ticket || 'N/A'}</span>
                    </div>
                `;
                
                // Add to notifications
                addNotificationToPanel(notification);
                
                // Update positions immediately
                setTimeout(() => fetchDashboard(), 500);
            } else {
                showNotification(`Trade failed: ${result.error}`, 'error');
            }
        }
        
        // Show enhanced alert
        function showEnhancedAlert(alertData) {
            const alertTypes = {
                'info': '📢',
                'warning': '⚠️',
                'error': '🚨',
                'success': '✅'
            };
            
            const icon = alertTypes[alertData.alertType] || '📢';
            
            const notification = document.createElement('div');
            notification.className = `alert-notification ${alertData.alertType}`;
            notification.innerHTML = `
                <div class="alert-icon">${icon}</div>
                <div class="alert-content">
                    <div class="alert-message">${alertData.message}</div>
                    <div class="alert-time">${new Date(alertData.timestamp).toLocaleTimeString()}</div>
                </div>
            `;
            
            addNotificationToPanel(notification);
        }
        
        // Add notification to panel
        function addNotificationToPanel(notification) {
            const panel = document.getElementById('notification-panel') || createNotificationPanel();
            panel.insertBefore(notification, panel.firstChild);
            
            // Remove old notifications if too many
            while (panel.children.length > 10) {
                panel.removeChild(panel.lastChild);
            }
            
            // Auto remove after 10 seconds
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, 10000);
        }
        
        // Create notification panel
        function createNotificationPanel() {
            const panel = document.createElement('div');
            panel.id = 'notification-panel';
            panel.className = 'notification-panel';
            document.body.appendChild(panel);
            return panel;
        }
        
        // Update connection status indicator
        function updateConnectionStatus(connected) {
            const statusEl = document.getElementById('connection-status');
            if (statusEl) {
                statusEl.className = connected ? 'connection-status connected' : 'connection-status disconnected';
                statusEl.textContent = connected ? '🟢 Live' : '🔴 Offline';
            }
            
            // Update chart real-time indicator
            const chartStatusEl = document.getElementById('chart-realtime-status');
            if (chartStatusEl) {
                chartStatusEl.className = connected ? 'realtime-indicator active' : 'realtime-indicator inactive';
                chartStatusEl.textContent = connected ? '🟢 Real-time' : '🔴 Polling';
            }
        }
        
        // Show notification (fallback)
        function showNotification(message, type = 'info') {
            console.log(`[${type.toUpperCase()}] ${message}`);
            
            // Create toast notification
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            toast.textContent = message;
            
            document.body.appendChild(toast);
            
            // Remove after 3 seconds
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.remove();
                }
            }, 3000);
        }

        // Initialize
        initializeTradingChart();
        setupRealtimeEventHandlers();
        fetchDashboard();
        fetchBotStatus();
        fetchEnhancedPerformance();
        
        // Reduce polling frequency since we have real-time updates
        setInterval(fetchDashboard, 5000);  // Reduced from 2 seconds
        setInterval(fetchBotStatus, 10000); // Reduced from 5 seconds  
        setInterval(fetchEnhancedPerformance, 30000); // Reduced from 10 seconds
    </script>
</body>
</html>
'''
