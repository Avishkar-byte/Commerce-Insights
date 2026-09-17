"""HTML building blocks that mirror the reference design in `UI/`.

Each helper emits the same structure and tokens as the approved screens, so the
pages read as one system rather than as styled Streamlit defaults.
"""

from __future__ import annotations

from collections.abc import Iterable

import streamlit as st

from lib import theme


def html(markup: str) -> None:
    """Render an HTML fragment safely as a single line.

    Streamlit renders markdown, and markdown ends an inline HTML block at the
    first blank or whitespace-only line, which would silently drop everything
    after it. Collapsing the fragment onto one line removes that failure mode.
    Lines are joined with a space so words split across source lines stay apart.

    Args:
        markup: The HTML fragment, which may be indented and multi-line.
    """
    st.markdown(
        " ".join(line.strip() for line in markup.splitlines() if line.strip()),
        unsafe_allow_html=True,
    )


def topbar() -> None:
    """Draw the thin header bar with the account avatar, as in the reference."""
    html(
        f"""
        <div style="display:flex;align-items:center;justify-content:flex-end;
                    height:56px;margin:-2.5rem -2.5rem 1.5rem -2.5rem;
                    padding:0 2.5rem;border-bottom:1px solid {theme.OUTLINE_VARIANT};
                    background:{theme.SURFACE_LOWEST}">
          <div style="width:32px;height:32px;border-radius:9999px;
                      background:{theme.PRIMARY};display:flex;align-items:center;
                      justify-content:center;color:#fff;font-size:13px;font-weight:600">A</div>
        </div>
        """
    )


def page_title(title: str, subtitle: str, eyebrow: str | None = None) -> None:
    """Draw the page heading block.

    Args:
        title: Page title, 28px.
        subtitle: One supporting line, 14px muted.
        eyebrow: Optional breadcrumb line above the title.
    """
    crumb = (
        f"<div style='font-size:12px;line-height:16px;color:{theme.SECONDARY};"
        f"margin-bottom:4px'>{eyebrow}</div>"
        if eyebrow
        else ""
    )
    html(
        f"""
        <div style="margin-bottom:2rem">
          {crumb}
          <h1 style="font-size:28px;line-height:36px;font-weight:600;
                     letter-spacing:-0.02em;color:{theme.ON_SURFACE};margin:0 0 4px 0">{title}</h1>
          <p style="font-size:14px;line-height:20px;color:{theme.SECONDARY};margin:0">{subtitle}</p>
        </div>
        """
    )


def kpi_grid(items: Iterable[tuple[str, str, str]]) -> None:
    """Draw the row of statistic tiles.

    Args:
        items: One (label, value, note) triple per tile.
    """
    tiles = list(items)
    cells = "".join(
        f"""
        <div style="display:flex;flex-direction:column;gap:6px;padding:16px;
                    border-radius:8px;background:{theme.SURFACE_LOW}">
          <span style="font-size:12px;line-height:16px;font-weight:500;
                       color:{theme.SECONDARY}">{label}</span>
          <span style="font-size:28px;line-height:36px;font-weight:600;
                       letter-spacing:-0.02em;color:{theme.ON_SURFACE};
                       font-variant-numeric:tabular-nums">{value}</span>
          <span style="font-size:12px;line-height:16px;color:{theme.SECONDARY}">{note}</span>
        </div>
        """
        for label, value, note in tiles
    )
    html(
        f"""
        <div style="display:grid;grid-template-columns:repeat({len(tiles)},minmax(0,1fr));
                    gap:24px;margin-bottom:2rem">{cells}</div>
        """
    )


def card_header(title: str, subtitle: str | None = None, aside: str | None = None) -> None:
    """Draw the heading inside a chart card.

    Args:
        title: A question or finding, 20px.
        subtitle: Optional supporting line, 12px muted.
        aside: Optional right-aligned note.
    """
    right = (
        f"<span style='font-size:12px;line-height:16px;color:{theme.SECONDARY}'>{aside}</span>"
        if aside
        else ""
    )
    sub = (
        f"<span style='font-size:12px;line-height:16px;color:{theme.SECONDARY}'>{subtitle}</span>"
        if subtitle
        else ""
    )
    html(
        f"""
        <div style="display:flex;align-items:flex-start;justify-content:space-between;
                    margin-bottom:1rem;gap:1rem">
          <div style="display:flex;flex-direction:column;gap:4px">
            <h2 style="font-size:20px;line-height:28px;font-weight:600;letter-spacing:-0.01em;
                       color:{theme.ON_SURFACE};margin:0">{title}</h2>
            {sub}
          </div>
          {right}
        </div>
        """
    )


def section_label(text: str, aside: str | None = None) -> None:
    """Draw a small section heading with an optional right-aligned note.

    Args:
        text: Section label, 14px semibold.
        aside: Optional right-aligned note, 12px muted.
    """
    right = (
        f"<span style='font-size:12px;line-height:16px;color:{theme.SECONDARY}'>{aside}</span>"
        if aside
        else ""
    )
    html(
        f"""
        <div style="display:flex;align-items:center;justify-content:space-between;
                    padding-bottom:4px;margin-bottom:12px">
          <span style="font-size:14px;line-height:20px;font-weight:600;
                       color:{theme.ON_SURFACE}">{text}</span>
          {right}
        </div>
        """
    )


def module_card(name: str, tag: str, description: str) -> None:
    """Draw one analysis-module row from the home page.

    Args:
        name: Page name.
        tag: Short category chip.
        description: One line describing the page.
    """
    html(
        f"""
        <div style="background:{theme.SURFACE_LOWEST};border:1px solid {theme.OUTLINE_VARIANT};
                    border-radius:8px;padding:20px;margin-bottom:12px;
                    display:flex;align-items:center;justify-content:space-between;gap:24px">
          <div style="display:flex;flex-direction:column;gap:4px">
            <div style="display:flex;align-items:center;gap:12px">
              <span style="font-size:16px;line-height:24px;font-weight:600;
                           color:{theme.ON_SURFACE}">{name}</span>
              <span style="display:inline-flex;align-items:center;padding:2px 8px;
                           background:{theme.SURFACE_CONTAINER};border-radius:4px;
                           font-size:12px;line-height:16px;font-weight:500;
                           color:{theme.SECONDARY}">{tag}</span>
            </div>
            <p style="font-size:14px;line-height:20px;color:{theme.SECONDARY};
                      margin:0">{description}</p>
          </div>
          <span style="font-size:14px;line-height:20px;font-weight:500;
                       color:{theme.PRIMARY};white-space:nowrap">Open page &rarr;</span>
        </div>
        """
    )


def headline(sentence_html: str, note: str) -> None:
    """Draw the home page's computed headline sentence.

    Args:
        sentence_html: The sentence, may contain highlight spans.
        note: Small line under the sentence.
    """
    html(
        f"""
        <div style="background:{theme.SURFACE_LOWEST};border:1px solid {theme.OUTLINE_VARIANT};
                    border-radius:8px;padding:24px;margin-bottom:1.5rem">
          <div style="max-width:760px;display:flex;flex-direction:column;gap:8px">
            <p style="font-size:20px;line-height:32px;font-weight:400;
                      color:{theme.ON_SURFACE};margin:0">{sentence_html}</p>
            <p style="font-size:14px;line-height:20px;color:{theme.SECONDARY};
                      margin:0">{note}</p>
          </div>
        </div>
        """
    )


def highlight(text: str) -> str:
    """Wrap a value so it stands out inside the headline sentence.

    Args:
        text: The value to emphasise.

    Returns:
        An HTML span in the primary colour.
    """
    return f"<span style='color:{theme.PRIMARY_CONTAINER};font-weight:600'>{text}</span>"


def notice(text: str) -> None:
    """Draw the flat information banner used above some page titles.

    Args:
        text: The message, in sentence case.
    """
    html(
        f"""
        <div style="background:{theme.SURFACE_LOW};border:1px solid {theme.OUTLINE_VARIANT};
                    border-radius:8px;padding:12px 16px;margin-bottom:1.5rem;
                    font-size:13px;line-height:18px;color:{theme.SECONDARY}">{text}</div>
        """
    )


def about_box(title: str, text: str) -> None:
    """Draw the tinted footnote box at the bottom of the home page.

    Args:
        title: Box heading.
        text: Body copy.
    """
    html(
        f"""
        <div style="margin-top:2.5rem;background:{theme.SURFACE_LOW};border-radius:8px;
                    padding:16px">
          <div style="display:flex;flex-direction:column;gap:4px">
            <span style="font-size:12px;line-height:16px;font-weight:600;
                         color:{theme.ON_SURFACE}">{title}</span>
            <p style="font-size:12px;line-height:16px;color:{theme.SECONDARY};
                      margin:0">{text}</p>
          </div>
        </div>
        """
    )


def ranked_bar_list(rows: list[tuple[str, str, float]], color: str | None = None) -> None:
    """Draw a label, inline bar and value list, as used for categories and states.

    Args:
        rows: One (label, formatted value, fraction of maximum) triple per row.
        color: Bar colour; defaults to the primary container colour.
    """
    fill = color or theme.PRIMARY_CONTAINER
    body = "".join(
        f"""
        <div style="display:grid;grid-template-columns:150px 1fr 110px;align-items:center;
                    gap:12px;padding:5px 0">
          <span style="font-size:13px;color:{theme.ON_SURFACE};overflow:hidden;
                       text-overflow:ellipsis;white-space:nowrap">{label}</span>
          <div style="background:{theme.SURFACE_LOW};border-radius:3px;height:14px">
            <div style="width:{max(2.0, share * 100):.1f}%;background:{fill};
                        height:14px;border-radius:3px"></div>
          </div>
          <span style="font-size:13px;color:{theme.SECONDARY};text-align:right;
                       font-variant-numeric:tabular-nums">{value}</span>
        </div>
        """
        for label, value, share in rows
    )
    html(f"<div>{body}</div>")
