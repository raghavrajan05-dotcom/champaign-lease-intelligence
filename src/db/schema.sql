-- Champaign Lease Intelligence: schema v0
-- Listings are stored as daily snapshots (append-only) so price changes
-- and time-on-market can be measured later.

CREATE TABLE IF NOT EXISTS managers (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    website     TEXT,
    platform    TEXT              -- e.g. 'appfolio', 'custom'
);

CREATE TABLE IF NOT EXISTS properties (
    id              SERIAL PRIMARY KEY,
    manager_id      INT NOT NULL REFERENCES managers(id),
    address         TEXT NOT NULL,
    city            TEXT,
    zip             TEXT,
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    dist_to_quad_mi DOUBLE PRECISION,
    UNIQUE (manager_id, address)
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id           SERIAL PRIMARY KEY,
    manager_id   INT NOT NULL REFERENCES managers(id),
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    status       TEXT CHECK (status IN ('running', 'success', 'failed')),
    n_listings   INT,
    error        TEXT
);

CREATE TABLE IF NOT EXISTS listing_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    run_id          INT NOT NULL REFERENCES scrape_runs(id),
    property_id     INT NOT NULL REFERENCES properties(id),
    external_id     TEXT NOT NULL,     -- the manager's own listing id
    scraped_on      DATE NOT NULL DEFAULT CURRENT_DATE,
    rent            NUMERIC(8,2),
    price_basis     TEXT CHECK (price_basis IN ('per_bed', 'per_unit')),
    beds            SMALLINT,
    baths           NUMERIC(3,1),      -- allows 1.5
    sqft            INT,
    available_date  DATE,
    furnished       BOOLEAN,
    url             TEXT,
    raw_hash        TEXT,              -- hash of saved raw HTML
    UNIQUE (external_id, scraped_on)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_scraped_on ON listing_snapshots (scraped_on);
CREATE INDEX IF NOT EXISTS idx_snapshots_property  ON listing_snapshots (property_id);
