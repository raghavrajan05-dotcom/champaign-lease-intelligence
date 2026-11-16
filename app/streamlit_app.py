"""Champaign Lease Intelligence: the public site.

Run locally:  streamlit run app/streamlit_app.py
Hosted on Streamlit Community Cloud; reads the daily data from the repo's "data" branch.
"""

import sys
from html import escape
from pathlib import Path
from urllib.parse import quote

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

# Let the app import our own code from src/ (needed for `streamlit run` and for hosting).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.geo.geocode import attach_distance, load_cache, load_remote_cache  # noqa: E402
from src.geo.landmarks import (  # noqa: E402
    BIKE_MPH, DETOUR, WALK_MPH, area_for, load_landmarks, miles_to, minutes,
)
from src.normalize import (  # noqa: E402
    OPEN_STATUSES, REMOTE_BASE, REPO, load_all, load_history, load_history_remote,
    load_latest_remote,
)

st.set_page_config(page_title="Champaign Lease Intelligence", page_icon="📍", layout="wide")

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
STATUS_STYLE = {  # small tags; anything not open is greyed out in the list
    "Last unit": "#C2410C", "Leased": "#6B7280", "Sold out": "#6B7280",
    "Unavailable": "#6B7280", "No longer listed": "#9CA3AF",
}
FALLBACK_COLORS = ["#0891B2", "#65A30D", "#B45309", "#7C3AED", "#BE123C"]
BED_OPTIONS = ["Studio", "1", "2", "3", "4", "5+"]
DISTANCE_OPTIONS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, "Any"]
ROWS_PER_PAGE = 40
STALE_DAYS = 2  # a source this many days behind the newest scrape gets a "last checked" note


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


def report_link(r) -> str:
    """Pre-filled GitHub issue so anyone can flag a wrong price or listing."""
    title = quote(f"Wrong info: {r.name} ({r.manager})")
    body = quote(f"Listing: {r.url}\nShown on the site: {price_label(r.rent_per_bed_min, r.rent_per_bed_max)}"
                 f" per bed\n\nWhat's wrong:\n")
    return f"https://github.com/{REPO}/issues/new?title={title}&body={body}"


def listing_row(r, lm) -> str:
    """One listing as a row: address + details | price | walk time | links."""
    basis = "" if pd.isna(r.price_basis) else escape(str(r.price_basis))
    warn = " warn" if basis and ("Estimate" in basis or "assumed" in basis
                                 or "Not shown" in basis) else ""
    tag = ""
    if r.status in STATUS_STYLE:
        tag = (f'<span class="tag-pill" style="background:{STATUS_STYLE[r.status]}">'
               f'{escape(r.status)}</span>')
    details = " · ".join(x for x in [
        None if pd.isna(r.area) else escape(r.area), beds_label(r.beds_min, r.beds_max),
        escape(r.manager), None if pd.isna(r.available) else escape(str(r.available))] if x)

    if pd.notna(r.rent_per_bed_min):
        price = (f'<div class="amt">{price_label(r.rent_per_bed_min, r.rent_per_bed_max)}'
                 f'<span> /bed/mo</span></div>')
        if pd.notna(r.fees_per_bed) and r.fees_per_bed > 0:
            price += (f'<div class="fee">+ ${r.fees_per_bed:,.0f} fees ≈ '
                      f'${r.rent_per_bed_min + r.fees_per_bed:,.0f}</div>')
    elif pd.notna(r.listed_price):
        price = f'<div class="amt listed">Listed ${r.listed_price:,.0f}</div>'
    else:
        price = '<div class="amt listed">No price listed</div>'

    if pd.isna(r.miles):
        walk = '<div class="lbl">location unknown</div>'
    elif r.walk_min <= 30:
        walk = (f'<div class="mins">{r.walk_min:.0f} min</div>'
                f'<div class="lbl">walk to {escape(lm["short"])}</div>')
    else:
        walk = (f'<div class="mins">{r.bike_min:.0f} min</div>'
                f'<div class="lbl">bike to {escape(lm["short"])}</div>')

    return (f'<div class="row{"" if r.is_open else " closed"}">'
            f'<div class="main"><a class="addr" href="{escape(str(r.url))}" target="_blank" '
            f'rel="noopener">{escape(str(r.name))}</a>{tag}'
            f'<div class="sub">{details}</div>'
            + (f'<div class="basis{warn}">{basis}</div>' if basis else "")
            + (f'<div class="basis warn">Price last checked {r.checked_on}</div>'
               if r.days_behind >= STALE_DAYS else "")
            + f'</div><div>{price}</div><div>{walk}</div>'
            f'<div class="links"><a href="{escape(str(r.url))}" target="_blank" rel="noopener">'
            f'Listing ↗</a><br><a class="report" href="{escape(report_link(r))}" '
            f'target="_blank" rel="noopener">Report a problem</a></div></div>')


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
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&display=swap');
.block-container {padding-top: 1.6rem; max-width: 1180px;}
.masthead {display: flex; gap: 14px; align-items: center; margin-bottom: 4px;}
.masthead .title {font-family: 'Fraunces', Georgia, serif; font-size: 2rem; line-height: 1.1;
  color: #1F2A37;}
.masthead .tag {color: #4B5563; font-size: 1rem; margin-top: 2px;}
.statusline {color: #6B7280; font-size: .82rem; margin: 8px 0 14px; padding-bottom: 12px;
  border-bottom: 1px solid #E7E2D9;}
.row {display: grid; grid-template-columns: minmax(0, 1fr) 170px 120px 130px; gap: 18px;
  align-items: center; padding: 14px 4px; border-bottom: 1px solid #ECE7DF;}
.row:hover {background: #F6F3EE;}
.row .addr {font-weight: 600; font-size: 1rem; color: #1F2A37 !important;
  text-decoration: none !important;}
.row .addr:hover {text-decoration: underline !important;}
.row .sub {color: #4B5563; font-size: .85rem; margin-top: 2px;}
.row .basis {color: #6B7280; font-size: .75rem; margin-top: 2px;}
.row .basis.warn {color: #B45309;}
.row .amt {font-size: 1.25rem; font-weight: 700; color: #1F2A37;}
.row .amt span {font-size: .8rem; font-weight: 400; color: #6B7280;}
.row .amt.listed {font-size: 1rem; color: #6B7280; font-weight: 600;}
.row .fee {font-size: .76rem; color: #4B5563;}
.row .mins {font-size: 1.05rem; font-weight: 600; color: #1F2A37;}
.row .lbl {font-size: .75rem; color: #6B7280;}
.row .links {font-size: .8rem; text-align: right; line-height: 1.7;}
.row .links a {color: #C2410C !important; text-decoration: none !important;}
.row .links a.report {color: #6B7280 !important;}
.row.closed .addr, .row.closed .amt {color: #9CA3AF !important;}
.row.closed .amt {text-decoration: line-through;}
.tag-pill {display: inline-block; font-size: .7rem; font-weight: 600; padding: 1px 7px;
  border-radius: 4px; margin-left: 6px; vertical-align: 1px; color: #fff;}
@media (max-width: 760px) {
  .block-container {padding-top: 3.2rem;}
  .masthead .title {font-size: 1.5rem;}
  .masthead svg {width: 30px; height: 30px; flex: none;}
  .row {grid-template-columns: 1fr 1fr; gap: 6px 12px;}
  .row .main {grid-column: 1 / -1;}
  .row .links {grid-column: 1 / -1; text-align: left;}
}
</style>
""", unsafe_allow_html=True)

if df.empty:
    st.warning("No data yet. Run the scrapers or: bash scripts/sync_data.sh")
    st.stop()

managers = sorted(df["manager"].unique())
df["listing_type"] = df["manager"].map(LISTING_TYPE).fillna(DEFAULT_TYPE)
df["status"] = df["status"].fillna("Available")
df["is_open"] = df["status"].isin(OPEN_STATUSES)
# How far behind each source is: a scraper that stopped shouldn't pass off old prices as today's.
_day = pd.to_datetime(df["scraped_on"])
_source_day = _day.groupby(df["manager"]).transform("max")
df["days_behind"] = (_day.max() - _source_day).dt.days
df["checked_on"] = _source_day.dt.strftime("%b %-d")

# ---------------------------------------------------------------- sidebar

with st.sidebar:
    st.markdown("### Where do you need to be?")
    place = st.selectbox("Distance from", landmarks["name"], label_visibility="collapsed")
    lm = landmarks[landmarks["name"] == place].iloc[0]
    max_miles = st.select_slider(
        f"Within (straight-line miles of {lm['short']})", DISTANCE_OPTIONS, value="Any",
        format_func=lambda v: v if v == "Any" else f"{v} mi",
    )

    st.markdown("### Budget and size")
    priced = df["rent_per_bed_min"].dropna()
    lo, hi = int(priced.min() // 25 * 25), int(-(-priced.max() // 25) * 25)
    price_range = st.slider("Rent per bed ($/month)", lo, hi, (lo, hi), step=25)
    beds = st.pills("Bedrooms", BED_OPTIONS, selection_mode="multi", default=BED_OPTIONS)

    st.markdown("### More filters")
    query = st.text_input("Street or building", placeholder="e.g. Green, Armory, Sixth")
    chosen_managers = st.multiselect("Property managers", managers, default=managers)
    show_closed = st.toggle("Show leased & sold-out listings", value=True,
                            help="Marked in grey and listed after open ones.")
    show_unpriced = st.toggle("Include listings without a price", value=False)

    st.markdown("### Sort")
    sort_by = st.radio("Sort by", ["Lowest price", "Closest", "Most bedrooms"],
                       label_visibility="collapsed")

# ---------------------------------------------------------------- filter

df["area"] = [area_for(a, b) for a, b in zip(df["lat"], df["lon"])]
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

# ---------------------------------------------------------------- header

MARK = ('<svg width="40" height="40" viewBox="0 0 40 40" aria-hidden="true">'
        '<path d="M20 3c-7 0-12.5 5.4-12.5 12.3C7.5 24.5 20 37 20 37s12.5-12.5 12.5-21.7C32.5 '
        '8.4 27 3 20 3z" fill="#C2410C"/><path d="M13.5 18.5 20 12.8l6.5 5.7v6.2h-4.2v-4h-4.6v4'
        'h-4.2z" fill="#FBFAF7"/></svg>')
updated = df["scraped_on"].max()
behind = (df[df["days_behind"] >= STALE_DAYS].groupby("manager")["checked_on"].first())
stale_note = "".join(f" · {escape(m)} last checked {d}" for m, d in behind.items())
st.markdown(
    f'<div class="masthead">{MARK}<div><div class="title">Champaign Lease Intelligence</div>'
    '<div class="tag">Off-campus apartments near UIUC, priced per bed and checked every '
    'morning.</div></div></div>'
    f'<div class="statusline">{int(df["is_open"].sum()):,} open listings from '
    f'{len(managers)} managers and buildings · updated {escape(str(updated))} · '
    'prices are base rent, plus required fees where the manager lists them · '
    f'not affiliated with the University of Illinois{stale_note}</div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- tabs

t_list, t_map, t_market, t_trends, t_about = st.tabs(
    ["Listings", "Map", "Prices", "Trends", "About"])

with t_list:
    left, right = st.columns([3, 1])
    left.markdown(f"**{int(view['is_open'].sum()):,} open listings** · sorted by {sort_by.lower()}"
                  + (f" · then {int((~view['is_open']).sum()):,} leased or sold out"
                     if (~view["is_open"]).any() else ""))
    as_table = right.toggle("Table view", value=False)
    if view.empty:
        st.info("Nothing matches those filters. Try widening the distance or budget.")
    elif as_table:
        st.dataframe(
            view.assign(beds=[beds_label(a, b) for a, b in zip(view["beds_min"], view["beds_max"])]),
            hide_index=True, use_container_width=True, height=560,
            column_order=["name", "area", "manager", "status", "rent_per_bed_min",
                          "rent_per_bed_max", "fees_per_bed", "price_basis", "listed_price",
                          "beds", "miles", "walk_min", "available", "url"],
            column_config={
                "name": "Property", "area": "Area", "manager": "Manager", "status": "Status",
                "rent_per_bed_min": st.column_config.NumberColumn("From $/bed", format="$%d"),
                "rent_per_bed_max": st.column_config.NumberColumn("To $/bed", format="$%d"),
                "fees_per_bed": st.column_config.NumberColumn("+ fees $/person", format="$%d"),
                "price_basis": "How the price was worked out",
                "listed_price": st.column_config.NumberColumn("Listed price (basis unknown)",
                                                              format="$%d"),
                "beds": "Bedrooms",
                "miles": st.column_config.NumberColumn(f"Miles to {lm['short']}", format="%.2f"),
                "walk_min": st.column_config.NumberColumn("Walk (min, est.)", format="%d"),
                "available": "Available",
                "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
            },
        )
    else:
        shown = st.session_state.get("rows_shown", ROWS_PER_PAGE)
        rows = [listing_row(r, lm) for r in view.head(shown).itertuples()]
        st.markdown("".join(rows), unsafe_allow_html=True)
        if shown < len(view):
            st.write("")
            if st.button(f"Show more ({len(view) - shown:,} left)", use_container_width=True):
                st.session_state["rows_shown"] = shown + ROWS_PER_PAGE
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
        # ABOUT_ME: Rod, rewrite this paragraph in your own words before launch.
        st.markdown(f"""
#### Why this exists
I'm Rod, a student at UIUC. Finding an apartment here means opening a dozen landlord sites
that all price things differently: some per person, some per apartment, some with fees in
the fine print. This site reads those listings every morning and puts them side by side: rent
per bed, required fees when the landlord lists them, and how far each place is from where
you actually spend your day.

It's a student project, not a listing service. Always confirm price and availability with
the landlord before you sign anything. If something looks wrong, use **Report a problem** on
that listing and I'll fix it.

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
- **Areas.** "Campustown", "Engineering campus" and so on are rough labels based on the
  nearest neighborhood center, not official borders.
- **Distance and walk time.** Straight-line miles. Walk/bike times assume streets add about
  {int((DETOUR - 1) * 100)}% to the distance, at {WALK_MPH:g} mph walking and {BIKE_MPH:g} mph biking:
  rough estimates, not directions.
- **Leased / sold out.** Shown in grey when a manager marks a unit leased or a floor plan
  sold out. "No longer listed" means it was on the manager's site recently but has since been
  taken down, which usually means it was leased.
- **Always confirm with the manager.** Prices and availability change; the listing link goes
  to the manager's own page.

#### How it's built
Python scrapers, data-quality checks and a daily GitHub Actions job feed this Streamlit site.
The code is public: [github.com/{REPO}](https://github.com/{REPO})

Not affiliated with or endorsed by the University of Illinois.
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
        st.markdown("#### Missing a building?")
        st.markdown(f"[Tell me here](https://github.com/{REPO}/issues/new?title="
                    f"{quote('Please add: ')}) and I'll ask the landlord about adding it.")
