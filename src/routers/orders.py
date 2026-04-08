import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Body

from src.models.schemas import (
    NewOrderRequest,
    UpdateOrderRequest,
    RemoveOrderRequest,
    ClosePositionRequest,
    OrderResponse,
    OrderListResponse,
    PositionListResponse,
)

from src.services.mt5_service import mt5_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])


@router.post("/newOrder", response_model=OrderResponse)
def new_order(req: NewOrderRequest):
    """
    Create a new order (market or pending). The server will validate and pass to MT5 manager.
    """
    try:
        payload = req.dict()
        result = mt5_manager.place_order(payload)
        # result is a dict: {success, message, ticket, details}
        return OrderResponse(
            success=bool(result.get("success", False)),
            message=result.get("message"),
            ticket=result.get("ticket"),
            symbol=req.symbol,
            order_type=req.order_type,
            price=req.price,
            volume=req.volume,
            comment=(req.comment or result.get("details", {}).get("comment")),
            details=result.get("details"),
        )
    except Exception as e:
        logger.exception("Error in /newOrder: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/getOpenOrders", response_model=OrderListResponse)
def get_open_orders(symbol: Optional[str] = Query(None, description="Optional symbol to filter")):
    """
    Retrieve open pending orders.
    """
    try:
        res = mt5_manager.get_open_orders(symbol)
        if not res.get("success", False):
            # return 200 but with success=false to allow clients to inspect details
            return OrderListResponse(success=False, message=res.get("message"), orders=[])
        orders = res.get("orders", [])
        return OrderListResponse(success=True, message=res.get("message"), orders=orders)
    except Exception as e:
        logger.exception("Error in /getOpenOrders: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/getOpenPositions", response_model=PositionListResponse)
def get_open_positions(symbol: Optional[str] = Query(None, description="Optional symbol to filter")):
    """
    Retrieve open positions.
    """
    try:
        res = mt5_manager.get_open_positions(symbol)
        if not res.get("success", False):
            return PositionListResponse(success=False, message=res.get("message"), positions=[])
        positions = res.get("positions", [])
        return PositionListResponse(success=True, message=res.get("message"), positions=positions)
    except Exception as e:
        logger.exception("Error in /getOpenPositions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/removeOrder", response_model=OrderResponse)
def remove_order(req: RemoveOrderRequest = Body(...)):
    """
    Cancel (remove) an existing pending order.
    """
    try:
        res = mt5_manager.cancel_order(req.ticket)
        return OrderResponse(
            success=bool(res.get("success", False)),
            message=res.get("message"),
            ticket=res.get("ticket"),
            details=res.get("details"),
        )
    except Exception as e:
        logger.exception("Error in /removeOrder: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/closePosition", response_model=OrderResponse)
def close_position(req: ClosePositionRequest = Body(...)):
    """
    Close an open position fully or partially.
    """
    try:
        res = mt5_manager.close_position(req.ticket, req.volume)
        return OrderResponse(
            success=bool(res.get("success", False)),
            message=res.get("message"),
            ticket=res.get("ticket"),
            details=res.get("details"),
        )
    except Exception as e:
        logger.exception("Error in /closePosition: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/updateOrder", response_model=OrderResponse)
def update_order(ticket: int = Query(..., description="Ticket of order to update"), req: UpdateOrderRequest = Body(...)):
    """
    Update an existing pending order.
    """
    try:
        payload = req.dict(exclude_none=True)
        res = mt5_manager.modify_order(ticket, payload)
        return OrderResponse(
            success=bool(res.get("success", False)),
            message=res.get("message"),
            ticket=res.get("ticket"),
            details=res.get("details"),
        )
    except Exception as e:
        logger.exception("Error in /updateOrder: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
