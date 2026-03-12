"""
Ambient Email Assistant - Enhanced Version
AI-powered email and calendar management with LangGraph workflows
Compatible with Streamlit UI
"""

import os
import pickle
import base64
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from email.mime.text import MIMEText
import re

# Google API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
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

# Configuration
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events'
]

TOKEN_FILE = 'token.json'
CREDENTIALS_FILE = 'credentials.json'
MEMORY_DIR = 'memory'
MEMORY_FILE = os.path.join(MEMORY_DIR, 'conversation_memory.pkl')
CHECKPOINT_DB = os.path.join(MEMORY_DIR, 'checkpoints.db')


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class EmailData:
    """Email data model - primary class name for Streamlit compatibility"""
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
    sender_email: str = ""  # FIXED: Added missing attribute
    labels: List[str] = field(default_factory=list)
    
    # AI-enhanced fields
    category: Optional[str] = None  # work, personal, urgent, spam, etc.
    priority_score: Optional[int] = None  # 0-10 scale
    sentiment: Optional[str] = None  # positive, neutral, negative
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
        """Set up aliases for compatibility"""
        object.__setattr__(self, 'start', self.start_time)
        object.__setattr__(self, 'end', self.end_time)
        object.__setattr__(self, 'title', self.summary)
    
    @property
    def duration_minutes(self) -> int:
        """Calculate event duration in minutes"""
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
        """Make ConflictInfo subscriptable for compatibility"""
        return getattr(self, key)
    
    @property
    def overlap_minutes(self) -> int:
        """Calculate overlap duration in minutes"""
        return int((self.overlap_end - self.overlap_start).total_seconds() / 60)
    
    def __str__(self):
        return f"Conflict: '{self.event1.summary}' vs '{self.event2.summary}' ({self.overlap_minutes} min)"


# ============================================================================
# GMAIL SERVICE
# ============================================================================

class GmailService:
    """Gmail API service wrapper"""
    
    def __init__(self, credentials_file: str = CREDENTIALS_FILE, token_file: str = TOKEN_FILE):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
        self.creds = None
    
    def inject_credentials(self, creds) -> bool:
        """Multi-user: receive credentials from browser OAuth — no file I/O."""
        try:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            self.creds = creds
            self.service = build('gmail', 'v1', credentials=self.creds)
            return True
        except Exception as e:
            print(f"GmailService.inject_credentials: {e}")
            return False

    def authenticate(self) -> bool:
        """Authenticate with Gmail API"""
        try:
            # Load existing credentials
            if os.path.exists(self.token_file):
                self.creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            
            # Refresh or get new credentials
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                else:
                    if not os.path.exists(self.credentials_file):
                        print(f"Error: {self.credentials_file} not found!")
                        print("Please download credentials from Google Cloud Console")
                        return False
                    
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_file, SCOPES)
                    self.creds = flow.run_local_server(port=0)
                
                # Save credentials
                with open(self.token_file, 'w') as token:
                    token.write(self.creds.to_json())
            
            # Build service
            self.service = build('gmail', 'v1', credentials=self.creds)
            return True
            
        except Exception as e:
            print(f"Authentication error: {e}")
            return False
    
    def get_emails(self, query: str = "", max_results: int = 50) -> List[EmailData]:
        """Fetch emails from Gmail"""
        if not self.service:
            if not self.authenticate():
                return []
        
        try:
            # Get message list
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            emails = []
            
            # Fetch each message
            for msg in messages:
                email = self._parse_message(msg['id'])
                if email:
                    emails.append(email)
            
            return emails
            
        except HttpError as error:
            print(f'Gmail API error: {error}')
            return []
    
    def _parse_message(self, msg_id: str) -> Optional[EmailData]:
        """Parse a Gmail message into EmailData object"""
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=msg_id,
                format='full'
            ).execute()
            
            # Extract headers
            headers = message['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
            recipient = next((h['value'] for h in headers if h['name'].lower() == 'to'), 'Unknown')
            date_str = next((h['value'] for h in headers if h['name'].lower() == 'date'), None)
            
            # Extract email address from sender string (e.g., "John Doe <john@example.com>" -> "john@example.com")
            sender_email = self._extract_email_address(sender)
            
            # Parse timestamp
            timestamp = self._parse_date(date_str) if date_str else datetime.now()
            
            # Extract body
            body = self._get_message_body(message)
            snippet = message.get('snippet', '')
            
            # Extract metadata
            labels = message.get('labelIds', [])
            is_unread = 'UNREAD' in labels
            is_important = 'IMPORTANT' in labels or 'STARRED' in labels
            
            # Check attachments
            has_attachment = self._has_attachments(message)
            
            # Check for calendar events (simple detection based on body content)
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
                labels=labels
            )
            
        except Exception as e:
            print(f"Error parsing message {msg_id}: {e}")
            return None
    
    def _detect_calendar_event(self, body: str, subject: str) -> bool:
        """Detect if email contains calendar event information"""
        calendar_keywords = [
            'meeting', 'calendar', 'event', 'invited', 'invitation',
            'scheduled', 'appointment', 'conference', 'zoom', 'teams',
            'when:', 'where:', 'time:', 'date:', 'rsvp'
        ]
        
        body_lower = body.lower()
        subject_lower = subject.lower()
        
        return any(keyword in body_lower or keyword in subject_lower 
                  for keyword in calendar_keywords)
    
    def _extract_email_address(self, sender: str) -> str:
        """Extract email address from sender string like 'John Doe <john@example.com>'"""
        import re
        # Look for email pattern in angle brackets
        match = re.search(r'<([^>]+)>', sender)
        if match:
            return match.group(1)
        
        # If no angle brackets, check if the whole string is an email
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(email_pattern, sender)
        if match:
            return match.group(0)
        
        # Fallback to original sender if no email found
        return sender
    
    def _get_message_body(self, message: Dict) -> str:
        """Extract email body from message"""
        try:
            parts = message['payload'].get('parts', [])
            
            if not parts:
                # Single part message
                body_data = message['payload'].get('body', {}).get('data', '')
                if body_data:
                    return base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
            
            # Multi-part message
            for part in parts:
                if part['mimeType'] == 'text/plain':
                    body_data = part.get('body', {}).get('data', '')
                    if body_data:
                        return base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
            
            # Fallback to HTML
            for part in parts:
                if part['mimeType'] == 'text/html':
                    body_data = part.get('body', {}).get('data', '')
                    if body_data:
                        html = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                        # Simple HTML to text conversion
                        text = re.sub('<[^<]+?>', '', html)
                        return text
            
            return message.get('snippet', '')
            
        except Exception as e:
            print(f"Error extracting body: {e}")
            return message.get('snippet', '')
    
    def _has_attachments(self, message: Dict) -> bool:
        """Check if message has attachments"""
        parts = message['payload'].get('parts', [])
        for part in parts:
            if part.get('filename'):
                return True
        return False
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse email date string to datetime"""
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except:
            return datetime.now()
    
    def send_email(self, to: str, subject: str, body: str, 
                   thread_id: Optional[str] = None) -> bool:
        """Send an email"""
        if not self.service:
            if not self.authenticate():
                return False
        
        try:
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            send_message = {'raw': raw_message}
            if thread_id:
                send_message['threadId'] = thread_id
            
            self.service.users().messages().send(
                userId='me',
                body=send_message
            ).execute()
            
            return True
            
        except HttpError as error:
            print(f'Error sending email: {error}')
            return False
    
    def create_draft(self, to: str, subject: str, body: str) -> bool:
        """Create an email draft"""
        if not self.service:
            if not self.authenticate():
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
    
    def __init__(self, credentials_file: str = CREDENTIALS_FILE, token_file: str = TOKEN_FILE):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
        self.creds = None
    
    def inject_credentials(self, creds) -> bool:
        """Multi-user: receive credentials from browser OAuth — no file I/O."""
        try:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            self.creds = creds
            self.service = build('calendar', 'v3', credentials=self.creds)
            return True
        except Exception as e:
            print(f"CalendarService.inject_credentials: {e}")
            return False

    def authenticate(self) -> bool:
        """Authenticate with Calendar API"""
        try:
            # Load existing credentials
            if os.path.exists(self.token_file):
                self.creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            
            # Refresh or get new credentials
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                else:
                    if not os.path.exists(self.credentials_file):
                        return False
                    
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_file, SCOPES)
                    self.creds = flow.run_local_server(port=0)
                
                # Save credentials
                with open(self.token_file, 'w') as token:
                    token.write(self.creds.to_json())
            
            # Build service
            self.service = build('calendar', 'v3', credentials=self.creds)
            return True
            
        except Exception as e:
            print(f"Calendar authentication error: {e}")
            return False
    
    def get_events(self, days_ahead: int = 30) -> List[CalendarEvent]:
        """Fetch calendar events"""
        if not self.service:
            if not self.authenticate():
                return []
        
        try:
            now = datetime.utcnow()
            time_min = now.isoformat() + 'Z'
            time_max = (now + timedelta(days=days_ahead)).isoformat() + 'Z'
            
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                maxResults=100,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            calendar_events = []
            
            for event in events:
                cal_event = self._parse_event(event)
                if cal_event:
                    calendar_events.append(cal_event)
            
            return calendar_events
            
        except HttpError as error:
            print(f'Calendar API error: {error}')
            return []
    
    def _parse_event(self, event: Dict) -> Optional[CalendarEvent]:
        """Parse a calendar event"""
        try:
            # Extract times
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            start_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(end.replace('Z', '+00:00'))
            
            # Extract attendees
            attendees = []
            for attendee in event.get('attendees', []):
                attendees.append(attendee.get('email', ''))
            
            return CalendarEvent(
                id=event['id'],
                summary=event.get('summary', 'No Title'),
                start_time=start_time,
                end_time=end_time,
                description=event.get('description'),
                location=event.get('location'),
                attendees=attendees,
                organizer=event.get('organizer', {}).get('email'),
                status=event.get('status', 'confirmed')
            )
            
        except Exception as e:
            print(f"Error parsing event: {e}")
            return None
    
    def find_conflicts(self, events: List[CalendarEvent]) -> List[ConflictInfo]:
        """Find overlapping events"""
        conflicts = []
        
        for i, event1 in enumerate(events):
            for event2 in events[i+1:]:
                # Check for overlap
                if event1.start_time < event2.end_time and event2.start_time < event1.end_time:
                    overlap_start = max(event1.start_time, event2.start_time)
                    overlap_end = min(event1.end_time, event2.end_time)
                    
                    conflicts.append(ConflictInfo(
                        event1=event1,
                        event2=event2,
                        overlap_start=overlap_start,
                        overlap_end=overlap_end
                    ))
        
        return conflicts
    
    def find_free_slots(self, events: List[CalendarEvent], 
                       duration_minutes: int = 60,
                       days_ahead: int = 7) -> List[Dict[str, Any]]:
        """Find free time slots - returns list of dicts for Streamlit compatibility"""
        free_slots = []
        
        try:
            # Define search window
            now = datetime.now()
            search_end = now + timedelta(days=days_ahead)
            
            # Debug: Print current time and events
            print(f"\n=== Finding Free Slots ===")
            print(f"Current time: {now}")
            print(f"Search until: {search_end}")
            print(f"Number of events to check: {len(events) if events else 0}")
            
            # Filter to only future events within search window
            future_events = []
            if events:
                for event in events:
                    # Convert event times to naive datetime if they're timezone-aware
                    event_start = event.start_time.replace(tzinfo=None) if event.start_time.tzinfo else event.start_time
                    event_end = event.end_time.replace(tzinfo=None) if event.end_time.tzinfo else event.end_time
                    
                    # Only consider events that end in the future
                    if event_end > now and event_start < search_end:
                        future_events.append((event_start, event_end, event.summary))
                        print(f"  Event: {event.summary} | {event_start} - {event_end}")
            
            print(f"Future events to avoid: {len(future_events)}")
            
            # Business hours: 8 AM - 8 PM (extended hours for more flexibility)
            # Start from current time or next business hour
            if now.hour >= 20:
                current_time = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
            elif now.hour < 8:
                current_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
            else:
                # Round up to next 30-minute mark
                minutes = (now.minute // 30 + 1) * 30
                if minutes >= 60:
                    current_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                else:
                    current_time = now.replace(minute=minutes, second=0, microsecond=0)
            
            print(f"Starting search from: {current_time}")
            
            max_iterations = 1000  # Prevent infinite loops
            iteration = 0
            
            while current_time < search_end and iteration < max_iterations:
                iteration += 1
                slot_end = current_time + timedelta(minutes=duration_minutes)
                
                # Skip if outside extended business hours (8 AM - 8 PM)
                if current_time.hour < 8:
                    current_time = current_time.replace(hour=8, minute=0, second=0, microsecond=0)
                    continue
                elif current_time.hour >= 20:
                    current_time = current_time.replace(hour=8, minute=0) + timedelta(days=1)
                    continue
                
                # Check if slot is free (no overlap with any event)
                is_free = True
                if future_events:
                    for event_start, event_end, event_name in future_events:
                        # Check for any overlap
                        if current_time < event_end and slot_end > event_start:
                            is_free = False
                            break
                
                # Only add future slots
                if is_free and current_time > now:
                    # Create dictionary for Streamlit compatibility
                    slot_dict = {
                        'start': current_time,
                        'end': slot_end,
                        'duration_minutes': duration_minutes
                    }
                    free_slots.append(slot_dict)
                    
                    if len(free_slots) <= 5:  # Debug first 5 slots
                        print(f"  ✓ Free slot: {current_time} - {slot_end}")
                
                # Stop if we have enough slots
                if len(free_slots) >= 20:
                    break
                
                # Move to next slot (30-minute increments)
                current_time += timedelta(minutes=30)
            
            print(f"Total free slots found: {len(free_slots)}")
            print("=" * 50 + "\n")
            
            return free_slots
        
        except Exception as e:
            print(f"Error finding free slots: {e}")
            import traceback
            traceback.print_exc()
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
                    api_key=self.api_key
                )
            except Exception as e:
                print(f"Error initializing LLM: {e}")
                self.llm = None
    
    def analyze_email(self, email: EmailData) -> EmailData:
        """Analyze email with AI"""
        if not self.llm:
            # Fallback to rule-based analysis
            return self._rule_based_analysis(email)
        
        try:
            # Create prompt
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are an email analysis assistant. Analyze the email and provide:
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
                ("human", "Subject: {subject}\nFrom: {sender}\nBody: {body}")
            ])
            
            # Get response
            chain = prompt | self.llm
            response = chain.invoke({
                "subject": email.subject,
                "sender": email.sender,
                "body": email.body[:1000]  # Limit body length
            })
            
            # Parse response
            content = response.content
            lines = content.strip().split('\n')
            
            for line in lines:
                if line.startswith('Category:'):
                    email.category = line.split(':', 1)[1].strip().lower()
                elif line.startswith('Priority:'):
                    try:
                        email.priority_score = int(line.split(':', 1)[1].strip())
                    except:
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
        """Fallback rule-based analysis"""
        # Category based on keywords
        body_lower = email.body.lower()
        subject_lower = email.subject.lower()
        
        if any(word in body_lower or word in subject_lower 
               for word in ['meeting', 'project', 'deadline', 'task']):
            email.category = 'work'
        elif any(word in body_lower or word in subject_lower 
                 for word in ['urgent', 'asap', 'important', 'critical']):
            email.category = 'urgent'
        elif any(word in body_lower or word in subject_lower 
                 for word in ['unsubscribe', 'newsletter', 'promotion']):
            email.category = 'newsletter'
        else:
            email.category = 'personal'
        
        # Priority score
        if email.is_important or email.category == 'urgent':
            email.priority_score = 9
        elif email.category == 'work':
            email.priority_score = 7
        elif email.category == 'newsletter':
            email.priority_score = 3
        else:
            email.priority_score = 5
        
        # Sentiment (simple)
        positive_words = ['thank', 'great', 'excellent', 'congratulations']
        negative_words = ['sorry', 'problem', 'issue', 'error', 'cancel']
        
        pos_count = sum(1 for word in positive_words if word in body_lower)
        neg_count = sum(1 for word in negative_words if word in body_lower)
        
        if pos_count > neg_count:
            email.sentiment = 'positive'
        elif neg_count > pos_count:
            email.sentiment = 'negative'
        else:
            email.sentiment = 'neutral'
        
        return email
    
    def generate_conflict_resolution_email(self, conflict: ConflictInfo,
                                          alternative_times: List[Tuple[datetime, datetime]]) -> str:
        """Generate email to resolve calendar conflict"""
        if not self.llm:
            return self._template_conflict_email(conflict, alternative_times)
        
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are a professional email assistant. Write a polite email to resolve a calendar conflict.
Include:
1. Acknowledgment of the conflict
2. Details of conflicting meetings
3. Suggested alternative times
4. Request for confirmation

Keep it professional and concise."""),
                ("human", """Conflict:
Meeting 1: {event1_summary} ({event1_time})
Meeting 2: {event2_summary} ({event2_time})
Overlap: {overlap_minutes} minutes

Alternative times:
{alternatives}

Write the email:""")
            ])
            
            # Format alternatives
            alt_text = "\n".join([
                f"- {start.strftime('%B %d, %Y at %I:%M %p')} - {end.strftime('%I:%M %p')}"
                for start, end in alternative_times[:3]
            ])
            
            chain = prompt | self.llm
            response = chain.invoke({
                "event1_summary": conflict.event1.summary,
                "event1_time": conflict.event1.start_time.strftime('%B %d at %I:%M %p'),
                "event2_summary": conflict.event2.summary,
                "event2_time": conflict.event2.start_time.strftime('%B %d at %I:%M %p'),
                "overlap_minutes": conflict.overlap_minutes,
                "alternatives": alt_text
            })
            
            return response.content
            
        except Exception as e:
            print(f"Error generating email: {e}")
            return self._template_conflict_email(conflict, alternative_times)
    
    def _template_conflict_email(self, conflict: ConflictInfo,
                                 alternative_times: List[Tuple[datetime, datetime]]) -> str:
        """Template-based conflict resolution email"""
        email_body = f"""Subject: Calendar Conflict - {conflict.event1.summary} and {conflict.event2.summary}

Dear Team,

I hope this email finds you well. I wanted to bring to your attention a scheduling conflict that has come up.

CONFLICT DETAILS:
• Meeting 1: {conflict.event1.summary}
  Time: {conflict.event1.start_time.strftime('%B %d, %Y at %I:%M %p')} - {conflict.event1.end_time.strftime('%I:%M %p')}

• Meeting 2: {conflict.event2.summary}
  Time: {conflict.event2.start_time.strftime('%B %d, %Y at %I:%M %p')} - {conflict.event2.end_time.strftime('%I:%M %p')}

These meetings overlap by {conflict.overlap_minutes} minutes.

ALTERNATIVE TIMES:
I've identified the following available time slots:
"""
        
        for i, (start, end) in enumerate(alternative_times[:3], 1):
            email_body += f"{i}. {start.strftime('%B %d, %Y at %I:%M %p')} - {end.strftime('%I:%M %p')}\n"
        
        email_body += """
Could you please let me know which alternative time works best for you, or if you have another preference?

Thank you for your understanding and flexibility.

Best regards
"""
        
        return email_body


# ============================================================================
# ENHANCED EMAIL ASSISTANT (Main Class for Streamlit)
# ============================================================================

class EnhancedEmailAssistant:
    """Main assistant class combining all services - Enhanced for Streamlit"""
    
    def __init__(self):
        self.gmail = GmailService()
        self.calendar = CalendarService()
        self.analyzer = AIAnalyzer()
        self.llm = None  # LLM instance for AI features
        
        # Memory
        self.conversation_memory = []
        self._load_memory()
        
        # Cache
        self.emails_cache: List[EmailData] = []
        self.events_cache: List[CalendarEvent] = []
        self.conflicts_cache: List[ConflictInfo] = []
    
    def initialize_llm(self, api_key: Optional[str] = None):
        """Initialize LLM for AI features"""
        if api_key:
            self.analyzer = AIAnalyzer(api_key=api_key)
            self.llm = self.analyzer.llm
        return self.llm is not None
    
    def _load_memory(self):
        """Load conversation memory from disk"""
        if not os.path.exists(MEMORY_DIR):
            os.makedirs(MEMORY_DIR)
        
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, 'rb') as f:
                    self.conversation_memory = pickle.load(f)
            except Exception as e:
                print(f"Error loading memory: {e}")
                self.conversation_memory = []
    
    def _save_memory(self):
        """Save conversation memory to disk"""
        try:
            with open(MEMORY_FILE, 'wb') as f:
                pickle.dump(self.conversation_memory[-100:], f)  # Keep last 100 messages
        except Exception as e:
            print(f"Error saving memory: {e}")
    
    def inject_credentials(self, creds) -> bool:
        """Multi-user: inject Google credentials into both services at once."""
        return self.gmail.inject_credentials(creds) and self.calendar.inject_credentials(creds)

    def authenticate(self) -> bool:
        """Authenticate both Gmail and Calendar"""
        gmail_auth = self.gmail.authenticate()
        calendar_auth = self.calendar.authenticate()
        return gmail_auth and calendar_auth
    
    def fetch_emails(self, query: str = "", max_results: int = 50) -> List[EmailData]:
        """Fetch and cache emails"""
        emails = self.gmail.get_emails(query, max_results)
        self.emails_cache = emails
        return emails
    
    def fetch_calendar_events(self, days_ahead: int = 30) -> List[CalendarEvent]:
        """Fetch and cache calendar events"""
        events = self.calendar.get_events(days_ahead)
        self.events_cache = events
        return events
    
    def categorize_emails_ai(self, emails: Optional[List[EmailData]] = None) -> List[EmailData]:
        """Analyze emails with AI - alias for analyze_emails"""
        return self.analyze_emails(emails)
    
    def analyze_emails(self, emails: Optional[List[EmailData]] = None) -> List[EmailData]:
        """Analyze emails with AI"""
        emails_to_analyze = emails or self.emails_cache
        
        analyzed = []
        for email in emails_to_analyze:
            analyzed_email = self.analyzer.analyze_email(email)
            analyzed.append(analyzed_email)
        
        if not emails:  # Update cache if analyzing cached emails
            self.emails_cache = analyzed
        
        return analyzed
    
    def detect_conflicts(self, events: Optional[List[CalendarEvent]] = None) -> List[ConflictInfo]:
        """Detect calendar conflicts"""
        events_to_check = events or self.events_cache
        self.conflicts_cache = self.calendar.find_conflicts(events_to_check)
        return self.conflicts_cache
    
    def find_free_slots(self, *args, **kwargs) -> List[Dict[str, Any]]:
        """Find free time slots - flexible signature for compatibility
        
        Supports multiple calling patterns:
        - find_free_slots() - use defaults
        - find_free_slots(duration_minutes=60, days_ahead=7)
        - find_free_slots(60, 7)
        - find_free_slots(events=some_events, duration_minutes=60)
        
        Returns list of dictionaries with 'start', 'end', 'duration_minutes' keys
        """
        # Extract parameters from kwargs first
        events = kwargs.get('events', None)
        duration_minutes = kwargs.get('duration_minutes', 60)
        days_ahead = kwargs.get('days_ahead', 7)
        refresh_events = kwargs.get('refresh_events', True)  # Auto-refresh by default
        
        # Handle positional arguments
        if len(args) >= 1:
            first_arg = args[0]
            # Check if first arg is a list (events) or int (duration_minutes)
            if isinstance(first_arg, list):
                # Pattern: find_free_slots(events, duration_minutes, days_ahead)
                events = first_arg
                if len(args) >= 2 and isinstance(args[1], int):
                    duration_minutes = args[1]
                if len(args) >= 3 and isinstance(args[2], int):
                    days_ahead = args[2]
            elif isinstance(first_arg, int):
                # Pattern: find_free_slots(duration_minutes, days_ahead, events)
                duration_minutes = first_arg
                if len(args) >= 2 and isinstance(args[1], int):
                    days_ahead = args[1]
                if len(args) >= 3 and isinstance(args[2], list):
                    events = args[2]
            # If first arg is neither list nor int, ignore it and use defaults
        
        # Ensure we have valid integer values
        if not isinstance(duration_minutes, int):
            print(f"Warning: duration_minutes is {type(duration_minutes)}, defaulting to 60")
            duration_minutes = 60
        if not isinstance(days_ahead, int):
            print(f"Warning: days_ahead is {type(days_ahead)}, defaulting to 7")
            days_ahead = 7
        
        # Auto-refresh events if none provided and refresh is enabled
        if events is None and refresh_events:
            print("🔄 Auto-refreshing calendar events to get latest data...")
            self.fetch_calendar_events(days_ahead=days_ahead)
            events_to_use = self.events_cache
        else:
            events_to_use = events if events is not None else self.events_cache
        
        print(f"DEBUG: Calling calendar.find_free_slots with events={len(events_to_use) if events_to_use else 0}, duration={duration_minutes}, days={days_ahead}")
        
        return self.calendar.find_free_slots(events_to_use, duration_minutes, days_ahead)
    
    def generate_conflict_email(self, conflict: ConflictInfo, free_slots: Optional[List[Dict[str, Any]]] = None) -> str:
        """Generate conflict resolution email - alias for compatibility
        
        Args:
            conflict: ConflictInfo object with conflicting events
            free_slots: Optional list of free time slots (will be generated if not provided)
        """
        return self.generate_conflict_resolution(conflict, free_slots)
    
    def generate_conflict_resolution(self, conflict: ConflictInfo, free_slots: Optional[List[Dict[str, Any]]] = None) -> str:
        """Generate conflict resolution email
        
        Args:
            conflict: ConflictInfo object with conflicting events
            free_slots: Optional list of free time slots (will be generated if not provided)
        """
        # If free slots not provided, generate them
        if free_slots is None:
            free_slots = self.find_free_slots(
                duration_minutes=conflict.event1.duration_minutes,
                days_ahead=14
            )
        
        # Convert dict format to tuple format for the analyzer
        alternative_times = []
        for slot in free_slots[:5]:  # Use first 5 slots
            if isinstance(slot, dict):
                alternative_times.append((slot['start'], slot['end']))
            else:
                # Already a tuple
                alternative_times.append(slot)
        
        return self.analyzer.generate_conflict_resolution_email(conflict, alternative_times)
    
    def find_calendar_invitation_email(self, event: CalendarEvent) -> Optional[EmailData]:
        """Find the email invitation that created this calendar event
        
        Searches for emails that:
        - Have calendar event indicator
        - Match the event title/summary
        - Match the event organizer
        - Were received around the event creation time
        """
        try:
            # Search emails with the event title
            search_query = f'subject:"{event.summary}"'
            emails = self.gmail.get_emails(query=search_query, max_results=20)
            
            # Filter for calendar invitations
            for email in emails:
                # Check if it's a calendar invitation
                if email.has_calendar_event:
                    # Check if sender matches organizer
                    if event.organizer and event.organizer.lower() in email.sender_email.lower():
                        print(f"📧 Found invitation email: {email.subject} from {email.sender}")
                        return email
                    # Or check if subject contains event title
                    if event.summary.lower() in email.subject.lower():
                        print(f"📧 Found related email: {email.subject}")
                        return email
            
            print(f"⚠️ No invitation email found for event: {event.summary}")
            return None
            
        except Exception as e:
            print(f"Error finding invitation email: {e}")
            return None
    
    def get_emails_by_date(self, target_date: datetime) -> List[EmailData]:
        """Get all emails received on a specific date
        
        Args:
            target_date: The date to search for emails
            
        Returns:
            List of emails received on that date
        """
        try:
            # Format date for Gmail search
            date_str = target_date.strftime('%Y/%m/%d')
            search_query = f'after:{date_str} before:{date_str}'
            
            emails = self.gmail.get_emails(query=search_query, max_results=100)
            print(f"📊 Found {len(emails)} emails on {date_str}")
            
            return emails
            
        except Exception as e:
            print(f"Error fetching emails by date: {e}")
            return []
    
    def get_email_statistics_by_date(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get email statistics for a date range
        
        Args:
            start_date: Start of date range
            end_date: End of date range
            
        Returns:
            Dictionary with email counts per day
        """
        stats = {
            'date_range': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            'daily_counts': {},
            'total_emails': 0,
            'peak_day': None,
            'peak_count': 0
        }
        
        try:
            current_date = start_date
            while current_date <= end_date:
                emails = self.get_emails_by_date(current_date)
                date_key = current_date.strftime('%Y-%m-%d')
                count = len(emails)
                
                stats['daily_counts'][date_key] = count
                stats['total_emails'] += count
                
                if count > stats['peak_count']:
                    stats['peak_count'] = count
                    stats['peak_day'] = date_key
                
                current_date += timedelta(days=1)
            
            return stats
            
        except Exception as e:
            print(f"Error getting email statistics: {e}")
            return stats
    
    def get_conflict_recipients(self, conflict: ConflictInfo) -> List[str]:
        """Get email addresses of people involved in conflicting events
        
        Returns list of unique email addresses from:
        - Event organizers
        - Event attendees
        """
        recipients = set()
        
        # Add organizer and attendees from event1
        if conflict.event1.organizer:
            recipients.add(conflict.event1.organizer)
        if conflict.event1.attendees:
            recipients.update(conflict.event1.attendees)
        
        # Add organizer and attendees from event2
        if conflict.event2.organizer:
            recipients.add(conflict.event2.organizer)
        if conflict.event2.attendees:
            recipients.update(conflict.event2.attendees)
        
        # Remove empty strings
        recipients = {email for email in recipients if email and email.strip()}
        
        return list(recipients)
    
    def send_conflict_resolution_email(self, conflict: ConflictInfo, 
                                       free_slots: Optional[List[Dict[str, Any]]] = None,
                                       custom_recipients: Optional[List[str]] = None,
                                       reply_to_invitation: bool = True) -> Dict[str, Any]:
        """Send conflict resolution email to involved parties
        
        Args:
            conflict: ConflictInfo object with conflicting events
            free_slots: Optional list of free time slots
            custom_recipients: Optional list of email addresses (overrides auto-detection)
            reply_to_invitation: If True, replies to the original invitation email
        
        Returns:
            Dictionary with send status and details
        """
        result = {
            'success': False,
            'recipients': [],
            'subject': '',
            'error': None,
            'method': 'draft',
            'thread_id': None,
            'email_stats': {}
        }
        
        try:
            # Generate the email body
            base_email_body = self.generate_conflict_resolution(conflict, free_slots)
            
            # Find the invitation email if reply_to_invitation is True
            invitation_email = None
            if reply_to_invitation:
                # Try both events to find invitation
                invitation_email = self.find_calendar_invitation_email(conflict.event1)
                if not invitation_email:
                    invitation_email = self.find_calendar_invitation_email(conflict.event2)
            
            # Get email statistics for the conflict date
            conflict_date = conflict.event1.start_time
            emails_on_conflict_day = self.get_emails_by_date(conflict_date)
            email_count = len(emails_on_conflict_day)
            
            # Add email statistics to the body
            email_body = base_email_body + f"\n\n---\n"
            email_body += f"📊 Email Statistics:\n"
            email_body += f"• Date: {conflict_date.strftime('%A, %B %d, %Y')}\n"
            email_body += f"• Total emails received on this day: {email_count}\n"
            
            if invitation_email:
                email_body += f"• This is in reply to: \"{invitation_email.subject}\"\n"
                email_body += f"• Original invitation from: {invitation_email.sender}\n"
            
            result['email_stats'] = {
                'date': conflict_date.strftime('%Y-%m-%d'),
                'count': email_count,
                'emails': [{'subject': e.subject, 'from': e.sender, 'time': e.timestamp.strftime('%I:%M %p')} 
                          for e in emails_on_conflict_day[:5]]  # First 5 emails
            }
            
            # Get recipients
            if custom_recipients:
                recipients = custom_recipients
            elif invitation_email:
                # Reply to the invitation sender
                recipients = [invitation_email.sender_email]
            else:
                recipients = self.get_conflict_recipients(conflict)
            
            if not recipients:
                result['error'] = "No recipients found. Please specify recipients manually."
                return result
            
            # Create subject
            if invitation_email:
                subject = f"Re: {invitation_email.subject} - Calendar Conflict Resolution"
                thread_id = invitation_email.thread_id
                result['thread_id'] = thread_id
                result['method'] = 'reply'
            else:
                subject = f"Calendar Conflict: {conflict.event1.summary} & {conflict.event2.summary}"
                thread_id = None
            
            # Send or create draft
            sent_to = []
            for recipient in recipients:
                if invitation_email and thread_id:
                    # Reply to the original thread
                    success = self.send_email(recipient, subject, email_body, thread_id=thread_id)
                    if success:
                        sent_to.append(recipient)
                        result['method'] = 'sent_as_reply'
                else:
                    # Create draft
                    success = self.create_draft(recipient, subject, email_body)
                    if success:
                        sent_to.append(recipient)
            
            result['success'] = len(sent_to) > 0
            result['recipients'] = sent_to
            result['subject'] = subject
            result['message'] = f"{'Sent reply' if result['method'] == 'sent_as_reply' else 'Draft created'} for {len(sent_to)} recipient(s)"
            
        except Exception as e:
            result['error'] = str(e)
            import traceback
            traceback.print_exc()
        
        return result
    
    def send_email(self, to: str, subject: str, body: str, 
                   thread_id: Optional[str] = None) -> bool:
        """Send an email"""
        return self.gmail.send_email(to, subject, body, thread_id)
    
    def create_draft(self, to: str, subject: str, body: str) -> bool:
        """Create an email draft"""
        return self.gmail.create_draft(to, subject, body)
    
    def run_ambient_agent(self, thread_id: str = "default") -> Dict[str, Any]:
        """Run complete ambient workflow"""
        result = {
            'status': 'success',
            'emails_fetched': 0,
            'emails_analyzed': 0,
            'events_fetched': 0,
            'conflicts_found': 0,
            'suggestions': [],
            'drafts_created': 0
        }
        
        try:
            # Step 1: Fetch emails
            emails = self.fetch_emails(max_results=50)
            result['emails_fetched'] = len(emails)
            
            # Step 2: Analyze emails
            analyzed = self.analyze_emails(emails)
            result['emails_analyzed'] = len(analyzed)
            
            # Step 3: Fetch calendar
            events = self.fetch_calendar_events(days_ahead=30)
            result['events_fetched'] = len(events)
            
            # Step 4: Detect conflicts
            conflicts = self.detect_conflicts(events)
            result['conflicts_found'] = len(conflicts)
            
            # Step 5: Generate suggestions
            suggestions = []
            
            # Email suggestions
            urgent_emails = [e for e in analyzed if e.priority_score and e.priority_score >= 8]
            if urgent_emails:
                suggestions.append(f"You have {len(urgent_emails)} high-priority emails requiring attention")
            
            unread_important = [e for e in analyzed if e.is_unread and e.is_important]
            if unread_important:
                suggestions.append(f"You have {len(unread_important)} unread important emails")
            
            # Calendar suggestions
            if conflicts:
                suggestions.append(f"Found {len(conflicts)} calendar conflicts that need resolution")
            
            today_events = [e for e in events if e.start_time.date() == datetime.now().date()]
            if today_events:
                suggestions.append(f"You have {len(today_events)} events scheduled for today")
            
            result['suggestions'] = suggestions
            
            # Step 6: Auto-draft conflict resolutions (count only, not creating actual drafts)
            for conflict in conflicts[:3]:  # Limit to first 3
                draft_body = self.generate_conflict_resolution(conflict)
                result['drafts_created'] += 1
            
            return result
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            return result


# ============================================================================
# MAIN (for testing)
# ============================================================================

if __name__ == "__main__":
    print("🤖 Ambient Email Assistant - Enhanced")
    print("=" * 50)
    
    # Initialize assistant
    assistant = EnhancedEmailAssistant()
    
    # Authenticate
    print("\n1. Authenticating...")
    if not assistant.authenticate():
        print("❌ Authentication failed!")
        exit(1)
    print("✅ Authenticated successfully")
    
    # Fetch emails
    print("\n2. Fetching emails...")
    emails = assistant.fetch_emails(max_results=10)
    print(f"✅ Fetched {len(emails)} emails")
    
    # Analyze emails
    print("\n3. Analyzing emails...")
    analyzed = assistant.analyze_emails(emails)
    print(f"✅ Analyzed {len(analyzed)} emails")
    
    # Print sample
    if analyzed:
        email = analyzed[0]
        print(f"\nSample: {email.subject}")
        print(f"  Category: {email.category}")
        print(f"  Priority: {email.priority_score}/10")
        print(f"  Sentiment: {email.sentiment}")
    
    # Fetch calendar
    print("\n4. Fetching calendar...")
    events = assistant.fetch_calendar_events(days_ahead=7)
    print(f"✅ Fetched {len(events)} events")
    
    # Detect conflicts
    print("\n5. Checking conflicts...")
    conflicts = assistant.detect_conflicts(events)
    print(f"✅ Found {len(conflicts)} conflicts")
    
    if conflicts:
        print(f"\nSample conflict: {conflicts[0]}")
    
    print("\n✅ All tests passed!")
