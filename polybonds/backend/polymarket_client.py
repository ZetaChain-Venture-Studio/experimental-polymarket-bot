"""
Polymarket API Client Wrapper.
Provides a simplified interface around py-clob-client.
"""

import httpx
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import logging

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import (
        OrderArgs, MarketOrderArgs, OrderType, BookParams, OpenOrderParams
    )
    from py_clob_client.order_builder.constants import BUY, SELL
    CLOB_AVAILABLE = True
except ImportError:
    CLOB_AVAILABLE = False
    print("Warning: py-clob-client not installed. Install with: pip install py-clob-client")

from .config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class MarketInfo:
    """Simplified market information."""
    id: str
    question: str
    description: str
    end_date: Optional[datetime]
    category: str
    token_id_yes: str
    token_id_no: str
    price_yes: float
    price_no: float
    volume_24h: float
    liquidity: float
    active: bool


@dataclass
class OrderResult:
    """Result of an order operation."""
    success: bool
    order_id: Optional[str]
    filled_price: Optional[float]
    filled_quantity: Optional[float]
    error_message: Optional[str]


class PolymarketClient:
    """
    Wrapper around Polymarket's CLOB API.
    Provides simplified methods for trading and data retrieval.
    """
    
    def __init__(self, settings: Settings = None):
        self.settings = settings or get_settings()
        self._clob_client: Optional[ClobClient] = None
        self._authenticated = False
        self._http_client = httpx.Client(timeout=30.0)
        
    # ===========================================
    # INITIALIZATION
    # ===========================================
    
    def initialize(self, read_only: bool = False) -> bool:
        """
        Initialize the CLOB client.
        
        Args:
            read_only: If True, skip authentication (for scanning only)
            
        Returns:
            True if initialization successful
        """
        if not CLOB_AVAILABLE:
            logger.error("py-clob-client not installed")
            return False
            
        try:
            if read_only:
                # Level 0: No authentication needed for reading
                self._clob_client = ClobClient(self.settings.clob_api_url)
                logger.info("CLOB client initialized in read-only mode")
                return True
            
            # Level 1 & 2: Full authentication for trading
            self._clob_client = ClobClient(
                host=self.settings.clob_api_url,
                key=self.settings.polymarket_private_key,
                chain_id=self.settings.polymarket_chain_id,
                signature_type=self.settings.polymarket_signature_type,
                funder=self.settings.polymarket_funder_address
            )
            
            # Create/derive API credentials
            api_creds = self._clob_client.create_or_derive_api_creds()
            self._clob_client.set_api_creds(api_creds)
            self._authenticated = True
            
            logger.info("CLOB client initialized with full authentication")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize CLOB client: {e}")
            return False
    
    @property
    def is_authenticated(self) -> bool:
        """Check if client is authenticated for trading."""
        return self._authenticated
    
    # ===========================================
    # MARKET DATA (Gamma API)
    # ===========================================
    
    def get_all_markets(self) -> List[Dict[str, Any]]:
        """
        Fetch all markets from Gamma API.
        
        Returns:
            List of market dictionaries
        """
        try:
            url = f"{self.settings.gamma_api_url}/markets"
            response = self._http_client.get(url, params={"active": "true"})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            return []
    
    def get_market(self, market_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single market by ID.
        
        Args:
            market_id: The market's condition ID
            
        Returns:
            Market dictionary or None
        """
        try:
            url = f"{self.settings.gamma_api_url}/markets/{market_id}"
            response = self._http_client.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch market {market_id}: {e}")
            return None
    
    def get_events(self) -> List[Dict[str, Any]]:
        """
        Fetch all events (grouped markets).
        
        Returns:
            List of event dictionaries
        """
        try:
            url = f"{self.settings.gamma_api_url}/events"
            response = self._http_client.get(url, params={"active": "true"})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch events: {e}")
            return []
    
    # ===========================================
    # ORDER BOOK DATA (CLOB API)
    # ===========================================
    
    def get_price(self, token_id: str, side: str = "BUY") -> Optional[float]:
        """
        Get the current best price for a token.
        
        Args:
            token_id: The outcome token ID
            side: "BUY" or "SELL"
            
        Returns:
            Price as float or None
        """
        if not self._clob_client:
            self.initialize(read_only=True)
            
        try:
            price = self._clob_client.get_price(token_id, side=side)
            return float(price) if price else None
        except Exception as e:
            logger.error(f"Failed to get price for {token_id}: {e}")
            return None
    
    def get_midpoint(self, token_id: str) -> Optional[float]:
        """
        Get the midpoint price for a token.
        
        Args:
            token_id: The outcome token ID
            
        Returns:
            Midpoint price as float or None
        """
        if not self._clob_client:
            self.initialize(read_only=True)
            
        try:
            mid = self._clob_client.get_midpoint(token_id)
            return float(mid) if mid else None
        except Exception as e:
            logger.error(f"Failed to get midpoint for {token_id}: {e}")
            return None
    
    def get_order_book(self, token_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the full order book for a token.
        
        Args:
            token_id: The outcome token ID
            
        Returns:
            Order book dictionary or None
        """
        if not self._clob_client:
            self.initialize(read_only=True)
            
        try:
            book = self._clob_client.get_order_book(token_id)
            return {
                "market": book.market,
                "asset_id": book.asset_id,
                "bids": [{"price": b.price, "size": b.size} for b in book.bids],
                "asks": [{"price": a.price, "size": a.size} for a in book.asks],
            }
        except Exception as e:
            logger.error(f"Failed to get order book for {token_id}: {e}")
            return None
    
    def get_spread(self, token_id: str) -> Optional[Dict[str, float]]:
        """
        Get bid-ask spread for a token.
        
        Args:
            token_id: The outcome token ID
            
        Returns:
            Dictionary with best_bid, best_ask, spread
        """
        if not self._clob_client:
            self.initialize(read_only=True)
            
        try:
            spread = self._clob_client.get_spread(token_id)
            return {
                "best_bid": float(spread.get("bid", 0)),
                "best_ask": float(spread.get("ask", 0)),
                "spread": float(spread.get("spread", 0))
            }
        except Exception as e:
            logger.error(f"Failed to get spread for {token_id}: {e}")
            return None
    
    # ===========================================
    # TRADING OPERATIONS
    # ===========================================
    
    def place_limit_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        price: float,
        size: float
    ) -> OrderResult:
        """
        Place a limit order.
        
        Args:
            token_id: The outcome token ID
            side: "BUY" or "SELL"
            price: Limit price (0.01 to 0.99)
            size: Number of shares
            
        Returns:
            OrderResult with success status and details
        """
        if not self._authenticated:
            return OrderResult(
                success=False,
                order_id=None,
                filled_price=None,
                filled_quantity=None,
                error_message="Client not authenticated. Call initialize() first."
            )
        
        try:
            order_side = BUY if side.upper() == "BUY" else SELL
            
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=order_side
            )
            
            signed_order = self._clob_client.create_order(order_args)
            response = self._clob_client.post_order(signed_order, OrderType.GTC)
            
            if response.get("success"):
                return OrderResult(
                    success=True,
                    order_id=response.get("orderID"),
                    filled_price=price,
                    filled_quantity=size,
                    error_message=None
                )
            else:
                return OrderResult(
                    success=False,
                    order_id=None,
                    filled_price=None,
                    filled_quantity=None,
                    error_message=response.get("errorMsg", "Unknown error")
                )
                
        except Exception as e:
            logger.error(f"Failed to place limit order: {e}")
            return OrderResult(
                success=False,
                order_id=None,
                filled_price=None,
                filled_quantity=None,
                error_message=str(e)
            )
    
    def place_market_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        amount: float  # USD amount for BUY, share amount for SELL
    ) -> OrderResult:
        """
        Place a market order (Fill-or-Kill).
        
        Args:
            token_id: The outcome token ID
            side: "BUY" or "SELL"
            amount: USD amount (BUY) or shares (SELL)
            
        Returns:
            OrderResult with success status and details
        """
        if not self._authenticated:
            return OrderResult(
                success=False,
                order_id=None,
                filled_price=None,
                filled_quantity=None,
                error_message="Client not authenticated. Call initialize() first."
            )
        
        try:
            order_side = BUY if side.upper() == "BUY" else SELL
            
            market_order_args = MarketOrderArgs(
                token_id=token_id,
                amount=amount,
                side=order_side
            )
            
            signed_order = self._clob_client.create_market_order(market_order_args)
            response = self._clob_client.post_order(signed_order, OrderType.FOK)
            
            if response.get("success"):
                return OrderResult(
                    success=True,
                    order_id=response.get("orderID"),
                    filled_price=None,  # Market orders don't have fixed price
                    filled_quantity=amount,
                    error_message=None
                )
            else:
                return OrderResult(
                    success=False,
                    order_id=None,
                    filled_price=None,
                    filled_quantity=None,
                    error_message=response.get("errorMsg", "Unknown error")
                )
                
        except Exception as e:
            logger.error(f"Failed to place market order: {e}")
            return OrderResult(
                success=False,
                order_id=None,
                filled_price=None,
                filled_quantity=None,
                error_message=str(e)
            )
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.
        
        Args:
            order_id: The order ID to cancel
            
        Returns:
            True if cancellation successful
        """
        if not self._authenticated:
            return False
            
        try:
            self._clob_client.cancel(order_id)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    def cancel_all_orders(self) -> bool:
        """
        Cancel all open orders.
        
        Returns:
            True if cancellation successful
        """
        if not self._authenticated:
            return False
            
        try:
            self._clob_client.cancel_all()
            return True
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return False
    
    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Get all open orders for the authenticated user.
        
        Returns:
            List of open order dictionaries
        """
        if not self._authenticated:
            return []
            
        try:
            orders = self._clob_client.get_orders(OpenOrderParams())
            return orders if orders else []
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []
    
    # ===========================================
    # ACCOUNT DATA
    # ===========================================
    
    def get_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get trade history for the authenticated user.

        Args:
            limit: Maximum number of trades to return

        Returns:
            List of trade dictionaries
        """
        if not self._authenticated:
            return []

        try:
            trades = self._clob_client.get_trades()
            return trades[:limit] if trades else []
        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return []

    def get_balance(self) -> Optional[float]:
        """
        Get USDC balance from the Polymarket account.

        Returns:
            Balance in USDC or None if unavailable
        """
        if not self._clob_client:
            return None

        try:
            # Try to get balance from CLOB client
            balance_info = self._clob_client.get_balance_allowance()
            if balance_info and 'balance' in balance_info:
                # Balance is in wei (6 decimals for USDC)
                return float(balance_info['balance']) / 1e6
        except Exception as e:
            logger.warning(f"Could not get balance from CLOB: {e}")

        return None
    
    # ===========================================
    # UTILITY METHODS
    # ===========================================
    
    def parse_market_info(self, market_data: Dict[str, Any]) -> Optional[MarketInfo]:
        """
        Parse raw market data into MarketInfo dataclass.
        
        Args:
            market_data: Raw market dictionary from API
            
        Returns:
            MarketInfo object or None
        """
        try:
            tokens = market_data.get("tokens", [])
            if len(tokens) < 2:
                return None
            
            # Find YES and NO tokens
            yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), tokens[0])
            no_token = next((t for t in tokens if t.get("outcome") == "No"), tokens[1])
            
            # Parse end date
            end_date = None
            end_date_str = market_data.get("endDate") or market_data.get("end_date_iso")
            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                except:
                    pass
            
            return MarketInfo(
                id=market_data.get("conditionId") or market_data.get("id"),
                question=market_data.get("question", ""),
                description=market_data.get("description", ""),
                end_date=end_date,
                category=market_data.get("category", ""),
                token_id_yes=yes_token.get("token_id", ""),
                token_id_no=no_token.get("token_id", ""),
                price_yes=float(yes_token.get("price", 0)),
                price_no=float(no_token.get("price", 0)),
                volume_24h=float(market_data.get("volume24hr", 0) or market_data.get("volume", 0)),
                liquidity=float(market_data.get("liquidity", 0)),
                active=market_data.get("active", True)
            )
        except Exception as e:
            logger.error(f"Failed to parse market info: {e}")
            return None
    
    def close(self):
        """Close HTTP client."""
        self._http_client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ===========================================
# SINGLETON INSTANCE
# ===========================================

_client: Optional[PolymarketClient] = None

def get_client(settings: Settings = None) -> PolymarketClient:
    """Get or create Polymarket client singleton."""
    global _client
    if _client is None:
        _client = PolymarketClient(settings)
    return _client
