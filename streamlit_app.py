"""
Ambient Email Assistant - Enhanced Version
AI-powered email and calendar management with LangGraph workflows
Compatible with Streamlit Cloud (browser-based OAuth, no credentials.json needed)
"""

import os
import pickle
import base64
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from email.mime.text import MIMEText
import re

# Streamlit
import streamlit as st

# Google API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# LangChain imports
try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import ChatPromptTemplate
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    print("Warning: LangChain not available. AI features will be disabled.")

# LangGraph imports
try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.sqlite import SqliteSaver
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    print("Warning: LangGraph not available. Workflow features will be limited.")

# Environment variables
from dotenv import load_dotenv
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events'
]

# Streamlit Cloud app URL — used as the OAuth redirect URI
APP_URL = "https://inboxai.streamlit.app"
REDIRECT_URI = APP_URL  # Google will redirect here after user grants access

MEMORY_DIR = 'memory'
MEMORY_FILE = os.path.join(MEMORY_DIR, 'conversation_memory.pkl')


# ============================================================================
# OAUTH HELPERS (Streamlit Cloud — no credentials.json, no local server)
# ============================================================================

def _get_client_config() -> dict:
    """
    Build the OAuth client config dict from Streamlit secrets.
    Falls back to environment variables so local dev still works.

    Expected Streamlit secret keys (under [google_credentials]):
        client_id, client_secret
    """
    try:
        client_id     = st.secrets["google_credentials"]["client_id"]
        client_secret = st.secrets["google_credentials"]["client_secret"]
    except (KeyError, FileNotFoundError):
        # Fallback: env vars (useful for local testing with a .env file)
        client_id     = os.getenv("GOOGLE_CLIENT_ID", "")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        st.error(
            "❌ Google OAuth credentials not found.  \n"
            "Add `client_id` and `client_secret` under `[google_credentials]` "
            "in your Streamlit Cloud secrets."
        )
        st.stop()

    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def _generate_code_verifier() -> str:
    """Generate a cryptographically random PKCE code_verifier (43-128 chars)."""
    import secrets
    return secrets.token_urlsafe(96)  # 128 URL-safe chars


def get_oauth_flow(state: Optional[str] = None) -> Flow:
    """Return a configured Flow, optionally restoring a previous state."""
    return Flow.from_client_config(
        _get_client_config(),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        state=state,
    )


def handle_google_auth() -> Optional[Credentials]:
    """
    Browser-based OAuth for Streamlit Cloud.

    Key design decisions:
    - We explicitly generate the code_verifier OURSELVES and save it to
      session_state. This is the only reliable way to survive the Streamlit
      rerun that happens when Google redirects back with ?code=.
    - We save `state` to session_state and reconstruct the Flow with the same
      state on the callback rerun, so oauthlib's state check passes.
    - We pass authorization_response (full URL) to fetch_token which is more
      robust than passing just the code.
    """
    from urllib.parse import urlencode

    # ── Already authenticated in this session? ──────────────────────────────
    if "google_creds_token" in st.session_state:
        creds = _creds_from_session()
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _save_creds_to_session(creds)
                return creds
            except Exception:
                pass  # fall through to re-auth

    # ── Returning from Google with ?code= in the URL ─────────────────────────
    params = dict(st.query_params)
    if "code" in params:
        try:
            callback_url   = f"{REDIRECT_URI}?{urlencode(params)}"
            saved_state    = st.session_state.pop("oauth_state",         None)
            code_verifier  = st.session_state.pop("oauth_code_verifier", None)

            flow = get_oauth_flow(state=saved_state)

            # Pass the code_verifier we saved before the redirect.
            # Google requires it because we sent a code_challenge in the
            # auth URL — if we don't send the verifier back we get
            # "Missing code verifier".
            fetch_kwargs = {"authorization_response": callback_url}
            if code_verifier:
                fetch_kwargs["code_verifier"] = code_verifier

            flow.fetch_token(**fetch_kwargs)

            creds = flow.credentials
            _save_creds_to_session(creds)
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"OAuth token exchange failed: {e}")
            # Wipe stale session keys so the user can start fresh
            for k in ("oauth_state", "oauth_code_verifier"):
                st.session_state.pop(k, None)
            if st.button("🔄 Try again"):
                st.rerun()
        return None

    # ── Not authenticated yet — show login UI ────────────────────────────────
    # Generate our OWN code_verifier before creating the flow so we control
    # it completely. Pass it to authorization_url() so the library builds the
    # matching code_challenge from it.
    code_verifier = _generate_code_verifier()

    flow = get_oauth_flow()
    auth_url, state = flow.authorization_url(
        prompt="consent",
        access_type="offline",
        include_granted_scopes="true",
        code_verifier=code_verifier,   # ← tells oauthlib to add code_challenge
    )

    # Persist both state and verifier so the callback rerun can find them
    st.session_state["oauth_state"]         = state
    st.session_state["oauth_code_verifier"] = code_verifier

    st.markdown(
        """
        <div style='text-align:center; padding: 60px 20px;'>
            <h1>📬 Ambient Email Assistant</h1>
            <p style='font-size:18px; color:#555;'>
                Connect your Google account to get started.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([2, 1, 2])
    with col2:
        st.link_button("🔐 Sign in with Google", auth_url, use_container_width=True)

    st.info(
        "This app uses read/write access to Gmail and Google Calendar "
        "to analyse emails, detect scheduling conflicts, and draft replies."
    )
    return None


def _save_creds_to_session(creds: Credentials):
    """Persist credentials fields (JSON-serialisable) in session_state."""
    st.session_state["google_creds_token"] = {
        "token":         creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri":     creds.token_uri,
        "client_id":     creds.client_id,
        "client_secret": creds.client_secret,
        "scopes":        list(creds.scopes) if creds.scopes else SCOPES,
        "expiry":        creds.expiry.isoformat() if creds.expiry else None,
    }


def _creds_from_session() -> Optional[Credentials]:
    """Re-hydrate a Credentials object from session_state."""
    data = st.session_state.get("google_creds_token")
    if not data:
        return None
    expiry = datetime.fromisoformat(data["expiry"]) if data.get("expiry") else None
    return Credentials(
        token=data["token"],
        refresh_token=data["refresh_token"],
        token_uri=data["token_uri"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data["scopes"],
        expiry=expiry,
    )


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class EmailData:
    """Email data model"""
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

    # AI-enhanced fields
    category: Optional[str] = None
    priority_score: Optional[int] = None
    sentiment: Optional[str] = None
    extracted_dates: List[str] = field(default_factory=list)
    action_items: List[str] = field(default_factory=list)

    def __str__(self):
        return f"Email(subject='{self.subject}', from='{self.sender}', date={self.timestamp})"


@dataclass
class CalendarEvent:
    """Calendar event data model"""
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
        object.__setattr__(self, 'start', self.start_time)
        object.__setattr__(self, 'end', self.end_time)
        object.__setattr__(self, 'title', self.summary)

    @property
    def duration_minutes(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() / 60)

    def __str__(self):
        return f"Event('{self.summary}', {self.start_time} - {self.end_time})"


@dataclass
class ConflictInfo:
    """Calendar conflict information"""
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
        return f"Conflict: '{self.event1.summary}' vs '{self.event2.summary}' ({self.overlap_minutes} min)"


# ============================================================================
# GMAIL SERVICE
# ============================================================================

class GmailService:
    """Gmail API service wrapper"""

    def __init__(self):
        self.service = None
        self.creds = None

    def inject_credentials(self, creds: Credentials) -> bool:
        """Receive credentials from browser OAuth — no file I/O."""
        try:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            self.creds = creds
            self.service = build('gmail', 'v1', credentials=self.creds)
            return True
        except Exception as e:
            print(f"GmailService.inject_credentials: {e}")
            return False

    def get_emails(self, query: str = "", max_results: int = 50) -> List[EmailData]:
        if not self.service:
            return []
        try:
            results = self.service.users().messages().list(
                userId='me', q=query, maxResults=max_results
            ).execute()
            messages = results.get('messages', [])
            emails = []
            for msg in messages:
                email = self._parse_message(msg['id'])
                if email:
                    emails.append(email)
            return emails
        except HttpError as error:
            print(f'Gmail API error: {error}')
            return []

    def _parse_message(self, msg_id: str) -> Optional[EmailData]:
        try:
            message = self.service.users().messages().get(
                userId='me', id=msg_id, format='full'
            ).execute()

            headers = message['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            sender  = next((h['value'] for h in headers if h['name'].lower() == 'from'),    'Unknown')
            recipient = next((h['value'] for h in headers if h['name'].lower() == 'to'),    'Unknown')
            date_str  = next((h['value'] for h in headers if h['name'].lower() == 'date'),  None)

            sender_email = self._extract_email_address(sender)
            timestamp    = self._parse_date(date_str) if date_str else datetime.now()
            body         = self._get_message_body(message)
            snippet      = message.get('snippet', '')
            labels       = message.get('labelIds', [])
            is_unread    = 'UNREAD' in labels
            is_important = 'IMPORTANT' in labels or 'STARRED' in labels
            has_attachment    = self._has_attachments(message)
            has_calendar_event = self._detect_calendar_event(body, subject)

            return EmailData(
                id=msg_id,
                thread_id=message['threadId'],
                subject=subject,
                sender=sender,
                recipient=recipient,
                timestamp=timestamp,
                body=body,
                snippet=snippet,
                is_unread=is_unread,
                is_important=is_important,
                has_attachment=has_attachment,
                has_calendar_event=has_calendar_event,
                sender_email=sender_email,
                labels=labels,
            )
        except Exception as e:
            print(f"Error parsing message {msg_id}: {e}")
            return None

    def _detect_calendar_event(self, body: str, subject: str) -> bool:
        keywords = [
            'meeting', 'calendar', 'event', 'invited', 'invitation',
            'scheduled', 'appointment', 'conference', 'zoom', 'teams',
            'when:', 'where:', 'time:', 'date:', 'rsvp',
        ]
        body_lower    = body.lower()
        subject_lower = subject.lower()
        return any(kw in body_lower or kw in subject_lower for kw in keywords)

    def _extract_email_address(self, sender: str) -> str:
        match = re.search(r'<([^>]+)>', sender)
        if match:
            return match.group(1)
        match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', sender)
        if match:
            return match.group(0)
        return sender

    def _get_message_body(self, message: Dict) -> str:
        try:
            parts = message['payload'].get('parts', [])
            if not parts:
                body_data = message['payload'].get('body', {}).get('data', '')
                if body_data:
                    return base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
            for part in parts:
                if part['mimeType'] == 'text/plain':
                    body_data = part.get('body', {}).get('data', '')
                    if body_data:
                        return base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
            for part in parts:
                if part['mimeType'] == 'text/html':
                    body_data = part.get('body', {}).get('data', '')
                    if body_data:
                        html = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                        return re.sub('<[^<]+?>', '', html)
            return message.get('snippet', '')
        except Exception as e:
            print(f"Error extracting body: {e}")
            return message.get('snippet', '')

    def _has_attachments(self, message: Dict) -> bool:
        parts = message['payload'].get('parts', [])
        return any(part.get('filename') for part in parts)

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
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            send_message = {'raw': raw_message}
            if thread_id:
                send_message['threadId'] = thread_id
            self.service.users().messages().send(userId='me', body=send_message).execute()
            return True
        except HttpError as error:
            print(f'Error sending email: {error}')
            return False

    def create_draft(self, to: str, subject: str, body: str) -> bool:
        if not self.service:
            return False
        try:
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            self.service.users().drafts().create(
                userId='me',
                body={'message': {'raw': raw_message}}
            ).execute()
            return True
        except HttpError as error:
            print(f'Error creating draft: {error}')
            return False


# ============================================================================
# CALENDAR SERVICE
# ============================================================================

class CalendarService:
    """Google Calendar API service wrapper"""

    def __init__(self):
        self.service = None
        self.creds = None

    def inject_credentials(self, creds: Credentials) -> bool:
        """Receive credentials from browser OAuth — no file I/O."""
        try:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            self.creds = creds
            self.service = build('calendar', 'v3', credentials=self.creds)
            return True
        except Exception as e:
            print(f"CalendarService.inject_credentials: {e}")
            return False

    def get_events(self, days_ahead: int = 30) -> List[CalendarEvent]:
        if not self.service:
            return []
        try:
            now      = datetime.utcnow()
            time_min = now.isoformat() + 'Z'
            time_max = (now + timedelta(days=days_ahead)).isoformat() + 'Z'
            result   = self.service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                maxResults=100,
                singleEvents=True,
                orderBy='startTime',
            ).execute()
            return [e for e in (self._parse_event(ev) for ev in result.get('items', [])) if e]
        except HttpError as error:
            print(f'Calendar API error: {error}')
            return []

    def _parse_event(self, event: Dict) -> Optional[CalendarEvent]:
        try:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end   = event['end'].get('dateTime',   event['end'].get('date'))
            start_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
            end_time   = datetime.fromisoformat(end.replace('Z',   '+00:00'))
            attendees  = [a.get('email', '') for a in event.get('attendees', [])]
            return CalendarEvent(
                id=event['id'],
                summary=event.get('summary', 'No Title'),
                start_time=start_time,
                end_time=end_time,
                description=event.get('description'),
                location=event.get('location'),
                attendees=attendees,
                organizer=event.get('organizer', {}).get('email'),
                status=event.get('status', 'confirmed'),
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
                        event1=e1,
                        event2=e2,
                        overlap_start=max(e1.start_time, e2.start_time),
                        overlap_end=min(e1.end_time, e2.end_time),
                    ))
        return conflicts

    def find_free_slots(self, events: List[CalendarEvent],
                        duration_minutes: int = 60,
                        days_ahead: int = 7) -> List[Dict[str, Any]]:
        free_slots = []
        try:
            now        = datetime.now()
            search_end = now + timedelta(days=days_ahead)

            # Build a list of (start, end) tuples for blocking
            future_events = []
            for ev in (events or []):
                s = ev.start_time.replace(tzinfo=None) if ev.start_time.tzinfo else ev.start_time
                e = ev.end_time.replace(tzinfo=None)   if ev.end_time.tzinfo   else ev.end_time
                if e > now and s < search_end:
                    future_events.append((s, e))

            # Start scanning from the next 30-min boundary inside business hours
            if now.hour >= 20:
                current = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
            elif now.hour < 8:
                current = now.replace(hour=8, minute=0, second=0, microsecond=0)
            else:
                mins = (now.minute // 30 + 1) * 30
                if mins >= 60:
                    current = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                else:
                    current = now.replace(minute=mins, second=0, microsecond=0)

            iterations = 0
            while current < search_end and iterations < 1000:
                iterations += 1
                slot_end = current + timedelta(minutes=duration_minutes)

                if current.hour < 8:
                    current = current.replace(hour=8, minute=0, second=0, microsecond=0)
                    continue
                if current.hour >= 20:
                    current = (current + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
                    continue

                is_free = all(
                    not (current < ev_end and slot_end > ev_start)
                    for ev_start, ev_end in future_events
                )

                if is_free and current > now:
                    free_slots.append({
                        'start': current,
                        'end': slot_end,
                        'duration_minutes': duration_minutes,
                    })

                if len(free_slots) >= 20:
                    break

                current += timedelta(minutes=30)

            return free_slots
        except Exception as e:
            print(f"Error finding free slots: {e}")
            return []


# ============================================================================
# AI ANALYZER
# ============================================================================

class AIAnalyzer:
    """AI-powered email and calendar analysis"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.llm = None
        if LANGCHAIN_AVAILABLE and self.api_key:
            try:
                self.llm = ChatOpenAI(
                    model=os.getenv('LLM_MODEL', 'gpt-4'),
                    temperature=float(os.getenv('LLM_TEMPERATURE', '0.7')),
                    api_key=self.api_key,
                )
            except Exception as e:
                print(f"Error initializing LLM: {e}")

    def analyze_email(self, email: EmailData) -> EmailData:
        if not self.llm:
            return self._rule_based_analysis(email)
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are an email analysis assistant. Analyse the email and provide:
1. Category (work, personal, urgent, spam, newsletter)
2. Priority score (0-10, where 10 is most important)
3. Sentiment (positive, neutral, negative)
4. Extracted dates (if any)
5. Action items (if any)

Respond in this exact format:
Category: <category>
Priority: <score>
Sentiment: <sentiment>
Dates: <comma-separated dates or "none">
Actions: <comma-separated actions or "none">
"""),
                ("human", "Subject: {subject}\nFrom: {sender}\nBody: {body}"),
            ])
            chain    = prompt | self.llm
            response = chain.invoke({
                "subject": email.subject,
                "sender":  email.sender,
                "body":    email.body[:1000],
            })
            for line in response.content.strip().split('\n'):
                if line.startswith('Category:'):
                    email.category = line.split(':', 1)[1].strip().lower()
                elif line.startswith('Priority:'):
                    try:
                        email.priority_score = int(line.split(':', 1)[1].strip())
                    except Exception:
                        email.priority_score = 5
                elif line.startswith('Sentiment:'):
                    email.sentiment = line.split(':', 1)[1].strip().lower()
                elif line.startswith('Dates:'):
                    dates = line.split(':', 1)[1].strip()
                    if dates.lower() != 'none':
                        email.extracted_dates = [d.strip() for d in dates.split(',')]
                elif line.startswith('Actions:'):
                    actions = line.split(':', 1)[1].strip()
                    if actions.lower() != 'none':
                        email.action_items = [a.strip() for a in actions.split(',')]
            return email
        except Exception as e:
            print(f"AI analysis error: {e}")
            return self._rule_based_analysis(email)

    def _rule_based_analysis(self, email: EmailData) -> EmailData:
        body_lower    = email.body.lower()
        subject_lower = email.subject.lower()

        if any(w in body_lower or w in subject_lower for w in ['meeting', 'project', 'deadline', 'task']):
            email.category = 'work'
        elif any(w in body_lower or w in subject_lower for w in ['urgent', 'asap', 'important', 'critical']):
            email.category = 'urgent'
        elif any(w in body_lower or w in subject_lower for w in ['unsubscribe', 'newsletter', 'promotion']):
            email.category = 'newsletter'
        else:
            email.category = 'personal'

        if email.is_important or email.category == 'urgent':
            email.priority_score = 9
        elif email.category == 'work':
            email.priority_score = 7
        elif email.category == 'newsletter':
            email.priority_score = 3
        else:
            email.priority_score = 5

        pos = sum(1 for w in ['thank', 'great', 'excellent', 'congratulations'] if w in body_lower)
        neg = sum(1 for w in ['sorry', 'problem', 'issue', 'error', 'cancel'] if w in body_lower)
        email.sentiment = 'positive' if pos > neg else ('negative' if neg > pos else 'neutral')
        return email

    def generate_conflict_resolution_email(self, conflict: ConflictInfo,
                                            alternative_times: List[Tuple[datetime, datetime]]) -> str:
        if not self.llm:
            return self._template_conflict_email(conflict, alternative_times)
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are a professional email assistant. Write a polite email to resolve a calendar conflict.
Include: acknowledgment, conflict details, suggested alternatives, request for confirmation.
Keep it professional and concise."""),
                ("human", """Conflict:
Meeting 1: {event1_summary} ({event1_time})
Meeting 2: {event2_summary} ({event2_time})
Overlap: {overlap_minutes} minutes

Alternative times:
{alternatives}

Write the email:"""),
            ])
            alt_text = "\n".join([
                f"- {s.strftime('%B %d, %Y at %I:%M %p')} - {e.strftime('%I:%M %p')}"
                for s, e in alternative_times[:3]
            ])
            chain    = prompt | self.llm
            response = chain.invoke({
                "event1_summary":  conflict.event1.summary,
                "event1_time":     conflict.event1.start_time.strftime('%B %d at %I:%M %p'),
                "event2_summary":  conflict.event2.summary,
                "event2_time":     conflict.event2.start_time.strftime('%B %d at %I:%M %p'),
                "overlap_minutes": conflict.overlap_minutes,
                "alternatives":    alt_text,
            })
            return response.content
        except Exception as e:
            print(f"Error generating email: {e}")
            return self._template_conflict_email(conflict, alternative_times)

    def _template_conflict_email(self, conflict: ConflictInfo,
                                  alternative_times: List[Tuple[datetime, datetime]]) -> str:
        body = (
            f"Subject: Calendar Conflict — {conflict.event1.summary} and {conflict.event2.summary}\n\n"
            f"Dear Team,\n\n"
            f"I wanted to flag a scheduling conflict that has come up.\n\n"
            f"CONFLICT DETAILS:\n"
            f"• Meeting 1: {conflict.event1.summary}\n"
            f"  Time: {conflict.event1.start_time.strftime('%B %d, %Y at %I:%M %p')} — "
            f"{conflict.event1.end_time.strftime('%I:%M %p')}\n\n"
            f"• Meeting 2: {conflict.event2.summary}\n"
            f"  Time: {conflict.event2.start_time.strftime('%B %d, %Y at %I:%M %p')} — "
            f"{conflict.event2.end_time.strftime('%I:%M %p')}\n\n"
            f"These meetings overlap by {conflict.overlap_minutes} minutes.\n\n"
            f"ALTERNATIVE TIMES:\n"
        )
        for i, (s, e) in enumerate(alternative_times[:3], 1):
            body += f"{i}. {s.strftime('%B %d, %Y at %I:%M %p')} — {e.strftime('%I:%M %p')}\n"
        body += (
            "\nCould you please let me know which time works best, "
            "or suggest another?\n\nThank you for your flexibility.\n\nBest regards\n"
        )
        return body


# ============================================================================
# ENHANCED EMAIL ASSISTANT
# ============================================================================

class EnhancedEmailAssistant:
    """Main assistant class — no file-based auth, credentials injected externally."""

    def __init__(self):
        self.gmail    = GmailService()
        self.calendar = CalendarService()
        self.analyzer = AIAnalyzer()
        self.llm      = None

        self.conversation_memory: List = []
        self._load_memory()

        self.emails_cache:    List[EmailData]    = []
        self.events_cache:    List[CalendarEvent] = []
        self.conflicts_cache: List[ConflictInfo]  = []

    # ── Auth ─────────────────────────────────────────────────────────────────

    def inject_credentials(self, creds: Credentials) -> bool:
        """Inject Google OAuth credentials into both services."""
        ok_gmail    = self.gmail.inject_credentials(creds)
        ok_calendar = self.calendar.inject_credentials(creds)
        return ok_gmail and ok_calendar

    # ── LLM ──────────────────────────────────────────────────────────────────

    def initialize_llm(self, api_key: Optional[str] = None) -> bool:
        if api_key:
            self.analyzer = AIAnalyzer(api_key=api_key)
            self.llm      = self.analyzer.llm
        return self.llm is not None

    # ── Memory ───────────────────────────────────────────────────────────────

    def _load_memory(self):
        os.makedirs(MEMORY_DIR, exist_ok=True)
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, 'rb') as f:
                    self.conversation_memory = pickle.load(f)
            except Exception:
                self.conversation_memory = []

    def _save_memory(self):
        try:
            with open(MEMORY_FILE, 'wb') as f:
                pickle.dump(self.conversation_memory[-100:], f)
        except Exception as e:
            print(f"Error saving memory: {e}")

    # ── Email ─────────────────────────────────────────────────────────────────

    def fetch_emails(self, query: str = "", max_results: int = 50) -> List[EmailData]:
        self.emails_cache = self.gmail.get_emails(query, max_results)
        return self.emails_cache

    def analyze_emails(self, emails: Optional[List[EmailData]] = None) -> List[EmailData]:
        target   = emails or self.emails_cache
        analyzed = [self.analyzer.analyze_email(e) for e in target]
        if not emails:
            self.emails_cache = analyzed
        return analyzed

    def categorize_emails_ai(self, emails: Optional[List[EmailData]] = None) -> List[EmailData]:
        return self.analyze_emails(emails)

    # ── Calendar ──────────────────────────────────────────────────────────────

    def fetch_calendar_events(self, days_ahead: int = 30) -> List[CalendarEvent]:
        self.events_cache = self.calendar.get_events(days_ahead)
        return self.events_cache

    def detect_conflicts(self, events: Optional[List[CalendarEvent]] = None) -> List[ConflictInfo]:
        self.conflicts_cache = self.calendar.find_conflicts(events or self.events_cache)
        return self.conflicts_cache

    def find_free_slots(self, *args, **kwargs) -> List[Dict[str, Any]]:
        """Flexible signature — see docstring for calling patterns."""
        events           = kwargs.get('events', None)
        duration_minutes = kwargs.get('duration_minutes', 60)
        days_ahead       = kwargs.get('days_ahead', 7)
        refresh_events   = kwargs.get('refresh_events', True)

        if len(args) >= 1:
            first = args[0]
            if isinstance(first, list):
                events = first
                if len(args) >= 2 and isinstance(args[1], int): duration_minutes = args[1]
                if len(args) >= 3 and isinstance(args[2], int): days_ahead       = args[2]
            elif isinstance(first, int):
                duration_minutes = first
                if len(args) >= 2 and isinstance(args[1], int): days_ahead = args[1]
                if len(args) >= 3 and isinstance(args[2], list): events    = args[2]

        if not isinstance(duration_minutes, int): duration_minutes = 60
        if not isinstance(days_ahead, int):       days_ahead       = 7

        if events is None and refresh_events:
            self.fetch_calendar_events(days_ahead=days_ahead)
            events = self.events_cache
        elif events is None:
            events = self.events_cache

        return self.calendar.find_free_slots(events, duration_minutes, days_ahead)

    # ── Conflict resolution ───────────────────────────────────────────────────

    def generate_conflict_resolution(self, conflict: ConflictInfo,
                                     free_slots: Optional[List[Dict[str, Any]]] = None) -> str:
        if free_slots is None:
            free_slots = self.find_free_slots(
                duration_minutes=conflict.event1.duration_minutes, days_ahead=14
            )
        alternative_times = [
            (s['start'], s['end']) if isinstance(s, dict) else s
            for s in free_slots[:5]
        ]
        return self.analyzer.generate_conflict_resolution_email(conflict, alternative_times)

    def generate_conflict_email(self, conflict: ConflictInfo,
                                free_slots: Optional[List[Dict[str, Any]]] = None) -> str:
        return self.generate_conflict_resolution(conflict, free_slots)

    def get_conflict_recipients(self, conflict: ConflictInfo) -> List[str]:
        recipients: set = set()
        for ev in (conflict.event1, conflict.event2):
            if ev.organizer: recipients.add(ev.organizer)
            if ev.attendees: recipients.update(ev.attendees)
        return [r for r in recipients if r and r.strip()]

    def find_calendar_invitation_email(self, event: CalendarEvent) -> Optional[EmailData]:
        try:
            emails = self.gmail.get_emails(query=f'subject:"{event.summary}"', max_results=20)
            for email in emails:
                if email.has_calendar_event:
                    if event.organizer and event.organizer.lower() in email.sender_email.lower():
                        return email
                    if event.summary.lower() in email.subject.lower():
                        return email
            return None
        except Exception as e:
            print(f"Error finding invitation email: {e}")
            return None

    def get_emails_by_date(self, target_date: datetime) -> List[EmailData]:
        try:
            date_str = target_date.strftime('%Y/%m/%d')
            return self.gmail.get_emails(
                query=f'after:{date_str} before:{date_str}', max_results=100
            )
        except Exception as e:
            print(f"Error fetching emails by date: {e}")
            return []

    def send_conflict_resolution_email(self, conflict: ConflictInfo,
                                       free_slots: Optional[List[Dict[str, Any]]] = None,
                                       custom_recipients: Optional[List[str]] = None,
                                       reply_to_invitation: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            'success': False, 'recipients': [], 'subject': '',
            'error': None, 'method': 'draft', 'thread_id': None, 'email_stats': {}
        }
        try:
            base_body = self.generate_conflict_resolution(conflict, free_slots)

            invitation_email = None
            if reply_to_invitation:
                invitation_email = (
                    self.find_calendar_invitation_email(conflict.event1)
                    or self.find_calendar_invitation_email(conflict.event2)
                )

            conflict_date  = conflict.event1.start_time
            emails_on_day  = self.get_emails_by_date(conflict_date)
            email_count    = len(emails_on_day)

            email_body  = base_body + "\n\n---\n"
            email_body += f"📊 Email Statistics:\n"
            email_body += f"• Date: {conflict_date.strftime('%A, %B %d, %Y')}\n"
            email_body += f"• Total emails received on this day: {email_count}\n"
            if invitation_email:
                email_body += f"• This is in reply to: \"{invitation_email.subject}\"\n"
                email_body += f"• Original invitation from: {invitation_email.sender}\n"

            result['email_stats'] = {
                'date': conflict_date.strftime('%Y-%m-%d'),
                'count': email_count,
                'emails': [
                    {'subject': e.subject, 'from': e.sender, 'time': e.timestamp.strftime('%I:%M %p')}
                    for e in emails_on_day[:5]
                ],
            }

            if custom_recipients:
                recipients = custom_recipients
            elif invitation_email:
                recipients = [invitation_email.sender_email]
            else:
                recipients = self.get_conflict_recipients(conflict)

            if not recipients:
                result['error'] = "No recipients found. Please specify recipients manually."
                return result

            if invitation_email:
                subject   = f"Re: {invitation_email.subject} — Calendar Conflict Resolution"
                thread_id = invitation_email.thread_id
                result['thread_id'] = thread_id
                result['method']    = 'reply'
            else:
                subject   = f"Calendar Conflict: {conflict.event1.summary} & {conflict.event2.summary}"
                thread_id = None

            sent_to = []
            for recipient in recipients:
                if invitation_email and thread_id:
                    if self.send_email(recipient, subject, email_body, thread_id=thread_id):
                        sent_to.append(recipient)
                        result['method'] = 'sent_as_reply'
                else:
                    if self.create_draft(recipient, subject, email_body):
                        sent_to.append(recipient)

            result['success']    = len(sent_to) > 0
            result['recipients'] = sent_to
            result['subject']    = subject
            result['message']    = (
                f"{'Sent reply' if result['method'] == 'sent_as_reply' else 'Draft created'} "
                f"for {len(sent_to)} recipient(s)"
            )
        except Exception as e:
            result['error'] = str(e)
            import traceback; traceback.print_exc()
        return result

    def send_email(self, to: str, subject: str, body: str,
                   thread_id: Optional[str] = None) -> bool:
        return self.gmail.send_email(to, subject, body, thread_id)

    def create_draft(self, to: str, subject: str, body: str) -> bool:
        return self.gmail.create_draft(to, subject, body)

    # ── Ambient agent ─────────────────────────────────────────────────────────

    def run_ambient_agent(self, thread_id: str = "default") -> Dict[str, Any]:
        result = {
            'status': 'success', 'emails_fetched': 0, 'emails_analyzed': 0,
            'events_fetched': 0, 'conflicts_found': 0, 'suggestions': [], 'drafts_created': 0,
        }
        try:
            emails = self.fetch_emails(max_results=50)
            result['emails_fetched']  = len(emails)
            analyzed = self.analyze_emails(emails)
            result['emails_analyzed'] = len(analyzed)

            events = self.fetch_calendar_events(days_ahead=30)
            result['events_fetched']  = len(events)
            conflicts = self.detect_conflicts(events)
            result['conflicts_found'] = len(conflicts)

            suggestions = []
            urgent   = [e for e in analyzed if e.priority_score and e.priority_score >= 8]
            if urgent:
                suggestions.append(f"You have {len(urgent)} high-priority emails requiring attention")
            unread_imp = [e for e in analyzed if e.is_unread and e.is_important]
            if unread_imp:
                suggestions.append(f"You have {len(unread_imp)} unread important emails")
            if conflicts:
                suggestions.append(f"Found {len(conflicts)} calendar conflicts that need resolution")
            today_ev = [e for e in events if e.start_time.date() == datetime.now().date()]
            if today_ev:
                suggestions.append(f"You have {len(today_ev)} events scheduled for today")
            result['suggestions'] = suggestions

            for conflict in conflicts[:3]:
                self.generate_conflict_resolution(conflict)
                result['drafts_created'] += 1

            return result
        except Exception as e:
            result['status'] = 'error'
            result['error']  = str(e)
            return result


# ============================================================================
# STREAMLIT APP ENTRY POINT
# ============================================================================

def main():
    st.set_page_config(
        page_title="Ambient Email Assistant",
        page_icon="📬",
        layout="wide",
    )

    # ── OAuth gate ───────────────────────────────────────────────────────────
    creds = handle_google_auth()
    if creds is None:
        st.stop()  # Login UI already rendered inside handle_google_auth()

    # ── Sign-out button ──────────────────────────────────────────────────────
    with st.sidebar:
        st.success("✅ Connected to Google")
        if st.button("Sign out"):
            st.session_state.pop("google_creds_token", None)
            st.query_params.clear()
            st.rerun()

    # ── Build assistant with injected credentials ────────────────────────────
    if "assistant" not in st.session_state:
        st.session_state["assistant"] = EnhancedEmailAssistant()

    assistant: EnhancedEmailAssistant = st.session_state["assistant"]
    assistant.inject_credentials(creds)

    # Optional: OpenAI key for AI features
    with st.sidebar:
        st.markdown("---")
        openai_key = st.text_input("OpenAI API key (optional)", type="password",
                                   help="Enables AI-powered email categorisation and conflict drafts")
        if openai_key:
            assistant.initialize_llm(api_key=openai_key)

    # ── Main UI ───────────────────────────────────────────────────────────────
    st.title("📬 Ambient Email Assistant")

    tab_emails, tab_calendar, tab_agent = st.tabs(["📧 Emails", "📅 Calendar", "🤖 Ambient Agent"])

    # ── Emails tab ────────────────────────────────────────────────────────────
    with tab_emails:
        st.subheader("Your Emails")
        col_q, col_n, col_btn = st.columns([3, 1, 1])
        with col_q:
            query = st.text_input("Search query", placeholder="e.g. is:unread label:important")
        with col_n:
            max_results = st.number_input("Max results", min_value=1, max_value=200, value=20)
        with col_btn:
            st.write("")
            fetch_btn = st.button("Fetch Emails", use_container_width=True)

        if fetch_btn:
            with st.spinner("Fetching emails…"):
                emails = assistant.fetch_emails(query=query, max_results=int(max_results))
            st.success(f"Fetched {len(emails)} emails")

        if assistant.emails_cache:
            if st.button("Analyse with AI"):
                with st.spinner("Analysing…"):
                    assistant.analyze_emails()
                st.success("Analysis complete")

            for email in assistant.emails_cache[:50]:
                with st.expander(f"{'🔴' if email.is_unread else '⚪'} {email.subject}  —  {email.sender}"):
                    cols = st.columns(4)
                    cols[0].metric("Category",  email.category  or "—")
                    cols[1].metric("Priority",  f"{email.priority_score}/10" if email.priority_score else "—")
                    cols[2].metric("Sentiment", email.sentiment or "—")
                    cols[3].metric("Date",      email.timestamp.strftime('%b %d'))
                    st.text_area("Body", email.body[:500], height=100, key=f"body_{email.id}")
                    if email.action_items:
                        st.markdown("**Action items:** " + " • ".join(email.action_items))

    # ── Calendar tab ──────────────────────────────────────────────────────────
    with tab_calendar:
        st.subheader("Calendar & Conflicts")
        days = st.slider("Days ahead", 1, 90, 30)
        if st.button("Fetch Calendar Events"):
            with st.spinner("Fetching events…"):
                events    = assistant.fetch_calendar_events(days_ahead=days)
                conflicts = assistant.detect_conflicts()
            st.success(f"Fetched {len(events)} events, {len(conflicts)} conflicts")

        if assistant.events_cache:
            st.markdown(f"**{len(assistant.events_cache)} upcoming events**")
            for ev in assistant.events_cache[:20]:
                st.write(f"- **{ev.summary}** — {ev.start_time.strftime('%b %d %I:%M %p')} → {ev.end_time.strftime('%I:%M %p')}")

        if assistant.conflicts_cache:
            st.markdown(f"### ⚠️ {len(assistant.conflicts_cache)} Conflict(s) Found")
            for i, conflict in enumerate(assistant.conflicts_cache):
                with st.expander(str(conflict)):
                    st.write(f"**Overlap:** {conflict.overlap_minutes} minutes")
                    if st.button("Generate Resolution Email", key=f"resolve_{i}"):
                        with st.spinner("Generating…"):
                            email_body = assistant.generate_conflict_resolution(conflict)
                        st.text_area("Draft email", email_body, height=300, key=f"draft_{i}")

                    if st.button("Find Free Slots", key=f"slots_{i}"):
                        with st.spinner("Scanning calendar…"):
                            slots = assistant.find_free_slots(
                                duration_minutes=conflict.event1.duration_minutes,
                                days_ahead=14,
                            )
                        st.write(f"Found {len(slots)} free slots:")
                        for slot in slots[:5]:
                            st.write(f"- {slot['start'].strftime('%b %d %I:%M %p')} — {slot['end'].strftime('%I:%M %p')}")

    # ── Ambient agent tab ─────────────────────────────────────────────────────
    with tab_agent:
        st.subheader("🤖 Run Ambient Agent")
        st.write("Fetches emails, analyses them, checks for calendar conflicts, and surfaces suggestions.")
        if st.button("Run Agent Now", type="primary"):
            with st.spinner("Running ambient agent…"):
                result = assistant.run_ambient_agent()
            if result['status'] == 'success':
                cols = st.columns(4)
                cols[0].metric("Emails fetched",   result['emails_fetched'])
                cols[1].metric("Emails analysed",  result['emails_analyzed'])
                cols[2].metric("Events fetched",   result['events_fetched'])
                cols[3].metric("Conflicts found",  result['conflicts_found'])
                if result['suggestions']:
                    st.markdown("### 💡 Suggestions")
                    for s in result['suggestions']:
                        st.info(s)
            else:
                st.error(f"Agent error: {result.get('error')}")


if __name__ == "__main__":
    main()
