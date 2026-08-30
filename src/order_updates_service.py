from __future__ import annotations

from enum import StrEnum
from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, Field

from order_room import InfraiError, InfraiRealtime


class OrderStage(StrEnum):
    CHECKOUT_CONFIRMED = "checkout.confirmed"
    FULFILLMENT_STARTED = "fulfillment.started"
    RECEIPT_ISSUED = "receipt.issued"
    ORDER_SHIPPED = "order.shipped"


NEXT_STAGE = {
    OrderStage.CHECKOUT_CONFIRMED: OrderStage.FULFILLMENT_STARTED,
    OrderStage.FULFILLMENT_STARTED: OrderStage.RECEIPT_ISSUED,
    OrderStage.RECEIPT_ISSUED: OrderStage.ORDER_SHIPPED,
}


class RoomRequest(BaseModel):
    request_id: str = Field(min_length=8)


class TokenRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    request_id: str = Field(min_length=8)


class OrderUpdate(BaseModel):
    request_id: str = Field(min_length=8)
    account_id: str = Field(min_length=1)
    previous_stage: OrderStage
    stage: OrderStage
    message: str = Field(min_length=1, max_length=500)


class PublishedUpdate(BaseModel):
    order_id: str
    channel: str
    event: OrderStage
    accepted: bool


def channel_for(order_id: str) -> str:
    return f"orders:{order_id}"


def require_next_stage(update: OrderUpdate) -> None:
    expected = NEXT_STAGE.get(update.previous_stage)
    if update.stage != expected:
        raise ValueError(
            f"expected {expected.value if expected else 'a terminal order'} after "
            f"{update.previous_stage.value}"
        )


app = FastAPI(title="E-commerce order rooms")


def realtime() -> InfraiRealtime:
    return InfraiRealtime.from_environment()


def client_error(error: InfraiError) -> HTTPException:
    status = error.status_code if 400 <= error.status_code < 500 else 502
    return HTTPException(status_code=status, detail={"code": error.code, "error": error.detail})


@app.post("/orders/{order_id}/room")
async def create_room(
    body: RoomRequest,
    order_id: Annotated[str, Path(min_length=1)],
) -> dict[str, object]:
    channel = channel_for(order_id)
    try:
        async with httpx.AsyncClient() as client:
            result = await realtime().create_order_channel(
                client, channel=channel, request_id=body.request_id
            )
    except InfraiError as error:
        raise client_error(error) from error
    return {"order_id": order_id, "channel": channel, "realtime": result}


@app.post("/orders/{order_id}/token")
async def issue_token(
    body: TokenRequest,
    order_id: Annotated[str, Path(min_length=1)],
) -> dict[str, object]:
    channel = channel_for(order_id)
    try:
        async with httpx.AsyncClient() as client:
            token = await realtime().issue_customer_token(
                client,
                client_id=body.customer_id,
                channel=channel,
                request_id=body.request_id,
            )
    except InfraiError as error:
        raise client_error(error) from error
    return {"order_id": order_id, "channel": channel, "token": token}


@app.post("/orders/{order_id}/updates", response_model=PublishedUpdate)
async def publish_update(
    body: OrderUpdate,
    order_id: Annotated[str, Path(min_length=1)],
) -> PublishedUpdate:
    try:
        require_next_stage(body)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    channel = channel_for(order_id)
    try:
        async with httpx.AsyncClient() as client:
            await realtime().publish_order_update(
                client,
                channel=channel,
                event=body.stage.value,
                data={
                    "order_id": order_id,
                    "previous_stage": body.previous_stage.value,
                    "stage": body.stage.value,
                    "message": body.message,
                },
                account_id=body.account_id,
                request_id=body.request_id,
            )
    except InfraiError as error:
        raise client_error(error) from error

    return PublishedUpdate(
        order_id=order_id,
        channel=channel,
        event=body.stage,
        accepted=True,
    )
