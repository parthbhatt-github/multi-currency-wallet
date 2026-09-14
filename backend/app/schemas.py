from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, HttpUrl


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    default_currency: str = Field(min_length=3, max_length=3)
    photo_url: HttpUrl | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    default_currency: str
    photo_url: str | None


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    photo_url: HttpUrl | None = None


class WalletResponse(BaseModel):
    id: str
    currency: str
    balance: Decimal
    balance_minor: int


class MoneyRequest(BaseModel):
    currency: str = Field(min_length=3, max_length=3)
    amount: Decimal = Field(gt=0, decimal_places=2)
    description: str | None = Field(default=None, max_length=500)


class TransferRequest(BaseModel):
    recipient_email: EmailStr
    source_currency: str = Field(min_length=3, max_length=3)
    target_currency: str = Field(min_length=3, max_length=3)
    amount: Decimal = Field(gt=0, decimal_places=2)
    description: str | None = Field(default=None, max_length=500)


class TransactionResponse(BaseModel):
    id: str
    type: str
    currency: str
    amount: Decimal
    amount_minor: int
    balance_after: Decimal
    description: str | None
    transfer_id: str | None
    source_currency: str | None
    source_amount_minor: int | None
    target_currency: str | None
    target_amount_minor: int | None
    rate_used: Decimal | None
    exchange_rate_id: str | None
    created_at: datetime


class PaginatedTransactions(BaseModel):
    items: list[TransactionResponse]
    total: int
    limit: int
    offset: int


class ExchangeRateResponse(BaseModel):
    id: str
    base_currency: str
    quote_currency: str
    rate: Decimal
    provider: str
    fetched_at: datetime


class HealthResponse(BaseModel):
    status: str
