# Champaign Lease Intelligence

**Live site: https://champaign-leases.streamlit.app**

A daily-updated tracker of off-campus rentals near UIUC. Every morning it reads each
property manager's public listings page, converts prices to dollars per bed per month,
checks the data, and publishes it to the site with distance to campus landmarks.

## How it works
1. **Scrape**: `src/scrapers/` (one module per listing platform) saves a CSV per manager per day.
2. **Normalize**: `src/normalize.py` maps every manager to the same columns.
3. **Check**: `src/quality.py` runs volume, schema, completeness, validity, uniqueness and
   freshness checks; a failure flags the daily run.
4. **Locate**: `src/geo/` geocodes addresses (US Census geocoder) and measures distance.
5. **Publish**: a GitHub Actions job (`.github/workflows/daily-scrape.yml`) commits the CSVs to
   the `data` branch; the Streamlit site (`app/`) reads them.
6. **Analyze**: `src/warehouse.py` builds a DuckDB star schema; `src/db/` loads Postgres.

Green Street Realty prices are used with their permission.

## Run locally
```
pip install -r requirements.txt
bash scripts/sync_data.sh          # copy the published data locally
streamlit run app/streamlit_app.py
pytest -q
```
