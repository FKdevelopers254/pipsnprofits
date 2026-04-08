"""
Real-time WebSocket streaming for sub-second price updates and notifications
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Set
from fastapi import WebSocket, WebSocketDisconnect
import websockets
from src.services.mt5_service import mt5_manager
from src.services.chart_service import chart_data_service
from src.services.performance_analytics import performance_analytics

logger = logging.getLogger(__name__)

class RealtimeManager:
    """Manages real-time WebSocket connections and data streaming"""
    
    def __init__(self):
        self.connections: Set[WebSocket] = set()
        self.subscription_data: Dict[str, Set[str]] = {
            'prices': set(),
            'trades': set(),
            'chart': set(),
            'analytics': set()
        }
        self.is_streaming = False
        self.stream_task = None
        
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept WebSocket connection and register client"""
        await websocket.accept()
        self.connections.add(websocket)
        logger.info(f"WebSocket client connected: {client_id} (Total: {len(self.connections)})")
        
        # Send initial data
        await self.send_initial_data(websocket, client_id)
        
    async def disconnect(self, websocket: WebSocket, client_id: str):
        """Remove WebSocket connection and cleanup subscriptions"""
        self.connections.discard(websocket)
        
        # Remove from all subscriptions
        for sub_type in self.subscription_data:
            self.subscription_data[sub_type].discard(client_id)
            
        logger.info(f"WebSocket client disconnected: {client_id} (Total: {len(self.connections)})")
        
        # Stop streaming if no clients
        if not self.connections and self.stream_task:
            self.stream_task.cancel()
            self.is_streaming = False
            logger.info("Stopped real-time streaming (no clients)")
    
    async def subscribe(self, websocket: WebSocket, client_id: str, data_type: str):
        """Subscribe client to specific data type"""
        if data_type in self.subscription_data:
            self.subscription_data[data_type].add(client_id)
            await websocket.send_json({
                "type": "subscription_confirmed",
                "data_type": data_type,
                "client_id": client_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            logger.info(f"Client {client_id} subscribed to {data_type}")
            
            # Start streaming if not already running
            if not self.is_streaming and self.connections:
                self.stream_task = asyncio.create_task(self.start_streaming())
                self.is_streaming = True
        else:
            await websocket.send_json({
                "type": "error",
                "message": f"Invalid subscription type: {data_type}"
            })
    
    async def unsubscribe(self, websocket: WebSocket, client_id: str, data_type: str):
        """Unsubscribe client from specific data type"""
        if data_type in self.subscription_data:
            self.subscription_data[data_type].discard(client_id)
            await websocket.send_json({
                "type": "unsubscription_confirmed", 
                "data_type": data_type,
                "client_id": client_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            logger.info(f"Client {client_id} unsubscribed from {data_type}")
    
    async def send_initial_data(self, websocket: WebSocket, client_id: str):
        """Send initial data snapshot to newly connected client"""
        try:
            # Send current chart data
            chart_data = chart_data_service.get_chart_data()
            await websocket.send_json({
                "type": "initial_chart_data",
                "data": chart_data,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Send current performance analytics
            performance_data = performance_analytics.calculate_metrics(days=30)
            performance_dict = {
                'total_trades': performance_data.total_trades,
                'total_pnl': performance_data.total_pnl,
                'winning_trades': performance_data.winning_trades,
                'losing_trades': performance_data.losing_trades,
                'win_rate': performance_data.win_rate,
                'avg_win': performance_data.avg_win,
                'avg_loss': performance_data.avg_loss,
                'profit_factor': performance_data.profit_factor,
                'sharpe_ratio': performance_data.sharpe_ratio,
                'max_drawdown': performance_data.max_drawdown,
                'risk_reward_ratio': performance_data.risk_reward_ratio
            }
            await websocket.send_json({
                "type": "initial_performance_data", 
                "data": performance_dict,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Send current positions
            if mt5_manager._initialized:
                positions_result = mt5_manager.get_open_positions()
                positions = positions_result.get('positions', []) if positions_result.get('success') else []
                await websocket.send_json({
                    "type": "initial_positions",
                    "data": {"positions": positions},
                    "timestamp": datetime.utcnow().isoformat()
                })
                
        except Exception as e:
            logger.error(f"Error sending initial data to {client_id}: {e}")
    
    async def start_streaming(self):
        """Main streaming loop - updates every 500ms for real-time feel"""
        logger.info("🚀 Starting real-time WebSocket streaming (500ms intervals)")
        
        try:
            while self.connections and self.is_streaming:
                start_time = asyncio.get_event_loop().time()
                
                # Stream price updates
                if self.subscription_data['prices']:
                    await self.stream_price_updates()
                
                # Stream chart updates  
                if self.subscription_data['chart']:
                    await self.stream_chart_updates()
                
                # Stream trade updates
                if self.subscription_data['trades']:
                    await self.stream_trade_updates()
                
                # Stream analytics updates
                if self.subscription_data['analytics']:
                    await self.stream_analytics_updates()
                
                # Calculate processing time and adjust delay
                processing_time = asyncio.get_event_loop().time() - start_time
                delay = max(0.1, 0.5 - processing_time)  # Target 500ms, minimum 100ms
                
                await asyncio.sleep(delay)
                
        except asyncio.CancelledError:
            logger.info("Real-time streaming cancelled")
        except Exception as e:
            logger.error(f"Error in streaming loop: {e}")
            self.is_streaming = False
    
    async def stream_price_updates(self):
        """Stream real-time price updates"""
        try:
            if not mt5_manager._initialized:
                return
                
            # Get current prices for subscribed symbols
            symbols = ['XAUUSD']  # Can be expanded
            price_data = {}
            
            for symbol in symbols:
                tick = mt5_manager.mt5.symbol_info_tick(symbol)
                if tick:
                    price_data[symbol] = {
                        'bid': tick.bid,
                        'ask': tick.ask, 
                        'spread': tick.ask - tick.bid,
                        'time': tick.time,
                        'volume': tick.volume,
                        'change': 0  # Calculate change from previous tick
                    }
            
            if price_data:
                message = {
                    "type": "price_update",
                    "data": price_data,
                    "timestamp": datetime.utcnow().isoformat()
                }
                await self.broadcast_to_subscribers('prices', message)
                
        except Exception as e:
            logger.error(f"Error streaming price updates: {e}")
    
    async def stream_chart_updates(self):
        """Stream real-time chart data updates"""
        try:
            # Get latest chart data
            chart_data = chart_data_service.get_chart_data()
            
            if chart_data and chart_data.get('candles'):
                # Send only the latest candle to reduce bandwidth
                latest_candle = chart_data['candles'][-1] if chart_data['candles'] else None
                
                if latest_candle:
                    message = {
                        "type": "chart_update",
                        "data": {
                            "latest_candle": latest_candle,
                            "indicators": chart_data.get('indicators', {}),
                            "volume": chart_data.get('volume', [])[-1] if chart_data.get('volume') else None
                        },
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    await self.broadcast_to_subscribers('chart', message)
                    
        except Exception as e:
            logger.error(f"Error streaming chart updates: {e}")
    
    async def stream_trade_updates(self):
        """Stream real-time trade updates"""
        try:
            if not mt5_manager._initialized:
                return
                
            # Get current positions
            positions_result = mt5_manager.get_open_positions()
            positions = positions_result.get('positions', []) if positions_result.get('success') else []
            
            message = {
                "type": "trade_update",
                "data": {
                    "positions": positions,
                    "position_count": len(positions),
                    "total_pnl": sum(pos.get('profit', 0) for pos in positions)
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            await self.broadcast_to_subscribers('trades', message)
            
        except Exception as e:
            logger.error(f"Error streaming trade updates: {e}")
    
    async def stream_analytics_updates(self):
        """Stream real-time performance analytics"""
        try:
            # Get latest performance metrics
            performance_data = performance_analytics.calculate_metrics(days=1)
            performance_dict = {
                'total_trades': performance_data.total_trades,
                'total_pnl': performance_data.total_pnl,
                'winning_trades': performance_data.winning_trades,
                'losing_trades': performance_data.losing_trades,
                'win_rate': performance_data.win_rate,
                'avg_win': performance_data.avg_win,
                'avg_loss': performance_data.avg_loss,
                'profit_factor': performance_data.profit_factor,
                'sharpe_ratio': performance_data.sharpe_ratio,
                'max_drawdown': performance_data.max_drawdown,
                'risk_reward_ratio': performance_data.risk_reward_ratio
            }
            
            message = {
                "type": "analytics_update",
                "data": performance_dict,
                "timestamp": datetime.utcnow().isoformat()
            }
            await self.broadcast_to_subscribers('analytics', message)
            
        except Exception as e:
            logger.error(f"Error streaming analytics updates: {e}")
    
    async def broadcast_to_subscribers(self, subscription_type: str, message: dict):
        """Broadcast message to all subscribed clients"""
        if not self.subscription_data[subscription_type]:
            return
            
        disconnected_clients = set()
        
        for websocket in self.connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")
                disconnected_clients.add(websocket)
        
        # Remove disconnected clients
        for websocket in disconnected_clients:
            self.connections.discard(websocket)
    
    async def broadcast_to_all(self, message: dict):
        """Broadcast message to all connected clients"""
        disconnected_clients = set()
        
        for websocket in self.connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to broadcast to client: {e}")
                disconnected_clients.add(websocket)
        
        # Remove disconnected clients
        for websocket in disconnected_clients:
            self.connections.discard(websocket)
    
    async def send_trade_notification(self, trade_data: dict):
        """Send instant trade execution notification"""
        message = {
            "type": "trade_notification",
            "data": trade_data,
            "timestamp": datetime.utcnow().isoformat(),
            "priority": "high"
        }
        await self.broadcast_to_all(message)
    
    async def send_alert(self, alert_type: str, message: str, data: dict = None):
        """Send system alert to all clients"""
        alert_message = {
            "type": "alert",
            "alert_type": alert_type,
            "message": message,
            "data": data or {},
            "timestamp": datetime.utcnow().isoformat(),
            "priority": "medium"
        }
        await self.broadcast_to_all(alert_message)

# Global realtime manager instance
realtime_manager = RealtimeManager()
