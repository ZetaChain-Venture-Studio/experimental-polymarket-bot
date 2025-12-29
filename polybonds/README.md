# 🔒 Polybonds Trading System

Automated trading system for Polymarket "Polybonds" - positions in 98%+ probability markets that haven't settled yet.

## 🎯 Strategy

Polybonds are the prediction market equivalent of short-term bonds:

- **Buy YES at $0.98** → Settlement at $1.00 = **2.04% return**
- **Buy YES at $0.99** → Settlement at $1.00 = **1.01% return**
- If settlement happens in 3 days = **Annualized 100-250%+ APY**

### Risk
Occasionally (~1-2% of trades), a "done deal" reverses due to unexpected events, oracle disputes, or market manipulation.

## 🚀 Quick Start

### 1. Clone and Setup

```bash
# Clone the repo
git clone <your-repo-url>
cd polybonds

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit .env with your credentials
nano .env
```

**Required settings:**
- `POLYMARKET_PRIVATE_KEY` - Export from Polymarket.com → Cash → ⋮ → Export Private Key
- `POLYMARKET_FUNDER_ADDRESS` - Your Polymarket wallet address

### 3. Run Commands

```bash
# Check configuration
python run.py check

# Scan for opportunities
python run.py scan

# View open positions
python run.py positions

# Execute trades (simulation mode by default)
python run.py trade

# Start web API
python run.py server
```

## 📁 Project Structure

```
polybonds/
├── backend/
│   ├── config.py           # Environment configuration
│   ├── database.py         # SQLAlchemy models
│   ├── polymarket_client.py # API wrapper
│   ├── market_scanner.py   # Opportunity finder
│   ├── trade_executor.py   # Order execution
│   └── api.py              # FastAPI server
├── frontend/               # React dashboard (coming soon)
├── .env.example            # Example configuration
├── requirements.txt        # Python dependencies
├── run.py                  # CLI entry point
└── README.md
```

## ⚙️ Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `MIN_PROBABILITY` | 0.98 | Minimum probability (98%) |
| `MAX_PROBABILITY` | 0.995 | Maximum probability (99.5%) |
| `MIN_VOLUME_24H` | 5000 | Minimum 24h volume ($) |
| `MAX_POSITION_SIZE_USD` | 100 | Max per-market position |
| `MAX_PORTFOLIO_ALLOCATION_PCT` | 0.05 | Max 5% per market |
| `STOP_LOSS_THRESHOLD` | 0.93 | Exit if price drops to 93% |
| `AUTO_TRADING_ENABLED` | false | Enable live trading |

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/opportunities` | GET | Current opportunities |
| `/api/positions` | GET | Open positions |
| `/api/portfolio` | GET | Portfolio overview |
| `/api/trades` | GET | Trade history |
| `/api/settlements` | GET | Settlement history |
| `/api/scan` | POST | Trigger market scan |
| `/api/trade/{market_id}` | POST | Execute trade |

## ⚠️ Warnings

1. **Start with `AUTO_TRADING_ENABLED=false`** - Test scanning first
2. **Use small amounts initially** - Start with $50-100
3. **Never commit `.env` file** - Contains your private key
4. **Monitor daily** - Even "safe" markets can surprise you
5. **Check legal status** - Polymarket is restricted in some jurisdictions

## 📊 Dashboard

Start the API server and access the Swagger docs:

```bash
python run.py server
# Open http://localhost:8000/docs
```

## 🛠️ Development

```bash
# Run tests
pytest tests/

# Format code
black backend/

# Type checking
mypy backend/
```

## 📜 License

MIT License - Use at your own risk.

---

**Disclaimer**: This software is provided as-is. Trading prediction markets involves substantial risk. Past performance does not guarantee future results. Never trade more than you can afford to lose.
