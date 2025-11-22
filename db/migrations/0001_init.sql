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
