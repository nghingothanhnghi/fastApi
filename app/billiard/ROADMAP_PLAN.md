# Billiard Roadmap: Implementation Plan (README section 11)

Plan for the items listed in [`README.md` section 11](README.md#11-roadmap-not-implemented-yet).
Every item reuses the pattern the module already has. Nothing here needs a new architecture.

## 0. Ground rules (the existing pattern, reused everywhere)

| Rule | Where it already lives | What it means for the new work |
|------|------------------------|--------------------------------|
| Only lifecycle modules write status | `table_lifecycle`, `session_lifecycle`, `game_lifecycle` | Reservation, maintenance, cancel, timed play and packages add **functions to the lifecycle modules**, never `table.status = ...` in a router or handler |
| Services flush, routers commit | `session_service`, `bank_account_service` | New services never call `commit()` |
| Routers stay thin | `session_router`, `pricing_router` | Business `if`s go to a service |
| Tenant isolation, 404 not 403 | `scope_tables()`, `get_locked_session()`, `pricing_rule_service._scope()` | New services copy `_scope()` from `pricing_rule_service.py` |
| Snapshots protect old bills | `pricing_snapshot`, `SessionItem.unit_price` | Package, discount and rate-window data are frozen into the session |
| Money is `Decimal` | `utils/billing.py` | Use `Decimal(str(x))` and `CENT` |
| Device path = POS path | `event_service` handlers call lifecycle helpers | Every new POS action that has a device event gets **one** lifecycle function used by both |
| Schema change needs a migration | `migrate_payment_bank_accounts.py` | Idempotent `migrate_billiard_<topic>.py`, same style (SQLite backup first, `inspect()` before `ALTER`, safe to run twice) |
| Tests use an in-memory SQLite `db` fixture | `test_game_service.py` | Same fixture, same `_user()` helper style |

### Two small refactors that unblock several items (do first)

| ID | Task | Why |
|----|------|-----|
| P0.1 | Add `session_lifecycle.recompute_totals(session)`: `grand_total = max(total_table_fee + total_product_fee - discount, 0)`. Call it from `finalize_stop` **and** `session_service.add_item` | The formula `table_fee + product_fee` is written twice today (`session_lifecycle.py:78`, `session_service.py:67`). Discounts and packages must not add a third and fourth copy |
| P0.2 | Move the repeated test helpers (`db` fixture, `_user`, `_table`) into `app/tests/_billiard_fixtures.py` and import them in the new test files | New test files need them; copying them again makes 9 copies |

Tests for P0: `test_recompute_totals_matches_old_formula_with_zero_discount`, `test_add_item_and_stop_give_same_grand_total_as_before` (run the existing `test_pricing_sessions.py` and `test_game_service.py` unchanged: they are the regression suite).

---

## 1. Order of work

Ordered by dependency and by value to the cashier. Sizes: **S** under 1 day, **M** 1 to 2 days, **L** 3 or more.

| Phase | Items | Why this order |
|-------|-------|----------------|
| **1. Core session rules** | P0, A Reservations/maintenance (S), B Cancelled sessions (M), C Discounts (M) | Small, independent, all use existing status columns |
| **2. Time and packages** | D Timed play (M), E Package CRUD (M), F Packages in billing (L) | D creates the `ends_at` logic that packages reuse |
| **3. Device events** | G More device events (M) | Needs A (`table_status`) and D (`time_extend`) |
| **4. Operations** | H Offline heartbeat job (S), I WebSocket POS updates (L) | Independent. I is easiest once phases 1 to 3 have settled the event names |
| **5. Needs a decision** | J Split bills across rate windows (L), K RS485 firmware (spec only here) | J waits for the spike (section 5, #8). K is spec and simulator only (section 5, #9) |

```text
P0 ──► C Discounts ──┐
P0 ──► F Packages ◄──┴── E Package CRUD, D Timed play
A ────────────────► G (table_status)      D ──► G (time_extend)
```

---

## 2. Feature plans

Each plan lists the tasks, then the test cases. Test names follow the existing `test_<what_happens>` style.

### A. Reservations / maintenance (S)

`TableStatus.RESERVED` and `MAINTENANCE` exist, but nothing sets them. `mark_playing` already refuses both (`409 Table is reserved`).

**Tasks**

| # | Task | File |
|---|------|------|
| A1 | `mark_reserved(table)`, `mark_maintenance(table)`, `release(table)`. Allowed only from `AVAILABLE` (release from `RESERVED` / `MAINTENANCE`). Raise `ValueError` like `mark_playing` | `services/table_lifecycle.py` |
| A2 | `table_service.set_status(db, table_id, action, user)`: lock table with `scope_tables(...).with_for_update()`, check an active session record (same check as `deactivate_table`), call the lifecycle function, map `ValueError` to `409` | `services/table_service.py` |
| A3 | Routes `POST /tables/{id}/reserve`, `POST /tables/{id}/maintenance`, `POST /tables/{id}/release`. ADMIN, MANAGER | `routes/table_router.py` |
| A4 | Schema: optional `note` (max 200). No new column: keep it out of the table row. Status only (decision 1): no reservation data is stored. A full reservation feature is a later, separate item (section 5, Follow-up) | `schemas/table.py` |
| A5 | README: section 4 note, section 9 table, remove the roadmap row | `README.md` |

No migration (columns already exist).

**Test cases** (`test_table_status.py`)

| Test | Expectation |
|------|-------------|
| `test_available_table_can_be_reserved_then_released` | status goes `available` → `reserved` → `available` |
| `test_maintenance_blocks_start` | `start_session` on a maintenance table → `409 Table is maintenance` |
| `test_cannot_reserve_playing_table` | `409`, status unchanged |
| `test_cannot_set_status_on_inactive_table` | `409` |
| `test_reserve_twice_is_409` | second call refused |
| `test_release_available_table_is_409` | nothing to release |
| `test_other_tenant_gets_404` | tenant isolation |
| `test_staff_role_cannot_change_status` | `403` (router test, same `dependency_overrides` pattern as `test_payments_bank_account_router.py`) |
| `test_find_inconsistencies_ignores_reserved_and_maintenance` | invariant helper still empty |

---

### B. Cancelled sessions (M)

`SessionStatus.CANCELLED` exists. Cancel means "opened by mistake": no bill, no payment, the table is freed.

**Decision (section 5, #2):** only ADMIN/MANAGER, only `ACTIVE` sessions, reason required. A `COMPLETED` session is never cancelled (that is a payment void, which already exists).

**Tasks**

| # | Task | File |
|---|------|------|
| B1 | New columns on `table_sessions`: `cancelled_at` (datetime), `cancelled_by_id` (FK users, SET NULL), `cancel_reason` (string 255) | `models/session.py` |
| B2 | Migration `migrate_billiard_session_cancel.py` (add the 3 columns if missing) | repo root |
| B3 | `session_lifecycle.cancel_session(db, session, table, cancelled_by_id, reason, at=None)`: status `CANCELLED`, `end_time`, zero totals, close the running game as `CANCELLED` (add `cancel_active_game` in `game_lifecycle`, mirror of `close_active_game`), `mark_available(table)` | `services/session_lifecycle.py`, `game_lifecycle.py` |
| B4 | `session_service.cancel_session(db, session_id, reason, user)`: `get_locked_session`, `409` if not active, lock the table (copy `stop_session`), call B3 | `services/session_service.py` |
| B5 | `POST /sessions/{id}/cancel` body `{"reason": "..."}` (min 3 chars). Returns the bill view with `status` | `routes/session_router.py`, `schemas/session.py` |
| B6 | Items on a cancelled session: keep rows, `grand_total` = 0. Reports already count only `completed`, so nothing changes there | none |
| B7 | `BillResponse` gets `status`, `cancel_reason` | `schemas/session.py`, `build_bill` |

**Test cases** (`test_session_cancel.py`)

| Test | Expectation |
|------|-------------|
| `test_cancel_active_session_frees_table` | session `cancelled`, table `available`, `grand_total` 0 |
| `test_cancel_closes_running_game_as_cancelled` | game status `cancelled`, scores kept |
| `test_cancel_requires_reason` | `422` |
| `test_cannot_cancel_completed_session` | `409` |
| `test_cannot_cancel_twice` | `409` |
| `test_cancelled_session_not_in_usage_report` | `/reports/tables/usage` totals unchanged |
| `test_cancelled_session_cannot_be_paid` | `POST /sessions/{id}/pay` → `409` |
| `test_cancelled_session_cannot_receive_items` | `409 Items can only be added to an active session` |
| `test_table_can_be_started_again_after_cancel` | new session opens, one active only |
| `test_cancel_other_tenant_404` | tenant isolation |
| `test_cancel_is_manager_only` | staff `403` |
| `test_controller_session_stop_on_cancelled_session_is_not_rebilled` | device event does not turn it back to `completed` (edge case, see G) |

---

### C. Discounts (M)

Column `discount` exists; `grand_total` ignores it. `payment_adapter.py:55` reads `grand_total` when the payment order is created, so the discount must be set **before** an order exists.

**Decisions (section 5, #3):** fixed amount or percent of the **table fee + products**; set by ADMIN/MANAGER; allowed while the session is `ACTIVE` or `COMPLETED` with `payment_order_id IS NULL`; capped so `grand_total` never goes below 0.

**Tasks**

| # | Task | File |
|---|------|------|
| C1 | Columns: `discount_reason` (255), `discounted_by_id` (FK users, SET NULL). Keep `discount` as the **amount** actually applied (snapshot, not a percent) | `models/session.py` |
| C2 | Migration `migrate_billiard_discount.py` | repo root |
| C3 | `session_lifecycle.apply_discount(session, amount)` → clamps to `[0, table_fee + product_fee]`, then `recompute_totals`. Percent is converted to an amount in the service (the stored value is always an amount) | `services/session_lifecycle.py` |
| C4 | `session_service.set_discount(db, session_id, amount \| percent, reason, user)`: lock, tenant check, `409` if an order exists, `422` if both or neither of amount/percent | `services/session_service.py` |
| C5 | `POST /sessions/{id}/discount`. Setting `0` removes it | `routes/session_router.py` |
| C6 | `finalize_stop` keeps an existing `discount` and recomputes (discount set during play survives Stop). If the discount was a percent, store the percent in `pricing_snapshot["discount"]` and recompute the amount at Stop (table fee is only final at Stop) | `session_lifecycle.py` |
| C7 | `BillResponse` shows `discount`, `discount_reason`. Live total in `get_active_tables` subtracts it | `schemas/session.py`, `table_service.get_active_tables` |
| C8 | Report: add `discount_total` to the usage report. Revenue stays `grand_total` (net). Note: `table_revenue + product_revenue - discount_total = total_revenue` | `services/report_service.py`, `schemas/report.py` |

**Test cases** (`test_session_discount.py`)

| Test | Expectation |
|------|-------------|
| `test_zero_discount_changes_nothing` | totals identical to today |
| `test_fixed_discount_reduces_grand_total` | `grand_total = table + products - discount` |
| `test_percent_discount_is_converted_to_amount` | 10 % of 310,000 → 31,000 |
| `test_discount_cannot_exceed_total` | clamped, `grand_total` 0 (never negative) |
| `test_discount_set_during_play_survives_stop` | amount kept after `finalize_stop` |
| `test_percent_discount_recomputed_at_stop` | uses the final table fee |
| `test_discount_after_order_created_is_409` | `payment_order_id` set → refused |
| `test_discount_on_cancelled_session_is_409` | |
| `test_both_amount_and_percent_is_422` | |
| `test_negative_discount_is_422` | |
| `test_discount_is_manager_only` | staff `403` |
| `test_other_tenant_404` | |
| `test_payment_order_total_uses_discounted_grand_total` | `payment_adapter` quote total equals `grand_total` after discount |
| `test_usage_report_shows_discount_total` | report arithmetic holds |
| `test_remove_discount_restores_total` | set `0` |

---

### D. Timed play (M)

`ends_at` exists and the controller state already sends it (`session_ends_at`). Nothing sets it. **Billing is not changed**: the fee still comes from real start/stop times. `ends_at` is a countdown and an overtime flag only.

**Decision (section 5, #4):** the server never auto-stops a session. It flags overtime; staff or the controller stops it.

**Tasks**

| # | Task | File |
|---|------|------|
| D1 | `open_session(..., planned_minutes: int \| None)` sets `ends_at = start + planned_minutes` | `services/session_lifecycle.py` |
| D2 | `session_lifecycle.extend_session(session, minutes)`: `ends_at += minutes` (if `ends_at` is empty, from `now`). Only for `ACTIVE`. Max 1440 | `services/session_lifecycle.py` |
| D3 | `POST /tables/{id}/start` accepts optional body `{"planned_minutes": 60}` (backward compatible: no body still works) | `routes/table_router.py`, `schemas/table.py` |
| D4 | `POST /sessions/{id}/extend` body `{"minutes": 30}` (1 to 480) | `routes/session_router.py` |
| D5 | `get_active_tables` adds `ends_at`, `remaining_seconds` (can be negative), `is_overtime` | `table_service.get_active_tables` |
| D6 | Bill shows `planned_minutes`/`ends_at` for information | `schemas/session.py` |

No migration.

**Test cases** (`test_timed_play.py`)

| Test | Expectation |
|------|-------------|
| `test_start_without_planned_minutes_has_no_ends_at` | old behaviour |
| `test_start_with_planned_minutes_sets_ends_at` | `ends_at = start + N min` |
| `test_extend_adds_minutes_to_ends_at` | |
| `test_extend_without_ends_at_starts_from_now` | |
| `test_extend_completed_session_is_409` | |
| `test_extend_limits_are_422` | 0, negative, over max |
| `test_overtime_flag_after_ends_at` | `is_overtime` true, `remaining_seconds` negative |
| `test_billing_ignores_ends_at` | stopping before or after `ends_at` gives the same fee as today for the same real duration |
| `test_controller_state_contains_ends_at` | `GET /controller/state` returns the value |
| `test_extend_other_tenant_404` | |

---

### E. Packages: CRUD (M)

Tables `billiard_packages` and `billiard_package_items` exist (duration, price, included products). Copy `pricing_rule_service.py` / `pricing_router.py` / `schemas/pricing.py` as the template.

**Tasks**

| # | Task | File |
|---|------|------|
| E1 | `schemas/package.py`: `PackageCreate`, `PackageUpdate`, `PackageItemIn`, `PackageOut`. Validate `duration_minutes` 1 to 1440, `price` ≥ 0, items unique by `product_id`, `included_quantity` ≥ 1 | new |
| E2 | `services/package_service.py`: `_scope`, list (active by default, `?include_inactive=`), create, update (replace item list), deactivate. `409` on duplicate name (`uq_package_name_per_client`). `400` if a product is missing or inactive | new |
| E3 | `routes/package_router.py`: `GET/POST /billiard/packages`, `PUT /billiard/packages/{id}`, `DELETE /billiard/packages/{id}` (= **deactivate**, history kept, same as tables). Register in `routes/__init__.py`. ADMIN, MANAGER for writes | new |
| E4 | `GET /billiard/packages/{id}` for the POS picker | `package_router.py` |

No migration. Package edits never change old sessions (see F: the session stores a snapshot).

**Test cases** (`test_packages.py`)

| Test | Expectation |
|------|-------------|
| `test_create_package_with_items` | |
| `test_duplicate_name_in_same_club_is_409`, `test_same_name_in_other_club_is_ok` | unique per `client_id` |
| `test_duration_and_price_validation_is_422` | 0 minutes, negative price, quantity 0 |
| `test_duplicate_product_in_items_is_422` | |
| `test_inactive_or_unknown_product_is_400` | |
| `test_update_replaces_items` | |
| `test_deactivate_hides_from_default_list` | row kept |
| `test_list_is_tenant_scoped`, `test_other_tenant_404` | |
| `test_package_endpoints_manager_only_for_writes` | staff can read, not write |

---

### F. Packages in billing (L)

**Billing rule (section 5, #5 and #6):** the package price covers the first `duration_minutes` of **table time only**. Products and additional services are charged separately. Time beyond the package duration is billed with the pricing rule assigned to the session (rate, rule type, params). Any package can be used on any active table: there is **no** table or zone restriction, so `BilliardPackage` gets no `table_id`.

```text
table_fee = package_price + calculate_fee(rule_type, hourly_rate, max(0, minutes - package_duration), params)
```

Included products: the package stores "2 beers included". When staff add those products to the session, the first N units cost 0, the rest are normal.

**Tasks**

| # | Task | File |
|---|------|------|
| F1 | New column `table_sessions.package_snapshot` (JSON): `{package_id, name, price, duration_minutes, items: [{product_id, included_quantity}]}`. The existing `package_id/name/price` stay. Package edits later never change it | `models/session.py` |
| F2 | Migration `migrate_billiard_package_snapshot.py` | repo root |
| F3 | `open_session(..., package: BilliardPackage \| None)`: snapshot the package, set `ends_at = start + duration` (reuses D1). `400` if inactive, `404` if other club | `services/session_lifecycle.py` |
| F4 | `POST /tables/{id}/start` body gains optional `package_id` (same body as D3) | `routes/table_router.py`, `schemas/table.py` |
| F5 | `billing_service.table_fee(session, minutes)`: if `package_snapshot` exists, use the formula above. Snapshot-based, so it works for the live total and for Stop exactly as pricing rules do today | `services/billing_service.py` |
| F6 | `session_service.add_item`: compute `included_remaining` per product from the snapshot minus already-added units; split the line into an included part (`unit_price` 0, name suffix `(package)`) and a paid part. Keep `SessionItem` snapshot rules | `services/session_service.py` |
| F7 | Bill: `package_name`, `package_price`, `package_minutes`, `overtime_minutes`. Live total in `get_active_tables` uses F5 | `schemas/session.py`, `table_service.py` |
| F8 | Controller path: `session_start` event may carry `data.package_id`; the handler calls the same `open_session` | `services/event_service.py` |
| F9 | `GET /billiard/pricing-rules/quote` accepts `package_id` to preview | `routes/pricing_router.py` |
| F10 | Interaction with discount (C) and rule selection: package overrides the *table fee* only; rule selection still runs so overtime uses the matching rule | `billing_service.quote_for_table` |

**Test cases** (`test_package_sessions.py`)

| Test | Expectation |
|------|-------------|
| `test_start_with_package_snapshots_name_price_duration` | |
| `test_start_with_inactive_package_is_400`, `..._other_club_is_404` | |
| `test_package_fee_inside_duration_is_package_price` | 50 of 60 min → price |
| `test_overtime_billed_with_session_rule` | 90 of 60 min → price + 30 min at rate; check per_minute, hourly, block, minimum_hour |
| `test_zero_minutes_still_charges_package_price` | policy decision, documents the behaviour |
| `test_editing_package_after_start_does_not_change_session` | snapshot |
| `test_included_item_is_free_up_to_quantity` | 2 included, add 1 → 0 |
| `test_item_over_included_quantity_is_split` | add 3 → 2 free + 1 paid |
| `test_included_quantity_counts_across_several_add_calls` | |
| `test_non_package_product_is_charged_normally` | |
| `test_live_total_matches_stop_total_with_package` | same invariant as pricing sessions |
| `test_package_session_gets_ends_at` | |
| `test_package_plus_discount` | discount applies after the package fee |
| `test_package_start_from_controller_event` | adopts the same code path |
| `test_session_without_package_unchanged` | full regression (`test_pricing_sessions.py` still green) |
| `test_quote_with_package_matches_real_bill` | preview equals Stop |

---

### G. More device events (M)

Handler pattern (copy `_h_score_change`, register in `HANDLERS`): `_h_xxx(db, device_pk, client_id, ev) -> Optional[note]`. Today these four are stored as `rejected` ("No handler yet").

| Event | Handler | Reuses |
|-------|---------|--------|
| `time_extend` | `data.minutes` → `session_lifecycle.extend_session` on the resolved active session | D2 |
| `table_status` | `data.status` in `reserved`, `maintenance`, `available` → table_lifecycle functions. `playing` is **rejected** (only a session start can make a table playing) | A1 |
| `button_press` | `data.action` mapped through a small table `BUTTON_ACTIONS = {"score_a_up": ..., "new_game": ...}` to existing handlers; unknown action → `rejected` with message (never silently dropped) | existing `_h_*` |
| `device_error` | Store as `processed`, write `data.code/message` into the event note, update the device row (`last_error`, `last_error_at`; 2 columns + migration) so managers see it in `/controller/status` | H (alert hook) |

**Tasks:** G1 handlers and `HANDLERS` entries; G2 `BUTTON_ACTIONS` map in one place; G3 device columns `last_error`, `last_error_at` + migration `migrate_billiard_device_error.py`; G4 `status` response shows them; G5 update README section 8 table; G6 keep `device_error` ordering rule (still ordered by `device_seq`).

**Test cases** (extend `test_event_sessions.py`, new file `test_event_handlers_extra.py`)

| Test | Expectation |
|------|-------------|
| `test_time_extend_event_extends_ends_at` | |
| `test_time_extend_without_active_session_is_rejected` | stays in `rejected`, device keeps it |
| `test_table_status_maintenance_event_sets_status` | |
| `test_table_status_playing_event_is_rejected` | |
| `test_table_status_on_playing_table_is_conflict` | not applied |
| `test_button_press_known_action_runs_handler` | |
| `test_button_press_unknown_action_is_rejected` | |
| `test_device_error_is_processed_and_recorded` | device `last_error` set |
| `test_new_events_are_idempotent` | replay returns `duplicates` |
| `test_new_events_respect_device_seq_order_and_cursor` | `server_state_version` advances only when contiguous |
| `test_new_events_cannot_cross_tenant` | table of another club → rejected |
| `test_device_clock_rules_apply_to_new_events` | future/too-old timestamps rejected |

---

### H. Offline heartbeat job (S) ✅ built

Built as planned, with two deliberate differences: the settings live in `app/billiard/config.py` (not a global config), and the "back online" log is written by `device_watchdog.mark_online`, called on every authenticated device contact (not only in the heartbeat handler), so a device that only syncs or reads `/state` also recovers. Added `billiard_devices.status_changed_at` for H5.

`device_service.effective_status` already shows offline after 90 s. The job records the **change** and can alert.

**Tasks**

| # | Task | File |
|---|------|------|
| H1 | New table `billiard_device_status_log` (`device_id` FK, `from_status`, `to_status`, `at`, `reason`) + migration. Created by `create_all` for new DBs | `models/device.py` |
| H2 | `device_service.sweep_offline(db, now)`: for devices stored as `online` whose `last_seen` is older than the threshold, `UPDATE ... WHERE status='online'` to `offline`, write a log row. Also writes `online` when a heartbeat arrives for an `offline` device (in `_h_heartbeat`). Idempotent and safe with several workers (conditional update) | `services/device_service.py`, `event_service.py` |
| H3 | Register the job in `main.py` with the existing `add_job` from `app.utils.scheduler` (every 30 s). Config `BILLIARD_OFFLINE_AFTER_SECONDS` (default 90) in `config.py` | `main.py`, `config.py` |
| H4 | Alert hook: a function `notify_device_offline(device)` in `services/device_alerts.py` that logs a warning now. Realtime push added by I | new |
| H5 | `GET /billiard/controller/status` also returns the last change time | `controller_router.py` |

**Test cases** (`test_device_watchdog.py`)

| Test | Expectation |
|------|-------------|
| `test_stale_device_is_marked_offline_and_logged` | one log row |
| `test_fresh_device_stays_online` | |
| `test_sweep_is_idempotent` | second run adds no row |
| `test_heartbeat_brings_device_back_online_and_logs` | |
| `test_sweep_only_touches_expired_devices` | boundary: exactly at 90 s |
| `test_threshold_is_configurable` | |
| `test_alert_hook_called_once_per_transition` | |
| `test_sweep_does_not_cross_tenants_in_status_endpoint` | managers only see their club |

---

### I. WebSocket POS updates (L) ✅ built

Built as designed, with these deliberate differences: (1) messages are produced by a Session listener on what is really flushed (plus `publish_after_commit` by hand for the watchdog's conditional `UPDATE`), instead of a call in every router, so the POS path, the controller path (I5) and the payment adapter all notify without any call site and none can be forgotten; (2) a super admin joins the chosen `client_id` or its own club (every user has a club, so "none" cannot happen); (3) the socket is accepted and then closed with 1008, so the browser can read the reason; (4) each connection remembers its own event loop, not one global loop; (5) added a `ready` first message. Multi-worker (I7) is the `Realtime` interface plus `set_realtime()`; the Redis version is not built.

The existing `app/utils/connection_manager.py` is built for hardware detection (location/user subscriptions), so do **not** bend it. Add a small billiard manager with one room per `client_id`.

**Design:** messages carry only the **type and ids**; the POS refetches the data it needs. This keeps the server as the only authority and avoids duplicating serializers.

```json
{"type": "table.changed", "table_id": 3, "version": 18271}
{"type": "session.changed", "session_id": 41, "table_id": 3}
{"type": "game.changed", "game_id": 77, "session_id": 41}
{"type": "device.status", "device_id": "BILLIARD-CONTROLLER-01", "status": "offline"}
```

**Tasks**

| # | Task | File |
|---|------|------|
| I1 | `services/realtime.py`: `BilliardRealtime` with `connect/disconnect`, `publish(client_id, message)` (per-tenant room, drops dead sockets) | new |
| I2 | `routes/ws_router.py`: `WS /ws/billiard?token=<JWT>`. Validate the token with the same decoding as `get_current_user`, join the room of the user's `client_id` (SUPER_ADMIN gets a chosen `client_id` or none). Server `ping` every 30 s | new |
| I3 | Publish **after commit**. The routers commit, so add a tiny `publish_after_commit(db, client_id, msg)` that uses the SQLAlchemy `after_commit` event on the session; services stay free of I/O | `services/realtime.py` |
| I4 | Call sites: table start/stop/status/discount/extend/cancel, item added, game start/score/new/finish, controller event batch (one message per touched table), device status change (H) | routers and `controller_router.py` |
| I5 | Controller events produce the same messages as the POS path (put the publish in the lifecycle-calling service, not in the router, only for the controller route) | `controller_router.py` |
| I6 | Keep `GET /tables/active` polling working (fallback). README: document the protocol and the fallback | `README.md` |
| I7 | Multi-worker note: the in-process manager works for one worker. Add a `Realtime` interface so a Redis pub/sub implementation can replace it later without touching callers | `realtime.py` |

**Test cases** (`test_billiard_realtime.py`, uses Starlette `TestClient.websocket_connect`)

| Test | Expectation |
|------|-------------|
| `test_ws_rejects_missing_or_bad_token` | closed with policy violation |
| `test_ws_receives_table_changed_after_start` | |
| `test_ws_not_notified_when_transaction_rolls_back` | publish only after commit |
| `test_ws_message_is_not_sent_to_other_tenant` | two clients, two rooms |
| `test_controller_event_notifies_pos` | score change from device → `game.changed` |
| `test_device_offline_notifies_pos` | needs H |
| `test_dead_socket_is_removed_and_others_still_receive` | |
| `test_multiple_clients_same_tenant_all_receive` | |
| `test_messages_contain_ids_only_no_money_fields` | design rule |
| `test_polling_endpoint_still_works_without_ws` | regression |
| `test_super_admin_room_selection` | |

---

### J. Split bills across rate windows (L), needs a decision

Today one rule is chosen at Start (`billing_service` header comment). A 20:00 to 23:00 session that crosses a 22:00 happy-hour window is billed all at the start rate.

**Proposal:** compute the fee per **segment** and store the breakdown in `pricing_snapshot["segments"]`. Only `per_minute` can be split cleanly. For `hourly`, `block`, `minimum_hour` the meaning of "rounded up" per segment is a business choice.

**Plan:** start with a design spike (J0: one page with 4 worked examples, agreed by the owner). Then:

| # | Task |
|---|------|
| J1 | Config `BILLIARD_SPLIT_RATE_WINDOWS` (default `false`, so nothing changes) |
| J2 | `billing_service.segments(db, table, start, end)`: cut `[start, end]` at every rule window boundary in club-local time (reuse `_matches` / `_to_local`), return `[(segment_start, segment_end, quote)]` |
| J3 | `calculate_fee_segments(...)` in `utils/billing.py`: `per_minute` sums per segment; other types follow the rule chosen in J0 |
| J4 | Freeze the segment breakdown at Stop into `pricing_snapshot`, so old bills never recompute |
| J5 | Bill shows the segment lines |
| J6 | Live total uses the same function as Stop |

**Test cases** (`test_rate_window_split.py`): `test_flag_off_keeps_single_rule_behaviour`, `test_session_inside_one_window_same_as_today`, `test_session_crossing_window_boundary_splits_minutes`, `test_overnight_window_boundary_22_to_02`, `test_day_of_week_boundary_at_midnight`, `test_dst_free_timezone_boundaries_use_club_timezone`, `test_rounding_unit_applied_once_on_total`, `test_segments_survive_rule_edit_after_stop`, `test_live_total_equals_stop_total`, `test_min_billable_minutes_applies_to_whole_session`.

---

### K. RS485 firmware (spec and test harness only in this repo)

Firmware and hardware deployment are **out of scope** (section 5, #9). The architecture is STM32 → RS485 → ESP32-WROOM → Wi-Fi → FastAPI, so there are **two protocols**: the RS485/UART link between the STM32 and the ESP32 (documented here, implemented by the firmware team later), and the existing HTTP event contract between the ESP32 and FastAPI (already built). What the backend repo can own:

| # | Task |
|---|------|
| K0 | `docs/hardware_spec.md`: block diagram from section 5 (STM32, RS485 transceiver, RS485-to-UART transceiver, ESP32-WROOM with CH340), signal and pin list, baud rate and bus settings (to be agreed), power, termination and biasing notes |
| K1 | `docs/controller_protocol.md`: RS485/UART frame format between STM32 and ESP32 (start byte, address, command, length, payload, CRC), button codes, display fields, and how the **ESP32 translates each frame into the event names already supported**. The STM32 never talks to FastAPI: the ESP32 adds `event_id`, `device_seq`, timestamps and the offline queue |
| K2 | `app/tests/device_simulator.py`: a script/class that replays a scripted offline day through `/billiard/controller/sync` (events with `device_seq`, `clock_synced`, local ids) |
| K3 | Contract tests (`test_controller_contract.py`): one JSON fixture per event type that the firmware team can reuse; assert accepted, duplicate, reject and ordering results |
| K4 | Optional frame fixtures (`app/tests/fixtures/rs485_frames.json`): example RS485 frames with their expected backend event, so the ESP32 firmware can be tested against the same table (the frame parser itself is firmware, not backend) |

**Test cases:** `test_every_documented_event_has_a_fixture`, `test_every_documented_frame_maps_to_a_supported_event`, `test_fixtures_validate_against_DeviceEventIn`, `test_simulated_offline_day_replays_to_same_totals_as_pos_path`, `test_replay_after_reboot_resumes_from_server_state_version`.

---

## 3. Cross-cutting test cases (run for every phase)

| Test | Why |
|------|-----|
| Full existing suite stays green (`test_game_service.py`, `test_pricing_sessions.py`, `test_event_service.py`, `test_event_sessions.py`, `test_billiard_payments.py`, `test_payments_*`) | No regression |
| `test_find_inconsistencies_empty_after_each_new_lifecycle_action` | Table/session invariant (reserve, maintenance, cancel, extend, package start) |
| `test_every_new_endpoint_is_tenant_scoped` | One parametrized test over new routes |
| `test_every_new_write_endpoint_has_role_check` | Manager-only where required |
| `test_old_sessions_without_new_columns_still_render_the_bill` | Legacy rows: `package_snapshot`, `discount_reason` null |
| `test_migrations_are_idempotent` | Each `migrate_billiard_*.py` runs twice, second run changes nothing |

Run command (same as the README): `python -m pytest app/tests/test_<file>.py -v`.

---

## 4. Definition of done (per item)

1. Lifecycle function added (not a direct status write), used by POS **and** controller where an event exists.
2. Service with tenant scope, router thin, schema validated.
3. Migration script, idempotent, listed in the deploy notes.
4. Tests from the table above, plus the cross-cutting ones.
5. README updated: section 4 (data model), 5 (rules), 8 (events), 9 (API), 12 (tests), and the row **removed** from section 11.
6. `Frontend Developer Guide Payments & Billiard.md` updated with the new request/response types (use `client_id: string`).

---

## 5. Open questions (decided)

All nine questions are answered. The answers below are the **decisions the plan is built on**. If one changes, the item it belongs to must be re-planned first.

| # | Item | Question | Decision |
|---|------|----------|----------|
| 1 | A | Do reservations need who/when/for-whom (name, phone, time)? | **Status only** (kept as the default). A full reservation feature (name, phone, time, new table) is wanted later, but it is **not** part of item A. See "Follow-up" below |
| 2 | B | Who may cancel, and until when? | **Manager only, active sessions only** |
| 3 | C | Percent or fixed amount? On table fee, products, or both? Manager approval? | **Both allowed (percent or fixed), applied to table + products, manager only** |
| 4 | D | When `ends_at` passes: only flag overtime, or auto-stop and bill? | **Flag only, never auto-stop** |
| 5 | F | Does the package price cover table time only? What is billed after the package time ends? Can one package be used on any table? | **The package price covers table time only.** Products and additional services are charged separately. When the package duration expires, overtime is billed according to the pricing rule assigned to the session. **Any package can be used on any active billiard table**, without table or zone restrictions |
| 6 | F | Included products: free units counted per session, or a fixed free bundle added at start? | **Counted per session as staff add them** |
| 7 | I | One API worker or several in production (Render)? | **Single worker, interface ready for Redis** (several workers need Redis pub/sub) |
| 8 | J | For `hourly`, `block`, `minimum_hour`: how should rounding work across segments? | **Default kept:** design spike first, `per_minute` only until the spike is agreed |
| 9 | K | Who owns the firmware and which MCU/transceiver? | **Spec and simulator only.** Hardware architecture below. Physical firmware development and hardware deployment are excluded from the current scope |

### Hardware architecture (decision 9)

```text
STM32 MCU --(UART)--> RS485 transceiver ==(RS485 differential pair)==> RS485-to-UART transceiver --(UART)--> ESP32-WROOM --(Wi-Fi)--> FastAPI backend
                                                                                                     (CH340 USB-to-UART interface)
```

| Part | Role |
|------|------|
| **STM32 MCU** | Table side: buttons, display, local scores. Talks RS485 through an external transceiver |
| **RS485 (differential)** | The wired link between the STM32 side and the ESP32 side |
| **RS485-to-UART transceiver** | External transceiver on the ESP32 side, converts the bus to UART |
| **ESP32-WROOM** (CH340 USB-to-UART interface) | The "controller" the backend already knows: reads the serial data and sends the events to FastAPI over Wi-Fi (`/billiard/controller/events`, `/sync`) |

**Current project scope for K:** hardware specifications, communication protocol documentation, and the simulator only. The backend contract does not change: the ESP32 keeps the device headers, `device_seq`, `event_id` and offline queue described in README section 8.

### Follow-up (not scheduled): full reservations

Decision 1 keeps item A as a status change. The wanted reservation feature (customer name, phone, date/time, hold period, which table) is a **separate, later item** with its own table, endpoints and tests. When it is planned it will reuse item A's lifecycle functions (`mark_reserved`, `release`) and must handle: overlapping reservations on one table, a no-show timeout that releases the table, and starting a session from a reservation. It is listed here so item A's design does not block it: item A stores no reservation data and adds no column, so nothing has to be undone.

---

## 6. Suggested pull requests

1. `billiard/p0-recompute-totals` (P0)
2. `billiard/table-status` (A)
3. `billiard/session-cancel` (B)
4. `billiard/discount` (C)
5. `billiard/timed-play` (D)
6. `billiard/packages-crud` (E)
7. `billiard/packages-billing` (F)
8. `billiard/device-events` (G)
9. `billiard/device-watchdog` (H)
10. `billiard/realtime` (I)
11. `billiard/rate-window-split` (J, after the decision)
12. `billiard/controller-contract` (K)

One PR per item keeps each review small and each migration separately deployable.
