"""
Ambient Email Assistant - Enhanced Version
AI-powered email and calendar management
Compatible with Streamlit Cloud deployment via Streamlit Secrets
"""

import os
import pickle
import base64
import tempfile
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from email.mime.text import MIMEText
import re

# Google API
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_AVAILABLE = True
    GOOGLE_IMPORT_ERROR = ""
except ImportError as e:
    GOOGLE_AVAILABLE = False
    GOOGLE_IMPORT_ERROR = str(e)

# LangChain
try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import ChatPromptTemplate
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

# dotenv (optional, local dev only)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events',
]

_TMPDIR      = tempfile.gettempdir()
TOKEN_FILE   = os.path.join(_TMPDIR, 'gmail_token.json')
CREDS_FILE   = os.path.join(_TMPDIR, 'gmail_credentials.json')
MEMORY_DIR   = os.path.join(_TMPDIR, 'email_assistant_memory')
MEMORY_FILE  = os.path.join(MEMORY_DIR, 'conversation_memory.pkl')


# ─────────────────────────────────────────────────────────────
# SECRETS HELPER  (Streamlit Cloud support)
# ─────────────────────────────────────────────────────────────

def _get_credentials_json() -> str:
    """Get the OAuth client credentials.json content from Secrets or local file."""
    try:
        import streamlit as st
        google = st.secrets.get("google", {})
        creds_json = google.get("credentials_json", "")
        if creds_json:
            return creds_json
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    local_creds = os.path.join(here, 'credentials.json')
    if os.path.exists(local_creds):
        with open(local_creds) as f:
            return f.read()
    return ""


def _write_creds_file() -> str:
    """Write credentials.json to temp file and return path."""
    content = _get_credentials_json()
    if not content:
        return ""
    with open(CREDS_FILE, "w") as f:
        f.write(content)
    return CREDS_FILE


def get_oauth_auth_url(redirect_uri: str) -> Tuple[str, str]:
    """
    Generate a Google OAuth authorization URL for the user to visit.
    Uses web Flow (not InstalledAppFlow) so it works on Streamlit Cloud.
    Returns (auth_url, state).
    """
    if not GOOGLE_AVAILABLE:
        return "", ""
    creds_file = _write_creds_file()
    if not creds_file:
        return "", ""
    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_secrets_file(
            creds_file, SCOPES, redirect_uri=redirect_uri)
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        return auth_url, state
    except Exception as e:
        print(f"Auth URL error: {e}")
        return "", ""


def exchange_code_for_token(code: str, redirect_uri: str) -> Optional[dict]:
    """
    Exchange an OAuth authorization code for user credentials.
    Uses web Flow — works for any user who logs in.
    Returns token dict or None on failure.
    """
    if not GOOGLE_AVAILABLE:
        return None
    creds_file = _write_creds_file()
    if not creds_file:
        return None
    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_secrets_file(
            creds_file, SCOPES, redirect_uri=redirect_uri)
        flow.fetch_token(code=code)
        return json.loads(flow.credentials.to_json())
    except Exception as e:
        print(f"Token exchange error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────

@dataclass
class EmailData:
    id: str
    thread_id: str
    subject: str
    sender: str
    recipient: str
    timestamp: datetime
    body: str
    snippet: str                          # ← always use 'snippet', NOT 'preview'
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
        return f"Email('{self.subject}', from='{self.sender}')"


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
    # Aliases populated in __post_init__
    start: datetime = field(init=False, repr=False)
    end:   datetime = field(init=False, repr=False)
    title: str      = field(init=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, 'start', self.start_time)
        object.__setattr__(self, 'end',   self.end_time)
        object.__setattr__(self, 'title', self.summary)

    @property
    def duration_minutes(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() / 60)


@dataclass
class ConflictInfo:
    event1: CalendarEvent
    event2: CalendarEvent
    overlap_start: datetime
    overlap_end: datetime

    # Make subscriptable so conflict['event1'] works in templates
    def __getitem__(self, key):
        return getattr(self, key)

    @property
    def overlap_minutes(self) -> float:
        return (self.overlap_end - self.overlap_start).total_seconds() / 60


# ─────────────────────────────────────────────────────────────
# GMAIL SERVICE
# ─────────────────────────────────────────────────────────────

class GmailService:
    def __init__(self):
        self.service = None
        self.creds   = None
        self.last_error = ""

    def authenticate(self, token_dict: dict = None) -> bool:
        """
        Authenticate using a per-user token dict (from OAuth flow).
        Falls back to Streamlit Secrets token for local/single-user use.
        """
        try:
            if not GOOGLE_AVAILABLE:
                self.last_error = f"Google libraries not installed. Check requirements.txt. Detail: {GOOGLE_IMPORT_ERROR}"
                return False

            # ── Build credentials from token dict (per-user OAuth) ──
            if token_dict:
                try:
                    import google.oauth2.credentials as gc
                    self.creds = gc.Credentials(
                        token=token_dict.get('token'),
                        refresh_token=token_dict.get('refresh_token'),
                        token_uri=token_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
                        client_id=token_dict.get('client_id'),
                        client_secret=token_dict.get('client_secret'),
                        scopes=token_dict.get('scopes', SCOPES),
                    )
                except Exception as e:
                    self.last_error = f"Failed to build credentials: {e}"
                    return False
            else:
                # ── Fallback: load from Streamlit Secrets token_json ──
                tok_json = ""
                try:
                    import streamlit as st
                    tok_json = st.secrets.get("google", {}).get("token_json", "")
                except Exception:
                    pass
                if not tok_json:
                    here = os.path.dirname(os.path.abspath(__file__))
                    local_token = os.path.join(here, 'token.json')
                    if os.path.exists(local_token):
                        with open(local_token) as f:
                            tok_json = f.read()
                if not tok_json:
                    self.last_error = "No token found. Please connect your Gmail account."
                    return False
                with open(TOKEN_FILE, 'w') as f:
                    f.write(tok_json)
                try:
                    self.creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
                except Exception as e:
                    self.last_error = f"Failed to load token: {e}"
                    return False

            # ── Refresh if expired ────────────────────────────
            if not self.creds.valid:
                if self.creds.expired and self.creds.refresh_token:
                    try:
                        self.creds.refresh(Request())
                    except Exception as e:
                        self.last_error = f"Token refresh failed: {e}"
                        return False
                else:
                    self.last_error = "Token invalid. Please reconnect your Gmail."
                    return False

            self.service = build('gmail', 'v1', credentials=self.creds)
            return True

        except Exception as e:
            self.last_error = f"Gmail auth error: {e}"
            return False

    def get_emails(self, query: str = "", max_results: int = 50) -> List['EmailData']:
        if not self.service and not self.authenticate():
            return []
        try:
            res  = self.service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
            msgs = res.get('messages', [])
            return [e for e in (self._parse_message(m['id']) for m in msgs) if e]
        except HttpError as e:
            print(f"Gmail list error: {e}")
            return []

    def _parse_message(self, msg_id: str) -> Optional['EmailData']:
        try:
            msg     = self.service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            headers = msg['payload']['headers']

            def hdr(name):
                return next((h['value'] for h in headers if h['name'].lower() == name.lower()), '')

            subject  = hdr('subject') or 'No Subject'
            sender   = hdr('from')    or 'Unknown'
            recipient = hdr('to')     or 'Unknown'
            date_str = hdr('date')

            sender_email = self._extract_email(sender)
            timestamp    = self._parse_date(date_str) if date_str else datetime.now()
            body         = self._get_body(msg)
            snippet      = msg.get('snippet', '')
            labels       = msg.get('labelIds', [])

            return EmailData(
                id=msg_id, thread_id=msg['threadId'],
                subject=subject, sender=sender, recipient=recipient,
                timestamp=timestamp, body=body, snippet=snippet,
                is_unread='UNREAD' in labels,
                is_important='IMPORTANT' in labels or 'STARRED' in labels,
                has_attachment=self._has_attachments(msg),
                has_calendar_event=self._detect_calendar(body, subject),
                sender_email=sender_email, labels=labels,
            )
        except Exception as e:
            print(f"Parse error {msg_id}: {e}")
            return None

    def _extract_email(self, sender: str) -> str:
        m = re.search(r'<([^>]+)>', sender)
        if m: return m.group(1)
        m = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', sender)
        return m.group(0) if m else sender

    def _get_body(self, msg: Dict) -> str:
        try:
            parts = msg['payload'].get('parts', [])
            if not parts:
                data = msg['payload'].get('body', {}).get('data', '')
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore') if data else ''
            for mime in ('text/plain', 'text/html'):
                for p in parts:
                    if p['mimeType'] == mime:
                        data = p.get('body', {}).get('data', '')
                        if data:
                            text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                            return re.sub('<[^<]+?>', '', text) if mime == 'text/html' else text
        except Exception:
            pass
        return msg.get('snippet', '')

    def _has_attachments(self, msg: Dict) -> bool:
        return any(p.get('filename') for p in msg['payload'].get('parts', []))

    def _detect_calendar(self, body: str, subject: str) -> bool:
        kw = ['meeting', 'calendar', 'event', 'invited', 'invitation',
              'scheduled', 'appointment', 'conference', 'zoom', 'teams']
        bl, sl = body.lower(), subject.lower()
        return any(k in bl or k in sl for k in kw)

    def _parse_date(self, date_str: str) -> datetime:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except Exception:
            return datetime.now()

    def send_email(self, to: str, subject: str, body: str, thread_id: Optional[str] = None) -> bool:
        if not self.service and not self.authenticate():
            return False
        try:
            msg = MIMEText(body)
            msg['to'] = to; msg['subject'] = subject
            raw     = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            payload = {'raw': raw}
            if thread_id: payload['threadId'] = thread_id
            self.service.users().messages().send(userId='me', body=payload).execute()
            return True
        except HttpError as e:
            print(f"Send error: {e}"); return False

    def create_draft(self, to: str, subject: str, body: str) -> bool:
        if not self.service and not self.authenticate():
            return False
        try:
            msg = MIMEText(body)
            msg['to'] = to; msg['subject'] = subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            self.service.users().drafts().create(userId='me', body={'message': {'raw': raw}}).execute()
            return True
        except HttpError as e:
            print(f"Draft error: {e}"); return False


# ─────────────────────────────────────────────────────────────
# CALENDAR SERVICE
# ─────────────────────────────────────────────────────────────

class CalendarService:
    def __init__(self):
        self.service    = None
        self.creds      = None
        self.last_error = ""

    def authenticate(self, token_dict: dict = None) -> bool:
        """
        Authenticate using a per-user token dict (from OAuth flow).
        Falls back to Streamlit Secrets token for local/single-user use.
        """
        try:
            if not GOOGLE_AVAILABLE:
                self.last_error = f"Google libraries not installed. Check requirements.txt. Detail: {GOOGLE_IMPORT_ERROR}"
                return False

            if token_dict:
                try:
                    import google.oauth2.credentials as gc
                    self.creds = gc.Credentials(
                        token=token_dict.get('token'),
                        refresh_token=token_dict.get('refresh_token'),
                        token_uri=token_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
                        client_id=token_dict.get('client_id'),
                        client_secret=token_dict.get('client_secret'),
                        scopes=token_dict.get('scopes', SCOPES),
                    )
                except Exception as e:
                    self.last_error = f"Failed to build credentials: {e}"
                    return False
            else:
                tok_json = ""
                try:
                    import streamlit as st
                    tok_json = st.secrets.get("google", {}).get("token_json", "")
                except Exception:
                    pass
                if not tok_json:
                    here = os.path.dirname(os.path.abspath(__file__))
                    local_token = os.path.join(here, 'token.json')
                    if os.path.exists(local_token):
                        with open(local_token) as f:
                            tok_json = f.read()
                if not tok_json:
                    self.last_error = "No token found. Please connect your Gmail account."
                    return False
                with open(TOKEN_FILE, 'w') as f:
                    f.write(tok_json)
                try:
                    self.creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
                except Exception as e:
                    self.last_error = f"Failed to load token: {e}"
                    return False

            if not self.creds.valid:
                if self.creds.expired and self.creds.refresh_token:
                    try:
                        self.creds.refresh(Request())
                    except Exception as e:
                        self.last_error = f"Calendar token refresh failed: {e}"
                        return False
                else:
                    self.last_error = "Calendar token invalid. Please reconnect."
                    return False

            self.service = build("calendar", "v3", credentials=self.creds)
            return True
        except Exception as e:
            self.last_error = f"Calendar auth error: {e}"
            return False

    def get_events(self, days_ahead: int = 30) -> List['CalendarEvent']:
        if not self.service and not self.authenticate():
            return []
        try:
            now      = datetime.utcnow()
            time_min = now.isoformat() + 'Z'
            time_max = (now + timedelta(days=days_ahead)).isoformat() + 'Z'
            res = self.service.events().list(
                calendarId='primary', timeMin=time_min, timeMax=time_max,
                maxResults=100, singleEvents=True, orderBy='startTime').execute()
            return [e for e in (self._parse_event(ev) for ev in res.get('items', [])) if e]
        except HttpError as e:
            print(f"Calendar list error: {e}"); return []

    def _parse_event(self, event: Dict) -> Optional['CalendarEvent']:
        try:
            s = event['start'].get('dateTime', event['start'].get('date'))
            e = event['end'].get('dateTime',   event['end'].get('date'))
            return CalendarEvent(
                id=event['id'],
                summary=event.get('summary', 'No Title'),
                start_time=datetime.fromisoformat(s.replace('Z', '+00:00')),
                end_time=datetime.fromisoformat(e.replace('Z', '+00:00')),
                description=event.get('description'),
                location=event.get('location'),
                attendees=[a.get('email', '') for a in event.get('attendees', [])],
                organizer=event.get('organizer', {}).get('email'),
                status=event.get('status', 'confirmed'),
            )
        except Exception as ex:
            print(f"Event parse error: {ex}"); return None

    def find_conflicts(self, events: List['CalendarEvent']) -> List['ConflictInfo']:
        conflicts = []
        for i, e1 in enumerate(events):
            for e2 in events[i+1:]:
                if e1.start_time < e2.end_time and e2.start_time < e1.end_time:
                    conflicts.append(ConflictInfo(
                        event1=e1, event2=e2,
                        overlap_start=max(e1.start_time, e2.start_time),
                        overlap_end=min(e1.end_time,   e2.end_time),
                    ))
        return conflicts

    def find_free_slots(self, events: List['CalendarEvent'],
                        duration_minutes: int = 60,
                        days_ahead: int = 7) -> List[Dict[str, Any]]:
        free = []
        now  = datetime.now()
        end  = now + timedelta(days=days_ahead)

        busy = []
        for ev in (events or []):
            s = ev.start_time.replace(tzinfo=None) if ev.start_time.tzinfo else ev.start_time
            e = ev.end_time.replace(tzinfo=None)   if ev.end_time.tzinfo   else ev.end_time
            if e > now and s < end:
                busy.append((s, e))

        # Start from next rounded 30-min mark in business hours
        if now.hour >= 20:
            cur = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        elif now.hour < 8:
            cur = now.replace(hour=8, minute=0, second=0, microsecond=0)
        else:
            m = ((now.minute // 30) + 1) * 30
            if m >= 60:
                cur = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            else:
                cur = now.replace(minute=m, second=0, microsecond=0)

        iterations = 0
        while cur < end and iterations < 1000 and len(free) < 20:
            iterations += 1
            if cur.hour < 8:
                cur = cur.replace(hour=8, minute=0, second=0, microsecond=0); continue
            if cur.hour >= 20:
                cur = (cur + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0); continue
            slot_end = cur + timedelta(minutes=duration_minutes)
            if cur > now and not any(cur < be and slot_end > bs for bs, be in busy):
                free.append({'start': cur, 'end': slot_end, 'duration_minutes': duration_minutes})
            cur += timedelta(minutes=30)

        return free


# ─────────────────────────────────────────────────────────────
# AI ANALYZER
# ─────────────────────────────────────────────────────────────

class AIAnalyzer:
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
                print(f"LLM init error: {e}")

    def analyze_email(self, email: 'EmailData') -> 'EmailData':
        if not self.llm:
            return self._rule_based(email)
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", "Analyse the email. Reply ONLY in this exact format:\nCategory: <work|personal|urgent|newsletter|spam>\nPriority: <0-10>\nSentiment: <positive|neutral|negative>\nDates: <dates or none>\nActions: <actions or none>"),
                ("human",  "Subject: {subject}\nFrom: {sender}\nBody: {body}"),
            ])
            resp = (prompt | self.llm).invoke({
                "subject": email.subject, "sender": email.sender, "body": email.body[:1000]})
            for line in resp.content.strip().split('\n'):
                if   line.startswith('Category:'):  email.category       = line.split(':',1)[1].strip().lower()
                elif line.startswith('Priority:'):
                    m = re.search(r'\d+', line.split(':',1)[1])
                    email.priority_score = int(m.group()) if m else 5
                elif line.startswith('Sentiment:'): email.sentiment      = line.split(':',1)[1].strip().lower()
                elif line.startswith('Dates:'):
                    v = line.split(':',1)[1].strip()
                    if v.lower() != 'none': email.extracted_dates = [d.strip() for d in v.split(',')]
                elif line.startswith('Actions:'):
                    v = line.split(':',1)[1].strip()
                    if v.lower() != 'none': email.action_items    = [a.strip() for a in v.split(',')]
            return email
        except Exception as e:
            print(f"AI analysis error: {e}")
            return self._rule_based(email)

    def _rule_based(self, email: 'EmailData') -> 'EmailData':
        bl, sl = email.body.lower(), email.subject.lower()
        if any(w in bl or w in sl for w in ['meeting','project','deadline','task']):      email.category = 'work'
        elif any(w in bl or w in sl for w in ['urgent','asap','important','critical']):  email.category = 'urgent'
        elif any(w in bl or w in sl for w in ['unsubscribe','newsletter','promotion']):  email.category = 'newsletter'
        else:                                                                              email.category = 'personal'
        sp = {'urgent':9, 'work':7, 'personal':5, 'newsletter':3}
        email.priority_score = 9 if email.is_important else sp.get(email.category, 5)
        pos = sum(1 for w in ['thank','great','excellent','congratulations'] if w in bl)
        neg = sum(1 for w in ['sorry','problem','issue','error','cancel']    if w in bl)
        email.sentiment = 'positive' if pos>neg else 'negative' if neg>pos else 'neutral'
        return email

    def generate_conflict_resolution_email(self, conflict: 'ConflictInfo',
                                           alt_times: List[Tuple[datetime, datetime]]) -> str:
        if not self.llm:
            return self._template_email(conflict, alt_times)
        try:
            alts = "\n".join(f"- {s.strftime('%B %d, %Y at %I:%M %p')} – {e.strftime('%I:%M %p')}" for s, e in alt_times[:3])
            prompt = ChatPromptTemplate.from_messages([
                ("system", "Write a polite professional email to resolve a calendar conflict. Be concise."),
                ("human",  "Conflict:\nMeeting 1: {e1} at {t1}\nMeeting 2: {e2} at {t2}\nOverlap: {ov} min\nAlternative times:\n{alts}\nWrite the email:"),
            ])
            resp = (prompt | self.llm).invoke({
                "e1": conflict.event1.summary,  "t1": conflict.event1.start_time.strftime('%B %d at %I:%M %p'),
                "e2": conflict.event2.summary,  "t2": conflict.event2.start_time.strftime('%B %d at %I:%M %p'),
                "ov": f"{conflict.overlap_minutes:.0f}", "alts": alts,
            })
            return resp.content
        except Exception as e:
            print(f"Email gen error: {e}")
            return self._template_email(conflict, alt_times)

    def _template_email(self, conflict: 'ConflictInfo', alt_times: List[Tuple[datetime, datetime]]) -> str:
        lines = [
            "Dear Team,",
            "",
            "I'd like to flag a scheduling conflict:",
            "",
            f"• {conflict.event1.summary}: {conflict.event1.start_time.strftime('%B %d at %I:%M %p')} – {conflict.event1.end_time.strftime('%I:%M %p')}",
            f"• {conflict.event2.summary}: {conflict.event2.start_time.strftime('%B %d at %I:%M %p')} – {conflict.event2.end_time.strftime('%I:%M %p')}",
            f"  (Overlap: {conflict.overlap_minutes:.0f} minutes)",
            "",
            "SUGGESTED ALTERNATIVE TIMES:",
        ]
        for i, (s, e) in enumerate(alt_times[:3], 1):
            lines.append(f"{i}. {s.strftime('%B %d, %Y at %I:%M %p')} – {e.strftime('%I:%M %p')}")
        lines += ["", "Please let me know which time works best.", "", "Best regards"]
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# ENHANCED EMAIL ASSISTANT  (entry point for Streamlit)
# ─────────────────────────────────────────────────────────────

class EnhancedEmailAssistant:
    def __init__(self):
        self.gmail    = GmailService()
        self.calendar = CalendarService()
        self.analyzer = AIAnalyzer()
        self.llm: Any = None
        self.conversation_memory: List = []
        self.emails_cache:    List[EmailData]    = []
        self.events_cache:    List[CalendarEvent] = []
        self.conflicts_cache: List[ConflictInfo]  = []
        self._load_memory()

    # Auth
    def authenticate(self, token_dict: dict = None) -> bool:
        """
        Authenticate both Gmail and Calendar.
        Pass token_dict (from per-user OAuth) or None to use Streamlit Secrets fallback.
        """
        gmail_ok = self.gmail.authenticate(token_dict=token_dict)
        if not gmail_ok:
            raise Exception(self.gmail.last_error)
        cal_ok = self.calendar.authenticate(token_dict=token_dict)
        if not cal_ok:
            raise Exception(self.calendar.last_error)
        return True

    def initialize_llm(self, api_key: Optional[str] = None) -> bool:
        self.analyzer = AIAnalyzer(api_key=api_key)
        self.llm      = self.analyzer.llm
        return self.llm is not None

    # Memory
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
        except Exception:
            pass

    # Email
    def fetch_emails(self, query: str = "", max_results: int = 50) -> List[EmailData]:
        self.emails_cache = self.gmail.get_emails(query, max_results)
        return self.emails_cache

    def analyze_emails(self, emails: Optional[List[EmailData]] = None) -> List[EmailData]:
        src = emails if emails is not None else self.emails_cache
        result = [self.analyzer.analyze_email(e) for e in src]
        if emails is None:
            self.emails_cache = result
        return result

    def categorize_emails_ai(self, emails: Optional[List[EmailData]] = None) -> List[EmailData]:
        return self.analyze_emails(emails)

    def send_email(self, to: str, subject: str, body: str, thread_id: Optional[str] = None) -> bool:
        return self.gmail.send_email(to, subject, body, thread_id)

    def create_draft(self, to: str, subject: str, body: str) -> bool:
        return self.gmail.create_draft(to, subject, body)

    # Calendar
    def fetch_calendar_events(self, days_ahead: int = 30) -> List[CalendarEvent]:
        self.events_cache = self.calendar.get_events(days_ahead)
        return self.events_cache

    def detect_conflicts(self, events: Optional[List[CalendarEvent]] = None) -> List[ConflictInfo]:
        src = events if events is not None else self.events_cache
        self.conflicts_cache = self.calendar.find_conflicts(src)
        return self.conflicts_cache

    def find_free_slots(self, *args, **kwargs) -> List[Dict[str, Any]]:
        events           = kwargs.get('events',          None)
        duration_minutes = kwargs.get('duration_minutes', 60)
        days_ahead       = kwargs.get('days_ahead',       7)
        for a in args:
            if isinstance(a, list): events           = a
            elif isinstance(a, int): duration_minutes = a
        return self.calendar.find_free_slots(
            events if events is not None else self.events_cache,
            duration_minutes, days_ahead)

    # Conflict email
    def generate_conflict_email(self, conflict: ConflictInfo,
                                free_slots: Optional[List[Dict[str, Any]]] = None) -> str:
        return self.generate_conflict_resolution(conflict, free_slots)

    def generate_conflict_resolution(self, conflict: ConflictInfo,
                                     free_slots: Optional[List[Dict[str, Any]]] = None) -> str:
        if free_slots is None:
            free_slots = self.find_free_slots(duration_minutes=60, days_ahead=14)
        alt = [(s['start'], s['end']) for s in (free_slots or [])[:5] if isinstance(s, dict)]
        return self.analyzer.generate_conflict_resolution_email(conflict, alt)

    # ── Main workflow ─────────────────────────────────────────
    def run_ambient_agent(self, thread_id: str = "default") -> Dict[str, Any]:
        """
        Runs the full workflow and returns a result dict with:
          'emails'          → List[EmailData]      (the actual objects)
          'calendar_events' → List[CalendarEvent]
          'conflicts'       → List[ConflictInfo]
          'suggestions'     → List[dict]
          'analysis_complete' → bool
        """
        result: Dict[str, Any] = {
            'status':            'success',
            'emails':            [],
            'calendar_events':   [],
            'conflicts':         [],
            'suggestions':       [],
            'analysis_complete': False,
            'error_logs':        [],
        }
        try:
            emails   = self.fetch_emails(max_results=50)
            analyzed = self.analyze_emails(emails)
            result['emails'] = analyzed

            events = self.fetch_calendar_events(days_ahead=30)
            result['calendar_events'] = events

            conflicts = self.detect_conflicts(events)
            result['conflicts'] = conflicts

            suggestions = []
            urgent = [e for e in analyzed if (e.priority_score or 0) >= 8]
            if urgent:
                suggestions.append({'title': f'{len(urgent)} high-priority emails',
                                    'description': 'Require your attention soon.',
                                    'type': 'email', 'action': 'review'})
            unread_imp = [e for e in analyzed if e.is_unread and e.is_important]
            if unread_imp:
                suggestions.append({'title': f'{len(unread_imp)} unread important emails',
                                    'description': 'Starred emails you haven\'t read.',
                                    'type': 'email', 'action': 'read'})
            if conflicts:
                suggestions.append({'title': f'{len(conflicts)} calendar conflicts',
                                    'description': 'Overlapping meetings need resolution.',
                                    'type': 'calendar', 'action': 'resolve'})
            today = datetime.now().date()
            today_evs = [e for e in events if e.start_time.date() == today]
            if today_evs:
                suggestions.append({'title': f'{len(today_evs)} events today',
                                    'description': ', '.join(e.summary for e in today_evs[:3]),
                                    'type': 'calendar', 'action': 'review'})
            result['suggestions']       = suggestions
            result['analysis_complete'] = True
            self._save_memory()

        except Exception as e:
            result['status'] = 'error'
            result['error_logs'].append(str(e))

        return result


# ─────────────────────────────────────────────────────────────
# MAIN (local testing only)
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🤖 Ambient Email Assistant")
    a = EnhancedEmailAssistant()
    if not a.authenticate():
        print("❌ Auth failed"); exit(1)
    print(f"✅ Auth OK | Emails: {len(a.fetch_emails(5))} | Events: {len(a.fetch_calendar_events(7))}")
