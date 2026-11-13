CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------- reference data ----------
CREATE TABLE districts (
  code          text PRIMARY KEY,            -- 'KA-MANDYA'
  name          text NOT NULL,
  state         text NOT NULL,               -- 'Karnataka'
  agmark_state  text NOT NULL,               -- spelling used by the price API
  agmark_district text NOT NULL,
  default_lang  text NOT NULL CHECK (default_lang IN ('kn','hi','mr'))
);

CREATE TABLE crops (
  code          text PRIMARY KEY,            -- 'ragi'
  name_en       text NOT NULL,
  agmark_name   text NOT NULL,               -- commodity name in the price API
  msp           numeric(10,2),               -- Rs/quintal, NULL if no MSP
  max_listing_qtl numeric(6,2) NOT NULL DEFAULT 50,
  min_price     numeric(10,2) NOT NULL,      -- hard sanity bounds for keypad entry
  max_price     numeric(10,2) NOT NULL
);

CREATE TABLE crop_calendar (                 -- the "seasonal shortlist"
  district_code text REFERENCES districts(code),
  month         smallint CHECK (month BETWEEN 1 AND 12),
  crop_code     text REFERENCES crops(code),
  rank          smallint NOT NULL,           -- 1 = most likely
  PRIMARY KEY (district_code, month, crop_code)
);

CREATE TABLE deduction_rules (               -- AFPP inputs, one row per district
  district_code     text PRIMARY KEY REFERENCES districts(code),
  transport_per_qtl numeric(8,2) NOT NULL,
  handling_per_qtl  numeric(8,2) NOT NULL,
  pct_deduction     numeric(5,4) NOT NULL,   -- e.g. 0.0200 = 2 %
  source_note       text NOT NULL
);

-- ---------- actors ----------
CREATE TABLE fpos (
  id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  district_code text NOT NULL REFERENCES districts(code),
  payee_details text                          -- shown to buyer on the deal note (UPI ID / account)
);

CREATE TABLE collection_points (
  id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fpo_id  uuid NOT NULL REFERENCES fpos(id),
  name    text NOT NULL,
  district_code text NOT NULL REFERENCES districts(code),
  geog    geography(Point,4326) NOT NULL
);
CREATE INDEX collection_points_geog_gix ON collection_points USING GIST (geog);

CREATE TABLE farmers (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone     text NOT NULL UNIQUE,            -- E.164, '+9198...'
  name      text NOT NULL,
  fpo_id    uuid NOT NULL REFERENCES fpos(id),
  village   text NOT NULL,
  district_code text NOT NULL REFERENCES districts(code),
  geog      geography(Point,4326) NOT NULL,  -- village centroid from FPO roster
  collection_point_id uuid NOT NULL REFERENCES collection_points(id),
  lang      text CHECK (lang IN ('kn','hi','mr')),      -- NULL until chosen
  consent_version text,                      -- NULL until consent given
  consent_at timestamptz,
  status    text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','BLOCKED')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX farmers_geog_gix ON farmers USING GIST (geog);

CREATE TABLE agents (
  id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fpo_id   uuid NOT NULL REFERENCES fpos(id),
  name     text NOT NULL,
  phone    text NOT NULL UNIQUE,
  pin_hash text NOT NULL,
  active   boolean NOT NULL DEFAULT true
);

CREATE TABLE buyers (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_name  text NOT NULL,
  email     text NOT NULL UNIQUE,
  password_hash text NOT NULL,
  phone     text NOT NULL,
  license_no text,                           -- APMC trader / GST number, checked by admin
  status    text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','SUSPENDED')),
  strikes   smallint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- prices ----------
CREATE TABLE mandi_prices (
  id bigserial PRIMARY KEY,
  district_code text NOT NULL REFERENCES districts(code),
  crop_code  text NOT NULL REFERENCES crops(code),
  market     text NOT NULL,
  price_date date NOT NULL,
  min_price  numeric(10,2), max_price numeric(10,2),
  modal_price numeric(10,2) NOT NULL,
  source     text NOT NULL,                  -- 'data.gov.in' | 'seed'
  fetched_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (district_code, crop_code, market, price_date)
);

CREATE TABLE price_floors (                  -- one row per district x crop x day
  district_code text NOT NULL REFERENCES districts(code),
  crop_code  text NOT NULL REFERENCES crops(code),
  as_of      date NOT NULL,                  -- the day the floor was computed for
  price_date date,                           -- date of the newest price used
  modal_price numeric(10,2) NOT NULL,
  afpp       numeric(10,2) NOT NULL,
  basis      text NOT NULL CHECK (basis IN ('DISTRICT_FRESH','DISTRICT_7D','STATE_7D')),
  PRIMARY KEY (district_code, crop_code, as_of)
);

-- ---------- marketplace ----------
CREATE TABLE clusters (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code      serial UNIQUE,                   -- short human id, 'C-104'
  collection_point_id uuid NOT NULL REFERENCES collection_points(id),
  crop_code text NOT NULL REFERENCES crops(code),
  status    text NOT NULL DEFAULT 'OPEN' CHECK (status IN
            ('OPEN','READY','BIDDING','CONFIRMING','DEAL','CLOSED','NO_BID','FAILED')),
  total_qtl numeric(8,2) NOT NULL DEFAULT 0,
  listing_count int NOT NULL DEFAULT 0,
  min_ask   numeric(10,2),
  wavg_ask  numeric(10,2),
  grade     text CHECK (grade IN ('A','B','C')),
  bidding_ends_at timestamptz,
  best_bid_id uuid,
  version   int NOT NULL DEFAULT 0,
  opened_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
-- at most one joinable cluster per pickup point and crop
CREATE UNIQUE INDEX clusters_one_joinable
  ON clusters (collection_point_id, crop_code) WHERE status IN ('OPEN','READY');

CREATE TABLE call_sessions (                 -- durable checkpoint of the Redis session
  id        uuid PRIMARY KEY,
  phone     text NOT NULL,
  farmer_id uuid REFERENCES farmers(id),
  kind      text NOT NULL CHECK (kind IN ('LISTING','BID_OFFER','PROXY_CONFIRM','UNKNOWN_CALLER')),
  provider  text NOT NULL CHECK (provider IN ('sim','exotel','asterisk')),
  provider_call_id text,
  state     text NOT NULL,
  data      jsonb NOT NULL DEFAULT '{}',
  version   int NOT NULL DEFAULT 0,
  outcome   text,                            -- 'COMPLETED','DROPPED','FAILED_INPUT','EXPIRED'
  started_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  ended_at  timestamptz
);
CREATE INDEX call_sessions_phone_idx ON call_sessions (phone, updated_at DESC);

CREATE TABLE listings (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code      serial UNIQUE,                   -- spoken to the farmer digit by digit
  farmer_id uuid NOT NULL REFERENCES farmers(id),
  cluster_id uuid NOT NULL REFERENCES clusters(id),
  crop_code text NOT NULL REFERENCES crops(code),
  qty_qtl   numeric(6,2) NOT NULL CHECK (qty_qtl > 0),
  ask_price numeric(10,2) NOT NULL CHECK (ask_price > 0),
  afpp_at_listing numeric(10,2),
  guardrail text NOT NULL DEFAULT 'NONE' CHECK (guardrail IN ('NONE','RAISED','KEPT_BELOW','NO_PRICE_DATA')),
  source    text NOT NULL CHECK (source IN ('IVR','AGENT_PROXY')),
  session_id uuid UNIQUE REFERENCES call_sessions(id),   -- idempotency: one listing per call session
  status    text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN
            ('PENDING_CONFIRM','ACTIVE','ACCEPTED','SOLD','WITHDRAWN','EXPIRED')),
  actual_qtl numeric(6,2),                   -- weighed at pickup
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL DEFAULT now() + interval '7 days'
);
-- one live listing per farmer per crop
CREATE UNIQUE INDEX listings_one_live ON listings (farmer_id, crop_code)
  WHERE status IN ('PENDING_CONFIRM','ACTIVE','ACCEPTED');
CREATE INDEX listings_cluster_idx ON listings (cluster_id);

CREATE TABLE verifications (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cluster_id uuid NOT NULL UNIQUE REFERENCES clusters(id),
  agent_id  uuid NOT NULL REFERENCES agents(id),
  grade     text NOT NULL CHECK (grade IN ('A','B','C','REJECT')),
  moisture_pct numeric(4,1),
  photo_path text NOT NULL,
  geog      geography(Point,4326) NOT NULL,
  accuracy_m numeric(8,1),
  distance_m numeric(8,1) NOT NULL,          -- to the collection point, computed server-side
  captured_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE bids (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cluster_id uuid NOT NULL REFERENCES clusters(id),
  buyer_id  uuid NOT NULL REFERENCES buyers(id),
  price_per_qtl numeric(10,2) NOT NULL CHECK (price_per_qtl > 0),
  min_qty_qtl numeric(8,2) NOT NULL CHECK (min_qty_qtl > 0),
  status    text NOT NULL DEFAULT 'LEADING' CHECK (status IN
            ('LEADING','OUTBID','CONFIRMING','DEAL','FAILED','CANCELLED')),
  idempotency_key text NOT NULL,
  confirm_deadline timestamptz,              -- set when the bid enters CONFIRMING
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (buyer_id, idempotency_key)
);
CREATE INDEX bids_cluster_idx ON bids (cluster_id, price_per_qtl DESC);
ALTER TABLE clusters ADD CONSTRAINT clusters_best_bid_fk FOREIGN KEY (best_bid_id) REFERENCES bids(id);

CREATE TABLE call_jobs (                     -- durable outbound-call queue
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone     text NOT NULL,
  farmer_id uuid REFERENCES farmers(id),
  kind      text NOT NULL CHECK (kind IN ('CALLBACK','BID_OFFER','PROXY_CONFIRM')),
  payload   jsonb NOT NULL DEFAULT '{}',
  status    text NOT NULL DEFAULT 'QUEUED' CHECK (status IN
            ('QUEUED','DIALING','IN_CALL','DONE','FAILED','CANCELLED')),
  attempts  smallint NOT NULL DEFAULT 0,
  max_attempts smallint NOT NULL DEFAULT 3,
  run_at    timestamptz NOT NULL DEFAULT now(),
  dedupe_key text NOT NULL UNIQUE,           -- e.g. 'bid:{bid_id}:{listing_id}'
  provider_call_id text,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX call_jobs_due_idx ON call_jobs (run_at) WHERE status = 'QUEUED';

CREATE TABLE bid_responses (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_id    uuid NOT NULL REFERENCES bids(id),
  listing_id uuid NOT NULL REFERENCES listings(id),
  response  text NOT NULL DEFAULT 'PENDING' CHECK (response IN ('PENDING','ACCEPT','REJECT','NO_ANSWER')),
  responded_at timestamptz,
  UNIQUE (bid_id, listing_id)
);

CREATE TABLE deals (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cluster_id uuid NOT NULL UNIQUE REFERENCES clusters(id),
  bid_id    uuid NOT NULL UNIQUE REFERENCES bids(id),
  buyer_id  uuid NOT NULL REFERENCES buyers(id),
  qty_qtl   numeric(8,2) NOT NULL,
  price_per_qtl numeric(10,2) NOT NULL,
  gross_value numeric(12,2) NOT NULL,
  platform_fee numeric(12,2) NOT NULL,       -- 1.5 % of gross, invoiced to buyer
  status    text NOT NULL DEFAULT 'CONFIRMED' CHECK (status IN
            ('CONFIRMED','PAYMENT_REPORTED','PAID','PICKED_UP','DISPUTED','CANCELLED')),
  pickup_by date NOT NULL,
  payment_ref text,                          -- UTR typed by buyer
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ledger (
  id       bigserial PRIMARY KEY,
  deal_id  uuid NOT NULL REFERENCES deals(id),
  entry    text NOT NULL CHECK (entry IN ('PLATFORM_FEE','FPO_VERIFICATION_FEE')),
  amount   numeric(12,2) NOT NULL,
  status   text NOT NULL DEFAULT 'DUE' CHECK (status IN ('DUE','PAID','VOID')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (deal_id, entry)
);

-- ---------- support, audit, realtime ----------
CREATE TABLE triage_tickets (
  id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone    text NOT NULL,
  farmer_id uuid REFERENCES farmers(id),
  reason   text NOT NULL CHECK (reason IN ('IVR_FAIL_3','UNKNOWN_CALLER','HELP_KEY')),
  status   text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','ASSIGNED','RESOLVED')),
  agent_id uuid REFERENCES agents(id),
  verbal_code char(2),                       -- told to the farmer by IVR, shown to agent only at bridge time
  code_expires_at timestamptz,
  code_used boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX triage_one_open ON triage_tickets (phone) WHERE status IN ('OPEN','ASSIGNED');

CREATE TABLE consent_log (
  id bigserial PRIMARY KEY,
  farmer_id uuid NOT NULL REFERENCES farmers(id),
  version text NOT NULL, lang text NOT NULL,
  session_id uuid NOT NULL, digit char(1) NOT NULL,
  at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE dtmf_events (                   -- evidence trail for every commercial keypress
  id bigserial PRIMARY KEY,
  session_id uuid NOT NULL,
  event_id text NOT NULL,
  state_before text NOT NULL, digits text NOT NULL, state_after text NOT NULL,
  dropped_reason text,                       -- 'BOUNCE','DUPLICATE_EVENT','OUT_OF_RANGE', NULL if applied
  at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, event_id)
);

CREATE TABLE events (                        -- outbox: source for WebSocket fan-out and replay
  seq bigserial PRIMARY KEY,
  type text NOT NULL,
  audience text NOT NULL DEFAULT 'all' CHECK (audience IN ('all','buyer','agent','ops')),
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
