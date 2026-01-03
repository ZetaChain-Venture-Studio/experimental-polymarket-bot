"""
Polybonds API Server.
Provides REST endpoints for the dashboard and external integrations.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from .config import get_settings
from .database import get_db
from .polymarket_client import get_client
from .market_scanner import MarketScanner, PolybondOpportunity
from .trade_executor import TradeExecutor

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Polybonds Trading System",
    description="Automated trading for 98%+ probability Polymarket positions",
    version="0.1.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
settings = get_settings()
db = get_db(settings.database_url)
client = get_client(settings)
scanner = MarketScanner(client=client, settings=settings, db=db)
executor = TradeExecutor(client=client, settings=settings, db=db)


# ===========================================
# RESPONSE MODELS
# ===========================================

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str


class OpportunityResponse(BaseModel):
    market_id: str
    question: str
    token_id: str
    side: str
    current_price: float
    potential_return_pct: float
    annualized_return_pct: float
    days_to_resolution: float
    risk_score: float
    risk_factors: List[str]
    volume_24h: float
    category: str


class PositionResponse(BaseModel):
    id: int
    market_id: str
    question: Optional[str]
    side: str
    quantity: float
    avg_entry_price: float
    total_cost_usd: float
    current_price: Optional[float]
    current_value_usd: Optional[float]
    unrealized_pnl: Optional[float]
    unrealized_pnl_pct: Optional[float]
    status: str


class TradeResponse(BaseModel):
    id: int
    market_id: str
    side: str
    action: str
    price: float
    quantity: float
    total_usd: float
    status: str
    created_at: Optional[str]


class SettlementResponse(BaseModel):
    id: int
    market_id: str
    question: Optional[str]
    side: str
    entry_price: float
    settlement_price: float
    pnl_usd: float
    pnl_pct: float
    outcome: str
    settled_at: Optional[str]


class PortfolioResponse(BaseModel):
    total_value_usd: float
    cash_balance_usd: float
    positions_value_usd: float
    total_realized_pnl: float
    total_unrealized_pnl: float
    open_positions_count: int
    win_rate: Optional[float]
    roi_pct: Optional[float]


class ExecuteTradeRequest(BaseModel):
    market_id: str
    amount_usd: Optional[float] = None


class ExecuteTradeResponse(BaseModel):
    success: bool
    trade_id: Optional[int]
    order_id: Optional[str]
    message: str


# ===========================================
# ENDPOINTS
# ===========================================

@app.get("/api/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="0.1.0"
    )


@app.get("/api/opportunities", tags=["Markets"])
async def get_opportunities(
    limit: int = Query(default=20, ge=1, le=100, description="Max opportunities to return"),
    min_return: float = Query(default=0, description="Minimum potential return %"),
    max_risk: float = Query(default=100, description="Maximum risk score")
) -> Dict[str, Any]:
    """Get current Polybond opportunities."""
    try:
        opportunities = scanner.scan_all_markets()
        
        # Apply filters
        filtered = [
            o for o in opportunities
            if o.potential_return_pct >= min_return and o.risk_score <= max_risk
        ]
        
        # Get summary
        summary = scanner.get_summary(filtered)
        
        return {
            "count": len(filtered[:limit]),
            "total_found": len(filtered),
            "summary": summary,
            "opportunities": [
                {
                    "market_id": o.market_id,
                    "question": o.question,
                    "token_id": o.token_id,
                    "side": o.side,
                    "current_price": o.current_price,
                    "potential_return_pct": o.potential_return_pct,
                    "annualized_return_pct": o.annualized_return_pct,
                    "days_to_resolution": o.days_to_resolution,
                    "end_date": o.end_date.isoformat() if o.end_date else None,
                    "resolution_source": o.resolution_source,
                    "resolution_rules": o.resolution_rules[:300] if o.resolution_rules else "",
                    "estimated_resolution_hours": o.estimated_resolution_hours,
                    "estimated_payout_date": o.estimated_payout_date.isoformat() if o.estimated_payout_date else None,
                    "risk_score": o.risk_score,
                    "risk_factors": o.risk_factors,
                    "volume_24h": o.volume_24h,
                    "category": o.category
                }
                for o in filtered[:limit]
            ]
        }
    except Exception as e:
        logger.error(f"Error scanning opportunities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/positions", tags=["Portfolio"])
async def get_positions() -> Dict[str, Any]:
    """Get all open positions."""
    try:
        positions = db.get_open_positions()
        
        # Update prices and enrich with market info
        result = []
        for pos in positions:
            market = db.get_market(pos.market_id)
            
            # Get current price
            current_price = client.get_price(pos.token_id, "SELL")
            if current_price:
                db.update_position_prices(pos.market_id, current_price)
            
            result.append({
                "id": pos.id,
                "market_id": pos.market_id,
                "question": market.question if market else None,
                "side": pos.side,
                "quantity": pos.quantity,
                "avg_entry_price": pos.avg_entry_price,
                "total_cost_usd": pos.total_cost_usd,
                "current_price": current_price or pos.current_price,
                "current_value_usd": (pos.quantity * current_price) if current_price else pos.current_value_usd,
                "unrealized_pnl": pos.unrealized_pnl,
                "unrealized_pnl_pct": pos.unrealized_pnl_pct,
                "status": pos.status
            })
        
        return {
            "count": len(result),
            "positions": result
        }
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/portfolio", response_model=PortfolioResponse, tags=["Portfolio"])
async def get_portfolio():
    """Get portfolio overview."""
    try:
        positions = db.get_open_positions()
        settlements = db.get_recent_settlements(limit=1000)
        
        # Calculate values
        positions_value = sum(
            (p.current_value_usd or p.total_cost_usd) for p in positions
        )
        total_cost = sum(p.total_cost_usd for p in positions)
        unrealized_pnl = positions_value - total_cost
        
        realized_pnl = sum(s.pnl_usd or 0 for s in settlements)
        
        # Calculate win rate
        wins = len([s for s in settlements if s.outcome == "win"])
        total_settled = len(settlements)
        win_rate = (wins / total_settled) if total_settled > 0 else None
        
        # Try to get actual balance from Polymarket
        actual_balance = client.get_balance()
        if actual_balance is not None:
            cash_balance = actual_balance
            total_value = cash_balance + positions_value
            # Calculate ROI based on total value vs positions cost
            initial_capital = total_cost + cash_balance if total_cost > 0 else cash_balance
        else:
            # Fallback: estimate based on positions
            initial_capital = 100  # Minimum fallback
            cash_balance = max(0, initial_capital - total_cost + realized_pnl)
            total_value = cash_balance + positions_value

        roi_pct = ((realized_pnl + unrealized_pnl) / initial_capital * 100) if initial_capital > 0 else 0
        
        return PortfolioResponse(
            total_value_usd=round(total_value, 2),
            cash_balance_usd=round(cash_balance, 2),
            positions_value_usd=round(positions_value, 2),
            total_realized_pnl=round(realized_pnl, 2),
            total_unrealized_pnl=round(unrealized_pnl, 2),
            open_positions_count=len(positions),
            win_rate=round(win_rate, 4) if win_rate else None,
            roi_pct=round(roi_pct, 2) if roi_pct else None
        )
    except Exception as e:
        logger.error(f"Error calculating portfolio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trades", tags=["Trading"])
async def get_trades(
    limit: int = Query(default=50, ge=1, le=500, description="Max trades to return")
) -> Dict[str, Any]:
    """Get trade history."""
    try:
        trades = db.get_recent_trades(limit=limit)
        
        return {
            "count": len(trades),
            "trades": [
                {
                    "id": t.id,
                    "market_id": t.market_id,
                    "side": t.side,
                    "action": t.action,
                    "price": t.price,
                    "quantity": t.quantity,
                    "total_usd": t.total_usd,
                    "status": t.status,
                    "order_id": t.order_id,
                    "created_at": t.created_at.isoformat() if t.created_at else None
                }
                for t in trades
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settlements", tags=["Trading"])
async def get_settlements(
    limit: int = Query(default=50, ge=1, le=500, description="Max settlements to return")
) -> Dict[str, Any]:
    """Get settlement history."""
    try:
        settlements = db.get_recent_settlements(limit=limit)
        
        # Calculate summary stats
        total_pnl = sum(s.pnl_usd or 0 for s in settlements)
        wins = len([s for s in settlements if s.outcome == "win"])
        losses = len(settlements) - wins
        
        return {
            "count": len(settlements),
            "summary": {
                "total_pnl_usd": round(total_pnl, 2),
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / len(settlements), 4) if settlements else None
            },
            "settlements": [
                {
                    "id": s.id,
                    "market_id": s.market_id,
                    "question": s.question,
                    "side": s.side,
                    "entry_price": s.entry_price,
                    "settlement_price": s.settlement_price,
                    "quantity": s.quantity,
                    "cost_usd": s.cost_usd,
                    "payout_usd": s.payout_usd,
                    "pnl_usd": s.pnl_usd,
                    "pnl_pct": s.pnl_pct,
                    "outcome": s.outcome,
                    "settled_at": s.settled_at.isoformat() if s.settled_at else None
                }
                for s in settlements
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching settlements: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scan", tags=["Markets"])
async def trigger_scan() -> Dict[str, Any]:
    """Manually trigger a market scan."""
    try:
        opportunities = scanner.scan_all_markets()
        summary = scanner.get_summary(opportunities)
        
        return {
            "success": True,
            "message": f"Scan complete: {len(opportunities)} opportunities found",
            "summary": summary
        }
    except Exception as e:
        logger.error(f"Error during scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trade/{market_id}", response_model=ExecuteTradeResponse, tags=["Trading"])
async def execute_trade(
    market_id: str,
    request: ExecuteTradeRequest = None
):
    """Execute a trade on a specific market."""
    try:
        # Get amount from body
        trade_amount = request.amount_usd if request else None
        logger.info(f"Trade request: market_id={market_id}, amount={trade_amount}")
        logger.info(f"AUTO_TRADING_ENABLED={settings.auto_trading_enabled}")

        # Get opportunity
        opportunity = scanner.get_opportunity(market_id)
        if not opportunity:
            logger.warning(f"Market not found or not eligible: {market_id}")
            # Try to fetch the market directly to see why it failed
            market_data = client.get_market(market_id)
            if market_data:
                logger.warning(f"Market exists but not eligible. Data: price_yes={market_data.get('outcomePrices')}, volume={market_data.get('volume24hr')}")
            raise HTTPException(status_code=404, detail="Market not found or not eligible")

        # Execute trade
        result = executor.execute_polybond_buy(
            opportunity,
            portfolio_value=10000,  # Use settings or fetch actual balance
            amount_usd=trade_amount
        )
        
        return ExecuteTradeResponse(
            success=result.success,
            trade_id=result.trade_id,
            order_id=result.order_id,
            message=result.error_message or f"Trade executed: ${result.total_usd:.2f}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing trade: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/close/{position_id}", response_model=ExecuteTradeResponse, tags=["Trading"])
async def close_position(position_id: int):
    """Close/sell a position."""
    try:
        result = executor.execute_sell(position_id, reason="manual")
        
        return ExecuteTradeResponse(
            success=result.success,
            trade_id=result.trade_id,
            order_id=result.order_id,
            message=result.error_message or f"Position closed: ${result.total_usd:.2f}"
        )
    except Exception as e:
        logger.error(f"Error closing position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settings", tags=["System"])
async def get_current_settings() -> Dict[str, Any]:
    """Get current settings (non-sensitive)."""
    return {
        "min_probability": settings.min_probability,
        "max_probability": settings.max_probability,
        "min_volume_24h": settings.min_volume_24h,
        "max_position_size_usd": settings.max_position_size_usd,
        "max_portfolio_allocation_pct": settings.max_portfolio_allocation_pct,
        "stop_loss_threshold": settings.stop_loss_threshold,
        "min_days_to_resolution": settings.min_days_to_resolution,
        "max_days_to_resolution": settings.max_days_to_resolution,
        "auto_trading_enabled": settings.auto_trading_enabled,
        "scan_interval_minutes": settings.scan_interval_minutes
    }


@app.get("/api/logs", tags=["System"])
async def get_logs(
    limit: int = Query(default=50, ge=1, le=500),
    level: Optional[str] = Query(default=None, description="Filter by level (INFO, WARNING, ERROR)")
) -> Dict[str, Any]:
    """Get recent activity logs."""
    try:
        logs = db.get_recent_logs(limit=limit, level=level)

        return {
            "count": len(logs),
            "logs": [
                {
                    "id": log.id,
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                    "level": log.level,
                    "module": log.module,
                    "message": log.message,
                    "details": log.details
                }
                for log in logs
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/debug/test-trade", tags=["System"])
async def debug_test_trade(amount_usd: float = 1.0) -> Dict[str, Any]:
    """
    Test trade functionality without actually executing.
    Creates a signed order and validates it can be created.
    """
    import traceback

    result = {
        "success": False,
        "balance": None,
        "opportunities_count": 0,
        "test_opportunity": None,
        "order_created": False,
        "errors": []
    }

    try:
        # Step 1: Check balance
        if not client.is_authenticated:
            init_success = client.initialize(read_only=False)
            if not init_success:
                result["errors"].append("Failed to initialize client")
                return result

        balance = client.get_balance()
        result["balance"] = balance
        if balance is None:
            result["errors"].append("Could not fetch balance")

        # Step 2: Find opportunities
        opportunities = scanner.scan_all_markets()
        result["opportunities_count"] = len(opportunities)

        if not opportunities:
            result["errors"].append("No opportunities found")
            return result

        # Step 3: Get first opportunity
        opp = opportunities[0]
        result["test_opportunity"] = {
            "market_id": opp.market_id,
            "question": opp.question[:60] + "...",
            "price": opp.current_price,
            "side": opp.side,
            "token_id": opp.token_id[:20] + "...",
        }

        # Step 4: Try to create an order (but don't post it)
        try:
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import BUY

            quantity = amount_usd / opp.current_price
            limit_price = min(opp.current_price + 0.005, 0.995)

            order_args = OrderArgs(
                token_id=opp.token_id,
                price=limit_price,
                size=quantity,
                side=BUY
            )

            # Try to create (sign) the order
            signed_order = client._clob_client.create_order(order_args)
            result["order_created"] = True
            result["signed_order"] = {
                "order_id": str(signed_order.order.orderId) if hasattr(signed_order, 'order') else "N/A",
                "signature_present": bool(getattr(signed_order, 'signature', None)),
            }
            result["success"] = True
            result["message"] = "Order creation test successful! Trading should work."

        except Exception as order_error:
            result["errors"].append(f"Order creation failed: {order_error}")
            result["order_traceback"] = traceback.format_exc()

        return result

    except Exception as e:
        result["errors"].append(f"Test trade error: {e}")
        result["traceback"] = traceback.format_exc()
        return result


@app.get("/api/debug/auth", tags=["System"])
async def debug_auth() -> Dict[str, Any]:
    """Debug authentication status and test CLOB client."""
    import traceback

    result = {
        "clob_available": False,
        "client_initialized": False,
        "authenticated": False,
        "private_key_length": 0,
        "private_key_starts_with_0x": False,
        "funder_address": "",
        "chain_id": 0,
        "signature_type": 0,
        "balance": None,
        "wallet_address": None,
        "api_key": None,
        "errors": []
    }

    try:
        # Check if py-clob-client is available
        try:
            from py_clob_client.client import ClobClient
            result["clob_available"] = True
        except ImportError as e:
            result["errors"].append(f"py-clob-client not installed: {e}")
            return result

        # Check settings
        pk = settings.polymarket_private_key
        result["private_key_length"] = len(pk) if pk else 0
        result["private_key_starts_with_0x"] = pk.startswith("0x") if pk else False
        result["funder_address"] = settings.polymarket_funder_address[:20] + "..." if settings.polymarket_funder_address else ""
        result["chain_id"] = settings.polymarket_chain_id
        result["signature_type"] = settings.polymarket_signature_type
        result["auto_trading_enabled"] = settings.auto_trading_enabled

        # Check client state
        result["client_initialized"] = client._clob_client is not None
        result["authenticated"] = client.is_authenticated

        # Check CLOB client internal state
        if client._clob_client is not None:
            clob = client._clob_client
            result["clob_internal"] = {
                "has_signer": hasattr(clob, 'signer') and clob.signer is not None,
                "has_creds": hasattr(clob, 'creds') and clob.creds is not None,
                "host": getattr(clob, 'host', None),
            }

            # Check signer details
            if hasattr(clob, 'signer') and clob.signer is not None:
                signer = clob.signer
                try:
                    wallet_addr = signer.address()
                    result["wallet_address"] = wallet_addr[:20] + "..." if wallet_addr else None
                    result["clob_internal"]["signer_address"] = wallet_addr
                except Exception as addr_err:
                    result["errors"].append(f"Failed to get signer address: {addr_err}")

                result["clob_internal"]["signer_has_signature_type"] = hasattr(signer, 'signature_type')
                if hasattr(signer, 'signature_type'):
                    result["clob_internal"]["signer_signature_type"] = signer.signature_type

            # Check API credentials
            if hasattr(clob, 'creds') and clob.creds is not None:
                creds = clob.creds
                result["api_key"] = creds.api_key[:20] + "..." if creds.api_key else None
                result["clob_internal"]["has_api_secret"] = bool(creds.api_secret)
                result["clob_internal"]["has_passphrase"] = bool(creds.api_passphrase)

        # If not authenticated, try to reinitialize
        if not client.is_authenticated:
            logger.info("Debug: Attempting to reinitialize client...")
            try:
                init_result = client.initialize(read_only=False)
                result["init_result"] = init_result
                result["authenticated_after_init"] = client.is_authenticated

                # Get updated info after init
                if client._clob_client is not None:
                    clob = client._clob_client
                    if hasattr(clob, 'signer') and clob.signer is not None:
                        try:
                            result["wallet_address"] = clob.signer.address()[:20] + "..."
                        except:
                            pass
                    if hasattr(clob, 'creds') and clob.creds is not None:
                        result["api_key"] = clob.creds.api_key[:20] + "..."
            except Exception as init_error:
                result["errors"].append(f"Init error: {init_error}")
                result["init_traceback"] = traceback.format_exc()

        # Try to get balance
        if client.is_authenticated:
            try:
                balance = client.get_balance()
                result["balance"] = balance
                result["balance_status"] = "success" if balance is not None else "failed"
                # Include last error if balance failed
                if balance is None and hasattr(client, '_last_balance_error'):
                    result["balance_error_detail"] = client._last_balance_error
            except Exception as balance_error:
                result["errors"].append(f"Balance error: {balance_error}")
                result["balance_traceback"] = traceback.format_exc()

        return result

    except Exception as e:
        result["errors"].append(f"Debug error: {e}")
        result["traceback"] = traceback.format_exc()
        return result


# ===========================================
# STARTUP/SHUTDOWN
# ===========================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    logger.info("Polybonds API server starting...")

    # Initialize client - use full auth if private key is available
    has_private_key = bool(settings.polymarket_private_key)
    if has_private_key:
        logger.info("Private key found, initializing with full authentication...")
        client.initialize(read_only=False)
    else:
        logger.info("No private key, initializing in read-only mode...")
        client.initialize(read_only=True)

    logger.info("Polybonds API server ready")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Polybonds API server shutting down...")
    client.close()


# ===========================================
# STATIC FILE SERVING (Frontend)
# ===========================================

# Get the path to the frontend dist folder
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")

# Serve static assets if frontend is built
if os.path.exists(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        """Serve the frontend dashboard."""
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend_routes(full_path: str):
        """Serve frontend for all non-API routes (SPA support)."""
        # Don't catch API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        # Check if it's a static file
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)

        # Return index.html for SPA routing
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
