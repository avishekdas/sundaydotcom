# scheduler-tick not running / errors
The tick creates partitions ahead (7 days) and drops expired ones. If it stops, writes fail when the partition horizon runs out (about a week).
1. Check the `tasklane-<stage>-tickEveryMinute` schedule is enabled and the schedules DLQ is empty.
2. Check the function's errors and reserved concurrency (1).
3. Run it once manually (`aws lambda invoke --function-name tasklane-<stage>-scheduler-tick out.json`) and confirm `created`/`dropped` in the output.
