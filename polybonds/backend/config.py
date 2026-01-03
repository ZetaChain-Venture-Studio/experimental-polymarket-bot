"""
Configuration management using Pydantic Settings.
Loads from environment variables and .env file.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # ===========================================
    # POLYMARKET API CREDENTIALS
    # ===========================================
    polymarket_private_key: str = Field(
        ...,
        description="Private key for Polymarket wallet (without 0x prefix)"
    )
    polymarket_funder_address: str = Field(
        ...,
        description="Wallet address that holds funds on Polymarket"
    )
    polymarket_chain_id: int = Field(
        default=137,
        description="Polygon chain ID"
    )
    polymarket_signature_type: int = Field(
        default=0,
        description="0=EOA, 1=Magic/Email, 2=Gnosis Safe"
    )
    
    # ===========================================
    # STRATEGY PARAMETERS
    # ===========================================
    min_probability: float = Field(
        default=0.98,
        ge=0.50,
        le=0.999,
        description="Minimum probability to consider (0.98 = 98%)"
    )
    max_probability: float = Field(
        default=0.9999,
        ge=0.50,
        le=1.0,
        description="Maximum probability (avoid already-settled markets)"
    )
    min_volume_24h: float = Field(
        default=5000,
        ge=0,
        description="Minimum 24h trading volume in USD"
    )
    max_position_size_usd: float = Field(
        default=100,
        ge=1,
        description="Maximum USD to invest per market"
    )
    max_portfolio_allocation_pct: float = Field(
        default=0.05,
        ge=0.01,
        le=0.5,
        description="Maximum % of portfolio per market (0.05 = 5%)"
    )
    stop_loss_threshold: float = Field(
        default=0.93,
        ge=0.5,
        le=0.99,
        description="Exit if price drops below this"
    )
    min_days_to_resolution: int = Field(
        default=0,
        ge=0,
        description="Minimum days until market resolution (0 = today)"
    )
    max_days_to_resolution: int = Field(
        default=30,
        ge=1,
        description="Maximum days until market resolution"
    )
    
    # ===========================================
    # AUTOMATION
    # ===========================================
    auto_trading_enabled: bool = Field(
        default=False,
        description="Enable automated trading"
    )
    scan_interval_minutes: int = Field(
        default=5,
        ge=1,
        description="How often to scan for opportunities"
    )
    
    # ===========================================
    # DATABASE
    # ===========================================
    database_url: str = Field(
        default="sqlite:///polybonds.db",
        description="Database connection string"
    )
    
    # ===========================================
    # API SERVER
    # ===========================================
    api_host: str = Field(
        default="0.0.0.0",
        description="API server host"
    )
    api_port: int = Field(
        default=8000,
        description="API server port"
    )
    
    # ===========================================
    # OPTIONAL: NOTIFICATIONS
    # ===========================================
    telegram_bot_token: Optional[str] = Field(
        default=None,
        description="Telegram bot token for notifications"
    )
    telegram_chat_id: Optional[str] = Field(
        default=None,
        description="Telegram chat ID for notifications"
    )
    discord_webhook_url: Optional[str] = Field(
        default=None,
        description="Discord webhook URL for notifications"
    )
    
    # ===========================================
    # POLYMARKET API ENDPOINTS (Constants)
    # ===========================================
    @property
    def clob_api_url(self) -> str:
        return "https://clob.polymarket.com"
    
    @property
    def gamma_api_url(self) -> str:
        return "https://gamma-api.polymarket.com"
    
    # ===========================================
    # CONTRACT ADDRESSES (Polygon Mainnet)
    # ===========================================
    @property
    def usdc_address(self) -> str:
        return "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    
    @property
    def ctf_exchange_address(self) -> str:
        return "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
    
    @property
    def neg_risk_exchange_address(self) -> str:
        return "0xC5d563A36AE78145C45a50134d48A1215220f80a"
    
    @property
    def neg_risk_adapter_address(self) -> str:
        return "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
    
    @property
    def ctf_address(self) -> str:
        return "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Uses lru_cache to avoid re-reading env file on every call.
    """
    return Settings()


# Convenience function for quick access
settings = get_settings()
