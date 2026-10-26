-- 0006 — the audit store is appended only through tl_audit_writer (arch 07 §7.3, D-056).
-- Runs as tl_migrator (owner of all tl objects). tl_audit_writer keeps INSERT (0001) and sequence usage.
revoke insert on tl.audit_events from tl_api_rw;
