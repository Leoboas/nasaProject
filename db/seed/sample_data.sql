INSERT INTO neo_asteroids (
    id, name, absolute_magnitude_h, is_potentially_hazardous_asteroid,
    estimated_diameter_min_km, estimated_diameter_max_km, close_approach_date,
    relative_velocity_km_s, miss_distance_km, orbiting_body
) VALUES (
    '1', 'Asteroid Demo', 22.1, true,
    0.1, 0.2, '2023-10-01',
    5.0, 12345, 'Earth'
) ON CONFLICT (id) DO NOTHING;
