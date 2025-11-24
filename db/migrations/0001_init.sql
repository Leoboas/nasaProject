CREATE TABLE IF NOT EXISTS neo_asteroids (
    id TEXT PRIMARY KEY,
    name TEXT,
    absolute_magnitude_h DOUBLE PRECISION,
    is_potentially_hazardous_asteroid BOOLEAN,
    estimated_diameter_min_km DOUBLE PRECISION,
    estimated_diameter_max_km DOUBLE PRECISION,
    close_approach_date DATE,
    relative_velocity_km_s DOUBLE PRECISION,
    miss_distance_km DOUBLE PRECISION,
    orbiting_body TEXT
);

-- Tabela dedicada à monitoria de asteroides relevantes (hazard/atlas/3i)
CREATE TABLE IF NOT EXISTS asteroides_monitoria (
    id TEXT NOT NULL,
    name TEXT,
    close_approach_date DATE,
    absolute_magnitude_h DOUBLE PRECISION,
    relative_velocity_km_s DOUBLE PRECISION,
    miss_distance_km DOUBLE PRECISION,
    alert_tag TEXT,
    is_potentially_hazardous_asteroid BOOLEAN,
    details_json JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (id, close_approach_date)
);

-- Limpeza de dados antigos (manter 90 dias)
DELETE FROM asteroides_monitoria
WHERE close_approach_date < CURRENT_DATE - INTERVAL '90 days';
