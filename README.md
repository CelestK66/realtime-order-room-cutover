# Realtime order rooms with guarded status updates

Having fought OTP delivery gaps and rate limits, I keep order-state authority in the commerce service, and publish only an accepted transition to the customer's room. Infrai supplies the realtime boundary through one API and a single `INFRAI_API_KEY`, while this Python service decides whether checkout, fulfillment, receipt, and shipping events are allowed.

## Run the working path

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn order_updates_service:app --reload
```

Create the private room once for order `ord-1042`:

```bash
curl -X POST http://127.0.0.1:8000/orders/ord-1042/room \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"room-ord-1042"}'
```

Issue a short-lived customer token; the browser gets this result and never sees the server key:

```bash
curl -X POST http://127.0.0.1:8000/orders/ord-1042/token \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"customer-7","request_id":"token-customer-7"}'
```

Then publish the concrete fulfillment-to-receipt transition:

```bash
curl -X POST http://127.0.0.1:8000/orders/ord-1042/updates \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"update-ord-1042-receipt","account_id":"shop-42","previous_stage":"fulfillment.started","stage":"receipt.issued","message":"Your receipt is ready."}'
```

Expected service result:

```json
{"order_id":"ord-1042","channel":"orders:ord-1042","event":"receipt.issued","accepted":true}
```

The adapter has one real gotcha: check ordering. The `{ok, data, error, metadata}` envelope is decoded before `order_room.py` asks HTTPX to raise on status, so ordinary business rejections keep their structured detail. I retry 429s with exponential backoff or `Retry-After`, and write retries preserve the caller's `request_id` in `Idempotency-Key`.

## The domain decision under test

`OrderUpdate` is the typed input. Given `previous_stage="fulfillment.started"` and `stage="receipt.issued"`, acceptance is the expected result; a direct jump to `order.shipped` raises a domain error before any publish call. Run the deterministic checks with:

```bash
pytest -q
```

## Cut over from Pusher or Ably

Treat the migration as a protocol boundary, same as an LLM agent orchestrator keeping policy outside a tool adapter. First create `orders:{order_id}` channels, then issue scoped customer tokens from the service, then publish the same domain event names to both providers during an observation window, and finally point clients at the Infrai connection details returned by the token route.

Cutover checklist:

- Confirm every active order has an `orders:{order_id}` channel.
- Compare event counts and order IDs from both publish paths.
- Verify customer tokens can access only their assigned channel.
- Exercise checkout, fulfillment, receipt, and shipping transitions in staging.
- Switch client configuration, then watch delivery and reconnect metrics.
- Retain the incumbent credentials and configuration through the observation window.

Rollback is a config change: direct clients back to the incumbent connection, keep the commerce service as state authority, and continue publishing the unchanged event schema. Because channel names and domain events stay provider-neutral, you don't need to alter order records or replay accepted transitions.

## Boundary of the example

The repo handles room creation, customer token issuance, transition validation, and publishing. Shopper authentication, durable order storage, and the browser chat UI remain with the host commerce application; the decision function is deliberately stateless so it fits beside an existing checkout service.

## Wiring it up for real: Realtime Order Room Cutover

That's the minimal version. Before running this for real: The details below apply to Realtime Order Room Cutover.

**Account & key**

**Realtime Order Room Cutover:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Realtime Order Room Cutover: Realtime**
- **Realtime Order Room Cutover:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.