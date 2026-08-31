"""
Ambient Email Assistant — Clean Attractive UI
OAuth: direct requests.post (no oauthlib/PKCE).
Features: real free-slot detection from live calendar + send email after draft.
"""

import os
import json
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

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]
APP_URL      = os.getenv("APP_URL", "http://localhost:8501")
REDIRECT_URI = os.getenv("REDIRECT_URI", APP_URL)
MEMORY_DIR   = "memory"
MEMORY_FILE  = os.path.join(MEMORY_DIR, "conversation_memory.pkl")

# ─────────────────────────────────────────────────────────────────────────────
# THEME
# ─────────────────────────────────────────────────────────────────────────────
THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=Inter:wght@300;400;500;600;700&display=swap');

/* Global Reset & Background */
*, *::before, *::after {
    box-sizing: border-box;
    font-family: "DM Sans", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
}

:root {
    --color-background: #f0f0f0;
    --color-card: #ffffff;
    --color-text: #222222;
    --color-muted: #666666;
    --color-border: #e0e0e0;
    --color-primary: #007bff;
    --color-primary-hover: #0056b3;
    --color-divider: #e5e7eb;
}

html, body, .stApp, [data-testid="stApp"], [data-testid="stAppViewContainer"], [data-testid="stMain"], .main {
    background-color: #f0f0f0 !important;
    color: #222222 !important;
}

[data-testid="stHeader"] {
    background: transparent !important;
}
#MainMenu, footer, [data-testid="stToolbar"] {
    display: none !important;
}

/* Sidebar */
[data-testid="stSidebar"], section[data-testid="stSidebar"], [data-testid="stSidebarContent"], [data-testid="stSidebarUserContent"] {
    background-color: #ffffff !important;
    border-right: 1px solid #e0e0e0 !important;
}
[data-testid="stSidebar"] {
    min-width: 280px !important;
    max-width: 320px !important;
}
[data-testid="stSidebarContent"] {
    padding: 1.5rem 1.25rem !important;
}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] span, [data-testid="stSidebar"] div {
    color: #444444 !important;
}

/* Main Container width & padding to fit screen */
.block-container {
    padding-top: 1.75rem !important;
    padding-bottom: 3rem !important;
    padding-left: 2.5rem !important;
    padding-right: 2.5rem !important;
    max-width: 100% !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    background: #ffffff !important;
    border: 1px solid #e0e0e0 !important;
    border-radius: 8px !important;
    padding: 4px !important;
    gap: 4px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.03) !important;
    margin-bottom: 1.5rem !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: #555555 !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    padding: 8px 20px !important;
    border-radius: 6px !important;
    border: none !important;
    transition: all 0.15s ease !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #007bff !important;
    background: #f8f9fa !important;
}
.stTabs [aria-selected="true"] {
    color: #ffffff !important;
    background: #007bff !important;
    font-weight: 600 !important;
    border-bottom: none !important;
    box-shadow: 0 2px 4px rgba(0,123,255,0.2) !important;
}
.stTabs [data-baseweb="tab-border"] {
    display: none !important;
}
.stTabs [data-baseweb="tab-panel"] {
    padding-top: 0 !important;
}

/* Buttons */
.stButton>button {
    background-color: #ffffff !important;
    border: 1px solid #d0d5dd !important;
    color: #344054 !important;
    border-radius: 6px !important;
    font-size: 0.88rem !important;
    font-weight: 600 !important;
    padding: 0.55rem 1.1rem !important;
    box-shadow: 0 1px 2px rgba(16,24,40,0.05) !important;
    transition: all 0.15s ease !important;
    min-height: 42px !important;
}
.stButton>button:hover {
    background-color: #f9fafb !important;
    border-color: #98a2b3 !important;
    color: #1d2939 !important;
    box-shadow: 0 2px 4px rgba(16,24,40,0.08) !important;
}
.stButton>button[kind="primary"] {
    background: #007bff !important;
    border: 1px solid #007bff !important;
    color: #ffffff !important;
    box-shadow: 0 2px 4px rgba(0,123,255,0.25) !important;
}
.stButton>button[kind="primary"]:hover {
    background: #0056b3 !important;
    border-color: #0056b3 !important;
    box-shadow: 0 3px 8px rgba(0,123,255,0.3) !important;
}

/* Inputs & Number Inputs & Textareas */
.stTextInput>div>div>input, .stTextArea>div>div>textarea, .stNumberInput>div>div>input {
    background-color: #ffffff !important;
    border: 1px solid #d0d5dd !important;
    border-radius: 6px !important;
    color: #101828 !important;
    font-size: 0.88rem !important;
    box-shadow: 0 1px 2px rgba(16,24,40,0.04) !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
    min-height: 42px !important;
}
.stTextInput>div>div>input:focus, .stTextArea>div>div>textarea:focus, .stNumberInput>div>div>input:focus {
    border-color: #007bff !important;
    box-shadow: 0 0 0 3px rgba(0,123,255,0.12) !important;
    outline: none !important;
}
input::placeholder, textarea::placeholder {
    color: #98a2b3 !important;
}

/* Number input buttons */
.stNumberInput [data-testid="stNumberInputStepDown"], .stNumberInput [data-testid="stNumberInputStepUp"] {
    background-color: #ffffff !important;
    border-color: #d0d5dd !important;
    color: #344054 !important;
    min-height: 20px !important;
}

/* Expanders */
[data-testid="stExpander"] {
    background-color: #ffffff !important;
    border: 1px solid #e0e0e0 !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02) !important;
    margin-bottom: 0.6rem !important;
    overflow: hidden !important;
}
[data-testid="stExpander"]:hover {
    border-color: #b0c4de !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.04) !important;
}
[data-testid="stExpander"] summary {
    color: #1f2937 !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    padding: 0.8rem 1.1rem !important;
    background-color: #ffffff !important;
}

/* Metrics */
[data-testid="stMetric"] {
    background-color: #ffffff !important;
    border: 1px solid #e0e0e0 !important;
    border-radius: 8px !important;
    padding: 1rem 1.25rem !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02) !important;
}
[data-testid="stMetricValue"] {
    color: #111827 !important;
    font-weight: 700 !important;
    font-size: 1.6rem !important;
}
[data-testid="stMetricLabel"] {
    color: #6b7280 !important;
    font-size: 0.75rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    font-weight: 600 !important;
}

/* Alerts */
.stSuccess {
    background-color: #ecfdf5 !important;
    border: 1px solid #a7f3d0 !important;
    color: #065f46 !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
}
.stError {
    background-color: #fef2f2 !important;
    border: 1px solid #fecaca !important;
    color: #991b1b !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
}
.stInfo {
    background-color: #eff6ff !important;
    border: 1px solid #bfdbfe !important;
    color: #1e40af !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
}
.stWarning {
    background-color: #fffbeb !important;
    border: 1px solid #fde68a !important;
    color: #92400e !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
}

[data-testid="stSpinner"]>div {
    border-top-color: #007bff !important;
}
</style>
"""

def inject_theme():
    st.markdown(THEME_CSS, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# OAUTH — direct requests.post, no oauthlib, no PKCE
# ─────────────────────────────────────────────────────────────────────────────
def _get_google_credentials() -> Tuple[str, str]:
    cid = ""
    cs  = ""

    # 1. Check credentials.json file in project root
    if os.path.exists("credentials.json"):
        try:
            with open("credentials.json", "r", encoding="utf-8") as f:
                cdata = json.load(f)
            oauth_data = cdata.get("web") or cdata.get("installed") or {}
            cid = oauth_data.get("client_id", "")
            cs  = oauth_data.get("client_secret", "")
        except Exception:
            pass

    # 2. Check Streamlit secrets
    if not cid or not cs:
        try:
            cid = st.secrets["google_credentials"]["client_id"]
            cs  = st.secrets["google_credentials"]["client_secret"]
        except Exception:
            pass

    # 3. Check environment variables
    if not cid or not cs:
        cid = os.getenv("GOOGLE_CLIENT_ID", "")
        cs  = os.getenv("GOOGLE_CLIENT_SECRET", "")

    return cid.strip(), cs.strip()


def _gcfg() -> Optional[dict]:
    cid, cs = _get_google_credentials()
    if not cid or not cs:
        return None
    return {
        "client_id": cid,
        "client_secret": cs,
        "auth_uri":  "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def _get_redirect_uri() -> str:
    try:
        if "REDIRECT_URI" in st.secrets:
            return st.secrets["REDIRECT_URI"]
        if "APP_URL" in st.secrets:
            return st.secrets["APP_URL"]
    except Exception:
        pass
    return os.getenv("REDIRECT_URI") or os.getenv("APP_URL") or "http://localhost:8501"


def _build_auth_url() -> Optional[str]:
    from urllib.parse import urlencode
    c = _gcfg()
    if not c:
        return None
    return c["auth_uri"] + "?" + urlencode({
        "client_id": c["client_id"], "redirect_uri": _get_redirect_uri(),
        "response_type": "code", "scope": " ".join(SCOPES),
        "access_type": "offline", "prompt": "consent",
    })


def _exchange_code(code: str) -> Credentials:
    c = _gcfg()
    if not c:
        raise RuntimeError("Google OAuth credentials are not configured.")
    resp = _requests.post(c["token_uri"], data={
        "code": code, "client_id": c["client_id"],
        "client_secret": c["client_secret"],
        "redirect_uri": _get_redirect_uri(), "grant_type": "authorization_code",
    }, timeout=15)
    body = resp.json()
    if not resp.ok or "error" in body:
        raise RuntimeError(f"{body.get('error')}: {body.get('error_description', resp.text)}")
    expiry = datetime.utcnow() + timedelta(seconds=int(body.get("expires_in", 3600)))
    return Credentials(
        token=body["access_token"], refresh_token=body.get("refresh_token"),
        token_uri=c["token_uri"], client_id=c["client_id"], client_secret=c["client_secret"],
        scopes=body.get("scope", " ".join(SCOPES)).split(), expiry=expiry,
    )


def _render_setup_screen():
    st.markdown("<br>", unsafe_allow_html=True)
    col_l, col_c, col_r = st.columns([1, 2.5, 1])
    with col_c:
        st.markdown(
            "<h1 style='text-align:center;font-family:Space Grotesk,sans-serif;"
            "font-size:2.2rem;font-weight:700;color:#e2edf8;margin-bottom:4px'>📬 InboxAI Setup</h1>"
            "<p style='text-align:center;color:#6b8aaa;font-size:0.95rem;margin-bottom:24px'>"
            "Connect your Google OAuth credentials to enable Gmail and Calendar features</p>",
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div style='background:#0e1a2d;border:1px solid #1e2d42;border-radius:10px;padding:16px 20px;margin-bottom:20px'>
                <div style='font-size:0.95rem;font-weight:600;color:#60a5fa;margin-bottom:6px'>🔑 Google OAuth Required</div>
                <div style='font-size:0.84rem;color:#8ab4d8;line-height:1.5'>
                    To read emails, detect calendar conflicts, and draft smart replies, InboxAI needs Google OAuth credentials.
                    You can either paste your credentials below or drop your <code>credentials.json</code> file.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        tab1, tab2 = st.tabs(["📝 Enter Client ID & Secret", "📁 Upload credentials.json"])

        with tab1:
            with st.form("manual_creds_form"):
                in_cid = st.text_input("Client ID", placeholder="123456789-xxx.apps.googleusercontent.com")
                in_cs = st.text_input("Client Secret", type="password", placeholder="GOCSPX-xxxxxxxxx")
                submitted = st.form_submit_button("💾 Save Credentials", use_container_width=True, type="primary")
                if submitted:
                    if in_cid.strip() and in_cs.strip():
                        os.makedirs(".streamlit", exist_ok=True)
                        secrets_path = os.path.join(".streamlit", "secrets.toml")
                        with open(secrets_path, "w", encoding="utf-8") as sf:
                            sf.write(f'[google_credentials]\nclient_id = "{in_cid.strip()}"\nclient_secret = "{in_cs.strip()}"\n')
                        st.success("Credentials saved to .streamlit/secrets.toml! Reloading...")
                        st.rerun()
                    else:
                        st.error("Please enter both Client ID and Client Secret.")

        with tab2:
            uploaded = st.file_uploader("Upload credentials.json from Google Cloud Console", type=["json"])
            if uploaded is not None:
                try:
                    raw = uploaded.read().decode("utf-8")
                    parsed = json.loads(raw)
                    oauth_data = parsed.get("web") or parsed.get("installed") or {}
                    if oauth_data.get("client_id") and oauth_data.get("client_secret"):
                        with open("credentials.json", "w", encoding="utf-8") as cf:
                            cf.write(raw)
                        st.success("credentials.json saved successfully! Reloading...")
                        st.rerun()
                    else:
                        st.error("The uploaded JSON does not contain client_id and client_secret under 'web' or 'installed'.")
                except Exception as ex:
                    st.error(f"Error parsing JSON: {ex}")

        with st.expander("ℹ️ How to get your Google credentials (Step-by-Step)"):
            st.markdown(
                f"""
                1. Go to the **[Google Cloud Console](https://console.cloud.google.com/)** and create a new project.
                2. In **APIs & Services > Library**, search and **Enable**:
                   - **Gmail API**
                   - **Google Calendar API**
                3. Go to **APIs & Services > OAuth consent screen**:
                   - Select **External**, set App name (e.g. `InboxAI`), and add your email as a **Test user**.
                4. Go to **APIs & Services > Credentials > Create Credentials > OAuth client ID**:
                   - Application type: **Web application**
                   - Authorized redirect URIs: Add `{REDIRECT_URI}`
                5. Click **Create**, then copy the **Client ID** and **Client Secret** (or click **Download JSON**) and save them above.
                """
            )


def _save_creds(creds: Credentials):
    st.session_state["_gcreds"] = {
        "token": creds.token, "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri, "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }
    try:
        with open("token.json", "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    except Exception:
        pass


def _load_creds() -> Optional[Credentials]:
    d = st.session_state.get("_gcreds")
    if d:
        return Credentials(
            token=d["token"], refresh_token=d["refresh_token"],
            token_uri=d["token_uri"], client_id=d["client_id"],
            client_secret=d["client_secret"], scopes=d["scopes"],
            expiry=datetime.fromisoformat(d["expiry"]) if d.get("expiry") else None,
        )
    if os.path.exists("token.json"):
        try:
            return Credentials.from_authorized_user_file("token.json", SCOPES)
        except Exception:
            pass
    return None


def _render_ludiflex_login_screen(auth_url: str):
    login_html = f"""
    <style>
    @import url("https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&display=swap");

    [data-testid="stSidebar"] {{ display: none !important; }}
    [data-testid="stHeader"] {{ display: none !important; }}
    #MainMenu, footer, [data-testid="stToolbar"] {{ display: none !important; }}

    .block-container {{
        padding: 0 !important;
        max-width: 100vw !important;
        margin: 0 !important;
    }}

    :root {{
      --color-background: #f0f0f0;
      --color-text: #333;
      --color-border: #ccc;
      --color-placeholder: #777;
      --color-primary: #007bff;
      --color-primary-hover: #0056b3;
      --color-link: #1a73e8;
      --color-divider: #ddd;
      --color-social-hover: #f0f0f0;
      --color-floating-label: #5f6368;
      --color-white: #fff;
    }}

    html, body, [data-testid="stAppViewContainer"], .main {{
      background-color: var(--color-background) !important;
      color: var(--color-text) !important;
      font-family: "DM Sans", sans-serif !important;
      margin: 0 !important;
      padding: 0 !important;
    }}

    .container {{
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 90vh;
      padding: 20px;
      box-sizing: border-box;
    }}

    .form-container {{
      position: relative;
      background-color: var(--color-white);
      padding: 50px 40px;
      width: 100%;
      max-width: 450px;
      border-radius: 8px;
      border: 1px solid var(--color-border);
      overflow: hidden;
      box-shadow: 0 10px 30px rgba(0,0,0,0.06);
      box-sizing: border-box;
    }}

    .form-header {{
      position: relative;
      z-index: 1;
    }}

    .form-header p {{
      color: var(--color-placeholder);
      font-size: 15px;
      margin: 0 0 4px 0;
    }}

    .form-header h1 {{
      font-size: 32px;
      font-weight: 700;
      color: #222;
      margin: 0;
    }}

    .form-box {{
      display: flex;
      flex-direction: column;
      gap: 20px;
      margin-top: 36px;
      position: relative;
      z-index: 1;
    }}

    .input-group {{
      position: relative;
      display: flex;
      width: 100%;
    }}

    .input-field {{
      height: 48px;
      padding-inline: 14px;
      border: 1px solid var(--color-border);
      border-radius: 6px;
      width: 100%;
      outline: none;
      font-size: 15px;
      background: var(--color-white);
      color: var(--color-text);
      box-sizing: border-box;
      transition: border-color 0.2s ease;
    }}

    #password {{
      padding-right: 42px;
    }}

    .floating-label {{
      position: absolute;
      top: 50%;
      left: 8px;
      transform: translateY(-50%);
      color: var(--color-placeholder);
      background-color: var(--color-white);
      padding-inline: 6px;
      transition: all 0.3s ease;
      pointer-events: none;
      font-size: 14px;
    }}

    .input-field:focus ~ .floating-label,
    .input-field:not(:placeholder-shown) ~ .floating-label {{
      top: 0;
      left: 8px;
      transform: translateY(-50%);
      font-size: 12px;
      color: var(--color-primary);
    }}

    .input-field:focus {{
      border-color: var(--color-primary);
    }}

    .input-field:not(:focus):not(:placeholder-shown) ~ .floating-label {{
      color: var(--color-floating-label);
    }}

    .eye-icon {{
      position: absolute;
      right: 14px;
      display: flex;
      top: 50%;
      transform: translateY(-50%);
      cursor: pointer;
      z-index: 2;
    }}

    .eye-icon svg {{
      width: 20px;
      height: 20px;
      color: var(--color-placeholder);
    }}

    .checkbox-group {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      font-size: 14px;
    }}

    .remember-me {{
      display: flex;
      align-items: center;
      gap: 6px;
      color: var(--color-text);
    }}

    .remember-me input {{
      cursor: pointer;
    }}

    .remember-me label {{
      cursor: pointer;
      user-select: none;
    }}

    .form-btn {{
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 10px;
      height: 48px;
      background: none;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      padding-inline: 8px;
      text-decoration: none;
      box-sizing: border-box;
    }}

    .form-btn--submit {{
      background-color: var(--color-primary);
      color: var(--color-white) !important;
      font-size: 16px;
      font-weight: 600;
      margin-top: 10px;
      transition: background-color 0.3s ease;
      width: 100%;
    }}

    .form-btn--submit:hover {{
      background-color: var(--color-primary-hover);
    }}

    .form-divider {{
      display: flex;
      align-items: center;
      gap: 20px;
      font-size: 14px;
      color: var(--color-placeholder);
      margin-top: 24px;
      position: relative;
      z-index: 1;
    }}

    .form-divider:before,
    .form-divider::after {{
      content: "";
      flex: 1;
      height: 1px;
      background-color: var(--color-divider);
    }}

    .form-socials {{
      width: 100%;
    }}

    .form-btn--google {{
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 12px;
      height: 48px;
      width: 100%;
      border: 1px solid var(--color-border);
      border-radius: 6px;
      background-color: var(--color-white);
      color: #3c4043 !important;
      font-size: 15px;
      font-weight: 600;
      text-decoration: none;
      cursor: pointer;
      transition: background-color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
      box-sizing: border-box;
    }}

    .form-btn--google:hover {{
      background-color: #f8f9fa;
      border-color: #bbb;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
    }}

    .google-icon {{
      width: 20px;
      height: 20px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }}

    .form-link {{
      color: var(--color-link);
      text-decoration: none;
    }}

    .form-link:hover {{
      text-decoration: underline;
    }}

    .form-bottom {{
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      gap: 20px;
      margin-top: 20px;
      position: relative;
      z-index: 1;
      font-size: 14px;
      color: var(--color-placeholder);
    }}

    .form-blob {{
      position: absolute;
      width: 200px;
      height: 200px;
      top: 0;
      right: 0;
      z-index: 0;
      pointer-events: none;
    }}

    .blob-image {{
      position: absolute;
      width: 200px;
      height: 200px;
      rotate: 205deg;
      pointer-events: none;
      opacity: 0;
      transform: scale(0.5) translateX(100px);
    }}

    .blob-image--1 {{
      top: -170px;
      right: -150px;
      animation: welcomeIn 1.2s ease-out 0.3s forwards;
      --final-opacity: 1;
    }}

    .blob-image--2 {{
      top: -165px;
      right: -150px;
      animation: welcomeIn 1.2s ease-out 0.6s forwards;
      --final-opacity: 0.6;
    }}

    .blob-image--3 {{
      top: -160px;
      right: -150px;
      animation: welcomeIn 1.2s ease-out 0.9s forwards;
      --final-opacity: 0.3;
    }}

    @keyframes welcomeIn {{
      0% {{
        opacity: 0;
        transform: scale(0.5) translateX(100px) rotate(180deg);
      }}
      60% {{
        opacity: calc(var(--final-opacity) * 0.8);
        transform: scale(1.1) translateX(-10px) rotate(200deg);
      }}
      100% {{
        opacity: calc(var(--final-opacity));
        transform: scale(1) translateX(0px) rotate(205deg);
      }}
    }}

    @media (max-width: 480px) {{
      .form-container {{
        padding: 40px 24px;
      }}
    }}
    </style>

    <div class="container">
      <div class="form-container">
        <!-- ANIMATED BLOBS -->
        <div class="form-blob">
          <svg class="blob-image blob-image--1" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
            <path fill="#007bff" d="M44.7,-76.4C58.8,-69.2,71.8,-59.1,79.6,-45.8C87.4,-32.6,90,-16.3,88.5,-0.9C86.9,14.6,81.2,29.1,73.1,42.2C64.9,55.3,54.3,66.9,41.2,74.6C28.1,82.3,14,86,-0.7,87.2C-15.5,88.4,-31,87.1,-44.6,80.1C-58.2,73.1,-69.9,60.5,-77.8,46.1C-85.7,31.7,-89.8,15.8,-88.9,0.5C-88.1,-14.8,-82.3,-29.7,-74,-42.6C-65.7,-55.5,-54.9,-66.5,-41.8,-74.3C-28.7,-82.1,-14.4,-86.8,0.5,-87.6C15.3,-88.4,30.6,-83.6,44.7,-76.4Z" transform="translate(100 100)" />
          </svg>
          <svg class="blob-image blob-image--2" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
            <path fill="#007bff" d="M44.7,-76.4C58.8,-69.2,71.8,-59.1,79.6,-45.8C87.4,-32.6,90,-16.3,88.5,-0.9C86.9,14.6,81.2,29.1,73.1,42.2C64.9,55.3,54.3,66.9,41.2,74.6C28.1,82.3,14,86,-0.7,87.2C-15.5,88.4,-31,87.1,-44.6,80.1C-58.2,73.1,-69.9,60.5,-77.8,46.1C-85.7,31.7,-89.8,15.8,-88.9,0.5C-88.1,-14.8,-82.3,-29.7,-74,-42.6C-65.7,-55.5,-54.9,-66.5,-41.8,-74.3C-28.7,-82.1,-14.4,-86.8,0.5,-87.6C15.3,-88.4,30.6,-83.6,44.7,-76.4Z" transform="translate(100 100)" />
          </svg>
          <svg class="blob-image blob-image--3" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
            <path fill="#007bff" d="M44.7,-76.4C58.8,-69.2,71.8,-59.1,79.6,-45.8C87.4,-32.6,90,-16.3,88.5,-0.9C86.9,14.6,81.2,29.1,73.1,42.2C64.9,55.3,54.3,66.9,41.2,74.6C28.1,82.3,14,86,-0.7,87.2C-15.5,88.4,-31,87.1,-44.6,80.1C-58.2,73.1,-69.9,60.5,-77.8,46.1C-85.7,31.7,-89.8,15.8,-88.9,0.5C-88.1,-14.8,-82.3,-29.7,-74,-42.6C-65.7,-55.5,-54.9,-66.5,-41.8,-74.3C-28.7,-82.1,-14.4,-86.8,0.5,-87.6C15.3,-88.4,30.6,-83.6,44.7,-76.4Z" transform="translate(100 100)" />
          </svg>
        </div>

        <!-- HEADER -->
        <div class="form-header">
          <p>Please enter your details</p>
          <h1>Welcome Back</h1>
        </div>

        <!-- FORM BOX -->
        <div class="form-box">
          <!-- EMAIL FIELD -->
          <div class="input-group">
            <input
              type="email"
              id="email"
              class="input-field"
              placeholder=" "
              required
            />
            <label for="email" class="floating-label">Email address</label>
          </div>

          <!-- PASSWORD FIELD -->
          <div class="input-group">
            <input
              type="password"
              id="password"
              class="input-field"
              placeholder=" "
              required
            />
            <label for="password" class="floating-label">Password</label>
            <div class="eye-icon" onclick="togglePassword()">
              <svg
                id="eye-svg"
                xmlns="http://www.w3.org/2000/svg"
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path
                  d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"
                />
                <circle cx="12" cy="12" r="3" />
              </svg>
            </div>
          </div>

          <!-- CHECKBOX ROW -->
          <div class="input-group checkbox-group">
            <div class="form-col remember-me">
              <input
                type="checkbox"
                id="remember-me-checkbox"
                class="checkbox-field"
                checked
              />
              <label for="remember-me-checkbox">Remember me</label>
            </div>
            <div class="form-col">
              <a href="{auth_url}" target="_blank" class="form-link">Forgot password?</a>
            </div>
          </div>

          <!-- SUBMIT BUTTON -->
          <a href="{auth_url}" target="_blank" class="form-btn form-btn--submit">
            Sign In
          </a>
        </div>

        <!-- DIVIDER -->
        <div class="form-divider">
          <p>Or</p>
        </div>

        <!-- SOCIALS -->
        <div class="form-bottom">
          <div class="form-socials">
            <a href="{auth_url}" target="_blank" class="form-btn--google" title="Continue with Google">
              <svg class="google-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20">
                <path fill="#4285F4" d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17Z"/>
                <path fill="#34A853" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.33 24 12 24Z"/>
                <path fill="#FBBC05" d="M5.28 14.27a7.2 7.2 0 0 1 0-4.54V6.58H1.25a11.98 11.98 0 0 0 0 10.84l4.03-3.15Z"/>
                <path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98Z"/>
              </svg>
              <span>Continue with Google</span>
            </a>
          </div>
          <p>
            Don't have an account? <a href="{auth_url}" target="_blank" class="form-link">Sign up</a>
          </p>
        </div>
      </div>
    </div>
    <base target="_blank">
    <script>
      function togglePassword() {{
        const passwordInput = document.getElementById("password");
        const eyeIcon = document.querySelector(".eye-icon");
        if (!passwordInput || !eyeIcon) return;

        if (passwordInput.type === "password") {{
          passwordInput.type = "text";
          eyeIcon.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-eye-off-icon lucide-eye-off"><path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/><path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/><path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/><path d="m2 2 20 20"/></svg>`;
        }} else {{
          passwordInput.type = "password";
          eyeIcon.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-eye-icon lucide-eye"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/></svg>`;
        }}
      }}
    </script>
    """
    import streamlit.components.v1 as components
    st.markdown("""
    <style>
    [data-testid="stSidebar"], [data-testid="stHeader"], #MainMenu, footer, [data-testid="stToolbar"] { display: none !important; }
    .block-container { padding: 0 !important; max-width: 100vw !important; }
    html, body, [data-testid="stAppViewContainer"], .main { background-color: #f0f0f0 !important; }
    iframe { border: none !important; width: 100% !important; }
    </style>
    """, unsafe_allow_html=True)
    components.html(login_html, height=750, scrolling=False)


def handle_google_auth() -> Optional[Credentials]:
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
            if os.path.exists("token.json"):
                try:
                    os.remove("token.json")
                except Exception:
                    pass

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

    auth_url = _build_auth_url()
    if not auth_url:
        _render_setup_screen()
        return None

    _render_ludiflex_login_screen(auth_url)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class EmailData:
    id: str; thread_id: str; subject: str; sender: str; recipient: str
    timestamp: datetime; body: str; snippet: str
    is_unread: bool = False; is_important: bool = False
    has_attachment: bool = False; has_calendar_event: bool = False
    sender_email: str = ""
    labels: List[str] = field(default_factory=list)
    category: Optional[str] = None; priority_score: Optional[int] = None
    sentiment: Optional[str] = None
    extracted_dates: List[str] = field(default_factory=list)
    action_items: List[str] = field(default_factory=list)

@dataclass
class CalendarEvent:
    id: str; summary: str; start_time: datetime; end_time: datetime
    description: Optional[str] = None; location: Optional[str] = None
    attendees: List[str] = field(default_factory=list)
    organizer: Optional[str] = None; status: str = "confirmed"
    start: datetime = field(init=False, repr=False)
    end:   datetime = field(init=False, repr=False)
    title: str      = field(init=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "start", self.start_time)
        object.__setattr__(self, "end",   self.end_time)
        object.__setattr__(self, "title", self.summary)

    @property
    def duration_minutes(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() / 60)

@dataclass
class ConflictInfo:
    event1: CalendarEvent; event2: CalendarEvent
    overlap_start: datetime; overlap_end: datetime

    def __getitem__(self, key): return getattr(self, key)

    @property
    def overlap_minutes(self) -> int:
        return int((self.overlap_end - self.overlap_start).total_seconds() / 60)

    def __str__(self):
        return f"'{self.event1.summary}'  ↔  '{self.event2.summary}'"


# ─────────────────────────────────────────────────────────────────────────────
# GMAIL SERVICE
# ─────────────────────────────────────────────────────────────────────────────
class GmailService:
    def __init__(self): self.service = None

    def inject_credentials(self, creds: Credentials) -> bool:
        try:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            self.service = build("gmail", "v1", credentials=creds)
            return True
        except Exception as e:
            print(f"GmailService: {e}"); return False

    def get_emails(self, query="", max_results=50) -> List[EmailData]:
        if not self.service:
            st.warning("Gmail service is not connected.")
            return []
        try:
            res = self.service.users().messages().list(
                userId="me", q=query, maxResults=max_results).execute()
            msgs = res.get("messages", [])
            if not msgs:
                return []
            return [e for e in (self._parse(m["id"]) for m in msgs) if e]
        except HttpError as e:
            err_msg = str(e)
            st.error(f"Gmail API Error: {e.reason or e}")
            if "has not been used in project" in err_msg or "disabled" in err_msg:
                st.info("💡 **Gmail API is disabled in your Google Cloud project.** Please enable it in Google Cloud Console under **APIs & Services > Library > Gmail API**.")
            print(f"Gmail: {e}"); return []
        except Exception as e:
            st.error(f"Error fetching emails: {e}")
            print(f"Gmail error: {e}"); return []

    def _parse(self, msg_id: str) -> Optional[EmailData]:
        try:
            msg  = self.service.users().messages().get(
                userId="me", id=msg_id, format="full").execute()
            hdrs = msg["payload"]["headers"]
            def h(n): return next((x["value"] for x in hdrs if x["name"].lower()==n), "")
            subject = h("subject") or "No Subject"
            sender  = h("from")   or "Unknown"
            labels  = msg.get("labelIds", [])
            body    = self._body(msg)
            return EmailData(
                id=msg_id, thread_id=msg["threadId"],
                subject=subject, sender=sender,
                recipient=h("to") or "Unknown",
                timestamp=self._date(h("date")),
                body=body, snippet=msg.get("snippet",""),
                is_unread   ="UNREAD"    in labels,
                is_important="IMPORTANT" in labels or "STARRED" in labels,
                has_attachment=any(p.get("filename") for p in msg["payload"].get("parts",[])),
                has_calendar_event=self._is_cal(body, subject),
                sender_email=self._email_addr(sender),
                labels=labels,
            )
        except Exception as e:
            print(f"Parse {msg_id}: {e}"); return None

    def _email_addr(self, s):
        m = re.search(r"<([^>]+)>", s)
        if m: return m.group(1)
        m = re.search(r"\b[\w._%+-]+@[\w.-]+\.[a-zA-Z]{2,}\b", s)
        return m.group(0) if m else s

    def _is_cal(self, body, subject):
        kws = ["meeting","calendar","event","invited","invitation","scheduled",
               "appointment","conference","zoom","teams","when:","where:","rsvp"]
        b,s = body.lower(), subject.lower()
        return any(k in b or k in s for k in kws)

    def _body(self, msg):
        try:
            parts = msg["payload"].get("parts",[])
            if not parts:
                d = msg["payload"].get("body",{}).get("data","")
                return base64.urlsafe_b64decode(d).decode("utf-8","ignore") if d else msg.get("snippet","")
            for p in parts:
                if p["mimeType"]=="text/plain":
                    d = p.get("body",{}).get("data","")
                    if d: return base64.urlsafe_b64decode(d).decode("utf-8","ignore")
            for p in parts:
                if p["mimeType"]=="text/html":
                    d = p.get("body",{}).get("data","")
                    if d: return re.sub("<[^<]+?>","",
                                        base64.urlsafe_b64decode(d).decode("utf-8","ignore"))
            return msg.get("snippet","")
        except: return msg.get("snippet","")

    def _date(self, s):
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(s)
        except: return datetime.now()

    def send_email(self, to, subject, body, thread_id=None) -> bool:
        if not self.service: return False
        try:
            msg = MIMEText(body); msg["to"]=to; msg["subject"]=subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            pl  = {"raw": raw}
            if thread_id: pl["threadId"] = thread_id
            self.service.users().messages().send(userId="me", body=pl).execute()
            return True
        except HttpError as e:
            print(f"Send: {e}"); return False

    def create_draft(self, to, subject, body) -> bool:
        if not self.service: return False
        try:
            msg = MIMEText(body); msg["to"]=to; msg["subject"]=subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            self.service.users().drafts().create(
                userId="me", body={"message":{"raw":raw}}).execute()
            return True
        except HttpError as e:
            print(f"Draft: {e}"); return False


# ─────────────────────────────────────────────────────────────────────────────
# CALENDAR SERVICE  — free-slot logic uses live Google Calendar busy/free
# ─────────────────────────────────────────────────────────────────────────────
class CalendarService:
    def __init__(self): self.service = None

    def inject_credentials(self, creds: Credentials) -> bool:
        try:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            self.service = build("calendar","v3", credentials=creds)
            return True
        except Exception as e:
            print(f"CalSvc: {e}"); return False

    def get_events(self, days_ahead=30) -> List[CalendarEvent]:
        if not self.service:
            st.warning("Calendar service is not connected.")
            return []
        try:
            now = datetime.utcnow()
            res = self.service.events().list(
                calendarId="primary",
                timeMin=now.isoformat()+"Z",
                timeMax=(now+timedelta(days=days_ahead)).isoformat()+"Z",
                maxResults=250, singleEvents=True, orderBy="startTime",
            ).execute()
            return [e for e in (self._pe(ev) for ev in res.get("items",[])) if e]
        except HttpError as e:
            err_msg = str(e)
            st.error(f"Calendar API Error: {e.reason or e}")
            if "has not been used in project" in err_msg or "disabled" in err_msg:
                st.info("💡 **Google Calendar API is disabled in your Google Cloud project.** Please enable it in Google Cloud Console under **APIs & Services > Library > Google Calendar API**.")
            print(f"CalAPI: {e}"); return []
        except Exception as e:
            st.error(f"Error fetching calendar events: {e}")
            print(f"Calendar error: {e}"); return []

    def _pe(self, ev) -> Optional[CalendarEvent]:
        try:
            s = ev["start"].get("dateTime", ev["start"].get("date"))
            e = ev["end"].get("dateTime",   ev["end"].get("date"))
            return CalendarEvent(
                id=ev["id"], summary=ev.get("summary","No Title"),
                start_time=datetime.fromisoformat(s.replace("Z","+00:00")),
                end_time  =datetime.fromisoformat(e.replace("Z","+00:00")),
                description=ev.get("description"), location=ev.get("location"),
                attendees=[a.get("email","") for a in ev.get("attendees",[])],
                organizer=ev.get("organizer",{}).get("email"),
                status=ev.get("status","confirmed"),
            )
        except Exception as e:
            print(f"EvParse: {e}"); return None

    def find_conflicts(self, events: List[CalendarEvent]) -> List[ConflictInfo]:
        out = []
        for i,e1 in enumerate(events):
            for e2 in events[i+1:]:
                if e1.start_time < e2.end_time and e2.start_time < e1.end_time:
                    out.append(ConflictInfo(
                        event1=e1, event2=e2,
                        overlap_start=max(e1.start_time,e2.start_time),
                        overlap_end  =min(e1.end_time,  e2.end_time),
                    ))
        return out

    def find_free_slots_live(self,
                             duration_minutes: int = 60,
                             days_ahead: int = 14,
                             business_start: int = 9,
                             business_end:   int = 18,
                             start_after: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Query the Calendar freebusy API for exact busy intervals,
        then walk in 30-min steps to find genuinely free windows.

        start_after: if given, begin searching from this moment (e.g. end of
                     the conflicting event) instead of from right now.
                     Cursor is snapped to the next clean 30-min boundary.
        Returns list of dicts: {start, end, duration_minutes}.
        """
        if not self.service:
            return []

        now        = datetime.now().astimezone()
        search_end = now + timedelta(days=days_ahead)

        # ── 1. Pull busy intervals via freebusy API ───────────────────
        try:
            fb = self.service.freebusy().query(body={
                "timeMin": now.isoformat(),
                "timeMax": search_end.isoformat(),
                "items":   [{"id": "primary"}],
            }).execute()
            raw_busy = fb.get("calendars", {}).get("primary", {}).get("busy", [])
        except HttpError as e:
            print(f"Freebusy API error: {e}"); raw_busy = []

        busy_periods: List[Tuple[datetime, datetime]] = []
        for b in raw_busy:
            try:
                bs = datetime.fromisoformat(b["start"].replace("Z", "+00:00"))
                be = datetime.fromisoformat(b["end"].replace("Z",   "+00:00"))
                busy_periods.append((bs, be))
            except Exception:
                continue
        busy_periods.sort(key=lambda x: x[0])

        # ── 2. Decide where to start the cursor ───────────────────────
        # RULE: never show past slots.
        # If start_after is in the future → start there.
        # If start_after is in the past (event already happened) → start from NOW.
        # Either way, always enforce cursor >= now + 15 min buffer.
        min_start = now + timedelta(minutes=15)

        if start_after is not None:
            if start_after.tzinfo is None:
                start_after = start_after.astimezone()
            # Use whichever is later: conflict end-time OR right now
            cursor = max(start_after, min_start).replace(second=0, microsecond=0)
        else:
            cursor = min_start.replace(second=0, microsecond=0)

        # Snap up to next 30-min boundary
        mins_over = cursor.minute % 30
        if mins_over:
            cursor += timedelta(minutes=30 - mins_over)
            cursor = cursor.replace(second=0, microsecond=0)

        # ── 3. Walk forward finding free windows ─────────────────────
        free_slots = []
        slot_delta  = timedelta(minutes=duration_minutes)
        step        = timedelta(minutes=30)
        # When start_after is given we honour the caller's start point exactly
        # and do NOT push it forward to business_start.
        # We only apply business_end so we don't suggest 2am slots.
        respect_business_start = (start_after is None)
        iterations  = 0

        while cursor < search_end and len(free_slots) < 5 and iterations < 2000:
            iterations += 1

            # Skip weekends → jump to Monday at business_start (or 00:00 if ignoring floor)
            if cursor.weekday() >= 5:
                days_to_monday = 7 - cursor.weekday()
                jump_hour = business_start if respect_business_start else cursor.hour
                cursor = (cursor + timedelta(days=days_to_monday)).replace(
                    hour=jump_hour, minute=0, second=0, microsecond=0)
                continue

            # Before business hours → only enforce if no explicit start_after
            if respect_business_start and cursor.hour < business_start:
                cursor = cursor.replace(
                    hour=business_start, minute=0, second=0, microsecond=0)
                continue

            # After business hours → always skip to next day
            if cursor.hour >= business_end:
                next_start = business_start if respect_business_start else 0
                cursor = (cursor + timedelta(days=1)).replace(
                    hour=next_start, minute=0, second=0, microsecond=0)
                continue

            slot_end = cursor + slot_delta

            # Slot overflows end-of-day → next day
            eod = cursor.replace(hour=business_end, minute=0, second=0, microsecond=0)
            if slot_end > eod:
                next_start = business_start if respect_business_start else 0
                cursor = (cursor + timedelta(days=1)).replace(
                    hour=next_start, minute=0, second=0, microsecond=0)
                continue

            # Check every busy block — if overlap, jump cursor past it and retry
            hit_busy = False
            for bs, be in busy_periods:
                if cursor < be and slot_end > bs:
                    hit_busy = True
                    jump = be.replace(second=0, microsecond=0)
                    mins = jump.minute % 30
                    if mins:
                        jump += timedelta(minutes=30 - mins)
                    cursor = jump
                    break  # restart loop with new cursor

            if not hit_busy:
                free_slots.append({
                    "start":            cursor,
                    "end":              slot_end,
                    "duration_minutes": duration_minutes,
                })
                cursor += step

        return free_slots


# ─────────────────────────────────────────────────────────────────────────────
# AI ANALYZER
# ─────────────────────────────────────────────────────────────────────────────
class AIAnalyzer:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.llm = None
        if LANGCHAIN_AVAILABLE and self.api_key:
            try:
                self.llm = ChatOpenAI(
                    model=os.getenv("LLM_MODEL","gpt-4"),
                    temperature=float(os.getenv("LLM_TEMPERATURE","0.7")),
                    api_key=self.api_key,
                )
            except Exception as e: print(f"LLM: {e}")

    def analyze_email(self, email: EmailData) -> EmailData:
        if not self.llm: return self._rules(email)
        try:
            p = ChatPromptTemplate.from_messages([
                ("system","Analyse email. ONLY respond:\nCategory: <work|personal|urgent|spam|newsletter>\nPriority: <0-10>\nSentiment: <positive|neutral|negative>\nDates: <csv or none>\nActions: <csv or none>"),
                ("human","Subject:{subject}\nFrom:{sender}\nBody:{body}"),
            ])
            r = (p|self.llm).invoke({"subject":email.subject,"sender":email.sender,"body":email.body[:1000]})
            for ln in r.content.strip().split("\n"):
                if ln.startswith("Category:"): email.category=ln.split(":",1)[1].strip().lower()
                elif ln.startswith("Priority:"):
                    try: email.priority_score=int(ln.split(":",1)[1].strip())
                    except: email.priority_score=5
                elif ln.startswith("Sentiment:"): email.sentiment=ln.split(":",1)[1].strip().lower()
                elif ln.startswith("Dates:"):
                    v=ln.split(":",1)[1].strip()
                    if v.lower()!="none": email.extracted_dates=[x.strip() for x in v.split(",")]
                elif ln.startswith("Actions:"):
                    v=ln.split(":",1)[1].strip()
                    if v.lower()!="none": email.action_items=[x.strip() for x in v.split(",")]
            return email
        except Exception as e: print(f"AI: {e}"); return self._rules(email)

    def _rules(self, email: EmailData) -> EmailData:
        b,s = email.body.lower(), email.subject.lower()
        if any(w in b or w in s for w in ["meeting","project","deadline","task"]):
            email.category="work"
        elif any(w in b or w in s for w in ["urgent","asap","critical"]):
            email.category="urgent"
        elif any(w in b or w in s for w in ["unsubscribe","newsletter","promotion"]):
            email.category="newsletter"
        else: email.category="personal"
        email.priority_score = 9 if (email.is_important or email.category=="urgent") \
                               else 7 if email.category=="work" \
                               else 3 if email.category=="newsletter" else 5
        pos=sum(1 for w in ["thank","great","excellent","congratulations"] if w in b)
        neg=sum(1 for w in ["sorry","problem","issue","error","cancel"] if w in b)
        email.sentiment="positive" if pos>neg else ("negative" if neg>pos else "neutral")
        return email

    def gen_conflict_email(self,
                           conflict: ConflictInfo,
                           free_slots: List[Dict[str,Any]],
                           recipient_email: str = "") -> str:
        """
        Generate the conflict resolution email.
        Free slots are passed in and embedded verbatim — no guessing.
        """
        # Format slots for the email body
        if free_slots:
            slot_lines = "\n".join(
                f"  Option {i}: {s['start'].strftime('%A, %B %d  at  %I:%M %p')} — "
                f"{s['end'].strftime('%I:%M %p')} ({s['duration_minutes']} min)"
                for i,s in enumerate(free_slots[:5], 1)
            )
        else:
            slot_lines = "  (No free slots found — please suggest a time that works for you.)"

        if not self.llm:
            return self._tpl(conflict, free_slots, slot_lines, recipient_email)

        try:
            p = ChatPromptTemplate.from_messages([
                ("system",
                 "You are a professional assistant. Write a concise, polite email "
                 "to resolve a calendar conflict. Embed the exact alternative times "
                 "provided — do NOT invent or change any times. Keep it under 200 words."),
                ("human",
                 "Conflict:\n"
                 "  Meeting 1: {e1}  ({t1_start} – {t1_end})\n"
                 "  Meeting 2: {e2}  ({t2_start} – {t2_end})\n"
                 "  Overlap  : {ov} minutes\n\n"
                 "Available alternative slots (from live calendar):\n{slots}\n\n"
                 "Recipient: {rcpt}\n"
                 "Write the email (subject line first, then body):"),
            ])
            r = (p|self.llm).invoke({
                "e1": conflict.event1.summary,
                "t1_start": conflict.event1.start_time.strftime("%b %d at %I:%M %p"),
                "t1_end":   conflict.event1.end_time.strftime("%I:%M %p"),
                "e2": conflict.event2.summary,
                "t2_start": conflict.event2.start_time.strftime("%b %d at %I:%M %p"),
                "t2_end":   conflict.event2.end_time.strftime("%I:%M %p"),
                "ov": conflict.overlap_minutes,
                "slots": slot_lines,
                "rcpt": recipient_email or "Team",
            })
            return r.content
        except Exception as e:
            print(f"GenEmail: {e}")
            return self._tpl(conflict, free_slots, slot_lines, recipient_email)

    def _tpl(self, conflict, free_slots, slot_lines, recipient_email=""):
        to_line = f"To: {recipient_email}\n" if recipient_email else ""
        return (
            f"{to_line}"
            f"Subject: Scheduling Conflict — {conflict.event1.summary} & {conflict.event2.summary}\n\n"
            f"Hi,\n\n"
            f"I wanted to flag a scheduling conflict between two meetings:\n\n"
            f"  • {conflict.event1.summary}:  "
            f"{conflict.event1.start_time.strftime('%A %b %d, %I:%M %p')} – "
            f"{conflict.event1.end_time.strftime('%I:%M %p')}\n"
            f"  • {conflict.event2.summary}:  "
            f"{conflict.event2.start_time.strftime('%A %b %d, %I:%M %p')} – "
            f"{conflict.event2.end_time.strftime('%I:%M %p')}\n\n"
            f"These overlap by {conflict.overlap_minutes} minutes. "
            f"Based on my calendar here are genuinely free slots:\n\n"
            f"{slot_lines}\n\n"
            f"Please let me know which works best, or suggest another time.\n\n"
            f"Best regards"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ASSISTANT
# ─────────────────────────────────────────────────────────────────────────────
class EnhancedEmailAssistant:
    def __init__(self):
        self.gmail    = GmailService()
        self.calendar = CalendarService()
        self.analyzer = AIAnalyzer()
        self.llm      = None
        self.conversation_memory: List = []
        os.makedirs(MEMORY_DIR, exist_ok=True)
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE,"rb") as f:
                    self.conversation_memory = pickle.load(f)
            except: self.conversation_memory = []
        self.emails_cache:    List[EmailData]     = []
        self.events_cache:    List[CalendarEvent] = []
        self.conflicts_cache: List[ConflictInfo]  = []

    def inject_credentials(self, creds) -> bool:
        return self.gmail.inject_credentials(creds) and self.calendar.inject_credentials(creds)

    def initialize_llm(self, api_key=None) -> bool:
        if api_key:
            self.analyzer = AIAnalyzer(api_key=api_key)
            self.llm = self.analyzer.llm
        return self.llm is not None

    def fetch_emails(self, query="", max_results=50) -> List[EmailData]:
        self.emails_cache = self.gmail.get_emails(query, max_results)
        return self.emails_cache

    def analyze_emails(self, emails=None) -> List[EmailData]:
        t = emails or self.emails_cache
        a = [self.analyzer.analyze_email(e) for e in t]
        if not emails: self.emails_cache = a
        return a

    def fetch_calendar_events(self, days_ahead=30) -> List[CalendarEvent]:
        self.events_cache = self.calendar.get_events(days_ahead)
        return self.events_cache

    def detect_conflicts(self, events=None) -> List[ConflictInfo]:
        self.conflicts_cache = self.calendar.find_conflicts(events or self.events_cache)
        return self.conflicts_cache

    def find_free_slots_live(self,
                             duration_minutes: int = 60,
                             days_ahead: int = 14,
                             start_after: Optional[datetime] = None) -> List[Dict[str,Any]]:
        """Always hit the live freebusy API. start_after = begin search from this datetime."""
        return self.calendar.find_free_slots_live(
            duration_minutes=duration_minutes,
            days_ahead=days_ahead,
            start_after=start_after,
        )

    def generate_conflict_resolution(self,
                                     conflict: ConflictInfo,
                                     free_slots: List[Dict[str,Any]],
                                     recipient_email: str = "") -> str:
        return self.analyzer.gen_conflict_email(conflict, free_slots, recipient_email)

    def send_email(self, to, subject, body, thread_id=None) -> bool:
        return self.gmail.send_email(to, subject, body, thread_id)

    def create_draft(self, to, subject, body) -> bool:
        return self.gmail.create_draft(to, subject, body)

    def run_ambient_agent(self) -> Dict[str,Any]:
        r = {"status":"success","emails_fetched":0,"emails_analyzed":0,
             "events_fetched":0,"conflicts_found":0,"suggestions":[],"drafts_created":0}
        try:
            em=self.fetch_emails(max_results=50); r["emails_fetched"]=len(em)
            an=self.analyze_emails(em);           r["emails_analyzed"]=len(an)
            ev=self.fetch_calendar_events(days_ahead=30); r["events_fetched"]=len(ev)
            co=self.detect_conflicts(ev);         r["conflicts_found"]=len(co)
            s=[]
            if [e for e in an if e.priority_score and e.priority_score>=8]:
                s.append(f"{len([e for e in an if e.priority_score and e.priority_score>=8])} high-priority emails need attention")
            ui=[e for e in an if e.is_unread and e.is_important]
            if ui: s.append(f"{len(ui)} unread important emails")
            if co: s.append(f"{len(co)} calendar conflicts detected")
            tod=[e for e in ev if e.start_time.date()==datetime.now().date()]
            if tod: s.append(f"{len(tod)} events today")
            r["suggestions"]=s
            for c in co[:3]: r["drafts_created"]+=1
        except Exception as e: r["status"]="error"; r["error"]=str(e)
        return r


# ─────────────────────────────────────────────────────────────────────────────
# UI HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def cat_badge(cat: Optional[str]) -> str:
    cat = (cat or "").lower()
    colors = {
        "urgent":     ("#dc2626", "#fee2e2", "#fca5a5"),
        "work":       ("#2563eb", "#dbeafe", "#bfdbfe"),
        "personal":   ("#16a34a", "#dcfce7", "#bbf7d0"),
        "newsletter": ("#d97706", "#fef3c7", "#fde68a"),
    }
    fg, bg, border = colors.get(cat, ("#64748b", "#f1f5f9", "#e2e8f0"))
    label = cat.capitalize() if cat else "—"
    return (f"<span style='background:{bg};color:{fg};border:1px solid {border};"
            f"border-radius:6px;padding:3px 10px;font-size:0.72rem;font-weight:700;"
            f"letter-spacing:0.04em;text-transform:uppercase'>{label}</span>")

def priority_color(score: Optional[int]) -> str:
    if score is None: return "#64748b"
    if score >= 8: return "#dc2626"
    if score >= 5: return "#d97706"
    return "#64748b"

def section(title: str):
    st.markdown(
        f"<p style='font-family:DM Sans,Inter,sans-serif;font-size:0.75rem;"
        f"font-weight:700;letter-spacing:0.08em;text-transform:uppercase;"
        f"color:#64748b;margin:16px 0 8px 0'>{title}</p>",
        unsafe_allow_html=True,
    )

def divider():
    st.markdown(
        "<hr style='border:none;border-top:1px solid #e2e8f0;margin:16px 0'>",
        unsafe_allow_html=True,
    )

def slot_box(slot: Dict[str,Any]) -> str:
    return (
        f"<div style='background:#f0fdf4;border:1px solid #bbf7d0;"
        f"border-left:4px solid #16a34a;border-radius:6px;"
        f"padding:10px 14px;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between'>"
        f"<span style='color:#15803d;font-family:DM Sans,sans-serif;"
        f"font-weight:600;font-size:0.88rem'>"
        f"{slot['start'].strftime('%A, %b %d')}</span>"
        f"<span style='color:#475569;font-size:0.85rem;margin-left:10px'>"
        f"{slot['start'].strftime('%I:%M %p')} — {slot['end'].strftime('%I:%M %p')}"
        f"  ({slot['duration_minutes']} min)</span>"
        f"</div>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="InboxAI — Ambient Email Assistant",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme()

    creds = handle_google_auth()
    if creds is None: st.stop()

    # ── Sidebar ───────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            "<div style='font-family:DM Sans,sans-serif;font-weight:700;"
            "font-size:1.3rem;color:#0f172a;margin-bottom:18px;letter-spacing:-0.02em'>InboxAI</div>",
            unsafe_allow_html=True,
        )
        divider()
        section("Status")
        st.markdown(
            "<div style='display:flex;align-items:center;gap:8px;background:#ecfdf5;"
            "border:1px solid #a7f3d0;color:#065f46;font-size:0.85rem;font-weight:600;"
            "padding:8px 12px;border-radius:6px'>"
            "<span style='width:7px;height:7px;border-radius:50%;background:#10b981;display:inline-block'></span>"
            "Connected to Google</div>",
            unsafe_allow_html=True,
        )
        divider()
        section("AI Engine (Optional)")
        openai_key = st.text_input(
            "OpenAI API Key", type="password",
            placeholder="sk-…", label_visibility="collapsed"
        )
        if openai_key:
            st.markdown("<p style='color:#16a34a;font-size:0.8rem;font-weight:600;margin-top:6px'>AI mode active</p>",
                        unsafe_allow_html=True)
        else:
            st.markdown("<p style='color:#64748b;font-size:0.8rem;margin-top:6px'>Rule-based (no key)</p>",
                        unsafe_allow_html=True)
        divider()
        if st.button("Sign out", use_container_width=True):
            for k in ("_gcreds", "assistant"):
                st.session_state.pop(k, None)
            if os.path.exists("token.json"):
                try:
                    os.remove("token.json")
                except Exception:
                    pass
            st.query_params.clear()
            st.rerun()

    # ── Assistant init ────────────────────────────────────────────────────
    if "assistant" not in st.session_state:
        st.session_state["assistant"] = EnhancedEmailAssistant()
    assistant: EnhancedEmailAssistant = st.session_state["assistant"]
    assistant.inject_credentials(creds)
    if openai_key: assistant.initialize_llm(api_key=openai_key)

    # ── Page title ────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="background:#ffffff;border:1px solid #e0e0e0;border-radius:8px;padding:20px 24px;margin-bottom:20px;box-shadow:0 1px 2px rgba(0,0,0,0.02);display:flex;align-items:center;justify-content:space-between">
          <div>
            <h1 style="font-family:'DM Sans',sans-serif;font-weight:700;font-size:1.55rem;color:#111827;margin:0 0 4px 0;letter-spacing:-0.01em">Ambient Email Assistant</h1>
            <p style="font-family:'DM Sans',sans-serif;font-size:0.88rem;color:#6b7280;margin:0">Intelligent email triage, calendar conflict detection & smart scheduling</p>
          </div>
          <div style="display:flex;align-items:center;gap:6px;background:#ecfdf5;border:1px solid #a7f3d0;padding:6px 14px;border-radius:20px">
            <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#10b981"></span>
            <span style="font-size:0.8rem;font-weight:600;color:#065f46">Active &amp; Synced</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_emails, tab_calendar, tab_agent = st.tabs([
        "Emails", "Calendar & Conflicts", "Ambient Agent"
    ])

    # ══════════════════════════════════════════════════════════════════════
    # EMAILS TAB
    # ══════════════════════════════════════════════════════════════════════
    with tab_emails:
        c1, c2, c3 = st.columns([6, 1.2, 1.8])
        with c1:
            query = st.text_input("Search Gmail",
                placeholder="is:unread label:important from:boss@company.com",
                label_visibility="collapsed")
        with c2:
            mx = st.number_input("Max", 1, 200, 20, label_visibility="collapsed")
        with c3:
            if st.button("Fetch Emails", type="primary", use_container_width=True):
                with st.spinner("Fetching emails…"):
                    emails = assistant.fetch_emails(query=query, max_results=int(mx))
                if emails:
                    st.success(f"Fetched {len(emails)} emails")
                else:
                    st.info("0 matching emails found for this search filter. Try leaving search blank or check if Gmail API is enabled.")

        if assistant.emails_cache:
            ca, _ = st.columns([2, 5])
            with ca:
                if st.button("Analyse All with AI", use_container_width=True):
                    with st.spinner("Analysing…"):
                        assistant.analyze_emails()
                    st.success("Analysis complete")
            divider()
            cache = assistant.emails_cache
            m1,m2,m3,m4 = st.columns(4)
            m1.metric("Total",    len(cache))
            m2.metric("Unread",   sum(1 for e in cache if e.is_unread))
            m3.metric("Urgent",   sum(1 for e in cache if e.priority_score and e.priority_score>=8))
            m4.metric("Analysed", sum(1 for e in cache if e.category))
            divider()
            section("Inbox")

            for email in cache[:50]:
                status_tag = " [Unread]" if email.is_unread else ""
                att_tag = " (Attachment)" if email.has_attachment else ""
                cal_tag = " (Calendar)" if email.has_calendar_event else ""
                with st.expander(f"{email.subject}{status_tag}{att_tag}{cal_tag}"):
                    r1,r2 = st.columns([3,1])
                    with r1:
                        st.markdown(
                            f"<span style='color:#64748b;font-size:0.8rem;font-weight:600'>From:</span>"
                            f"<span style='color:#0f172a;font-size:0.88rem;font-weight:500;margin-left:8px'>{email.sender}</span>"
                            f"<br><span style='color:#64748b;font-size:0.8rem;font-weight:600'>Date:</span>"
                            f"<span style='color:#475569;font-size:0.84rem;margin-left:8px'>"
                            f"{email.timestamp.strftime('%b %d, %Y  %I:%M %p')}</span>",
                            unsafe_allow_html=True)
                    with r2:
                        if email.category:
                            st.markdown(cat_badge(email.category), unsafe_allow_html=True)
                        if email.priority_score is not None:
                            pc = priority_color(email.priority_score)
                            st.markdown(
                                f"<div style='color:{pc};font-size:0.82rem;font-weight:600;margin-top:6px'>"
                                f"Priority: {email.priority_score}/10</div>",
                                unsafe_allow_html=True)
                    st.markdown("<hr style='border:none;border-top:1px solid #f1f5f9;margin:12px 0'>",
                                unsafe_allow_html=True)
                    st.text_area("Body", email.body[:600], height=110,
                                 key=f"b_{email.id}", label_visibility="collapsed")
                    if email.action_items:
                        st.markdown(
                            "<div style='font-size:0.84rem;color:#2563eb;font-weight:500;margin-top:8px'>"
                            "Action Items: " + " · ".join(email.action_items) + "</div>",
                            unsafe_allow_html=True)
                    if email.sentiment:
                        st.markdown(
                            f"<div style='font-size:0.8rem;color:#64748b;margin-top:6px'>"
                            f"Sentiment: {email.sentiment.capitalize()}</div>",
                            unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # CALENDAR & CONFLICTS TAB
    # ══════════════════════════════════════════════════════════════════════
    with tab_calendar:
        c1, c2 = st.columns([5, 2])
        with c1:
            days = st.slider("Days ahead", 1, 90, 30)
        with c2:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("Fetch Calendar", type="primary", use_container_width=True):
                with st.spinner("Fetching calendar…"):
                    evs = assistant.fetch_calendar_events(days_ahead=days)
                    cfs = assistant.detect_conflicts()
                st.success(f"{len(evs)} events · {len(cfs)} conflict(s) found")

        if assistant.events_cache or assistant.conflicts_cache:
            today = sum(1 for e in assistant.events_cache
                        if e.start_time.date() == datetime.now().date())
            m1,m2,m3 = st.columns(3)
            m1.metric("Total Events", len(assistant.events_cache))
            m2.metric("Today",        today)
            m3.metric("Conflicts",    len(assistant.conflicts_cache))
            divider()

        if assistant.events_cache:
            section("Upcoming Events")
            for ev in assistant.events_cache[:30]:
                loc = f" · Location: {ev.location}" if ev.location else ""
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:16px;"
                    f"background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;"
                    f"padding:12px 18px;margin-bottom:8px;box-shadow:0 1px 2px rgba(0,0,0,0.02)'>"
                    f"<span style='font-family:DM Sans,sans-serif;background:#eff6ff;color:#2563eb;"
                    f"font-size:0.84rem;font-weight:600;min-width:145px;padding:4px 10px;border-radius:6px;border:1px solid #dbeafe'>"
                    f"{ev.start_time.strftime('%b %d · %I:%M %p')}</span>"
                    f"<span style='color:#1e293b;font-size:0.9rem;font-weight:500'>{ev.summary}{loc}</span>"
                    f"</div>",
                    unsafe_allow_html=True)

        # ── CONFLICTS ─────────────────────────────────────────────────────
        if assistant.conflicts_cache:
            divider()
            section(f"Conflicts ({len(assistant.conflicts_cache)})")

            for i, cf in enumerate(assistant.conflicts_cache):
                with st.expander(f"{str(cf)} — {cf.overlap_minutes} min overlap",
                                 expanded=(i==0)):

                    cc1, cc2 = st.columns(2)
                    for col, ev in [(cc1, cf.event1), (cc2, cf.event2)]:
                        with col:
                            st.markdown(
                                f"<div style='background:#f8fafc;border:1px solid #e2e8f0;"
                                f"border-radius:8px;padding:14px 16px'>"
                                f"<div style='font-family:DM Sans,sans-serif;font-weight:600;"
                                f"color:#0f172a;font-size:0.92rem;margin-bottom:4px'>Event: {ev.summary}</div>"
                                f"<div style='color:#64748b;font-size:0.82rem'>"
                                f"{ev.start_time.strftime('%b %d · %I:%M %p')} – "
                                f"{ev.end_time.strftime('%I:%M %p')}</div></div>",
                                unsafe_allow_html=True)

                    st.markdown(
                        f"<div style='text-align:center;background:#fef2f2;border:1px solid #fecaca;"
                        f"color:#dc2626;font-weight:600;font-size:0.84rem;border-radius:6px;padding:6px 12px;margin:12px 0'>"
                        f"Overlap: {cf.overlap_minutes} minutes</div>",
                        unsafe_allow_html=True)

                    # ── Step 1: find free slots from LIVE calendar ─────────
                    slot_key    = f"slots_{i}"
                    draft_key   = f"draft_{i}"
                    to_key      = f"to_{i}"
                    subj_key    = f"subj_{i}"
                    sent_key    = f"sent_{i}"

                    # Search starts right after the LATER of the two conflicting events
                    conflict_end = max(cf.event1.end_time, cf.event2.end_time)

                    if st.button("Check Live Calendar for Free Slots",
                                 key=f"fs_{i}", use_container_width=True, type="primary"):
                        with st.spinner("Querying live calendar via freebusy API…"):
                            slots = assistant.find_free_slots_live(
                                duration_minutes=cf.event1.duration_minutes,
                                days_ahead=14,
                                start_after=conflict_end,
                            )
                        st.session_state[slot_key] = slots

                    # Show free slots if available
                    if slot_key in st.session_state:
                        slots = st.session_state[slot_key]
                        if slots:
                            st.markdown(
                                f"<div style='color:#15803d;font-weight:600;font-size:0.84rem;margin-bottom:8px'>"
                                f"Found {len(slots)} free slots from Google Calendar:</div>",
                                unsafe_allow_html=True)
                            for s in slots[:5]:
                                st.markdown(slot_box(s), unsafe_allow_html=True)
                        else:
                            st.warning("No free slots found in the next 14 days during business hours.")

                    divider()

                    # ── Step 2: draft the email ────────────────────────────
                    if st.button("Generate Resolution Email",
                                 key=f"re_{i}", use_container_width=True):
                        slots = st.session_state.get(slot_key, [])
                        if not slots:
                            st.warning("Tip: Click 'Check Live Calendar' first to embed real free times in the email.")
                        recipient_guess = (cf.event1.organizer or cf.event2.organizer or
                                           next(iter(cf.event1.attendees or []), "") or "")
                        with st.spinner("Drafting email…"):
                            body = assistant.generate_conflict_resolution(
                                cf, slots, recipient_email=recipient_guess
                            )
                        st.session_state[draft_key]   = body
                        st.session_state[to_key]      = recipient_guess
                        st.session_state[subj_key]    = (
                            f"Scheduling Conflict — {cf.event1.summary} & {cf.event2.summary}"
                        )
                        st.session_state.pop(sent_key, None)

                    # Show draft + send UI
                    if draft_key in st.session_state:
                        st.markdown(
                            "<div style='color:#2563eb;font-weight:600;font-size:0.84rem;margin-bottom:6px'>"
                            "Draft Email — review &amp; edit before sending:</div>",
                            unsafe_allow_html=True)

                        to_addr = st.text_input(
                            "To",
                            value=st.session_state.get(to_key,""),
                            key=f"to_inp_{i}",
                            placeholder="recipient@example.com",
                        )
                        subj = st.text_input(
                            "Subject",
                            value=st.session_state.get(subj_key,""),
                            key=f"subj_inp_{i}",
                        )
                        body_edit = st.text_area(
                            "Email Body",
                            value=st.session_state[draft_key],
                            height=320,
                            key=f"body_inp_{i}",
                        )

                        btn_send, btn_save_draft = st.columns(2)

                        with btn_send:
                            if st.button("Send Email Now",
                                         key=f"send_{i}",
                                         type="primary",
                                         use_container_width=True):
                                if not to_addr.strip():
                                    st.error("Please enter a recipient email address.")
                                else:
                                    with st.spinner("Sending…"):
                                        ok = assistant.send_email(
                                            to_addr.strip(), subj.strip(), body_edit
                                        )
                                    if ok:
                                        st.session_state[sent_key] = to_addr.strip()
                                        st.success(f"Email sent to {to_addr.strip()}")
                                    else:
                                        st.error("Send failed — check Gmail permissions.")

                        with btn_save_draft:
                            if st.button("Save as Draft",
                                         key=f"savedraft_{i}",
                                         use_container_width=True):
                                if not to_addr.strip():
                                    st.error("Please enter a recipient email address.")
                                else:
                                    with st.spinner("Saving draft…"):
                                        ok = assistant.create_draft(
                                            to_addr.strip(), subj.strip(), body_edit
                                        )
                                    if ok:
                                        st.success("Draft saved to Gmail Drafts folder.")
                                    else:
                                        st.error("Failed to save draft.")

                        if sent_key in st.session_state:
                            st.markdown(
                                f"<div style='background:#f0fdf4;border:1px solid #bbf7d0;"
                                f"border-radius:6px;padding:10px 16px;margin-top:8px;"
                                f"color:#15803d;font-size:0.85rem;font-weight:500'>"
                                f"Email successfully sent to <strong>{st.session_state[sent_key]}</strong></div>",
                                unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # AGENT TAB
    # ══════════════════════════════════════════════════════════════════════
    with tab_agent:
        st.markdown(
            "<div style='background:#ffffff;border:1px solid #e0e0e0;border-radius:8px;"
            "padding:20px 24px;margin-bottom:20px;box-shadow:0 1px 2px rgba(0,0,0,0.02)'>"
            "<div style='font-family:DM Sans,sans-serif;font-weight:700;"
            "color:#0f172a;font-size:1rem;margin-bottom:10px'>What the agent does</div>"
            "<div style='font-size:0.88rem;color:#475569;line-height:1.9'>"
            "1. Fetches your last 50 emails and analyses priority, category &amp; sentiment<br>"
            "2. Pulls calendar events and detects scheduling conflicts<br>"
            "3. Uses the live freebusy API to find real available slots<br>"
            "4. Surfaces personalised action suggestions"
            "</div></div>",
            unsafe_allow_html=True,
        )
        if st.button("Run Agent Now", type="primary"):
            with st.spinner("Running agent…"):
                result = assistant.run_ambient_agent()
            if result["status"] == "success":
                m1,m2,m3,m4 = st.columns(4)
                m1.metric("Emails Fetched",  result["emails_fetched"])
                m2.metric("Analysed",        result["emails_analyzed"])
                m3.metric("Events",          result["events_fetched"])
                m4.metric("Conflicts",       result["conflicts_found"])
                divider()
                if result["suggestions"]:
                    section("Suggestions")
                    for s in result["suggestions"]:
                        st.markdown(
                            f"<div style='background:#eff6ff;border:1px solid #bfdbfe;"
                            f"border-left:4px solid #2563eb;border-radius:6px;"
                            f"padding:12px 18px;margin-bottom:8px;"
                            f"font-size:0.9rem;font-weight:500;color:#1e40af'>{s}</div>",
                            unsafe_allow_html=True)
                else:
                    st.success("All clear — no urgent items or conflicts detected.")
            else:
                st.error(f"Agent error: {result.get('error')}")


if __name__ == "__main__":
    main()
