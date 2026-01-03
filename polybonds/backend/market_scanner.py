"""
Market Scanner Module.
Identifies eligible "Polybond" opportunities from Polymarket.

A Polybond is a position in a market with 98%+ probability that hasn't
settled yet - essentially a short-term "bond" that pays out at $1.00.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import logging

from .config import Settings, get_settings
from .polymarket_client import PolymarketClient, get_client
from .database import DatabaseManager, get_db

logger = logging.getLogger(__name__)


@dataclass
class PolybondOpportunity:
    """Represents a Polybond trading opportunity."""

    # Market identification
    market_id: str
    question: str
    token_id: str
    side: str  # 'YES' or 'NO' - which side is the "bond"

    # Pricing
    current_price: float
    implied_probability: float  # Same as price for prediction markets

    # Returns
    potential_return_pct: float  # (1.0 - price) / price * 100
    annualized_return_pct: float  # Potential return annualized

    # Market data
    volume_24h: float
    liquidity: float

    # Timing
    end_date: Optional[datetime]
    days_to_resolution: float

    # Risk assessment (must come before fields with defaults)
    risk_score: float  # 0-100, lower is safer

    # Resolution info (fields with defaults)
    resolution_source: str = ""
    resolution_rules: str = ""
    estimated_resolution_hours: float = 24.0  # Hours after end_date
    estimated_payout_date: Optional[datetime] = None  # When you'll get paid
    risk_factors: List[str] = field(default_factory=list)

    # Metadata
    category: str = ""
    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MarketScanner:
    """
    Scans Polymarket for Polybond opportunities.
    
    Eligibility Criteria:
    1. Probability >= MIN_PROBABILITY (default 98%)
    2. Probability <= MAX_PROBABILITY (default 99.5%)
    3. 24h Volume >= MIN_VOLUME_24H
    4. Days until resolution between MIN and MAX
    5. Market is active
    6. Not already at max allocation
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
        
    def scan_all_markets(self) -> List[PolybondOpportunity]:
        """
        Scan all Polymarket markets for Polybond opportunities.
        
        Returns:
            List of PolybondOpportunity objects sorted by annualized return
        """
        logger.info("Starting market scan...")
        opportunities = []
        
        # Initialize client if needed (read-only mode)
        if not self.client._clob_client:
            self.client.initialize(read_only=True)
        
        # Fetch all active markets
        markets = self.client.get_all_markets()
        logger.info(f"Fetched {len(markets)} markets from Polymarket")
        
        for market in markets:
            try:
                opportunity = self._evaluate_market(market)
                if opportunity:
                    opportunities.append(opportunity)
                    
                    # Update database
                    self._save_market_to_db(market, eligible=True)
                else:
                    # Save as ineligible
                    self._save_market_to_db(market, eligible=False)
                    
            except Exception as e:
                logger.debug(f"Error evaluating market: {e}")
                continue
        
        # Sort by annualized return (best opportunities first)
        opportunities.sort(key=lambda x: x.annualized_return_pct, reverse=True)
        
        logger.info(f"Found {len(opportunities)} Polybond opportunities")
        
        # Log activity
        self.db.log_activity(
            level="INFO",
            module="market_scanner",
            message=f"Scan complete: {len(opportunities)} opportunities from {len(markets)} markets",
            details={"total_markets": len(markets), "opportunities": len(opportunities)}
        )
        
        return opportunities
    
    def _evaluate_market(self, market_data: Dict[str, Any]) -> Optional[PolybondOpportunity]:
        """
        Evaluate if a market qualifies as a Polybond opportunity.
        
        Args:
            market_data: Raw market data from API
            
        Returns:
            PolybondOpportunity if eligible, None otherwise
        """
        # Parse market info
        market = self.client.parse_market_info(market_data)
        if not market:
            return None
        
        # Skip inactive markets
        if not market.active:
            return None
        
        # Use API prices from Gamma API (CLOB price fetching is too slow/unreliable)
        price_yes = market.price_yes
        price_no = market.price_no

        # Skip if no valid prices
        if (price_yes is None or price_yes == 0) and (price_no is None or price_no == 0):
            return None
        
        # Determine which side is the "bond" (high probability side)
        bond_side = None
        bond_price = 0
        token_id = ""

        # Debug: log high probability markets
        max_price = max(price_yes or 0, price_no or 0)
        if max_price >= 0.80:
            logger.info(f"High prob market: {market.question[:50]}... YES={price_yes} NO={price_no}")

        if price_yes and price_yes >= self.settings.min_probability:
            bond_side = "YES"
            bond_price = price_yes
            token_id = market.token_id_yes
        elif price_no and price_no >= self.settings.min_probability:
            bond_side = "NO"
            bond_price = price_no
            token_id = market.token_id_no
        else:
            return None  # Neither side meets minimum probability
        
        # Check maximum probability (avoid already-settling markets)
        if bond_price > self.settings.max_probability:
            return None
        
        # Check volume requirement
        if market.volume_24h < self.settings.min_volume_24h:
            return None
        
        # Check time to resolution
        if market.end_date is None:
            return None
            
        now = datetime.now(timezone.utc)
        if market.end_date.tzinfo is None:
            market.end_date = market.end_date.replace(tzinfo=timezone.utc)
            
        time_to_resolution = market.end_date - now
        days_to_resolution = time_to_resolution.total_seconds() / 86400

        # Allow markets that ended up to 3 days ago (pending settlement)
        if days_to_resolution < -3:
            return None
        if days_to_resolution > self.settings.max_days_to_resolution:
            return None
        
        # Calculate returns
        potential_return_pct = ((1.0 - bond_price) / bond_price) * 100
        annualized_return_pct = (potential_return_pct / max(days_to_resolution, 0.1)) * 365

        # Get resolution info
        resolution_source = market.resolution_source
        resolution_rules = market.resolution_rules
        estimated_resolution_hours = market.estimated_resolution_hours or 24.0

        # Calculate estimated payout date (end_date + resolution time + 2h challenge period)
        estimated_payout_date = None
        if market.end_date:
            from datetime import timedelta
            # Resolution time + 2 hour challenge period minimum
            total_hours = estimated_resolution_hours + 2.0
            estimated_payout_date = market.end_date + timedelta(hours=total_hours)

        # Calculate risk score (now includes resolution factors)
        risk_score, risk_factors = self._calculate_risk_score(
            market_data, bond_price, days_to_resolution, market.volume_24h,
            resolution_source, estimated_resolution_hours
        )

        return PolybondOpportunity(
            market_id=market.id,
            question=market.question,
            token_id=token_id,
            side=bond_side,
            current_price=bond_price,
            implied_probability=bond_price,
            potential_return_pct=round(potential_return_pct, 4),
            annualized_return_pct=round(annualized_return_pct, 2),
            volume_24h=market.volume_24h,
            liquidity=market.liquidity,
            end_date=market.end_date,
            days_to_resolution=round(days_to_resolution, 2),
            resolution_source=resolution_source,
            resolution_rules=resolution_rules,
            estimated_resolution_hours=estimated_resolution_hours,
            estimated_payout_date=estimated_payout_date,
            risk_score=round(risk_score, 1),
            risk_factors=risk_factors,
            category=market.category
        )
    
    def _calculate_risk_score(
        self,
        market_data: Dict[str, Any],
        price: float,
        days_to_resolution: float,
        volume: float,
        resolution_source: str = "",
        estimated_resolution_hours: float = 24.0
    ) -> tuple[float, List[str]]:
        """
        Calculate risk score (0-100, lower is safer).

        Factors:
        1. Probability (lower = higher risk) - 0-25 points
        2. Volume (lower = higher risk) - 0-15 points
        3. Time to resolution (longer = higher risk) - 0-20 points
        4. Category risk - 0-15 points
        5. Resolution source reliability - 0-15 points
        6. Resolution time uncertainty - 0-10 points

        Returns:
            Tuple of (risk_score, list_of_risk_factors)
        """
        score = 0
        factors = []

        # 1. Probability factor (0-25 points)
        # 98% = 25 points, 99% = 12.5 points, 99.5% = 6.25 points
        prob_risk = (1 - price) * 1250
        score += prob_risk
        if price < 0.985:
            factors.append(f"Lower probability ({price:.1%})")

        # 2. Volume factor (0-15 points)
        if volume < 10000:
            score += 15
            factors.append(f"Low volume (${volume:,.0f})")
        elif volume < 25000:
            score += 12
            factors.append(f"Medium-low volume (${volume:,.0f})")
        elif volume < 50000:
            score += 8
        elif volume < 100000:
            score += 4
        # > $100k volume = 0 points

        # 3. Time factor (0-20 points)
        if days_to_resolution > 21:
            score += 20
            factors.append(f"Long time to resolution ({days_to_resolution:.0f} days)")
        elif days_to_resolution > 14:
            score += 16
            factors.append(f"Extended resolution time ({days_to_resolution:.0f} days)")
        elif days_to_resolution > 7:
            score += 10
        elif days_to_resolution > 3:
            score += 5
        elif days_to_resolution > 1:
            score += 2
        # < 1 day = 0 points (closest to payout)

        # 4. Category factor (0-15 points)
        category = market_data.get("category", "").lower()

        # Higher risk categories (more prone to reversals)
        high_risk_categories = ["politics", "elections", "sports", "entertainment"]
        medium_risk_categories = ["business", "science", "technology"]
        low_risk_categories = ["crypto", "finance", "weather", "economy"]

        if any(cat in category for cat in high_risk_categories):
            score += 15
            factors.append(f"Higher-risk category ({category})")
        elif any(cat in category for cat in medium_risk_categories):
            score += 9
        elif any(cat in category for cat in low_risk_categories):
            score += 3
        else:
            score += 7  # Unknown category

        # 5. Resolution source reliability (0-15 points)
        source_lower = resolution_source.lower() if resolution_source else ""

        # Most reliable sources (automated, official)
        if "uma" in source_lower:
            score += 0  # UMA is automated and reliable
        elif any(s in source_lower for s in ["ap", "reuters", "associated press", "bloomberg"]):
            score += 3  # Major news agencies are reliable
        elif any(s in source_lower for s in ["coingecko", "coinmarketcap", "chainlink"]):
            score += 2  # Crypto data feeds are reliable
        elif any(s in source_lower for s in ["espn", "nfl", "nba", "official"]):
            score += 5  # Sports official sources
        elif resolution_source:
            score += 8  # Unknown source
            factors.append(f"Unknown resolution source ({resolution_source[:30]})")
        else:
            score += 15  # No resolution source specified
            factors.append("No resolution source specified")

        # 6. Resolution time uncertainty (0-10 points)
        if estimated_resolution_hours <= 2:
            score += 0  # Fast resolution
        elif estimated_resolution_hours <= 6:
            score += 2
        elif estimated_resolution_hours <= 24:
            score += 5
        elif estimated_resolution_hours <= 48:
            score += 8
            factors.append(f"Slow resolution (~{estimated_resolution_hours:.0f}h)")
        else:
            score += 10
            factors.append(f"Very slow resolution (~{estimated_resolution_hours:.0f}h)")

        return min(score, 100), factors
    
    def _save_market_to_db(self, market_data: Dict[str, Any], eligible: bool):
        """Save market data to database."""
        try:
            market_info = self.client.parse_market_info(market_data)
            if not market_info:
                return
                
            self.db.upsert_market({
                "id": market_info.id,
                "question": market_info.question,
                "description": market_info.description,
                "token_id_yes": market_info.token_id_yes,
                "token_id_no": market_info.token_id_no,
                "end_date": market_info.end_date,
                "category": market_info.category,
                "current_price_yes": market_info.price_yes,
                "current_price_no": market_info.price_no,
                "volume_24h": market_info.volume_24h,
                "last_scanned": datetime.now(timezone.utc),
                "is_eligible": eligible
            })
        except Exception as e:
            logger.debug(f"Failed to save market to DB: {e}")
    
    def get_opportunity(self, market_id: str) -> Optional[PolybondOpportunity]:
        """
        Get a specific opportunity by market ID.
        
        Args:
            market_id: The market's condition ID
            
        Returns:
            PolybondOpportunity if eligible, None otherwise
        """
        market_data = self.client.get_market(market_id)
        if not market_data:
            return None
        return self._evaluate_market(market_data)
    
    def get_summary(self, opportunities: List[PolybondOpportunity]) -> Dict[str, Any]:
        """
        Get summary statistics for a list of opportunities.
        
        Args:
            opportunities: List of PolybondOpportunity objects
            
        Returns:
            Dictionary with summary statistics
        """
        if not opportunities:
            return {
                "total": 0,
                "avg_return": 0,
                "avg_annualized": 0,
                "avg_risk": 0,
                "total_volume": 0,
                "by_category": {}
            }
        
        # Calculate statistics
        total = len(opportunities)
        avg_return = sum(o.potential_return_pct for o in opportunities) / total
        avg_annualized = sum(o.annualized_return_pct for o in opportunities) / total
        avg_risk = sum(o.risk_score for o in opportunities) / total
        total_volume = sum(o.volume_24h for o in opportunities)
        
        # Group by category
        by_category = {}
        for opp in opportunities:
            cat = opp.category or "Unknown"
            if cat not in by_category:
                by_category[cat] = 0
            by_category[cat] += 1
        
        return {
            "total": total,
            "avg_return_pct": round(avg_return, 2),
            "avg_annualized_pct": round(avg_annualized, 2),
            "avg_risk_score": round(avg_risk, 1),
            "total_volume_24h": round(total_volume, 2),
            "by_category": by_category
        }


# ===========================================
# CONVENIENCE FUNCTIONS
# ===========================================

def scan_markets(settings: Settings = None) -> List[PolybondOpportunity]:
    """
    Convenience function to scan markets.
    
    Args:
        settings: Optional settings override
        
    Returns:
        List of Polybond opportunities
    """
    scanner = MarketScanner(settings=settings)
    return scanner.scan_all_markets()


def print_opportunities(opportunities: List[PolybondOpportunity], limit: int = 20):
    """
    Pretty print opportunities to console.
    
    Args:
        opportunities: List of opportunities
        limit: Maximum number to display
    """
    print("\n" + "=" * 80)
    print("🔒 POLYBOND OPPORTUNITIES")
    print("=" * 80)
    
    if not opportunities:
        print("\nNo opportunities found matching criteria.\n")
        return
    
    for i, opp in enumerate(opportunities[:limit], 1):
        print(f"\n{i}. {opp.question[:70]}...")
        print(f"   Side: {opp.side} @ ${opp.current_price:.4f}")
        print(f"   Return: {opp.potential_return_pct:.2f}% ({opp.annualized_return_pct:.0f}% APY)")
        print(f"   Days to resolution: {opp.days_to_resolution:.1f}")
        print(f"   Risk score: {opp.risk_score}/100")
        print(f"   24h Volume: ${opp.volume_24h:,.0f}")
        if opp.risk_factors:
            print(f"   ⚠️  Factors: {', '.join(opp.risk_factors)}")
    
    if len(opportunities) > limit:
        print(f"\n... and {len(opportunities) - limit} more opportunities")
    
    print("\n" + "=" * 80)
