import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Let the app import our own code from src/ (needed for `streamlit run` and for hosting).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.geo.geocode import attach_distance, load_cache  # noqa: E402
from src.normalize import load_all  # noqa: E402

st.set_page_config(page_title="Champaign Lease Intelligence", layout="wide")


@st.cache_data
def get_listings() -> pd.DataFrame:
    return attach_distance(load_all(), load_cache())


df = get_listings()

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
st.caption(
    "Green Street prices are per-bed ranges for a whole building. "
    "Community Property Management lists whole-unit rent; per-bed price here "
    "is that rent split evenly across bedrooms (studios count as one bed). "
    "Distances are straight-line miles to the center of the Main Quad. "
    "Listings we couldn't locate only appear when distance is set to Any."
)