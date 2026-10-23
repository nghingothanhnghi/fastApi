# Frontend Developer Guide: Payments & Billiard

Oct 21, 2026 · @Someone

## Start here

The frontend needs about 20 endpoints to take payment for a billiard bill, run the cash drawer and review bank transfers. Generate types from the backend's OpenAPI file, and use this guide for the screens and rules the schema cannot tell you.

### Set up

| Topic | What to do |
| --- | --- |
| Schema and docs | The API serves `/openapi.json` and a Swagger page at `/docs`. Generate types with `npx openapi-typescript https://<api>/openapi.json -o api.d.ts` |
| Login | `POST /auth/login` with form-encoded `username` and `password` (not JSON). It returns `{"access_token", "token_type": "bearer"}` |
| Auth header | Send `Authorization: Bearer <access_token>` on every call except the SePay webhook, which is not yours. A `401` means log in again |
| Money | Amounts arrive as strings such as `"310000.00"`. The currency is VND, which has no decimals, so convert with `Number()` and format with `Intl.NumberFormat("vi-VN")`. Send amounts in request bodies as plain numbers |
| Dates | ISO 8601. Some timestamps come without an offset, for example `2026-10-21T00:28:54.654112`. Treat a timestamp with no offset as UTC (append `Z`), then show it in the club's time zone |
| The amount | Never send the bill total. For a single payment the server uses `grand_total`. In a split you send how the total is divided, and the lines must add up exactly to `balance_due` |

### Which URLs to call

| Screen | URLs | Response |
| --- | --- | --- |
| Billiard bill and payment | `/sessions/{id}`, `/sessions/{id}/stop`, `/sessions/{id}/pay...` | `Bill` (includes the payment lines) |
| Cash drawer | `/payments/shifts...` | `Shift` or `ShiftSummary` |
| Manager bank inbox | `/payments/bank-feed/transactions...` | `BankTransaction` |
| Another business later | `/payments/orders/{source_type}/{source_id}/...` | `Order` (same lines as the bill) |

Billiard screens should use the `/sessions/{id}/pay...` URLs because they return the full bill, so one response redraws the whole screen. The `/payments/orders/...` URLs return the payment part only.

## Screens to build

Six screens cover the whole flow. The pay screen and the transfer-waiting screen are the same page in two states, driven by the bill's `payment_state`.

### 1. Pay screen (after the session is stopped)

Show the bill (items, `total_table_fee`, `total_product_fee`, `grand_total`) and the ways to pay: Cash, Bank transfer, Split, and Card only if Stripe is enabled for the club.

- **Cash:** an input for the amount handed over, quick buttons (exact, 50,000, 100,000, 200,000, 500,000) and the change shown live as `tendered - balance_due`. Disable the button while tendered is below `balance_due`. Send `{"payment_method": "cash", "cash_tendered": 500000}`. Leaving tendered out means an exact payment.
- **Bank transfer:** one button. Send `{"payment_method": "bank_transfer"}`, then show screen 2.
- **Split:** open the split editor (screen 3).
- **Card (Stripe):** send `{"payment_method": "stripe"}`. The response has `gateway.client_secret`. Complete the card payment with Stripe's SDK, then call `POST /sessions/{id}/pay/confirm`.
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
| `403` | Not a manager, or closing someone else's shift | "Only a manager can do this" |
| `404` | Unknown id, or it belongs to another club | "Not found". Go back to the list |
| `409` | Wrong state, such as "Stop the session before paying", "Already paid", "A payment is already in progress", or no open shift | Reload the bill and redraw. The screen was out of date |
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

### Two backend gaps to track

- `GET /auth/me` returns no roles, so the frontend cannot tell a manager from a cashier. Adding a `roles` list to it would let you hide manager buttons.
- No endpoint lists every waiting transfer line, so the manager's Assign action needs the manager to open the bill first.
