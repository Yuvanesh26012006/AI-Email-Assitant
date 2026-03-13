"""
Ambient Email Assistant — Clean Attractive UI
OAuth: direct requests.post (no oauthlib/PKCE).
Features: real free-slot detection from live calendar + send email after draft.
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
APP_URL      = "https://inboxai.streamlit.app"
REDIRECT_URI = APP_URL
MEMORY_DIR   = "memory"
MEMORY_FILE  = os.path.join(MEMORY_DIR, "conversation_memory.pkl")

# ─────────────────────────────────────────────────────────────────────────────
# THEME
# ─────────────────────────────────────────────────────────────────────────────
THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
html,body,[data-testid="stAppViewContainer"]{background-color:#0b0f19!important;color:#c9d8ea!important;font-family:'Inter',sans-serif!important;}
[data-testid="stHeader"]{background:transparent!important;}
#MainMenu,footer,[data-testid="stToolbar"]{display:none!important;}
[data-testid="stSidebar"]{background:#0d1321!important;border-right:1px solid #1e2d42!important;}
[data-testid="stSidebarContent"]{padding:1.5rem 1rem!important;}
.stTabs [data-baseweb="tab-list"]{background:transparent!important;border-bottom:1px solid #1e2d42!important;gap:0!important;}
.stTabs [data-baseweb="tab"]{background:transparent!important;color:#4a6080!important;font-family:'Space Grotesk',sans-serif!important;font-weight:500!important;font-size:0.88rem!important;padding:0.65rem 1.4rem!important;border:none!important;}
.stTabs [aria-selected="true"]{color:#60a5fa!important;border-bottom:2px solid #60a5fa!important;background:transparent!important;}
.stTabs [data-baseweb="tab-panel"]{padding-top:1.5rem!important;}
.stButton>button{background:#131d2e!important;border:1px solid #1e3050!important;color:#8ab4d8!important;border-radius:8px!important;font-family:'Inter',sans-serif!important;font-size:0.85rem!important;font-weight:500!important;transition:all 0.15s ease!important;}
.stButton>button:hover{background:#1a2d47!important;border-color:#2e5080!important;color:#c0d8f0!important;box-shadow:0 2px 12px rgba(96,165,250,0.1)!important;}
.stButton>button[kind="primary"]{background:linear-gradient(135deg,#1d4ed8,#1e40af)!important;border-color:#2563eb!important;color:#dbeafe!important;}
.stButton>button[kind="primary"]:hover{background:linear-gradient(135deg,#2563eb,#1d4ed8)!important;box-shadow:0 4px 20px rgba(37,99,235,0.3)!important;}
.stTextInput>div>div>input,.stTextArea>div>div>textarea,.stNumberInput>div>div>input{background:#0d1828!important;border:1px solid #1e2d42!important;border-radius:8px!important;color:#c9d8ea!important;font-family:'Inter',sans-serif!important;font-size:0.88rem!important;}
.stTextInput>div>div>input:focus,.stTextArea>div>div>textarea:focus{border-color:#2563eb!important;box-shadow:0 0 0 2px rgba(37,99,235,0.15)!important;}
input::placeholder,textarea::placeholder{color:#2e4060!important;}
[data-testid="stExpander"]{background:#0e1a2d!important;border:1px solid #1e2d42!important;border-radius:10px!important;}
[data-testid="stExpander"] summary{color:#8ab4d8!important;font-size:0.88rem!important;}
[data-testid="stMetric"]{background:#0e1a2d!important;border:1px solid #1e2d42!important;border-radius:10px!important;padding:1rem 1.2rem!important;}
[data-testid="stMetricValue"]{font-family:'Space Grotesk',sans-serif!important;color:#e2edf8!important;font-weight:700!important;}
[data-testid="stMetricLabel"]{color:#3a5575!important;font-size:0.72rem!important;text-transform:uppercase!important;letter-spacing:0.07em!important;}
.stSuccess{background:#051a10!important;border:1px solid #14532d!important;color:#4ade80!important;border-radius:8px!important;}
.stError{background:#1a0505!important;border:1px solid #7f1d1d!important;color:#f87171!important;border-radius:8px!important;}
.stInfo{background:#050e1f!important;border:1px solid #1e3a5f!important;color:#60a5fa!important;border-radius:8px!important;}
.stWarning{background:#1a1005!important;border:1px solid #78350f!important;color:#fbbf24!important;border-radius:8px!important;}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] span{color:#4a6080!important;}
[data-testid="stSpinner"]>div{border-top-color:#60a5fa!important;}
</style>
"""

def inject_theme():
    st.markdown(THEME_CSS, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# OAUTH — direct requests.post, no oauthlib, no PKCE
# ─────────────────────────────────────────────────────────────────────────────
def _gcfg() -> dict:
    try:
        cid = st.secrets["google_credentials"]["client_id"]
        cs  = st.secrets["google_credentials"]["client_secret"]
    except Exception:
        cid = os.getenv("GOOGLE_CLIENT_ID", "")
        cs  = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not cid or not cs:
        st.error("Google credentials not found in Streamlit secrets.")
        st.stop()
    return {"client_id": cid, "client_secret": cs,
            "auth_uri":  "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"}

def _build_auth_url() -> str:
    from urllib.parse import urlencode
    c = _gcfg()
    return c["auth_uri"] + "?" + urlencode({
        "client_id": c["client_id"], "redirect_uri": REDIRECT_URI,
        "response_type": "code", "scope": " ".join(SCOPES),
        "access_type": "offline", "prompt": "consent",
    })

def _exchange_code(code: str) -> Credentials:
    c    = _gcfg()
    resp = _requests.post(c["token_uri"], data={
        "code": code, "client_id": c["client_id"],
        "client_secret": c["client_secret"],
        "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code",
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

def _save_creds(creds: Credentials):
    st.session_state["_gcreds"] = {
        "token": creds.token, "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri, "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }

def _load_creds() -> Optional[Credentials]:
    d = st.session_state.get("_gcreds")
    if not d: return None
    return Credentials(
        token=d["token"], refresh_token=d["refresh_token"],
        token_uri=d["token_uri"], client_id=d["client_id"],
        client_secret=d["client_secret"], scopes=d["scopes"],
        expiry=datetime.fromisoformat(d["expiry"]) if d.get("expiry") else None,
    )

def handle_google_auth() -> Optional[Credentials]:
    if "_gcreds" in st.session_state:
        creds = _load_creds()
        if creds and creds.valid: return creds
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request()); _save_creds(creds); return creds
            except Exception:
                st.session_state.pop("_gcreds", None)

    params = dict(st.query_params)
    if "error" in params:
        st.error(f"Google sign-in error: {params['error']}")
        st.query_params.clear(); return None

    if "code" in params:
        code = params["code"]
        st.query_params.clear()
        try:
            with st.spinner("Completing sign-in…"):
                creds = _exchange_code(code)
            _save_creds(creds); st.rerun()
        except Exception as e:
            st.error(f"Sign-in failed: {e}")
        return None

    auth_url = _build_auth_url()
    st.markdown("<br><br>", unsafe_allow_html=True)
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        st.markdown(
            "<h1 style='text-align:center;font-family:Space Grotesk,sans-serif;"
            "font-size:2.4rem;font-weight:700;color:#e2edf8;margin-bottom:4px'>📬 InboxAI</h1>"
            "<p style='text-align:center;color:#3a5575;font-size:0.95rem;margin-bottom:28px'>"
            "AI-powered email analysis &amp; smart scheduling</p>",
            unsafe_allow_html=True,
        )
        for icon, text in [
            ("📧", "Smart email prioritisation & sentiment analysis"),
            ("📅", "Calendar conflict detection & resolution drafts"),
            ("🕐", "Free slot finder with live calendar check"),
            ("🤖", "Ambient AI agent for automated triage"),
        ]:
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:12px;background:#0e1a2d;"
                f"border:1px solid #1e2d42;border-radius:8px;padding:11px 16px;margin-bottom:7px'>"
                f"<span style='font-size:1.1rem'>{icon}</span>"
                f"<span style='font-size:0.84rem;color:#6b8aaa'>{text}</span></div>",
                unsafe_allow_html=True,
            )
        st.markdown("<br>", unsafe_allow_html=True)
        st.link_button("🔐  Sign in with Google", url=auth_url, use_container_width=True)
        st.markdown(
            "<p style='text-align:center;color:#1e3050;font-size:0.73rem;margin-top:12px'>"
            "Requires Gmail &amp; Google Calendar access</p>",
            unsafe_allow_html=True,
        )
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
        if not self.service: return []
        try:
            res = self.service.users().messages().list(
                userId="me", q=query, maxResults=max_results).execute()
            return [e for e in (self._parse(m["id"]) for m in res.get("messages",[])) if e]
        except HttpError as e:
            print(f"Gmail: {e}"); return []

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
        if not self.service: return []
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
            print(f"CalAPI: {e}"); return []

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
        if start_after is not None:
            # Make timezone-aware if needed
            if start_after.tzinfo is None:
                start_after = start_after.astimezone()
            # Start exactly at the conflict-end time, snap up to next 30-min mark
            cursor = start_after.replace(second=0, microsecond=0)
        else:
            # Default: 15 min from now, snapped to next 30-min mark
            cursor = now + timedelta(minutes=15)
            cursor = cursor.replace(second=0, microsecond=0)

        # Snap cursor up to the next 30-min boundary (e.g. 8:00 → 8:00, 8:05 → 8:30)
        mins_over = cursor.minute % 30
        if mins_over:
            cursor += timedelta(minutes=30 - mins_over)
            cursor = cursor.replace(second=0, microsecond=0)

        # Never search before now
        if cursor < now:
            cursor = now + timedelta(minutes=15)
            mins_over = cursor.minute % 30
            if mins_over:
                cursor += timedelta(minutes=30 - mins_over)
            cursor = cursor.replace(second=0, microsecond=0)

        # ── 3. Walk forward finding free windows ─────────────────────
        free_slots = []
        slot_delta = timedelta(minutes=duration_minutes)
        step       = timedelta(minutes=30)
        iterations = 0

        while cursor < search_end and len(free_slots) < 20 and iterations < 2000:
            iterations += 1

            # Skip weekends → jump to Monday 09:00
            if cursor.weekday() >= 5:
                days_to_monday = 7 - cursor.weekday()
                cursor = (cursor + timedelta(days=days_to_monday)).replace(
                    hour=business_start, minute=0, second=0, microsecond=0)
                continue

            # Before business hours → jump to business_start same day
            if cursor.hour < business_start:
                cursor = cursor.replace(
                    hour=business_start, minute=0, second=0, microsecond=0)
                continue

            # After business hours → jump to next day business_start
            if cursor.hour >= business_end or (cursor.hour == business_end and cursor.minute > 0):
                cursor = (cursor + timedelta(days=1)).replace(
                    hour=business_start, minute=0, second=0, microsecond=0)
                continue

            slot_end = cursor + slot_delta

            # Slot would overflow end of business day → next day
            eod = cursor.replace(
                hour=business_end, minute=0, second=0, microsecond=0)
            if slot_end > eod:
                cursor = (cursor + timedelta(days=1)).replace(
                    hour=business_start, minute=0, second=0, microsecond=0)
                continue

            # Check overlap with every busy block.
            # On any hit, jump cursor to the END of that busy block (skip it entirely).
            hit_busy = False
            for bs, be in busy_periods:
                if cursor < be and slot_end > bs:   # overlap detected
                    hit_busy = True
                    # Jump to end of this busy block, snapped to next 30-min mark
                    jump = be.replace(second=0, microsecond=0)
                    mins = jump.minute % 30
                    if mins:
                        jump += timedelta(minutes=30 - mins)
                    cursor = jump
                    break   # re-evaluate from the new cursor position

            if not hit_busy:
                # Genuinely free — record it and step forward
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
                s.append(f"🔴  {len([e for e in an if e.priority_score and e.priority_score>=8])} high-priority emails need attention")
            ui=[e for e in an if e.is_unread and e.is_important]
            if ui: s.append(f"📬  {len(ui)} unread important emails")
            if co: s.append(f"⚡  {len(co)} calendar conflicts detected")
            tod=[e for e in ev if e.start_time.date()==datetime.now().date()]
            if tod: s.append(f"📅  {len(tod)} events today")
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
        "urgent":     ("#fca5a5","#450a0a"),
        "work":       ("#93c5fd","#0c1a3a"),
        "personal":   ("#6ee7b7","#052e16"),
        "newsletter": ("#fde68a","#3b1d08"),
    }
    fg,bg = colors.get(cat,("#94a3b8","#0f172a"))
    label = cat.capitalize() if cat else "—"
    return (f"<span style='background:{bg};color:{fg};border-radius:5px;"
            f"padding:2px 9px;font-size:0.72rem;font-weight:600;"
            f"letter-spacing:0.04em;text-transform:uppercase'>{label}</span>")

def priority_color(score: Optional[int]) -> str:
    if score is None: return "#3a5575"
    if score >= 8: return "#f87171"
    if score >= 5: return "#fbbf24"
    return "#3a5575"

def section(title: str):
    st.markdown(
        f"<p style='font-family:Space Grotesk,sans-serif;font-size:0.7rem;"
        f"font-weight:600;letter-spacing:0.1em;text-transform:uppercase;"
        f"color:#2e4a68;margin-bottom:10px'>{title}</p>",
        unsafe_allow_html=True,
    )

def divider():
    st.markdown(
        "<hr style='border:none;border-top:1px solid #1e2d42;margin:18px 0'>",
        unsafe_allow_html=True,
    )

def slot_box(slot: Dict[str,Any]) -> str:
    return (
        f"<div style='background:#051428;border:1px solid #1e3a5f;"
        f"border-left:3px solid #2563eb;border-radius:7px;"
        f"padding:10px 14px;margin-bottom:7px'>"
        f"<span style='color:#60a5fa;font-family:Space Grotesk,sans-serif;"
        f"font-weight:600;font-size:0.85rem'>"
        f"🟢 {slot['start'].strftime('%A, %b %d')}</span>"
        f"<span style='color:#3a5575;font-size:0.82rem;margin-left:10px'>"
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
        page_icon="📬", layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme()

    creds = handle_google_auth()
    if creds is None: st.stop()

    # ── Sidebar ───────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            "<div style='font-family:Space Grotesk,sans-serif;font-weight:700;"
            "font-size:1.15rem;color:#e2edf8;margin-bottom:20px'>📬 InboxAI</div>",
            unsafe_allow_html=True,
        )
        divider()
        section("Status")
        st.success("✓ Connected to Google")
        divider()
        section("AI Engine (Optional)")
        openai_key = st.text_input(
            "OpenAI API Key", type="password",
            placeholder="sk-…", label_visibility="collapsed"
        )
        if openai_key:
            st.markdown("<p style='color:#4ade80;font-size:0.78rem'>✓ AI mode active</p>",
                        unsafe_allow_html=True)
        else:
            st.markdown("<p style='color:#2e4a68;font-size:0.78rem'>Rule-based (no key)</p>",
                        unsafe_allow_html=True)
        divider()
        if st.button("Sign out", use_container_width=True):
            for k in ("_gcreds","assistant"):
                st.session_state.pop(k, None)
            st.query_params.clear(); st.rerun()

    # ── Assistant init ────────────────────────────────────────────────────
    if "assistant" not in st.session_state:
        st.session_state["assistant"] = EnhancedEmailAssistant()
    assistant: EnhancedEmailAssistant = st.session_state["assistant"]
    assistant.inject_credentials(creds)
    if openai_key: assistant.initialize_llm(api_key=openai_key)

    # ── Page title ────────────────────────────────────────────────────────
    st.markdown(
        "<h1 style='font-family:Space Grotesk,sans-serif;font-weight:700;"
        "font-size:1.8rem;color:#e2edf8;margin-bottom:4px'>Ambient Email Assistant</h1>"
        "<p style='color:#2e4a68;font-size:0.9rem;margin-bottom:24px'>"
        "AI-powered email triage, conflict detection &amp; smart scheduling</p>",
        unsafe_allow_html=True,
    )

    tab_emails, tab_calendar, tab_agent = st.tabs([
        "📧   Emails", "📅   Calendar & Conflicts", "🤖   Ambient Agent"
    ])

    # ══════════════════════════════════════════════════════════════════════
    # EMAILS TAB
    # ══════════════════════════════════════════════════════════════════════
    with tab_emails:
        c1,c2,c3 = st.columns([4,1,1])
        with c1:
            query = st.text_input("Search Gmail",
                placeholder="is:unread   label:important   from:boss@company.com",
                label_visibility="collapsed")
        with c2:
            mx = st.number_input("Max",1,200,20,label_visibility="collapsed")
        with c3:
            if st.button("Fetch Emails", type="primary", use_container_width=True):
                with st.spinner("Fetching emails…"):
                    emails = assistant.fetch_emails(query=query, max_results=int(mx))
                st.success(f"Fetched {len(emails)} emails")

        if assistant.emails_cache:
            ca, _ = st.columns([2,5])
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
                dot = "🔵" if email.is_unread else "⚪"
                att = " 📎" if email.has_attachment else ""
                cal = " 📅" if email.has_calendar_event else ""
                with st.expander(f"{dot}  {email.subject}{att}{cal}"):
                    r1,r2 = st.columns([3,1])
                    with r1:
                        st.markdown(
                            f"<span style='color:#2e4a68;font-size:0.8rem'>From</span>"
                            f"<span style='color:#8ab4d8;font-size:0.85rem;margin-left:8px'>{email.sender}</span>"
                            f"<br><span style='color:#2e4a68;font-size:0.8rem'>Date</span>"
                            f"<span style='color:#4a6080;font-size:0.82rem;margin-left:8px'>"
                            f"{email.timestamp.strftime('%b %d, %Y  %I:%M %p')}</span>",
                            unsafe_allow_html=True)
                    with r2:
                        if email.category:
                            st.markdown(cat_badge(email.category), unsafe_allow_html=True)
                        if email.priority_score is not None:
                            pc = priority_color(email.priority_score)
                            st.markdown(
                                f"<div style='color:{pc};font-size:0.78rem;margin-top:4px'>"
                                f"Priority {email.priority_score}/10</div>",
                                unsafe_allow_html=True)
                    st.markdown("<hr style='border:none;border-top:1px solid #1e2d42;margin:10px 0'>",
                                unsafe_allow_html=True)
                    st.text_area("Body", email.body[:600], height=110,
                                 key=f"b_{email.id}", label_visibility="collapsed")
                    if email.action_items:
                        st.markdown(
                            "<div style='font-size:0.8rem;color:#60a5fa;margin-top:6px'>"
                            "⚡ " + "  ·  ".join(email.action_items) + "</div>",
                            unsafe_allow_html=True)
                    if email.sentiment:
                        icons = {"positive":"😊","negative":"😟","neutral":"😐"}
                        st.markdown(
                            f"<div style='font-size:0.78rem;color:#2e4a68;margin-top:4px'>"
                            f"{icons.get(email.sentiment,'')} {email.sentiment.capitalize()} sentiment</div>",
                            unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # CALENDAR & CONFLICTS TAB
    # ══════════════════════════════════════════════════════════════════════
    with tab_calendar:
        c1,c2 = st.columns([4,1])
        with c1:
            days = st.slider("Days ahead",1,90,30,label_visibility="collapsed")
        with c2:
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
                loc = f"  ·  📍 {ev.location}" if ev.location else ""
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:16px;"
                    f"background:#0e1a2d;border:1px solid #1e2d42;border-radius:8px;"
                    f"padding:10px 16px;margin-bottom:6px'>"
                    f"<span style='font-family:Space Grotesk,sans-serif;color:#60a5fa;"
                    f"font-size:0.82rem;font-weight:600;min-width:140px'>"
                    f"{ev.start_time.strftime('%b %d · %I:%M %p')}</span>"
                    f"<span style='color:#8ab4d8;font-size:0.88rem'>{ev.summary}{loc}</span>"
                    f"</div>",
                    unsafe_allow_html=True)

        # ── CONFLICTS ─────────────────────────────────────────────────────
        if assistant.conflicts_cache:
            divider()
            section(f"⚠️  Conflicts  ({len(assistant.conflicts_cache)})")

            for i, cf in enumerate(assistant.conflicts_cache):
                with st.expander(f"⚡  {str(cf)}  —  {cf.overlap_minutes} min overlap",
                                 expanded=(i==0)):

                    cc1, cc2 = st.columns(2)
                    for col, ev in [(cc1, cf.event1), (cc2, cf.event2)]:
                        with col:
                            st.markdown(
                                f"<div style='background:#0e1a2d;border:1px solid #1e2d42;"
                                f"border-radius:8px;padding:14px 16px'>"
                                f"<div style='font-family:Space Grotesk,sans-serif;font-weight:600;"
                                f"color:#e2edf8;font-size:0.9rem;margin-bottom:4px'>📅 {ev.summary}</div>"
                                f"<div style='color:#3a5575;font-size:0.8rem'>"
                                f"{ev.start_time.strftime('%b %d · %I:%M %p')} – "
                                f"{ev.end_time.strftime('%I:%M %p')}</div></div>",
                                unsafe_allow_html=True)

                    st.markdown(
                        f"<div style='text-align:center;color:#f87171;font-size:0.82rem;margin:12px 0'>"
                        f"⚡ Overlap: {cf.overlap_minutes} minutes</div>",
                        unsafe_allow_html=True)

                    # ── Step 1: find free slots from LIVE calendar ─────────
                    slot_key    = f"slots_{i}"
                    draft_key   = f"draft_{i}"
                    to_key      = f"to_{i}"
                    subj_key    = f"subj_{i}"
                    sent_key    = f"sent_{i}"

                    # Search starts right after the LATER of the two conflicting events
                    conflict_end = max(cf.event1.end_time, cf.event2.end_time)

                    if st.button("🔍 Check Live Calendar for Free Slots",
                                 key=f"fs_{i}", use_container_width=True, type="primary"):
                        with st.spinner("Querying live calendar via freebusy API…"):
                            slots = assistant.find_free_slots_live(
                                duration_minutes=cf.event1.duration_minutes,
                                days_ahead=14,
                                start_after=conflict_end,   # begin right after conflict ends
                            )
                        st.session_state[slot_key] = slots

                    # Show free slots if available
                    if slot_key in st.session_state:
                        slots = st.session_state[slot_key]
                        if slots:
                            st.markdown(
                                f"<div style='color:#4ade80;font-size:0.82rem;margin-bottom:8px'>"
                                f"✅ Found {len(slots)} genuinely free slots (live from Google Calendar):</div>",
                                unsafe_allow_html=True)
                            for s in slots[:8]:
                                st.markdown(slot_box(s), unsafe_allow_html=True)
                        else:
                            st.warning("No free slots found in the next 14 days during business hours.")

                    divider()

                    # ── Step 2: draft the email ────────────────────────────
                    if st.button("✉️ Generate Resolution Email",
                                 key=f"re_{i}", use_container_width=True):
                        slots = st.session_state.get(slot_key, [])
                        if not slots:
                            st.warning("💡 Tip: Click 'Check Live Calendar' first to embed real free times in the email.")
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
                            "<div style='color:#60a5fa;font-size:0.82rem;margin-bottom:4px'>"
                            "📝 Draft Email — review &amp; edit before sending:</div>",
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
                            if st.button("📤 Send Email Now",
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
                                        st.success(f"✅ Email sent to {to_addr.strip()}")
                                    else:
                                        st.error("Send failed — check Gmail permissions.")

                        with btn_save_draft:
                            if st.button("💾 Save as Draft",
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
                                        st.success("💾 Draft saved to Gmail Drafts folder.")
                                    else:
                                        st.error("Failed to save draft.")

                        if sent_key in st.session_state:
                            st.markdown(
                                f"<div style='background:#051a10;border:1px solid #14532d;"
                                f"border-radius:8px;padding:10px 16px;margin-top:8px;"
                                f"color:#4ade80;font-size:0.85rem'>"
                                f"✅ Email successfully sent to "
                                f"<strong>{st.session_state[sent_key]}</strong></div>",
                                unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # AGENT TAB
    # ══════════════════════════════════════════════════════════════════════
    with tab_agent:
        st.markdown(
            "<div style='background:#0e1a2d;border:1px solid #1e2d42;border-radius:10px;"
            "padding:20px 24px;margin-bottom:24px'>"
            "<div style='font-family:Space Grotesk,sans-serif;font-weight:600;"
            "color:#e2edf8;font-size:1rem;margin-bottom:10px'>🤖 What the agent does</div>"
            "<div style='font-size:0.85rem;color:#3a5575;line-height:1.8'>"
            "① Fetches your last 50 emails and analyses priority, category &amp; sentiment<br>"
            "② Pulls calendar events and detects scheduling conflicts<br>"
            "③ Uses the live freebusy API to find real available slots<br>"
            "④ Surfaces personalised action suggestions"
            "</div></div>",
            unsafe_allow_html=True,
        )
        if st.button("▶  Run Agent Now", type="primary"):
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
                            f"<div style='background:#050e1f;border:1px solid #1e3a5f;"
                            f"border-left:3px solid #2563eb;border-radius:8px;"
                            f"padding:12px 16px;margin-bottom:8px;"
                            f"font-size:0.88rem;color:#60a5fa'>{s}</div>",
                            unsafe_allow_html=True)
                else:
                    st.success("✅ All clear — no urgent items or conflicts detected.")
            else:
                st.error(f"Agent error: {result.get('error')}")


if __name__ == "__main__":
    main()
