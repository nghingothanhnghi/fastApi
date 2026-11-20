# Billiard & Payments: Test Warnings Note

Captured Nov 19, 2026 from `python -m pytest -v` (Python 3.13.3, pydantic 2.11): **297 passed, 0 failed**. Only warnings are left. This note lists the ones that touch the billiard/payments code. Warnings from CMS, hydro, AI vision, sensors, websockets and token code are out of scope here.

## 1. ✅ DONE Nov 20, 2026: Pydantic `.dict()` → `model_dump()`

Fixed in `payment_service.py` by the project owner. **Verified Nov 20:** `test_payments_orders.py`, `test_payments_transfer_expiry.py` and `test_billiard_payments.py` ran 69 passed in 11.24s with **no warnings at all**. Kept below for the record.

### Pydantic v2: `.dict()` is deprecated

| | |
| --- | --- |
| Warning | `PydanticDeprecatedSince20: The dict method is deprecated; use model_dump instead` |
| Where | `app/payments/services/payment_service.py:104` (`update_payment_status`) |
| Triggered by | Every payment cancel and transfer expiry (`cancel_line`, `expire_line`), so 11 billiard/payments tests |
| Fix | `updates.dict(exclude_unset=True)` → `updates.model_dump(exclude_unset=True)` |
| Same pattern, not yet hit by a test | `payment_service.py:22` in `create_payment`: `payment_in.dict()` → `payment_in.model_dump()` |
| Risk | None. `exclude_unset` behaves the same in `model_dump` |
| Why it matters | Pydantic v3 removes `.dict()`. Cancelling a payment line and the 5-minute expiry job would start failing |

After the change, re-run `test_payments_orders.py`, `test_payments_transfer_expiry.py`, `test_billiard_payments.py` and `test_payments_bank_feed.py`. The warning count in those files should drop to zero.

## 2. ✅ CLOSED Nov 20, 2026: `utcnow()` column default is not a payments issue

**Verified:** `test_payments_shifts.py`, `test_payments_bank_feed.py` and `test_payments_manual_confirm.py` ran 50 passed in 4.96s with no warnings. Together with section 1, all 119 payments and billiard payment tests are warning-free. The `utcnow` source is in hydro code and goes to the hydro cleanup. The steps below are kept only for that cleanup.

**Update Nov 20:** the `utcnow` warning did **not** appear when the three files above were run alone, so it does not come from the payments or billiard models. In the full run it was shown under payments tests only because Python prints a repeated warning once, next to whichever test hit it first. The remaining place to check is `test_payments_shifts.py` (and `test_payments_bank_feed.py`, `test_payments_manual_confirm.py`):

`python -m pytest app/tests/test_payments_shifts.py app/tests/test_payments_bank_feed.py app/tests/test_payments_manual_confirm.py -v`

If those show no warning either, close this item: the source is hydro code and belongs to the hydro cleanup. If `test_payments_shifts.py` still warns, continue with the steps below.

**Steps**

1. In the project root run: `findstr /S /N /C:"default=datetime.utcnow" app\*.py` (Windows) or `rg "default=datetime.utcnow" app`.
2. Also search for `onupdate=datetime.utcnow` and `default=datetime.utcnow()`.
3. For each hit, note the file. If it is under `app/hydro_system`, it belongs to the hydro cleanup, not to payments.
4. Replace with `default=lambda: datetime.now(timezone.utc)` (add `from datetime import timezone`), or use `server_default=func.now()`.
5. Re-run `python -m pytest app/tests/test_payments_shifts.py app/tests/test_payments_transfer_expiry.py -v` and check the `utcnow` warning is gone.

### SQLAlchemy column default calls `datetime.utcnow()`

| | |
| --- | --- |
| Warning | `DeprecationWarning: datetime.datetime.utcnow() is deprecated` raised from `sqlalchemy/sql/schema.py:3624` |
| Seen in payments tests | `test_cash_void_in_the_same_shift_nets_to_zero`, `test_split_bill_keeps_its_paid_part_when_the_transfer_part_expires`, `test_pending_lines_exclude_paid_and_cancelled_lines_and_flag_expired_ones` (also `test_control_actuator_by_id...` in hydro) |
| What it means | Some model column uses `default=datetime.utcnow`. SQLAlchemy calls it on insert, so the warning points into SQLAlchemy, not into your file |
| Not the payments models | `PaymentOrder`, `PaymentLine`, `CashShift`, `BankTransaction` and billiard models use `server_default=func.now()` or pass a timezone-aware value, so they are not the source |
| How to find it | Search the repo: `grep -rn "default=datetime.utcnow" app` (or `rg`). The likely hit is a hydro model touched by the same tests |
| Fix | `default=lambda: datetime.now(timezone.utc)` or `server_default=func.now()` |

Only fix this if the model it finds is shared with payments or billiard. Otherwise it belongs to the hydro cleanup.

## 3. ✅ CLOSED Nov 20, 2026: pydantic `class Config` / `Field(example=...)` warnings are not billiard

**Verified:** `test_game_service.py`, `test_event_service.py`, `test_event_sessions.py` and `test_pricing_sessions.py` ran 61 passed in 6.45s with no warnings. Every billiard and payments test file has now been run, and none produces a warning. The pydantic warnings come from another module and are out of scope for this note. The original description is kept below in case you clean them up later.

### Original description

The payments test files showed no such warning when run alone, so this is very likely outside payments. One last check for billiard:

`python -m pytest app/tests/test_game_service.py app/tests/test_event_service.py app/tests/test_event_sessions.py app/tests/test_pricing_sessions.py -v`

If there is no warning, close this item as "not billiard". If there is, use the trace command below.

Seven `class-based config` warnings and one `Field(example=...)` warning come from pydantic itself, with no file named. To find the schema, run once:

```bash
python -W error::DeprecationWarning -m pytest app/tests/test_billiard_payments.py -x
```

If it stops inside `app/billiard` or `app/payments`, fix it there: `class Config:` → `model_config = ConfigDict(...)`, and `Field(example=...)` → `Field(json_schema_extra={"example": ...})`. The billiard and payments schemas shown so far already use `model_config`, so the source is most likely another module.

## 4. For the future (not warnings yet)

| Item | Note |
| --- | --- |
| Turn warnings into errors for billiard/payments | Once sections 1 and 2 are clean, add `filterwarnings = error::DeprecationWarning` for those test files so a new deprecated call fails the build |
| `utcnow()` in your own billiard-adjacent code | `app/user/user.py` (`create_user`, `verify_reset_code`, `cleanup_expired_codes`) still uses `datetime.utcnow()`. Not in these test runs, but `create_user` runs on the first login/bootstrap path |
| Keep `.dict()` out of new code | Use `model_dump()` and `model_validate()` in any new schema work, matching `app/billiard` and `app/payments/services/order_service.py` |

## Done when

- [x] `payment_service.py` uses `model_dump` (2 places), done Nov 20
- [x] The `utcnow` source: not payments, handed to the hydro cleanup (Nov 20)
- [x] Billiard game/event/pricing tests checked for pydantic warnings: none (Nov 20)

**Status: complete for billiard and payments. 180 tests across all billiard and payments files, 0 warnings.**
- [ ] `python -m pytest app/tests/test_payments_*.py app/tests/test_billiard_payments.py app/tests/test_event_*.py app/tests/test_game_service.py app/tests/test_pricing_sessions.py -W error::DeprecationWarning` passes
