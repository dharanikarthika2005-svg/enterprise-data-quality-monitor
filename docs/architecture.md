# Architecture notes

## Module responsibilities

| Module | Responsibility | Depends on |
|---|---|---|
| `src/config.py` | Single source of policy: required columns, allowed values, patterns, alert thresholds | — |
| `src/ingestion.py` | Extract. File checks, checksum, CSV parsing, malformed-line handling | config, transformation |
| `src/transformation.py` | Column standardisation, text cleaning, derived `line_revenue` and `month` | pandas |
| `src/validation.py` | Rule catalogue (`RULES`), per-record checks, duplicate detection, status assignment, error report | config |
| `src/database.py` | Schema, connections, `transaction()` context manager, reads and writes | config |
| `src/pipeline.py` | ETL orchestration and batch lifecycle (Pending → Processing → Completed / Completed with Issues / Failed) | everything in `src/` above |
| `src/metrics.py` | Pure functions turning counts into rates with explicit denominators | — |
| `src/monitoring.py` | Threshold alerts, batch comparison, trend frames, pooled quality | config, metrics |
| `src/analytics.py` | Parameterised SQL over `sales` | database (connection passed in) |
| `dashboard/*` | Streamlit presentation only | src/* |

## Key decisions

1. **Status precedence.** Each record has one status: duplicate > rejected > flagged > accepted. Counts therefore partition the batch, and rates cannot be double-counted.
2. **Audit before load.** The batch row is committed as `Processing` before validation starts, so a crash leaves a visible record.
3. **Single load transaction.** Staged records, issues, sales rows and final totals are written together. Failure rolls back everything, then the batch is marked `Failed` in a separate transaction.
4. **Database constraints as the last line of defence.** The `UNIQUE` constraint on `sales.order_id` and the `CHECK` constraints on quantity and price hold even if Python-side checks are bypassed.
5. **No silent correction.** Raw values are stored in `staged_records.raw_json`. Values are parsed for validation, but the original text is never changed.
6. **Pure metrics.** Rates are computed from stored counts, so they can be recalculated later without re-reading files.
7. **Reusable logic.** The dashboard and the tests call the same `process_file()` function.

## Batch status lifecycle

```
Processing ──► Completed                (no rejected, flagged or duplicate records)
     │   └──► Completed with Issues     (at least one rejected, flagged or duplicate record)
     └──────► Failed                    (file-structure error or database/unexpected error; no sales kept)
```
