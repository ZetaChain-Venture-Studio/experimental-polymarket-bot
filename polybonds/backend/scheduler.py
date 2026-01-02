"""
Scheduler Module.
Handles automated background tasks using APScheduler.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from .config import Settings, get_settings
from .database import DatabaseManager, get_db, PositionStatus
from .market_scanner import MarketScanner
from .trade_executor import TradeExecutor
from .polymarket_client import get_client

logger = logging.getLogger(__name__)


class PolybondsScheduler:
    """
    Manages scheduled tasks for the Polybonds trading system.

    Tasks:
    - Market scan: Find new opportunities (every 5 minutes)
    - Stop-loss check: Monitor positions (every 1 minute)
    - Settlement monitor: Check resolved markets (every hour)
    - Portfolio snapshot: Save portfolio state (every 10 minutes)
    """

    def __init__(
        self,
        settings: Settings = None,
        db: DatabaseManager = None,
        portfolio_value: float = 10000
    ):
        self.settings = settings or get_settings()
        self.db = db or get_db()
        self.portfolio_value = portfolio_value

        self.scanner = MarketScanner(settings=self.settings, db=self.db)
        self.executor = TradeExecutor(settings=self.settings, db=self.db)
        self.client = get_client(self.settings)

        self.scheduler = BackgroundScheduler(timezone="UTC")
        self._setup_jobs()
        self._setup_listeners()

    def _setup_jobs(self):
        """Configure all scheduled jobs."""

        # Market scan - every 5 minutes
        self.scheduler.add_job(
            self.job_scan_markets,
            IntervalTrigger(minutes=5),
            id="scan_markets",
            name="Market Scanner",
            replace_existing=True,
            max_instances=1
        )

        # Stop-loss check - every 1 minute
        self.scheduler.add_job(
            self.job_check_stop_losses,
            IntervalTrigger(minutes=1),
            id="check_stop_losses",
            name="Stop-Loss Monitor",
            replace_existing=True,
            max_instances=1
        )

        # Settlement monitor - every hour
        self.scheduler.add_job(
            self.job_check_settlements,
            IntervalTrigger(hours=1),
            id="check_settlements",
            name="Settlement Monitor",
            replace_existing=True,
            max_instances=1
        )

        # Portfolio snapshot - every 10 minutes
        self.scheduler.add_job(
            self.job_portfolio_snapshot,
            IntervalTrigger(minutes=10),
            id="portfolio_snapshot",
            name="Portfolio Snapshot",
            replace_existing=True,
            max_instances=1
        )

    def _setup_listeners(self):
        """Set up event listeners for job monitoring."""

        def job_listener(event):
            if event.exception:
                logger.error(
                    f"Job {event.job_id} failed with exception: {event.exception}"
                )
                self.db.log_activity(
                    level="ERROR",
                    module="scheduler",
                    message=f"Job {event.job_id} failed",
                    details={"error": str(event.exception)}
                )
            else:
                logger.debug(f"Job {event.job_id} completed successfully")

        self.scheduler.add_listener(
            job_listener,
            EVENT_JOB_ERROR | EVENT_JOB_EXECUTED
        )

    # ===========================================
    # SCHEDULED JOBS
    # ===========================================

    def job_scan_markets(self):
        """
        Scan for Polybond opportunities and optionally execute trades.
        Runs every 5 minutes.
        """
        logger.info("Starting scheduled market scan...")

        try:
            # Scan for opportunities
            opportunities = self.scanner.scan_all_markets()

            self.db.log_activity(
                level="INFO",
                module="scheduler",
                message=f"Market scan completed: {len(opportunities)} opportunities found",
                details={"count": len(opportunities)}
            )

            if not opportunities:
                logger.info("No opportunities found")
                return

            # Auto-trade if enabled
            if self.settings.auto_trading_enabled:
                logger.info("Auto-trading enabled - executing trades on top opportunities")

                max_trades = 3  # Max trades per scan
                executed = 0

                for opp in opportunities[:max_trades]:
                    if executed >= max_trades:
                        break

                    result = self.executor.execute_polybond_buy(
                        opp,
                        portfolio_value=self.portfolio_value
                    )

                    if result.success:
                        logger.info(
                            f"Auto-trade executed: {opp.question[:50]}... "
                            f"${result.total_usd:.2f} @ ${result.filled_price:.4f}"
                        )
                        executed += 1
                    else:
                        logger.warning(f"Auto-trade blocked: {result.error_message}")

                logger.info(f"Auto-trading complete: {executed}/{max_trades} trades executed")
            else:
                logger.info(
                    f"Found {len(opportunities)} opportunities "
                    "(auto-trading disabled - view in dashboard)"
                )

        except Exception as e:
            logger.error(f"Market scan failed: {e}")
            raise

    def job_check_stop_losses(self):
        """
        Check all positions for stop-loss triggers.
        Runs every 1 minute.
        """
        logger.debug("Checking stop-losses...")

        try:
            # Initialize client for price checks
            if not self.client.is_initialized:
                self.client.initialize(read_only=True)

            positions = self.db.get_open_positions()

            if not positions:
                return

            stopped_count = 0

            for position in positions:
                # Get current price
                current_price = self.client.get_price(position.token_id, "SELL")

                if current_price is None:
                    continue

                # Update position price in database
                self.db.update_position_prices(position.market_id, current_price)

                # Check stop-loss threshold
                if current_price < self.settings.stop_loss_threshold:
                    logger.warning(
                        f"STOP-LOSS TRIGGERED: Position {position.id} "
                        f"({position.side}) price {current_price:.4f} < "
                        f"threshold {self.settings.stop_loss_threshold}"
                    )

                    # Execute stop-loss sell
                    result = self.executor.execute_sell(
                        position.id,
                        reason="stop_loss"
                    )

                    if result.success:
                        stopped_count += 1
                        self.db.log_activity(
                            level="WARNING",
                            module="scheduler",
                            message=f"Stop-loss executed for position {position.id}",
                            details={
                                "position_id": position.id,
                                "market_id": position.market_id,
                                "trigger_price": current_price,
                                "realized_pnl": result.total_usd - position.total_cost_usd
                            }
                        )

            if stopped_count > 0:
                logger.warning(f"Stop-loss check: {stopped_count} positions stopped out")

        except Exception as e:
            logger.error(f"Stop-loss check failed: {e}")
            raise

    def job_check_settlements(self):
        """
        Check if any markets with open positions have settled.
        Runs every hour.
        """
        logger.info("Checking for market settlements...")

        try:
            # Initialize client
            if not self.client.is_initialized:
                self.client.initialize(read_only=True)

            positions = self.db.get_open_positions()

            if not positions:
                logger.info("No open positions to check for settlements")
                return

            settled_count = 0

            for position in positions:
                # Get market info
                market = self.db.get_market(position.market_id)
                if not market:
                    continue

                # Check if market has ended
                if market.end_date and market.end_date < datetime.now(timezone.utc):
                    # Try to get settlement price from API
                    # If market is settled, price should be 0 or 1
                    current_price = self.client.get_price(position.token_id, "SELL")

                    if current_price is not None and (current_price <= 0.01 or current_price >= 0.99):
                        # Market has likely settled
                        settlement_price = 1.0 if current_price >= 0.99 else 0.0

                        # Calculate P&L
                        payout = position.quantity * settlement_price
                        pnl = payout - position.total_cost_usd
                        pnl_pct = (pnl / position.total_cost_usd) * 100
                        outcome = "win" if pnl >= 0 else "loss"

                        logger.info(
                            f"Settlement detected: {market.question[:50]}... "
                            f"- {outcome.upper()} - P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)"
                        )

                        # Record settlement
                        self.db.record_settlement({
                            "market_id": position.market_id,
                            "position_id": position.id,
                            "question": market.question,
                            "side": position.side,
                            "entry_price": position.avg_entry_price,
                            "settlement_price": settlement_price,
                            "quantity": position.quantity,
                            "cost_usd": position.total_cost_usd,
                            "payout_usd": payout,
                            "pnl_usd": pnl,
                            "pnl_pct": pnl_pct,
                            "outcome": outcome
                        })

                        # Close position
                        self.db.close_position(position.id, settlement_price, pnl)

                        settled_count += 1

                        self.db.log_activity(
                            level="INFO",
                            module="scheduler",
                            message=f"Market settled: {outcome}",
                            details={
                                "market_id": position.market_id,
                                "question": market.question[:100],
                                "pnl_usd": pnl,
                                "pnl_pct": pnl_pct
                            }
                        )

            logger.info(f"Settlement check complete: {settled_count} positions settled")

        except Exception as e:
            logger.error(f"Settlement check failed: {e}")
            raise

    def job_portfolio_snapshot(self):
        """
        Save a snapshot of the current portfolio state.
        Runs every 10 minutes.
        """
        logger.debug("Taking portfolio snapshot...")

        try:
            # Get all open positions
            positions = self.db.get_open_positions()

            # Calculate values
            positions_value = sum(
                p.current_value_usd or p.total_cost_usd
                for p in positions
            )

            total_unrealized_pnl = sum(
                p.unrealized_pnl or 0
                for p in positions
            )

            total_realized_pnl = self.db.get_total_realized_pnl()

            # Get trade stats from settlements
            session = self.db.get_session()
            try:
                from .database import Settlement
                settlements = session.query(Settlement).all()
                total_trades = len(settlements)
                winning_trades = len([s for s in settlements if s.outcome == "win"])
                losing_trades = len([s for s in settlements if s.outcome == "loss"])
            finally:
                session.close()

            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

            # Estimate total value (positions + assumed cash)
            # In real implementation, would track actual cash balance
            cash_balance = max(0, self.portfolio_value - positions_value)
            total_value = positions_value + cash_balance

            # Calculate ROI
            initial_value = self.portfolio_value
            roi_pct = ((total_value + total_realized_pnl - initial_value) / initial_value) * 100

            # Save snapshot
            snapshot = self.db.save_portfolio_snapshot({
                "total_value_usd": total_value,
                "cash_balance_usd": cash_balance,
                "positions_value_usd": positions_value,
                "total_realized_pnl": total_realized_pnl,
                "total_unrealized_pnl": total_unrealized_pnl,
                "open_positions_count": len(positions),
                "total_trades_count": total_trades,
                "winning_trades_count": winning_trades,
                "losing_trades_count": losing_trades,
                "win_rate": win_rate,
                "roi_pct": roi_pct,
                "annualized_roi_pct": roi_pct * 12  # Rough estimate
            })

            logger.debug(
                f"Portfolio snapshot saved: ${total_value:.2f} "
                f"({len(positions)} positions, ROI: {roi_pct:+.1f}%)"
            )

        except Exception as e:
            logger.error(f"Portfolio snapshot failed: {e}")
            raise

    # ===========================================
    # CONTROL METHODS
    # ===========================================

    def start(self):
        """Start the scheduler."""
        logger.info("Starting Polybonds scheduler...")

        # Run initial jobs immediately
        logger.info("Running initial scan...")
        self.job_scan_markets()

        logger.info("Taking initial portfolio snapshot...")
        self.job_portfolio_snapshot()

        # Start scheduler
        self.scheduler.start()

        logger.info("Scheduler started with the following jobs:")
        for job in self.scheduler.get_jobs():
            logger.info(f"  - {job.name}: {job.trigger}")

        self.db.log_activity(
            level="INFO",
            module="scheduler",
            message="Scheduler started",
            details={
                "auto_trading": self.settings.auto_trading_enabled,
                "portfolio_value": self.portfolio_value
            }
        )

    def stop(self):
        """Stop the scheduler."""
        logger.info("Stopping Polybonds scheduler...")
        self.scheduler.shutdown(wait=True)

        self.db.log_activity(
            level="INFO",
            module="scheduler",
            message="Scheduler stopped"
        )

    def run_job_now(self, job_id: str):
        """Manually trigger a specific job."""
        job = self.scheduler.get_job(job_id)
        if job:
            logger.info(f"Manually running job: {job.name}")
            job.func()
        else:
            logger.error(f"Job not found: {job_id}")

    def get_status(self) -> dict:
        """Get scheduler status."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger)
            })

        return {
            "running": self.scheduler.running,
            "auto_trading": self.settings.auto_trading_enabled,
            "portfolio_value": self.portfolio_value,
            "jobs": jobs
        }


# ===========================================
# CONVENIENCE FUNCTION
# ===========================================

def create_scheduler(
    settings: Settings = None,
    db: DatabaseManager = None,
    portfolio_value: float = 10000
) -> PolybondsScheduler:
    """Create and return a scheduler instance."""
    return PolybondsScheduler(
        settings=settings,
        db=db,
        portfolio_value=portfolio_value
    )
