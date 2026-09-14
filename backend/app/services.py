import json
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.exchange import ExchangeService
from app.models import IdempotencyKey, Transaction, TransactionType, Transfer, User, Wallet
from app.money import convert_minor, from_minor, normalize_currency, to_minor
from app.schemas import MoneyRequest, TransferRequest
from app.security import create_access_token, hash_password, verify_password


def ensure_supported(currency: str) -> str:
    normalized = normalize_currency(currency)
    if normalized not in get_settings().supported_currencies:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unsupported currency {normalized}")
    return normalized


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def signup(self, email: str, password: str, full_name: str, default_currency: str, photo_url: str | None) -> str:
        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            full_name=full_name,
            default_currency=ensure_supported(default_currency),
            photo_url=photo_url,
        )
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered") from exc
        return create_access_token(user.id)

    def login(self, email: str, password: str) -> str:
        user = self.db.execute(select(User).where(User.email == email.lower())).scalars().first()
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        return create_access_token(user.id)


class WalletService:
    def __init__(self, db: Session):
        self.db = db
        self.exchange = ExchangeService(db)

    def wallet_for_update(self, user_id: str, currency: str) -> Wallet:
        wallet = (
            self.db.execute(
                select(Wallet)
                .where(Wallet.user_id == user_id)
                .where(Wallet.currency == currency)
                .with_for_update()
            )
            .scalars()
            .first()
        )
        if wallet:
            return wallet
        wallet = Wallet(user_id=user_id, currency=currency, balance_minor=0)
        self.db.add(wallet)
        self.db.flush()
        return wallet

    def list_wallets(self, user_id: str) -> list[Wallet]:
        return self.db.execute(select(Wallet).where(Wallet.user_id == user_id).order_by(Wallet.currency)).scalars().all()

    def credit(self, user: User, payload: MoneyRequest) -> Transaction:
        currency = ensure_supported(payload.currency)
        amount_minor = to_minor(payload.amount, currency)
        wallet = self.wallet_for_update(user.id, currency)
        wallet.balance_minor += amount_minor
        tx = Transaction(
            user_id=user.id,
            wallet_id=wallet.id,
            type=TransactionType.credit,
            currency=currency,
            amount_minor=amount_minor,
            balance_after_minor=wallet.balance_minor,
            description=payload.description,
        )
        self.db.add(tx)
        self.db.flush()
        return tx

    def debit(self, user: User, payload: MoneyRequest) -> Transaction:
        currency = ensure_supported(payload.currency)
        amount_minor = to_minor(payload.amount, currency)
        wallet = self.wallet_for_update(user.id, currency)
        if wallet.balance_minor < amount_minor:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient funds")
        wallet.balance_minor -= amount_minor
        tx = Transaction(
            user_id=user.id,
            wallet_id=wallet.id,
            type=TransactionType.debit,
            currency=currency,
            amount_minor=-amount_minor,
            balance_after_minor=wallet.balance_minor,
            description=payload.description,
        )
        self.db.add(tx)
        self.db.flush()
        return tx

    def transfer(self, sender: User, payload: TransferRequest) -> tuple[Transaction, Transaction]:
        source_currency = ensure_supported(payload.source_currency)
        target_currency = ensure_supported(payload.target_currency)
        if sender.email == payload.recipient_email.lower():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot transfer to yourself")
        recipient = self.db.execute(select(User).where(User.email == payload.recipient_email.lower())).scalars().first()
        if recipient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")

        source_amount_minor = to_minor(payload.amount, source_currency)
        rate, exchange_rate = self.exchange.conversion_rate(source_currency, target_currency)
        target_amount_minor = convert_minor(source_amount_minor, source_currency, target_currency, rate)

        sender_wallet = self.wallet_for_update(sender.id, source_currency)
        recipient_wallet = self.wallet_for_update(recipient.id, target_currency)
        if sender_wallet.balance_minor < source_amount_minor:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient funds")

        transfer = Transfer(sender_id=sender.id, recipient_id=recipient.id)
        self.db.add(transfer)
        self.db.flush()

        sender_wallet.balance_minor -= source_amount_minor
        recipient_wallet.balance_minor += target_amount_minor

        debit_tx = Transaction(
            user_id=sender.id,
            wallet_id=sender_wallet.id,
            type=TransactionType.transfer_debit,
            currency=source_currency,
            amount_minor=-source_amount_minor,
            balance_after_minor=sender_wallet.balance_minor,
            description=payload.description,
            transfer_id=transfer.id,
            exchange_rate_id=exchange_rate.id if exchange_rate else None,
            source_currency=source_currency,
            source_amount_minor=source_amount_minor,
            target_currency=target_currency,
            target_amount_minor=target_amount_minor,
            rate_used=rate,
        )
        credit_tx = Transaction(
            user_id=recipient.id,
            wallet_id=recipient_wallet.id,
            type=TransactionType.transfer_credit,
            currency=target_currency,
            amount_minor=target_amount_minor,
            balance_after_minor=recipient_wallet.balance_minor,
            description=payload.description,
            transfer_id=transfer.id,
            exchange_rate_id=exchange_rate.id if exchange_rate else None,
            source_currency=source_currency,
            source_amount_minor=source_amount_minor,
            target_currency=target_currency,
            target_amount_minor=target_amount_minor,
            rate_used=rate,
        )
        self.db.add_all([debit_tx, credit_tx])
        self.db.flush()
        return debit_tx, credit_tx


class TransactionService:
    def __init__(self, db: Session):
        self.db = db

    def list_transactions(
        self,
        user_id: str,
        currency: str | None,
        tx_type: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Transaction], int]:
        query = select(Transaction).where(Transaction.user_id == user_id)
        count_query = select(func.count()).select_from(Transaction).where(Transaction.user_id == user_id)
        if currency:
            normalized = ensure_supported(currency)
            query = query.where(Transaction.currency == normalized)
            count_query = count_query.where(Transaction.currency == normalized)
        if tx_type:
            query = query.where(Transaction.type == tx_type)
            count_query = count_query.where(Transaction.type == tx_type)
        total = self.db.execute(count_query).scalar_one()
        items = (
            self.db.execute(query.order_by(Transaction.created_at.desc()).limit(limit).offset(offset))
            .scalars()
            .all()
        )
        return items, total


def transaction_amount(tx: Transaction) -> Decimal:
    return from_minor(tx.amount_minor, tx.currency)


def idempotent(db: Session, user: User, key: str, handler):
    existing = (
        db.execute(select(IdempotencyKey).where(IdempotencyKey.user_id == user.id).where(IdempotencyKey.key == key))
        .scalars()
        .first()
    )
    if existing:
        return json.loads(existing.response_body), existing.response_code
    try:
        body, code = handler()
        db.add(IdempotencyKey(user_id=user.id, key=key, response_code=code, response_body=json.dumps(body, default=str)))
        db.commit()
        return body, code
    except Exception:
        db.rollback()
        raise
