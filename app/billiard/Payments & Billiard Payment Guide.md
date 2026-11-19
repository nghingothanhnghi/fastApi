# Payments & Billiard Payment Guide

Updated Nov 19, 2026 · @JohnyWalker

## How payment works

The Payments module decides how a bill is paid; billiard only says what to charge. A finished table session becomes one payment order, and that order is paid by one or more payment lines (cash, bank transfer, or a single Stripe payment).

|  | Payments module (`app/payments/`) | Billiard (`app/billiard/`) |
| --- | --- | --- |
| Owns | Orders, payment lines, cash change, split payments, VietQR transfers, SePay bank feed, voids, cash shifts, audit trail | Tables, sessions, pricing, drinks and food, the bill |
| Decides | Whether a line is paid, pending, cancelled or voided | The amount (`grand_total`), the club (tenant), and that the session must be stopped first |
| Writes back | Nothing in billiard's tables except through the adapter | A mirror of the payment state on the session, so reports never join Payments tables |

The amount never comes from the client. It is always the session's `grand_total`, read on the server.

### States

| Bill (`payment_state`) | Meaning |
| --- | --- |
| `unpaid` | Nothing collected and nothing waiting |
| `pending` | Part paid, a transfer is waiting, or a Stripe payment is in progress |
| `paid` | Completed lines cover the full amount |

| Payment line (`status`) | Meaning |
| --- | --- |
| `pending` | A transfer waiting for the bank feed or the cashier |
| `completed` | Money received |
| `cancelled` | A pending line voided before any money arrived. A cashier can cancel it, or the system cancels it automatically when a transfer was never received (see "Transfers that never arrive") |
| `voided` | Money was received, then reversed by a manager |
| `failed` | The line could not be recorded |

## Setup

Cash works with no configuration. Bank transfer needs the receiving account, and automatic confirmation needs a SePay webhook. Each `PAYMENT_*` variable falls back to the older `BILLIARD_*` name where one existed, so existing deployments keep working.

| Variable | Default | What it does |
| --- | --- | --- |
| `PAYMENT_BANK_BIN` | empty | NAPAS bank BIN of the receiving account, e.g. `970436` |
| `PAYMENT_BANK_ACCOUNT_NO` | empty | Receiving account number. SePay transfers to any other account are ignored |
| `PAYMENT_BANK_ACCOUNT_NAME` | empty | Account holder name shown to the customer |
| `PAYMENT_BANK_CODE` | empty | Short bank code, e.g. `VCB`, used only for the hosted QR image URL |
| `PAYMENT_MEMO_PREFIX` | `PAY` | Prefix of the transfer content that identifies a payment line, e.g. `PAY12L34` |
| `PAYMENT_TRANSFER_EXPIRE_MINUTES` | `15` | How long a transfer QR is shown as valid |
| `PAYMENT_TRANSFER_AUTO_CANCEL_GRACE_MINUTES` | `60` | A waiting transfer line is cancelled by a background job this many minutes **after** its QR expired. `0` turns the job off |
| `PAYMENT_BANK_TRANSFER_REQUIRES_CONFIRMATION` | `true` | `false` makes a transfer count as paid immediately, like cash |
| `PAYMENT_MANUAL_CONFIRM_REQUIRES_MANAGER` | `false` | `true`: only a manager or admin may press "received" by hand. Cashiers get `403` |
| `PAYMENT_MANUAL_CONFIRM_REQUIRES_NOTE` | `false` | `true`: pressing "received" by hand needs a note of at least 3 characters (e.g. the bank reference). Otherwise `422` |
| `PAYMENT_REQUIRE_OPEN_SHIFT` | `false` | `true` refuses payments until a cashier has opened a shift |
| `SEPAY_WEBHOOK_SECRET` | empty | HMAC secret for the SePay webhook (preferred) |
| `SEPAY_API_KEY` | empty | API key alternative. The webhook answers `503` if neither is set |
| `SEPAY_TIMESTAMP_TOLERANCE_SECONDS` | `300` | Allowed clock difference for HMAC requests |
| `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET` | empty | Needed only for Stripe |

### Steps

1. Set `PAYMENT_BANK_BIN`, `PAYMENT_BANK_ACCOUNT_NO` and `PAYMENT_BANK_ACCOUNT_NAME`. Without the BIN and account number no QR is drawn; a transfer line still works and the cashier confirms it by hand.
2. Set `SEPAY_WEBHOOK_SECRET` (or `SEPAY_API_KEY`).
3. In SePay, add a webhook to `https://<your-api>/payments/bank-feed/sepay`. It must be HTTPS on a public domain.
4. Send one small real transfer and check that the bill settles. The QR format was checked for structure and checksum, not scanned with a real banking app.
5. Decide whether to set `PAYMENT_REQUIRE_OPEN_SHIFT=true` so every payment lands in a shift.
6. Decide how strict the manual "received" button should be (`PAYMENT_MANUAL_CONFIRM_REQUIRES_MANAGER`, `PAYMENT_MANUAL_CONFIRM_REQUIRES_NOTE`). Both default to off, which trusts the cashier. The SePay auto-confirm and the manager "assign" action are never affected by these two settings.
7. Check that the app scheduler is running. The job `payments_transfer_expiry_job` runs every 5 minutes and cancels stale transfer lines (it is registered in `main.py`).

### Upgrading an existing database

Run `python migrate_payments_orders.py` once. It is idempotent and backs up SQLite first. It creates the payment tables, adds `table_sessions.payment_order_id`, and deletes the old demo payment lines, events and bank transactions. Sessions already paid stay paid, and sessions left pending by a deleted line are reset to unpaid. A fresh database gets everything from `init_db`.

The SQLite path was tested; the PostgreSQL path was not.

## Cashier guide

A normal day is: open a shift, run sessions, take payment after each stop, close the shift with a cash count. You can only take payment after the session is stopped.

1. **Open the shift.** `POST /payments/shifts/open` with `{"opening_float": 1000000}`, the cash already in the drawer. Only one shift per club can be open.
2. **Start a table, add drinks.** `POST /tables/{id}/start`, then `POST /sessions/{id}/items`.
3. **Stop the session.** `POST /sessions/{id}/stop` returns the bill with `grand_total`.
4. **Take payment** with one of the ways below, using `POST /sessions/{id}/pay`.
5. **Close the shift.** `POST /payments/shifts/{id}/close` with `{"counted_cash": 1290000}`. The response shows expected cash, counted cash and the variance.

During the day you can record cash that leaves or enters the drawer outside a sale: `POST /payments/shifts/{id}/movements` with `{"type": "pay_out", "amount": 20000, "reason": "bought ice"}` (or `pay_in`).

### Ways to pay

| Way | Request body | Result |
| --- | --- | --- |
| Cash, exact | `{"payment_method": "cash"}` | Bill is `paid` at once |
| Cash with change | `{"payment_method": "cash", "cash_tendered": 500000}` | Paid. The line shows `change_given` (190,000 for a 310,000 bill) |
| Bank transfer | `{"payment_method": "bank_transfer"}` | Bill stays `pending` and shows a QR. It turns `paid` when the transfer is confirmed |
| Split | `{"payments": [{"method": "cash", "amount": 200000}, {"method": "bank_transfer", "amount": 110000}]}` | Cash line completes, transfer line waits. The bill is `pending` with `balance_due` 110,000 |
| Stripe | `{"payment_method": "stripe"}` | `pending` with a `client_secret` for the card form. Then call `POST /sessions/{id}/pay/confirm` |

Send either `payment_method` or `payments`, never both. For a split, the line amounts must add up exactly to the amount due. You can use up to 6 lines, and Stripe cannot be mixed with the others.

### Taking a bank transfer

1. Show the customer the QR from `payments[].transfer` (`qr_payload` to draw it, or `qr_image_url`). It carries the exact amount and the memo, for example `PAY12L34`.
2. The customer pays. If the SePay webhook is set up, the bill turns `paid` by itself within seconds; refresh the bill to see it.
3. If the webhook is not set up or is slow, check your bank app and press received: `POST /sessions/{id}/pay/lines/{line_id}/confirm`. Depending on the club's settings this may need a **note** (for example the bank reference you checked) or may be **restricted to a manager**. See "Manual confirmation rules".
4. If the money never arrives, cancel the line with `POST /sessions/{id}/pay/lines/{line_id}/cancel` and take the balance another way.

The QR is shown as valid for 15 minutes by default (`PAYMENT_TRANSFER_EXPIRE_MINUTES`). Cancelling and paying again makes a new QR.

### Transfers that never arrive

A line that stays `pending` is not left forever. Once its QR has expired **and** the grace period has passed (60 minutes by default), the system cancels it by itself:

- The line becomes `cancelled` with the note "Transfer not received in time", and the audit trail records `line_expired` (no actor).
- The bill goes back to `unpaid`, or stays `pending` if another part was already paid, so the cashier can start over.
- The grace period exists so a slow bank notification can still match a line whose QR just expired. Until the job runs, "received" still works on an expired line.
- If the customer's money arrives **after** the line was cancelled, the bank transaction shows as `needs_review` ("Money received for a line that is cancelled"). The manager applies it by paying again with a new transfer line and assigning the transaction to it.
- A line the bank (or a cashier) confirmed a moment before the job ran is never cancelled: the job re-checks the line under a lock.

### Manual confirmation rules

The "received" button trusts the person pressing it, so it can be tightened:

| Setting | Effect on `POST .../lines/{line_id}/confirm` |
| --- | --- |
| `PAYMENT_MANUAL_CONFIRM_REQUIRES_MANAGER=true` | A cashier gets `403 Only a manager can confirm a transfer manually` |
| `PAYMENT_MANUAL_CONFIRM_REQUIRES_NOTE=true` | A missing, blank or too short (< 3 characters) note gets `422 A note is required to confirm a transfer manually` |

Confirming a line that is already `completed` stays idempotent and is never refused. The note is stored on the payment line and in the audit event.

### Reading the bill

`GET /sessions/{id}` shows the bill at any time, including after payment.

| Field | Meaning |
| --- | --- |
| `payment_state` | `unpaid`, `pending` or `paid` |
| `payment_method` | `cash`, `bank_transfer`, `stripe`, or `split` |
| `amount_paid` | Sum of completed lines |
| `balance_due` | `grand_total` minus `amount_paid` |
| `payments[]` | Every line: method, amount, status, `cash_tendered`, `change_given`, `note`, and `transfer` while a transfer waits |
| `paid_by` | Empty when the bank feed confirmed the payment automatically |

Amounts arrive as strings such as `"310000.00"`.

## Bank transfer and SePay

A transfer is confirmed automatically only when the memo identifies the payment line and the amount is exactly right. Anything else is kept for a manager, so money is never silently absorbed or invented.

### How a transfer is matched

SePay watches the receiving account and calls `POST /payments/bank-feed/sepay` for every incoming transfer. The transaction is stored first (unique per SePay `id`, so a replay does nothing), then matched by searching the transfer content for the payment code, in any case and with any text around it. SePay's own `code` field is checked too.

| Result | When | What happens |
| --- | --- | --- |
| `matched` | Code found, line still `pending`, amount exactly equal | Line completes, the bill settles, audit event `transfer_auto_confirmed` with no user |
| `needs_review` | Code found but the amount differs, the line was already paid (possible double transfer), or the line was cancelled or voided (including cancelled by the expiry job) | Nothing is confirmed; a manager decides |
| `unmatched` | No code in the content, or the code matches no line | Kept for a manager |
| `ignored` | Outgoing transfer, or a different account | Kept for audit |

If the line is settled by someone else between the match and the lock, the transaction becomes `needs_review` ("Could not confirm the line"), so the money is never lost and never counted twice.

### What the webhook answers

- It answers `{"success": true}` once an authenticated transaction is stored, even if it could not be matched. SePay retries for up to 5 hours on anything else.
- `401` for a missing or wrong signature or key, `503` if no secret or key is configured, `400` for invalid JSON or a missing id or amount.
- With a secret set, requests are verified with HMAC-SHA256 over `<X-SePay-Timestamp>.<raw body>` and rejected if the timestamp is more than `SEPAY_TIMESTAMP_TOLERANCE_SECONDS` (5 minutes) off. An API-key-only request is then refused.

### Customer pays the wrong amount

| Situation | What the system does | What the manager does |
| --- | --- | --- |
| Customer sends less | `needs_review`, bill stays `pending` | Cancel the waiting transfer line. Pay again as a split: a transfer line for the amount actually received plus cash or another transfer for the rest. Then assign the bank transaction to the new transfer line (exact amount). The pending-lines list (below) finds that line by amount |
| Customer sends more | `needs_review`, bill stays `pending` | Refund the extra outside the system. Press received on the line (it completes at the billed amount; add a note if the club requires one), then ignore the transaction with a note such as overpaid, refunded 10,000 |
| Customer sends twice | Second transfer is `needs_review` (line already paid) | Refund the duplicate, then ignore it |
| Customer forgets the memo | `unmatched` | Assign it to the right pending line (exact amount only) |
| Customer pays after the line was cancelled | `needs_review` ("line that is cancelled") | Create a new transfer line for the bill and assign the transaction to it |

### Limits to know

- SePay stops retrying after 5 hours. If the server is down longer, the transfer is not lost at the bank but the webhook is. Until a catch-up job exists, check unmatched money in your bank app and use the received button.
- Changing `PAYMENT_MEMO_PREFIX` only affects new transfer lines. A line waiting with the old prefix will show up as `unmatched`.
- Unmatched transactions carry no club, so every manager can see them. Matched and `needs_review` ones are scoped to the club of their bill.

## Manager guide

Managers and admins can reverse money, resolve bank transactions the system would not guess, and close any shift. Cashiers get `403` on the first two.

### Void a payment

A void reverses a completed line, for example cash handed back or a transfer returned. Send `POST /sessions/{id}/pay/lines/{line_id}/void` with `{"reason": "wrong table charged"}`. The reason is required and must be at least 3 characters.

- The payment record becomes `refunded`.
- The bill goes back to `pending` (part paid) or `unpaid`, and can be paid again.
- The void is written to the audit trail with your name and the reason.
- A cash void counts as money out of the drawer in the shift where the void happens, so a void after close lands in the next shift.

To drop a line that never received money (a transfer that did not arrive), use cancel instead. Any user can do that: `POST /sessions/{id}/pay/lines/{line_id}/cancel`. If nobody does, the system cancels it automatically (see "Transfers that never arrive").

### Review bank transactions

Open the review list with `GET /payments/bank-feed/transactions?status=needs_review`, and look at `unmatched` too. The list is paged with `limit` (1 to 200, default 50) and `offset`.

| Action | Request | Rule |
| --- | --- | --- |
| Find the line to assign | `GET /payments/bank-feed/pending-lines?amount=<transaction amount>` | Lists bank-transfer lines still waiting for money, newest first. `amount` keeps only lines of exactly that amount; `limit` (1 to 200) and `offset` page the result. Each row has `line_id`, `order_id`, `source_type`, `source_id` (the session id for billiard), `amount`, `currency`, `order_total`, `transfer_memo`, `created_at`, `expires_at`, `expired` |
| Link money to a bill | `POST /payments/bank-feed/transactions/{id}/assign` with `{"line_id": 7}` | The line must be a pending bank transfer of the same club, and the amount must match exactly (`422` otherwise) |
| Dismiss | `POST /payments/bank-feed/transactions/{id}/ignore` with `{"note": "refunded"}` | Use for refunds, duplicates and transfers that are not bill payments. Add a note |

A transaction can be assigned or ignored only while it is `unmatched` or `needs_review` (`409` otherwise). A line whose QR expired (`expired: true`) but that is still `pending` can still be assigned, until the expiry job cancels it.

### Shifts and the cash drawer

Only the person who opened a shift or a manager can close it. At close the system freezes the expected cash, the counted cash and the variance.

| Part | Meaning |
| --- | --- |
| Expected cash | Opening float + cash received - cash voided + pay-ins - pay-outs |
| Variance | Counted cash - expected cash. A negative number means cash is missing |
| Not in the drawer | Change given back, and bank transfers (reported per method only) |

Use `GET /payments/shifts/current` for live totals while a shift is open, and `GET /payments/shifts` for history. Because the drawer reads from payment lines for the whole club, any business paid through this module shows up in it. A pay-out larger than the cash expected in the drawer is refused with `409`.

### Audit trail

`GET /sessions/{id}/pay/events` lists every payment action on a bill, oldest first, with who did it. An empty actor means the system, for example the bank feed or the expiry job.

| Event | When |
| --- | --- |
| `line_created` | A payment line was added |
| `cash_received` | A cash line completed |
| `transfer_awaiting` | A transfer line is waiting for money |
| `transfer_confirmed` | A cashier pressed received (the note, if any, is in the event data) |
| `transfer_auto_confirmed` | The bank feed matched and confirmed it (no actor) |
| `transfer_assigned_from_bank` | A manager linked a bank transaction to a line |
| `line_cancelled` | A pending line was cancelled by a person |
| `line_expired` | The expiry job cancelled a transfer that never arrived (no actor) |
| `line_failed` | A line could not be recorded |
| `line_voided` | A manager reversed a completed line |
| `order_paid` | Completed lines now cover the full amount |

## API quick reference

Billiard screens use the `/sessions/{id}/pay...` URLs; every other business, and the cash drawer and bank feed, use `/payments/...`. All endpoints need a logged-in user (JWT) except the SePay webhook.

### Billiard session URLs

| Method | Path | Role | Description |
| --- | --- | --- | --- |
| `GET` | `/sessions/{id}` | any user of the club | The bill, also after payment |
| `POST` | `/sessions/{id}/stop` | any user | Stop and return the bill |
| `POST` | `/sessions/{id}/pay` | any user | Pay in one go or split |
| `POST` | `/sessions/{id}/pay/confirm` | any user | Settle a Stripe payment |
| `POST` | `/sessions/{id}/pay/lines/{line_id}/confirm` | any user (manager only if `PAYMENT_MANUAL_CONFIRM_REQUIRES_MANAGER`) | Cashier confirms a transfer arrived. Optional `{"note": "..."}`, required if `PAYMENT_MANUAL_CONFIRM_REQUIRES_NOTE` |
| `POST` | `/sessions/{id}/pay/lines/{line_id}/cancel` | any user | Cancel a pending line |
| `POST` | `/sessions/{id}/pay/lines/{line_id}/void` | manager, admin | Reverse a completed line (reason required) |
| `GET` | `/sessions/{id}/pay/events` | any user | Audit trail |

### Generic Payments URLs

The same operations exist for any business under `/payments/orders/{source_type}/{source_id}/...`. For billiard, `source_type` is `billiard_session` and `source_id` is the session id.

| Method | Path | Role | Description |
| --- | --- | --- | --- |
| `GET` | `/payments/orders/{source_type}/{source_id}` | any user of the club | Total, paid, balance and every line |
| `POST` | `/payments/orders/{source_type}/{source_id}/pay` | any user | Pay in one go or split |
| `POST` | `/payments/orders/{source_type}/{source_id}/pay/confirm` | any user | Settle a Stripe payment |
| `POST` | `/payments/orders/{source_type}/{source_id}/lines/{line_id}/confirm` | any user (same manual-confirm rules) | Confirm a transfer |
| `POST` | `/payments/orders/{source_type}/{source_id}/lines/{line_id}/cancel` | any user | Cancel a pending line |
| `POST` | `/payments/orders/{source_type}/{source_id}/lines/{line_id}/void` | manager, admin | Reverse a completed line |
| `GET` | `/payments/orders/{source_type}/{source_id}/events` | any user | Audit trail |
| `POST` | `/payments/shifts/open` | any user | Open a shift (`409` if one is open) |
| `GET` | `/payments/shifts/current` | any user | Open shift with live totals, or `null` |
| `GET` | `/payments/shifts` | any user | Recent shifts (`limit`, `offset`) |
| `GET` | `/payments/shifts/{id}` | any user | Drawer maths, per-method totals, movements |
| `POST` | `/payments/shifts/{id}/movements` | any user | Pay-in or pay-out with a reason |
| `POST` | `/payments/shifts/{id}/close` | opener or manager | Close with the counted cash |
| `POST` | `/payments/bank-feed/sepay` | SePay HMAC or API key | Webhook for incoming transfers |
| `GET` | `/payments/bank-feed/transactions` | manager | List; filter with `?status=`; paged with `limit` and `offset` |
| `GET` | `/payments/bank-feed/pending-lines` | manager | Transfer lines still waiting for money; `?amount=` filters by exact amount; paged |
| `POST` | `/payments/bank-feed/transactions/{id}/assign` | manager | Link to a pending transfer line |
| `POST` | `/payments/bank-feed/transactions/{id}/ignore` | manager | Dismiss |

### Back-office endpoints (administrators only)

`POST /payments/`, `PATCH /payments/{id}` and `/payments/stripe/create|confirm/{ref}|refund/{ref}` work on payment records below the order layer. They require an **admin or super admin**; a cashier or manager gets `403`. (`POST /payments/` and `PATCH /payments/{id}` used to have no login check at all; that is fixed.) `GET /payments/`, `/payments/client/{id}` and `/payments/user/{id}` need a login and are limited to the caller's own scope unless the caller is a super admin. Billiard screens never use any of these.

### Example: split payment

Request to `POST /sessions/42/pay`:

```json
{"payments": [
  {"method": "cash", "amount": 200000, "cash_tendered": 500000},
  {"method": "bank_transfer", "amount": 110000}
]}
```

The bill in the response, trimmed:

```json
{
  "session_id": 42,
  "grand_total": "310000.00",
  "payment_state": "pending",
  "payment_method": "split",
  "amount_paid": "200000.00",
  "balance_due": "110000.00",
  "payments": [
    {"id": 1, "method": "cash", "amount": "200000.00", "status": "completed",
     "cash_tendered": "500000.00", "change_given": "300000.00"},
    {"id": 2, "method": "bank_transfer", "amount": "110000.00", "status": "pending",
     "transfer": {"memo": "PAY7L2", "amount": "110000.00",
                  "qr_payload": "000201...", "expires_at": "2026-10-21T13:10:00Z"}}
  ]
}
```

### Error codes

| Code | Typical reason |
| --- | --- |
| `401` | SePay webhook with a missing or wrong signature or key |
| `403` | A non-manager tried to void, assign, ignore or list bank transactions or pending lines, close someone else's shift, or confirm a transfer by hand while that is restricted to managers. A non-admin called a back-office `/payments/` endpoint |
| `404` | Unknown session or line, or it belongs to another club. Never `403`, so ids are not leaked |
| `409` | Wrong state: session not stopped, already paid, payment in progress, nothing to pay, shift already open, no open shift when one is required, pay-out above the drawer cash, transaction already handled |
| `422` | Split lines do not add up, cash tendered below the amount, void without a reason, assigned amount differs from the line, manual confirmation without the required note |
| `503` | SePay webhook called while no secret or key is configured |

## Make another module payable

A new business module gets cash, change, split, VietQR, bank-feed confirmation, voids and the audit trail by writing one adapter and registering it. Billiard's adapter is `app/billiard/services/payment_adapter.py`, about 70 lines.

### The contract

| Method | What it must do |
| --- | --- |
| `source_type` | A unique name, e.g. `"shop_order"` |
| `load(db, source_id, user, *, lock=True)` | Return the business object or raise `404`. With a user, enforce the tenant check (`404`, never `403`). With `user=None` (a system caller such as the bank feed or the expiry job) skip it. With `lock=True` take a row lock so payments on the same object are serialized |
| `check_payable(obj)` | Raise `409` if it cannot take a payment yet (billiard: the session must be stopped) |
| `quote(obj)` | Return `Quote(client_id, currency, total, metadata)`: what to collect, for which club. `metadata` is merged into every payment record so a human can reconcile it, e.g. `{"billiard_session_id": 42}` |
| `apply_state(db, obj, order)` | Copy the order's state onto the business object. Do not commit |

### Example

```python
# app/shop/services/payment_adapter.py
from app.payments.services.payable_registry import Quote, payable_registry

class ShopOrderPayable:
    source_type = "shop_order"

    def load(self, db, source_id, user, *, lock=True):
        ...  # find the order, 404 for other tenants, lock when asked

    def check_payable(self, order):
        if order.status != "confirmed":
            raise HTTPException(409, "Confirm the order before paying")

    def quote(self, order):
        return Quote(client_id=order.client_id, currency="VND", total=order.total,
                     metadata={"shop_order_id": order.id})

    def apply_state(self, db, order, payment_order):
        order.payment_order_id = payment_order.id
        order.payment_state = payment_order.state.value   # unpaid | pending | paid
        order.paid_at = payment_order.paid_at

payable_registry.register(ShopOrderPayable())
```

### Steps

1. Add a `payment_order_id` column to your business table, plus any mirror fields you want for reports (state, method, paid time). A mirror means reports never join the Payments tables.
2. Write the adapter as above and make sure its module is imported at startup, because importing it registers it. Billiard does this in `app/billiard/routes/__init__.py`.
3. Pay through `/payments/orders/shop_order/{id}/pay`. If you want friendlier URLs, call `payment_order_service.pay(db, "shop_order", str(id), request, user)` from your own route, as billiard does.
4. Test the adapter against `app/tests/test_payments_testkit.py`, which runs the Payments logic against a fake business.

### Rules the adapter protects

- The amount always comes from `quote()`, never from the client.
- Payments commits by itself, because the payment providers do. Your route does not need to wrap it in a transaction.
- Never use the Payments tables from business code. Read the mirror fields, or call `payment_order_service`.
- `apply_state` also runs when the system acts without a user (bank feed confirmation, expiry job), so it must not depend on a logged-in user.

## Troubleshooting

Most problems show up as a status code or a bank transaction that is not `matched`. Check the bill's `payments[]` and the audit trail first.

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| Customer paid by transfer but the bill is still `pending` | Webhook not set up, the memo was missing or mistyped, or the amount differs | Open `GET /payments/bank-feed/transactions?status=needs_review` and check `unmatched` too. Assign it to the line (find it with `pending-lines?amount=`), or press received if you can see the money in the bank app |
| The transfer line shows `cancelled` ("Transfer not received in time") and the customer says they paid | The expiry job cancelled it before the money arrived | The late transfer is in the review list as `needs_review`. Take payment again with a new transfer line and assign the transaction to it |
| The bill went back to `unpaid` by itself | The expiry job cancelled the only waiting line | Expected. Pay again. To change or turn off the delay, see `PAYMENT_TRANSFER_AUTO_CANCEL_GRACE_MINUTES` |
| Expired lines are never cancelled | `PAYMENT_TRANSFER_AUTO_CANCEL_GRACE_MINUTES=0`, or the scheduler is not running | Set a value above 0 and check that `payments_transfer_expiry_job` is registered and running |
| `403 Only a manager can confirm a transfer manually` | `PAYMENT_MANUAL_CONFIRM_REQUIRES_MANAGER=true` and a cashier pressed received | Ask a manager, or wait for the bank feed |
| `422 A note is required to confirm a transfer manually` | `PAYMENT_MANUAL_CONFIRM_REQUIRES_NOTE=true` and no note was sent | Send `{"note": "checked in the bank app, ref FT123"}` |
| SePay webhook returns `401` | Wrong secret or key, a body changed in transit, or the server clock is more than 5 minutes off | Check `SEPAY_WEBHOOK_SECRET` or `SEPAY_API_KEY`, and keep the server clock on NTP. If a secret is set, an API-key-only request is refused |
| SePay webhook returns `503` | Neither `SEPAY_WEBHOOK_SECRET` nor `SEPAY_API_KEY` is set | Set one |
| No QR on a transfer line | `PAYMENT_BANK_BIN` or `PAYMENT_BANK_ACCOUNT_NO` is empty | Set both. Until then press received by hand |
| `409` A payment is already in progress | A pending line exists on that bill | Confirm it or cancel it, then pay the balance |
| `409` Stop the session before paying | The session is still active | Stop it first |
| `409` about an open shift | `PAYMENT_REQUIRE_OPEN_SHIFT=true` and no shift is open | Open a shift with `POST /payments/shifts/open` |
| `422` lines do not add up | Split amounts differ from the amount due | After a cancel or void the amount due can be lower than `grand_total`. Use `balance_due` from the bill |
| `403` on void, assign, ignore or pending-lines | The user is not a manager or admin | Ask a manager, or give the user that role |
| `403` on `POST /payments/` or `PATCH /payments/{id}` | These are back-office routes for admins | Billiard screens never need them. Use the `/sessions/...` URLs |
| `500` some payment lines could not be recorded | A line failed while saving (for example a database error) | Lines already recorded stay. Read the bill, then pay the balance again |
| A bill shows `paid` but has no lines | It was paid before the Payments module existed | Expected. Such a bill counts as settled and cannot be paid again |
| A transfer was waiting when `PAYMENT_MEMO_PREFIX` changed | The matcher no longer knows the old memo | It appears as `unmatched`. Assign it by hand |

### Before you go live

- Send one small real transfer and one real cash payment, then close the shift and check the variance.
- Confirm the SePay webhook shows success in SePay's log.
- Check that a cashier gets `403` on a void and a manager does not.
- Let one test transfer expire and check that the line is cancelled after the grace period and the bill can be paid again.
- If you set a manual-confirm restriction, check that the cashier sees the expected `403` or `422`.
- Run the tests: `test_payments_orders.py`, `test_payments_shifts.py`, `test_payments_bank_feed.py`, `test_payments_transfer_expiry.py`, `test_payments_manual_confirm.py` and `test_billiard_payments.py`.