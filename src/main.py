from pathlib import Path
import sys

# Make the project root importable when running python src/main.py
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import signal
import sys
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import asyncio

from src.config import load_config, detect_live_flag
from src.logging_setup import setup_logging
from src.services.mt5_service import mt5_manager
from src.routers import ws
from src.routers.ws import candle_watcher
from src.routers import dashboard, bot, backtesting


logger = logging.getLogger(__name__)


def build_app(cfg: dict) -> FastAPI:
    app = FastAPI(title="MT5 Order Manager", version="0.1.0")

    # Mount static files
    static_dir = Path(__file__).parent.parent / "src" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    else:
        logger.warning(f"Static directory not found: {static_dir}")

    from src.routers import orders
    from src.routers import websocket_router
    from src.routers import rl_router

    app.include_router(orders.router)
    app.include_router(dashboard.router)
    app.include_router(bot.router)
    app.include_router(backtesting.router)
    app.include_router(websocket_router.router)
    app.include_router(rl_router.router)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "mt5_connected": mt5_manager._initialized}

    return app


def _signal_handler(signum, frame):
    logger.info("Received termination signal (%s). Shutting down.", signum)
    try:
        mt5_manager.shutdown()
    except Exception:
        logger.exception("Error during shutdown")
    sys.exit(0)


def main(argv=None):
    use_live = detect_live_flag(argv)
    cfg = load_config(use_live=use_live)

    # logging
    setup_logging(level=cfg.get("log_level", "INFO"))

    # choose account (live or demo[0])
    accounts = cfg.get("accounts", {})
    account_cfg = None
    if use_live:
        account_cfg = accounts.get("live")
        if account_cfg is None:
            logger.error(
                "Live config requested but 'live' account not found in config."
            )
            raise SystemExit(1)
    else:
        demo_list = accounts.get("demo", [])
        if not demo_list:
            logger.error("No demo accounts configured in config.")
            raise SystemExit(1)
        account_cfg = demo_list[0]

    # Initialize MT5 once (singleton)
    mt5_path = cfg.get("mt5", {}).get("path")
    if not mt5_manager.initialize(account_cfg=account_cfg, mt5_path=mt5_path):
        logger.error("Failed to initialize MT5 manager. Exiting.")
        raise SystemExit(1)

    # register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    app = build_app(cfg)
    app.include_router(ws.router)

    @app.on_event("startup")
    async def start_candle_task():
        asyncio.create_task(candle_watcher())

    host = cfg.get("server", {}).get("host", "127.0.0.1")
    port = int(cfg.get("server", {}).get("port", 5100))

    logger.info("Starting server on %s:%s (use_live=%s)", host, port, use_live)

    # Run uvicorn programmatically so the user can start via `python src/main.py`
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
