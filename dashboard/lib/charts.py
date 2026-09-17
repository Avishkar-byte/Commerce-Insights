"""Reusable Plotly chart builders.

Figures only. The surrounding cards, titles and tiles live in lib/ui.py so the
layout matches the reference design in UI/.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import theme


def show(figure: go.Figure, height: int = 360) -> None:
    """Display a figure with the project's standard sizing.

    Args:
        figure: The figure to draw.
        height: Pixel height.
    """
    figure.update_layout(height=height)
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})


def combo_bar_line(
    df: pd.DataFrame,
    x: str,
    bar: str,
    line: str,
    bar_name: str,
    line_name: str,
) -> go.Figure:
    """Build a bar series with a line series on a secondary axis.

    Args:
        df: Source frame, already sorted.
        x: Category column.
        bar: Column drawn as bars.
        line: Column drawn as a line.
        bar_name: Legend label for the bars.
        line_name: Legend label for the line.

    Returns:
        The figure.
    """
    figure = go.Figure()
    figure.add_bar(
        x=df[x], y=df[bar], name=bar_name, marker_color=theme.PRIMARY_CONTAINER, yaxis="y"
    )
    figure.add_scatter(
        x=df[x],
        y=df[line],
        name=line_name,
        mode="lines+markers",
        line={"color": theme.SECONDARY, "width": 2},
        marker={"size": 5},
        yaxis="y2",
    )
    figure.update_layout(
        yaxis={"title": bar_name, "rangemode": "tozero"},
        yaxis2={
            "title": line_name,
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
            "rangemode": "tozero",
        },
        hovermode="x unified",
    )
    return figure


def horizontal_bar(
    df: pd.DataFrame,
    label: str,
    value: str,
    text: list[str] | None = None,
    color: str | list[str] | None = None,
) -> go.Figure:
    """Build a horizontal bar chart, largest value at the top.

    Args:
        df: Source frame, already sorted descending.
        label: Category column.
        value: Measure column.
        text: Optional per-bar labels.
        color: A single colour or one colour per bar.

    Returns:
        The figure.
    """
    figure = go.Figure(
        go.Bar(
            x=df[value],
            y=df[label],
            orientation="h",
            marker_color=color or theme.PRIMARY_CONTAINER,
            text=text,
            textposition="auto",
            hovertemplate="%{y}: %{x:,.0f}<extra></extra>",
        )
    )
    figure.update_layout(
        yaxis={"autorange": "reversed", "title": None},
        xaxis={"title": None},
        showlegend=False,
    )
    return figure


def line(df: pd.DataFrame, x: str, y: str, name: str, percent: bool = False) -> go.Figure:
    """Build a single line chart.

    Args:
        df: Source frame, already sorted.
        x: Category column.
        y: Measure column.
        name: Series name.
        percent: Format the y axis as a percentage.

    Returns:
        The figure.
    """
    figure = go.Figure(
        go.Scatter(
            x=df[x],
            y=df[y],
            name=name,
            mode="lines+markers",
            line={"color": theme.PRIMARY_CONTAINER, "width": 2},
            marker={"size": 5},
        )
    )
    figure.update_layout(
        yaxis={"rangemode": "tozero", "tickformat": ".0%" if percent else None},
        hovermode="x unified",
        showlegend=False,
    )
    return figure


def stacked_percent(
    df: pd.DataFrame, label: str, series: list[str], colors: dict[str, str]
) -> go.Figure:
    """Build a 100 percent stacked horizontal bar chart.

    Args:
        df: Source frame with one row per label.
        label: Category column drawn on the y axis.
        series: Columns stacked left to right.
        colors: Colour per series name.

    Returns:
        The figure.
    """
    totals = df[series].sum(axis=1).replace(0, pd.NA)
    figure = go.Figure()
    for name in series:
        figure.add_bar(
            y=df[label],
            x=(df[name] / totals).fillna(0),
            name=name,
            orientation="h",
            marker_color=colors.get(name, theme.NEUTRAL),
            hovertemplate="%{y} · " + name + ": %{x:.1%}<extra></extra>",
        )
    figure.update_layout(
        barmode="stack",
        legend={"traceorder": "normal"},
        xaxis={"tickformat": ".0%", "title": None, "range": [0, 1]},
        yaxis={"autorange": "reversed", "title": None},
    )
    return figure
