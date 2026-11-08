-- Persistent ordering/episode state. Existing bindings stay disabled/unchanged.
CREATE TABLE IF NOT EXISTS rule_runtime (
    source_device_id INTEGER PRIMARY KEY REFERENCES devices(id),
    state JSON NOT NULL
);
