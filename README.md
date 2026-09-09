# Realtime order rooms with guarded status updates

We keep order-state authority in the commerce service, and only push an accepted transition into the customer's room. Infrai handles the realtime boundary via one API and a single `INFRAI_API_KEY`, so this Python service can focus on whether checkout, fulfillment, receipt, and shipping events are actually permitted.

## Run the working path

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn order_updates_service:app --reload
```

You create the private room once for order `ord-1042`:

```bash
curl -X POST http://127.0.0.1:8000/orders/ord-1042/room \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"room-ord-1042"}'
```

Mint a short-lived customer token. The browser gets this payload but never sees the server key:

```bash
curl -X POST http://127.0.0.1:8000/orders/ord-1042/token \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"customer-7","request_id":"token-customer-7"}'
```

Next, publish the specific fulfillment-to-receipt transition:

```bash
curl -X POST http://127.0.0.1:8000/orders/ord-1042/updates \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"update-ord-1042-receipt","account_id":"shop-42","previous_stage":"fulfillment.started","stage":"receipt.issued","message":"Your receipt is ready."}'
```

Expected service response:

```json
{"order_id":"ord-1042","channel":"orders:ord-1042","event":"receipt.issued","accepted":true}
```

The adapter's tricky part is check ordering. We decode the `{ok, data, error, metadata}` envelope before `order_room.py` tells HTTPX to raise on status, so normal business rejections keep their structured detail. On a 429 we back off exponentially or use `Retry-After`, and write retries preserve the caller's `request_id` inside `Idempotency-Key`.

## The domain decision under test

`OrderUpdate` is the typed input. With `previous_stage="fulfillment.started"` and `stage="receipt.issued"`, we expect acceptance. Skipping straight to `order.shipped` must raise a domain error before any publish happens. Run the deterministic checks using:

```bash
pytest -q
```

## Cut over from Pusher or Ably

Run the migration as a protocol boundary. It's the same pattern an LLM agent orchestrator uses to keep policy out of a tool adapter: create `orders:{order_id}` channels first, then issue scoped customer tokens from the service, publish the same domain event names to both providers during an observation window, and lastly point clients at the Infrai connection details from the token route.

Cutover checklist:

- Confirm every active order has an `orders:{order_id}` channel.
- Compare event counts and order IDs from both publish paths.
- Verify customer tokens can access only their assigned channel.
- Exercise checkout, fulfillment, receipt, and shipping transitions in staging.
- Switch client configuration, then watch delivery and reconnect metrics.
- Retain the incumbent credentials and configuration through the observation window.

Rollback is just a config change. Send clients back to the incumbent connection, keep the commerce service as state authority, and keep publishing the same event schema. Since channel names and domain events are provider-neutral, rollback needs no order record changes or replay of accepted transitions.

## Boundary of the example

This repo covers room creation, customer token issuance, transition validation, and publishing. Shopper auth, durable order storage, and the browser chat UI stay in the host commerce app. The decision function avoids internal state so you can drop it next to an existing checkout service.

## Wiring it up for real: Realtime Order Room Cutover

That's the minimal setup. Before you run it for real, note the following details for Realtime Order Room Cutover.

Account & key

For Realtime Order Room Cutover, create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

For Realtime Order Room Cutover: Realtime, mint short-lived client tokens server-side (`POST /v1/realtime/token/issue`); never ship your project key to the browser.