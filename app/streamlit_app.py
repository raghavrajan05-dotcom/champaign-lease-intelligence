import glob

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Champaign Lease Intelligence", layout="wide")


@st.cache_data
def load_latest(prefix: str) -> pd.DataFrame:
    """Read the newest scraped CSV for one manager."""
    files = sorted(glob.glob(f"data/{prefix}_*.csv"))
    if not files:
        return pd.DataFrame()
    return pd.read_csv(files[-1])


df = load_latest("green-street-realty")

st.title("Champaign Lease Intelligence")

if df.empty:
    st.warning("No data yet. Run: python -m src.scrapers.greenstreet")
    st.stop()

st.caption(f"Green Street Realty · last updated {df['scraped_on'].iloc[0]}")

priced = df[df["rent_per_bed_min"].notna()]
lo, hi = int(priced["rent_per_bed_min"].min()), int(priced["rent_per_bed_min"].max())
max_rent = st.sidebar.slider("Max rent per bed ($/mo)", lo, hi, hi, step=25)
show_unpriced = st.sidebar.checkbox("Include properties with no listed price", value=False)

filtered = priced[priced["rent_per_bed_min"] <= max_rent]
if show_unpriced:
    filtered = pd.concat([filtered, df[df["rent_per_bed_min"].isna()]])

st.subheader(f"{len(filtered)} properties")
st.dataframe(
    filtered[["name", "rent_per_bed_min", "rent_per_bed_max",
              "beds_min", "beds_max", "available_raw", "url"]],
    hide_index=True,
    column_config={
        "name": "Property",
        "rent_per_bed_min": st.column_config.NumberColumn("From ($/bed)", format="$%d"),
        "rent_per_bed_max": st.column_config.NumberColumn("To ($/bed)", format="$%d"),
        "beds_min": "Min beds",
        "beds_max": "Max beds",
        "available_raw": "Available",
        "url": st.column_config.LinkColumn("Listing"),
    },
)