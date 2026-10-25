# scheduler-tick not running / errors
The tick creates partitions ahead (7 days) and drops expired ones. If it stops, writes fail when the partition horizon runs out (about a week).
1. Check the `tasklane-<stage>-tickSchedule` schedule is enabled (dev: hourly 08:00–19:00 New York time, D-037 — no ticks overnight is expected) and the schedules DLQ is empty.
2. Check the function's errors and reserved concurrency (1).
3. Run it once manually (`aws lambda invoke --function-name tasklane-<stage>-scheduler-tick out.json`) and confirm `created`/`dropped` in the output.
