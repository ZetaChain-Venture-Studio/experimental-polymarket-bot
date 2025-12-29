# 🚀 POLYBONDS CLAUDE CODE MEGA-PROMPT

**Copy this ENTIRE document and paste it as your first message in Claude Code, along with uploading the polybonds.zip file.**

---

## CONTEXT: What This Project Is

I'm building **Polybonds** - an automated trading bot for Polymarket prediction markets. The strategy is to buy positions in markets with 98%+ probability that haven't settled yet. These are like short-term bonds:

- Buy YES at $0.98 → Settles at $1.00 = 2.04% return
- Buy YES at $0.99 → Settles at $1.00 = 1.01% return
- If it settles in 3 days = 100-250% annualized APY

The risk is ~1-2% of trades fail due to unexpected reversals (black swan events).

---

## WHAT I'VE UPLOADED: polybonds.zip

I've uploaded a zip file containing the complete backend system. Please unzip it first:

```bash
unzip polybonds.zip
cd polybonds
```

### Project Structure After Unzipping:

```
polybonds/
├── backend/
│   ├── __init__.py           # Package init
│   ├── config.py             # Pydantic settings management
│   ├── database.py           # SQLAlchemy models (6 tables)
│   ├── polymarket_client.py  # API wrapper for Polymarket
│   ├── market_scanner.py     # Core logic: finds 98%+ markets
│   ├── trade_executor.py     # Executes trades with risk management
│   └── api.py                # FastAPI REST endpoints (12 endpoints)
├── frontend/                 # EMPTY - needs React dashboard
├── tests/                    # EMPTY - needs tests
├── .env.example              # Configuration template
├── .gitignore               
├── requirements.txt          # Python deps
├── run.py                    # CLI with scan/trade/server commands
└── README.md
```

---

## IMMEDIATE FIRST STEPS

Run these commands to set up and test:

```bash
# 1. Unzip and enter directory
unzip polybonds.zip
cd polybonds

# 2. Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file
cp .env.example .env

# 5. Test the setup (will work without API credentials)
python run.py check

# 6. Scan for opportunities (read-only, no trading)
python run.py scan --limit 20

# 7. Start the API server
python run.py server
# Then open http://localhost:8000/docs for Swagger UI
```

---

## COMPLETE .env CONFIGURATION

```bash
# ===========================================
# POLYMARKET API CREDENTIALS
# ===========================================
# Get from: Polymarket.com → Cash → ⋮ → Export Private Key
POLYMARKET_PRIVATE_KEY=your_64_character_hex_private_key_without_0x
POLYMARKET_FUNDER_ADDRESS=0xYourPolygonWalletAddress
POLYMARKET_CHAIN_ID=137
POLYMARKET_SIGNATURE_TYPE=0

# ===========================================
# STRATEGY PARAMETERS
# ===========================================
MIN_PROBABILITY=0.98
MAX_PROBABILITY=0.995
MIN_VOLUME_24H=5000
MAX_POSITION_SIZE_USD=100
MAX_PORTFOLIO_ALLOCATION_PCT=0.05
STOP_LOSS_THRESHOLD=0.93
MIN_DAYS_TO_RESOLUTION=1
MAX_DAYS_TO_RESOLUTION=30

# ===========================================
# AUTOMATION
# ===========================================
AUTO_TRADING_ENABLED=false
SCAN_INTERVAL_MINUTES=5

# ===========================================
# DATABASE & API
# ===========================================
DATABASE_URL=sqlite:///polybonds.db
API_HOST=0.0.0.0
API_PORT=8000
```

---

## CLI COMMANDS AVAILABLE

```bash
python run.py scan              # Scan for Polybond opportunities
python run.py scan --limit 50   # Show top 50 opportunities
python run.py trade             # Execute trades (simulation mode)
python run.py trade --max-trades 10 --portfolio 5000
python run.py positions         # View open positions
python run.py history           # View trade history  
python run.py settlements       # View settlement history
python run.py server            # Start FastAPI server on :8000
python run.py check             # Check configuration
```

---

## API ENDPOINTS (FastAPI at localhost:8000)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/opportunities` | GET | Get 98%+ probability markets |
| `/api/opportunities?limit=50&min_return=1.5&max_risk=50` | GET | Filtered opportunities |
| `/api/positions` | GET | All open positions |
| `/api/portfolio` | GET | Portfolio overview stats |
| `/api/trades` | GET | Trade history |
| `/api/settlements` | GET | Settlement history |
| `/api/scan` | POST | Trigger manual scan |
| `/api/trade/{market_id}` | POST | Execute trade on market |
| `/api/close/{position_id}` | POST | Close a position |
| `/api/settings` | GET | Current settings |
| `/api/logs` | GET | Activity logs |

---

## DATABASE SCHEMA (SQLite)

### Table: markets
```sql
id TEXT PRIMARY KEY,
question TEXT,
description TEXT,
token_id_yes TEXT,
token_id_no TEXT,
end_date DATETIME,
category TEXT,
current_price_yes FLOAT,
current_price_no FLOAT,
volume_24h FLOAT,
last_scanned DATETIME,
is_eligible BOOLEAN,
eligibility_reason TEXT,
created_at DATETIME
```

### Table: trades
```sql
id INTEGER PRIMARY KEY,
market_id TEXT FK,
token_id TEXT,
side TEXT (YES/NO),
action TEXT (BUY/SELL),
price FLOAT,
quantity FLOAT,
total_usd FLOAT,
order_id TEXT,
status TEXT,
error_message TEXT,
created_at DATETIME,
filled_at DATETIME
```

### Table: positions
```sql
id INTEGER PRIMARY KEY,
market_id TEXT FK UNIQUE,
token_id TEXT,
side TEXT,
quantity FLOAT,
avg_entry_price FLOAT,
total_cost_usd FLOAT,
current_price FLOAT,
current_value_usd FLOAT,
unrealized_pnl FLOAT,
unrealized_pnl_pct FLOAT,
status TEXT,
opened_at DATETIME,
closed_at DATETIME,
settlement_price FLOAT,
realized_pnl FLOAT
```

### Table: portfolio_snapshots
```sql
id INTEGER PRIMARY KEY,
timestamp DATETIME,
total_value_usd FLOAT,
cash_balance_usd FLOAT,
positions_value_usd FLOAT,
total_realized_pnl FLOAT,
total_unrealized_pnl FLOAT,
open_positions_count INTEGER,
total_trades_count INTEGER,
winning_trades_count INTEGER,
losing_trades_count INTEGER,
win_rate FLOAT,
roi_pct FLOAT,
annualized_roi_pct FLOAT
```

### Table: settlements
```sql
id INTEGER PRIMARY KEY,
market_id TEXT FK,
position_id INTEGER FK,
question TEXT,
side TEXT,
entry_price FLOAT,
settlement_price FLOAT,
quantity FLOAT,
cost_usd FLOAT,
payout_usd FLOAT,
pnl_usd FLOAT,
pnl_pct FLOAT,
outcome TEXT (win/loss),
settled_at DATETIME
```

### Table: activity_log
```sql
id INTEGER PRIMARY KEY,
timestamp DATETIME,
level TEXT,
module TEXT,
message TEXT,
details TEXT (JSON)
```

---

## CORE ALGORITHM: Market Scanner

The scanner finds "Polybonds" using these criteria:

```python
# ELIGIBILITY RULES
1. YES or NO price >= 0.98 (98% probability)
2. YES or NO price <= 0.995 (not already settling at 99.9%)
3. 24h volume >= $5,000 (enough liquidity)
4. Days to resolution: 1-30 days
5. Market is active (not paused/resolved)
6. Under max portfolio allocation (5% per market)

# RETURN CALCULATION
potential_return_pct = ((1.0 - price) / price) * 100
# Example: price=0.98 → return = (0.02/0.98)*100 = 2.04%

annualized_return_pct = (potential_return_pct / days_to_resolution) * 365
# Example: 2.04% in 3 days = 248% APY

# RISK SCORE (0-100, lower = safer)
Probability factor (0-30 pts):
  - 98% = 30 points (riskier)
  - 99% = 15 points
  - 99.5% = 7.5 points (safer)

Volume factor (0-20 pts):
  - < $10k = 20 points (low liquidity risk)
  - $10-25k = 15 points
  - $25-50k = 10 points
  - $50-100k = 5 points
  - > $100k = 0 points

Time factor (0-30 pts):
  - > 21 days = 30 points (more time for reversal)
  - 14-21 days = 25 points
  - 7-14 days = 15 points
  - 3-7 days = 8 points
  - 1-3 days = 3 points
  - < 1 day = 0 points (imminent payout)

Category factor (0-20 pts):
  - Politics/Sports/Entertainment = 20 points (prone to upsets)
  - Business/Science/Tech = 12 points
  - Crypto/Finance/Economy = 5 points

# POSITION SIZING
base_size = min(MAX_POSITION_SIZE_USD, portfolio_value * MAX_ALLOCATION)
risk_multiplier = 1.0 - (risk_score / 200)  # 0.5 to 1.0
final_size = base_size * risk_multiplier
```

---

## POLYMARKET API DETAILS

### Endpoints
- **CLOB API**: `https://clob.polymarket.com` (order book, trading)
- **Gamma API**: `https://gamma-api.polymarket.com` (market data, events)

### Authentication Levels
- **Level 0**: No auth needed - read prices, markets, order books
- **Level 1**: Private key - derive API credentials
- **Level 2**: API key/secret/passphrase - place orders

### Rate Limits
- General: 5,000 requests / 10 seconds
- Orders: 24,000 / 10 minutes (40/second sustained)
- Market data: 200 / 10 seconds

### SDK
Using `py-clob-client` Python package (official Polymarket SDK)

### Smart Contracts (Polygon Mainnet)
- **USDC.e**: `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`
- **CTF Exchange**: `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E`
- **NegRisk Exchange**: `0xC5d563A36AE78145C45a50134d48A1215220f80a`
- **Conditional Tokens**: `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045`

---

## WHAT NEEDS TO BE BUILT NEXT

### Priority 1: React Frontend Dashboard
Build in `frontend/` folder with:
- React 18 + Vite
- Tailwind CSS for styling
- Fetch from FastAPI backend at :8000

**Components needed:**
```
frontend/
├── src/
│   ├── App.jsx
│   ├── components/
│   │   ├── Dashboard.jsx        # Main container
│   │   ├── PortfolioStats.jsx   # Stats cards at top
│   │   ├── ActivePositions.jsx  # Positions table
│   │   ├── Opportunities.jsx    # Polybond list with TRADE buttons
│   │   ├── TradeHistory.jsx     # Recent trades
│   │   └── SettlementLog.jsx    # Settlements with P&L
│   ├── hooks/
│   │   └── useApi.js            # API fetch hooks
│   └── index.css                # Tailwind imports
├── package.json
├── vite.config.js
└── tailwind.config.js
```

**Dashboard Layout:**
```
+------------------------------------------------------------------+
|  🔒 POLYBONDS                              [Auto: ON] [Settings] |
+------------------------------------------------------------------+
|  +------------+ +------------+ +------------+ +------------+     |
|  | 💰 Total   | | 💵 Cash    | | 📈 Positions| | 📊 ROI     |     |
|  | $10,250.00 | | $2,500.00  | | $7,750.00  | | +12.5%     |     |
|  +------------+ +------------+ +------------+ +------------+     |
+------------------------------------------------------------------+
|  ACTIVE POSITIONS (5)              |  POLYBOND OPPORTUNITIES     |
|  +---------------------------------+  +-------------------------+|
|  | Market | Side | Entry | P&L    |  | Question | Price | APY  ||
|  |--------|------|-------|--------|  |----------|-------|------||
|  | Will...|  YES | $0.98 | +$2.04 |  | Will X...|$0.983 | 185% ||
|  | Did... |  YES | $0.99 | +$0.50 |  | Is Y...  |$0.991 | 220% ||
|  | Has... |  NO  | $0.98 | +$1.80 |  | Has Z... |$0.978 | 156% ||
|  +---------------------------------+  | [TRADE $50] [TRADE $100]||
|                                       +-------------------------+|
+------------------------------------------------------------------+
|  RECENT TRADES                     |  SETTLEMENTS                |
|  +-----------------------------+   |  +------------------------+ |
|  | Time    | Action | Amount  |   |  | Market | Result | P&L  | |
|  |---------|--------|---------|   |  |--------|--------|------| |
|  | 2m ago  | BUY    | $100    |   |  | Did X  | ✅ WIN | +$2  | |
|  | 15m ago | BUY    | $50     |   |  | Was Y  | ✅ WIN | +$1  | |
|  +-----------------------------+   |  +------------------------+ |
+------------------------------------------------------------------+
```

### Priority 2: Automated Scheduling
Add to backend:
- APScheduler for periodic tasks
- Scan every 5 minutes
- Check stop-losses every 1 minute
- Monitor settlements every hour
- Portfolio snapshots every 10 minutes

### Priority 3: Notifications
- Telegram bot notifications
- Discord webhook notifications
- Alert on: new trades, stop-losses, settlements

### Priority 4: Push to GitHub
```bash
git init
git add -A
git commit -m "🚀 Polybonds trading system"
git branch -M main
git remote add origin https://github.com/nobtc4you/experimental-polymarket-bot.git
git push -u origin main --force
```

---

## IMPORTANT WARNINGS

1. **`AUTO_TRADING_ENABLED=false`** - Starts in simulation mode (safe)
2. **Never commit `.env`** - Contains your private key!
3. **Start with $50-100** - Test before scaling
4. **98% is not 100%** - Expect 1-2% of trades to fail
5. **Legal restrictions** - Polymarket blocked in US, UK, France, etc.

---

## GITHUB REPO

Push to: `https://github.com/nobtc4you/experimental-polymarket-bot`

---

## WHAT I WANT YOU TO DO NOW

1. **Unzip polybonds.zip** and explore the code
2. **Run `python run.py check`** to verify setup
3. **Run `python run.py scan`** to see it find opportunities
4. **Build the React frontend** in `frontend/`
5. **Push everything to GitHub**

Let's start by unzipping and testing the backend works, then build the dashboard!
