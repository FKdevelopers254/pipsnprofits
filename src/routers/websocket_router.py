"""
WebSocket router for real-time streaming
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import HTMLResponse
import uuid

from src.routers.realtime import realtime_manager
from src.services.bot_service import trading_bot

logger = logging.getLogger(__name__)
router = APIRouter()

# Store active connections with metadata
active_connections: Dict[str, Dict] = {}

@router.websocket("/ws/realtime")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for real-time streaming"""
    client_id = str(uuid.uuid4())
    
    try:
        # Register connection
        await realtime_manager.connect(websocket, client_id)
        active_connections[client_id] = {
            'websocket': websocket,
            'connected_at': datetime.utcnow(),
            'subscriptions': set()
        }
        
        # Handle messages
        while True:
            try:
                # Receive message with timeout
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                
                await handle_websocket_message(websocket, client_id, data)
                
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({
                    "type": "ping",
                    "timestamp": datetime.utcnow().isoformat()
                })
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON format"
                })
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket client {client_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        # Cleanup
        await realtime_manager.disconnect(websocket, client_id)
        if client_id in active_connections:
            del active_connections[client_id]

async def handle_websocket_message(websocket: WebSocket, client_id: str, data: dict):
    """Handle incoming WebSocket messages"""
    message_type = data.get('type')
    
    if message_type == 'subscribe':
        subscription_type = data.get('data_type')
        await realtime_manager.subscribe(websocket, client_id, subscription_type)
        
        # Track subscription
        if client_id in active_connections:
            active_connections[client_id]['subscriptions'].add(subscription_type)
            
    elif message_type == 'unsubscribe':
        subscription_type = data.get('data_type')
        await realtime_manager.unsubscribe(websocket, client_id, subscription_type)
        
        # Remove subscription tracking
        if client_id in active_connections:
            active_connections[client_id]['subscriptions'].discard(subscription_type)
            
    elif message_type == 'ping':
        # Respond to ping
        await websocket.send_json({
            "type": "pong",
            "timestamp": datetime.utcnow().isoformat()
        })
        
    elif message_type == 'get_status':
        # Send current status
        await send_status_update(websocket)
        
    elif message_type == 'execute_trade':
        # Handle trade execution request
        await handle_trade_request(websocket, client_id, data)
        
    else:
        await websocket.send_json({
            "type": "error",
            "message": f"Unknown message type: {message_type}"
        })

async def send_status_update(websocket: WebSocket):
    """Send current system status"""
    try:
        bot_status = trading_bot.get_status()
        
        await websocket.send_json({
            "type": "status_update",
            "data": {
                "bot": bot_status,
                "connections": len(active_connections),
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Error sending status update: {e}")

async def handle_trade_request(websocket: WebSocket, client_id: str, data: dict):
    """Handle trade execution requests via WebSocket"""
    try:
        action = data.get('action')  # 'buy', 'sell', 'close'
        symbol = data.get('symbol', 'XAUUSD')
        volume = data.get('volume', 0.01)
        
        # Validate request
        if action not in ['buy', 'sell', 'close']:
            await websocket.send_json({
                "type": "error",
                "message": "Invalid action. Use 'buy', 'sell', or 'close'"
            })
            return
        
        # Execute trade
        if action == 'close':
            result = await trading_bot.close_all_positions()
        else:
            result = await trading_bot.execute_manual_trade(action, symbol, volume)
        
        # Send result
        await websocket.send_json({
            "type": "trade_result",
            "data": result,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Broadcast trade notification
        if result.get('success'):
            await realtime_manager.send_trade_notification({
                "action": action,
                "symbol": symbol,
                "volume": volume,
                "result": result,
                "client_id": client_id
            })
            
    except Exception as e:
        logger.error(f"Error handling trade request: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"Trade execution failed: {str(e)}"
        })

@router.get("/ws/status")
async def get_websocket_status():
    """Get WebSocket connection status"""
    return {
        "active_connections": len(active_connections),
        "is_streaming": realtime_manager.is_streaming,
        "subscriptions": {
            sub_type: len(subscribers) 
            for sub_type, subscribers in realtime_manager.subscription_data.items()
        },
        "timestamp": datetime.utcnow().isoformat()
    }

@router.post("/ws/broadcast")
async def broadcast_message(message: dict):
    """Broadcast message to all connected WebSocket clients"""
    await realtime_manager.broadcast_to_all({
        "type": "broadcast",
        "data": message,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    return {
        "success": True,
        "message": "Message broadcasted to all clients",
        "recipients": len(active_connections)
    }

@router.post("/ws/alert")
async def send_alert(alert_type: str, message: str, data: dict = None):
    """Send alert to all WebSocket clients"""
    await realtime_manager.send_alert(alert_type, message, data)
    
    return {
        "success": True,
        "alert_type": alert_type,
        "message": message,
        "recipients": len(active_connections)
    }
