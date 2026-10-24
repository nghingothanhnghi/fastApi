# Frontend Developer Guide: Payments & Billiard

Oct 24, 2026 · @Someone

## Start here

The frontend needs about 25 endpoints to run a billiard table from start to payment: open a table, add drinks, stop the session, take payment, run the cash drawer and review bank transfers. Generate types from the backend's OpenAPI file, and use this guide for the screens and rules the schema cannot tell you.

New to the project? Read "The whole process, start to finish" first. It follows one session from the first tap to the receipt, then the screen-by-screen sections explain each part in detail.

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

### Which URLs to call

| Screen | URLs | Response |
| --- | --- | --- |
| Table board | `/tables`, `/tables/active`, `/tables/{id}/start` | `Table[]`, `ActiveTable[]`, `StartSessionResponse` |
| Menu and items | `/products`, `/sessions/{id}/items` | `Product[]`, `SessionItem` |
| Billiard bill and payment | `/sessions/{id}`, `/sessions/{id}/stop`, `/sessions/{id}/pay...` | `Bill` (includes the payment lines) |
| Cash drawer | `/payments/shifts...` | `Shift` or `ShiftSummary` |
| Manager bank inbox | `/payments/bank-feed/transactions...` | `BankTransaction` |
| Another business later | `/payments/orders/{source_type}/{source_id}/...` | `Order` (same lines as the bill) |

Billiard screens should use the `/sessions/{id}/pay...` URLs because they return the full bill, so one response redraws the whole screen. The `/payments/orders/...` URLs return the payment part only. For billiard they work too, with `source_type` set to `billiard_session` and `source_id` set to the session id, but you do not need them.

Do not build billiard screens on `POST /payments/`, `PATCH /payments/{id}` or `/payments/stripe/*`. Those are back-office routes for administrators (admin or super admin only). A cashier gets a `403` there. `POST /payments/` and `PATCH /payments/{id}` had no login check at all until the fix on branch `fix/payments-require-admin-auth`, so do not rely on them being open. Everything a cashier needs is under `/sessions`, `/tables` and `/payments/shifts`.

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

`GET /auth/me` returns the user but not their roles (see the gaps at the end). Keep whatever role information your login flow gets, because it decides whether to show manager buttons.

### Step 2. Open the shift

A shift is the cash drawer for the club: one open shift per club, not per cashier. `GET /payments/shifts/current` returns the open shift, or `null`. If it is `null`, show the opening-float form (screen 5) and call `POST /payments/shifts/open` with `{"opening_float": 1000000}`. A second open call returns `409 A shift is already open`, so load the existing one instead. If the club does not require shifts you can skip this step, but the drawer totals in step 9 are worked out for the time the shift was open, so a drawer count only makes sense when a shift was open.

### Step 3. The table board

`GET /tables` lists every table: `{"id": 1, "name": "T01", "status": "available", "hourly_rate": "100000.00"}`. `status` is `available`, `playing`, `reserved` or `maintenance`. Offer Start only on `available` tables; the server answers `409` for a table that cannot be started.

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
    "current_total": "310000.00"
  }
]
```

Keep `session_id` on the tile. Every later call uses it. `current_total` is a running estimate for display; the real bill comes from the stop call.

### Step 4. Start a session

`POST /tables/{id}/start` has no body. It returns the new session:

```json
{ "session_id": 42, "table_id": 1, "start_time": "2026-10-24T02:00:00", "opened_by": "cashier1" }
```

If the table already has an active session the server answers `409 Table already has an active session`. Reload the board and open that session instead.

### Step 5. Add drinks and food

`GET /products` returns the menu. Show products where `is_active` is true. A product with `variants` is sold by variant, so make the cashier pick one and send its `variant_id`. Otherwise use `base_price`. The price shown is for display only; the server prices the item itself.

`POST /sessions/{id}/items` with `{"product_id": 5, "variant_id": null, "quantity": 2}` returns `201` with the new line:

```json
{
  "id": 7, "product_id": 5, "variant_id": null, "product_name": "Coca Cola",
  "quantity": 2, "unit_price": "15000.00", "total_price": "30000.00"
}
```

Errors: `404 Product not found`, `400 Product is not available`, `400 Variant does not belong to this product`, and `409 Items can only be added to an active session` once the session is stopped. To show the current list, call `GET /sessions/{id}`: `items` is the full list and `grand_total` is up to date.

### Step 6. Stop the session

`POST /sessions/{id}/stop` ends the clock, frees the table and returns the bill. A second stop returns `409 Session is already completed`, so on that error just load the bill with `GET /sessions/{id}`.

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

Show this as the pay screen (screen 1). `billing_policy` and `pricing_rule_name` explain how the table fee was worked out; show `pricing_rule_name` as a small caption when it is not `null`.

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

While the transfer line is `pending`, show screen 2 and refresh the bill every 3 to 5 seconds. There are three ways it ends:

1. **The bank feed confirms it.** SePay posts the incoming transfer to the backend, which matches the memo and the exact amount. The bill turns `paid` by itself, with `paid_by: null`.
2. **The cashier presses Received.** `POST /sessions/{id}/pay/lines/14/confirm` (the body is optional: `{"note": "checked in the bank app"}`). The bill is returned, now `paid`.
3. **The cashier presses Cancel.** `POST /sessions/{id}/pay/lines/14/cancel` (optional `{"reason": "customer left"}`). The line becomes `cancelled`, the bill goes back to part paid or `unpaid`, and the cashier pays the balance another way.

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

- Draw `transfer.qr_payload` as a QR code with a QR library. If it is `null`, use `<img src={transfer.qr_image_url}>`. If both are `null`, show the account number, account name, amount and memo as text so the customer can type the transfer.
- Always show the amount and the memo in large text. The memo (for example `PAY7L2`) is how the bank feed finds the payment.
- Show a countdown to `transfer.expires_at`. After it passes, say the QR has expired but keep the Received button working, because the customer may have paid already.
- Buttons: **Received** (`POST /sessions/{id}/pay/lines/{line_id}/confirm`) and **Cancel** (`POST /sessions/{id}/pay/lines/{line_id}/cancel`, optional reason).
- Refresh the bill every 3 to 5 seconds while this screen is open. The bank feed can turn the bill `paid` with no user action, and the screen should switch to the receipt by itself.

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

A list from `GET /payments/bank-feed/transactions?status=needs_review`, with tabs for `unmatched`, `matched` and `ignored`. Each row shows the amount, the transfer `content`, the `reason`, and the time.

- **Ignore** asks for a note and calls `POST /payments/bank-feed/transactions/{id}/ignore`.
- **Assign** links the money to a waiting transfer line: `POST /payments/bank-feed/transactions/{id}/assign` with `{"line_id": 7}`. The amount must equal the line's amount, so show the line's amount next to the transaction and block a mismatch.
- There is no endpoint that lists every waiting transfer line. For assign, let the manager open the bill (`GET /sessions/{id}`) and pick the pending transfer line from `payments[]`.

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

A bill can go from `paid` back to `pending` or `unpaid` when a manager voids a line, so always handle every row, not only the forward path.

### Payment line status

| `status` | Show | Actions |
| --- | --- | --- |
| `pending` | Waiting badge, plus the QR for a transfer | Received, Cancel |
| `completed` | Paid badge | Void (managers only) |
| `cancelled` | Greyed, labelled cancelled | None |
| `voided` | Greyed, with `voided_at` and `void_reason` | None |
| `failed` | Red error badge, "could not be recorded" | None. Tell the cashier to pay the balance again |

Cash lines are `completed` as soon as they are created, so a pending cash line only appears if something failed.

### Bank transaction status

| `status` | Meaning | Actions |
| --- | --- | --- |
| `needs_review` | A code was found but the amount differs, the line was already paid, or the line was cancelled or voided. Read `reason` | Assign, Ignore |
| `unmatched` | No code, or an unknown code | Assign, Ignore |
| `matched` | It settled a line. `order_id` and `line_id` are set | None |
| `ignored` | Outgoing transfer, another account, or dismissed. Read `note` | None |

### Who sees which buttons

| Action | Allowed for |
| --- | --- |
| Pay, Received, Cancel, open shift, pay-in or pay-out | Any logged-in user of the club |
| Void a line | Manager or admin |
| List, assign or ignore bank transactions | Manager or admin |
| Close a shift | The user who opened it, or a manager |

A gap you need to know about: `GET /auth/me` does not return roles, and the endpoints that do (`GET /users`) are for administration. Until the backend adds roles to `/auth/me`, use the role information your login flow already keeps. If you have none, show manager buttons to everyone and turn a `403` into the message "Only a manager can do this". The server enforces every rule, so a visible button never gives access it should not.

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
  bank_code: string | null;
  account_no: string | null;
  account_name: string | null;
  amount: Money;
  memo: string;                      // e.g. "PAY7L2"
  qr_payload: string | null;         // draw as a QR code; null if no bank account is configured
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
  note: string | null;
  confirmed_at: ISODate | null;
  voided_at: ISODate | null;
  void_reason: string | null;
  transfer: TransferInstruction | null;
}
```

### Tables, menu and items

```ts
type TableStatus = "available" | "playing" | "reserved" | "maintenance";

interface Table {                    // GET /tables
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
  current_total: Money;
}

interface StartSessionResponse {     // POST /tables/{id}/start
  session_id: number;
  table_id: number;
  start_time: ISODate;
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
```

### Billiard bill

```ts
interface SessionItem {
  id: number;
  product_id: number | null;
  variant_id: number | null;
  product_name: string;
  quantity: number;
  unit_price: Money;
  total_price: Money;
}

interface Bill {                     // GET /sessions/{id}, /stop, and every /pay... response
  session_id: number;
  table_id: number;
  table_name: string;
  currency: string;                  // "VND"
  start_time: ISODate;
  end_time: ISODate | null;
  duration_minutes: number | null;
  hourly_rate: Money;
  billing_policy: string;
  pricing_rule_name: string | null;
  pricing_params: Record<string, unknown>;
  total_table_fee: Money;
  total_product_fee: Money;
  grand_total: Money;
  items: SessionItem[];
  payment_state: PaymentState;
  payment_method: BillPaymentMethod | null;
  payment_reference: string | null;
  paid_at: ISODate | null;
  amount_paid: Money;                // sum of completed lines
  balance_due: Money;                // grand_total - amount_paid
  payments: PaymentLine[];
  opened_by: string | null;
  stopped_by: string | null;
  paid_by: string | null;            // null = confirmed by the bank feed (or not paid)
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

interface ConfirmLineRequest { note?: string }             // max 255
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
  | "line_cancelled" | "line_failed" | "line_voided" | "order_paid";

interface PaymentEvent {             // GET /sessions/{id}/pay/events
  id: number;
  line_id: number | null;
  event_type: EventType;
  actor_id: number | null;           // null = the system (e.g. the bank feed)
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
  startTable:   (tableId: number) => request<StartSessionResponse>("POST", `/tables/${tableId}/start`),
  products:     () => request<Product[]>("GET", "/products"),
  addItem:      (id: number, b: AddItemRequest) => request<SessionItem>("POST", `/sessions/${id}/items`, b),

  bill:  (id: number) => request<Bill>("GET", `/sessions/${id}`),
  stop:  (id: number) => request<Bill>("POST", `/sessions/${id}/stop`),

  pay:   (id: number, body: PayRequest) => request<PayResponse>("POST", `/sessions/${id}/pay`, body),
  confirmCard: (id: number) => request<Bill>("POST", `/sessions/${id}/pay/confirm`),

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

  bankTransactions: (status?: BankTxStatus) =>                    // manager only
    request<BankTransaction[]>("GET", `/payments/bank-feed/transactions${status ? `?status=${status}` : ""}`),
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

// Cashier presses Received
await api.confirmLine(42, waiting!.id);

// Manager voids a completed line
await api.voidLine(42, 1, "gave too much change");

// Card
const card = await api.pay(42, { payment_method: "stripe" });
// confirm the card with Stripe using card.gateway.client_secret, then:
await api.confirmCard(42);
```

## Polling, errors and edge cases

A transfer can be confirmed by the bank feed at any moment, so the transfer-waiting screen must refresh itself. Every other failure should reload the bill and redraw it.

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

Stop polling when the screen closes, and keep going only while `payment_state` is `pending`.

### Error handling

The server's `detail` text is readable, but it is English and not a stable code. Branch on the status, show your own headline, and show `detail` underneath.

| Status | Meaning | What the UI does |
| --- | --- | --- |
| `401` | Token missing or expired | Send the user to login |
| `400` | Adding an item that cannot be sold (`Product is not available`, `Variant does not belong to this product`) | Show the message and refresh the menu |
| `403` | Not a manager, or closing someone else's shift | "Only a manager can do this" |
| `404` | Unknown id, or it belongs to another club | "Not found". Go back to the list |
| `409` | Wrong state. Table: "Table already has an active session". Session: "Items can only be added to an active session", "Session is already completed", "Stop the session before paying". Payment: "Already paid", "A payment is already in progress", "This order already has cash/transfer payments; pay the balance with those methods" (card after part payment). Shift: "Open a shift before taking payments", "A shift is already open", a pay-out larger than the drawer | Reload the bill, the board or the shift and redraw. The screen was out of date |
| `422` | Split lines do not add up, cash tendered is below the amount, a void or movement reason is too short, or the amount differs on assign | Show the message next to the form. Validate the same rules in the browser first |
| `500` on pay | Some lines could not be recorded | Reload the bill. Show which lines failed and offer to pay `balance_due` again |

### Edge cases

- **Double click.** Disable the pay button while a request is running. A second pay call returns `409`, which you treat as "reload the bill".
- **Page reload during a transfer.** The QR data is on the bill (`GET /sessions/{id}`), so rebuild the waiting screen from it. Do not store the QR yourself.
- **QR expired.** `transfer.expires_at` only says when to stop showing the QR as valid. The line stays `pending` until someone confirms or cancels it, so keep both buttons. To start over, cancel and pay again for a new QR.
- **Paid, then voided.** A bill can move from `paid` back to `pending` or `unpaid`. Redraw from the response and never assume paid is final.
- **Two cashiers on one bill.** Treat every response as the truth and redraw. Do not merge it with local state.
- **Old paid bills.** A bill that is `paid` with `payments: []` was settled before the payment module. Show it as paid and hide the line list.
- **Automatic confirmation.** A bill can become `paid` with `paid_by: null`. Show "Confirmed automatically by the bank" instead of a cashier name.
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
| 19 | Token expires | The user is sent to login and comes back to the same bill |
| 20 | Open a bill paid before the payment module | It shows as paid with no line list |
| 21 | Double click Pay | One payment is created and no error is shown |
| 22 | Start a table that already has a session | `409` message is shown and the board reloads |
| 23 | Add an item after the session is stopped | `409` message is shown, nothing is added |
| 24 | Try to pay a session that is still running | `409 Stop the session before paying`, and the Pay button should not have been shown |
| 25 | Stop the same session twice | The second call returns `409`, and the app shows the bill and the pay screen |
| 26 | Split 200,000 cash + 110,000 transfer, then press Cash on the waiting bill | `409 A payment is already in progress`. No pay buttons are shown while a transfer waits |
| 27 | Pay 100,000 cash, then try Card | `409`, and the Card button is already hidden |
| 28 | Pay out more cash than the drawer holds | `409` message is shown, and the form checks the amount first |
### Simulating the bank webhook in development

Ask the backend developer to set `SEPAY_API_KEY` on the dev server, then post a transfer with the memo shown on the QR. Use a new `id` for every test.

```bash
curl -X POST https://<api>/payments/bank-feed/sepay \
  -H "Authorization: Apikey $SEPAY_API_KEY" -H "Content-Type: application/json" \
  -d '{"id": 900001, "gateway": "Vietcombank", "transactionDate": "2026-10-21 18:00:00",
       "accountNumber": "<PAYMENT_BANK_ACCOUNT_NO>", "code": null,
       "content": "chuyen tien PAY7L2", "transferType": "in", "transferAmount": 110000,
       "accumulated": 0, "referenceCode": "FT1", "description": ""}'
```

It answers `{"success": true}` even when the transfer is not matched, so check the bill or the bank inbox for the result. For the wrong-amount test, change `transferAmount`.

### Backend gaps to track

- `GET /auth/me` returns no roles, so the frontend cannot tell a manager from a cashier. Adding a `roles` list to it would let you hide manager buttons.
- No endpoint lists every waiting transfer line, so the manager's Assign action needs the manager to open the bill first.
- `GET /products` needs no login and is not limited to the user's club. Scoping it to the club would stop a cashier seeing another club's menu.
- No endpoint says whether Stripe is configured, so the Card button has to be switched on in the frontend.
- `POST /payments/` and `PATCH /payments/{id}` had no login check. The fix is on branch `fix/payments-require-admin-auth` and makes them admin-only; billiard screens never need them.
