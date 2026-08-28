from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from src.domain.customer import (
    AccountStatus,
    AccountSummary,
    AccountType,
    CustomerProfile,
    KycStatus,
    KycSummary,
    Money,
    RiskRating,
    TransactionDirection,
    TransactionStatus,
    TransactionSummary,
    validate_reference,
)

from src.domain.errors import InvariantViolationError


class TestMoney:
    def test_valid_amount_and_currency(self) -> None:
        money = Money(amount=Decimal("2499.00"), currency="inr")
        assert money.currency == "INR"
        assert money.amount == Decimal("2499.00")

    def test_rejects_negative_amount(self) -> None:
        with pytest.raises(InvariantViolationError, match="non-negative"):
            Money(amount=Decimal("-1.00"), currency="USD")

    def test_rejects_non_finite_amount(self) -> None:
        with pytest.raises(InvariantViolationError, match="finite"):
            Money(amount=Decimal("NaN"), currency="USD")

    def test_rejects_more_than_two_decimal_places(self) -> None:
        with pytest.raises(InvariantViolationError, match="decimal places"):
            Money(amount=Decimal("1.005"), currency="USD")

    def test_accepts_whole_number_amount(self) -> None:
        money = Money(amount=Decimal("100"), currency="USD")
        assert money.amount == Decimal("100")

    def test_rejects_invalid_currency(self) -> None:
        with pytest.raises(InvariantViolationError, match="ISO code"):
            Money(amount=Decimal("1.00"), currency="US")

    def test_is_immutable(self) -> None:
        money = Money(amount=Decimal("1.00"), currency="USD")
        with pytest.raises(AttributeError):
            money.currency = "EUR"  # type: ignore[misc]


class TestCustomerProfile:
    def test_valid_profile(self) -> None:
        profile = CustomerProfile(
            customer_ref="cust_demo_001",
            display_name="Demo Customer",
            segment="retail",
            locale="en-IN",
        )
        assert profile.customer_ref == "cust_demo_001"

    def test_rejects_blank_display_name(self) -> None:
        with pytest.raises(InvariantViolationError, match="Display name"):
            CustomerProfile(
                customer_ref="cust_demo_001", display_name="  ", segment="retail", locale="en-IN"
            )

    def test_rejects_invalid_reference(self) -> None:
        with pytest.raises(InvariantViolationError, match="customer_ref"):
            CustomerProfile(
                customer_ref="!!", display_name="Demo", segment="retail", locale="en-IN"
            )


class TestAccountSummary:
    def _money(self) -> Money:
        return Money(amount=Decimal("100.00"), currency="INR")

    def test_valid_masked_account(self) -> None:
        account = AccountSummary(
            account_ref="acct_demo_checking",
            account_type=AccountType.CHECKING,
            masked_number="********4217",
            status=AccountStatus.ACTIVE,
            available_balance=self._money(),
        )
        assert account.status is AccountStatus.ACTIVE

    def test_rejects_unmasked_number(self) -> None:
        with pytest.raises(InvariantViolationError, match="masked"):
            AccountSummary(
                account_ref="acct_demo_checking",
                account_type=AccountType.CHECKING,
                masked_number="1234567890123456",
                status=AccountStatus.ACTIVE,
                available_balance=self._money(),
            )

    def test_rejects_overly_long_masked_number(self) -> None:
        with pytest.raises(InvariantViolationError, match="masked"):
            AccountSummary(
                account_ref="acct_demo_checking",
                account_type=AccountType.CHECKING,
                masked_number="*" * 33,
                status=AccountStatus.ACTIVE,
                available_balance=self._money(),
            )


class TestKycSummary:
    def test_valid_summary(self) -> None:
        summary = KycSummary(
            customer_ref="cust_demo_001",
            status=KycStatus.VERIFIED,
            risk_rating=RiskRating.LOW,
            last_reviewed_on=date(2026, 1, 1),
            next_review_due_on=date(2027, 1, 1),
        )
        assert summary.status is KycStatus.VERIFIED

    def test_rejects_due_date_before_reviewed_date(self) -> None:
        with pytest.raises(InvariantViolationError, match="next review due"):
            KycSummary(
                customer_ref="cust_demo_001",
                status=KycStatus.REVIEW_DUE,
                risk_rating=RiskRating.MEDIUM,
                last_reviewed_on=date(2026, 1, 1),
                next_review_due_on=date(2025, 1, 1),
            )


class TestTransactionSummary:
    def _money(self, amount: str = "2499.00") -> Money:
        return Money(amount=Decimal(amount), currency="INR")

    def test_valid_transaction(self) -> None:
        txn = TransactionSummary(
            transaction_ref="txn_demo_1001",
            account_ref="acct_demo_checking",
            direction=TransactionDirection.DEBIT,
            status=TransactionStatus.POSTED,
            amount=self._money(),
            counterparty_display="Demo Merchant",
            posted_at=datetime.now(UTC),
        )
        assert txn.direction is TransactionDirection.DEBIT

    def test_rejects_zero_amount(self) -> None:
        with pytest.raises(InvariantViolationError, match="positive"):
            TransactionSummary(
                transaction_ref="txn_demo_1001",
                account_ref="acct_demo_checking",
                direction=TransactionDirection.DEBIT,
                status=TransactionStatus.POSTED,
                amount=self._money("0.00"),
                counterparty_display="Demo Merchant",
                posted_at=datetime.now(UTC),
            )

    def test_rejects_blank_counterparty(self) -> None:
        with pytest.raises(InvariantViolationError, match="Counterparty"):
            TransactionSummary(
                transaction_ref="txn_demo_1001",
                account_ref="acct_demo_checking",
                direction=TransactionDirection.DEBIT,
                status=TransactionStatus.POSTED,
                amount=self._money(),
                counterparty_display="   ",
                posted_at=datetime.now(UTC),
            )

    def test_rejects_naive_timestamp(self) -> None:
        with pytest.raises(InvariantViolationError, match="time-zone aware"):
            TransactionSummary(
                transaction_ref="txn_demo_1001",
                account_ref="acct_demo_checking",
                direction=TransactionDirection.DEBIT,
                status=TransactionStatus.POSTED,
                amount=self._money(),
                counterparty_display="Demo Merchant",
                posted_at=datetime(2026, 1, 1),
            )


class TestValidateReference:
    def test_returns_stripped_value(self) -> None:
        assert validate_reference("account_ref", "  acct_demo_checking  ") == "acct_demo_checking"

    def test_rejects_too_short_value(self) -> None:
        with pytest.raises(InvariantViolationError, match="account_ref"):
            validate_reference("account_ref", "ab")

    def test_rejects_disallowed_characters(self) -> None:
        with pytest.raises(InvariantViolationError):
            validate_reference("account_ref", "acct demo!")
