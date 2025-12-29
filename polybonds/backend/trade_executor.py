"""
Trade Executor Module.
Handles order placement, tracking, and position management.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List
import logging

from .config import Settings, get_settings
from .polymarket_client import PolymarketClient, get_client, OrderResult
from .database import DatabaseManager, get_db, TradeStatus, PositionStatus
from .market_scanner import PolybondOpportunity

logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """Result of a trade execution."""
    success: bool
    trade_id: Optional[int]
    order_id: Optional[str]
    position_id: Optional[int]
    filled_price: Optional[float]
    filled_quantity: Optional[float]
    total_usd: Optional[float]
    error_message: Optional[str]


class RiskManager:
    """
    Manages trading risk.
    Enforces position limits and portfolio constraints.
    """
    
    def __init__(self, settings: Settings = None, db: DatabaseManager = None):
        self.settings = settings or get_settings()
        self.db = db or get_db()
    
    def check_trade_allowed(
        self,
        opportunity: PolybondOpportunity,
        portfolio_value: float
    ) -> tuple[bool, str]:
        """
        Check if a trade is allowed based on risk parameters.
        
        Args:
            opportunity: The opportunity to check
            portfolio_value: Current total portfolio value in USD
            
        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        # Check if we already have a position in this market
        existing_position = self.db.get_position(opportunity.market_id)
        if existing_position:
            current_allocation = existing_position.total_cost_usd / portfolio_value
            if current_allocation >= self.settings.max_portfolio_allocation_pct:
                return False, f"Max allocation reached for this market ({current_allocation:.1%})"
        
        # Check risk score threshold (reject very risky opportunities)
        if opportunity.risk_score > 75:
            return False, f"Risk score too high: {opportunity.risk_score}/100"
        
        # Check total portfolio exposure (don't put more than 80% in positions)
        total_positions_value = self.db.get_total_positions_value()
        if total_positions_value / portfolio_value > 0.80:
            return False, "Portfolio too concentrated in positions (>80%)"
        
        return True, "Trade allowed"
    
    def calculate_position_size(
        self,
        opportunity: PolybondOpportunity,
        portfolio_value: float
    ) -> float:
        """
        Calculate appropriate position size.
        
        Args:
            opportunity: The opportunity
            portfolio_value: Current total portfolio value
            
        Returns:
            Position size in USD
        """
        # Start with maximum position size
        max_by_absolute = self.settings.max_position_size_usd
        
        # Limit by portfolio allocation
        max_by_allocation = portfolio_value * self.settings.max_portfolio_allocation_pct
        
        # Adjust by risk score (lower risk = can allocate more)
        # Risk score 0-100, multiplier 0.5-1.0
        risk_multiplier = 1.0 - (opportunity.risk_score / 200)
        
        # Check existing position
        existing_position = self.db.get_position(opportunity.market_id)
        if existing_position:
            # Reduce by existing allocation
            remaining_allocation = (
                (portfolio_value * self.settings.max_portfolio_allocation_pct) 
                - existing_position.total_cost_usd
            )
            max_by_allocation = max(0, remaining_allocation)
        
        # Calculate final size
        base_size = min(max_by_absolute, max_by_allocation)
        final_size = base_size * risk_multiplier
        
        # Round to 2 decimal places
        return round(max(0, final_size), 2)


class TradeExecutor:
    """
    Executes trades on Polymarket.
    """
    
    def __init__(
        self,
        client: PolymarketClient = None,
        settings: Settings = None,
        db: DatabaseManager = None
    ):
        self.client = client or get_client()
        self.settings = settings or get_settings()
        self.db = db or get_db()
        self.risk_manager = RiskManager(settings, db)
    
    def execute_polybond_buy(
        self,
        opportunity: PolybondOpportunity,
        portfolio_value: float = None,
        amount_usd: float = None
    ) -> TradeResult:
        """
        Execute a buy order for a Polybond opportunity.
        
        Args:
            opportunity: The opportunity to trade
            portfolio_value: Current portfolio value (for position sizing)
            amount_usd: Override amount in USD (optional)
            
        Returns:
            TradeResult with execution details
        """
        # Default portfolio value if not provided
        if portfolio_value is None:
            portfolio_value = 10000  # Assume $10k for position sizing
        
        # Risk check
        allowed, reason = self.risk_manager.check_trade_allowed(
            opportunity, portfolio_value
        )
        
        if not allowed:
            logger.warning(f"Trade blocked: {reason}")
            return TradeResult(
                success=False,
                trade_id=None,
                order_id=None,
                position_id=None,
                filled_price=None,
                filled_quantity=None,
                total_usd=None,
                error_message=reason
            )
        
        # Calculate position size
        if amount_usd is None:
            amount_usd = self.risk_manager.calculate_position_size(
                opportunity, portfolio_value
            )
        
        if amount_usd < 1:
            return TradeResult(
                success=False,
                trade_id=None,
                order_id=None,
                position_id=None,
                filled_price=None,
                filled_quantity=None,
                total_usd=None,
                error_message="Position size too small (< $1)"
            )
        
        # Calculate quantity (shares = usd / price)
        quantity = amount_usd / opportunity.current_price
        
        # Set limit price slightly above current (ensure fill)
        limit_price = min(opportunity.current_price + 0.005, 0.995)
        
        logger.info(
            f"Executing Polybond buy: {opportunity.question[:50]}... "
            f"@ ${limit_price:.4f} x {quantity:.2f} shares (${amount_usd:.2f})"
        )
        
        # Check if trading is enabled
        if not self.settings.auto_trading_enabled:
            logger.info("Auto-trading disabled - simulating trade")
            
            # Record simulated trade
            trade = self.db.record_trade({
                "market_id": opportunity.market_id,
                "token_id": opportunity.token_id,
                "side": opportunity.side,
                "action": "BUY",
                "price": limit_price,
                "quantity": quantity,
                "total_usd": amount_usd,
                "order_id": "SIMULATED",
                "status": TradeStatus.FILLED.value,
                "filled_at": datetime.now(timezone.utc)
            })
            
            # Create/update position
            position = self.db.create_or_update_position({
                "market_id": opportunity.market_id,
                "token_id": opportunity.token_id,
                "side": opportunity.side,
                "quantity": quantity,
                "avg_entry_price": limit_price,
                "total_cost_usd": amount_usd,
                "current_price": limit_price,
                "current_value_usd": amount_usd,
                "unrealized_pnl": 0,
                "unrealized_pnl_pct": 0
            })
            
            return TradeResult(
                success=True,
                trade_id=trade.id,
                order_id="SIMULATED",
                position_id=position.id,
                filled_price=limit_price,
                filled_quantity=quantity,
                total_usd=amount_usd,
                error_message=None
            )
        
        # Execute real trade
        try:
            # Initialize client with authentication if needed
            if not self.client.is_authenticated:
                if not self.client.initialize(read_only=False):
                    return TradeResult(
                        success=False,
                        trade_id=None,
                        order_id=None,
                        position_id=None,
                        filled_price=None,
                        filled_quantity=None,
                        total_usd=None,
                        error_message="Failed to authenticate with Polymarket"
                    )
            
            # Place the order
            order_result = self.client.place_limit_order(
                token_id=opportunity.token_id,
                side="BUY",
                price=limit_price,
                size=quantity
            )
            
            if not order_result.success:
                # Record failed trade
                trade = self.db.record_trade({
                    "market_id": opportunity.market_id,
                    "token_id": opportunity.token_id,
                    "side": opportunity.side,
                    "action": "BUY",
                    "price": limit_price,
                    "quantity": quantity,
                    "total_usd": amount_usd,
                    "status": TradeStatus.FAILED.value,
                    "error_message": order_result.error_message
                })
                
                return TradeResult(
                    success=False,
                    trade_id=trade.id,
                    order_id=None,
                    position_id=None,
                    filled_price=None,
                    filled_quantity=None,
                    total_usd=None,
                    error_message=order_result.error_message
                )
            
            # Record successful trade
            trade = self.db.record_trade({
                "market_id": opportunity.market_id,
                "token_id": opportunity.token_id,
                "side": opportunity.side,
                "action": "BUY",
                "price": limit_price,
                "quantity": quantity,
                "total_usd": amount_usd,
                "order_id": order_result.order_id,
                "status": TradeStatus.FILLED.value,
                "filled_at": datetime.now(timezone.utc)
            })
            
            # Create/update position
            position = self.db.create_or_update_position({
                "market_id": opportunity.market_id,
                "token_id": opportunity.token_id,
                "side": opportunity.side,
                "quantity": quantity,
                "avg_entry_price": limit_price,
                "total_cost_usd": amount_usd,
                "current_price": limit_price,
                "current_value_usd": amount_usd,
                "unrealized_pnl": 0,
                "unrealized_pnl_pct": 0
            })
            
            # Log activity
            self.db.log_activity(
                level="INFO",
                module="trade_executor",
                message=f"Polybond buy executed: {opportunity.question[:50]}...",
                details={
                    "market_id": opportunity.market_id,
                    "side": opportunity.side,
                    "price": limit_price,
                    "quantity": quantity,
                    "total_usd": amount_usd,
                    "order_id": order_result.order_id
                }
            )
            
            logger.info(f"Trade executed successfully: Order {order_result.order_id}")
            
            return TradeResult(
                success=True,
                trade_id=trade.id,
                order_id=order_result.order_id,
                position_id=position.id,
                filled_price=limit_price,
                filled_quantity=quantity,
                total_usd=amount_usd,
                error_message=None
            )
            
        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            
            # Record failed trade
            trade = self.db.record_trade({
                "market_id": opportunity.market_id,
                "token_id": opportunity.token_id,
                "side": opportunity.side,
                "action": "BUY",
                "price": limit_price,
                "quantity": quantity,
                "total_usd": amount_usd,
                "status": TradeStatus.FAILED.value,
                "error_message": str(e)
            })
            
            return TradeResult(
                success=False,
                trade_id=trade.id,
                order_id=None,
                position_id=None,
                filled_price=None,
                filled_quantity=None,
                total_usd=None,
                error_message=str(e)
            )
    
    def execute_sell(
        self,
        position_id: int,
        reason: str = "manual"
    ) -> TradeResult:
        """
        Sell/close a position.
        
        Args:
            position_id: The position ID to close
            reason: Reason for selling (e.g., "stop_loss", "take_profit", "manual")
            
        Returns:
            TradeResult with execution details
        """
        session = self.db.get_session()
        try:
            from .database import Position
            position = session.query(Position).filter_by(id=position_id).first()
            
            if not position:
                return TradeResult(
                    success=False,
                    trade_id=None,
                    order_id=None,
                    position_id=None,
                    filled_price=None,
                    filled_quantity=None,
                    total_usd=None,
                    error_message=f"Position {position_id} not found"
                )
            
            if position.status != PositionStatus.OPEN.value:
                return TradeResult(
                    success=False,
                    trade_id=None,
                    order_id=None,
                    position_id=position_id,
                    filled_price=None,
                    filled_quantity=None,
                    total_usd=None,
                    error_message="Position is not open"
                )
            
            # Get current price
            current_price = self.client.get_price(position.token_id, "SELL")
            if current_price is None:
                current_price = position.current_price or position.avg_entry_price
            
            logger.info(
                f"Executing sell for position {position_id}: "
                f"{position.quantity:.2f} shares @ ${current_price:.4f} (reason: {reason})"
            )
            
            # TODO: Execute actual sell order when trading is enabled
            # For now, just simulate
            
            sale_value = position.quantity * current_price
            realized_pnl = sale_value - position.total_cost_usd
            
            # Record trade
            trade = self.db.record_trade({
                "market_id": position.market_id,
                "token_id": position.token_id,
                "side": position.side,
                "action": "SELL",
                "price": current_price,
                "quantity": position.quantity,
                "total_usd": sale_value,
                "order_id": f"SELL_{reason.upper()}",
                "status": TradeStatus.FILLED.value,
                "filled_at": datetime.now(timezone.utc)
            })
            
            # Close position
            self.db.close_position(position_id, current_price, realized_pnl)
            
            # Log activity
            self.db.log_activity(
                level="INFO",
                module="trade_executor",
                message=f"Position closed: {reason}",
                details={
                    "position_id": position_id,
                    "market_id": position.market_id,
                    "realized_pnl": realized_pnl,
                    "reason": reason
                }
            )
            
            return TradeResult(
                success=True,
                trade_id=trade.id,
                order_id=f"SELL_{reason.upper()}",
                position_id=position_id,
                filled_price=current_price,
                filled_quantity=position.quantity,
                total_usd=sale_value,
                error_message=None
            )
            
        finally:
            session.close()
    
    def check_stop_losses(self) -> List[int]:
        """
        Check all positions for stop-loss triggers.
        
        Returns:
            List of position IDs that were stopped out
        """
        stopped_positions = []
        positions = self.db.get_open_positions()
        
        for position in positions:
            current_price = self.client.get_price(position.token_id, "SELL")
            if current_price is None:
                continue
            
            # Update position price
            self.db.update_position_prices(position.market_id, current_price)
            
            # Check stop-loss threshold
            if current_price < self.settings.stop_loss_threshold:
                logger.warning(
                    f"STOP LOSS triggered for position {position.id}: "
                    f"Price {current_price:.4f} < {self.settings.stop_loss_threshold}"
                )
                
                result = self.execute_sell(position.id, reason="stop_loss")
                if result.success:
                    stopped_positions.append(position.id)
        
        return stopped_positions
