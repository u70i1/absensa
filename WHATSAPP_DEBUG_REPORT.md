# WhatsApp debug report — 25 September 2026

Validated against source code, read-only application database queries, host
processes, and tests. Database snapshot: approximately **07:20 WIB**.
The actual table name is `whatsapp_notification_logs`.

## 1. Timestamps: timezone display difference, no corruption found

The application uses `Asia/Jakarta`; the inspected PostgreSQL connection uses
`UTC`. All three log timestamp columns are `timestamp with time zone`.
For example, today's run was created at `00:11:33+00:00`, which is correctly
`07:11:33 WIB`. No stored log dates disagreed with their Jakarta creation dates.
Tests also confirmed that scheduling and attendance-day boundaries use Jakarta,
including when the same instant falls on the previous UTC date.

Display timestamps in Jakarta in the database viewer or use the query below;
do not add seven hours to stored values. PostgreSQL converts timestamp display
using the connection timezone ([documentation](https://www.postgresql.org/docs/current/datatype-datetime.html#DATATYPE-DATETIME-TIMEZONE)).

## 2. Automatic sending: scheduler process missing

The inspected host was running Uvicorn, but no
`app.jobs.whatsapp_notifications` process. FastAPI does not start that job,
and Compose starts only PostgreSQL. `/admin/whatsapp/daily` refreshes UI state;
it does not execute scheduled notifications.

At inspection, automatic service was enabled, send time was **07:10**, and
attendance was **3**, above the configured minimum of **2**. Today's existing
run was explicitly marked `manual`. This supports a missing scheduler, rather
than timezone or minimum attendance, as the cause of manual-only operation.

Remedy: keep one separate scheduler process running under a process manager,
with automatic restart, alongside FastAPI and the WhatsApp bridge:

```bash
cd web
.venv/bin/python -m app.jobs.whatsapp_notifications
```

The [job](web/app/jobs/whatsapp_notifications.py) polls every 30 seconds.
Starting it can send real messages; it was not started during this audit.
Later logs supplied by the user show the job running. Its subsequent failure
was a `502` from the WhatsApp bridge, not a missed schedule.

## 3. IDs: unordered query results plus normal sequence gaps

The unsorted query returned IDs such as `6, 14, 8, 11, 12, 5`.
With `ORDER BY id`, they were ascending. SQL guarantees no default row order
([documentation](https://www.postgresql.org/docs/current/queries-order.html)).

There were 12 rows with IDs ranging from 1 to 15; the sequence increments by 1.
A focused test confirmed that a duplicate `_claim()` consumes a sequence value
without inserting a duplicate delivery. Rollbacks can also leave gaps
([documentation](https://www.postgresql.org/docs/current/functions-sequence.html)).
The IDs are unique, not random or broken; they do not need renumbering.

```sql
SELECT id, day, kind, status,
       created_at AT TIME ZONE 'Asia/Jakarta' AS created_at_wib
FROM whatsapp_notification_logs
ORDER BY id;
```

## Additional confirmed bug: unnecessary Safe Mode waits

In [`run_daily()`](web/app/services/whatsapp_notification_service.py), the delay
runs before checking whether the next student has a guardian number or an
existing delivery claim. Once one send is attempted, every subsequent skipped
student can cost another 30 seconds. This prolongs `running` state and FastAPI's
wait for manual background tasks during shutdown.

Reproduction: one recipient followed by three students without contacts sent
one message but requested delays of `[30, 30, 30]`. The service now applies
throttling only between eligible send attempts, while retaining the final
attendance check and atomic duplicate protection.

At the time of the audit, 29 existing tests passed and a focused diagnostic
reproduced the Safe Mode bug. The later fix passed 33 focused Python tests and
10 bridge tests using fake sends. The separate bridge `502` cause still needs
diagnosis from its own process logs; the application now pauses the daily job
and shows affected deliveries instead of silently marking the day successful.
