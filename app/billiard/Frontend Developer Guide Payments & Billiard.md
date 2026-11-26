# Frontend Developer Guide: Payments & Billiard

Updated Nov 19, 2026 · @Someone

## Start here

The frontend needs about 30 endpoints to run a billiard table from start to payment: open a table, add drinks, stop the session, take payment, run the cash drawer and review bank transfers. Generate types from the backend's OpenAPI file, and use this guide for the screens and rules the schema cannot tell you.

New to the project? Read "The whole process, start to finish" first. It follows one session from the first tap to the receipt, then the screen-by-screen sections explain each part in detail.

### What changed since Nov 26

| Change | What to do in the frontend |
| --- | --- |
| A table started from the controller with a package the server cannot apply now opens the session and is flagged for **billing review**. New fields on the board (`needs_billing_review`, `requested_package_id`, `billing_review_reason`) and on the bill (those plus `billing_review_resolution`, `billing_review_note`, `billing_reviewed_by`, `billing_reviewed_at`). New `GET /sessions/billing-review` and `POST /sessions/{id}/billing-review`. Payment returns `409` until it is resolved | Show a warning badge on the board tile and a "Needs billing review" list. On the bill, hide Pay while `needs_billing_review` is true and show a Resolve button (see screen 13) |
| `POST /sessions/{id}/items` also returns `lines` (every line created, free first). The old top-level fields are unchanged | Optional: use `lines` instead of reloading the bill. Reloading still works |
| `minimum_hour` overtime on a package is prorated (no second minimum) | None. The totals come from the server |
| New package endpoints `/billiard/packages` (list, get, create, change, deactivate) | New manager screen 12 (packages). The POS picker lists them with `GET /billiard/packages` and starts a session with `package_id` (see Step 4) |
| Sessions can start with a package: `POST /tables/{id}/start` accepts `package_id`; the bill gets `package_name`, `package_price`, `package_minutes`, `overtime_minutes`; items have `from_package`; the board has `package_name` and `overtime_minutes`; the quote accepts `package_id` | Add a package picker to Start (next to the timed-play choice). On the bill show the package as the table-time line and `overtime_minutes` as extra time. Show free items with their `(package)` name and a price of 0. After `POST /items` reload the bill, because one call can create two lines |

### What changed since Nov 20

| Change | What to do in the frontend |
| --- | --- |
| Each club saves its own receiving bank account (`/payments/bank-accounts`). The transfer QR is built from it instead of a server setting | New manager screen 11 (bank account set-up). The cashier screens do not change, but read the QR rules in screen 2 |
| `transfer.bank_code` can now be `null` while the QR still works (the club saved only the bank BIN) | Never require `bank_code`. Draw `qr_payload`; `qr_image_url` is still filled |
| A transfer to a different account than the one the QR showed lands in the bank inbox as `needs_review` (reason "Received on account ending ...") | Show the reason as it is. No new status |
| A QR already on screen keeps the account it was created with, even if a manager changes the account afterwards | Nothing to do. Rebuild the QR from the bill, never from a cached account |
| New errors `413`, `501` (QR image upload) and `409` (account in use) | See "Error handling" and screen 11 |

### What changed since Nov 13

| Change | What to do in the frontend |
| --- | --- |
| `PATCH /tables/{id}` edits a table's name or hourly rate, and `DELETE /tables/{id}` deactivates it | New: see screen 9 (manager set-up). `GET /tables` now returns only active tables, so a deactivated table disappears from the board |
| Manual "Received" can be restricted by the club: manager only, and/or a note is required | The Received call can now return `403` or `422`. Always offer a note field and handle both (see screen 2). No endpoint tells you which rule is on |
| `GET /billiard/controller/status` rows have `last_error` and `last_error_at` (latest fault the controller reported). The controller can now also send `time_extend`, `table_status`, `button_press` and `device_error` events, which change `ends_at`, the table status and the scoreboard | Show the fault as a warning on the controller card (screen 10). The board needs no new fields: poll `GET /tables/active` and `ends_at` / `remaining_seconds` / `status` already reflect these events |
| Controller device admin endpoints: `GET /billiard/controller/status`, `GET /billiard/controller/hydro-candidates`, `POST /billiard/controller/register` | New manager screen 10. The other `/controller/...` calls stay device-only |
| New audit event type `line_expired` | Add it to your event labels (see "Generic order and audit trail") |
| Several error messages were corrected | Starting a busy table answers `409 Table is playing`, not "already has an active session"; starting a game in a stopped session answers `409 Games can only be started in an active session` (see "Error handling") |

### Earlier changes (since Oct 24)

| Change | What to do in the frontend |
| --- | --- |
| `GET /auth/me` now returns `roles` | Use it to decide whether to show manager buttons. The old "no roles" workaround is no longer needed (see "Who sees which buttons") |
| `POST /payments/` and `PATCH /payments/{id}` are admin only (the auth fix is merged) | Nothing to change. Billiard screens never used them |
| `GET /payments/bank-feed/transactions` is paged (`limit` 1 to 200, default 50, and `offset`) | Add paging to the manager inbox (screen 6) |
| Scoreboard endpoints for the games played in a session | See "Extra billiard screens" |
| Pricing rules and a price quote | See "Extra billiard screens". The bill's `pricing_rule_name` comes from these |
| Table usage report and table creation (manager) | See "Extra billiard screens" |

### Set up

| Topic | What to do |
| --- | --- |
| Schema and docs | The API serves `/openapi.json` and a Swagger page at `/docs`. Generate types with `npx openapi-typescript https://<api>/openapi.json -o api.d.ts` |
| Login | `POST /auth/login` with form-encoded `username` and `password` (not JSON). It returns `{"access_token", "token_type": "bearer"}` |
| Auth header | Send `Authorization: Bearer <access_token>` on every call except the SePay webhook, which is not yours. A `401` means log in again |
| Money | Amounts arrive as strings such as `"310000.00"`. The currency is VND, which has no decimals, so convert with `Number()` and format with `Intl.NumberFormat("vi-VN")`. Send amounts in request bodies as plain numbers |
| Dates | ISO 8601. Some timestamps come without an offset, for example `2026-10-21T00:28:54.654112`. Treat a timestamp with no offset as UTC (append `Z`), then show it in the club's time zone |
| The amount | Never send the bill total. For a single payment the server uses `grand_total`. In a split you send how the total is divided, and the lines must add up exactly to `balance_due` |
| Your club | Every call is limited to the logged-in user's club. An id that belongs to another club returns `404`, not `403` |
| Trailing slash | Use the paths exactly as written here. `/tables`, `/products` and `/payments/shifts` have no trailing slash |
| Live updates | There is no WebSocket yet. Poll: `GET /tables/active` about every 30 seconds, and a waiting bill every 3 to 5 seconds (see "Polling, errors and edge cases") |

### Which URLs to call

| Screen | URLs | Response |
| --- | --- | --- |
| Table board | `/tables`, `/tables/active`, `/tables/{id}/start` | `Table[]`, `ActiveTable[]`, `StartSessionResponse` |
| Menu and items | `/products`, `/sessions/{id}/items` | `Product[]`, `SessionItem` |
| Billiard bill and payment | `/sessions/{id}`, `/sessions/{id}/stop`, `/sessions/{id}/pay...` | `Bill` (includes the payment lines) |
| Cash drawer | `/payments/shifts...` | `Shift` or `ShiftSummary` |
| Manager bank inbox | `/payments/bank-feed/transactions...`, `/payments/bank-feed/pending-lines` | `BankTransaction`, `PendingTransferLine` |
| Another business later | `/payments/orders/{source_type}/{source_id}/...` | `Order` (same lines as the bill) |
| Scoreboard | `/sessions/{id}/games`, `/games/{id}/score`, `/games/{id}/reset`, `/games/{id}/new`, `/games/{id}/finish` | `Game`, `NewGameResponse` |
| Packages | `/billiard/packages`, `/billiard/packages/{id}` | `Package[]`, `Package` |
| Pricing rules and quote | `/billiard/pricing-rules`, `/billiard/pricing-rules/quote` | `PricingRule[]`, `PricingQuote` |
| Manager reports and set-up | `/reports/tables/usage`, `POST /tables`, `PATCH /tables/{id}`, `DELETE /tables/{id}` | `TableUsageReport`, `Table`, `DeactivateTableResponse` |
| Manager controller devices | `/billiard/controller/status`, `/billiard/controller/hydro-candidates`, `/billiard/controller/register` | `ControllerDevice[]`, `HydroCandidate[]`, `RegisterControllerResponse` |

`/billiard/controller/events`, `/sync` and `/state` are for the table controller devices (ESP32), which sign in with a device key, not a user token. Do not build screens on those three. The `status`, `hydro-candidates` and `register` calls above are the only controller calls a screen should use.

Billiard screens should use the `/sessions/{id}/pay...` URLs because they return the full bill, so one response redraws the whole screen. The `/payments/orders/...` URLs return the payment part only. For billiard they work too, with `source_type` set to `billiard_session` and `source_id` set to the session id, but you do not need them.

Do not build billiard screens on `POST /payments/`, `PATCH /payments/{id}` or `/payments/stripe/*`. Those are back-office routes for administrators (admin or super admin only). A cashier or manager gets a `403` there. Everything a cashier needs is under `/sessions`, `/tables` and `/payments/shifts`.

## The whole process, start to finish

This follows one cashier's day, in the order the screens appear. Each step names the call, what comes back and where the user goes next. The sample numbers are the same throughout: 135 minutes at 100,000 VND an hour is 225,000, plus 85,000 of drinks and food, so the bill is 310,000 VND.

Two rules hold in every step. The server works out the amount from the session, so the frontend never sends a total. And what you draw comes from the last response, so after any action replace your copy of the bill with the one returned.

### The day at a glance

| # | Step | Call | Who | Next screen |
| --- | --- | --- | --- | --- |
| 1 | Log in | `POST /auth/login` | Anyone | Table board |
| 2 | Open the shift | `POST /payments/shifts/open` | Cashier | Table board. Required only when the club sets `PAYMENT_REQUIRE_OPEN_SHIFT=true` |
| 3 | See the tables | `GET /tables`, `GET /tables/active` | Cashier | Pick a free table |
| 4 | Start a session | `POST /tables/{id}/start` | Cashier | Session screen |
| 5 | Add drinks and food | `GET /products`, `POST /sessions/{id}/items` | Cashier | Repeat while the table is playing |
| 6 | Stop the session | `POST /sessions/{id}/stop` | Cashier | Pay screen (bill is `unpaid`) |
| 7 | Take payment | `POST /sessions/{id}/pay` | Cashier | Receipt, or the transfer-waiting screen |
| 8 | Finish a transfer | `POST /sessions/{id}/pay/lines/{line_id}/confirm`, or the bank feed does it | Cashier or the bank | Receipt |
| 9 | Close the shift | `POST /payments/shifts/{id}/close` | Cashier | Variance screen |
| 10 | Fix a mistake | `POST /sessions/{id}/pay/lines/{line_id}/void`, `/payments/bank-feed/...` | Manager | The bill reopens |

The lifecycle of one bill, so you know which step is allowed when:

| Moment | Session | `payment_state` | What you can do |
| --- | --- | --- | --- |
| After start | running, `end_time` is `null` | `unpaid` | Add items, stop. Paying is refused with `409 Stop the session before paying` |
| After stop | finished, `end_time` is set | `unpaid` | Pay. Adding items is refused with `409` |
| During a payment | finished | `pending` | Confirm or cancel a waiting line, or pay the balance |
| After payment | finished | `paid` | Show the receipt. Only a manager can void a line |

### Step 1. Log in

`POST /auth/login` takes form data (`username`, `password`), not JSON, and returns `{"access_token": "...", "token_type": "bearer"}`. Send the token as `Authorization: Bearer <token>` from now on. The token expires, and a `401` anywhere means send the user to login and then back to the same screen.

Right after login, call `GET /auth/me`. It returns the user with a `roles` list (each role has a `name` such as `"manager"`). Keep it, because it decides whether to show manager buttons (see "Who sees which buttons").

### Step 2. Open the shift

A shift is the cash drawer for the club: one open shift per club, not per cashier. `GET /payments/shifts/current` returns the open shift, or `null`. If it is `null`, show the opening-float form (screen 5) and call `POST /payments/shifts/open` with `{"opening_float": 1000000}`. A second open call returns `409 A shift is already open`, so load the existing one instead. If the club does not require shifts you can skip this step, but the drawer totals in step 9 are worked out for the time the shift was open, so a drawer count only makes sense when a shift was open.

### Step 3. The table board

`GET /tables` lists every **active** table: `{"id": 1, "name": "T01", "status": "available", "hourly_rate": "100000.00"}`. A table a manager deactivated is not in the list. `status` is `available`, `playing`, `reserved` or `maintenance`. Offer Start only on `available` tables; the server answers `409` for a table that cannot be started.

`GET /tables/active` lists the tables that are playing right now, with live numbers you can show on the tile and refresh every 30 seconds or so:

```json
[
  {
    "id": 1,
    "name": "T01",
    "status": "playing",
    "session_id": 42,
    "start_time": "2026-10-24T02:00:00",
    "elapsed_minutes": 135,
    "hourly_rate": "100000.00",
    "current_table_fee": "225000.00",
    "current_product_fee": "85000.00",
    "ends_at": null,
    "remaining_seconds": null,
    "is_overtime": false,
    "current_discount": "0.00",
    "current_total": "310000.00"
  }
]
```

Keep `session_id` on the tile. Every later call uses it. `current_total` is a running estimate for display; the real bill comes from the stop call. It follows the same pricing rule as the final bill, so it should match what Stop returns.

### Step 4. Start a session

`POST /tables/{id}/start` takes an optional body: `{"planned_minutes": 90}` (1 to 1440) for timed play, `{"package_id": 3}` to start with a package (the package's duration becomes `ends_at`), or no body for open play. Never send both `planned_minutes` and `package_id` (`422`). It returns the new session:

```json
{ "session_id": 42, "table_id": 1, "start_time": "2026-10-24T02:00:00", "ends_at": "2026-10-24T03:30:00", "opened_by": "cashier1" }
```

A package must be active (`400 Package is not available`) and belong to the club (`404 Package not found`): reload `GET /billiard/packages` when you see either. If the table cannot be started the server answers `409` with the reason: `Table is playing` (somebody else started it first), `Table is reserved`, `Table is maintenance`, `Table is inactive`, or, if two people start it at the same instant, `Table already has an active session`. Reload the board and open the running session if there is one.

### Step 5. Add drinks and food

`GET /products` returns the menu. Show products where `is_active` is true. A product with `variants` is sold by variant, so make the cashier pick one and send its `variant_id`. Otherwise use `base_price`. The price shown is for display only; the server prices the item itself.

`POST /sessions/{id}/items` with `{"product_id": 5, "variant_id": null, "quantity": 2}` returns `201` with the new line:

```json
{
  "id": 7, "product_id": 5, "variant_id": null, "product_name": "Coca Cola",
  "quantity": 2, "unit_price": "15000.00", "total_price": "30000.00"
}
```

If the session was started with a package that includes this product, the first units are free: the call can create **two** lines, a free one (`from_package: true`, `unit_price` `"0.00"`, name ending in `(package)`) and a paid one for the rest. The response's own fields are the paid line when there is one (otherwise the free line), and `lines` lists every line this call created, free first. You can draw from `lines` or reload `GET /sessions/{id}`; both work.

Errors: `404 Product not found`, `400 Product is not available`, `400 Variant does not belong to this product`, and `409 Items can only be added to an active session` once the session is stopped. To show the current list, call `GET /sessions/{id}`: `items` is the full list and `grand_total` is up to date.

### Step 6. Stop the session

`POST /sessions/{id}/stop` ends the clock, closes the running game (if any), frees the table and returns the bill. A second stop returns `409 Session is already completed`, so on that error just load the bill with `GET /sessions/{id}`.

`POST /sessions/{id}/discount` (managers only) gives a discount on the table fee plus products. Send **either** `{"amount": 5000, "reason": "Regular customer"}` **or** `{"percent": 10, "reason": "Birthday"}` (never both; the reason is required, 3 to 255 characters) and show the returned `Bill`: `discount`, `grand_total` and, for a percent, `discount_percent`. `{"amount": 0}` removes it. It works while the session is playing (the board's `current_total` already includes it) and after Stop, but only until a payment is started: then it returns `409 A payment was already started...`, so hide the button once the bill has payment lines or is `pending` or `paid`. A percent follows the total as items are added and at Stop; a fixed amount never makes the total negative. Always show `discount` as its own line above `grand_total`, and charge `grand_total` (the server already subtracts the discount).

`POST /sessions/{id}/cancel` (managers only) cancels a session that was opened by mistake. Send `{"reason": "Opened on the wrong table"}` (3 to 255 characters, required: ask the manager for it). It frees the table, ends the running game as cancelled and returns the same `Bill` with `status: "cancelled"`, `cancel_reason`, `cancelled_by` and `cancelled_at`, and every total `0`. Only an **active** session can be cancelled: `409` for a completed or already cancelled one (a paid session is reversed with a payment void, not a cancel). Ask for confirmation first, drop the session from the board afterwards, and never show a Pay button for `status: "cancelled"` (`POST /pay` returns `409`).

```json
{
  "session_id": 42,
  "table_id": 1,
  "table_name": "T01",
  "currency": "VND",
  "start_time": "2026-10-24T02:00:00",
  "end_time": "2026-10-24T04:15:00",
  "duration_minutes": 135,
  "hourly_rate": "100000.00",
  "billing_policy": "per_minute",
  "pricing_rule_name": null,
  "pricing_params": {},
  "total_table_fee": "225000.00",
  "total_product_fee": "85000.00",
  "discount": "0.00",
  "discount_percent": null,
  "discount_reason": null,
  "discounted_by": null,
  "grand_total": "310000.00",
  "items": [
    { "id": 7, "product_id": 5, "variant_id": null, "product_name": "Coca Cola", "quantity": 2, "unit_price": "15000.00", "total_price": "30000.00" },
    { "id": 8, "product_id": 9, "variant_id": null, "product_name": "Fruit plate", "quantity": 1, "unit_price": "55000.00", "total_price": "55000.00" }
  ],
  "payment_state": "unpaid",
  "payment_method": null,
  "payment_reference": null,
  "paid_at": null,
  "amount_paid": "0.00",
  "balance_due": "310000.00",
  "payments": [],
  "opened_by": "cashier1",
  "stopped_by": "cashier1",
  "paid_by": null
}
```

Show this as the pay screen (screen 1). `billing_policy` and `pricing_rule_name` explain how the table fee was worked out; show `pricing_rule_name` as a small caption when it is not `null`. `billing_policy` is one of `per_minute`, `hourly`, `block`, `minimum_hour`; very old bills can also show `rounded_hour`, which means the same as `hourly`. `opened_by` and `stopped_by` are `null` when the table controller started or stopped the session by itself.

### Step 7. Take payment

Call `POST /sessions/{id}/pay` with one of these bodies. Send either `payment_method` or `payments`, never both.

| The customer pays | Body | What comes back |
| --- | --- | --- |
| Cash, exact | `{"payment_method": "cash"}` | `payment_state: "paid"` |
| Cash with change | `{"payment_method": "cash", "cash_tendered": 500000}` | `paid`, with `change_given: "190000.00"` on the line |
| Bank transfer | `{"payment_method": "bank_transfer"}` | `pending`, with a QR on the line (see below) |
| Part cash, part transfer | `{"payments": [{"method": "cash", "amount": 200000}, {"method": "bank_transfer", "amount": 110000}]}` | `pending`, cash line paid, transfer line waiting |
| Card | `{"payment_method": "stripe"}` | `pending`, with `gateway.client_secret` |

The response is the whole bill plus a `gateway` field (`null` unless it is a card payment), so redraw the screen from it. For a cash payment of 500,000 on this bill:

```json
{
  "session_id": 42,
  "grand_total": "310000.00",
  "payment_state": "paid",
  "payment_method": "cash",
  "payment_reference": "manual-3-c1-a1b2c3d4",
  "paid_at": "2026-10-24T04:16:10.123456Z",
  "amount_paid": "310000.00",
  "balance_due": "0.00",
  "payments": [
    {
      "id": 12, "method": "cash", "amount": "310000.00", "status": "completed",
      "cash_tendered": "500000.00", "change_given": "190000.00",
      "payment_reference": "manual-3-c1-a1b2c3d4", "note": null,
      "confirmed_at": "2026-10-24T04:16:10.100000Z",
      "voided_at": null, "void_reason": null, "transfer": null
    }
  ],
  "paid_by": "cashier1",
  "gateway": null
}
```

(The bill fields from step 6, such as `items`, are also present; they are left out here to keep the example short.)

For the split above, the response has `payment_state: "pending"`, `amount_paid: "200000.00"` and `balance_due: "110000.00"`. The transfer line is the one still waiting:

```json
{
  "id": 14, "method": "bank_transfer", "amount": "110000.00", "status": "pending",
  "cash_tendered": null, "change_given": null,
  "payment_reference": "manual-3-c1-9f8e7d6c", "note": null,
  "confirmed_at": null, "voided_at": null, "void_reason": null,
  "transfer": {
    "bank_code": "VCB",
    "account_no": "0123456789",
    "account_name": "CLB BIDA",
    "amount": "110000.00",
    "memo": "PAY7L14",
    "qr_payload": "000201010212...6304ABCD",
    "qr_image_url": "https://img.vietqr.io/image/VCB-0123456789-compact2.png?amount=110000&addInfo=PAY7L14",
    "expires_at": "2026-10-24T04:31:10Z"
  }
}
```

`qr_payload` is shortened here. The real one is a long text string that you draw as a QR code. The memo `PAY7L14` is made of the order number (7) and the line id (14); it is what lets the bank feed find this payment.

Rules the server enforces on this call:

- The amount due is `balance_due`. A split must add up to it exactly, with 1 to 6 lines, or the server answers `422`.
- A bill that has a waiting transfer line cannot take a new payment: the server answers `409 A payment is already in progress`. Confirm or cancel the waiting line first.
- Card pays the whole bill in one go. It is refused with `409` once any cash or transfer line exists, and cannot be part of a split.
- The server may be set to treat a bank transfer as paid at once (`PAYMENT_BANK_TRANSFER_REQUIRES_CONFIRMATION=false`). Then a transfer line comes back `completed` and there is no waiting screen. So always decide the screen from `payment_state` and the lines, never from the method you sent.
- With `PAYMENT_REQUIRE_OPEN_SHIFT=true` and no open shift the answer is `409 Open a shift before taking payments`.

### Step 8. Finish a bank transfer

While the transfer line is `pending`, show screen 2 and refresh the bill every 3 to 5 seconds. There are four ways it ends:

1. **The bank feed confirms it.** SePay posts the incoming transfer to the backend, which matches the memo and the exact amount. The bill turns `paid` by itself, with `paid_by: null`.
2. **The cashier presses Received.** `POST /sessions/{id}/pay/lines/14/confirm` (the body is optional: `{"note": "checked in the bank app"}`). The bill is returned, now `paid`. The club may require a note (`422` without one) or restrict the button to managers (`403` for a cashier), see screen 2.
3. **The cashier presses Cancel.** `POST /sessions/{id}/pay/lines/14/cancel` (optional `{"reason": "customer left"}`). The line becomes `cancelled`, the bill goes back to part paid or `unpaid`, and the cashier pays the balance another way.
4. **The server cancels it.** If nobody acts, a background job cancels the line some time after the QR expired (60 minutes of grace by default). Your polling sees the line turn `cancelled` with the note "Transfer not received in time".

### Step 9. Show the receipt, close the shift

When `payment_state` is `paid`, show the receipt (screen 4). The same data stays available later from `GET /sessions/{id}`, so a customer can ask for it again.

At the end of the day, count the drawer and call `POST /payments/shifts/{id}/close` with `{"counted_cash": 1290000}`. The response shows `expected_cash`, `counted_cash` and `variance` (counted minus expected, negative means cash is missing). Only the cashier who opened the shift or a manager can close it. Cash that leaves or enters the drawer outside a sale is recorded with `POST /payments/shifts/{id}/movements`, for example `{"type": "pay_out", "amount": 20000, "reason": "bought ice"}`. A pay-out larger than the cash in the drawer is refused with `409`.

### Step 10. Manager tools

A manager can void a completed line that was a mistake (`POST /sessions/{id}/pay/lines/{line_id}/void` with `{"reason": "gave too much change"}`). The bill goes back to `pending` or `unpaid` and can be paid again. Money that arrived in the bank but could not be matched is handled in the bank inbox (screen 6). `GET /sessions/{id}/pay/events` returns the audit trail of every payment action on a bill, which is useful for a "history" panel.

## Screens to build

Six screens cover the payment part of the flow; the table board and the menu come before them (steps 3 to 5 above). The pay screen and the transfer-waiting screen are the same page in two states, driven by the bill's `payment_state`.

### 1. Pay screen (after the session is stopped)

Show the bill (items, `total_table_fee`, `total_product_fee`, `grand_total`) and the ways to pay: Cash, Bank transfer, Split, and Card only if Stripe is enabled for the club.

- **Cash:** an input for the amount handed over, quick buttons (exact, 50,000, 100,000, 200,000, 500,000) and the change shown live as `tendered - balance_due`. Disable the button while tendered is below `balance_due`. Send `{"payment_method": "cash", "cash_tendered": 500000}`. Leaving tendered out means an exact payment.
- **Bank transfer:** one button. Send `{"payment_method": "bank_transfer"}`, then show screen 2.
- **Split:** open the split editor (screen 3).
- **Card (Stripe):** show it only if your app offers cards. No endpoint tells you whether Stripe is configured, so use a setting in the frontend. Send `{"payment_method": "stripe"}`. The response has `gateway.client_secret`. Complete the card payment with Stripe's SDK, then call `POST /sessions/{id}/pay/confirm`. Card pays the whole bill at once, so hide it as soon as the bill has any cash or transfer line; the server refuses it with `409` after that.
- While a transfer line is waiting, do not show any pay buttons. The server refuses a new payment with `409 A payment is already in progress`. The cashier must press Received or Cancel first.
- After a successful `paid` response, show the receipt (screen 4).

### 2. Transfer waiting

Shown when `payment_state` is `pending` and a line has `method: "bank_transfer"`, `status: "pending"` and a `transfer` object.

- Draw `transfer.qr_payload` as a QR code with a QR library. If it is `null`, use `<img src={transfer.qr_image_url}>`. If both are `null`, the club has no bank account saved: show the amount and memo and say "Ask a manager to set up the bank account" (managers: link to screen 11). Account number and name are shown as text when present. The account on the QR is the club's saved account at the moment the line was created, so always show `transfer.account_name` next to the QR; the cashier can spot a wrong account before the customer pays.
- Always show the amount and the memo in large text. The memo (for example `PAY7L2`) is how the bank feed finds the payment.
- Show a countdown to `transfer.expires_at`. After it passes, say the QR has expired but keep the Received button working, because the customer may have paid already. The server only cancels the line itself after a grace period (60 minutes by default).
- Buttons: **Received** (`POST /sessions/{id}/pay/lines/{line_id}/confirm`) and **Cancel** (`POST /sessions/{id}/pay/lines/{line_id}/cancel`, optional reason).
- **Received needs a note field.** Show an optional text box ("Bank reference you checked") and send it as `{"note": "..."}` when it is filled in. A club can require it: then the server answers `422 A note is required to confirm a transfer manually` for a missing or very short note (under 3 characters). On that `422`, keep the note box open and mark it required. A club can also allow only managers to press Received: then a cashier gets `403 Only a manager can confirm a transfer manually`. Show "Ask a manager to confirm this transfer, or wait for the bank" and keep the screen polling. There is no endpoint that tells you in advance which rule is on, so react to the response.
- Refresh the bill every 3 to 5 seconds while this screen is open. The bank feed can turn the bill `paid` with no user action, and the screen should switch to the receipt by itself. If the server cancels the line after the grace period, the bill goes back to `unpaid` and the screen should switch back to the pay screen.

### 3. Split editor

- A list of up to 6 lines. Each has a method (cash or bank transfer), an amount, and for cash an optional tendered amount.
- Show `remaining = balance_due - sum(line amounts)`. Enable Pay only when `remaining` is exactly 0. Prefill a new line with the remaining amount.
- Send `{"payments": [{"method": "cash", "amount": 200000, "cash_tendered": 500000}, {"method": "bank_transfer", "amount": 110000}]}`.
- Cash lines complete at once; a transfer line goes to screen 2. A part-paid bill (`pending`, `amount_paid > 0`, no waiting line) reopens this editor with `balance_due` prefilled.
- Stripe cannot be mixed into a split.

### 4. Receipt

Shown when `payment_state` is `paid`. List every line with its method and amount, `change_given` for cash, `paid_at`, and `paid_by`. When `paid_by` is `null`, write that the bank feed confirmed it automatically. A bill that is `paid` with an empty `payments` list was paid before the new payment module; show it as settled with no line detail.

### 5. Cash drawer (shifts)

| State | What to show |
| --- | --- |
| No open shift (`GET /payments/shifts/current` returns `null`) | A form for the opening float. `POST /payments/shifts/open` with `{"opening_float": 1000000}` |
| Shift open | Live totals from `/current`: `expected_cash`, `cash_sales`, `cash_voids`, `pay_ins`, `pay_outs`, and the per-method `methods` list. Buttons for pay-in and pay-out (type, amount, reason of at least 3 characters) and Close |
| Closing | Ask for the counted cash. `POST /payments/shifts/{id}/close` with `{"counted_cash": 1290000}` |
| After close | Show `expected_cash`, `counted_cash` and `variance`. A negative variance means cash is missing, so show it in red |
| History | `GET /payments/shifts?limit=30&offset=0` |

If the club sets `PAYMENT_REQUIRE_OPEN_SHIFT=true`, paying without an open shift returns `409`. Check `/payments/shifts/current` before showing the pay screen and send the cashier to open a shift first.

Two more rules from the server. There is one open shift per club, so a second cashier sees the same open shift instead of opening their own. And a pay-out larger than the cash in the drawer is refused with `409`, so show the drawer's `expected_cash` next to the pay-out form and check the amount before you send it.

### 6. Manager bank inbox

A list from `GET /payments/bank-feed/transactions?status=needs_review`, with tabs for `unmatched`, `matched` and `ignored`. Each row shows the amount, the transfer `content`, the `reason`, and the time. The list is paged: `limit` is 1 to 200 (default 50) and `offset` skips rows, so add a "Load more" button that raises `offset` by `limit` until a page comes back shorter than `limit`.

- **Ignore** asks for a note and calls `POST /payments/bank-feed/transactions/{id}/ignore`.
- **Assign** links the money to a waiting transfer line: `POST /payments/bank-feed/transactions/{id}/assign` with `{"line_id": 7}`. The amount must equal the line's amount, so show the line's amount next to the transaction and block a mismatch.
- To pick the line, call `GET /payments/bank-feed/pending-lines?amount=<transaction amount>` (managers only; `limit` 1 to 200, default 50, and `offset`). Each row has `line_id`, `order_id`, `source_type`, `source_id` (the session id for billiard), `amount`, `currency`, `order_total`, `transfer_memo`, `created_at`, `expires_at` and `expired`. Show a picker with the table or session, the amount and the time, and send the chosen `line_id` to assign. Without `amount` it lists every waiting line, newest first. A row with `expired: true` can still be assigned until the server cancels the line.
- A transaction whose reason says "Money received for a line that is cancelled" arrived after the server (or a cashier) cancelled the line. It will not appear in `pending-lines`. Tell the manager to take payment again with a new transfer line on that bill, then assign the transaction to the new line.

## Extra billiard screens

These do not touch payment, but they sit on the same table and session screens.

### 7. Scoreboard (games inside a session)

A running session can have games, and each game keeps a score for player A and player B. Only one game can be active in a session at a time.

| Action | Call | Notes |
| --- | --- | --- |
| List the games | `GET /sessions/{id}/games` | `Game[]` |
| Start a game | `POST /sessions/{id}/games` (no body, `201`) | `409 Games can only be started in an active session` once the session is stopped, `409 Session already has an active game` if one is running |
| Change a score | `POST /games/{game_id}/score` with `{"player": "A", "delta": 1}` | `delta` is -10 to 10 and never 0. `409 Score cannot go below 0` |
| Reset the score | `POST /games/{game_id}/reset` | Back to 0 to 0 |
| Next game | `POST /games/{game_id}/new` | Completes this game and opens the next at 0 to 0. The session and its billing timer are not touched. Returns `{finished, started}` |
| Finish | `POST /games/{game_id}/finish` | Completes this game without starting another |

Use `+1` and `-1` buttons. Replace the game in your list with the one the server returns, and never add to the score locally. Games can be changed only while the game and the session are active (`409 Session is not active` or `409 Game is not active` otherwise), so on `409` reload the list.

The table controller (the physical scoreboard) can change scores and start games too, so the score you see may change between refreshes. Always redraw from the server's response, and reload the games list when you open the scoreboard.

### 8. Pricing rules and price quote

The table fee on the bill comes from the pricing rules; the bill shows the rule that applied in `pricing_rule_name` and `pricing_params`. The rule is chosen once, when the session starts, and stays fixed for that session, so a session that runs past the end of a happy-hour window keeps the happy-hour price.

- `GET /billiard/pricing-rules` lists the rules. Any logged-in user can read them. Managers create (`POST`), change (`PUT /{rule_id}`) and delete (`DELETE /{rule_id}`) them. Deleting or editing a rule never changes an existing bill.
- A rule has a `rule_type`: `per_minute`, `hourly`, `block` (set `params.block_minutes`, 1 to 1440) or `minimum_hour` (set `params.min_minutes`, 1 to 1440). Other `params` keys are dropped by the server.
- A rule can be limited to one `table_id`, to days (`days_of_week` such as `"sat,sun"`) and to a time window. `start_time` and `end_time` must be sent together. When several rules match, the highest `priority` wins, and a rule for one specific table beats an all-tables rule of the same priority.
- `GET /billiard/pricing-rules/quote?table_id=1&minutes=90` answers "what would 90 minutes cost now" and writes nothing. Use it for a price preview on the table tile. `at` is optional; unlike other timestamps, a time without an offset in `at` means the club's local time, not UTC.

### 9. Manager set-up and report

- `POST /tables` with `{"name": "T05", "hourly_rate": 100000}` adds a table (managers only, `201`). The name is 1 to 50 characters and the rate must be above 0. `409` if the club already has a table with that name.
- `PATCH /tables/{id}` with `{"name": "T05 VIP"}` and/or `{"hourly_rate": 120000}` edits a table (managers only). Send only the fields you change. `409` if the new name is taken. A new rate applies to **new** sessions only; a running session and old bills keep the rate they started with.
- `DELETE /tables/{id}` **deactivates** a table (managers only); it does not erase it, so history and reports stay. It returns `{"message": "Billiard table deactivated successfully", "id": 5, "is_active": false}`. `409` if the table has a running session (stop it first) or is already inactive. Ask for confirmation before you call it, and drop the table from the board afterwards. There is no endpoint to reactivate a table yet.
- `POST /tables/{id}/reserve`, `POST /tables/{id}/maintenance` and `POST /tables/{id}/release` (managers only, no body) change a free table's status and return the `Table`. Rules: `reserve` works only on an `available` table, `maintenance` on an `available` or `reserved` one (a broken reserved table can go straight to maintenance), and `release` only on a `reserved` or `maintenance` one. A `playing` table is always `409` ("Table is playing, stop its session first"); any other wrong status is `409` too (the message says the current status). It is a status only: the table shows `reserved` or `maintenance` on the board and cannot be started until it is released.
- `GET /reports/tables/usage?start_date=...&end_date=...` returns one row per table and a `totals` row. The dates filter on the session's end time and are read in the club's time zone; a date-only `end_date` includes that whole day. Revenue columns count paid sessions only, `discount_total` is the discounts on those paid sessions (`table_revenue + product_revenue - discount_total = total_revenue`), and `unpaid_total` is money for sessions that were stopped but not yet paid.

### 10. Controller devices (manager)

The club's physical scoreboards are run by one central controller (ESP32). A manager can see whether it is online and register it. Everything else about the controller is done by the device itself.

| Action | Call | Notes |
| --- | --- | --- |
| List controllers | `GET /billiard/controller/status` | `ControllerDevice[]`. `status` is `online`, `offline`, `syncing` or `error`. A controller that has been silent for 90 seconds shows `offline`. `last_error` / `last_error_at` hold the latest fault it reported (`null` if none): show it as a warning with the time |
| Find devices to register | `GET /billiard/controller/hydro-candidates` | Existing devices of the club that are not yet a controller, so the manager can pick one instead of typing an id |
| Register | `POST /billiard/controller/register` with `{"device_id": "BILLIARD-CONTROLLER-01", "name": "Main hall"}` or `{"hydro_device_id": 3}` | `201`. Returns the device **and its `api_key`, shown once**. `409` if the id is already registered, `404` if the hydro device is not found, `422` if neither `device_id` nor `hydro_device_id` is sent |

Show the `api_key` in a dialog with a copy button and a clear warning that it cannot be shown again, because only a hash is stored. Never keep it in local storage or logs. Show `last_seen` as "x minutes ago" and highlight an `offline` controller, because while it is offline the physical boards keep working but the POS sees changes only after it reconnects and syncs.

### 11. Bank account set-up (manager)

Each club saves the account its transfer QR pays into. Show this screen to managers and admins only (a cashier gets `403` on everything except `GET /payments/bank-accounts/current`).

| Action | Call | Notes |
| --- | --- | --- |
| Show the current account | `GET /payments/bank-accounts/current` | `BankAccount` or `null`. Any logged-in user can call it, so a cashier screen can show "Paying to: CLUB A, ****6789" |
| Read a QR image | `POST /payments/bank-accounts/parse-qr`, multipart form with one field `file` (PNG or JPG, max 5 MB) | Returns `{bank_bin, account_no, amount, memo}`. **Saves nothing.** Prefill the form with it |
| Save | `POST /payments/bank-accounts` with `{"bank_bin": "970436", "account_no": "0123456789", "account_name": "CLUB A", "bank_code": "VCB"}` | `201`. Replaces the active account; the old one goes to history |
| Correct the name | `PATCH /payments/bank-accounts/{id}` with `{"account_name": "...", "bank_code": "..."}` | Bank and account number cannot be edited: save a new account instead |
| Turn off | `POST /payments/bank-accounts/{id}/deactivate` | Transfers then show no QR until a new account is saved. Ask for confirmation first |
| History | `GET /payments/bank-accounts` and `GET /payments/bank-accounts/events` | Newest first |

Build the form like this:

1. Two ways in: an **Upload QR image** button and the plain fields. Both end at the same form.
2. After an upload, fill `bank_bin` and `account_no` from the response and leave `account_name` empty. The QR does not carry the holder name, so the manager must type it. Ignore `amount` and `memo`: they are only present when the picture was a payment QR, and they are not saved.
3. Show a clear summary before saving ("Account 0123456789, bank 970436, holder CLUB A") and say that new transfers will pay this account.
4. After saving, reload `current` and show the account. Do not store it in local storage.

Handle the errors in the form: `422` for a bad field or a QR that is not an account QR (show the message and keep the typed fields), `409` when the account is already used by another club, `413` for a large image (check the size in the browser first), and `501` when the server cannot read QR images (hide the upload button after the first `501` and keep typing).

### 12. Packages (manager)

A package is a fixed price for a number of minutes of table time, with some products included free (for example "2 hours, 150,000, 2 beers"). The package price covers table time only; products are charged separately except the included ones, and time beyond the duration is billed by the normal rule (see "Packages" in the README).

- List with `GET /billiard/packages?include_inactive=true`; show inactive rows greyed out with a Reactivate button (`PUT` with `{"is_active": true}`).
- The form has `name`, `duration_minutes` (1 to 1440), `price` (0 or more, 2 decimals) and a product list. Build the product list from `GET /products`, only products with `is_active`, and each product once.
- Save with `POST` (new) or `PUT` (change). On `PUT`, send `items` only when the list changed: a list replaces all items, omitting it keeps them.
- Errors: `409` name already used in this club (inactive packages keep their name), `400` a product is missing or inactive (reload the menu), `422` a bad value, `403` for staff.
- "Delete" calls `DELETE`, which only deactivates. Old bills are not affected.

### 13. Billing review (cashier)

When a controller starts a table with a package the server cannot apply, the session still opens (the game is real) and is flagged. Show it in three places:

- **Board:** a badge on tiles with `needs_billing_review: true` and the reason (`billing_review_reason`). Poll `GET /tables/active` as usual; there is no push yet.
- **List:** `GET /sessions/billing-review` returns the sessions that still need a decision (`session_id`, `table_name`, `requested_package_id`, `reason`, `grand_total`).
- **Bill:** while `needs_billing_review` is true, hide Pay (the server answers `409 Billing review required before payment`) and show **Resolve**.

Resolve offers two choices, both through `POST /sessions/{id}/billing-review`:

1. **Assign a package:** pick from `GET /billiard/packages` and send `{"action": "assign_package", "package_id": 3}`. The server applies the package, turns the units of included products that were already added into free ones, recomputes the fee if the session is stopped, and returns the new `Bill`. Redraw from it.
2. **Confirm normal pricing:** send `{"action": "confirm_normal_pricing", "note": "Customer did not buy a package"}`. The note is required (3 to 255 characters) and is kept for audit. Amounts do not change.

Any logged-in user of the club can resolve it. After it is resolved show who decided and when (`billing_reviewed_by`, `billing_reviewed_at`, `billing_review_resolution`, `billing_review_note`) and keep `requested_package_id` visible as history. Errors: `409` already resolved, payment already started, or the session was cancelled; `400` the package is inactive; `404` the package or session is not found; `422` a missing package id or note.

## State to UI rules

Decide what to render from the bill alone: `payment_state`, `payment_method`, `amount_paid`, `balance_due` and `payments[]`. Do not keep your own copy of the payment state; redraw from each response.

### Which screen for which bill

| `payment_state` | What the bill looks like | Show |
| --- | --- | --- |
| `unpaid` | No lines | Pay screen for the full `grand_total` |
| `pending` | A line with `method: "bank_transfer"`, `status: "pending"` | Transfer waiting (screen 2), and poll |
| `pending` | No waiting line and `amount_paid > 0` | Pay screen for `balance_due` (part paid) |
| `pending` | `payment_method: "stripe"` and no lines | Card form, then the confirm call |
| `paid` | Any | Receipt |

A bill can go from `paid` back to `pending` or `unpaid` when a manager voids a line, and from `pending` back to `unpaid` when a waiting transfer is cancelled (by a person or by the server), so always handle every row, not only the forward path.

### Payment line status

| `status` | Show | Actions |
| --- | --- | --- |
| `pending` | Waiting badge, plus the QR for a transfer | Received, Cancel |
| `completed` | Paid badge | Void (managers only) |
| `cancelled` | Greyed, labelled cancelled. The `note` says why, for example "Transfer not received in time" | None |
| `voided` | Greyed, with `voided_at` and `void_reason` | None |
| `failed` | Red error badge, "could not be recorded" | None. Tell the cashier to pay the balance again |

Cash lines are `completed` as soon as they are created, so a pending cash line only appears if something failed.

### Bank transaction status

| `status` | Meaning | Actions |
| --- | --- | --- |
| `needs_review` | A code was found but the amount differs, the line was already paid, the line was cancelled or voided, or the money arrived on a different account than the QR showed. Read `reason` | Assign, Ignore |
| `unmatched` | No code, or an unknown code | Assign, Ignore |
| `matched` | It settled a line. `order_id` and `line_id` are set | None |
| `ignored` | Outgoing transfer, an account no club has saved, or dismissed. Read `note` | None |

### Who sees which buttons

| Action | Allowed for |
| --- | --- |
| Pay, Cancel a waiting line, open shift, pay-in or pay-out | Any logged-in user of the club |
| Received (confirm a transfer by hand) | Any logged-in user of the club, unless the club limits it to managers; the club may also require a note |
| Scoreboard (start a game, change score, reset, new game, finish) | Any logged-in user of the club |
| Price quote, list pricing rules | Any logged-in user of the club |
| List or read packages | Any logged-in user of the club |
| Create, change or deactivate a package | Manager or admin |
| Void a line | Manager or admin |
| List, assign or ignore bank transactions, list pending transfer lines | Manager or admin |
| Save, correct or turn off the club's bank account, read its history, upload a QR image | Manager or admin |
| Read the current bank account | Any logged-in user of the club |
| Create, edit or deactivate a table, create, change or delete a pricing rule, table usage report | Manager or admin |
| List, register controller devices | Manager or admin |
| Close a shift | The user who opened it, or a manager |

`GET /auth/me` returns `roles`, so decide from it. Role names are `super_admin`, `admin`, `manager`, `moderator` and `user`. The server always lets a `super_admin` through, so treat `super_admin`, `admin` and `manager` as managers:

```ts
const MANAGER_ROLES = ["super_admin", "admin", "manager"];
const isManager = (me: Me) => me.roles.some(r => MANAGER_ROLES.includes(r.name));
```

Use it only to hide buttons. The server enforces every rule, so a `403` can still happen (for example a role change while the app is open). Turn it into the message "Only a manager can do this".

## TypeScript types

These match the backend response models. Fields marked `| null` are always present in the JSON, with `null` when empty. If you generate types from `/openapi.json`, prefer those and use this section as a cross-check.

### Shared

```ts
type Money = string;                 // "310000.00" (Decimal as string, VND has no decimals)
type ISODate = string;               // no offset means UTC: append "Z"

type PaymentState = "unpaid" | "pending" | "paid";
type BillPaymentMethod = "cash" | "bank_transfer" | "stripe" | "split";
type LineMethod = "cash" | "bank_transfer";
type LineStatus = "pending" | "completed" | "cancelled" | "voided" | "failed";

interface TransferInstruction {      // only on a pending bank_transfer line
  bank_code: string | null;          // can be null even when the QR works (the club saved only the BIN)
  account_no: string | null;
  account_name: string | null;
  amount: Money;
  memo: string;                      // e.g. "PAY7L2"
  qr_payload: string | null;         // draw as a QR code; null if the club has no bank account saved
  qr_image_url: string | null;       // hosted QR image fallback
  expires_at: ISODate | null;
}

interface PaymentLine {
  id: number;
  method: LineMethod;
  amount: Money;
  status: LineStatus;
  cash_tendered: Money | null;       // cash only
  change_given: Money | null;        // cash only
  payment_reference: string | null;
  note: string | null;               // e.g. the confirmation note, or "Transfer not received in time"
  confirmed_at: ISODate | null;
  voided_at: ISODate | null;
  void_reason: string | null;
  transfer: TransferInstruction | null;
}
```

### Tables, menu and items

```ts
type TableStatus = "available" | "playing" | "reserved" | "maintenance";

interface Role {                     // inside GET /auth/me
  id: number;
  name: string;                      // "super_admin" | "admin" | "manager" | "moderator" | "user"
  display_name: string;
  description: string | null;
  is_active: boolean;
  permissions: string[] | null;
  is_system_role: boolean;
  created_at: ISODate;
  updated_at: ISODate | null;
}
interface Me {                       // GET /auth/me (only the fields the screens use)
  id: number;
  username: string;
  client_id: string | null;
  roles: Role[];
}

interface Table {                    // GET /tables (active tables only)
  id: number;
  name: string;
  status: TableStatus;
  hourly_rate: Money;
}

interface ActiveTable {              // GET /tables/active (only tables being played)
  id: number;
  name: string;
  status: TableStatus;
  session_id: number;
  start_time: ISODate;
  elapsed_minutes: number;
  hourly_rate: Money;
  current_table_fee: Money;          // running estimate, for display only
  current_product_fee: Money;
  ends_at: ISODate | null;           // timed play only
  remaining_seconds: number | null;  // negative once past ends_at; null for open play
  is_overtime: boolean;              // flag only: the server never stops a session by itself
  package_name: string | null;       // session started with a package
  overtime_minutes: number | null;   // minutes beyond the package so far
  needs_billing_review: boolean;     // controller asked for a package the server could not apply
  requested_package_id: number | null;
  billing_review_reason: string | null;
  current_discount: Money;           // 0 when there is no discount
  current_total: Money;              // table fee + products - discount
}

interface StartSessionResponse {     // POST /tables/{id}/start
  session_id: number;
  table_id: number;
  start_time: ISODate;
  ends_at: ISODate | null;           // null for open play
  opened_by: string;
}

interface ProductVariant {
  id: number;
  name: string;
  sku: string | null;
  price: number;                     // note: a number here, not a Money string
  stock: number;
}
interface Product {                  // GET /products (no login needed)
  id: number;
  name: string;
  description: string | null;
  base_price: number;
  sku: string | null;
  is_active: boolean;
  image_url: string | null;
  variants: ProductVariant[];
}

interface AddItemRequest {           // POST /sessions/{id}/items
  product_id: number;
  variant_id?: number | null;
  quantity: number;                  // 1 to 1000
}

interface CreateTableRequest { name: string; hourly_rate: number }   // POST /tables (manager); name 1-50 chars, rate > 0
interface UpdateTableRequest {                                       // PATCH /tables/{id} (manager); send only changed fields
  name?: string;                     // 1 to 50 characters
  hourly_rate?: number;              // above 0
}
interface DeactivateTableResponse {  // DELETE /tables/{id} (manager)
  message: string;                   // "Billiard table deactivated successfully"
  id: number;
  is_active: boolean;                // false
}
```

### Scoreboard, pricing and report

```ts
type GameStatus = "active" | "completed" | "cancelled";
interface Game {                     // /sessions/{id}/games and /games/{id}/...
  id: number;
  session_id: number;
  game_number: number;
  start_time: ISODate;
  end_time: ISODate | null;
  player_a_score: number;
  player_b_score: number;
  status: GameStatus;
}
interface ScoreChangeRequest { player: "A" | "B"; delta: number }   // -10 to 10, not 0
interface NewGameResponse { finished: Game; started: Game }

type PricingRuleType = "per_minute" | "hourly" | "block" | "minimum_hour";
interface PricingRule {              // GET /billiard/pricing-rules
  id: number;
  name: string;
  rule_type: PricingRuleType;
  hourly_rate: Money | null;
  params: Record<string, unknown> | null;   // block: { block_minutes }, minimum_hour: { min_minutes }
  table_id: number | null;           // null = every table
  days_of_week: string | null;       // "sat,sun"; null = every day
  start_time: string | null;         // "18:00:00"; sent together with end_time
  end_time: string | null;
  priority: number;                  // 0 to 1000
  is_active: boolean;
  created_at: ISODate;
}
interface PricingRuleRequest {       // POST (all needed fields) and PUT (any field)
  name: string;                      // 1 to 100 characters
  rule_type: PricingRuleType;
  hourly_rate?: number;              // above 0
  params?: Record<string, unknown>;
  table_id?: number | null;
  days_of_week?: string | null;      // mon,tue,wed,thu,fri,sat,sun
  start_time?: string | null;
  end_time?: string | null;
  priority?: number;
  is_active?: boolean;
}
interface PackageItem {
  product_id: number;
  product_name: string | null;
  included_quantity: number;         // units given free
}
interface Package {                  // GET /billiard/packages, GET/PUT/DELETE /billiard/packages/{id}
  id: number;
  name: string;                      // unique per club
  duration_minutes: number;          // 1 to 1440
  price: Money;                      // covers table time only
  is_active: boolean;
  items: PackageItem[];
  created_at: ISODate | null;
}
interface PackageRequest {           // POST (all of name, duration_minutes, price); PUT (all optional)
  name: string;
  duration_minutes: number;
  price: Money;
  items?: { product_id: number; included_quantity: number }[];   // PUT: a list REPLACES, omit to keep
  is_active?: boolean;
}

interface PricingQuote {             // GET /billiard/pricing-rules/quote
  table_id: number;
  at: ISODate;
  minutes: number;
  rule_id: number | null;
  rule_name: string | null;
  rule_type: string;
  hourly_rate: Money;
  params: Record<string, unknown>;
  package_id: number | null;         // only when the request had package_id
  package_name: string | null;
  package_price: Money | null;
  package_minutes: number | null;
  overtime_minutes: number | null;
  fee: Money;                        // table time only (package price + overtime with a package)
}

interface TableUsageRow {
  table_id: number;
  table_name: string;
  times_played: number;
  total_minutes: number;
  table_revenue: Money;              // paid sessions only
  product_revenue: Money;            // paid sessions only
  total_revenue: Money;              // paid sessions only
  unpaid_total: Money;               // stopped but not yet paid
  discount_total: Money;             // discounts on paid sessions; table_revenue + product_revenue - discount_total = total_revenue
}
interface TableUsageReport {         // GET /reports/tables/usage
  period_start: ISODate | null;
  period_end: ISODate | null;
  rows: TableUsageRow[];
  totals: TableUsageRow;
}
```

### Controller devices (manager)

```ts
type DeviceStatus = "online" | "offline" | "syncing" | "error";

interface ControllerDevice {         // GET /billiard/controller/status
  device_id: string;
  name: string;
  status: DeviceStatus;              // "offline" after 90 seconds without a request
  firmware_version: string | null;
  last_seen: ISODate | null;
  last_applied_seq: number;          // highest contiguous device event the server applied
  last_error: string | null;         // latest device_error, "code: message"
  last_error_at: ISODate | null;     // when the server received it
}

interface HydroCandidate {           // GET /billiard/controller/hydro-candidates
  hydro_device_id: number;
  device_id: string;
  name: string;
  location: string | null;
}

interface RegisterControllerRequest {          // POST /billiard/controller/register; send device_id or hydro_device_id
  device_id?: string;                // max 64 characters
  hydro_device_id?: number;          // copies the id and name from that device
  name?: string;                     // max 100 characters
}
interface RegisterControllerResponse extends ControllerDevice {
  api_key: string;                   // shown ONCE; only a hash is stored
}
```

### Billiard bill

```ts
interface AddItemResponse extends SessionItem {   // POST /sessions/{id}/items
  lines: SessionItem[];              // every line this call created: one, or two (free first, then paid)
}

interface SessionItem {
  id: number;
  product_id: number | null;
  variant_id: number | null;
  product_name: string;
  quantity: number;
  unit_price: Money;
  total_price: Money;
  from_package: boolean;             // free units included by the package (unit_price 0)
}

interface BillingReviewItem {        // GET /sessions/billing-review
  session_id: number; table_id: number; table_name: string; status: string; start_time: ISODate;
  requested_package_id: number | null; reason: string | null; grand_total: Money;
}
type BillingReviewRequest =          // POST /sessions/{id}/billing-review
  | { action: "assign_package"; package_id: number }
  | { action: "confirm_normal_pricing"; note: string };   // note: 3 to 255 characters

interface Bill {                     // GET /sessions/{id}, /stop, and every /pay... response
  session_id: number;
  table_id: number;
  table_name: string;
  currency: string;                  // "VND"
  status: "active" | "completed" | "cancelled";
  start_time: ISODate;
  ends_at: ISODate | null;           // timed play countdown target
  end_time: ISODate | null;
  duration_minutes: number | null;
  hourly_rate: Money;
  billing_policy: string;            // per_minute | hourly | block | minimum_hour (old bills: rounded_hour)
  pricing_rule_name: string | null;
  pricing_params: Record<string, unknown>;
  package_name: string | null;       // session started with a package
  package_price: Money | null;
  package_minutes: number | null;
  overtime_minutes: number | null;   // beyond the package, billed by the rule; null until stopped
  needs_billing_review: boolean;     // true: payment is blocked until resolved
  requested_package_id: number | null;   // what the controller asked for (history, never overwritten)
  billing_review_reason: string | null;
  billing_review_resolution: "assign_package" | "confirm_normal_pricing" | null;
  billing_review_note: string | null;
  billing_reviewed_by: string | null;
  billing_reviewed_at: ISODate | null;
  total_table_fee: Money;
  total_product_fee: Money;
  discount: Money;                   // amount taken off (table fee + products); 0 = none
  discount_percent: Money | null;    // set when it was given as a percent
  discount_reason: string | null;
  discounted_by: string | null;
  grand_total: Money;                // table fee + products - discount
  items: SessionItem[];
  payment_state: PaymentState;
  payment_method: BillPaymentMethod | null;
  payment_reference: string | null;
  paid_at: ISODate | null;
  amount_paid: Money;                // sum of completed lines
  balance_due: Money;                // grand_total - amount_paid
  payments: PaymentLine[];
  opened_by: string | null;          // null when the table controller started the session
  stopped_by: string | null;         // null when the table controller stopped it
  paid_by: string | null;            // null = confirmed by the bank feed (or not paid)
  cancelled_at: ISODate | null;      // only when status = "cancelled"
  cancelled_by: string | null;
  cancel_reason: string | null;
}

interface PayResponse extends Bill {  // POST /sessions/{id}/pay
  gateway: Record<string, unknown> | null;   // Stripe: { client_secret, ... }
}
```

### Pay requests

```ts
interface PayOne {
  payment_method: "cash" | "bank_transfer" | "stripe";
  cash_tendered?: number;            // only with payment_method "cash"
}
interface SplitLine {
  method: LineMethod;
  amount: number;                    // > 0
  cash_tendered?: number;            // cash only
  note?: string;                     // max 255
}
interface PaySplit { payments: SplitLine[] }   // 1 to 6 lines, must add up to balance_due

type PayRequest = PayOne | PaySplit;           // never both

interface ConfirmLineRequest { note?: string }             // max 255. Required (3+ chars) when the club turns that rule on
interface CancelLineRequest { reason?: string }            // max 255
interface VoidLineRequest { reason: string }               // 3 to 255 characters
```

### Generic order and audit trail

```ts
interface Order {                    // GET /payments/orders/{source_type}/{source_id}
  source_type: string;
  source_id: string;
  order_id: number | null;           // null until the first payment attempt
  currency: string;
  total: Money;
  state: PaymentState;
  method: BillPaymentMethod | null;
  paid_at: ISODate | null;
  amount_paid: Money;
  balance_due: Money;
  payments: PaymentLine[];
}
interface PayOrderResponse extends Order { gateway: Record<string, unknown> | null }

type EventType =
  | "line_created" | "cash_received" | "transfer_awaiting" | "transfer_confirmed"
  | "transfer_auto_confirmed" | "transfer_assigned_from_bank"
  | "line_cancelled" | "line_expired" | "line_failed" | "line_voided" | "order_paid";

interface PaymentEvent {             // GET /sessions/{id}/pay/events
  id: number;
  line_id: number | null;
  event_type: EventType;             // "line_expired" = the server cancelled a transfer that never arrived (actor_id is null)
  actor_id: number | null;           // null = the system (e.g. the bank feed or the expiry job)
  data: Record<string, unknown> | null;
  created_at: ISODate;
}
```

### Shifts

```ts
interface Shift {                    // GET /payments/shifts (list)
  id: number;
  status: "open" | "closed";
  opened_at: ISODate;
  closed_at: ISODate | null;
  opening_float: Money;
  expected_cash: Money | null;       // frozen at close; live value is in ShiftSummary
  counted_cash: Money | null;
  variance: Money | null;            // counted - expected; negative = cash missing
  note: string | null;
  close_note: string | null;
  opened_by: string | null;
  closed_by: string | null;
}

interface MethodTotals {
  method: string;
  received_count: number;
  received_total: Money;
  voided_total: Money;
  net_total: Money;
}
interface CashMovement {
  id: number;
  type: "pay_in" | "pay_out";
  amount: Money;
  reason: string;
  created_by: string | null;
  created_at: ISODate;
}

interface ShiftSummary extends Shift {        // open, /current, /{id}, /movements, /close
  cash_sales: Money;
  cash_voids: Money;
  pay_ins: Money;
  pay_outs: Money;
  change_given: Money;               // informational: already netted out of cash_sales
  payments_count: number;
  methods: MethodTotals[];
  movements: CashMovement[];
}

interface OpenShiftRequest { opening_float?: number; note?: string }       // float >= 0
interface MovementRequest { type: "pay_in" | "pay_out"; amount: number; reason: string }  // reason 3 to 255
interface CloseShiftRequest { counted_cash: number; note?: string }       // >= 0
```

### Bank account

```ts
interface BankAccount {              // GET /payments/bank-accounts/current (or null)
  id: number;
  client_id: string;                 // UUID string
  bank_bin: string;                  // 6 digits
  bank_code: string | null;          // e.g. "VCB"
  account_no: string;
  account_name: string;
  is_active: boolean;
  created_at: ISODate;
}

interface BankAccountCreate {        // POST /payments/bank-accounts
  bank_bin: string;                  // exactly 6 digits
  account_no: string;                // 4 to 32 letters or digits
  account_name: string;              // 2 to 100 characters
  bank_code?: string | null;         // max 20
}

interface BankAccountRename { account_name: string; bank_code?: string | null }

interface ParsedBankQr {             // POST /payments/bank-accounts/parse-qr (nothing is saved)
  bank_bin: string;
  account_no: string;
  amount: number | null;             // only when the picture was a payment QR; ignore it
  memo: string | null;
}

interface BankAccountEvent {         // GET /payments/bank-accounts/events (managers)
  id: number;
  account_id: number | null;
  event_type: "account_created" | "account_replaced" | "account_renamed" | "account_deactivated";
  actor_id: number | null;
  data: Record<string, unknown> | null;
  created_at: ISODate;
}
```

### Bank feed

```ts
type BankTxStatus = "matched" | "unmatched" | "needs_review" | "ignored";

interface BankTransaction {
  id: number;
  provider: string;                  // "sepay"
  external_id: string;
  gateway: string | null;            // bank name
  account_number: string | null;
  transfer_type: string | null;      // "in" | "out"
  amount: Money;
  content: string | null;            // the transfer note as the bank sent it
  code: string | null;
  reference_code: string | null;
  transaction_date: ISODate | null;
  status: BankTxStatus;
  reason: string | null;             // why it needs review or is unmatched
  order_id: number | null;
  line_id: number | null;
  handled_by_id: number | null;
  handled_at: ISODate | null;
  note: string | null;
  created_at: ISODate;
}

interface PendingTransferLine {      // GET /payments/bank-feed/pending-lines (managers)
  line_id: number;
  order_id: number;
  source_type: string;               // "billiard_session"
  source_id: string;                 // the session id for billiard
  amount: Money;
  currency: string;
  order_total: Money;
  transfer_memo: string | null;
  created_at: ISODate;
  expires_at: ISODate | null;
  expired: boolean;                  // the QR has expired; the line is still payable until the server cancels it
}

interface AssignRequest { line_id: number }
interface IgnoreRequest { note?: string }      // max 255
```

## Calls

One small client is enough. It adds the token, sends JSON, and turns every failure into an `ApiError` carrying the status code and the server's message.

### Client

```ts
const BASE = import.meta.env.VITE_API_URL;   // your API origin
let token: string | null = null;

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    // HTTPException: detail is a string. Request validation (422): detail is a list of { loc, msg }.
    const msg = typeof err.detail === "string"
      ? err.detail
      : Array.isArray(err.detail) ? err.detail.map((d: any) => d.msg).join("; ") : res.statusText;
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;       // GET /payments/shifts/current can be null
}

export async function login(username: string, password: string) {
  const res = await fetch(BASE + "/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username, password }),   // form data, not JSON
  });
  if (!res.ok) throw new ApiError(res.status, "Invalid credentials");
  token = (await res.json()).access_token;
}
```

### Endpoints

```ts
export const api = {
  tables:       () => request<Table[]>("GET", "/tables"),
  activeTables: () => request<ActiveTable[]>("GET", "/tables/active"),
  startTable:   (tableId: number, opts?: { planned_minutes?: number; package_id?: number }) =>   // not both
    request<StartSessionResponse>("POST", `/tables/${tableId}/start`, opts),
  extendSession: (id: number, minutes: number) => request<Bill>("POST", `/sessions/${id}/extend`, { minutes }),
  products:     () => request<Product[]>("GET", "/products"),
  addItem:      (id: number, b: AddItemRequest) => request<AddItemResponse>("POST", `/sessions/${id}/items`, b),
  billingReviews: () => request<BillingReviewItem[]>("GET", "/sessions/billing-review"),
  resolveBillingReview: (id: number, b: BillingReviewRequest) => request<Bill>("POST", `/sessions/${id}/billing-review`, b),

  bill:  (id: number) => request<Bill>("GET", `/sessions/${id}`),
  stop:  (id: number) => request<Bill>("POST", `/sessions/${id}/stop`),

  pay:   (id: number, body: PayRequest) => request<PayResponse>("POST", `/sessions/${id}/pay`, body),
  confirmCard: (id: number) => request<Bill>("POST", `/sessions/${id}/pay/confirm`),

  // note is optional, but send it whenever the cashier typed one: the club may require it (422 without)
  confirmLine: (id: number, lineId: number, note?: string) =>
    request<Bill>("POST", `/sessions/${id}/pay/lines/${lineId}/confirm`, note ? { note } : undefined),
  cancelLine: (id: number, lineId: number, reason?: string) =>
    request<Bill>("POST", `/sessions/${id}/pay/lines/${lineId}/cancel`, reason ? { reason } : undefined),
  voidLine: (id: number, lineId: number, reason: string) =>      // manager only
    request<Bill>("POST", `/sessions/${id}/pay/lines/${lineId}/void`, { reason }),
  events: (id: number) => request<PaymentEvent[]>("GET", `/sessions/${id}/pay/events`),

  currentShift: () => request<ShiftSummary | null>("GET", "/payments/shifts/current"),
  shifts: (limit = 30, offset = 0) => request<Shift[]>("GET", `/payments/shifts?limit=${limit}&offset=${offset}`),
  shift: (id: number) => request<ShiftSummary>("GET", `/payments/shifts/${id}`),
  openShift: (b: OpenShiftRequest) => request<ShiftSummary>("POST", "/payments/shifts/open", b),
  moveCash: (id: number, b: MovementRequest) => request<ShiftSummary>("POST", `/payments/shifts/${id}/movements`, b),
  closeShift: (id: number, b: CloseShiftRequest) => request<ShiftSummary>("POST", `/payments/shifts/${id}/close`, b),

  me: () => request<Me>("GET", "/auth/me"),

  games:       (sessionId: number) => request<Game[]>("GET", `/sessions/${sessionId}/games`),
  startGame:   (sessionId: number) => request<Game>("POST", `/sessions/${sessionId}/games`),
  changeScore: (gameId: number, b: ScoreChangeRequest) => request<Game>("POST", `/games/${gameId}/score`, b),
  resetScore:  (gameId: number) => request<Game>("POST", `/games/${gameId}/reset`),
  newGame:     (gameId: number) => request<NewGameResponse>("POST", `/games/${gameId}/new`),
  finishGame:  (gameId: number) => request<Game>("POST", `/games/${gameId}/finish`),

  pricingRules: () => request<PricingRule[]>("GET", "/billiard/pricing-rules"),
  quote: (tableId: number, minutes: number, at?: string, packageId?: number) =>
    request<PricingQuote>("GET", `/billiard/pricing-rules/quote?table_id=${tableId}&minutes=${minutes}${at ? `&at=${encodeURIComponent(at)}` : ""}${packageId ? `&package_id=${packageId}` : ""}`),
  createRule: (b: PricingRuleRequest) => request<PricingRule>("POST", "/billiard/pricing-rules", b),             // manager
  packages: (includeInactive = false) => request<Package[]>("GET", `/billiard/packages${includeInactive ? "?include_inactive=true" : ""}`),
  package: (id: number) => request<Package>("GET", `/billiard/packages/${id}`),
  createPackage: (b: PackageRequest) => request<Package>("POST", "/billiard/packages", b),                          // manager
  updatePackage: (id: number, b: Partial<PackageRequest>) => request<Package>("PUT", `/billiard/packages/${id}`, b),   // manager
  deactivatePackage: (id: number) => request<Package>("DELETE", `/billiard/packages/${id}`),                         // manager
  updateRule: (id: number, b: Partial<PricingRuleRequest>) => request<PricingRule>("PUT", `/billiard/pricing-rules/${id}`, b),  // manager
  createTable: (b: CreateTableRequest) => request<Table>("POST", "/tables", b),                                  // manager
  updateTable: (id: number, b: UpdateTableRequest) => request<Table>("PATCH", `/tables/${id}`, b),               // manager
  deactivateTable: (id: number) => request<DeactivateTableResponse>("DELETE", `/tables/${id}`),                  // manager
  tableUsage: (startDate?: string, endDate?: string) => {                                                         // manager
    const q = new URLSearchParams();
    if (startDate) q.set("start_date", startDate);
    if (endDate) q.set("end_date", endDate);
    const qs = q.toString();
    return request<TableUsageReport>("GET", `/reports/tables/usage${qs ? `?${qs}` : ""}`);
  },

  controllers:      () => request<ControllerDevice[]>("GET", "/billiard/controller/status"),                       // manager
  hydroCandidates:  () => request<HydroCandidate[]>("GET", "/billiard/controller/hydro-candidates"),               // manager
  registerController: (b: RegisterControllerRequest) =>                                                           // manager
    request<RegisterControllerResponse>("POST", "/billiard/controller/register", b),

  bankTransactions: (status?: BankTxStatus, limit = 50, offset = 0) => {   // manager only
    const q = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) q.set("status", status);
    return request<BankTransaction[]>("GET", `/payments/bank-feed/transactions?${q}`);
  },
  // Bank account of the club
  bankAccount:        () => request<BankAccount | null>("GET", "/payments/bank-accounts/current"),
  bankAccounts:       () => request<BankAccount[]>("GET", "/payments/bank-accounts"),              // manager
  bankAccountEvents:  () => request<BankAccountEvent[]>("GET", "/payments/bank-accounts/events"),  // manager
  saveBankAccount:    (b: BankAccountCreate) => request<BankAccount>("POST", "/payments/bank-accounts", b),
  renameBankAccount:  (id: number, b: BankAccountRename) =>
    request<BankAccount>("PATCH", `/payments/bank-accounts/${id}`, b),
  deactivateBankAccount: (id: number) =>
    request<BankAccount>("POST", `/payments/bank-accounts/${id}/deactivate`),
  // multipart upload: request() always sends JSON, so this call uses fetch directly.
  // Do not set Content-Type yourself; the browser adds the boundary.
  parseBankQr: async (file: File): Promise<ParsedBankQr> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(BASE + "/payments/bank-accounts/parse-qr", {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new ApiError(res.status, typeof err.detail === "string" ? err.detail : res.statusText);
    }
    return res.json();
  },
  pendingLines: (amount?: number | string, limit = 50, offset = 0) => {    // manager only
    const q = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (amount !== undefined) q.set("amount", String(amount));
    return request<PendingTransferLine[]>("GET", `/payments/bank-feed/pending-lines?${q}`);
  },
  assignTx: (txId: number, lineId: number) =>
    request<BankTransaction>("POST", `/payments/bank-feed/transactions/${txId}/assign`, { line_id: lineId }),
  ignoreTx: (txId: number, note?: string) =>
    request<BankTransaction>("POST", `/payments/bank-feed/transactions/${txId}/ignore`, note ? { note } : undefined),
};
```

### Usage

```ts
// Start a table, add two drinks, stop the session and get the bill
const { session_id } = await api.startTable(1);
await api.addItem(session_id, { product_id: 5, quantity: 2 });
const stopped = await api.stop(session_id);          // stopped.payment_state === "unpaid"

// Cash, customer hands over 500,000 for a 310,000 bill
const bill = await api.pay(42, { payment_method: "cash", cash_tendered: 500000 });
// bill.payment_state === "paid", bill.payments[0].change_given === "190000.00"

// Split: 200,000 cash + 110,000 transfer
const split = await api.pay(42, { payments: [
  { method: "cash", amount: 200000 },
  { method: "bank_transfer", amount: 110000 },
]});
const waiting = split.payments.find(p => p.status === "pending" && p.transfer);
// draw waiting.transfer.qr_payload, then poll api.bill(42)

// Cashier presses Received. Handle the club's manual-confirm rules.
try {
  await api.confirmLine(42, waiting!.id, noteFromInput);
} catch (e) {
  if (e instanceof ApiError && e.status === 422) { /* note required: keep the note box open */ }
  if (e instanceof ApiError && e.status === 403) { /* only a manager may confirm: ask a manager or wait */ }
}

// Manager voids a completed line
await api.voidLine(42, 1, "gave too much change");

// Manager renames a table and deactivates another
await api.updateTable(3, { name: "T03 VIP", hourly_rate: 120000 });
await api.deactivateTable(7);

// Card
const card = await api.pay(42, { payment_method: "stripe" });
// confirm the card with Stripe using card.gateway.client_secret, then:
await api.confirmCard(42);
```

## Polling, errors and edge cases

A transfer can be confirmed by the bank feed (or cancelled by the server) at any moment, so the transfer-waiting screen must refresh itself. Every other failure should reload the bill and redraw it.

### Poll a pending bill

```ts
export function watchBill(id: number, onBill: (b: Bill) => void, ms = 4000) {
  let stopped = false;
  const tick = async () => {
    if (stopped) return;
    if (document.visibilityState === "visible") {
      try {
        const bill = await api.bill(id);
        onBill(bill);
        if (bill.payment_state !== "pending") return;      // paid or released: stop
      } catch (e) {
        if (e instanceof ApiError && (e.status === 401 || e.status === 404)) return;
      }
    }
    setTimeout(tick, ms);
  };
  tick();
  return () => { stopped = true; };                     // call on unmount
}
```

Stop polling when the screen closes, and keep going only while `payment_state` is `pending`. When the poll ends because the bill became `unpaid` (the server cancelled the waiting line), switch the screen back to the pay screen.

### Error handling

The server's `detail` text is readable, but it is English and not a stable code. Branch on the status, show your own headline, and show `detail` underneath.

| Status | Meaning | What the UI does |
| --- | --- | --- |
| `401` | Token missing or expired | Send the user to login |
| `400` | Adding an item that cannot be sold (`Product is not available`, `Variant does not belong to this product`) | Show the message and refresh the menu |
| `403` | Not a manager (void, bank inbox, pending lines, create/edit/deactivate table, pricing rules, usage report, controller devices), or closing someone else's shift, or confirming a transfer by hand when the club limits that to managers (`Only a manager can confirm a transfer manually`) | "Only a manager can do this" |
| `404` | Unknown id, or it belongs to another club | "Not found". Go back to the list |
| `409` | Wrong state. Table: `Table is playing` / `Table is reserved` / `Table is maintenance` / `Table is inactive` / `Table already has an active session` (start); `Table '<name>' already exists` (create or rename); `Cannot deactivate a table with an active session` / `Billiard table is already inactive` (deactivate). Session: "Items can only be added to an active session", "Session is already completed", "Stop the session before paying". Payment: "Already paid", "A payment is already in progress", "This order already has cash/transfer payments; pay the balance with those methods" (card after part payment). Shift: "Open a shift before taking payments", "A shift is already open", a pay-out larger than the drawer. Scoreboard: "Session is not active", "Game is not active", "Games can only be started in an active session", "Session already has an active game", "Score cannot go below 0". Controller: `Device '<id>' is already registered`. Bank account: `This bank account is already in use` | Reload the bill, the board or the shift and redraw. The screen was out of date |
| `422` | Split lines do not add up, cash tendered is below the amount, a void or movement reason is too short, the amount differs on assign, or a manual confirmation needs a note (`A note is required to confirm a transfer manually`), or a bank account field is invalid or the picture is not an account QR | Show the message next to the form. Validate the same rules in the browser first |
| `413` / `501` | Bank-account QR upload: the image is over 5 MB (`413`), or the server has no QR reader installed (`501`) | Check the size before sending. On `501` hide the upload button and let the manager type the account |
| `500` on pay | Some lines could not be recorded | Reload the bill. Show which lines failed and offer to pay `balance_due` again |

### Edge cases

- **Double click.** Disable the pay button while a request is running. A second pay call returns `409`, which you treat as "reload the bill".
- **Account changed while a QR is waiting.** The waiting line keeps the account its QR showed, and the money still matches. Only new lines use the new account. Never redraw an old QR from `GET /payments/bank-accounts/current`; always draw it from the line's `transfer` object.
- **Page reload during a transfer.** The QR data is on the bill (`GET /sessions/{id}`), so rebuild the waiting screen from it. Do not store the QR yourself.
- **QR expired.** `transfer.expires_at` only says when to stop showing the QR as valid. The line stays `pending` for a grace period (60 minutes by default) so a slow bank notification can still match it, so keep both buttons. To start over, cancel and pay again for a new QR.
- **Line cancelled by the server.** After the grace period a background job cancels the line itself: its `status` becomes `cancelled`, its `note` is "Transfer not received in time", and the bill goes back to `unpaid` (or stays `pending` if another part was already paid). If the screen is polling, treat that like any cancelled line and show the pay buttons again. If the customer pays after that, the money appears in the manager inbox as `needs_review` ("Money received for a line that is cancelled"); to apply it, pay again with a new transfer line and assign the transaction to it.
- **Received refused.** A `403` or `422` on Received is a club rule, not a bug. Keep the line `pending`, show the reason and keep polling.
- **Paid, then voided.** A bill can move from `paid` back to `pending` or `unpaid`. Redraw from the response and never assume paid is final.
- **Two cashiers on one bill.** Treat every response as the truth and redraw. Do not merge it with local state.
- **Scores changed by the device.** The physical scoreboard can change scores too. Redraw from each response and reload the games list when the scoreboard opens.
- **Table disappeared.** A manager may have deactivated it. After a `404` or a missing id on the board, reload `GET /tables`.
- **Old paid bills.** A bill that is `paid` with `payments: []` was settled before the payment module. Show it as paid and hide the line list.
- **Automatic confirmation.** A bill can become `paid` with `paid_by: null`. Show "Confirmed automatically by the bank" instead of a cashier name.
- **Session without a cashier name.** `opened_by` or `stopped_by` can be `null` when the table controller acted. Show "Table controller".
- **Amounts.** Convert both sides with `Number()` before comparing, for example `Number(bill.balance_due) === sum`. VND has no decimals, so amounts are whole numbers.
- **Time zones.** Timestamps are UTC. Show them in the club's time zone (the backend default is Asia/Ho\_Chi\_Minh).
- **Stopping twice.** A second stop returns `409 Session is already completed`. Load the bill with `GET /sessions/{id}` and carry on to the pay screen.
- **Transfer counted as paid at once.** If the server has transfer confirmation switched off, a transfer line comes back `completed` and the bill is `paid` with no waiting screen. Always choose the screen from `payment_state` and the lines.
- **Menu is not limited to one club.** `GET /products` needs no login and returns every product, so show only `is_active` ones and let the server be the judge when adding an item.

## Test checklist

Run these on a development backend before release. Use a stopped session with a 310,000 VND bill unless a row says otherwise.

| # | Scenario | Expected result |
| --- | --- | --- |
| 1 | Pay cash with no tendered amount | Bill is `paid`, `change_given` is 0 |
| 2 | Pay cash, tendered 500,000 | Bill is `paid`, change shows 190,000 |
| 3 | Type tendered 100,000 | The button stays disabled. If forced, the server returns `422` and the message is shown |
| 4 | Pay by bank transfer | QR and memo appear, bill is `pending`, the screen refreshes every few seconds |
| 5 | Press Received on the waiting line | Bill is `paid`, the receipt shows |
| 6 | Simulate the bank webhook (see below) while the waiting screen is open | The screen switches to the receipt by itself, and `paid_by` is empty so it says confirmed automatically |
| 7 | Reload the page during a transfer | The waiting screen is rebuilt from the bill with the same QR |
| 8 | Split 200,000 cash + 110,000 transfer | Cash line is paid, bill shows `balance_due` 110,000, the transfer is waiting |
| 9 | Make the split lines add up to the wrong total | Pay stays disabled |
| 10 | Cancel a waiting transfer, then pay the balance in cash | Bill goes back to `unpaid` or part paid, then `paid` |
| 11 | Manager voids a completed line with a reason | Bill reopens and can be paid again |
| 12 | Cashier tries the same void | The user sees "Only a manager can do this" |
| 13 | Open a shift, pay cash, close with the exact counted cash | `variance` is 0 |
| 14 | Close a shift with 10,000 less cash | `variance` is negative and shown in red |
| 15 | Open a shift while one is already open | The `409` message is shown and the open shift is loaded instead |
| 16 | Turn on `PAYMENT_REQUIRE_OPEN_SHIFT` and pay with no shift | The user is sent to open a shift |
| 17 | Webhook with the wrong amount | The manager inbox shows a `needs_review` row with the reason, and the bill stays `pending` |
| 18 | Assign that transaction to a line of a different amount | Blocked in the UI, and the server would return `422` |
| 18a | Open the assign picker for a transaction | It lists only waiting lines of the same amount (`?amount=`), each with its table or session and time |
| 18b | Leave a transfer line unpaid for more than the QR time plus the grace period | The line shows `cancelled` ("Transfer not received in time") and the bill can be paid again; a later transfer lands in `needs_review` |
| 19 | Token expires | The user is sent to login and comes back to the same bill |
| 20 | Open a bill paid before the payment module | It shows as paid with no line list |
| 21 | Double click Pay | One payment is created and no error is shown |
| 22 | Start a table that is already playing | `409 Table is playing` is shown and the board reloads |
| 23 | Add an item after the session is stopped | `409` message is shown, nothing is added |
| 24 | Try to pay a session that is still running | `409 Stop the session before paying`, and the Pay button should not have been shown |
| 25 | Stop the same session twice | The second call returns `409`, and the app shows the bill and the pay screen |
| 26 | Split 200,000 cash + 110,000 transfer, then press Cash on the waiting bill | `409 A payment is already in progress`. No pay buttons are shown while a transfer waits |
| 27 | Pay 100,000 cash, then try Card | `409`, and the Card button is already hidden |
| 28 | Pay out more cash than the drawer holds | `409` message is shown, and the form checks the amount first |
| 29 | Log in as a cashier, then as a manager, and compare `GET /auth/me` | The cashier has no manager buttons (void, bank inbox, reports, table and controller set-up); the manager has them |
| 30 | Scroll the bank inbox past 50 rows | "Load more" fetches the next page with `offset=50` and no row repeats |
| 31 | Start a game, press +1 for A three times, then -1 for B at 0 | A shows 3; the B change returns `409 Score cannot go below 0` and the score stays 0 |
| 32 | Press "Next game" | The old game is `completed`, a new one is `active`, and the list shows both |
| 33 | Start a second game while one is active, or after the session is stopped | `409` message is shown and the list reloads |
| 34 | Ask for a quote for 90 minutes on a table with a block or minimum-hour rule | `fee` and `rule_name` match the rule, and nothing is created |
| 35 | Open the table usage report for a date range | Revenue counts paid sessions only, and `unpaid_total` covers stopped but unpaid sessions |
| 36 | Rename a table, then rename another table to the same name | The first works; the second shows `409 Table '<name>' already exists` |
| 37 | Change a table's hourly rate while it is playing | The running session keeps its old rate; the next session uses the new one |
| 38 | Deactivate a playing table | `409 Cannot deactivate a table with an active session`. Stop the session, then deactivate: the table leaves the board |
| 39 | Turn on manual-confirm "note required" and press Received with no note | `422` is shown, the note box stays open and is marked required. With a note it succeeds |
| 40 | Turn on manual-confirm "manager only" and press Received as a cashier | `403` is shown, the line stays `pending`, and polling continues. A manager can confirm |
| 41 | Open the controller screen as a manager and register a controller | The `api_key` is shown once. Registering the same id again returns `409` |
| 42 | Stop sending requests from the controller for over 90 seconds | `GET /billiard/controller/status` shows it `offline` |
| 43 | As a manager, save a bank account by typing the fields | `201`; `GET /payments/bank-accounts/current` shows it; the next transfer QR shows that account name |
| 44 | Upload a screenshot of a bank account QR | The form is prefilled with the BIN and account number, nothing is saved until you type the holder name and press Save |
| 45 | Upload a photo of something that is not a bank QR, or a card QR | `422` message is shown and the typed fields stay |
| 46 | Save the same account in a second club | `409 This bank account is already in use` |
| 47 | Log in as a cashier and open the bank account screen | Save, history and upload are hidden or answer `403`; `current` still works |
| 48 | Change the account while a transfer QR is waiting, then pay that line | The old QR still settles the bill; a new transfer line shows the new account |
| 49 | Send a webhook to an account that no club has saved | The transaction is `ignored` |

### Simulating the bank webhook in development

Ask the backend developer to set `SEPAY_API_KEY` on the dev server, then post a transfer with the memo shown on the QR. Use a new `id` for every test.

```bash
curl -X POST https://<api>/payments/bank-feed/sepay \
  -H "Authorization: Apikey $SEPAY_API_KEY" -H "Content-Type: application/json" \
  -d '{"id": 900001, "gateway": "Vietcombank", "transactionDate": "2026-10-21 18:00:00",
       "accountNumber": "<account number shown on the QR>", "code": null,
       "content": "chuyen tien PAY7L2", "transferType": "in", "transferAmount": 110000,
       "accumulated": 0, "referenceCode": "FT1", "description": ""}'
```

It answers `{"success": true}` even when the transfer is not matched, so check the bill or the bank inbox for the result. For the wrong-amount test, change `transferAmount`.

### Backend gaps to track

- `GET /products` needs no login and is not limited to the user's club. Scoping it to the club would stop a cashier seeing another club's menu.
- No endpoint says whether Stripe is configured, so the Card button has to be switched on in the frontend.
- No endpoint says whether the club's bank account is set before a transfer is started: a missing account shows up as a transfer line with no QR. Call `GET /payments/bank-accounts/current` on the pay screen if you want to warn the cashier first.
- No endpoint says whether manual confirmation needs a note or a manager, so the Received button has to react to the `403` and `422` responses.
- No WebSocket yet: the board and the scoreboard have to poll. Real-time updates are on the backend roadmap.
- A deactivated table cannot be reactivated.
- Packages can list any active product, because `GET /products` and the product catalogue are not scoped to the club (see the first point).

Fixed since Oct 24 (kept here so old notes make sense): `GET /auth/me` now returns `roles`, `POST /payments/` and `PATCH /payments/{id}` are admin only, `GET /payments/bank-feed/pending-lines` lists the waiting transfer lines, and stale transfer lines are cancelled automatically.