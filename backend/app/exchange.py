from datetime import timezone, timedelta
from decimal import Decimal

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ExchangeRate, utcnow


SEEDED_RATES = {
    "USD": Decimal("1"),
    "EUR": Decimal("0.92"),
    "GBP": Decimal("0.79"),
    "INR": Decimal("83.10"),
    "JPY": Decimal("156.40"),
}


class ExchangeService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def seed_rates(self) -> None:
        now = utcnow()
        for currency in self.settings.supported_currencies:
            rate = SEEDED_RATES.get(currency)
            if rate is None:
                continue
            existing = self._find_rate(self.settings.base_currency, currency)
            if existing:
                continue
            self.db.add(
                ExchangeRate(
                    base_currency=self.settings.base_currency,
                    quote_currency=currency,
                    rate=rate,
                    provider="seed",
                    fetched_at=now,
                )
            )
        self.db.commit()

    async def refresh(self) -> list[ExchangeRate]:
        params = {"base": self.settings.base_currency, "symbols": ",".join(self.settings.supported_currencies)}
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(self.settings.exchange_provider_url, params=params)
            response.raise_for_status()
            payload = response.json()

        rates = payload.get("rates")
        if not isinstance(rates, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Exchange provider returned invalid data")

        now = utcnow()
        saved = []
        for currency in self.settings.supported_currencies:
            raw_rate = rates.get(currency)
            if raw_rate is None:
                continue
            rate = self._find_rate(self.settings.base_currency, currency, provider="provider")
            if rate is None:
                rate = ExchangeRate(
                    base_currency=self.settings.base_currency,
                    quote_currency=currency,
                    provider="provider",
                )
                self.db.add(rate)
            rate.rate = Decimal(str(raw_rate))
            rate.fetched_at = now
            saved.append(rate)
        self.db.commit()
        return saved

    def conversion_rate(self, source_currency: str, target_currency: str) -> tuple[Decimal, ExchangeRate | None]:
        if source_currency == target_currency:
            return Decimal("1"), None

        source = self.latest_rate(source_currency)
        target = self.latest_rate(target_currency)
        rate = Decimal(str(target.rate)) / Decimal(str(source.rate))
        return rate, target

    def latest_rate(self, quote_currency: str) -> ExchangeRate:
        rate = (
            self.db.execute(
                select(ExchangeRate)
                .where(ExchangeRate.base_currency == self.settings.base_currency)
                .where(ExchangeRate.quote_currency == quote_currency)
                .order_by(ExchangeRate.provider.desc(), ExchangeRate.fetched_at.desc())
            )
            .scalars()
            .first()
        )
        if rate is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"No exchange rate for {quote_currency}")
        max_age = timedelta(minutes=self.settings.exchange_rate_max_age_minutes)
        fetched_at = rate.fetched_at
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        if utcnow() - fetched_at > max_age:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Exchange rates are stale")
        return rate

    def _find_rate(self, base_currency: str, quote_currency: str, provider: str = "seed") -> ExchangeRate | None:
        return (
            self.db.execute(
                select(ExchangeRate)
                .where(ExchangeRate.base_currency == base_currency)
                .where(ExchangeRate.quote_currency == quote_currency)
                .where(ExchangeRate.provider == provider)
            )
            .scalars()
            .first()
        )
