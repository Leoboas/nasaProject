CREATE TABLE IF NOT EXISTS asteroides_monitoria (
    id TEXT NOT NULL,
    name TEXT,
    close_approach_date DATE NOT NULL,
    absolute_magnitude_h DOUBLE PRECISION,
    relative_velocity_km_s DOUBLE PRECISION,
    miss_distance_km DOUBLE PRECISION,
    alert_tag TEXT,
    is_potentially_hazardous_asteroid BOOLEAN NOT NULL DEFAULT FALSE,
    details_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, close_approach_date)
);

CREATE INDEX IF NOT EXISTS idx_asteroides_monitoria_close_approach_date
    ON asteroides_monitoria (close_approach_date DESC);

CREATE INDEX IF NOT EXISTS idx_asteroides_monitoria_hazardous
    ON asteroides_monitoria (is_potentially_hazardous_asteroid)
    WHERE is_potentially_hazardous_asteroid;
