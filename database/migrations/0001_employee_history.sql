-- ===================================================================
-- employee_history: audit-trail / event-log for every significant
-- change to an employee. One row per event.
--
-- Supported event_type values (enforced by CHECK):
--   hired, promoted, transferred, department_changed,
--   position_changed, status_changed, salary_changed,
--   created, updated, reactivated, deactivated, deleted
--
-- from_value / to_value are free-form TEXT so any attribute can be
-- captured. Both are nullable because some events (e.g. "hired",
-- "created") have no "from" value.
-- ===================================================================

CREATE TABLE IF NOT EXISTS employee_history (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id     BIGINT,
    employee_no     TEXT   NOT NULL,
    event_type      TEXT   NOT NULL,
    from_value      TEXT,
    to_value        TEXT,
    field           TEXT,
    note            TEXT,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT employee_history_event_type_chk CHECK (
        event_type IN (
            'hired',
            'promoted',
            'transferred',
            'department_changed',
            'position_changed',
            'status_changed',
            'salary_changed',
            'created',
            'updated',
            'reactivated',
            'deactivated',
            'deleted'
        )
    )
);

-- Index for the common per-employee timeline query.
CREATE INDEX IF NOT EXISTS idx_employee_history_employee
    ON employee_history (employee_no, occurred_at DESC);

-- Index for the stall-detection / "time since last promotion" query.
CREATE INDEX IF NOT EXISTS idx_employee_history_event_type
    ON employee_history (event_type, occurred_at DESC);

-- Foreign key to employees. Deferred so service-layer writes can
-- insert the history row in a separate round-trip without ordering
-- surprises.
ALTER TABLE employee_history
    DROP CONSTRAINT IF EXISTS fk_employee_history_employee;
ALTER TABLE employee_history
    ADD CONSTRAINT fk_employee_history_employee
    FOREIGN KEY (employee_no)
    REFERENCES employees (employee_no)
    ON DELETE CASCADE;

-- Helpful Row-Level Security pattern (optional; safe no-op if RLS
-- is not enabled).
ALTER TABLE employee_history ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS employee_history_read_all ON employee_history;
CREATE POLICY employee_history_read_all ON employee_history
    FOR SELECT USING (true);
DROP POLICY IF EXISTS employee_history_write_all ON employee_history;
CREATE POLICY employee_history_write_all ON employee_history
    FOR ALL USING (true) WITH CHECK (true);
