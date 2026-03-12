"""
Ambient Email Assistant — Redesigned UI
Dark command-centre aesthetic with glassmorphism cards.
"""

import os
import pickle
import base64
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from email.mime.text import MIMEText
import re
import requests as _requests

import streamlit as st

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import ChatPromptTemplate
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

APP_URL      = "https://inboxai.streamlit.app"
REDIRECT_URI = APP_URL
MEMORY_DIR   = "memory"
MEMORY_FILE  = os.path.join(MEMORY_DIR, "conversation_memory.pkl")

# ---------------------------------------------------------------------------
# CUSTOM CSS
# ---------------------------------------------------------------------------

def inject_css():
    st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,300&display=swap" rel="stylesheet">
    <style>
    /* ── Reset & base ───────────────────────────────── */
    html, body, [data-testid="stAppViewContainer"] {
        background: #080c14 !important;
        font-family: 'DM Sans', sans-serif;
        color: #c8d6e8;
    }
    [data-testid="stHeader"] { background: transparent !important; }
    [data-testid="stSidebar"] {
        background: #0d1420 !important;
        border-right: 1px solid rgba(99,179,237,0.12);
    }
    [data-testid="stSidebar"] * { color: #a0b4cc !important; }

    /* ── Hide streamlit chrome ──────────────────────── */
    #MainMenu, footer, [data-testid="stToolbar"] { display: none !important; }

    /* ── Hero header ────────────────────────────────── */
    .hero {
        background: linear-gradient(135deg, #0d1f35 0%, #091525 50%, #060e1a 100%);
        border: 1px solid rgba(99,179,237,0.15);
        border-radius: 20px;
        padding: 48px 40px 40px;
        margin-bottom: 32px;
        position: relative;
        overflow: hidden;
    }
    .hero::before {
        content: '';
        position: absolute;
        top: -60px; right: -60px;
        width: 260px; height: 260px;
        background: radial-gradient(circle, rgba(56,189,248,0.12) 0%, transparent 70%);
        pointer-events: none;
    }
    .hero::after {
        content: '';
        position: absolute;
        bottom: -40px; left: 20%;
        width: 180px; height: 180px;
        background: radial-gradient(circle, rgba(139,92,246,0.08) 0%, transparent 70%);
        pointer-events: none;
    }
    .hero-title {
        font-family: 'Syne', sans-serif;
        font-size: 2.6rem;
        font-weight: 800;
        color: #f0f7ff;
        letter-spacing: -0.02em;
        margin: 0 0 8px 0;
        line-height: 1.1;
    }
    .hero-sub {
        font-size: 1.05rem;
        color: #7a9ab8;
        font-weight: 300;
        margin: 0;
    }
    .hero-badge {
        display: inline-block;
        background: rgba(56,189,248,0.12);
        border: 1px solid rgba(56,189,248,0.3);
        color: #38bdf8;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        padding: 4px 12px;
        border-radius: 20px;
        margin-bottom: 16px;
    }

    /* ── Stat cards ─────────────────────────────────── */
    .stat-row {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        margin-bottom: 28px;
    }
    .stat-card {
        background: linear-gradient(145deg, #0f1c2e, #0a1420);
        border: 1px solid rgba(99,179,237,0.1);
        border-radius: 16px;
        padding: 22px 20px;
        position: relative;
        overflow: hidden;
        transition: border-color 0.2s, transform 0.2s;
    }
    .stat-card:hover {
        border-color: rgba(99,179,237,0.28);
        transform: translateY(-2px);
    }
    .stat-card-accent {
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        border-radius: 16px 16px 0 0;
    }
    .accent-blue  { background: linear-gradient(90deg, #38bdf8, #6366f1); }
    .accent-green { background: linear-gradient(90deg, #34d399, #10b981); }
    .accent-amber { background: linear-gradient(90deg, #fbbf24, #f59e0b); }
    .accent-rose  { background: linear-gradient(90deg, #f87171, #e11d48); }
    .stat-label {
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #4a6a8a;
        margin-bottom: 8px;
    }
    .stat-value {
        font-family: 'Syne', sans-serif;
        font-size: 2rem;
        font-weight: 700;
        color: #e2edf8;
        line-height: 1;
    }

    /* ── Glass cards ────────────────────────────────── */
    .glass-card {
        background: rgba(13, 26, 45, 0.7);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(99,179,237,0.1);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 16px;
    }
    .card-title {
        font-family: 'Syne', sans-serif;
        font-size: 0.95rem;
        font-weight: 700;
        color: #e2edf8;
        letter-spacing: 0.02em;
        margin-bottom: 4px;
    }
    .card-meta {
        font-size: 0.8rem;
        color: #4a6a8a;
        margin-bottom: 12px;
    }

    /* ── Email row ──────────────────────────────────── */
    .email-row {
        background: linear-gradient(135deg, #0d1a2d, #091422);
        border: 1px solid rgba(99,179,237,0.08);
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 10px;
        transition: border-color 0.2s, background 0.2s;
        cursor: pointer;
    }
    .email-row:hover {
        border-color: rgba(99,179,237,0.22);
        background: linear-gradient(135deg, #102035, #0c1a2e);
    }
    .email-row-unread { border-left: 3px solid #38bdf8; }
    .email-subject {
        font-family: 'Syne', sans-serif;
        font-size: 0.92rem;
        font-weight: 600;
        color: #deeaf8;
        margin-bottom: 3px;
    }
    .email-from {
        font-size: 0.78rem;
        color: #4a6a8a;
    }

    /* ── Priority pill ──────────────────────────────── */
    .pill {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .pill-urgent  { background: rgba(248,113,113,0.15); color: #f87171; border: 1px solid rgba(248,113,113,0.3); }
    .pill-work    { background: rgba(56,189,248,0.12);  color: #38bdf8; border: 1px solid rgba(56,189,248,0.25); }
    .pill-personal{ background: rgba(52,211,153,0.12);  color: #34d399; border: 1px solid rgba(52,211,153,0.25); }
    .pill-newsletter{ background: rgba(251,191,36,0.1); color: #fbbf24; border: 1px solid rgba(251,191,36,0.25); }
    .pill-default { background: rgba(99,179,237,0.1);   color: #63b3ed; border: 1px solid rgba(99,179,237,0.2); }

    /* ── Section heading ────────────────────────────── */
    .section-heading {
        font-family: 'Syne', sans-serif;
        font-size: 1.25rem;
        font-weight: 700;
        color: #e2edf8;
        letter-spacing: -0.01em;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .section-heading::after {
        content: '';
        flex: 1;
        height: 1px;
        background: linear-gradient(90deg, rgba(99,179,237,0.2), transparent);
    }

    /* ── Conflict card ──────────────────────────────── */
    .conflict-card {
        background: linear-gradient(135deg, #1a0f1e, #14091a);
        border: 1px solid rgba(248,113,113,0.2);
        border-left: 3px solid #f87171;
        border-radius: 12px;
        padding: 18px 20px;
        margin-bottom: 12px;
    }
    .conflict-title {
        font-family: 'Syne', sans-serif;
        font-size: 0.9rem;
        font-weight: 700;
        color: #fca5a5;
        margin-bottom: 6px;
    }
    .conflict-detail {
        font-size: 0.8rem;
        color: #7a5a5a;
    }

    /* ── Event row ──────────────────────────────────── */
    .event-row {
        background: linear-gradient(135deg, #0d1e35, #091525);
        border: 1px solid rgba(99,179,237,0.08);
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 16px;
    }
    .event-time {
        font-family: 'Syne', sans-serif;
        font-size: 0.8rem;
        font-weight: 600;
        color: #38bdf8;
        min-width: 110px;
        white-space: nowrap;
    }
    .event-title-text {
        font-size: 0.88rem;
        color: #c8d6e8;
        font-weight: 500;
    }

    /* ── Suggestion banner ──────────────────────────── */
    .suggestion-banner {
        background: linear-gradient(135deg, #0d2040, #091830);
        border: 1px solid rgba(56,189,248,0.2);
        border-left: 3px solid #38bdf8;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 10px;
        font-size: 0.88rem;
        color: #7ab8d8;
    }

    /* ── Streamlit widget overrides ─────────────────── */
    .stButton > button {
        background: linear-gradient(135deg, #1a3a5c, #152e4a) !important;
        border: 1px solid rgba(99,179,237,0.25) !important;
        color: #a8d4f0 !important;
        border-radius: 10px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 500 !important;
        font-size: 0.88rem !important;
        padding: 0.45rem 1rem !important;
        transition: all 0.2s !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #1e4570, #183556) !important;
        border-color: rgba(99,179,237,0.45) !important;
        color: #d0eaff !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 20px rgba(56,189,248,0.12) !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #0f6fbd, #0857a0) !important;
        border-color: rgba(56,189,248,0.4) !important;
        color: #e8f5ff !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #1380d4, #0966b8) !important;
        box-shadow: 0 4px 24px rgba(56,189,248,0.25) !important;
    }
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        background: #0a1525 !important;
        border: 1px solid rgba(99,179,237,0.18) !important;
        border-radius: 10px !important;
        color: #c8d6e8 !important;
        font-family: 'DM Sans', sans-serif !important;
        font-size: 0.88rem !important;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: rgba(56,189,248,0.45) !important;
        box-shadow: 0 0 0 3px rgba(56,189,248,0.08) !important;
    }
    .stSelectbox > div > div {
        background: #0a1525 !important;
        border: 1px solid rgba(99,179,237,0.18) !important;
        border-radius: 10px !important;
        color: #c8d6e8 !important;
    }
    [data-testid="stMetricValue"] {
        font-family: 'Syne', sans-serif !important;
        color: #e2edf8 !important;
        font-weight: 700 !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.72rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
        color: #4a6a8a !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        background: transparent !important;
        gap: 4px;
        border-bottom: 1px solid rgba(99,179,237,0.1) !important;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent !important;
        border-radius: 8px 8px 0 0 !important;
        color: #4a6a8a !important;
        font-family: 'Syne', sans-serif !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        padding: 10px 20px !important;
        border: none !important;
        transition: color 0.2s !important;
    }
    .stTabs [aria-selected="true"] {
        color: #38bdf8 !important;
        border-bottom: 2px solid #38bdf8 !important;
        background: transparent !important;
    }
    .stTabs [data-baseweb="tab"]:hover { color: #a0c8e8 !important; }
    .stExpander {
        background: #0d1a2d !important;
        border: 1px solid rgba(99,179,237,0.1) !important;
        border-radius: 12px !important;
    }
    .stExpander > div > div > div > div {
        background: transparent !important;
        color: #c8d6e8 !important;
    }
    div[data-testid="stSlider"] > div { color: #38bdf8 !important; }
    .stNumberInput > div > div > input {
        background: #0a1525 !important;
        border: 1px solid rgba(99,179,237,0.18) !important;
        color: #c8d6e8 !important;
        border-radius: 10px !important;
    }
    div[data-testid="stMarkdownContainer"] p { color: #a0b8cc; }
    .stAlert {
        border-radius: 10px !important;
        border: none !important;
    }
    [data-testid="stSidebarContent"] {
        padding: 24px 16px !important;
    }
    label[data-testid="stWidgetLabel"] > div > p {
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
        color: #4a6a8a !important;
    }
    .stSuccess {
        background: rgba(52,211,153,0.08) !important;
        border: 1px solid rgba(52,211,153,0.2) !important;
        color: #34d399 !important;
        border-radius: 10px !important;
    }
    .stError {
        background: rgba(248,113,113,0.08) !important;
        border: 1px solid rgba(248,113,113,0.2) !important;
        color: #f87171 !important;
        border-radius: 10px !important;
    }
    .stInfo {
        background: rgba(56,189,248,0.06) !important;
        border: 1px solid rgba(56,189,248,0.18) !important;
        color: #7ab8d8 !important;
        border-radius: 10px !important;
    }
    .stSpinner > div { border-top-color: #38bdf8 !important; }
    </style>
    """, unsafe_allow_html=True)


def render_hero(user_email: str = ""):
    st.markdown(f"""
    <div class="hero">
      <div class="hero-badge">✦ AI-Powered Inbox</div>
      <div class="hero-title">Ambient Email<br>Assistant</div>
      <div class="hero-sub">
        Intelligent email analysis, conflict detection &amp; smart scheduling.
        {"&nbsp;·&nbsp; <span style='color:#38bdf8'>" + user_email + "</span>" if user_email else ""}
      </div>
    </div>
    """, unsafe_allow_html=True)


def pill_html(category: Optional[str]) -> str:
    cat  = (category or "").lower()
    cls  = {"urgent": "pill-urgent", "work": "pill-work",
            "personal": "pill-personal", "newsletter": "pill-newsletter"}.get(cat, "pill-default")
    label= cat.capitalize() if cat else "—"
    return f'<span class="pill {cls}">{label}</span>'


# ---------------------------------------------------------------------------
# OAUTH — pure requests, zero oauthlib, zero PKCE
# ---------------------------------------------------------------------------

def _google_creds_config() -> dict:
    try:
        cid     = st.secrets["google_credentials"]["client_id"]
        csecret = st.secrets["google_credentials"]["client_secret"]
    except (KeyError, FileNotFoundError):
        cid     = os.getenv("GOOGLE_CLIENT_ID", "")
        csecret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not cid or not csecret:
        st.error("Google credentials not found. Add them to Streamlit secrets.")
        st.stop()
    return {
        "client_id":     cid,
        "client_secret": csecret,
        "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
        "token_uri":     "https://oauth2.googleapis.com/token",
    }


def _build_auth_url() -> str:
    from urllib.parse import urlencode
    c = _google_creds_config()
    p = {
        "client_id":     c["client_id"],
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         " ".join(SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
    }
    return c["auth_uri"] + "?" + urlencode(p)


def _exchange_code(code: str) -> Credentials:
    c    = _google_creds_config()
    resp = _requests.post(
        c["token_uri"],
        data={
            "code":          code,
            "client_id":     c["client_id"],
            "client_secret": c["client_secret"],
            "redirect_uri":  REDIRECT_URI,
            "grant_type":    "authorization_code",
        },
        timeout=15,
    )
    body = resp.json()
    if not resp.ok or "error" in body:
        raise RuntimeError(
            f"{body.get('error', resp.status_code)}: "
            f"{body.get('error_description', resp.text)}"
        )
    expiry = datetime.utcnow() + timedelta(seconds=int(body.get("expires_in", 3600)))
    return Credentials(
        token=body["access_token"],
        refresh_token=body.get("refresh_token"),
        token_uri=c["token_uri"],
        client_id=c["client_id"],
        client_secret=c["client_secret"],
        scopes=body.get("scope", " ".join(SCOPES)).split(),
        expiry=expiry,
    )


def _save_creds(creds: Credentials):
    st.session_state["_gcreds"] = {
        "token":         creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri":     creds.token_uri,
        "client_id":     creds.client_id,
        "client_secret": creds.client_secret,
        "scopes":        list(creds.scopes) if creds.scopes else SCOPES,
        "expiry":        creds.expiry.isoformat() if creds.expiry else None,
    }


def _load_creds() -> Optional[Credentials]:
    d = st.session_state.get("_gcreds")
    if not d:
        return None
    expiry = datetime.fromisoformat(d["expiry"]) if d.get("expiry") else None
    return Credentials(
        token=d["token"],
        refresh_token=d["refresh_token"],
        token_uri=d["token_uri"],
        client_id=d["client_id"],
        client_secret=d["client_secret"],
        scopes=d["scopes"],
        expiry=expiry,
    )


def handle_google_auth() -> Optional[Credentials]:
    if "_gcreds" in st.session_state:
        creds = _load_creds()
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _save_creds(creds)
                return creds
            except Exception:
                st.session_state.pop("_gcreds", None)

    params = dict(st.query_params)
    if "error" in params:
        st.error(f"Google sign-in error: {params['error']}")
        st.query_params.clear()
        return None

    if "code" in params:
        code = params["code"]
        st.query_params.clear()
        try:
            with st.spinner("Completing sign-in…"):
                creds = _exchange_code(code)
            _save_creds(creds)
            st.rerun()
        except Exception as e:
            st.error(f"Sign-in failed: {e}")
        return None

    # ── Login page ────────────────────────────────────────────────────────
    auth_url = _build_auth_url()
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] {
        background: radial-gradient(ellipse at 70% 20%, #0d2a4a 0%, #060c18 55%, #04080f 100%) !important;
    }
    .login-wrap {
        display: flex; flex-direction: column; align-items: center;
        justify-content: center; min-height: 80vh; text-align: center;
    }
    .login-icon {
        font-size: 4rem; margin-bottom: 24px;
        filter: drop-shadow(0 0 24px rgba(56,189,248,0.4));
    }
    .login-title {
        font-family: 'Syne', sans-serif;
        font-size: 3rem; font-weight: 800;
        color: #f0f7ff; letter-spacing: -0.03em;
        margin-bottom: 12px; line-height: 1.05;
    }
    .login-sub {
        font-size: 1.1rem; color: #5a7a9a;
        max-width: 400px; line-height: 1.6; margin-bottom: 40px;
    }
    .login-btn {
        display: inline-flex; align-items: center; gap: 10px;
        background: linear-gradient(135deg, #0f6fbd, #0857a0);
        border: 1px solid rgba(56,189,248,0.35);
        color: #e8f5ff !important; text-decoration: none !important;
        font-family: 'Syne', sans-serif; font-weight: 600;
        font-size: 0.95rem; letter-spacing: 0.02em;
        padding: 14px 32px; border-radius: 14px;
        box-shadow: 0 8px 32px rgba(56,189,248,0.2);
        transition: all 0.25s;
    }
    .login-btn:hover {
        background: linear-gradient(135deg, #1380d4, #0966b8);
        box-shadow: 0 12px 40px rgba(56,189,248,0.35);
        transform: translateY(-2px);
    }
    .login-features {
        display: flex; gap: 32px; margin-top: 56px; flex-wrap: wrap; justify-content: center;
    }
    .feat {
        background: rgba(13,26,45,0.6);
        border: 1px solid rgba(99,179,237,0.1);
        border-radius: 14px; padding: 20px 24px;
        text-align: left; max-width: 180px;
    }
    .feat-icon { font-size: 1.5rem; margin-bottom: 8px; }
    .feat-label { font-size: 0.8rem; color: #5a7a9a; line-height: 1.4; }
    </style>
    <div class="login-wrap">
      <div class="login-icon">📬</div>
      <div class="login-title">Ambient Email<br>Assistant</div>
      <div class="login-sub">
        AI-powered email analysis, smart conflict detection,
        and intelligent scheduling — all in one place.
      </div>
      <a class="login-btn" href="{url}" target="_self">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
          <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
          <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
          <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
        </svg>
        Sign in with Google
      </a>
      <div class="login-features">
        <div class="feat">
          <div class="feat-icon">📧</div>
          <div class="feat-label">Smart email analysis &amp; prioritisation</div>
        </div>
        <div class="feat">
          <div class="feat-icon">⚡</div>
          <div class="feat-label">Conflict detection &amp; resolution drafts</div>
        </div>
        <div class="feat">
          <div class="feat-icon">🗓️</div>
          <div class="feat-label">Free slot finder &amp; scheduler</div>
        </div>
        <div class="feat">
          <div class="feat-icon">🤖</div>
          <div class="feat-label">Ambient AI agent running in background</div>
        </div>
      </div>
    </div>
    """.replace("{url}", auth_url), unsafe_allow_html=True)
    return None


# ---------------------------------------------------------------------------
# DATA MODELS
# ---------------------------------------------------------------------------

@dataclass
class EmailData:
    id: str
    thread_id: str
    subject: str
    sender: str
    recipient: str
    timestamp: datetime
    body: str
    snippet: str
    is_unread: bool = False
    is_important: bool = False
    has_attachment: bool = False
    has_calendar_event: bool = False
    sender_email: str = ""
    labels: List[str] = field(default_factory=list)
    category: Optional[str] = None
    priority_score: Optional[int] = None
    sentiment: Optional[str] = None
    extracted_dates: List[str] = field(default_factory=list)
    action_items: List[str] = field(default_factory=list)

    def __str__(self):
        return f"Email(subject='{self.subject}')"


@dataclass
class CalendarEvent:
    id: str
    summary: str
    start_time: datetime
    end_time: datetime
    description: Optional[str] = None
    location: Optional[str] = None
    attendees: List[str] = field(default_factory=list)
    organizer: Optional[str] = None
    status: str = "confirmed"
    start: datetime = field(init=False, repr=False)
    end: datetime = field(init=False, repr=False)
    title: str = field(init=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "start", self.start_time)
        object.__setattr__(self, "end",   self.end_time)
        object.__setattr__(self, "title", self.summary)

    @property
    def duration_minutes(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() / 60)


@dataclass
class ConflictInfo:
    event1: CalendarEvent
    event2: CalendarEvent
    overlap_start: datetime
    overlap_end: datetime

    def __getitem__(self, key):
        return getattr(self, key)

    @property
    def overlap_minutes(self) -> int:
        return int((self.overlap_end - self.overlap_start).total_seconds() / 60)

    def __str__(self):
        return f"'{self.event1.summary}' vs '{self.event2.summary}'"


# ---------------------------------------------------------------------------
# GMAIL SERVICE
# ---------------------------------------------------------------------------

class GmailService:
    def __init__(self):
        self.service = None

    def inject_credentials(self, creds: Credentials) -> bool:
        try:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            self.service = build("gmail", "v1", credentials=creds)
            return True
        except Exception as e:
            print(f"GmailService: {e}")
            return False

    def get_emails(self, query: str = "", max_results: int = 50) -> List[EmailData]:
        if not self.service:
            return []
        try:
            results  = self.service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()
            return [e for e in (self._parse(m["id"]) for m in results.get("messages", [])) if e]
        except HttpError as e:
            print(f"Gmail error: {e}")
            return []

    def _parse(self, msg_id: str) -> Optional[EmailData]:
        try:
            msg     = self.service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()
            headers = msg["payload"]["headers"]

            def hdr(n):
                return next((h["value"] for h in headers if h["name"].lower() == n), "")

            subject  = hdr("subject") or "No Subject"
            sender   = hdr("from")    or "Unknown"
            recipient= hdr("to")      or "Unknown"
            labels   = msg.get("labelIds", [])

            return EmailData(
                id=msg_id, thread_id=msg["threadId"],
                subject=subject, sender=sender, recipient=recipient,
                timestamp=self._parse_date(hdr("date")),
                body=self._get_body(msg),
                snippet=msg.get("snippet", ""),
                is_unread    ="UNREAD"    in labels,
                is_important ="IMPORTANT" in labels or "STARRED" in labels,
                has_attachment=self._has_attachments(msg),
                has_calendar_event=self._has_calendar(self._get_body(msg), subject),
                sender_email=self._extract_email(sender),
                labels=labels,
            )
        except Exception as e:
            print(f"Parse error {msg_id}: {e}")
            return None

    def _extract_email(self, s: str) -> str:
        m = re.search(r"<([^>]+)>", s)
        if m: return m.group(1)
        m = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", s)
        return m.group(0) if m else s

    def _has_calendar(self, body: str, subject: str) -> bool:
        kws = ["meeting","calendar","event","invited","invitation","scheduled",
               "appointment","conference","zoom","teams","when:","where:","rsvp"]
        b, s = body.lower(), subject.lower()
        return any(k in b or k in s for k in kws)

    def _get_body(self, message: dict) -> str:
        try:
            parts = message["payload"].get("parts", [])
            if not parts:
                data = message["payload"].get("body", {}).get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            for part in parts:
                if part["mimeType"] == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            for part in parts:
                if part["mimeType"] == "text/html":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                        return re.sub("<[^<]+?>", "", html)
            return message.get("snippet", "")
        except Exception:
            return message.get("snippet", "")

    def _has_attachments(self, message: dict) -> bool:
        return any(p.get("filename") for p in message["payload"].get("parts", []))

    def _parse_date(self, date_str: str) -> datetime:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except Exception:
            return datetime.now()

    def send_email(self, to, subject, body, thread_id=None) -> bool:
        if not self.service: return False
        try:
            msg = MIMEText(body)
            msg["to"] = to; msg["subject"] = subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            payload = {"raw": raw}
            if thread_id: payload["threadId"] = thread_id
            self.service.users().messages().send(userId="me", body=payload).execute()
            return True
        except HttpError as e:
            print(f"Send error: {e}"); return False

    def create_draft(self, to, subject, body) -> bool:
        if not self.service: return False
        try:
            msg = MIMEText(body)
            msg["to"] = to; msg["subject"] = subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            self.service.users().drafts().create(
                userId="me", body={"message": {"raw": raw}}
            ).execute()
            return True
        except HttpError as e:
            print(f"Draft error: {e}"); return False


# ---------------------------------------------------------------------------
# CALENDAR SERVICE
# ---------------------------------------------------------------------------

class CalendarService:
    def __init__(self):
        self.service = None

    def inject_credentials(self, creds: Credentials) -> bool:
        try:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            self.service = build("calendar", "v3", credentials=creds)
            return True
        except Exception as e:
            print(f"CalendarService: {e}"); return False

    def get_events(self, days_ahead: int = 30) -> List[CalendarEvent]:
        if not self.service: return []
        try:
            now = datetime.utcnow()
            res = self.service.events().list(
                calendarId="primary",
                timeMin=now.isoformat() + "Z",
                timeMax=(now + timedelta(days=days_ahead)).isoformat() + "Z",
                maxResults=100, singleEvents=True, orderBy="startTime",
            ).execute()
            return [e for e in (self._parse_event(ev) for ev in res.get("items", [])) if e]
        except HttpError as e:
            print(f"Calendar error: {e}"); return []

    def _parse_event(self, event: dict) -> Optional[CalendarEvent]:
        try:
            start = event["start"].get("dateTime", event["start"].get("date"))
            end   = event["end"].get("dateTime",   event["end"].get("date"))
            return CalendarEvent(
                id=event["id"], summary=event.get("summary", "No Title"),
                start_time=datetime.fromisoformat(start.replace("Z", "+00:00")),
                end_time  =datetime.fromisoformat(end.replace("Z",   "+00:00")),
                description=event.get("description"),
                location   =event.get("location"),
                attendees  =[a.get("email", "") for a in event.get("attendees", [])],
                organizer  =event.get("organizer", {}).get("email"),
                status     =event.get("status", "confirmed"),
            )
        except Exception as e:
            print(f"Event parse error: {e}"); return None

    def find_conflicts(self, events: List[CalendarEvent]) -> List[ConflictInfo]:
        conflicts = []
        for i, e1 in enumerate(events):
            for e2 in events[i + 1:]:
                if e1.start_time < e2.end_time and e2.start_time < e1.end_time:
                    conflicts.append(ConflictInfo(
                        event1=e1, event2=e2,
                        overlap_start=max(e1.start_time, e2.start_time),
                        overlap_end  =min(e1.end_time,   e2.end_time),
                    ))
        return conflicts

    def find_free_slots(self, events: List[CalendarEvent],
                        duration_minutes: int = 60,
                        days_ahead: int = 7) -> List[Dict[str, Any]]:
        free_slots = []
        try:
            now, search_end = datetime.now(), datetime.now() + timedelta(days=days_ahead)
            future = []
            for ev in (events or []):
                s = ev.start_time.replace(tzinfo=None) if ev.start_time.tzinfo else ev.start_time
                e = ev.end_time.replace(tzinfo=None)   if ev.end_time.tzinfo   else ev.end_time
                if e > now and s < search_end:
                    future.append((s, e))

            if now.hour >= 20:
                cur = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
            elif now.hour < 8:
                cur = now.replace(hour=8, minute=0, second=0, microsecond=0)
            else:
                mins = (now.minute // 30 + 1) * 30
                cur  = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0) if mins >= 60 \
                       else now.replace(minute=mins, second=0, microsecond=0)

            iters = 0
            while cur < search_end and iters < 1000:
                iters += 1
                slot_end = cur + timedelta(minutes=duration_minutes)
                if cur.hour < 8:
                    cur = cur.replace(hour=8, minute=0, second=0, microsecond=0); continue
                if cur.hour >= 20:
                    cur = (cur + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0); continue
                if all(not (cur < e and slot_end > s) for s, e in future) and cur > now:
                    free_slots.append({"start": cur, "end": slot_end, "duration_minutes": duration_minutes})
                if len(free_slots) >= 20: break
                cur += timedelta(minutes=30)
        except Exception as e:
            print(f"Free slots error: {e}")
        return free_slots


# ---------------------------------------------------------------------------
# AI ANALYZER
# ---------------------------------------------------------------------------

class AIAnalyzer:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.llm = None
        if LANGCHAIN_AVAILABLE and self.api_key:
            try:
                self.llm = ChatOpenAI(
                    model=os.getenv("LLM_MODEL", "gpt-4"),
                    temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
                    api_key=self.api_key,
                )
            except Exception as e:
                print(f"LLM init error: {e}")

    def analyze_email(self, email: EmailData) -> EmailData:
        if not self.llm:
            return self._rule_based(email)
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", "Analyse the email. Respond ONLY:\nCategory: <work|personal|urgent|spam|newsletter>\nPriority: <0-10>\nSentiment: <positive|neutral|negative>\nDates: <csv or none>\nActions: <csv or none>"),
                ("human", "Subject: {subject}\nFrom: {sender}\nBody: {body}"),
            ])
            resp = (prompt | self.llm).invoke({
                "subject": email.subject, "sender": email.sender, "body": email.body[:1000]
            })
            for line in resp.content.strip().split("\n"):
                if line.startswith("Category:"): email.category = line.split(":", 1)[1].strip().lower()
                elif line.startswith("Priority:"):
                    try: email.priority_score = int(line.split(":", 1)[1].strip())
                    except: email.priority_score = 5
                elif line.startswith("Sentiment:"): email.sentiment = line.split(":", 1)[1].strip().lower()
                elif line.startswith("Dates:"):
                    v = line.split(":", 1)[1].strip()
                    if v.lower() != "none": email.extracted_dates = [x.strip() for x in v.split(",")]
                elif line.startswith("Actions:"):
                    v = line.split(":", 1)[1].strip()
                    if v.lower() != "none": email.action_items = [x.strip() for x in v.split(",")]
            return email
        except Exception as e:
            print(f"AI error: {e}"); return self._rule_based(email)

    def _rule_based(self, email: EmailData) -> EmailData:
        b, s = email.body.lower(), email.subject.lower()
        if any(w in b or w in s for w in ["meeting","project","deadline","task"]): email.category = "work"
        elif any(w in b or w in s for w in ["urgent","asap","critical"]): email.category = "urgent"
        elif any(w in b or w in s for w in ["unsubscribe","newsletter","promotion"]): email.category = "newsletter"
        else: email.category = "personal"
        email.priority_score = 9 if (email.is_important or email.category == "urgent") \
                               else 7 if email.category == "work" \
                               else 3 if email.category == "newsletter" else 5
        pos = sum(1 for w in ["thank","great","excellent","congratulations"] if w in b)
        neg = sum(1 for w in ["sorry","problem","issue","error","cancel"] if w in b)
        email.sentiment = "positive" if pos > neg else ("negative" if neg > pos else "neutral")
        return email

    def generate_conflict_email(self, conflict: ConflictInfo,
                                 alts: List[Tuple[datetime, datetime]]) -> str:
        if not self.llm:
            return self._template_email(conflict, alts)
        try:
            alt_text = "\n".join(
                f"- {s.strftime('%B %d, %Y at %I:%M %p')} - {e.strftime('%I:%M %p')}"
                for s, e in alts[:3]
            )
            prompt = ChatPromptTemplate.from_messages([
                ("system", "Write a polite professional email to resolve a calendar conflict. Include conflict details and suggest alternatives."),
                ("human", "Meeting 1: {e1} ({t1})\nMeeting 2: {e2} ({t2})\nOverlap: {ov} min\nAlternatives:\n{alt}"),
            ])
            resp = (prompt | self.llm).invoke({
                "e1": conflict.event1.summary, "t1": conflict.event1.start_time.strftime("%B %d at %I:%M %p"),
                "e2": conflict.event2.summary, "t2": conflict.event2.start_time.strftime("%B %d at %I:%M %p"),
                "ov": conflict.overlap_minutes, "alt": alt_text,
            })
            return resp.content
        except Exception as e:
            print(f"Email gen error: {e}"); return self._template_email(conflict, alts)

    def _template_email(self, conflict: ConflictInfo, alts: List[Tuple[datetime, datetime]]) -> str:
        body = (
            f"Subject: Calendar Conflict - {conflict.event1.summary} & {conflict.event2.summary}\n\n"
            f"Dear Team,\n\nI wanted to flag a scheduling conflict.\n\n"
            f"• Meeting 1: {conflict.event1.summary}\n"
            f"  {conflict.event1.start_time.strftime('%B %d, %Y at %I:%M %p')} - {conflict.event1.end_time.strftime('%I:%M %p')}\n\n"
            f"• Meeting 2: {conflict.event2.summary}\n"
            f"  {conflict.event2.start_time.strftime('%B %d, %Y at %I:%M %p')} - {conflict.event2.end_time.strftime('%I:%M %p')}\n\n"
            f"Overlap: {conflict.overlap_minutes} minutes\n\nALTERNATIVE TIMES:\n"
        )
        for i, (s, e) in enumerate(alts[:3], 1):
            body += f"{i}. {s.strftime('%B %d, %Y at %I:%M %p')} - {e.strftime('%I:%M %p')}\n"
        body += "\nPlease let me know which time works best.\n\nBest regards\n"
        return body


# ---------------------------------------------------------------------------
# ENHANCED EMAIL ASSISTANT
# ---------------------------------------------------------------------------

class EnhancedEmailAssistant:
    def __init__(self):
        self.gmail    = GmailService()
        self.calendar = CalendarService()
        self.analyzer = AIAnalyzer()
        self.llm      = None
        self.conversation_memory: List = []
        self._load_memory()
        self.emails_cache:    List[EmailData]     = []
        self.events_cache:    List[CalendarEvent] = []
        self.conflicts_cache: List[ConflictInfo]  = []

    def inject_credentials(self, creds: Credentials) -> bool:
        return self.gmail.inject_credentials(creds) and self.calendar.inject_credentials(creds)

    def initialize_llm(self, api_key: Optional[str] = None) -> bool:
        if api_key:
            self.analyzer = AIAnalyzer(api_key=api_key)
            self.llm = self.analyzer.llm
        return self.llm is not None

    def _load_memory(self):
        os.makedirs(MEMORY_DIR, exist_ok=True)
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "rb") as f:
                    self.conversation_memory = pickle.load(f)
            except Exception:
                self.conversation_memory = []

    def fetch_emails(self, query="", max_results=50) -> List[EmailData]:
        self.emails_cache = self.gmail.get_emails(query, max_results)
        return self.emails_cache

    def analyze_emails(self, emails=None) -> List[EmailData]:
        target = emails or self.emails_cache
        analyzed = [self.analyzer.analyze_email(e) for e in target]
        if not emails: self.emails_cache = analyzed
        return analyzed

    def fetch_calendar_events(self, days_ahead=30) -> List[CalendarEvent]:
        self.events_cache = self.calendar.get_events(days_ahead)
        return self.events_cache

    def detect_conflicts(self, events=None) -> List[ConflictInfo]:
        self.conflicts_cache = self.calendar.find_conflicts(events or self.events_cache)
        return self.conflicts_cache

    def find_free_slots(self, *args, **kwargs) -> List[Dict[str, Any]]:
        events           = kwargs.get("events", None)
        duration_minutes = kwargs.get("duration_minutes", 60)
        days_ahead       = kwargs.get("days_ahead", 7)
        if len(args) >= 1:
            f = args[0]
            if isinstance(f, list):
                events = f
                if len(args) >= 2 and isinstance(args[1], int): duration_minutes = args[1]
                if len(args) >= 3 and isinstance(args[2], int): days_ahead       = args[2]
            elif isinstance(f, int):
                duration_minutes = f
                if len(args) >= 2 and isinstance(args[1], int): days_ahead = args[1]
        if not isinstance(duration_minutes, int): duration_minutes = 60
        if not isinstance(days_ahead, int):       days_ahead       = 7
        if events is None:
            self.fetch_calendar_events(days_ahead=days_ahead)
            events = self.events_cache
        return self.calendar.find_free_slots(events, duration_minutes, days_ahead)

    def generate_conflict_resolution(self, conflict: ConflictInfo, free_slots=None) -> str:
        if free_slots is None:
            free_slots = self.find_free_slots(
                duration_minutes=conflict.event1.duration_minutes, days_ahead=14
            )
        alts = [(s["start"], s["end"]) if isinstance(s, dict) else s for s in free_slots[:5]]
        return self.analyzer.generate_conflict_email(conflict, alts)

    def send_email(self, to, subject, body, thread_id=None):
        return self.gmail.send_email(to, subject, body, thread_id)

    def create_draft(self, to, subject, body):
        return self.gmail.create_draft(to, subject, body)

    def run_ambient_agent(self) -> Dict[str, Any]:
        result = {
            "status": "success", "emails_fetched": 0, "emails_analyzed": 0,
            "events_fetched": 0, "conflicts_found": 0, "suggestions": [], "drafts_created": 0,
        }
        try:
            emails    = self.fetch_emails(max_results=50)
            result["emails_fetched"]  = len(emails)
            analyzed  = self.analyze_emails(emails)
            result["emails_analyzed"] = len(analyzed)
            events    = self.fetch_calendar_events(days_ahead=30)
            result["events_fetched"]  = len(events)
            conflicts = self.detect_conflicts(events)
            result["conflicts_found"] = len(conflicts)

            s = []
            urgent = [e for e in analyzed if e.priority_score and e.priority_score >= 8]
            if urgent: s.append(f"🔴 {len(urgent)} high-priority emails need your attention")
            unread_imp = [e for e in analyzed if e.is_unread and e.is_important]
            if unread_imp: s.append(f"📬 {len(unread_imp)} unread important emails waiting")
            if conflicts: s.append(f"⚡ {len(conflicts)} calendar conflicts detected")
            today_ev = [e for e in events if e.start_time.date() == datetime.now().date()]
            if today_ev: s.append(f"📅 {len(today_ev)} events scheduled for today")
            result["suggestions"] = s

            for c in conflicts[:3]:
                self.generate_conflict_resolution(c)
                result["drafts_created"] += 1
        except Exception as e:
            result["status"] = "error"; result["error"] = str(e)
        return result


# ---------------------------------------------------------------------------
# STREAMLIT APP
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="Ambient Email Assistant",
        page_icon="📬",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_css()

    creds = handle_google_auth()
    if creds is None:
        st.stop()

    # ── Sidebar ───────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("""
        <div style='display:flex;align-items:center;gap:10px;margin-bottom:24px'>
          <span style='font-size:1.6rem'>📬</span>
          <span style='font-family:Syne,sans-serif;font-weight:700;font-size:1rem;color:#e2edf8'>
            InboxAI
          </span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div style="height:1px;background:rgba(99,179,237,0.1);margin-bottom:20px"></div>',
                    unsafe_allow_html=True)

        st.markdown('<p style="font-size:0.7rem;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:#2a4a6a;margin-bottom:8px">Status</p>',
                    unsafe_allow_html=True)
        st.success("✓ Connected to Google")

        st.markdown('<div style="height:1px;background:rgba(99,179,237,0.08);margin:20px 0"></div>',
                    unsafe_allow_html=True)

        st.markdown('<p style="font-size:0.7rem;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:#2a4a6a;margin-bottom:8px">AI Features</p>',
                    unsafe_allow_html=True)
        openai_key = st.text_input(
            "OpenAI API Key",
            type="password",
            placeholder="sk-…",
            help="Optional. Enables AI categorisation & smart drafts.",
            label_visibility="collapsed",
        )
        if openai_key:
            st.markdown('<p style="font-size:0.75rem;color:#34d399;margin-top:4px">✓ AI mode enabled</p>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<p style="font-size:0.75rem;color:#4a6a8a;margin-top:4px">Rule-based mode (no key)</p>',
                        unsafe_allow_html=True)

        st.markdown('<div style="height:1px;background:rgba(99,179,237,0.08);margin:20px 0"></div>',
                    unsafe_allow_html=True)

        if st.button("Sign out", use_container_width=True):
            st.session_state.pop("_gcreds", None)
            st.session_state.pop("assistant", None)
            st.query_params.clear()
            st.rerun()

    # ── Build assistant ───────────────────────────────────────────────────
    if "assistant" not in st.session_state:
        st.session_state["assistant"] = EnhancedEmailAssistant()

    assistant: EnhancedEmailAssistant = st.session_state["assistant"]
    assistant.inject_credentials(creds)
    if openai_key:
        assistant.initialize_llm(api_key=openai_key)

    # ── Hero ──────────────────────────────────────────────────────────────
    render_hero()

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab_emails, tab_calendar, tab_agent = st.tabs([
        "📧  Emails", "📅  Calendar & Conflicts", "🤖  Ambient Agent"
    ])

    # ════════════════════════════════════════════════════════════════════════
    # EMAILS TAB
    # ════════════════════════════════════════════════════════════════════════
    with tab_emails:
        st.markdown('<div class="section-heading">Fetch & Analyse Emails</div>', unsafe_allow_html=True)

        col_q, col_n, col_btn = st.columns([4, 1, 1])
        with col_q:
            query = st.text_input(
                "Search", placeholder="is:unread  ·  label:important  ·  from:boss@company.com",
                label_visibility="collapsed"
            )
        with col_n:
            max_results = st.number_input("Max", 1, 200, 20, label_visibility="collapsed")
        with col_btn:
            fetch_btn = st.button("Fetch Emails", use_container_width=True, type="primary")

        if fetch_btn:
            with st.spinner("Fetching emails…"):
                emails = assistant.fetch_emails(query=query, max_results=int(max_results))
            st.success(f"Fetched {len(emails)} emails")

        if assistant.emails_cache:
            col_a, col_spacer = st.columns([2, 5])
            with col_a:
                analyse_btn = st.button("Analyse All with AI", use_container_width=True)
            if analyse_btn:
                with st.spinner("Analysing…"):
                    assistant.analyze_emails()
                st.success("Analysis complete")

            # ── Stats row ──────────────────────────────────────────────
            cache = assistant.emails_cache
            n_unread   = sum(1 for e in cache if e.is_unread)
            n_important= sum(1 for e in cache if e.is_important)
            n_analysed = sum(1 for e in cache if e.category)
            n_urgent   = sum(1 for e in cache if e.priority_score and e.priority_score >= 8)

            st.markdown(f"""
            <div class="stat-row">
              <div class="stat-card">
                <div class="stat-card-accent accent-blue"></div>
                <div class="stat-label">Total</div>
                <div class="stat-value">{len(cache)}</div>
              </div>
              <div class="stat-card">
                <div class="stat-card-accent accent-amber"></div>
                <div class="stat-label">Unread</div>
                <div class="stat-value">{n_unread}</div>
              </div>
              <div class="stat-card">
                <div class="stat-card-accent accent-rose"></div>
                <div class="stat-label">Urgent</div>
                <div class="stat-value">{n_urgent}</div>
              </div>
              <div class="stat-card">
                <div class="stat-card-accent accent-green"></div>
                <div class="stat-label">Analysed</div>
                <div class="stat-value">{n_analysed}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # ── Email list ──────────────────────────────────────────────
            st.markdown('<div class="section-heading" style="font-size:1rem;margin-top:8px">Inbox</div>',
                        unsafe_allow_html=True)

            for email in cache[:50]:
                unread_cls = "email-row-unread" if email.is_unread else ""
                attach_ico = " 📎" if email.has_attachment else ""
                cal_ico    = " 📅" if email.has_calendar_event else ""

                with st.expander(
                    f"{'🔵' if email.is_unread else '○'}  {email.subject}{attach_ico}{cal_ico}",
                    expanded=False
                ):
                    top_l, top_r = st.columns([3, 1])
                    with top_l:
                        st.markdown(f"""
                        <div style='margin-bottom:4px'>
                          <span style='font-size:0.82rem;color:#4a6a8a'>From</span>
                          <span style='font-size:0.88rem;color:#a0c0e0;margin-left:8px'>{email.sender}</span>
                        </div>
                        <div>
                          <span style='font-size:0.82rem;color:#4a6a8a'>Date</span>
                          <span style='font-size:0.85rem;color:#7a9ab8;margin-left:8px'>
                            {email.timestamp.strftime('%b %d, %Y · %I:%M %p')}
                          </span>
                        </div>
                        """, unsafe_allow_html=True)
                    with top_r:
                        if email.category:
                            st.markdown(pill_html(email.category), unsafe_allow_html=True)
                        if email.priority_score is not None:
                            color = "#f87171" if email.priority_score >= 8 else \
                                    "#fbbf24" if email.priority_score >= 5 else "#4a6a8a"
                            st.markdown(
                                f'<div style="font-size:0.78rem;color:{color};margin-top:4px">Priority {email.priority_score}/10</div>',
                                unsafe_allow_html=True
                            )

                    st.markdown('<div style="height:1px;background:rgba(99,179,237,0.08);margin:12px 0"></div>',
                                unsafe_allow_html=True)
                    st.text_area("Body", email.body[:600], height=110, key=f"b_{email.id}",
                                 label_visibility="collapsed")

                    if email.action_items:
                        items_html = "  ·  ".join(email.action_items)
                        st.markdown(
                            f'<div style="font-size:0.8rem;color:#38bdf8;margin-top:8px">⚡ {items_html}</div>',
                            unsafe_allow_html=True
                        )
                    if email.sentiment:
                        icon = {"positive": "😊", "negative": "😟", "neutral": "😐"}.get(email.sentiment, "")
                        st.markdown(
                            f'<div style="font-size:0.78rem;color:#4a6a8a;margin-top:4px">{icon} {email.sentiment.capitalize()} sentiment</div>',
                            unsafe_allow_html=True
                        )

    # ════════════════════════════════════════════════════════════════════════
    # CALENDAR TAB
    # ════════════════════════════════════════════════════════════════════════
    with tab_calendar:
        st.markdown('<div class="section-heading">Calendar & Conflicts</div>', unsafe_allow_html=True)

        col_d, col_btn2 = st.columns([3, 1])
        with col_d:
            days = st.slider("Days ahead", 1, 90, 30, label_visibility="collapsed")
        with col_btn2:
            cal_btn = st.button("Fetch Calendar", use_container_width=True, type="primary")

        if cal_btn:
            with st.spinner("Fetching events…"):
                events    = assistant.fetch_calendar_events(days_ahead=days)
                conflicts = assistant.detect_conflicts()
            st.success(f"Fetched {len(events)} events · {len(conflicts)} conflict(s) detected")

        # ── Stats ──────────────────────────────────────────────────────
        if assistant.events_cache or assistant.conflicts_cache:
            today_count = sum(1 for e in assistant.events_cache
                              if e.start_time.date() == datetime.now().date())
            st.markdown(f"""
            <div class="stat-row" style="grid-template-columns:repeat(3,1fr)">
              <div class="stat-card">
                <div class="stat-card-accent accent-blue"></div>
                <div class="stat-label">Total Events</div>
                <div class="stat-value">{len(assistant.events_cache)}</div>
              </div>
              <div class="stat-card">
                <div class="stat-card-accent accent-amber"></div>
                <div class="stat-label">Today</div>
                <div class="stat-value">{today_count}</div>
              </div>
              <div class="stat-card">
                <div class="stat-card-accent accent-rose"></div>
                <div class="stat-label">Conflicts</div>
                <div class="stat-value">{len(assistant.conflicts_cache)}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        # ── Events list ────────────────────────────────────────────────
        if assistant.events_cache:
            st.markdown('<div class="section-heading" style="font-size:1rem">Upcoming Events</div>',
                        unsafe_allow_html=True)
            for ev in assistant.events_cache[:25]:
                loc = f"  ·  📍 {ev.location}" if ev.location else ""
                st.markdown(f"""
                <div class="event-row">
                  <div class="event-time">{ev.start_time.strftime('%b %d · %I:%M %p')}</div>
                  <div class="event-title-text">{ev.summary}{loc}</div>
                </div>
                """, unsafe_allow_html=True)

        # ── Conflicts ──────────────────────────────────────────────────
        if assistant.conflicts_cache:
            st.markdown(
                f'<div class="section-heading" style="font-size:1rem;margin-top:24px">⚠️ Conflicts ({len(assistant.conflicts_cache)})</div>',
                unsafe_allow_html=True
            )
            for i, conflict in enumerate(assistant.conflicts_cache):
                with st.expander(f"⚡ {conflict.event1.summary}  ↔  {conflict.event2.summary}", expanded=i == 0):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"""
                        <div class="glass-card">
                          <div class="card-title">📅 {conflict.event1.summary}</div>
                          <div class="card-meta">
                            {conflict.event1.start_time.strftime('%b %d · %I:%M %p')} –
                            {conflict.event1.end_time.strftime('%I:%M %p')}
                          </div>
                        </div>
                        """, unsafe_allow_html=True)
                    with c2:
                        st.markdown(f"""
                        <div class="glass-card">
                          <div class="card-title">📅 {conflict.event2.summary}</div>
                          <div class="card-meta">
                            {conflict.event2.start_time.strftime('%b %d · %I:%M %p')} –
                            {conflict.event2.end_time.strftime('%I:%M %p')}
                          </div>
                        </div>
                        """, unsafe_allow_html=True)

                    st.markdown(
                        f'<div style="text-align:center;color:#f87171;font-size:0.85rem;margin-bottom:16px">⚡ Overlap: {conflict.overlap_minutes} minutes</div>',
                        unsafe_allow_html=True
                    )

                    btn_a, btn_b = st.columns(2)
                    with btn_a:
                        if st.button("✉️ Generate Resolution Email", key=f"re_{i}", use_container_width=True):
                            with st.spinner("Drafting email…"):
                                body = assistant.generate_conflict_resolution(conflict)
                            st.text_area("Draft Email", body, height=280, key=f"draft_{i}")
                    with btn_b:
                        if st.button("🕐 Find Free Slots", key=f"fs_{i}", use_container_width=True):
                            with st.spinner("Scanning calendar…"):
                                slots = assistant.find_free_slots(
                                    duration_minutes=conflict.event1.duration_minutes,
                                    days_ahead=14,
                                )
                            if slots:
                                st.markdown('<div style="margin-top:8px">', unsafe_allow_html=True)
                                for slot in slots[:6]:
                                    st.markdown(f"""
                                    <div style="background:rgba(56,189,248,0.06);border:1px solid rgba(56,189,248,0.15);
                                    border-radius:8px;padding:8px 14px;margin-bottom:6px;font-size:0.82rem;color:#7ab8d8">
                                      🟢 {slot['start'].strftime('%a %b %d · %I:%M %p')} –
                                          {slot['end'].strftime('%I:%M %p')}
                                    </div>
                                    """, unsafe_allow_html=True)
                                st.markdown('</div>', unsafe_allow_html=True)
                            else:
                                st.info("No free slots found in the next 14 days.")

    # ════════════════════════════════════════════════════════════════════════
    # AGENT TAB
    # ════════════════════════════════════════════════════════════════════════
    with tab_agent:
        st.markdown('<div class="section-heading">Ambient Agent</div>', unsafe_allow_html=True)

        st.markdown("""
        <div class="glass-card" style="margin-bottom:28px">
          <div class="card-title" style="font-size:1.05rem;margin-bottom:10px">🤖 What does the agent do?</div>
          <div style="font-size:0.88rem;color:#5a7a9a;line-height:1.7">
            The ambient agent runs a full scan in one click:<br>
            ① Fetches your last 50 emails and analyses priority, category &amp; sentiment<br>
            ② Pulls upcoming calendar events and detects any scheduling conflicts<br>
            ③ Auto-drafts conflict resolution emails<br>
            ④ Surfaces personalised action suggestions
          </div>
        </div>
        """, unsafe_allow_html=True)

        run_btn = st.button("▶  Run Agent Now", type="primary", use_container_width=False)

        if run_btn:
            with st.spinner("Agent running — fetching, analysing, detecting conflicts…"):
                result = assistant.run_ambient_agent()

            if result["status"] == "success":
                st.markdown(f"""
                <div class="stat-row">
                  <div class="stat-card">
                    <div class="stat-card-accent accent-blue"></div>
                    <div class="stat-label">Emails Fetched</div>
                    <div class="stat-value">{result['emails_fetched']}</div>
                  </div>
                  <div class="stat-card">
                    <div class="stat-card-accent accent-green"></div>
                    <div class="stat-label">Analysed</div>
                    <div class="stat-value">{result['emails_analyzed']}</div>
                  </div>
                  <div class="stat-card">
                    <div class="stat-card-accent accent-amber"></div>
                    <div class="stat-label">Events</div>
                    <div class="stat-value">{result['events_fetched']}</div>
                  </div>
                  <div class="stat-card">
                    <div class="stat-card-accent accent-rose"></div>
                    <div class="stat-label">Conflicts</div>
                    <div class="stat-value">{result['conflicts_found']}</div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

                if result["suggestions"]:
                    st.markdown('<div class="section-heading" style="font-size:1rem;margin-top:8px">💡 Suggestions</div>',
                                unsafe_allow_html=True)
                    for s in result["suggestions"]:
                        st.markdown(f'<div class="suggestion-banner">{s}</div>',
                                    unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div class="suggestion-banner">
                      ✅ Everything looks clear — no urgent items or conflicts detected.
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.error(f"Agent error: {result.get('error')}")


if __name__ == "__main__":
    main()
