-- Reference seed data for Annadata Dhwani
-- Requires psql variables: -v venue_lat=.. -v venue_lon=..

-- 1. Districts
INSERT INTO districts (code, name, state, agmark_state, agmark_district, default_lang)
VALUES
    ('KA-MANDYA', 'Mandya', 'Karnataka', 'Karnataka', 'Mandya', 'kn'),
    ('KA-MYSURU', 'Mysuru', 'Karnataka', 'Karnataka', 'Mysore', 'kn')
ON CONFLICT DO NOTHING;

-- 2. Crops
INSERT INTO crops (code, name_en, agmark_name, msp, max_listing_qtl, min_price, max_price)
VALUES
    ('ragi', 'Ragi', 'Ragi (Finger Millet)', 5205, 50, 1500, 9000),
    ('paddy_common', 'Paddy', 'Paddy(Dhan)(Common)', 2441, 50, 1000, 5000),
    ('maize', 'Maize', 'Maize', 2410, 50, 1000, 5000)
ON CONFLICT DO NOTHING;

-- 3. Crop Calendar (Months 10, 11, 12 for both districts)
INSERT INTO crop_calendar (district_code, month, crop_code, rank)
VALUES
    ('KA-MANDYA', 10, 'ragi', 1),
    ('KA-MANDYA', 10, 'paddy_common', 2),
    ('KA-MANDYA', 10, 'maize', 3),
    ('KA-MANDYA', 11, 'ragi', 1),
    ('KA-MANDYA', 11, 'paddy_common', 2),
    ('KA-MANDYA', 11, 'maize', 3),
    ('KA-MANDYA', 12, 'ragi', 1),
    ('KA-MANDYA', 12, 'paddy_common', 2),
    ('KA-MANDYA', 12, 'maize', 3),
    ('KA-MYSURU', 10, 'ragi', 1),
    ('KA-MYSURU', 10, 'paddy_common', 2),
    ('KA-MYSURU', 10, 'maize', 3),
    ('KA-MYSURU', 11, 'ragi', 1),
    ('KA-MYSURU', 11, 'paddy_common', 2),
    ('KA-MYSURU', 11, 'maize', 3),
    ('KA-MYSURU', 12, 'ragi', 1),
    ('KA-MYSURU', 12, 'paddy_common', 2),
    ('KA-MYSURU', 12, 'maize', 3)
ON CONFLICT DO NOTHING;

-- 4. Deduction Rules
INSERT INTO deduction_rules (district_code, transport_per_qtl, handling_per_qtl, pct_deduction, source_note)
VALUES
    ('KA-MANDYA', 50, 10, 0.0200, 'assumed; confirm with FPO'),
    ('KA-MYSURU', 50, 10, 0.0200, 'assumed; confirm with FPO')
ON CONFLICT DO NOTHING;

-- 5. FPO
INSERT INTO fpos (id, name, district_code, payee_details)
VALUES
    ('00000000-0000-0000-0000-000000000001', 'Keregodu Farmer Producer Company', 'KA-MANDYA', 'UPI keregodu-fpo@bank (demo)')
ON CONFLICT DO NOTHING;

-- 6. Collection Points
INSERT INTO collection_points (id, fpo_id, name, district_code, geog)
VALUES
    ('00000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000001', 'Keregodu FPO yard', 'KA-MANDYA', ST_SetSRID(ST_MakePoint(76.9200, 12.6300), 4326)::geography),
    ('00000000-0000-0000-0000-000000000012', '00000000-0000-0000-0000-000000000001', 'Hosahalli point', 'KA-MANDYA', ST_SetSRID(ST_MakePoint(76.8800, 12.5800), 4326)::geography),
    ('00000000-0000-0000-0000-000000000013', '00000000-0000-0000-0000-000000000001', 'Venue demo point', 'KA-MANDYA', ST_SetSRID(ST_MakePoint(:venue_lon, :venue_lat), 4326)::geography)
ON CONFLICT DO NOTHING;

-- 7. Agents
INSERT INTO agents (id, fpo_id, name, phone, pin_hash, active)
VALUES
    ('00000000-0000-0000-0000-000000000021', '00000000-0000-0000-0000-000000000001', 'Kavya', '+919800000101', '<HASH_PIN>', true),
    ('00000000-0000-0000-0000-000000000022', '00000000-0000-0000-0000-000000000001', 'Suresh', '+919800000102', '<HASH_PIN>', true)
ON CONFLICT DO NOTHING;

-- 8. Buyers
INSERT INTO buyers (id, org_name, email, password_hash, status)
VALUES
    ('00000000-0000-0000-0000-000000000031', 'Mysuru Grain Traders', 'buyer1@demo.test', '<HASH_PW>', 'APPROVED'),
    ('00000000-0000-0000-0000-000000000032', 'Mandya Agro Foods', 'buyer2@demo.test', '<HASH_PW>', 'APPROVED'),
    ('00000000-0000-0000-0000-000000000033', 'Admin', 'admin@demo.test', '<HASH_PW>', 'APPROVED')
ON CONFLICT DO NOTHING;
