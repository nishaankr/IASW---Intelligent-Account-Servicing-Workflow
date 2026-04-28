"""Shared visual components and CSS for the IASW Streamlit UI.

Imported by Home.py and the page files in pages/. Centralises:
  - Brand palette + global CSS (inject once per page).
  - Reusable badge/pill/chip helpers used across pages.
  - Document rendering helper that bypasses cross-origin iframe issues.

Naming convention: a leading underscore keeps this file from being treated
as a Streamlit page by the multipage discovery rule.
"""

import base64
from typing import Optional

import requests
import streamlit as st


# --- Brand palette ---------------------------------------------------------
# Banking-app inspired soft palette: steel-blue primary, warm off-white bg,
# muted semantic colors. Avoids the high-contrast pure-white + navy look.

COLOR_PRIMARY = "#3D5A80"
COLOR_PRIMARY_LIGHT = "#5C7B9C"
COLOR_PRIMARY_DARK = "#2A405A"
COLOR_TEXT = "#2D3748"
COLOR_TEXT_MUTED = "#64748B"
COLOR_BG = "#F6F8FB"
COLOR_BG_CARD = "#FFFFFF"
COLOR_BG_SOFT = "#EEF1F5"
COLOR_BORDER = "#E2E8F0"
COLOR_BORDER_SOFT = "#EDF0F4"
COLOR_SUCCESS = "#16A34A"
COLOR_SUCCESS_BG = "#F0FDF4"
COLOR_SUCCESS_BORDER = "#BBF7D0"
COLOR_WARNING = "#CA8A04"
COLOR_WARNING_BG = "#FEFCE8"
COLOR_WARNING_BORDER = "#FDE68A"
COLOR_ERROR = "#DC2626"
COLOR_ERROR_BG = "#FEF2F2"
COLOR_ERROR_BORDER = "#FECACA"
COLOR_INFO = "#2563EB"
COLOR_INFO_BG = "#EFF6FF"
COLOR_INFO_BORDER = "#BFDBFE"


# --- Global CSS ------------------------------------------------------------

_CSS = f"""
<style>
  /* Hide Streamlit chrome */
  #MainMenu {{ visibility: hidden; }}
  footer {{ visibility: hidden; }}

  /* Container width and padding */
  .block-container {{
    padding-top: 1.8rem;
    padding-bottom: 4rem;
    max-width: 1280px;
  }}

  /* Hero banner — softer gradient, no harsh contrast */
  .iasw-hero {{
    background: linear-gradient(135deg, {COLOR_PRIMARY} 0%, {COLOR_PRIMARY_LIGHT} 100%);
    color: white;
    padding: 24px 30px;
    border-radius: 14px;
    margin-bottom: 26px;
    box-shadow: 0 1px 2px rgba(45, 55, 72, 0.06);
  }}
  .iasw-hero h1 {{
    margin: 0;
    font-size: 24px;
    font-weight: 700;
    color: white !important;
    letter-spacing: -0.01em;
  }}
  .iasw-hero p {{
    margin: 6px 0 0 0;
    opacity: 0.92;
    font-size: 14px;
    line-height: 1.5;
    color: rgba(255,255,255,0.92);
  }}

  /* Section label — small uppercase divider between blocks */
  .iasw-section-title {{
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: {COLOR_TEXT_MUTED};
    margin: 22px 0 10px 0;
  }}

  /* Pill / badge */
  .iasw-badge {{
    display: inline-block;
    padding: 4px 11px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    line-height: 1.4;
    white-space: nowrap;
    border: 1px solid transparent;
  }}

  /* Score chip — bigger, bolder, "X / 5" format */
  .iasw-score {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 64px;
    padding: 7px 12px;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 700;
    border: 1px solid transparent;
    box-shadow: 0 1px 1px rgba(0,0,0,0.03);
  }}

  /* Score row — full card per dimension */
  .iasw-score-row {{
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 14px 16px;
    border: 1px solid {COLOR_BORDER_SOFT};
    border-radius: 10px;
    background: {COLOR_BG_CARD};
    margin-bottom: 8px;
    transition: border-color 0.15s ease;
  }}
  .iasw-score-row:hover {{
    border-color: {COLOR_BORDER};
  }}
  .iasw-score-row .label {{
    font-weight: 600;
    color: {COLOR_TEXT};
    font-size: 14px;
    margin-bottom: 2px;
  }}
  .iasw-score-row .reason {{
    color: {COLOR_TEXT_MUTED};
    font-size: 13px;
    line-height: 1.55;
  }}

  /* Soft "key/value" panel */
  .iasw-kv {{
    background: {COLOR_BG_SOFT};
    border: 1px solid {COLOR_BORDER_SOFT};
    border-radius: 10px;
    padding: 12px 16px;
    font-size: 13px;
    line-height: 1.55;
  }}

  /* Heading colors — use brand primary, not navy */
  h1 {{ color: {COLOR_PRIMARY} !important; }}
  h2 {{ color: {COLOR_PRIMARY_LIGHT} !important; font-size: 20px !important; font-weight: 600 !important; }}
  h3 {{ color: {COLOR_PRIMARY_LIGHT} !important; font-size: 16px !important; font-weight: 600 !important; }}

  /* Streamlit metric tiles — softer card look */
  div[data-testid="stMetric"] {{
    background: {COLOR_BG_CARD};
    border: 1px solid {COLOR_BORDER_SOFT};
    border-radius: 10px;
    padding: 14px 16px;
    box-shadow: 0 1px 2px rgba(45, 55, 72, 0.03);
  }}
  div[data-testid="stMetricValue"] {{ color: {COLOR_PRIMARY} !important; font-weight: 700 !important; }}
  div[data-testid="stMetricLabel"] {{ color: {COLOR_TEXT_MUTED} !important; font-size: 12px !important; }}

  /* Buttons — soft corners, brand color for primary */
  .stButton > button {{
    border-radius: 8px;
    font-weight: 600;
    border: 1px solid {COLOR_BORDER};
    transition: all 0.15s ease;
  }}
  .stButton > button[kind="primary"] {{
    background: {COLOR_PRIMARY};
    border-color: {COLOR_PRIMARY};
  }}
  .stButton > button[kind="primary"]:hover {{
    background: {COLOR_PRIMARY_DARK};
    border-color: {COLOR_PRIMARY_DARK};
  }}

  /* Form inputs — softer borders */
  .stTextInput > div > div,
  .stTextArea > div > div,
  .stSelectbox > div > div {{
    border-radius: 8px;
    border-color: {COLOR_BORDER} !important;
  }}
  .stTextInput input::placeholder,
  .stTextArea textarea::placeholder {{
    color: {COLOR_TEXT_MUTED} !important;
    opacity: 0.65 !important;
  }}

  /* Bordered containers — softer */
  div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: 12px !important;
    border-color: {COLOR_BORDER_SOFT} !important;
    background: {COLOR_BG_CARD} !important;
  }}

  /* Document viewer wrapper */
  .iasw-doc-wrap {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
    overflow: hidden;
    background: {COLOR_BG_SOFT};
    padding: 0;
  }}
</style>
"""


def inject_css() -> None:
    """Inject shared CSS once per page. Call after st.set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)


# --- Reusable HTML components ---------------------------------------------

def hero(title: str, subtitle: str) -> None:
    """Branded gradient banner at the top of a page."""
    st.markdown(
        f'<div class="iasw-hero"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def section_label(text: str) -> None:
    """Small uppercase section label between blocks."""
    st.markdown(
        f'<div class="iasw-section-title">{text}</div>',
        unsafe_allow_html=True,
    )


def _confidence_palette(value):
    if value is None:
        return COLOR_TEXT_MUTED, COLOR_BG_SOFT, COLOR_BORDER_SOFT
    if value >= 0.85:
        return COLOR_SUCCESS, COLOR_SUCCESS_BG, COLOR_SUCCESS_BORDER
    if value >= 0.50:
        return COLOR_WARNING, COLOR_WARNING_BG, COLOR_WARNING_BORDER
    return COLOR_ERROR, COLOR_ERROR_BG, COLOR_ERROR_BORDER


def confidence_badge(value) -> str:
    """HTML pill showing 0-1 confidence, semantically coloured."""
    if value is None:
        return (f'<span class="iasw-badge" style="color:{COLOR_TEXT_MUTED};'
                f'background:{COLOR_BG_SOFT};border-color:{COLOR_BORDER_SOFT}">—</span>')
    txt, bg, border = _confidence_palette(value)
    return (f'<span class="iasw-badge" style="color:{txt};background:{bg};'
            f'border-color:{border}">{value:.1%}</span>')


def status_badge(status: str) -> str:
    palette = {
        "PENDING_AI":                (COLOR_INFO,    COLOR_INFO_BG,    COLOR_INFO_BORDER),
        "AI_VERIFIED_PENDING_HUMAN": (COLOR_WARNING, COLOR_WARNING_BG, COLOR_WARNING_BORDER),
        "APPROVED":                  (COLOR_SUCCESS, COLOR_SUCCESS_BG, COLOR_SUCCESS_BORDER),
        "REJECTED":                  (COLOR_ERROR,   COLOR_ERROR_BG,   COLOR_ERROR_BORDER),
    }
    txt, bg, border = palette.get(status, (COLOR_TEXT_MUTED, COLOR_BG_SOFT, COLOR_BORDER_SOFT))
    label = (status or "—").replace("_", " ")
    return (f'<span class="iasw-badge" style="color:{txt};background:{bg};'
            f'border-color:{border}">{label}</span>')


def recommendation_badge(action: str) -> str:
    palette = {
        "APPROVE": (COLOR_SUCCESS, COLOR_SUCCESS_BG, COLOR_SUCCESS_BORDER),
        "REJECT":  (COLOR_ERROR,   COLOR_ERROR_BG,   COLOR_ERROR_BORDER),
        "REVIEW":  (COLOR_WARNING, COLOR_WARNING_BG, COLOR_WARNING_BORDER),
    }
    if action is None:
        return (f'<span class="iasw-badge" style="color:{COLOR_TEXT_MUTED};'
                f'background:{COLOR_BG_SOFT};border-color:{COLOR_BORDER_SOFT}">—</span>')
    txt, bg, border = palette.get(action, (COLOR_TEXT_MUTED, COLOR_BG_SOFT, COLOR_BORDER_SOFT))
    return (f'<span class="iasw-badge" style="color:{txt};background:{bg};'
            f'border-color:{border}">{action}</span>')


def score_chip(score) -> str:
    """Big chip showing a 0-5 dimension score as 'X / 5' with semantic color."""
    if score is None:
        return (f'<span class="iasw-score" style="color:{COLOR_TEXT_MUTED};'
                f'background:{COLOR_BG_SOFT};border-color:{COLOR_BORDER_SOFT}">— / 5</span>')
    s = int(score)
    if s >= 4:
        txt, bg, border = COLOR_SUCCESS, COLOR_SUCCESS_BG, COLOR_SUCCESS_BORDER
    elif s == 3:
        txt, bg, border = COLOR_INFO, COLOR_INFO_BG, COLOR_INFO_BORDER
    elif s == 2:
        txt, bg, border = COLOR_WARNING, COLOR_WARNING_BG, COLOR_WARNING_BORDER
    else:
        txt, bg, border = COLOR_ERROR, COLOR_ERROR_BG, COLOR_ERROR_BORDER
    return (f'<span class="iasw-score" style="color:{txt};background:{bg};'
            f'border-color:{border}">{s} / 5</span>')


def score_row(label: str, score, reason: str) -> str:
    """Render a full score-card row (chip + label + reason) as HTML."""
    chip = score_chip(score)
    safe_reason = (reason or "").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<div class="iasw-score-row">'
        f'  <div>{chip}</div>'
        '  <div style="flex:1">'
        f'    <div class="label">{label}</div>'
        f'    <div class="reason">{safe_reason}</div>'
        '  </div>'
        '</div>'
    )


# --- Document rendering ----------------------------------------------------

def render_document(doc_url: str, height: int = 700) -> None:
    """Render an archived document inline.

    Fetches the bytes server-side and embeds them via a base64 data URL
    (or st.image for images). Sidesteps cross-origin iframe issues and
    Content-Disposition: attachment quirks that would otherwise force the
    browser to download instead of display.
    """
    try:
        resp = requests.get(doc_url, timeout=10)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        st.error(f"Could not load document: {e}", icon="🚫")
        return

    ct = resp.headers.get("content-type", "").split(";")[0].strip().lower()

    if ct.startswith("image/"):
        # Native Streamlit image rendering scales nicely and respects column width.
        # `use_column_width=True` is the universally-supported argument across
        # Streamlit versions; newer versions also accept `use_container_width`,
        # but older ones don't, so we stick with the broadly compatible one.
        st.image(resp.content, use_column_width=True)
    elif ct == "application/pdf":
        # Embed via base64 data URL — same-origin, no Content-Disposition issues.
        b64 = base64.b64encode(resp.content).decode("ascii")
        st.markdown(
            f'<div class="iasw-doc-wrap">'
            f'<iframe src="data:application/pdf;base64,{b64}#view=FitH" '
            f'width="100%" height="{height}px" '
            f'style="border:0;display:block;"></iframe>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.warning(f"Unsupported document type: {ct or 'unknown'}", icon="📄")
        return

    # Always offer a direct link for download as a fallback.
    st.markdown(
        f'<div style="margin-top:8px;font-size:13px">'
        f'<a href="{doc_url}" target="_blank" style="color:{COLOR_PRIMARY}">'
        f'Open in new tab ↗</a></div>',
        unsafe_allow_html=True,
    )
