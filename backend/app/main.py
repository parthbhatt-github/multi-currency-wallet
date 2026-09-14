from decimal import Decimal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, engine, get_db
from app.dependencies import current_user, idempotency_key, optional_current_user
from app.exchange import ExchangeService
from app.logging_config import RequestLoggingMiddleware
from app.models import ExchangeRate, Transaction, User
from app.money import from_minor
from app.schemas import (
    AuthResponse,
    ExchangeRateResponse,
    HealthResponse,
    LoginRequest,
    MoneyRequest,
    PaginatedTransactions,
    ProfileResponse,
    ProfileUpdate,
    SignupRequest,
    TransactionResponse,
    TransferRequest,
    WalletResponse,
)
from app.services import AuthService, TransactionService, WalletService, ensure_supported, idempotent


settings = get_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        ExchangeService(db).seed_rates()
    finally:
        db.close()


def profile_response(user: User) -> ProfileResponse:
    return ProfileResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        default_currency=user.default_currency,
        photo_url=user.photo_url,
    )


def transaction_response(tx: Transaction) -> TransactionResponse:
    return TransactionResponse(
        id=tx.id,
        type=tx.type.value,
        currency=tx.currency,
        amount=from_minor(tx.amount_minor, tx.currency),
        amount_minor=tx.amount_minor,
        balance_after=from_minor(tx.balance_after_minor, tx.currency),
        description=tx.description,
        transfer_id=tx.transfer_id,
        source_currency=tx.source_currency,
        source_amount_minor=tx.source_amount_minor,
        target_currency=tx.target_currency,
        target_amount_minor=tx.target_amount_minor,
        rate_used=Decimal(str(tx.rate_used)) if tx.rate_used is not None else None,
        exchange_rate_id=tx.exchange_rate_id,
        created_at=tx.created_at,
    )


def exchange_response(rate: ExchangeRate) -> ExchangeRateResponse:
    return ExchangeRateResponse(
        id=rate.id,
        base_currency=rate.base_currency,
        quote_currency=rate.quote_currency,
        rate=Decimal(str(rate.rate)),
        provider=rate.provider,
        fetched_at=rate.fetched_at,
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/ready", response_model=HealthResponse)
def ready(db: Session = Depends(get_db)) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ready")


@app.post("/auth/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> AuthResponse:
    token = AuthService(db).signup(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        default_currency=payload.default_currency,
        photo_url=str(payload.photo_url) if payload.photo_url else None,
    )
    return AuthResponse(access_token=token)


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    return AuthResponse(access_token=AuthService(db).login(payload.email, payload.password))


@app.get("/me", response_model=ProfileResponse)
def me(user: User = Depends(current_user)) -> ProfileResponse:
    return profile_response(user)


@app.patch("/me", response_model=ProfileResponse)
def update_me(payload: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> ProfileResponse:
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.default_currency is not None:
        user.default_currency = ensure_supported(payload.default_currency)
    if payload.photo_url is not None:
        user.photo_url = str(payload.photo_url)
    db.commit()
    return profile_response(user)


@app.get("/wallets", response_model=list[WalletResponse])
def wallets(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[WalletResponse]:
    return [
        WalletResponse(
            id=wallet.id,
            currency=wallet.currency,
            balance=from_minor(wallet.balance_minor, wallet.currency),
            balance_minor=wallet.balance_minor,
        )
        for wallet in WalletService(db).list_wallets(user.id)
    ]


@app.post("/wallets/credit", response_model=TransactionResponse)
def credit(
    payload: MoneyRequest,
    response: Response,
    user: User = Depends(current_user),
    key: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
):
    def handler():
        tx = WalletService(db).credit(user, payload)
        return transaction_response(tx).model_dump(mode="json"), status.HTTP_201_CREATED

    body, code = idempotent(db, user, key, handler)
    response.status_code = code
    return body


@app.post("/wallets/debit", response_model=TransactionResponse)
def debit(
    payload: MoneyRequest,
    response: Response,
    user: User = Depends(current_user),
    key: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
):
    def handler():
        tx = WalletService(db).debit(user, payload)
        return transaction_response(tx).model_dump(mode="json"), status.HTTP_201_CREATED

    body, code = idempotent(db, user, key, handler)
    response.status_code = code
    return body


@app.post("/transfers", response_model=list[TransactionResponse], status_code=status.HTTP_201_CREATED)
def transfer(
    payload: TransferRequest,
    response: Response,
    user: User = Depends(current_user),
    key: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
):
    def handler():
        debit_tx, credit_tx = WalletService(db).transfer(user, payload)
        return [transaction_response(debit_tx).model_dump(mode="json"), transaction_response(credit_tx).model_dump(mode="json")], status.HTTP_201_CREATED

    body, code = idempotent(db, user, key, handler)
    response.status_code = code
    return body


@app.get("/transactions", response_model=PaginatedTransactions)
def transactions(
    currency: str | None = None,
    type: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PaginatedTransactions:
    items, total = TransactionService(db).list_transactions(user.id, currency, type, limit, offset)
    return PaginatedTransactions(
        items=[transaction_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


def authorize_exchange_refresh(
    refresh_token: str | None = Header(default=None, alias="X-Exchange-Refresh-Token"),
    user: User | None = Depends(optional_current_user),
) -> None:
    configured_token = get_settings().exchange_refresh_token
    if configured_token and refresh_token == configured_token:
        return
    if user and user.email.split("@")[0] == "admin":
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


@app.post("/exchange-rates/refresh", response_model=list[ExchangeRateResponse])
async def refresh_exchange_rates(
    db: Session = Depends(get_db),
    _: None = Depends(authorize_exchange_refresh),
) -> list[ExchangeRateResponse]:
    rates = await ExchangeService(db).refresh()
    return [exchange_response(rate) for rate in rates]
