-- Starter analysis queries for Champaign Lease Intelligence.
-- Run all:  docker compose exec -T db psql -U lease -d leases < src/db/queries.sql

-- 1. How much data do we have? Listings scraped per manager per day.
SELECT m.name AS manager, s.scraped_on, COUNT(*) AS listings
FROM listing_snapshots s
JOIN properties p ON p.id = s.property_id
JOIN managers  m ON m.id = p.manager_id
GROUP BY m.name, s.scraped_on
ORDER BY s.scraped_on DESC, m.name;

-- 2. Typical rent per bed by bedroom count (latest day only).
--    Studios (beds = 0) count as one bed.
WITH latest AS (
    SELECT * FROM listing_snapshots
    WHERE scraped_on = (SELECT MAX(scraped_on) FROM listing_snapshots)
)
SELECT beds,
       COUNT(*) AS listings,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
           ORDER BY CASE WHEN price_basis = 'per_unit'
                         THEN rent / GREATEST(beds, 1) ELSE rent END
       )::numeric, 0) AS median_rent_per_bed
FROM latest
WHERE rent IS NOT NULL AND beds IS NOT NULL
GROUP BY beds
ORDER BY beds;

-- 3. Price changes: listings whose rent differs from their previous snapshot.
WITH ordered AS (
    SELECT external_id, scraped_on, rent,
           LAG(rent) OVER (PARTITION BY external_id ORDER BY scraped_on) AS prev_rent
    FROM listing_snapshots
)
SELECT external_id, scraped_on, prev_rent, rent, rent - prev_rent AS change
FROM ordered
WHERE prev_rent IS NOT NULL AND rent <> prev_rent
ORDER BY scraped_on DESC;

-- 4. Listings that disappeared: seen before, missing from the latest scrape.
--    (A first rough signal that a unit was leased.)
SELECT external_id,
       MIN(scraped_on) AS first_seen,
       MAX(scraped_on) AS last_seen,
       MAX(scraped_on) - MIN(scraped_on) + 1 AS days_listed
FROM listing_snapshots
GROUP BY external_id
HAVING MAX(scraped_on) < (SELECT MAX(scraped_on) FROM listing_snapshots)
ORDER BY last_seen DESC;