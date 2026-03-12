"""
Ambient Email Assistant
AI-powered email and calendar management.
Streamlit Cloud compatible — browser OAuth via direct HTTP, no PKCE.
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

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

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

MEMORY_DIR  = "memory"
MEMORY_FILE = os.path.join(MEMORY_DIR, "conversation_memory.pkl")

# ---------------------------------------------------------------------------
# OAUTH — pure requests, zero oauthlib, zero PKCE
# ---------------------------------------------------------------------------

def _google_creds() -> dict:
    """Read client_id / client_secret from Streamlit secrets or env vars."""
    try:
        cid = st.secrets["google_credentials"]["client_id"]
        csecret = st.secrets["google_credentials"]["client_secret"]
    except (KeyError, FileNotFoundError):
        cid     = os.getenv("GOOGLE_CLIENT_ID", "")
        csecret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not cid or not csecret:
        st.error("Google credentials not found in Streamlit secrets.")
        st.stop()
    return {
        "client_id":     cid,
        "client_secret": csecret,
        "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
        "token_uri":     "https://oauth2.googleapis.com/token",
    }


def _build_auth_url() -> str:
    """Construct the Google consent-screen URL manually (no oauthlib)."""
    from urllib.parse import urlencode
    c = _google_creds()
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
    """
    POST the authorization code straight to Google's token endpoint.
    No oauthlib, no PKCE, no state — nothing that can be lost across reruns.
    """
    c    = _google_creds()
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
    """
    Full OAuth flow for Streamlit Cloud.
    Token exchange is done with a plain requests.post so PKCE / state /
    code_verifier are never involved — nothing to lose across reruns.
    """
    # Already signed in?
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

    # Callback from Google?
    params = dict(st.query_params)

    if "error" in params:
        st.error(f"Google sign-in error: {params['error']}")
        st.query_params.clear()
        return None

    if "code" in params:
        code = params["code"]
        # clear URL immediately so a page-refresh doesn't reuse the code
        st.query_params.clear()
        try:
            with st.spinner("Completing sign-in…"):
                creds = _exchange_code(code)
            _save_creds(creds)
            st.rerun()
        except Exception as e:
            st.error(f"Sign-in failed: {e}")
        return None

    # Show sign-in button
    auth_url = _build_auth_url()
    st.markdown(
        """
        <div style='text-align:center;padding:60px 20px'>
          <h1>📬 Ambient Email Assistant</h1>
          <p style='font-size:18px;color:#555'>
            Connect your Google account to get started.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([2, 1, 2])
    with c2:
        st.link_button("🔐 Sign in with Google", auth_url, use_container_width=True)
    st.info(
        "This app requires Gmail and Google Calendar access to analyse "
        "emails, detect scheduling conflicts, and draft replies."
    )
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
        return f"Email(subject='{self.subject}', from='{self.sender}')"


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

    def __str__(self):
        return f"Event('{self.summary}', {self.start_time} - {self.end_time})"


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
        return (
            f"Conflict: '{self.event1.summary}' vs '{self.event2.summary}' "
            f"({self.overlap_minutes} min)"
        )


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
            print(f"GmailService.inject_credentials: {e}")
            return False

    def get_emails(self, query: str = "", max_results: int = 50) -> List[EmailData]:
        if not self.service:
            return []
        try:
            results  = self.service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()
            messages = results.get("messages", [])
            return [e for e in (self._parse_message(m["id"]) for m in messages) if e]
        except HttpError as e:
            print(f"Gmail API error: {e}")
            return []

    def _parse_message(self, msg_id: str) -> Optional[EmailData]:
        try:
            msg     = self.service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()
            headers = msg["payload"]["headers"]

            def hdr(name):
                return next(
                    (h["value"] for h in headers if h["name"].lower() == name), ""
                )

            subject  = hdr("subject") or "No Subject"
            sender   = hdr("from")    or "Unknown"
            recipient= hdr("to")      or "Unknown"
            date_str = hdr("date")
            sender_email = self._extract_email(sender)
            timestamp    = self._parse_date(date_str)
            body         = self._get_body(msg)
            snippet      = msg.get("snippet", "")
            labels       = msg.get("labelIds", [])

            return EmailData(
                id=msg_id,
                thread_id=msg["threadId"],
                subject=subject,
                sender=sender,
                recipient=recipient,
                timestamp=timestamp,
                body=body,
                snippet=snippet,
                is_unread    ="UNREAD"    in labels,
                is_important ="IMPORTANT" in labels or "STARRED" in labels,
                has_attachment=self._has_attachments(msg),
                has_calendar_event=self._has_calendar(body, subject),
                sender_email=sender_email,
                labels=labels,
            )
        except Exception as e:
            print(f"Error parsing message {msg_id}: {e}")
            return None

    def _extract_email(self, s: str) -> str:
        m = re.search(r"<([^>]+)>", s)
        if m:
            return m.group(1)
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

    def send_email(self, to: str, subject: str, body: str,
                   thread_id: Optional[str] = None) -> bool:
        if not self.service:
            return False
        try:
            msg = MIMEText(body)
            msg["to"]      = to
            msg["subject"] = subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            payload = {"raw": raw}
            if thread_id:
                payload["threadId"] = thread_id
            self.service.users().messages().send(userId="me", body=payload).execute()
            return True
        except HttpError as e:
            print(f"Error sending email: {e}")
            return False

    def create_draft(self, to: str, subject: str, body: str) -> bool:
        if not self.service:
            return False
        try:
            msg = MIMEText(body)
            msg["to"]      = to
            msg["subject"] = subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            self.service.users().drafts().create(
                userId="me", body={"message": {"raw": raw}}
            ).execute()
            return True
        except HttpError as e:
            print(f"Error creating draft: {e}")
            return False


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
            print(f"CalendarService.inject_credentials: {e}")
            return False

    def get_events(self, days_ahead: int = 30) -> List[CalendarEvent]:
        if not self.service:
            return []
        try:
            now      = datetime.utcnow()
            result   = self.service.events().list(
                calendarId="primary",
                timeMin=now.isoformat() + "Z",
                timeMax=(now + timedelta(days=days_ahead)).isoformat() + "Z",
                maxResults=100,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            return [e for e in (self._parse_event(ev) for ev in result.get("items", [])) if e]
        except HttpError as e:
            print(f"Calendar API error: {e}")
            return []

    def _parse_event(self, event: dict) -> Optional[CalendarEvent]:
        try:
            start = event["start"].get("dateTime", event["start"].get("date"))
            end   = event["end"].get("dateTime",   event["end"].get("date"))
            return CalendarEvent(
                id=event["id"],
                summary=event.get("summary", "No Title"),
                start_time=datetime.fromisoformat(start.replace("Z", "+00:00")),
                end_time  =datetime.fromisoformat(end.replace("Z",   "+00:00")),
                description=event.get("description"),
                location   =event.get("location"),
                attendees  =[a.get("email", "") for a in event.get("attendees", [])],
                organizer  =event.get("organizer", {}).get("email"),
                status     =event.get("status", "confirmed"),
            )
        except Exception as e:
            print(f"Error parsing event: {e}")
            return None

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
            now        = datetime.now()
            search_end = now + timedelta(days=days_ahead)

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
                if mins >= 60:
                    cur = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                else:
                    cur = now.replace(minute=mins, second=0, microsecond=0)

            iters = 0
            while cur < search_end and iters < 1000:
                iters += 1
                slot_end = cur + timedelta(minutes=duration_minutes)

                if cur.hour < 8:
                    cur = cur.replace(hour=8, minute=0, second=0, microsecond=0)
                    continue
                if cur.hour >= 20:
                    cur = (cur + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
                    continue

                is_free = all(not (cur < e and slot_end > s) for s, e in future)
                if is_free and cur > now:
                    free_slots.append({"start": cur, "end": slot_end, "duration_minutes": duration_minutes})
                if len(free_slots) >= 20:
                    break
                cur += timedelta(minutes=30)

            return free_slots
        except Exception as e:
            print(f"Error finding free slots: {e}")
            return []


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
                ("system", """Analyse the email and respond ONLY in this format:
Category: <work|personal|urgent|spam|newsletter>
Priority: <0-10>
Sentiment: <positive|neutral|negative>
Dates: <comma-separated or none>
Actions: <comma-separated or none>"""),
                ("human", "Subject: {subject}\nFrom: {sender}\nBody: {body}"),
            ])
            resp = (prompt | self.llm).invoke({
                "subject": email.subject,
                "sender":  email.sender,
                "body":    email.body[:1000],
            })
            for line in resp.content.strip().split("\n"):
                if line.startswith("Category:"):
                    email.category = line.split(":", 1)[1].strip().lower()
                elif line.startswith("Priority:"):
                    try: email.priority_score = int(line.split(":", 1)[1].strip())
                    except: email.priority_score = 5
                elif line.startswith("Sentiment:"):
                    email.sentiment = line.split(":", 1)[1].strip().lower()
                elif line.startswith("Dates:"):
                    v = line.split(":", 1)[1].strip()
                    if v.lower() != "none":
                        email.extracted_dates = [x.strip() for x in v.split(",")]
                elif line.startswith("Actions:"):
                    v = line.split(":", 1)[1].strip()
                    if v.lower() != "none":
                        email.action_items = [x.strip() for x in v.split(",")]
            return email
        except Exception as e:
            print(f"AI analysis error: {e}")
            return self._rule_based(email)

    def _rule_based(self, email: EmailData) -> EmailData:
        b, s = email.body.lower(), email.subject.lower()
        if any(w in b or w in s for w in ["meeting","project","deadline","task"]):
            email.category = "work"
        elif any(w in b or w in s for w in ["urgent","asap","critical"]):
            email.category = "urgent"
        elif any(w in b or w in s for w in ["unsubscribe","newsletter","promotion"]):
            email.category = "newsletter"
        else:
            email.category = "personal"

        if email.is_important or email.category == "urgent":
            email.priority_score = 9
        elif email.category == "work":
            email.priority_score = 7
        elif email.category == "newsletter":
            email.priority_score = 3
        else:
            email.priority_score = 5

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
                "e1": conflict.event1.summary,
                "t1": conflict.event1.start_time.strftime("%B %d at %I:%M %p"),
                "e2": conflict.event2.summary,
                "t2": conflict.event2.start_time.strftime("%B %d at %I:%M %p"),
                "ov": conflict.overlap_minutes,
                "alt": alt_text,
            })
            return resp.content
        except Exception as e:
            print(f"Error generating email: {e}")
            return self._template_email(conflict, alts)

    def _template_email(self, conflict: ConflictInfo,
                         alts: List[Tuple[datetime, datetime]]) -> str:
        body = (
            f"Subject: Calendar Conflict - {conflict.event1.summary} and {conflict.event2.summary}\n\n"
            f"Dear Team,\n\nI wanted to flag a scheduling conflict.\n\n"
            f"CONFLICT DETAILS:\n"
            f"Meeting 1: {conflict.event1.summary}\n"
            f"  {conflict.event1.start_time.strftime('%B %d, %Y at %I:%M %p')} - "
            f"{conflict.event1.end_time.strftime('%I:%M %p')}\n\n"
            f"Meeting 2: {conflict.event2.summary}\n"
            f"  {conflict.event2.start_time.strftime('%B %d, %Y at %I:%M %p')} - "
            f"{conflict.event2.end_time.strftime('%I:%M %p')}\n\n"
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

    def fetch_emails(self, query: str = "", max_results: int = 50) -> List[EmailData]:
        self.emails_cache = self.gmail.get_emails(query, max_results)
        return self.emails_cache

    def analyze_emails(self, emails: Optional[List[EmailData]] = None) -> List[EmailData]:
        target = emails or self.emails_cache
        analyzed = [self.analyzer.analyze_email(e) for e in target]
        if not emails:
            self.emails_cache = analyzed
        return analyzed

    def categorize_emails_ai(self, emails=None):
        return self.analyze_emails(emails)

    def fetch_calendar_events(self, days_ahead: int = 30) -> List[CalendarEvent]:
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

    def generate_conflict_resolution(self, conflict: ConflictInfo,
                                     free_slots=None) -> str:
        if free_slots is None:
            free_slots = self.find_free_slots(
                duration_minutes=conflict.event1.duration_minutes, days_ahead=14
            )
        alts = [
            (s["start"], s["end"]) if isinstance(s, dict) else s
            for s in free_slots[:5]
        ]
        return self.analyzer.generate_conflict_email(conflict, alts)

    def generate_conflict_email(self, conflict, free_slots=None):
        return self.generate_conflict_resolution(conflict, free_slots)

    def get_conflict_recipients(self, conflict: ConflictInfo) -> List[str]:
        recipients: set = set()
        for ev in (conflict.event1, conflict.event2):
            if ev.organizer: recipients.add(ev.organizer)
            if ev.attendees: recipients.update(ev.attendees)
        return [r for r in recipients if r and r.strip()]

    def find_calendar_invitation_email(self, event: CalendarEvent):
        try:
            emails = self.gmail.get_emails(query=f'subject:"{event.summary}"', max_results=20)
            for e in emails:
                if e.has_calendar_event:
                    if event.organizer and event.organizer.lower() in e.sender_email.lower():
                        return e
                    if event.summary.lower() in e.subject.lower():
                        return e
        except Exception:
            pass
        return None

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
            emails   = self.fetch_emails(max_results=50)
            result["emails_fetched"]  = len(emails)
            analyzed = self.analyze_emails(emails)
            result["emails_analyzed"] = len(analyzed)
            events   = self.fetch_calendar_events(days_ahead=30)
            result["events_fetched"]  = len(events)
            conflicts = self.detect_conflicts(events)
            result["conflicts_found"] = len(conflicts)

            s = []
            urgent = [e for e in analyzed if e.priority_score and e.priority_score >= 8]
            if urgent: s.append(f"You have {len(urgent)} high-priority emails requiring attention")
            unread_imp = [e for e in analyzed if e.is_unread and e.is_important]
            if unread_imp: s.append(f"You have {len(unread_imp)} unread important emails")
            if conflicts: s.append(f"Found {len(conflicts)} calendar conflicts that need resolution")
            today_ev = [e for e in events if e.start_time.date() == datetime.now().date()]
            if today_ev: s.append(f"You have {len(today_ev)} events scheduled for today")
            result["suggestions"] = s

            for c in conflicts[:3]:
                self.generate_conflict_resolution(c)
                result["drafts_created"] += 1
        except Exception as e:
            result["status"] = "error"
            result["error"]  = str(e)
        return result


# ---------------------------------------------------------------------------
# STREAMLIT APP
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Ambient Email Assistant", page_icon="📬", layout="wide")

    creds = handle_google_auth()
    if creds is None:
        st.stop()

    with st.sidebar:
        st.success("Connected to Google")
        if st.button("Sign out"):
            st.session_state.pop("_gcreds", None)
            st.query_params.clear()
            st.rerun()
        st.markdown("---")
        openai_key = st.text_input("OpenAI API key (optional)", type="password",
                                   help="Enables AI email categorisation")

    if "assistant" not in st.session_state:
        st.session_state["assistant"] = EnhancedEmailAssistant()

    assistant: EnhancedEmailAssistant = st.session_state["assistant"]
    assistant.inject_credentials(creds)
    if openai_key:
        assistant.initialize_llm(api_key=openai_key)

    st.title("📬 Ambient Email Assistant")

    tab_emails, tab_calendar, tab_agent = st.tabs(["📧 Emails", "📅 Calendar", "🤖 Agent"])

    with tab_emails:
        st.subheader("Your Emails")
        col_q, col_n, col_btn = st.columns([3, 1, 1])
        with col_q:
            query = st.text_input("Search query", placeholder="is:unread label:important")
        with col_n:
            max_results = st.number_input("Max", 1, 200, 20)
        with col_btn:
            st.write("")
            fetch_btn = st.button("Fetch", use_container_width=True)

        if fetch_btn:
            with st.spinner("Fetching emails…"):
                emails = assistant.fetch_emails(query=query, max_results=int(max_results))
            st.success(f"Fetched {len(emails)} emails")

        if assistant.emails_cache:
            if st.button("Analyse with AI"):
                with st.spinner("Analysing…"):
                    assistant.analyze_emails()
                st.success("Done")

            for email in assistant.emails_cache[:50]:
                badge = "🔴" if email.is_unread else "⚪"
                with st.expander(f"{badge} {email.subject} — {email.sender}"):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Category",  email.category or "—")
                    c2.metric("Priority",  f"{email.priority_score}/10" if email.priority_score else "—")
                    c3.metric("Sentiment", email.sentiment or "—")
                    c4.metric("Date",      email.timestamp.strftime("%b %d"))
                    st.text_area("Body", email.body[:500], height=100, key=f"b_{email.id}")
                    if email.action_items:
                        st.markdown("**Actions:** " + " • ".join(email.action_items))

    with tab_calendar:
        st.subheader("Calendar & Conflicts")
        days = st.slider("Days ahead", 1, 90, 30)
        if st.button("Fetch Calendar"):
            with st.spinner("Fetching…"):
                events    = assistant.fetch_calendar_events(days_ahead=days)
                conflicts = assistant.detect_conflicts()
            st.success(f"{len(events)} events, {len(conflicts)} conflicts")

        if assistant.events_cache:
            for ev in assistant.events_cache[:20]:
                st.write(f"- **{ev.summary}** — {ev.start_time.strftime('%b %d %I:%M %p')} → {ev.end_time.strftime('%I:%M %p')}")

        if assistant.conflicts_cache:
            st.markdown(f"### ⚠️ {len(assistant.conflicts_cache)} Conflict(s)")
            for i, conflict in enumerate(assistant.conflicts_cache):
                with st.expander(str(conflict)):
                    st.write(f"Overlap: {conflict.overlap_minutes} min")
                    if st.button("Generate Resolution Email", key=f"r_{i}"):
                        with st.spinner("Generating…"):
                            body = assistant.generate_conflict_resolution(conflict)
                        st.text_area("Draft", body, height=300, key=f"d_{i}")
                    if st.button("Find Free Slots", key=f"f_{i}"):
                        with st.spinner("Scanning…"):
                            slots = assistant.find_free_slots(
                                duration_minutes=conflict.event1.duration_minutes, days_ahead=14
                            )
                        for slot in slots[:5]:
                            st.write(f"- {slot['start'].strftime('%b %d %I:%M %p')} — {slot['end'].strftime('%I:%M %p')}")

    with tab_agent:
        st.subheader("🤖 Ambient Agent")
        st.write("Fetches emails, analyses them, checks conflicts, and surfaces suggestions.")
        if st.button("Run Agent", type="primary"):
            with st.spinner("Running…"):
                result = assistant.run_ambient_agent()
            if result["status"] == "success":
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Emails fetched",  result["emails_fetched"])
                c2.metric("Emails analysed", result["emails_analyzed"])
                c3.metric("Events",          result["events_fetched"])
                c4.metric("Conflicts",       result["conflicts_found"])
                for s in result["suggestions"]:
                    st.info(s)
            else:
                st.error(f"Error: {result.get('error')}")


if __name__ == "__main__":
    main()
