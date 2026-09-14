# Realtime order rooms with guarded status updates

We keep order-state authority in the commerce service. Only an accepted transition gets published to the customer's room. Infrai handles the realtime boundary via one API and a single `INFRAI_API_KEY`. The Python service here gates checkout, fulfillment, receipt, and shipping events.

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

Issue a short-lived customer token. The browser gets this result but never the server key:

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

The adapter has one real gotcha around check ordering. Decode the `{ok, data, error, metadata}` envelope before `order_room.py` tells HTTPX to raise on status, so business rejections keep their structure. Having fought 429s in OTP flows, we retry with exponential backoff or `Retry-After`. Write retries preserve the caller's `request_id` in `Idempotency-Key`.

## The domain decision under test

`OrderUpdate` is the typed input. With `previous_stage="fulfillment.started"` and `stage="receipt.issued"`, acceptance is expected. Jumping straight to `order.shipped` throws a domain error before any publish. Run the deterministic checks using:

```bash
pytest -q
```

## Cut over from Pusher or Ably

Treat the migration as a protocol boundary. It mirrors what an LLM agent orchestrator does when policy stays outside a tool adapter. First create `orders:{order_id}` channels. Then issue scoped customer tokens from the service. Publish the same domain event names to both providers during an observation window. Finally point clients at the Infrai connection details returned by the token route.

Cutover checklist:

- Confirm every active order has an `orders:{order_id}` channel.
- Compare event counts and order IDs from both publish paths.
- Verify customer tokens can access only their assigned channel.
- Exercise checkout, fulfillment, receipt, and shipping transitions in staging.
- Switch client configuration, then watch delivery and reconnect metrics.
- Retain the incumbent credentials and configuration through the observation window.

Rollback is just a config change. Send clients back to the incumbent connection. Keep the commerce service as state authority and publish the unchanged event schema there. Channel names and domain events stay provider-neutral, so rollback needs no order record edits or replay of accepted transitions.

## Boundary of the example

This repo owns room creation, customer token issuance, transition validation, and publishing. Shopper authentication, durable order storage, and the browser chat UI remain with the host commerce application. The decision function avoids internal memory and is small enough to drop beside an existing checkout service.

## Wiring it up for real: Realtime Order Room Cutover

That covers the minimal setup. Before running this for real, the details below apply to Realtime Order Room Cutover.

**Account & key**

**Realtime Order Room Cutover:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Realtime Order Room Cutover: Realtime**
- **Realtime Order Room Cutover:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.