import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Let the app import our own code from src/ (needed for `streamlit run` and for hosting).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.geo.geocode import attach_distance, load_cache, load_remote_cache  # noqa: E402
from src.normalize import (  # noqa: E402
    REMOTE_BASE, load_all, load_latest_remote, load_unpriced_buildings,
)

st.set_page_config(page_title="Champaign Lease Intelligence", layout="wide")


@st.cache_data(ttl=3600)  # re-read at most once an hour
def get_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(priced listings, price-free buildings), both with distance to the Quad."""
    local = load_all()
    if not local.empty:  # running on your laptop with data/ synced
        listings, cache = local, load_cache()
    else:  # hosted: no data/ folder, so read the public daily files from GitHub
        listings, cache = load_latest_remote(), load_remote_cache(REMOTE_BASE)
    return attach_distance(listings, cache), attach_distance(load_unpriced_buildings(), cache)


df, buildings = get_data()

st.title("Champaign Lease Intelligence")

if df.empty:
    st.warning("No data yet. Run the scrapers or: bash scripts/sync_data.sh")
    st.stop()

updated = df.groupby("manager")["scraped_on"].max()
st.caption("Last updated: " + " · ".join(f"{m} {d}" for m, d in updated.items()))

# ---- sidebar filters ----
managers = sorted(df["manager"].unique())
chosen = st.sidebar.multiselect("Property manager", managers, default=managers)

priced = df[df["rent_per_bed_min"].notna()]
lo, hi = int(priced["rent_per_bed_min"].min()), int(priced["rent_per_bed_min"].max())
max_rent = st.sidebar.slider("Max rent per bed ($/mo)", lo, hi, hi, step=25)
show_unpriced = st.sidebar.checkbox("Include listings with no listed price", value=False)

max_miles = st.sidebar.selectbox(
    "Max distance to Main Quad", ["Any", 0.5, 1.0, 1.5, 2.0],
    format_func=lambda v: v if v == "Any" else f"{v} mi",
)

view = df[df["manager"].isin(chosen)]
mask = view["rent_per_bed_min"] <= max_rent
if show_unpriced:
    mask = mask | view["rent_per_bed_min"].isna()
if max_miles != "Any":
    mask = mask & (view["miles_to_quad"] <= max_miles)
view = view[mask].sort_values("rent_per_bed_min")

st.subheader(f"{len(view)} listings")
st.dataframe(
    view[["manager", "name", "rent_per_bed_min", "rent_per_bed_max",
          "beds_min", "beds_max", "miles_to_quad", "available", "url"]],
    hide_index=True,
    column_config={
        "manager": "Manager",
        "name": "Property",
        "rent_per_bed_min": st.column_config.NumberColumn("From ($/bed)", format="$%d"),
        "rent_per_bed_max": st.column_config.NumberColumn("To ($/bed)", format="$%d"),
        "beds_min": "Min beds",
        "beds_max": "Max beds",
        "miles_to_quad": st.column_config.NumberColumn("Miles to Quad", format="%.2f"),
        "available": "Available",
        "url": st.column_config.LinkColumn("Listing"),
    },
)
# ---- buildings listed without prices (manager declined price data) ----
if not buildings.empty:
    b = buildings if max_miles == "Any" else buildings[buildings["miles_to_quad"] <= max_miles]
    st.subheader(f"{len(b)} more buildings, prices not listed")
    st.caption(
        "Green Street Realty asked that its prices not be included here. "
        "Their buildings are listed with distance to campus; see their site for prices and availability."
    )
    st.dataframe(
        b.sort_values("miles_to_quad")[["manager", "name", "miles_to_quad", "url"]],
        hide_index=True,
        column_config={
            "manager": "Manager",
            "name": "Building",
            "miles_to_quad": st.column_config.NumberColumn("Miles to Quad", format="%.2f"),
            "url": st.column_config.LinkColumn("Prices on manager's site"),
        },
    )

st.caption(
    "Community Property Management lists whole-unit rent; per-bed price here "
    "is that rent split evenly across bedrooms (studios count as one bed). "
    "Distances are straight-line miles to the center of the Main Quad. "
    "Listings we couldn't locate only appear when distance is set to Any."
)
