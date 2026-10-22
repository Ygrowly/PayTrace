# PayTrace Domain Model

## Canonical Payment Event

All analytics data maps to a single event model (`paytrace.event.v1`):

| Field | Type | Notes |
|-------|------|-------|
| event_id | str | Unique per event |
| event_time | datetime | UTC |
| purchase_intent_id | str | Links cancel→reorder chains |
| order_id | str | Order identifier |
| event_type | EventType | FUNNEL_PROGRESSION, ORDER_CANCELLED, REORDERED, PAYMENT_METHOD_SWITCHED, PAYMENT_FAILED, PAYMENT_TIMEOUT, AUTH_FAILED, CALLBACK_EXCEPTION, CONFIG_CHANGE |
| funnel_stage | FunnelStage? | Set only for FUNNEL_PROGRESSION events |
| status | EventStatus | success, failed, timeout, cancelled |
| payment_method | str? | card, wallet, bank_transfer |
| payment_channel | str? | channel_a, channel_b, channel_c |
| region | str | CN, US, EU |
| currency | str | CNY, USD, EUR |
| order_amount_minor | int | Minimum currency unit (no floats) |
| selected_payable_minor | int? | Actual payable after discounts |
| best_payable_minor | int? | Best available payable |
| benefit_id | str? | Discount/benefit identifier |
| error_code | str? | Error code for failed events |
| latency_ms | int? | Payment event latency |

## Funnel (9 stages)

```text
ORDER_CONFIRMED → CHECKOUT_ENTERED → PAYMENT_OPTIONS_SHOWN
→ PAYMENT_METHOD_SELECTED → PAYMENT_INITIATED → AUTHENTICATION_PASSED
→ CHANNEL_SUCCEEDED → PLATFORM_CONFIRMED → PAYMENT_COMPLETED
```

Cancellation, reorder, and payment failure are branch events, not primary funnel stages.

## Core metrics (per incident period)

| Metric | Definition |
|--------|-----------|
| Payment completion count | Intents reaching PAYMENT_COMPLETED |
| Payment completion rate | Completed / ORDER_CONFIRMED |
| Stage step rate | Reached stage N / reached stage N-1 |
| Estimated lost intents | Observational estimate vs baseline rates |
| Benefit gap | selected_payable - best_payable (minor units) |
| Cancel rate | Cancelled intents / total intents |
| Reorder recovery rate | Recovered / reordered |

## Root cause labels (Ontology-enforced)

```text
BENEFIT_SELECTION_FRICTION  — discount/benefit UX friction
AUTHENTICATION_FAILURE       — 3DS, risk rejection
CHANNEL_TIMEOUT              — payment channel latency/timeout
CALLBACK_FAILURE             — webhook/signature issues
NORMAL_PAYMENT_FAILURE       — expected business failures (insufficient balance, expired card)
DATA_QUALITY_ISSUE           — missing events or fields
UNKNOWN                      — anomaly detected but no pattern matched
```

## Evidence types (7 kinds)

```text
FUNNEL_STAGE_DEGRADATION  — stage conversion dropped vs baseline
DIMENSION_CONTRIBUTION    — a dimension segment disproportionately affected
BENEFIT_GAP_FRICTION      — benefit gap shifted (observational, not causal)
CHANNEL_TIMEOUT           — timeout count + latency surge
ERROR_CODE_CONCENTRATION  — specific error codes dominate failures
CANCEL_REORDER_FLOW       — cancel → reorder → switch → recovery flow changed
CONFIG_CHANGE             — promo/routing/risk/version changes near incident
```

## Incident lifecycle

```text
DETECTED → INVESTIGATING → ACTION_REQUIRED → MONITORING → RESOLVED
```

## DiagnosisRun lifecycle

```text
PENDING → DISPATCH_FAILED → QUEUED → RUNNING
→ COLLECTING_EVIDENCE → GENERATING_REPORT → VALIDATING
→ SUCCEEDED | NEEDS_DATA | FAILED | CANCELLED
```

Stale non-terminal runs (>5 min without update) are force-failed by the 3-layer recovery mechanism.
