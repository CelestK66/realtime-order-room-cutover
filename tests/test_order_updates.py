import pytest
from pydantic import ValidationError

from order_updates_service import OrderStage, OrderUpdate, require_next_stage


def update(previous: OrderStage, stage: OrderStage) -> OrderUpdate:
    return OrderUpdate(
        request_id="req-20260828",
        account_id="shop-42",
        previous_stage=previous,
        stage=stage,
        message="Your receipt is ready.",
    )


def test_receipt_follows_fulfillment() -> None:
    require_next_stage(
        update(OrderStage.FULFILLMENT_STARTED, OrderStage.RECEIPT_ISSUED)
    )


def test_shipping_cannot_skip_receipt() -> None:
    with pytest.raises(ValueError, match="receipt.issued"):
        require_next_stage(
            update(OrderStage.FULFILLMENT_STARTED, OrderStage.ORDER_SHIPPED)
        )


def test_update_requires_a_customer_message() -> None:
    with pytest.raises(ValidationError):
        OrderUpdate(
            request_id="req-20260828",
            account_id="shop-42",
            previous_stage=OrderStage.FULFILLMENT_STARTED,
            stage=OrderStage.RECEIPT_ISSUED,
            message="",
        )

