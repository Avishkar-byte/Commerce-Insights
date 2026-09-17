"""Design tokens, global CSS, and the Plotly template.

The tokens below are taken from the reference design in `UI/` and
`docs/design/DESIGN.md` (the Tailwind config embedded in each `code.html`),
so the app matches the approved screens rather than approximating them.

Note that the reference palette is the blue-tinted Material scale
(`#eff3ff`, `#121c2a`, `#c2c6d3`), not the neutral greys listed in CLAUDE.md.
The delay scale is unchanged, and is the one place colour carries meaning.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets"

#: Browser tab icon, passed to st.set_page_config.
FAVICON = str(ASSETS / "favicon.png")

# --- surfaces -----------------------------------------------------------------
SURFACE = "#f8f9ff"
SURFACE_LOWEST = "#ffffff"          # page background, cards
SURFACE_LOW = "#eff3ff"             # sidebar, stat tiles, about box
SURFACE_CONTAINER = "#e6eeff"       # chips
SURFACE_HIGH = "#dfe9fc"            # active navigation row
SURFACE_VARIANT = "#d9e3f7"

# --- ink ----------------------------------------------------------------------
ON_SURFACE = "#121c2a"              # primary text
SECONDARY = "#555f71"               # muted text
OUTLINE = "#727782"
OUTLINE_VARIANT = "#c2c6d3"         # hairline borders

# --- brand --------------------------------------------------------------------
PRIMARY = "#00478c"                 # links
PRIMARY_CONTAINER = "#1f5fad"       # active indicator, primary series
ERROR = "#ba1a1a"

# --- delay scale, on time through very late ----------------------------------
DELAY_ON_TIME = "#1E8A5A"
DELAY_1_3 = "#D9A21B"
DELAY_4_7 = "#D9731B"
DELAY_8_14 = "#C2451E"
DELAY_15_PLUS = "#8F1D14"
NEUTRAL = "#8A94A6"

FONT_FAMILY = "Inter, sans-serif"

#: Delay buckets in the order they must always appear.
DELAY_ORDER = [
    "On time",
    "1–3 days late",
    "4–7 days late",
    "8–14 days late",
    "15+ days late",
    "Not delivered",
]

DELAY_COLORS = {
    "On time": DELAY_ON_TIME,
    "1–3 days late": DELAY_1_3,
    "4–7 days late": DELAY_4_7,
    "8–14 days late": DELAY_8_14,
    "15+ days late": DELAY_15_PLUS,
    "Not delivered": NEUTRAL,
}

SCORE_COLORS = {
    "1 star": DELAY_15_PLUS,
    "2 stars": DELAY_8_14,
    "3 stars": DELAY_1_3,
    "4 stars": "#5B9E6F",
    "5 stars": DELAY_ON_TIME,
}

DISTANCE_ORDER = ["<100", "100–500", "500–1000", "1000–2000", "2000+", "unknown"]

TEMPLATE_NAME = "olist"

#: Sidebar width from the reference layout.
SIDEBAR_WIDTH = 280


def delay_colors(buckets: list[str]) -> list[str]:
    """Map delay bucket labels to their colours.

    Args:
        buckets: Bucket labels, in display order.

    Returns:
        One colour per bucket, neutral for unknown labels.
    """
    return [DELAY_COLORS.get(bucket, NEUTRAL) for bucket in buckets]


def register_template() -> None:
    """Register and select the project's Plotly template."""
    template = go.layout.Template()
    template.layout = go.Layout(
        font={"family": FONT_FAMILY, "size": 12, "color": SECONDARY},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=[PRIMARY_CONTAINER, SECONDARY, DELAY_ON_TIME, DELAY_1_3, DELAY_4_7],
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
        xaxis={
            "gridcolor": OUTLINE_VARIANT,
            "linecolor": OUTLINE_VARIANT,
            "zerolinecolor": OUTLINE_VARIANT,
            "tickfont": {"size": 12, "color": SECONDARY},
            "title": {"font": {"size": 12, "color": SECONDARY}},
        },
        yaxis={
            "gridcolor": OUTLINE_VARIANT,
            "linecolor": OUTLINE_VARIANT,
            "zerolinecolor": OUTLINE_VARIANT,
            "tickfont": {"size": 12, "color": SECONDARY},
            "title": {"font": {"size": 12, "color": SECONDARY}},
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"size": 12, "color": SECONDARY},
        },
        hoverlabel={"font": {"family": FONT_FAMILY, "size": 12}, "bordercolor": OUTLINE_VARIANT},
    )
    pio.templates[TEMPLATE_NAME] = template
    pio.templates.default = TEMPLATE_NAME


@lru_cache(maxsize=1)
def _logo_data_uri() -> str:
    """Return the sidebar mark as an inline data URI.

    Inlining keeps the logo working without Streamlit having to serve a static
    file, and CSS cannot reference a file outside the served static directory.

    Returns:
        A ``data:image/svg+xml;base64,...`` string, or an empty string when the
        asset is missing.
    """
    path = ASSETS / "logo.svg"
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def inject_css() -> None:
    """Load Inter and restyle Streamlit's chrome to match the reference design.

    The stylesheet is collapsed to a single blank-line-free block before it is
    injected. Streamlit renders markdown, and markdown ends an inline HTML block
    at the first blank line, which would otherwise dump the rest of the CSS onto
    the page as visible paragraphs.
    """
    css = "\n".join(line.strip() for line in _CSS.splitlines() if line.strip())
    css = css.replace("__LOGO__", _logo_data_uri())
    st.markdown(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2'
        '?family=Inter:wght@400;500;600;700&display=swap">'
        f"<style>{css}</style>",
        unsafe_allow_html=True,
    )


_CSS = f"""
        :root {{
          --surface-lowest: {SURFACE_LOWEST};
          --surface-low: {SURFACE_LOW};
          --surface-container: {SURFACE_CONTAINER};
          --surface-high: {SURFACE_HIGH};
          --on-surface: {ON_SURFACE};
          --secondary: {SECONDARY};
          --outline-variant: {OUTLINE_VARIANT};
          --primary: {PRIMARY};
          --primary-container: {PRIMARY_CONTAINER};
        }}

        html, body, [class*="css"], .stApp {{
          font-family: {FONT_FAMILY};
          color: var(--on-surface);
        }}
        .stApp {{ background: var(--surface-lowest); }}

        /* Streamlit's own header and footer are replaced by the design's own bar. */
        header[data-testid="stHeader"] {{ display: none; }}
        [data-testid="stToolbar"] {{ display: none; }}
        footer {{ display: none; }}
        #MainMenu {{ display: none; }}

        /* ---- main column ---- */
        [data-testid="stMainBlockContainer"] {{
          padding: 2.5rem 2.5rem 4rem 2.5rem;
          max-width: 1180px;
        }}

        /* ---- sidebar ---- */
        [data-testid="stSidebar"] {{
          width: {SIDEBAR_WIDTH}px !important;
          min-width: {SIDEBAR_WIDTH}px !important;
          background: var(--surface-low);
          border-right: 1px solid var(--outline-variant);
        }}
        [data-testid="stSidebar"] > div:first-child {{ padding: 1.25rem 1.25rem 1rem 1.25rem; }}

        /* Product name sits above the generated navigation. */
        [data-testid="stSidebarNav"]::before {{
          content: "Olist Commerce Insights";
          display: flex;
          align-items: center;
          min-height: 28px;
          font-size: 16px;
          line-height: 20px;
          font-weight: 600;
          letter-spacing: -0.01em;
          color: var(--on-surface);
          padding: 0 0 1.25rem 36px;
          background-image: url("__LOGO__");
          background-repeat: no-repeat;
          background-position: left 1px;
          background-size: 28px 28px;
        }}
        [data-testid="stSidebarNav"] {{ padding-top: 0; }}
        [data-testid="stSidebarNav"] ul {{ padding: 0; margin: 0; gap: 2px; }}
        [data-testid="stSidebarNav"] li {{ margin: 0; list-style: none; }}
        [data-testid="stSidebarNav"] a {{
          display: block;
          padding: 8px 12px;
          border-radius: 0;
          border-left: 3px solid transparent;
          color: var(--secondary);
          font-size: 14px;
          line-height: 20px;
          font-weight: 500;
          text-decoration: none;
          transition: background-color .15s, color .15s;
        }}
        [data-testid="stSidebarNav"] a span {{ font-size: 14px; }}
        [data-testid="stSidebarNav"] a:hover {{
          background: var(--surface-container);
          color: var(--on-surface);
        }}
        [data-testid="stSidebarNav"] a[aria-current="page"] {{
          border-left: 3px solid var(--primary-container);
          background: var(--surface-high);
          color: var(--on-surface);
          font-weight: 600;
          padding-left: 9px;
        }}
        [data-testid="stSidebarNav"] a[aria-current="page"] span {{ font-weight: 600; }}

        /* ---- sidebar controls ---- */
        [data-testid="stSidebar"] label p {{
          font-size: 12px !important;
          line-height: 16px;
          color: var(--secondary) !important;
          font-weight: 400;
        }}
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] {{ margin-bottom: 4px; }}
        [data-testid="stSidebar"] hr {{
          margin: 1rem 0;
          border-color: var(--outline-variant);
        }}
        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] [data-baseweb="input"] > div {{
          background: var(--surface-lowest);
          border: 1px solid var(--outline-variant);
          border-radius: 4px;
          font-size: 13px;
          min-height: 34px;
        }}
        [data-testid="stSidebar"] [data-baseweb="tag"] {{
          background: var(--surface-container) !important;
          border: 1px solid var(--outline-variant);
          border-radius: 4px;
          color: var(--on-surface) !important;
          font-size: 12px;
          font-weight: 500;
        }}
        [data-testid="stSidebar"] [data-baseweb="tag"] span {{
          color: var(--on-surface) !important;
        }}
        [data-testid="stSidebar"] [data-testid="stSliderTickBarMin"],
        [data-testid="stSidebar"] [data-testid="stSliderTickBarMax"] {{
          font-size: 11px;
          color: var(--secondary);
        }}

        /* Reset filters, rendered as a link-style button. */
        [data-testid="stSidebar"] .stButton button {{
          background: transparent;
          border: none;
          color: var(--primary-container);
          font-size: 14px;
          font-weight: 500;
          padding: 0;
          min-height: 20px;
          text-align: right;
          justify-content: flex-end;
        }}
        [data-testid="stSidebar"] .stButton button:hover {{
          text-decoration: underline;
          color: var(--primary-container);
          background: transparent;
        }}
        [data-testid="stSidebar"] .stButton button p {{ font-size: 14px; font-weight: 500; }}

        /* ---- chart cards ---- */
        [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{
          background: var(--surface-lowest);
        }}
        div[data-testid="stVerticalBlockBorderWrapper"][style*="border"] {{
          border: 1px solid var(--outline-variant) !important;
          border-radius: 8px;
          padding: 24px;
          background: var(--surface-lowest);
        }}

        /* ---- generic typography ---- */
        h1 {{
          font-size: 28px !important;
          line-height: 36px !important;
          font-weight: 600 !important;
          letter-spacing: -0.02em;
          color: var(--on-surface);
          padding: 0 !important;
          margin: 0 0 4px 0 !important;
        }}
        h2 {{
          font-size: 20px !important;
          line-height: 28px !important;
          font-weight: 600 !important;
          letter-spacing: -0.01em;
          color: var(--on-surface);
          padding: 0 !important;
          margin: 0 !important;
        }}
        h3 {{
          font-size: 16px !important;
          line-height: 24px !important;
          font-weight: 600 !important;
          color: var(--on-surface);
          padding: 0 !important;
        }}
        p, li, .stMarkdown {{ font-size: 14px; line-height: 20px; }}
        hr {{ border-color: var(--outline-variant); margin: 1.5rem 0; }}

        /* ---- alerts ---- */
        [data-testid="stAlert"] {{
          background: var(--surface-low);
          border: 1px solid var(--outline-variant);
          border-radius: 8px;
          color: var(--on-surface);
          font-size: 13px;
        }}
        [data-testid="stAlert"] p {{ font-size: 13px; color: var(--secondary); }}

        /* ---- tables ---- */
        [data-testid="stDataFrame"] {{
          border: 1px solid var(--outline-variant);
          border-radius: 8px;
        }}

        /* ---- page controls on the sellers page ---- */
        [data-testid="stMain"] [data-baseweb="select"] > div,
        [data-testid="stMain"] [data-baseweb="input"] > div {{
          background: var(--surface-lowest);
          border: 1px solid var(--outline-variant);
          border-radius: 4px;
          min-height: 34px;
          font-size: 13px;
        }}
        [data-testid="stMain"] [data-testid="stWidgetLabel"] p {{
          font-size: 12px !important;
          color: var(--secondary) !important;
        }}
"""
