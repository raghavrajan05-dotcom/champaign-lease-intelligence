"""Champaign Lease Intelligence: the public site.

Run locally:  streamlit run app/streamlit_app.py
Hosted on Streamlit Community Cloud; reads the daily data from the repo's "data" branch.
"""

import sys
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

# Let the app import our own code from src/ (needed for `streamlit run` and for hosting).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.geo.geocode import attach_distance, load_cache, load_remote_cache  # noqa: E402
from src.geo.landmarks import (  # noqa: E402
    BIKE_MPH, DETOUR, WALK_MPH, load_landmarks, miles_to, minutes,
)
from src.normalize import (  # noqa: E402
    OPEN_STATUSES, REMOTE_BASE, REPO, load_all, load_history, load_history_remote,
    load_latest_remote,
)

st.set_page_config(page_title="Champaign Lease Intelligence", page_icon="🏠", layout="wide")

LISTING_TYPE = {
    "Green Street Realty": "Whole building (price range)",
    "JSM Living": "Floor plan",
    "MHM Properties": "Apartment type",
    "Octave": "Floor plan",
    "Seven07": "Floor plan",
    "The Rive": "Floor plan",
}
DEFAULT_TYPE = "Single unit"
MANAGER_COLORS = {
    "Green Street Realty": "#1F8A4C",
    "JSM Living": "#2563EB",
    "Community Property Management": "#9333EA",
    "Ramshaw Real Estate": "#D97706",
    "Weiner Companies": "#DB2777",
    "Roland Realty": "#0E7490",
    "MHM Properties": "#B91C1C",
    "Smile Student Living": "#CA8A04",
    "Octave": "#4F46E5",
    "Seven07": "#0F766E",
    "The Rive": "#C2410C",
}
STATUS_STYLE = {  # badge colors; anything not open is greyed out on the cards
    "Last unit": "#E84A27", "Leased": "#64748B", "Sold out": "#64748B",
    "Unavailable": "#64748B", "No longer listed": "#94A3B8",
}
FALLBACK_COLORS = ["#0891B2", "#65A30D", "#B45309", "#7C3AED", "#BE123C"]
BED_OPTIONS = ["Studio", "1", "2", "3", "4", "5+"]
DISTANCE_OPTIONS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, "Any"]
CARDS_PER_PAGE = 24


# ---------------------------------------------------------------- data

def no_longer_listed(current: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """Listings we saw earlier that a manager has since taken down (usually: leased).

    Last row seen for each listing missing from that manager's newest scrape."""
    if history.empty:
        return history
    h = history[history["manager"].isin(current["manager"].unique())]
    latest = current.groupby("manager")["scraped_on"].max()
    h = h[h["scraped_on"] < h["manager"].map(latest)]
    live = set(zip(current["manager"], current["listing_id"]))
    gone = h[[k not in live for k in zip(h["manager"], h["listing_id"])]]
    gone = gone.sort_values("scraped_on").drop_duplicates(["manager", "listing_id"], keep="last")
    return gone.assign(status="No longer listed",
                       available=lambda d: "last seen " + d["scraped_on"].astype(str))


@st.cache_data(ttl=3600)  # re-read at most once an hour
def get_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(today's listings + ones taken down recently, with lat/lon; every daily scrape)."""
    local = load_all()
    if not local.empty:  # running on your laptop with data/ synced
        listings, cache, history = local, load_cache(), load_history()
    else:  # hosted: no data/ folder, so read the public daily files from GitHub
        listings, cache, history = (load_latest_remote(), load_remote_cache(REMOTE_BASE),
                                    load_history_remote())
    if "status" in history:
        history["status"] = history["status"].fillna("Available")
    gone = no_longer_listed(listings, history)
    both = pd.concat([listings, gone], ignore_index=True) if len(gone) else listings
    return attach_distance(both, cache), history


def manager_color(manager: str, managers: list[str]) -> str:
    if manager in MANAGER_COLORS:
        return MANAGER_COLORS[manager]
    return FALLBACK_COLORS[managers.index(manager) % len(FALLBACK_COLORS)]


def beds_label(lo, hi) -> str:
    if pd.isna(lo):
        return "Beds not listed"
    name = lambda b: "Studio" if b == 0 else f"{int(b)} bed"  # noqa: E731
    return name(lo) if lo == hi or pd.isna(hi) else f"{name(lo)} – {int(hi)} bed"


def price_label(lo, hi) -> str:
    if pd.isna(lo):
        return "Price not listed"
    return f"${lo:,.0f}" if pd.isna(hi) or hi == lo else f"${lo:,.0f}–${hi:,.0f}"


def price_html(r) -> str:
    """Price line, how it was worked out, and any required monthly fees."""
    basis = "" if pd.isna(r.price_basis) else escape(str(r.price_basis))
    if pd.isna(r.rent_per_bed_min):
        if pd.notna(r.listed_price):
            return (f'<div class="price listed">Listed ${r.listed_price:,.0f}</div>'
                    f'<div class="basis warn">{basis}. Ask the manager.</div>')
        return '<div class="price listed">Price not listed</div>'
    html = (f'<div class="price">{price_label(r.rent_per_bed_min, r.rent_per_bed_max)} '
            f'<small>/ bed / month</small></div>')
    if pd.notna(r.fees_per_bed) and r.fees_per_bed > 0:
        html += (f'<div class="fees">+ ${r.fees_per_bed:,.0f} required monthly fees per person '
                 f'(≈ ${r.rent_per_bed_min + r.fees_per_bed:,.0f} total)</div>')
    if basis:
        html += f'<div class="basis{" warn" if "Estimate" in basis or "assumed" in basis else ""}">{basis}</div>'
    return html


def matches_beds(lo, hi, chosen: set[int]) -> bool:
    """Does a listing offering lo..hi bedrooms include any chosen count? (5 means 5+)."""
    if pd.isna(lo):
        return len(chosen) == len(BED_OPTIONS)  # unknown beds: only when not filtering
    hi = lo if pd.isna(hi) else hi
    return any(min(b, 5) in chosen for b in range(int(lo), int(hi) + 1))


df, history = get_data()
landmarks = load_landmarks()

# ---------------------------------------------------------------- style

st.markdown("""
<style>
.block-container {padding-top: 2.2rem; max-width: 1250px;}
.hero {background: linear-gradient(120deg, #13294B 0%, #1E3A6E 60%, #E84A27 160%);
  color: #fff; border-radius: 18px; padding: 28px 32px 24px; margin-bottom: 18px;}
.hero .eyebrow {font-size: .78rem; letter-spacing: .12em; text-transform: uppercase;
  opacity: .8; font-weight: 600;}
.hero h1 {color: #fff; font-size: 2.3rem; line-height: 1.15; margin: 6px 0 8px; padding: 0;}
.hero p {color: #DCE3F0; font-size: 1.02rem; margin: 0; max-width: 760px;}
.hero .updated {margin-top: 14px; font-size: .8rem; color: #B9C5DA;}
.kpi {background: #F3F5F9; border-radius: 14px; padding: 14px 18px; height: 100%;}
.kpi .label {font-size: .78rem; color: #5B6B85; text-transform: uppercase; letter-spacing: .06em;
  font-weight: 600;}
.kpi .value {font-size: 1.75rem; font-weight: 700; color: #13294B; margin-top: 2px;}
.kpi .sub {font-size: .8rem; color: #5B6B85;}
.cards {display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 14px;}
a.card {display: block; text-decoration: none !important; color: #13294B !important;
  border: 1px solid #E3E8F0; border-radius: 14px; padding: 14px 16px 12px; background: #fff;
  transition: box-shadow .15s, transform .15s, border-color .15s;}
a.card:hover {box-shadow: 0 8px 24px rgba(19,41,75,.12); transform: translateY(-2px);
  border-color: #C9D3E3;}
.card .top {display: flex; justify-content: space-between; align-items: center; gap: 8px;}
.badge {font-size: .7rem; font-weight: 700; padding: 3px 8px; border-radius: 999px; color: #fff;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 62%;}
.dist {font-size: .76rem; color: #5B6B85; white-space: nowrap;}
.card .name {font-weight: 650; font-size: 1rem; margin: 10px 0 2px; line-height: 1.3;
  min-height: 2.6em;}
.card .price {font-size: 1.45rem; font-weight: 750; color: #E84A27;}
.card .price small {font-size: .78rem; color: #5B6B85; font-weight: 500;}
.card .meta {font-size: .8rem; color: #5B6B85; margin-top: 4px;}
a.card.closed {background: #F6F7F9; opacity: .72;}
a.card.closed .price {color: #64748B; text-decoration: line-through;}
.status {float: right; color: #fff; font-weight: 700; padding: 2px 8px; border-radius: 999px;
  text-transform: none; letter-spacing: 0;}
.card .price.listed {font-size: 1.05rem; color: #5B6B85;}
.card .fees {font-size: .78rem; color: #13294B; margin-top: 2px;}
.card .basis {font-size: .72rem; color: #5B6B85; margin-top: 2px;}
.card .basis.warn {color: #B45309;}
.card .kind {font-size: .7rem; color: #8090A8; margin-top: 6px; text-transform: uppercase;
  letter-spacing: .05em;}
.legend {display: flex; gap: 14px; flex-wrap: wrap; font-size: .8rem; color: #5B6B85;}
.legend span::before {content: ""; display: inline-block; width: 10px; height: 10px;
  border-radius: 50%; margin-right: 5px; background: var(--c);}
</style>
""", unsafe_allow_html=True)

if df.empty:
    st.warning("No data yet. Run the scrapers or: bash scripts/sync_data.sh")
    st.stop()

managers = sorted(df["manager"].unique())
df["listing_type"] = df["manager"].map(LISTING_TYPE).fillna(DEFAULT_TYPE)
df["status"] = df["status"].fillna("Available")
df["is_open"] = df["status"].isin(OPEN_STATUSES)

# ---------------------------------------------------------------- sidebar

with st.sidebar:
    st.markdown("### Where do you need to be?")
    place = st.selectbox("Distance from", landmarks["name"], label_visibility="collapsed")
    lm = landmarks[landmarks["name"] == place].iloc[0]
    max_miles = st.select_slider(
        f"Within (straight-line miles of {lm['short']})", DISTANCE_OPTIONS, value="Any",
        format_func=lambda v: v if v == "Any" else f"{v} mi",
    )

    st.markdown("### Budget & size")
    priced = df["rent_per_bed_min"].dropna()
    lo, hi = int(priced.min() // 25 * 25), int(-(-priced.max() // 25) * 25)
    price_range = st.slider("Rent per bed ($/month)", lo, hi, (lo, hi), step=25)
    beds = st.pills("Bedrooms", BED_OPTIONS, selection_mode="multi", default=BED_OPTIONS)

    st.markdown("### Narrow it down")
    query = st.text_input("Street or building", placeholder="e.g. Green, Armory, Sixth")
    chosen_managers = st.multiselect("Property managers", managers, default=managers)
    show_closed = st.toggle("Show leased & sold-out listings", value=True,
                            help="Marked in grey and listed after open ones.")
    show_unpriced = st.toggle("Include listings without a price", value=False)

    st.markdown("### Sort")
    sort_by = st.radio("Sort by", ["Lowest price", "Closest", "Most bedrooms"],
                       label_visibility="collapsed")

# ---------------------------------------------------------------- filter

df["miles"] = miles_to(df, lm["lat"], lm["lon"])
df["walk_min"] = minutes(df["miles"], WALK_MPH)
df["bike_min"] = minutes(df["miles"], BIKE_MPH)

chosen_beds = {0 if b == "Studio" else 5 if b == "5+" else int(b) for b in (beds or [])}
view = df[df["manager"].isin(chosen_managers)]
in_budget = view["rent_per_bed_min"].between(*price_range)
if show_unpriced:
    in_budget |= view["rent_per_bed_min"].isna()
if show_closed:
    in_budget |= ~view["is_open"] & view["rent_per_bed_min"].isna()  # leased: often no price
else:
    in_budget &= view["is_open"]
view = view[in_budget]
view = view[[matches_beds(a, b, chosen_beds) for a, b in zip(view["beds_min"], view["beds_max"])]]
if max_miles != "Any":
    view = view[view["miles"] <= max_miles]
if query.strip():
    view = view[view["name"].str.contains(query.strip(), case=False, na=False, regex=False)]
sort_cols = {"Lowest price": (["rent_per_bed_min", "miles"], [True, True]),
             "Closest": (["miles", "rent_per_bed_min"], [True, True]),
             "Most bedrooms": (["beds_max", "rent_per_bed_min"], [False, True])}[sort_by]
view = view.sort_values(["is_open"] + sort_cols[0], ascending=[False] + sort_cols[1],
                        na_position="last")

# ---------------------------------------------------------------- hero + KPIs

updated = df["scraped_on"].max()
st.markdown(
    f"""<div class="hero"><div class="eyebrow">UIUC off-campus housing · updated daily</div>
<h1>Find your Champaign lease</h1>
<p>{int(df["is_open"].sum()):,} open listings from {len(managers)} property managers and
buildings, priced per bed, with distance to the places you actually go. Pick a spot on the
left to re-measure everything.</p>
<div class="updated">Last updated {escape(str(updated))} · data refreshes every morning ·
prices are base rent; required monthly fees are added where the manager states them</div></div>""",
    unsafe_allow_html=True,
)


def kpi(col, label: str, value: str, sub: str) -> None:
    col.markdown(f'<div class="kpi"><div class="label">{label}</div>'
                 f'<div class="value">{value}</div><div class="sub">{sub}</div></div>',
                 unsafe_allow_html=True)


open_df = df[df["is_open"]]
vp = view[view["is_open"]].dropna(subset=["rent_per_bed_min"])
near = open_df[(open_df["miles"] <= 0.5) & open_df["rent_per_bed_min"].notna()]
close_1mi = open_df[(open_df["miles"] <= 1.0) & open_df["rent_per_bed_min"].notna()]
k1, k2, k3, k4 = st.columns(4)
kpi(k1, "Open & matching your filters", f"{int(view['is_open'].sum()):,}",
    f"{int((~view['is_open']).sum()):,} more leased or sold out")
kpi(k2, "Median rent / bed", f"${vp['rent_per_bed_min'].median():,.0f}" if len(vp) else "–",
    "lowest listed price, matching listings")
kpi(k3, f"Within ½ mile of {escape(lm['short'])}", f"{len(near):,}",
    f"about a {int(0.5 * DETOUR / WALK_MPH * 60)}-minute walk or less")
kpi(k4, f"Cheapest within 1 mi of {escape(lm['short'])}",
    f"${close_1mi['rent_per_bed_min'].min():,.0f}" if len(close_1mi) else "–", "per bed per month")
st.write("")

# ---------------------------------------------------------------- tabs

t_list, t_map, t_market, t_trends, t_about = st.tabs(
    [":material/home: Listings", ":material/map: Map", ":material/bar_chart: Market",
     ":material/trending_up: Trends", ":material/info: About"])

with t_list:
    left, right = st.columns([3, 1])
    left.markdown(f"**{int(view['is_open'].sum()):,} open listings** · sorted by {sort_by.lower()}"
                  + (f" · then {int((~view['is_open']).sum()):,} leased / sold out"
                     if (~view["is_open"]).any() else ""))
    as_table = right.toggle("Table view", value=False)
    if view.empty:
        st.info("Nothing matches those filters. Try widening the distance or budget.")
    elif as_table:
        st.dataframe(
            view.assign(beds=[beds_label(a, b) for a, b in zip(view["beds_min"], view["beds_max"])]),
            hide_index=True, use_container_width=True, height=560,
            column_order=["name", "manager", "status", "rent_per_bed_min", "rent_per_bed_max",
                          "fees_per_bed", "price_basis", "listed_price", "beds",
                          "miles", "walk_min", "bike_min", "available", "listing_type", "url"],
            column_config={
                "name": "Property", "manager": "Manager", "status": "Status",
                "rent_per_bed_min": st.column_config.NumberColumn("From $/bed", format="$%d"),
                "rent_per_bed_max": st.column_config.NumberColumn("To $/bed", format="$%d"),
                "fees_per_bed": st.column_config.NumberColumn("+ fees $/person", format="$%d"),
                "price_basis": "How the price was worked out",
                "listed_price": st.column_config.NumberColumn("Listed price (basis unknown)",
                                                              format="$%d"),
                "beds": "Bedrooms",
                "miles": st.column_config.NumberColumn(f"Miles to {lm['short']}", format="%.2f"),
                "walk_min": st.column_config.NumberColumn("Walk (min, est.)", format="%d"),
                "bike_min": st.column_config.NumberColumn("Bike (min, est.)", format="%d"),
                "available": "Available", "listing_type": "Listing type",
                "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
            },
        )
    else:
        shown = st.session_state.get("cards_shown", CARDS_PER_PAGE)
        cards = []
        for r in view.head(shown).itertuples():
            color = manager_color(r.manager, managers)
            if pd.isna(r.miles):
                dist = "location unknown"
            elif r.walk_min <= 30:
                dist = f"{r.miles:.2f} mi · ~{r.walk_min:.0f} min walk"
            else:
                dist = f"{r.miles:.2f} mi · ~{r.bike_min:.0f} min bike"
            avail = "" if pd.isna(r.available) else f" · {escape(str(r.available))}"
            status = ""
            if r.status in STATUS_STYLE:
                status = (f'<span class="status" style="background:{STATUS_STYLE[r.status]}">'
                          f'{escape(r.status)}</span>')
            cards.append(
                f'<a class="card{"" if r.is_open else " closed"}" href="{escape(str(r.url))}" '
                f'target="_blank" rel="noopener">'
                f'<div class="top"><span class="badge" style="background:{color}">'
                f'{escape(r.manager)}</span><span class="dist">{dist}</span></div>'
                f'<div class="name">{escape(str(r.name))}</div>'
                f'{price_html(r)}'
                f'<div class="meta">{beds_label(r.beds_min, r.beds_max)}{avail}</div>'
                f'<div class="kind">{escape(r.listing_type)}{status}</div></a>')
        st.markdown('<div class="cards">' + "".join(cards) + "</div>", unsafe_allow_html=True)
        if shown < len(view):
            st.write("")
            if st.button(f"Show more ({len(view) - shown:,} left)", use_container_width=True):
                st.session_state["cards_shown"] = shown + CARDS_PER_PAGE
                st.rerun()

with t_map:
    pts = view[view["is_open"]].dropna(subset=["lat", "lon"]).copy()
    if pts.empty:
        st.info("No mappable listings match those filters.")
    else:
        p = pts["rent_per_bed_min"]
        rank = p.rank(pct=True).fillna(0.5)  # 0 = cheapest shown, 1 = priciest shown
        pts["r"] = (40 + 200 * rank).astype(int)
        pts["g"] = (170 - 120 * rank).astype(int)
        pts["b"] = 70
        pts["price"] = [price_label(a, b) for a, b in zip(pts["rent_per_bed_min"], pts["rent_per_bed_max"])]
        pts["beds_txt"] = [beds_label(a, b) for a, b in zip(pts["beds_min"], pts["beds_max"])]
        lms = landmarks.assign(is_sel=landmarks["name"] == place)
        layers = [
            pdk.Layer("ScatterplotLayer", pts, get_position="[lon, lat]",
                      get_fill_color="[r, g, b, 200]", get_radius=28, radius_min_pixels=4,
                      get_line_color=[255, 255, 255], line_width_min_pixels=1, stroked=True,
                      pickable=True),
            pdk.Layer("ScatterplotLayer", lms, get_position="[lon, lat]",
                      get_fill_color="is_sel ? [232, 74, 39, 255] : [19, 41, 75, 230]",
                      get_radius=45, radius_min_pixels=7, stroked=True,
                      get_line_color=[255, 255, 255], line_width_min_pixels=2),
            pdk.Layer("TextLayer", lms, get_position="[lon, lat]", get_text="short",
                      get_size=13, get_color=[19, 41, 75], get_pixel_offset=[0, -18],
                      font_weight=700, background=True, get_background_color=[255, 255, 255, 220]),
        ]
        st.pydeck_chart(pdk.Deck(
            layers=layers, map_style="light",
            initial_view_state=pdk.ViewState(latitude=lm["lat"], longitude=lm["lon"], zoom=14),
            tooltip={"html": "<b>{name}</b><br/>{price} / bed · {beds_txt}<br/>{manager}"
                             "<br/>{miles} mi to " + escape(lm["short"]),
                     "style": {"fontSize": "12px"}},
        ), height=560)
        st.caption(f"{len(pts):,} of {int(view['is_open'].sum()):,} open matching listings have a "
                   "map location (leased and sold-out listings aren't mapped). "
                   "Dot color runs from green (cheapest per bed shown) to red (priciest). "
                   "Navy dots are campus landmarks; orange is the one you picked.")

with t_market:
    m = view[view["is_open"]].dropna(subset=["rent_per_bed_min"])
    if m.empty:
        st.info("No priced listings match those filters.")
    else:
        st.caption("Descriptive only: open listings today, using each listing's lowest per-bed "
                   "price. Listings differ in size, age and amenities, so these aren't "
                   "like-for-like comparisons.")
        color = alt.Color("manager:N", title="Manager", scale=alt.Scale(
            domain=managers, range=[manager_color(x, managers) for x in managers]))
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Rent per bed vs. distance to {lm['short']}**")
            base = alt.Chart(m.dropna(subset=["miles"]))
            dots = base.mark_circle(size=55, opacity=.7).encode(
                x=alt.X("miles:Q", title=f"Straight-line miles to {lm['short']}"),
                y=alt.Y("rent_per_bed_min:Q", title="$ per bed / month"),
                color=color, tooltip=["name", "manager", alt.Tooltip("rent_per_bed_min", format="$,.0f"),
                                      alt.Tooltip("miles", format=".2f")])
            trend = base.transform_regression("miles", "rent_per_bed_min").mark_line(
                color="#13294B", strokeDash=[6, 4]).encode(x="miles:Q", y="rent_per_bed_min:Q")
            st.altair_chart((dots + trend).properties(height=330), use_container_width=True)
            st.caption("Dashed line: one straight-line fit across all managers.")
        with c2:
            st.markdown("**Median rent per bed by distance**")
            bands = pd.cut(m["miles"], [0, .5, 1, 1.5, 2, 99],
                           labels=["< 0.5 mi", "0.5–1 mi", "1–1.5 mi", "1.5–2 mi", "2+ mi"])
            by_band = (m.assign(band=bands).dropna(subset=["band"]).groupby("band", observed=True)
                       ["rent_per_bed_min"].agg(["median", "count"]).reset_index())
            bars = alt.Chart(by_band).mark_bar(color="#E84A27", cornerRadiusEnd=4).encode(
                x=alt.X("band:N", title=None, sort=None),
                y=alt.Y("median:Q", title="Median $ per bed"),
                tooltip=["band", alt.Tooltip("median", format="$,.0f"), "count"])
            labels = bars.mark_text(dy=-8, color="#13294B").encode(text="count:Q")
            st.altair_chart((bars + labels).properties(height=330), use_container_width=True)
            st.caption("Number above each bar = listings in that band.")
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**Median rent per bed by bedrooms**")
            by_beds = (m.dropna(subset=["beds_min"])
                       .assign(beds=lambda d: d["beds_min"].clip(upper=5).map(
                           {0: "Studio", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5+"}))
                       .groupby("beds")["rent_per_bed_min"].agg(["median", "count"]).reset_index())
            bars = alt.Chart(by_beds).mark_bar(color="#13294B", cornerRadiusEnd=4).encode(
                x=alt.X("beds:N", title="Bedrooms", sort=BED_OPTIONS),
                y=alt.Y("median:Q", title="Median $ per bed"),
                tooltip=["beds", alt.Tooltip("median", format="$,.0f"), "count"])
            labels = bars.mark_text(dy=-8, color="#13294B").encode(text="count:Q")
            st.altair_chart((bars + labels).properties(height=300), use_container_width=True)
        with c4:
            st.markdown("**How prices are spread out**")
            hist = alt.Chart(m).mark_bar(opacity=.85).encode(
                x=alt.X("rent_per_bed_min:Q", bin=alt.Bin(step=100), title="$ per bed / month"),
                y=alt.Y("count():Q", title="Listings", stack=True), color=color)
            st.altair_chart(hist.properties(height=300), use_container_width=True)

with t_trends:
    if history.empty or history["scraped_on"].nunique() < 2:
        st.info("Trends appear once there are at least two days of data.")
    else:
        h = history[history["manager"].isin(chosen_managers)].copy()
        h["scraped_on"] = pd.to_datetime(h["scraped_on"])
        st.markdown("**Listings tracked per day**")
        counts = h.groupby(["scraped_on", "manager"]).size().reset_index(name="listings")
        line = alt.Chart(counts).mark_line(point=True).encode(
            x=alt.X("scraped_on:T", title=None),
            y=alt.Y("listings:Q", title="Listings"),
            color=alt.Color("manager:N", title="Manager", scale=alt.Scale(
                domain=managers, range=[manager_color(x, managers) for x in managers])),
            tooltip=["manager", alt.Tooltip("scraped_on:T", title="Date"), "listings"])
        st.altair_chart(line.properties(height=280), use_container_width=True)
        st.caption("Gaps are days a scrape didn't run. Drops can mean units got leased "
                   "(or a manager changed their site).")

        # Price changes: the same listing (manager's own listing ID), first vs latest price seen.
        key = ["manager", "listing_id", "name"]
        hp = (h.dropna(subset=["rent_per_bed_min"])
              .groupby(key + ["scraped_on"], dropna=False)["rent_per_bed_min"].min()
              .reset_index().sort_values("scraped_on"))
        g = hp.groupby(key, dropna=False)
        changes = g.agg(first_seen=("scraped_on", "first"), was=("rent_per_bed_min", "first"),
                        last_seen=("scraped_on", "last"), now=("rent_per_bed_min", "last")
                        ).reset_index()
        changes = changes[changes["was"] != changes["now"]].assign(
            change=lambda d: d["now"] - d["was"]).sort_values("change")
        latest_day = h["scraped_on"].max()
        st.markdown(f"**Price changes since we started tracking** · {len(changes)} found")
        if changes.empty:
            st.caption("No listed price has changed yet. Most managers set prices once for "
                       "the leasing season, so changes are rare and worth noticing.")
        else:
            st.dataframe(
                changes.assign(still_listed=changes["last_seen"] == latest_day),
                hide_index=True, use_container_width=True,
                column_order=["name", "manager", "was", "now", "change", "first_seen",
                              "last_seen", "still_listed"],
                column_config={
                    "name": "Property", "manager": "Manager",
                    "was": st.column_config.NumberColumn("Was $/bed", format="$%d"),
                    "now": st.column_config.NumberColumn("Now $/bed", format="$%d"),
                    "change": st.column_config.NumberColumn("Change", format="$%+d"),
                    "first_seen": st.column_config.DateColumn("First seen"),
                    "last_seen": st.column_config.DateColumn("Last seen"),
                    "still_listed": st.column_config.CheckboxColumn("Still listed"),
                })

with t_about:
    a1, a2 = st.columns([3, 2])
    with a1:
        st.markdown(f"""
#### What this is
A free, student-built tracker of off-campus rentals near UIUC. Every morning it reads each
property manager's public listings page, converts every price to **dollars per bed per month**,
and measures straight-line distance to campus landmarks.

#### How to read it
- **Per-bed price, and how we got it.** Every listing says how its price was worked out:
  *per person, as listed* (the manager prices by the bed), *whole-unit rent* (studios and
  1-beds), or *estimate: unit rent ÷ bedrooms* (a whole apartment's rent split evenly; your
  real share depends on how roommates split it). If a manager doesn't say whether a price is
  per person or per unit, we show it as "Listed $X" and leave it out of per-bed comparisons.
- **Fees.** Prices are base rent. Many managers add required monthly fees (utilities,
  internet, trash, tech). Where a manager states them, we add them per person; otherwise
  ask the manager.
- **Whole building vs. unit.** Green Street Realty lists one price range per building; other
  managers list individual units or floor plans.
- **Distance and walk time.** Straight-line miles. Walk/bike times assume streets add about
  {int((DETOUR - 1) * 100)}% to the distance, at {WALK_MPH:g} mph walking and {BIKE_MPH:g} mph biking:
  rough estimates, not directions.
- **Leased / sold out.** Shown in grey when a manager marks a unit leased or a floor plan
  sold out. "No longer listed" means it was on the manager's site recently but has since been
  taken down, which usually means it was leased.
- **Always confirm with the manager.** Prices and availability change; the listing link goes
  to the manager's own page.

#### How it's built
Python scrapers → data-quality checks → daily GitHub Actions run → public CSVs →
this Streamlit site. Code: [github.com/{REPO}](https://github.com/{REPO})
""")
    with a2:
        st.markdown("#### Sources")
        src = (df.groupby("manager")
               .agg(listings=("name", "size"), last_scraped=("scraped_on", "max"))
               .reset_index())
        src["listing_type"] = src["manager"].map(LISTING_TYPE).fillna(DEFAULT_TYPE)
        st.dataframe(src, hide_index=True, use_container_width=True, column_config={
            "manager": "Manager", "listings": "Listings", "last_scraped": "Last scraped",
            "listing_type": "Listed as"})
        st.caption("Green Street Realty prices are used with their permission. "
                   "Landmark locations: Wikipedia, OpenStreetMap or the US Census geocoder.")
        st.markdown("#### Spot a problem?")
        st.markdown(f"[Open an issue on GitHub](https://github.com/{REPO}/issues) "
                    "if a listing looks wrong or you want a building added.")
