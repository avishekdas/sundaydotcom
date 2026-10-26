-- 0005 — partition DDL must never queue behind a long transaction and stall writes (M0B-9).
alter function tl.ensure_partitions(regclass, date, int, text) set lock_timeout = '5s';
alter function tl.drop_partitions_older_than(regclass, int) set lock_timeout = '5s';
