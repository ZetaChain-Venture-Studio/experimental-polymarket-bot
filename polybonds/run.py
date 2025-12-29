#!/usr/bin/env python3
"""
Polybonds Trading System - Main Entry Point

Usage:
    python run.py scan           # Scan for opportunities
    python run.py trade          # Scan and execute trades
    python run.py positions      # View open positions
    python run.py history        # View trade history
    python run.py server         # Start API server
    python run.py --help         # Show help
"""

import argparse
import sys
import logging
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("polybonds")


def setup_environment():
    """Load environment and initialize database."""
    from dotenv import load_dotenv
    load_dotenv()
    
    from backend.config import get_settings
    from backend.database import get_db
    
    settings = get_settings()
    db = get_db(settings.database_url)
    
    return settings, db


def cmd_scan(args):
    """Scan for Polybond opportunities."""
    print("\n🔍 Scanning for Polybond opportunities...\n")
    
    settings, db = setup_environment()
    
    from backend.market_scanner import MarketScanner, print_opportunities
    
    scanner = MarketScanner(settings=settings, db=db)
    opportunities = scanner.scan_all_markets()
    
    # Print summary
    summary = scanner.get_summary(opportunities)
    print(f"\n📊 Summary:")
    print(f"   Total opportunities: {summary['total']}")
    if summary['total'] > 0:
        print(f"   Average return: {summary['avg_return_pct']:.2f}%")
        print(f"   Average annualized: {summary['avg_annualized_pct']:.0f}%")
        print(f"   Average risk score: {summary['avg_risk_score']:.0f}/100")
        print(f"   Total 24h volume: ${summary['total_volume_24h']:,.0f}")
    
    # Print opportunities
    limit = args.limit if hasattr(args, 'limit') else 20
    print_opportunities(opportunities, limit=limit)
    
    return opportunities


def cmd_trade(args):
    """Scan and execute trades."""
    print("\n💰 Scanning and trading Polybonds...\n")
    
    settings, db = setup_environment()
    
    # Check if trading is enabled
    if not settings.auto_trading_enabled:
        print("⚠️  AUTO_TRADING_ENABLED=false - Running in simulation mode")
        print("   Set AUTO_TRADING_ENABLED=true in .env to execute real trades\n")
    
    from backend.market_scanner import MarketScanner
    from backend.trade_executor import TradeExecutor
    
    scanner = MarketScanner(settings=settings, db=db)
    executor = TradeExecutor(settings=settings, db=db)
    
    # Scan for opportunities
    opportunities = scanner.scan_all_markets()
    
    if not opportunities:
        print("No opportunities found matching criteria.")
        return
    
    # Execute trades on top opportunities
    max_trades = args.max_trades if hasattr(args, 'max_trades') else 5
    portfolio_value = args.portfolio if hasattr(args, 'portfolio') else 10000
    
    print(f"\n📈 Executing up to {max_trades} trades (portfolio: ${portfolio_value:,.0f}):\n")
    
    executed = 0
    for opp in opportunities[:max_trades]:
        print(f"\n{'='*60}")
        print(f"📌 {opp.question[:60]}...")
        print(f"   Side: {opp.side} @ ${opp.current_price:.4f}")
        print(f"   Return: {opp.potential_return_pct:.2f}% ({opp.annualized_return_pct:.0f}% APY)")
        print(f"   Risk: {opp.risk_score}/100")
        
        result = executor.execute_polybond_buy(opp, portfolio_value=portfolio_value)
        
        if result.success:
            print(f"   ✅ EXECUTED: ${result.total_usd:.2f} @ ${result.filled_price:.4f}")
            executed += 1
        else:
            print(f"   ❌ BLOCKED: {result.error_message}")
    
    print(f"\n{'='*60}")
    print(f"✨ Executed {executed}/{max_trades} trades")


def cmd_positions(args):
    """View open positions."""
    print("\n📊 Open Positions:\n")
    
    settings, db = setup_environment()
    
    from backend.polymarket_client import get_client
    
    positions = db.get_open_positions()
    
    if not positions:
        print("No open positions.\n")
        return
    
    client = get_client(settings)
    client.initialize(read_only=True)
    
    total_cost = 0
    total_value = 0
    total_pnl = 0
    
    print(f"{'Market':<50} {'Side':<5} {'Entry':<8} {'Current':<8} {'P&L':<12}")
    print("-" * 90)
    
    for pos in positions:
        # Update current price
        current_price = client.get_price(pos.token_id, "SELL")
        if current_price:
            db.update_position_prices(pos.market_id, current_price)
            current_value = pos.quantity * current_price
            pnl = current_value - pos.total_cost_usd
            pnl_pct = (pnl / pos.total_cost_usd) * 100 if pos.total_cost_usd > 0 else 0
        else:
            current_price = pos.avg_entry_price
            current_value = pos.total_cost_usd
            pnl = 0
            pnl_pct = 0
        
        # Get market info
        market = db.get_market(pos.market_id)
        question = market.question[:47] + "..." if market and len(market.question) > 50 else (market.question if market else pos.market_id[:47])
        
        pnl_str = f"${pnl:+.2f} ({pnl_pct:+.1f}%)"
        
        print(f"{question:<50} {pos.side:<5} ${pos.avg_entry_price:<7.4f} ${current_price:<7.4f} {pnl_str:<12}")
        
        total_cost += pos.total_cost_usd
        total_value += current_value
        total_pnl += pnl
    
    print("-" * 90)
    total_pnl_pct = (total_pnl / total_cost) * 100 if total_cost > 0 else 0
    print(f"{'TOTAL':<50} {'':<5} ${total_cost:<7.2f} ${total_value:<7.2f} ${total_pnl:+.2f} ({total_pnl_pct:+.1f}%)")
    print()


def cmd_history(args):
    """View trade history."""
    print("\n📜 Trade History:\n")
    
    settings, db = setup_environment()
    
    limit = args.limit if hasattr(args, 'limit') else 20
    trades = db.get_recent_trades(limit=limit)
    
    if not trades:
        print("No trades yet.\n")
        return
    
    print(f"{'Time':<20} {'Action':<6} {'Side':<5} {'Price':<8} {'Amount':<10} {'Status':<10}")
    print("-" * 70)
    
    for trade in trades:
        time_str = trade.created_at.strftime("%Y-%m-%d %H:%M") if trade.created_at else "N/A"
        print(f"{time_str:<20} {trade.action:<6} {trade.side:<5} ${trade.price:<7.4f} ${trade.total_usd:<9.2f} {trade.status:<10}")
    
    print()


def cmd_settlements(args):
    """View settlement history."""
    print("\n✅ Settlement History:\n")
    
    settings, db = setup_environment()
    
    limit = args.limit if hasattr(args, 'limit') else 20
    settlements = db.get_recent_settlements(limit=limit)
    
    if not settlements:
        print("No settlements yet.\n")
        return
    
    total_pnl = 0
    wins = 0
    losses = 0
    
    print(f"{'Time':<20} {'Outcome':<8} {'Entry':<8} {'Settled':<8} {'P&L':<12}")
    print("-" * 60)
    
    for s in settlements:
        time_str = s.settled_at.strftime("%Y-%m-%d %H:%M") if s.settled_at else "N/A"
        pnl_str = f"${s.pnl_usd:+.2f}"
        outcome_emoji = "🟢" if s.outcome == "win" else "🔴"
        
        print(f"{time_str:<20} {outcome_emoji} {s.outcome:<5} ${s.entry_price:<7.4f} ${s.settlement_price:<7.4f} {pnl_str:<12}")
        
        total_pnl += s.pnl_usd or 0
        if s.outcome == "win":
            wins += 1
        else:
            losses += 1
    
    print("-" * 60)
    total_trades = wins + losses
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    print(f"Total P&L: ${total_pnl:+.2f} | Win Rate: {win_rate:.1f}% ({wins}W/{losses}L)")
    print()


def cmd_server(args):
    """Start the API server."""
    print("\n🚀 Starting Polybonds API Server...\n")
    
    settings, db = setup_environment()
    
    import uvicorn
    
    host = args.host if hasattr(args, 'host') else settings.api_host
    port = args.port if hasattr(args, 'port') else settings.api_port
    
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    print(f"   Docs: http://{host}:{port}/docs")
    print()
    
    uvicorn.run(
        "backend.api:app",
        host=host,
        port=port,
        reload=True
    )


def cmd_check(args):
    """Check configuration and connection."""
    print("\n🔧 Checking Polybonds configuration...\n")
    
    try:
        settings, db = setup_environment()
        print("✅ Environment loaded")
        print(f"   Chain ID: {settings.polymarket_chain_id}")
        print(f"   Min probability: {settings.min_probability:.0%}")
        print(f"   Max position: ${settings.max_position_size_usd}")
        print(f"   Auto-trading: {'Enabled' if settings.auto_trading_enabled else 'Disabled'}")
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return
    
    # Check database
    try:
        positions = db.get_open_positions()
        print(f"✅ Database connected ({len(positions)} open positions)")
    except Exception as e:
        print(f"❌ Database error: {e}")
    
    # Check API connection
    try:
        from backend.polymarket_client import get_client
        client = get_client(settings)
        client.initialize(read_only=True)
        
        markets = client.get_all_markets()
        print(f"✅ Polymarket API connected ({len(markets)} markets)")
    except Exception as e:
        print(f"❌ API connection error: {e}")
    
    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="🔒 Polybonds Trading System - Automated 98%+ probability market trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py scan              Scan for opportunities
  python run.py scan --limit 50   Show top 50 opportunities
  python run.py trade             Execute trades on top opportunities
  python run.py positions         View current positions
  python run.py server            Start web dashboard API
  python run.py check             Check configuration
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan for Polybond opportunities")
    scan_parser.add_argument("--limit", type=int, default=20, help="Max opportunities to display")
    
    # Trade command
    trade_parser = subparsers.add_parser("trade", help="Scan and execute trades")
    trade_parser.add_argument("--max-trades", type=int, default=5, help="Max trades to execute")
    trade_parser.add_argument("--portfolio", type=float, default=10000, help="Portfolio value for sizing")
    
    # Positions command
    positions_parser = subparsers.add_parser("positions", help="View open positions")
    
    # History command
    history_parser = subparsers.add_parser("history", help="View trade history")
    history_parser.add_argument("--limit", type=int, default=20, help="Max trades to display")
    
    # Settlements command
    settlements_parser = subparsers.add_parser("settlements", help="View settlement history")
    settlements_parser.add_argument("--limit", type=int, default=20, help="Max settlements to display")
    
    # Server command
    server_parser = subparsers.add_parser("server", help="Start API server")
    server_parser.add_argument("--host", type=str, default="0.0.0.0", help="Server host")
    server_parser.add_argument("--port", type=int, default=8000, help="Server port")
    
    # Check command
    check_parser = subparsers.add_parser("check", help="Check configuration")
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    
    # Route to command handler
    commands = {
        "scan": cmd_scan,
        "trade": cmd_trade,
        "positions": cmd_positions,
        "history": cmd_history,
        "settlements": cmd_settlements,
        "server": cmd_server,
        "check": cmd_check,
    }
    
    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
