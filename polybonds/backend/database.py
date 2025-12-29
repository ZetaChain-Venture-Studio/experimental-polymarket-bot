"""
Database models and operations using SQLAlchemy.
"""

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, 
    DateTime, Text, ForeignKey, Enum as SQLEnum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from typing import Optional, List
import enum
import json

Base = declarative_base()


# ===========================================
# ENUMS
# ===========================================

class TradeStatus(str, enum.Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PositionStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    SETTLED = "settled"


class Side(str, enum.Enum):
    YES = "YES"
    NO = "NO"


class Action(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class LogLevel(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"


# ===========================================
# MODELS
# ===========================================

class Market(Base):
    """Polymarket markets we're tracking."""
    __tablename__ = "markets"
    
    id = Column(String, primary_key=True)
    question = Column(Text, nullable=False)
    description = Column(Text)
    token_id_yes = Column(String)
    token_id_no = Column(String)
    end_date = Column(DateTime)
    category = Column(String)
    current_price_yes = Column(Float)
    current_price_no = Column(Float)
    volume_24h = Column(Float)
    last_scanned = Column(DateTime)
    is_eligible = Column(Boolean, default=False)
    eligibility_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    trades = relationship("Trade", back_populates="market")
    positions = relationship("Position", back_populates="market")
    settlements = relationship("Settlement", back_populates="market")


class Trade(Base):
    """Individual trades executed."""
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    market_id = Column(String, ForeignKey("markets.id"), nullable=False)
    token_id = Column(String, nullable=False)
    side = Column(String, nullable=False)  # YES or NO
    action = Column(String, nullable=False)  # BUY or SELL
    price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    total_usd = Column(Float, nullable=False)
    order_id = Column(String)
    status = Column(String, default=TradeStatus.PENDING.value)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    filled_at = Column(DateTime)
    
    # Relationships
    market = relationship("Market", back_populates="trades")


class Position(Base):
    """Aggregated positions (open holdings)."""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    market_id = Column(String, ForeignKey("markets.id"), nullable=False, unique=True)
    token_id = Column(String, nullable=False)
    side = Column(String, nullable=False)  # YES or NO
    quantity = Column(Float, nullable=False)
    avg_entry_price = Column(Float, nullable=False)
    total_cost_usd = Column(Float, nullable=False)
    current_price = Column(Float)
    current_value_usd = Column(Float)
    unrealized_pnl = Column(Float)
    unrealized_pnl_pct = Column(Float)
    status = Column(String, default=PositionStatus.OPEN.value)
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime)
    settlement_price = Column(Float)
    realized_pnl = Column(Float)
    
    # Relationships
    market = relationship("Market", back_populates="positions")


class PortfolioSnapshot(Base):
    """Portfolio snapshots for tracking performance over time."""
    __tablename__ = "portfolio_snapshots"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    total_value_usd = Column(Float)
    cash_balance_usd = Column(Float)
    positions_value_usd = Column(Float)
    total_realized_pnl = Column(Float)
    total_unrealized_pnl = Column(Float)
    open_positions_count = Column(Integer)
    total_trades_count = Column(Integer)
    winning_trades_count = Column(Integer)
    losing_trades_count = Column(Integer)
    win_rate = Column(Float)
    roi_pct = Column(Float)
    annualized_roi_pct = Column(Float)


class Settlement(Base):
    """Settlement history when markets resolve."""
    __tablename__ = "settlements"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    market_id = Column(String, ForeignKey("markets.id"), nullable=False)
    position_id = Column(Integer, ForeignKey("positions.id"))
    question = Column(Text)
    side = Column(String)
    entry_price = Column(Float)
    settlement_price = Column(Float)
    quantity = Column(Float)
    cost_usd = Column(Float)
    payout_usd = Column(Float)
    pnl_usd = Column(Float)
    pnl_pct = Column(Float)
    outcome = Column(String)  # 'win' or 'loss'
    settled_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    market = relationship("Market", back_populates="settlements")


class ActivityLog(Base):
    """Activity log for debugging and monitoring."""
    __tablename__ = "activity_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    level = Column(String, default=LogLevel.INFO.value)
    module = Column(String)
    message = Column(Text)
    details = Column(Text)  # JSON string for additional context


# ===========================================
# DATABASE MANAGER
# ===========================================

class DatabaseManager:
    """Manages database connections and operations."""
    
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
    def create_tables(self):
        """Create all tables if they don't exist."""
        Base.metadata.create_all(self.engine)
        
    def get_session(self):
        """Get a new database session."""
        return self.SessionLocal()
    
    # ===========================================
    # MARKET OPERATIONS
    # ===========================================
    
    def upsert_market(self, market_data: dict) -> Market:
        """Insert or update a market."""
        session = self.get_session()
        try:
            market = session.query(Market).filter_by(id=market_data["id"]).first()
            if market:
                for key, value in market_data.items():
                    setattr(market, key, value)
            else:
                market = Market(**market_data)
                session.add(market)
            session.commit()
            session.refresh(market)
            return market
        finally:
            session.close()
    
    def get_market(self, market_id: str) -> Optional[Market]:
        """Get a market by ID."""
        session = self.get_session()
        try:
            return session.query(Market).filter_by(id=market_id).first()
        finally:
            session.close()
    
    def get_eligible_markets(self) -> List[Market]:
        """Get all eligible markets."""
        session = self.get_session()
        try:
            return session.query(Market).filter_by(is_eligible=True).all()
        finally:
            session.close()
    
    # ===========================================
    # TRADE OPERATIONS
    # ===========================================
    
    def record_trade(self, trade_data: dict) -> Trade:
        """Record a new trade."""
        session = self.get_session()
        try:
            trade = Trade(**trade_data)
            session.add(trade)
            session.commit()
            session.refresh(trade)
            return trade
        finally:
            session.close()
    
    def update_trade_status(self, trade_id: int, status: str, 
                            filled_at: datetime = None, error_message: str = None):
        """Update trade status."""
        session = self.get_session()
        try:
            trade = session.query(Trade).filter_by(id=trade_id).first()
            if trade:
                trade.status = status
                if filled_at:
                    trade.filled_at = filled_at
                if error_message:
                    trade.error_message = error_message
                session.commit()
        finally:
            session.close()
    
    def get_recent_trades(self, limit: int = 50) -> List[Trade]:
        """Get recent trades."""
        session = self.get_session()
        try:
            return session.query(Trade).order_by(Trade.created_at.desc()).limit(limit).all()
        finally:
            session.close()
    
    # ===========================================
    # POSITION OPERATIONS
    # ===========================================
    
    def get_position(self, market_id: str) -> Optional[Position]:
        """Get position for a market."""
        session = self.get_session()
        try:
            return session.query(Position).filter_by(
                market_id=market_id, 
                status=PositionStatus.OPEN.value
            ).first()
        finally:
            session.close()
    
    def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        session = self.get_session()
        try:
            return session.query(Position).filter_by(status=PositionStatus.OPEN.value).all()
        finally:
            session.close()
    
    def create_or_update_position(self, position_data: dict) -> Position:
        """Create or update a position."""
        session = self.get_session()
        try:
            position = session.query(Position).filter_by(
                market_id=position_data["market_id"],
                status=PositionStatus.OPEN.value
            ).first()
            
            if position:
                # Update existing position (average in)
                new_qty = position.quantity + position_data["quantity"]
                new_cost = position.total_cost_usd + position_data["total_cost_usd"]
                position.quantity = new_qty
                position.total_cost_usd = new_cost
                position.avg_entry_price = new_cost / new_qty
            else:
                # Create new position
                position = Position(**position_data)
                session.add(position)
            
            session.commit()
            session.refresh(position)
            return position
        finally:
            session.close()
    
    def update_position_prices(self, market_id: str, current_price: float):
        """Update position with current price."""
        session = self.get_session()
        try:
            position = session.query(Position).filter_by(
                market_id=market_id,
                status=PositionStatus.OPEN.value
            ).first()
            
            if position:
                position.current_price = current_price
                position.current_value_usd = position.quantity * current_price
                position.unrealized_pnl = position.current_value_usd - position.total_cost_usd
                position.unrealized_pnl_pct = (position.unrealized_pnl / position.total_cost_usd) * 100
                session.commit()
        finally:
            session.close()
    
    def close_position(self, position_id: int, settlement_price: float, realized_pnl: float):
        """Close a position after settlement."""
        session = self.get_session()
        try:
            position = session.query(Position).filter_by(id=position_id).first()
            if position:
                position.status = PositionStatus.SETTLED.value
                position.closed_at = datetime.utcnow()
                position.settlement_price = settlement_price
                position.realized_pnl = realized_pnl
                session.commit()
        finally:
            session.close()
    
    # ===========================================
    # PORTFOLIO OPERATIONS
    # ===========================================
    
    def get_total_positions_value(self) -> float:
        """Get total value of all open positions."""
        session = self.get_session()
        try:
            positions = session.query(Position).filter_by(status=PositionStatus.OPEN.value).all()
            return sum(p.current_value_usd or p.total_cost_usd for p in positions)
        finally:
            session.close()
    
    def get_total_realized_pnl(self) -> float:
        """Get total realized P&L from all settlements."""
        session = self.get_session()
        try:
            settlements = session.query(Settlement).all()
            return sum(s.pnl_usd or 0 for s in settlements)
        finally:
            session.close()
    
    def save_portfolio_snapshot(self, snapshot_data: dict) -> PortfolioSnapshot:
        """Save a portfolio snapshot."""
        session = self.get_session()
        try:
            snapshot = PortfolioSnapshot(**snapshot_data)
            session.add(snapshot)
            session.commit()
            session.refresh(snapshot)
            return snapshot
        finally:
            session.close()
    
    def get_latest_snapshot(self) -> Optional[PortfolioSnapshot]:
        """Get the most recent portfolio snapshot."""
        session = self.get_session()
        try:
            return session.query(PortfolioSnapshot).order_by(
                PortfolioSnapshot.timestamp.desc()
            ).first()
        finally:
            session.close()
    
    # ===========================================
    # SETTLEMENT OPERATIONS
    # ===========================================
    
    def record_settlement(self, settlement_data: dict) -> Settlement:
        """Record a market settlement."""
        session = self.get_session()
        try:
            settlement = Settlement(**settlement_data)
            session.add(settlement)
            session.commit()
            session.refresh(settlement)
            return settlement
        finally:
            session.close()
    
    def get_recent_settlements(self, limit: int = 50) -> List[Settlement]:
        """Get recent settlements."""
        session = self.get_session()
        try:
            return session.query(Settlement).order_by(
                Settlement.settled_at.desc()
            ).limit(limit).all()
        finally:
            session.close()
    
    # ===========================================
    # LOGGING OPERATIONS
    # ===========================================
    
    def log_activity(self, level: str, module: str, message: str, details: dict = None):
        """Log an activity."""
        session = self.get_session()
        try:
            log = ActivityLog(
                level=level,
                module=module,
                message=message,
                details=json.dumps(details) if details else None
            )
            session.add(log)
            session.commit()
        finally:
            session.close()
    
    def get_recent_logs(self, limit: int = 100, level: str = None) -> List[ActivityLog]:
        """Get recent activity logs."""
        session = self.get_session()
        try:
            query = session.query(ActivityLog)
            if level:
                query = query.filter_by(level=level)
            return query.order_by(ActivityLog.timestamp.desc()).limit(limit).all()
        finally:
            session.close()


# ===========================================
# SINGLETON INSTANCE
# ===========================================

_db_manager: Optional[DatabaseManager] = None

def get_db(database_url: str = None) -> DatabaseManager:
    """Get or create database manager singleton."""
    global _db_manager
    if _db_manager is None:
        if database_url is None:
            from .config import settings
            database_url = settings.database_url
        _db_manager = DatabaseManager(database_url)
        _db_manager.create_tables()
    return _db_manager
