"""Global sidebar filters shared by every page.

Month range (default 2017-01 to 2018-08), customer states, and product
categories, with options read from the meta document. Selections persist in
st.session_state so they survive page changes, and a "Reset filters" button
restores the defaults.
"""

from __future__ import annotations

import streamlit as st

from lib import db, theme

DEFAULT_START = "2017-01"
DEFAULT_END = "2018-08"

_STATE_KEYS = ("month_range", "customer_states", "categories")


def _options() -> tuple[list[str], list[str], list[str]]:
    """Read the filter option lists from the meta document.

    Returns:
        A tuple of (year months, customer states, product categories).
    """
    meta = db.get_meta()
    filters = meta.get("filters", {})
    return (
        filters.get("year_months", []),
        filters.get("customer_states", []),
        filters.get("primary_categories", []),
    )


def _reset() -> None:
    """Clear every stored filter so the defaults apply again."""
    for key in _STATE_KEYS:
        st.session_state.pop(key, None)


def render_sidebar() -> dict:
    """Draw the sidebar filters and return the matching MongoDB query.

    Returns:
        A $match document for the order-level collections.
    """
    months, states, categories = _options()

    with st.sidebar:
        st.divider()
        header = st.columns([1, 1])
        header[0].markdown(
            f"<span style='font-size:14px;font-weight:600;color:{theme.ON_SURFACE}'>Filters</span>",
            unsafe_allow_html=True,
        )
        header[1].button("Reset filters", on_click=_reset, width="stretch")

        if not months:
            st.warning(
                "No data loaded yet. Run `.\\tasks.ps1 pipeline` in PowerShell, "
                "then reload."
            )
            return {}

        default_start = DEFAULT_START if DEFAULT_START in months else months[0]
        default_end = DEFAULT_END if DEFAULT_END in months else months[-1]

        start, end = st.select_slider(
            "Purchase month",
            options=months,
            value=st.session_state.get("month_range", (default_start, default_end)),
            key="month_range",
        )

        chosen_states = st.multiselect(
            "Customer state",
            options=states,
            default=st.session_state.get("customer_states", []),
            key="customer_states",
            placeholder="All states",
        )

        chosen_categories = st.multiselect(
            "Product category",
            options=categories,
            default=st.session_state.get("categories", []),
            key="categories",
            placeholder="All categories",
        )

        st.divider()
        run_at = db.get_meta().get("run_at")
        if run_at:
            st.markdown(
                f"<span style='font-size:12px;color:{theme.OUTLINE}'>"
                f"Data updated {run_at:%d %b %Y, %H:%M}</span>",
                unsafe_allow_html=True,
            )

    match: dict = {"year_month": {"$gte": start, "$lte": end}}
    if chosen_states:
        match["customer_state"] = {"$in": chosen_states}
    if chosen_categories:
        match["primary_category"] = {"$in": chosen_categories}
    return match


def describe(match: dict) -> str:
    """Summarise the active filters in one sentence.

    Args:
        match: The $match document from render_sidebar.

    Returns:
        A short human-readable description.
    """
    if not match:
        return "No filters applied."

    window = match.get("year_month", {})
    parts = [f"{window.get('$gte', '?')} to {window.get('$lte', '?')}"]

    states = match.get("customer_state", {}).get("$in")
    parts.append(f"{len(states)} state(s)" if states else "all states")

    categories = match.get("primary_category", {}).get("$in")
    parts.append(f"{len(categories)} categor(ies)" if categories else "all categories")

    return " · ".join(parts)


def empty_state(what: str = "this selection") -> None:
    """Explain how to widen a selection that returned nothing.

    Args:
        what: Noun phrase naming what was empty.
    """
    st.info(
        f"No data for {what}. Try widening the month range, clearing the "
        "customer state filter, or selecting more categories."
    )
