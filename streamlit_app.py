"""
Streamlit Email Assistant with AI & Calendar Integration
"""

import streamlit as st
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import json
import pickle
import time

# ── Fix import path for Streamlit Cloud ──────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Page configuration
st.set_page_config(
    page_title="AI Email Assistant",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Import the enhanced assistant
try:
    from ambient_email_assistant_enhanced import EnhancedEmailAssistant, EmailData, CalendarEvent
except ImportError as e:
    st.error(f"❌ Cannot import ambient_email_assistant_enhanced.\nError: {e}\nDirectory: {BASE_DIR}\nFiles: {os.listdir(BASE_DIR)}")
    st.stop()

# Custom CSS
st.markdown("""
<style>
    :root {
        --primary-color: #00E5A0;
        --secondary-color: #00B8D4;
        --accent-color: #FF6B6B;
        --warning-color: #FFB800;
        --dark-bg: #0D0D0F;
        --card-bg: #1C1C21;
        --border-color: #2A2A30;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: #1a1a1a; }
    ::-webkit-scrollbar-thumb { background: #00E5A0; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #00B8D4; }
    .main-header {
        font-size: 2.5rem; font-weight: 700;
        background: linear-gradient(135deg, #00E5A0 0%, #00B8D4 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 1rem; text-align: center; padding: 1rem 0;
    }
    .sub-header {
        font-size: 1.8rem; font-weight: 600; color: #00E5A0;
        margin: 1.5rem 0 1rem 0; border-bottom: 2px solid #00E5A0; padding-bottom: 0.5rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #1C1C21 0%, #232328 100%);
        padding: 1.5rem; border-radius: 12px; border: 1px solid #00E5A0;
        box-shadow: 0 4px 16px rgba(0,229,160,0.1); margin-bottom: 1rem; transition: all 0.3s ease;
    }
    .metric-card:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,229,160,0.2); }
    .email-card {
        background: #1C1C21; padding: 1rem; border-radius: 10px;
        border-left: 4px solid #00E5A0; margin-bottom: 0.8rem; transition: all 0.2s ease;
    }
    .email-card:hover { background: #232328; border-left-color: #00B8D4; transform: translateX(4px); }
    .conflict-card {
        background: linear-gradient(135deg, #2a1a1a 0%, #3a2020 100%);
        padding: 1.2rem; border-radius: 10px; border-left: 4px solid #FF6B6B;
        margin-bottom: 0.8rem; box-shadow: 0 4px 12px rgba(255,107,107,0.1);
    }
    .calendar-event-card {
        background: #1C1C21; padding: 1rem; border-radius: 8px;
        border-left: 4px solid #00B8D4; margin-bottom: 0.6rem;
    }
    .stButton>button {
        background: linear-gradient(135deg, #00E5A0 0%, #00B8D4 100%);
        color: white; font-weight: 600; border: none; padding: 0.6rem 2rem;
        border-radius: 8px; transition: all 0.3s ease; box-shadow: 0 2px 8px rgba(0,229,160,0.2);
    }
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,229,160,0.4); }
    .success-box {
        background: linear-gradient(135deg, #1a2a1a 0%, #1a3a1a 100%);
        border: 1px solid #00E5A0; padding: 1rem; border-radius: 8px; margin: 1rem 0;
    }
    .warning-box {
        background: linear-gradient(135deg, #2a2a1a 0%, #3a3020 100%);
        border: 1px solid #FFB800; padding: 1rem; border-radius: 8px; margin: 1rem 0;
    }
    .error-box {
        background: linear-gradient(135deg, #2a1a1a 0%, #3a2020 100%);
        border: 1px solid #FF6B6B; padding: 1rem; border-radius: 8px; margin: 1rem 0;
    }
    .badge { display: inline-block; padding: 0.3rem 0.8rem; border-radius: 20px; font-size: 0.85rem; font-weight: 600; margin-right: 0.5rem; }
    .badge-unread { background: #00B8D4; color: white; }
    .badge-important { background: #FFB800; color: white; }
    .badge-calendar { background: #8B5CF6; color: white; }
    .stat-container { text-align: center; padding: 1rem; }
    .stat-value {
        font-size: 2.5rem; font-weight: 700;
        background: linear-gradient(135deg, #00E5A0 0%, #00B8D4 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .stat-label { font-size: 0.9rem; color: #A3A3A3; margin-top: 0.5rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: #1C1C21; padding: 0.5rem; border-radius: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: transparent; border-radius: 8px; color: #A3A3A3; font-weight: 600; padding: 0.8rem 1.5rem; }
    .stTabs [aria-selected="true"] { background: linear-gradient(135deg, #00E5A0 0%, #00B8D4 100%); color: white; }
    .stTextInput>div>div>input, .stTextArea>div>div>textarea { background-color: #1C1C21; border: 1px solid #2A2A30; border-radius: 8px; color: white; }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #0D0D0F 0%, #18181B 100%); }
    .stProgress > div > div > div > div { background: linear-gradient(90deg, #00E5A0 0%, #00B8D4 100%); }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────
def init_session_state():
    defaults = {
        'assistant': None, 'authenticated': False,
        'emails': [], 'calendar_events': [], 'conflicts': [],
        'current_view': 'dashboard', 'selected_email': None,
        'workflow_result': None, 'loading': False,
        'email_filter': 'all', 'sort_by': 'date_desc', 'show_ai_enabled': False
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# ── Helpers ───────────────────────────────────────────────────
def show_loading(message="Loading..."):
    return st.spinner(message)

def show_success(message):
    st.success(f"✅ {message}")

def show_error(message):
    st.error(f"❌ {message}")

def show_info(message):
    st.info(f"ℹ️ {message}")

def show_warning(message):
    st.warning(f"⚠️ {message}")

def safe_snippet(email_obj):
    """Safely get a preview snippet from an email."""
    return (getattr(email_obj, 'snippet', None) or getattr(email_obj, 'preview', None) or '')[:120]

def init_assistant():
    if st.session_state.assistant is None:
        with show_loading("Initializing assistant..."):
            try:
                st.session_state.assistant = EnhancedEmailAssistant()
                return True
            except Exception as e:
                show_error(f"Error initializing assistant: {e}")
                return False
    return True

def authenticate():
    if st.session_state.authenticated:
        return True
    with show_loading("Authenticating with Google..."):
        try:
            st.session_state.assistant.authenticate()   # raises with real error on failure
            st.session_state.authenticated = True

            # Try OpenAI key from Streamlit Secrets first, then env
            openai_key = None
            try:
                openai_key = st.secrets.get("OPENAI_API_KEY") or st.secrets.get("google", {}).get("openai_api_key")
            except Exception:
                pass
            if not openai_key:
                openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                st.session_state.assistant.initialize_llm(api_key=openai_key)
                st.session_state.show_ai_enabled = True
            return True
        except Exception as e:
            show_error(f"Authentication failed: {e}")
            st.info("💡 If you see a token refresh error, re-run the app locally to get a fresh token.json, then update Streamlit Secrets.")
            return False

def fetch_emails(max_results=50, query=''):
    with show_loading(f"Fetching {max_results} emails..."):
        try:
            emails = st.session_state.assistant.fetch_emails(max_results=max_results, query=query)
            st.session_state.emails = emails
            return emails
        except Exception as e:
            show_error(f"Error fetching emails: {e}")
            return []

def fetch_calendar(days_ahead=30):
    with show_loading("Fetching calendar events..."):
        try:
            events = st.session_state.assistant.fetch_calendar_events(days_ahead=days_ahead)
            st.session_state.calendar_events = events
            return events
        except Exception as e:
            show_error(f"Error fetching calendar: {e}")
            return []

def detect_conflicts():
    with show_loading("Detecting conflicts..."):
        try:
            conflicts = st.session_state.assistant.detect_conflicts(st.session_state.calendar_events)
            st.session_state.conflicts = conflicts
            return conflicts
        except Exception as e:
            show_error(f"Error detecting conflicts: {e}")
            return []

def run_workflow():
    with show_loading("Running AI workflow... This may take a minute..."):
        try:
            progress_bar = st.progress(0)
            status_text = st.empty()
            status_text.text("Fetching emails...")
            progress_bar.progress(20)
            time.sleep(0.5)

            result = st.session_state.assistant.run_ambient_agent(thread_id="streamlit-session")

            progress_bar.progress(100)
            status_text.text("Complete!")
            time.sleep(0.5)
            progress_bar.empty()
            status_text.empty()

            st.session_state.workflow_result = result
            st.session_state.emails          = result.get('emails', [])
            st.session_state.calendar_events = result.get('calendar_events', [])
            st.session_state.conflicts       = result.get('conflicts', [])
            return result
        except Exception as e:
            show_error(f"Error running workflow: {e}")
            return None

def filter_emails(emails, filter_type='all'):
    if filter_type == 'unread':    return [e for e in emails if e.is_unread]
    if filter_type == 'important': return [e for e in emails if e.is_important]
    if filter_type == 'calendar':  return [e for e in emails if e.has_calendar_event]
    return emails

def sort_emails(emails, sort_by='date_desc'):
    if sort_by == 'date_desc': return sorted(emails, key=lambda e: e.timestamp, reverse=True)
    if sort_by == 'date_asc':  return sorted(emails, key=lambda e: e.timestamp)
    if sort_by == 'sender':    return sorted(emails, key=lambda e: e.sender)
    if sort_by == 'priority':  return sorted(emails, key=lambda e: (e.priority_score or 0), reverse=True)
    return emails

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<h2 style="text-align: center;">📧 AI Email Assistant</h2>', unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("🔐 Connection")

    if not st.session_state.authenticated:
        if st.button("🔑 Connect to Gmail", use_container_width=True, type="primary"):
            if init_assistant() and authenticate():
                show_success("Successfully authenticated!")
                st.rerun()
    else:
        st.markdown('<div class="success-box"><strong>✅ Connected to Gmail</strong></div>', unsafe_allow_html=True)
        if st.session_state.show_ai_enabled:
            st.markdown('<div class="success-box"><strong>🤖 AI Features Enabled</strong></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="warning-box"><strong>⚠️ AI features disabled</strong><br><small>Add OPENAI_API_KEY to Secrets</small></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("🧭 Navigation")

    nav_options = {
        '📊 Dashboard': 'dashboard', '📧 Emails': 'emails',
        '📅 Calendar': 'calendar',   '⚠️ Conflicts': 'conflicts',
        '✍️ Compose': 'compose',     '🤖 AI Workflow': 'workflow'
    }
    for label, view_id in nav_options.items():
        btn_type = "primary" if st.session_state.current_view == view_id else "secondary"
        if st.button(label, use_container_width=True, key=f"nav_{view_id}", type=btn_type):
            st.session_state.current_view = view_id
            st.rerun()

    st.markdown("---")
    if st.session_state.authenticated:
        st.subheader("⚡ Quick Actions")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄", use_container_width=True, help="Refresh"):
                fetch_emails(); fetch_calendar(); st.rerun()
        with col2:
            if st.button("🤖", use_container_width=True, help="Run AI"):
                run_workflow(); st.rerun()
        st.markdown("---")
        st.subheader("📊 Quick Stats")
        st.metric("Emails",    len(st.session_state.emails))
        st.metric("Events",    len(st.session_state.calendar_events))
        st.metric("Conflicts", len(st.session_state.conflicts))

# ── Main content ──────────────────────────────────────────────
if not st.session_state.authenticated:
    st.markdown('<h1 class="main-header">🚀 Welcome to AI Email Assistant</h1>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown('<div class="metric-card"><div style="text-align:center"><div style="font-size:3rem">📧</div><h3 style="color:#00E5A0">Smart Email</h3><p style="color:#A3A3A3">Manage your Gmail with AI-powered insights and automation</p></div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="metric-card"><div style="text-align:center"><div style="font-size:3rem">📅</div><h3 style="color:#00B8D4">Calendar Sync</h3><p style="color:#A3A3A3">Detect conflicts and find free slots automatically</p></div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown('<div class="metric-card"><div style="text-align:center"><div style="font-size:3rem">🤖</div><h3 style="color:#8B5CF6">AI Powered</h3><p style="color:#A3A3A3">Smart categorization, prioritization, and auto-responses</p></div></div>', unsafe_allow_html=True)
    st.markdown("---")
    col1, col2 = st.columns([2,1])
    with col1:
        st.markdown("""
        ## 🎯 Getting Started
        ### Step 1: Connect Your Gmail
        Click **"Connect to Gmail"** in the sidebar to authenticate.
        ### Step 2: Explore Features
        - 📊 **Dashboard** – Overview of emails and calendar
        - 📧 **Emails** – Read, filter, and search emails
        - 📅 **Calendar** – View events and manage schedule
        - ⚠️ **Conflicts** – Resolve scheduling conflicts
        - ✍️ **Compose** – Write and send emails
        - 🤖 **AI Workflow** – Run intelligent automation
        """)
    with col2:
        st.markdown('<div class="warning-box"><h3>📋 Prerequisites</h3><ul><li>✅ Google Cloud credentials</li><li>✅ Gmail account</li><li>⚪ OpenAI API key (optional)</li></ul></div><div class="success-box"><h3>🔒 Privacy</h3><p>Your data stays secure. We use Google OAuth and never store your credentials.</p></div>', unsafe_allow_html=True)
    st.info("👈 **Start by clicking 'Connect to Gmail' in the sidebar**")

elif st.session_state.current_view == 'dashboard':
    st.markdown('<h1 class="main-header">📊 Dashboard</h1>', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f'<div class="metric-card"><div class="stat-container"><div class="stat-value">{len(st.session_state.emails)}</div><div class="stat-label">Total Emails</div><div style="color:#00B8D4;font-size:0.9rem;margin-top:0.5rem">{sum(1 for e in st.session_state.emails if e.is_unread)} unread</div></div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="metric-card"><div class="stat-container"><div class="stat-value">{len(st.session_state.calendar_events)}</div><div class="stat-label">Calendar Events</div><div style="color:#8B5CF6;font-size:0.9rem;margin-top:0.5rem">Next 30 days</div></div></div>', unsafe_allow_html=True)
    with col3:
        cc = len(st.session_state.conflicts); color = "#FF6B6B" if cc > 0 else "#00E5A0"
        st.markdown(f'<div class="metric-card"><div class="stat-container"><div class="stat-value" style="background:linear-gradient(135deg,{color} 0%,{color} 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent">{cc}</div><div class="stat-label">Conflicts</div><div style="color:{color};font-size:0.9rem;margin-top:0.5rem">{"Needs attention" if cc>0 else "All clear"}</div></div></div>', unsafe_allow_html=True)
    with col4:
        ic = sum(1 for e in st.session_state.emails if e.is_important)
        st.markdown(f'<div class="metric-card"><div class="stat-container"><div class="stat-value">{ic}</div><div class="stat-label">Important</div><div style="color:#FFB800;font-size:0.9rem;margin-top:0.5rem">Starred emails</div></div></div>', unsafe_allow_html=True)
    st.markdown("---")
    col_left, col_right = st.columns([2,1])
    with col_left:
        st.markdown('<h2 class="sub-header">📬 Recent Emails</h2>', unsafe_allow_html=True)
        if st.session_state.emails:
            for email in st.session_state.emails[:8]:
                unread_badge    = '<span class="badge badge-unread">Unread</span>'    if email.is_unread         else ''
                important_badge = '<span class="badge badge-important">Important</span>' if email.is_important   else ''
                calendar_badge  = '<span class="badge badge-calendar">Calendar</span>'  if email.has_calendar_event else ''
                snippet = safe_snippet(email)
                st.markdown(f'<div class="email-card"><div style="margin-bottom:0.5rem">{unread_badge}{important_badge}{calendar_badge}</div><strong style="font-size:1.1rem">{email.subject}</strong><br><small style="color:#00B8D4">From: {email.sender}</small> • <small style="color:#A3A3A3">{email.timestamp.strftime("%b %d, %I:%M %p")}</small><br><p style="color:#A3A3A3;margin-top:0.5rem;font-size:0.9rem">{snippet}...</p></div>', unsafe_allow_html=True)
                if st.button("View Details", key=f"view_{email.id}", use_container_width=True):
                    st.session_state.selected_email = email
                    st.session_state.current_view = 'emails'
                    st.rerun()
        else:
            st.markdown('<div class="warning-box"><p>📭 No emails loaded yet.</p><p>Click 🔄 in the sidebar to fetch your emails.</p></div>', unsafe_allow_html=True)
    with col_right:
        st.markdown('<h2 class="sub-header">🎯 AI Insights</h2>', unsafe_allow_html=True)
        if st.session_state.workflow_result:
            result = st.session_state.workflow_result
            st.markdown('<div class="success-box"><strong>✅ Workflow Completed</strong><p style="margin-top:0.5rem;font-size:0.9rem">AI analysis complete</p></div>', unsafe_allow_html=True)
            if result.get('suggestions'):
                st.write("**💡 Top Suggestions:**")
                for i, sug in enumerate(result['suggestions'][:5], 1):
                    title = sug.get('title', str(sug)) if isinstance(sug, dict) else str(sug)
                    desc  = sug.get('description', '') if isinstance(sug, dict) else ''
                    st.markdown(f'<div style="background:#1C1C21;padding:0.8rem;border-radius:6px;margin-bottom:0.5rem;border-left:3px solid #00E5A0"><strong>{i}. {title}</strong><br><small style="color:#A3A3A3">{desc}</small></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="warning-box"><strong>🤖 Run AI Analysis</strong><p style="margin-top:0.5rem;font-size:0.9rem">Get intelligent insights about your emails and calendar</p></div>', unsafe_allow_html=True)
            if st.button("🚀 Run AI Workflow", use_container_width=True, type="primary"):
                run_workflow(); st.rerun()
        st.markdown("---")
        st.write("**📅 Today's Events:**")
        today = datetime.now().date()
        today_events = [e for e in st.session_state.calendar_events if e.start.date() == today]
        if today_events:
            for event in today_events[:5]:
                st.markdown(f'<div class="calendar-event-card"><strong>{event.title}</strong><br><small>⏰ {event.start.strftime("%I:%M %p")} - {event.end.strftime("%I:%M %p")}</small></div>', unsafe_allow_html=True)
        else:
            st.info("No events scheduled for today")

elif st.session_state.current_view == 'emails':
    st.markdown('<h1 class="main-header">📧 Email Manager</h1>', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns([2,1,1,1])
    with col1:
        query = st.text_input("🔍 Search emails", placeholder="e.g., is:unread from:boss@company.com", label_visibility="collapsed")
    with col2:
        max_results = st.number_input("Max", min_value=10, max_value=200, value=50, label_visibility="collapsed")
    with col3:
        if st.button("🔄 Fetch", use_container_width=True, type="primary"):
            fetch_emails(max_results=max_results, query=query); st.rerun()
    with col4:
        if st.button("🤖 Analyze", use_container_width=True):
            if st.session_state.assistant and st.session_state.assistant.llm:
                with show_loading("Analyzing emails with AI..."):
                    categorized = st.session_state.assistant.categorize_emails_ai(st.session_state.emails)
                    st.session_state.emails = categorized
                    show_success("AI analysis complete!"); st.rerun()
            else:
                show_warning("AI features not available. Add OPENAI_API_KEY to Secrets")
    st.markdown("---")
    tab1, tab2, tab3, tab4 = st.tabs(["📬 All", "🔵 Unread", "⭐ Important", "📅 Calendar"])
    with tab1: filter_type = 'all'
    with tab2: filter_type = 'unread'
    with tab3: filter_type = 'important'
    with tab4: filter_type = 'calendar'
    sort_col1, sort_col2 = st.columns([4,1])
    with sort_col2:
        sort_by = st.selectbox("Sort by", ["Date (newest)", "Date (oldest)", "Sender", "Priority"], label_visibility="collapsed")
        sort_map = {"Date (newest)": "date_desc", "Date (oldest)": "date_asc", "Sender": "sender", "Priority": "priority"}
        sort_key = sort_map.get(sort_by, "date_desc")
    filtered_emails = sort_emails(filter_emails(st.session_state.emails, filter_type), sort_key)
    st.write(f"**Showing {len(filtered_emails)} emails**")
    for email in filtered_emails:
        with st.expander(f"{'🔵' if email.is_unread else '✅'} {'⭐' if email.is_important else ''} {email.subject[:60]}... - {email.sender}", expanded=False):
            col1, col2 = st.columns([3,1])
            with col1:
                st.write(f"**From:** {email.sender} ({email.sender_email})")
                st.write(f"**Date:** {email.timestamp.strftime('%A, %B %d, %Y at %I:%M %p')}")
                st.write(f"**Subject:** {email.subject}")
                if email.category or email.priority_score or email.sentiment:
                    st.markdown("---")
                    insight_cols = st.columns(3)
                    if email.category:      insight_cols[0].metric("Category",  email.category)
                    if email.priority_score: insight_cols[1].metric("Priority", f"{email.priority_score:.1f}/10")
                    if email.sentiment:      insight_cols[2].metric("Sentiment", email.sentiment)
            with col2:
                if st.button("📧 Reply", key=f"reply_{email.id}", use_container_width=True):
                    st.session_state.selected_email = email
                    st.session_state.current_view = 'compose'; st.rerun()
            st.markdown("---")
            st.markdown("**Email Body:**")
            st.text_area("", value=email.body, height=250, key=f"body_{email.id}", disabled=True, label_visibility="collapsed")

elif st.session_state.current_view == 'calendar':
    st.markdown('<h1 class="main-header">📅 Calendar Manager</h1>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns([2,1,1])
    with col1: days_ahead = st.slider("Days to look ahead", min_value=7, max_value=90, value=30)
    with col2:
        if st.button("🔄 Refresh Calendar", use_container_width=True, type="primary"):
            fetch_calendar(days_ahead=days_ahead); st.rerun()
    with col3:
        if st.button("⚠️ Check Conflicts", use_container_width=True):
            if not st.session_state.calendar_events: fetch_calendar()
            detect_conflicts(); st.rerun()
    st.markdown("---")
    if st.session_state.calendar_events:
        st.write(f"**Showing {len(st.session_state.calendar_events)} events**")
        events_by_date = {}
        for event in st.session_state.calendar_events:
            dk = event.start.date()
            events_by_date.setdefault(dk, []).append(event)
        for date in sorted(events_by_date.keys()):
            st.markdown(f'<h3 style="color:#00B8D4;margin-top:1.5rem">📆 {date.strftime("%A, %B %d, %Y")}</h3>', unsafe_allow_html=True)
            for event in sorted(events_by_date[date], key=lambda e: e.start):
                duration = (event.end - event.start).total_seconds() / 60
                loc_str = f'<small style="color:#8B5CF6">📍 {event.location}</small><br>' if event.location else ''
                att_str = f'<small style="color:#A3A3A3">👥 {len(event.attendees)} attendees</small>' if event.attendees else ''
                st.markdown(f'<div class="calendar-event-card"><strong style="font-size:1.1rem">{event.title}</strong><br><small style="color:#00B8D4">👤 {event.organizer}</small><br><small style="color:#A3A3A3">⏰ {event.start.strftime("%I:%M %p")} - {event.end.strftime("%I:%M %p")} ({duration:.0f} min)</small><br>{loc_str}{att_str}</div>', unsafe_allow_html=True)
                if event.description:
                    with st.expander("View description"): st.write(event.description)
    else:
        st.markdown('<div class="warning-box"><p>📭 No calendar events loaded.</p><p>Click "Refresh Calendar" to fetch your events.</p></div>', unsafe_allow_html=True)

elif st.session_state.current_view == 'conflicts':
    st.markdown('<h1 class="main-header">⚠️ Calendar Conflicts</h1>', unsafe_allow_html=True)
    col1, col2 = st.columns([3,1])
    with col1: st.write("Detect overlapping meetings and get AI-powered resolution suggestions")
    with col2:
        if st.button("🔍 Detect Conflicts", use_container_width=True, type="primary"):
            if not st.session_state.calendar_events: fetch_calendar()
            detect_conflicts(); st.rerun()
    st.markdown("---")
    if st.session_state.conflicts:
        st.markdown(f'<div class="error-box"><strong>⚠️ Found {len(st.session_state.conflicts)} scheduling conflicts</strong><p style="margin-top:0.5rem;font-size:0.9rem">Review each conflict and generate resolution emails</p></div>', unsafe_allow_html=True)
        for i, conflict in enumerate(st.session_state.conflicts, 1):
            st.markdown(f'<h3 style="color:#FF6B6B">Conflict #{i}</h3>', unsafe_allow_html=True)
            st.markdown(f'<div class="conflict-card"><h4 style="color:#FF6B6B">⚔️ {conflict["event1"].title} vs {conflict["event2"].title}</h4><p><strong>Overlap:</strong> {conflict["overlap_minutes"]:.0f} minutes</p><p><strong>Time:</strong> {conflict["overlap_start"].strftime("%B %d, %I:%M %p")} - {conflict["overlap_end"].strftime("%I:%M %p")}</p></div>', unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Event 1:** {conflict['event1'].title}")
                st.write(f"**Time:** {conflict['event1'].start.strftime('%I:%M %p')} - {conflict['event1'].end.strftime('%I:%M %p')}")
                st.write(f"**Organizer:** {conflict['event1'].organizer}")
            with col2:
                st.write(f"**Event 2:** {conflict['event2'].title}")
                st.write(f"**Time:** {conflict['event2'].start.strftime('%I:%M %p')} - {conflict['event2'].end.strftime('%I:%M %p')}")
                st.write(f"**Organizer:** {conflict['event2'].organizer}")
            st.markdown("---")
            action_col1, action_col2 = st.columns(2)
            with action_col1:
                if st.button("🔍 Find Alternative Times", key=f"slots_{i}", use_container_width=True):
                    with show_loading("Finding free slots..."):
                        free_slots = st.session_state.assistant.find_free_slots(st.session_state.calendar_events, conflict['event1'].start, duration_minutes=60, max_slots=10)
                        if free_slots:
                            st.success(f"✅ Found {len(free_slots)} available slots:")
                            for j, slot in enumerate(free_slots, 1):
                                st.markdown(f'<div style="background:#1a2a1a;padding:0.6rem;border-radius:6px;margin-bottom:0.3rem"><strong>{j}.</strong> {slot["start"].strftime("%A, %B %d at %I:%M %p")} ({slot["duration_minutes"]:.0f} min)</div>', unsafe_allow_html=True)
                        else:
                            show_warning("No free slots found in the next few days")
            with action_col2:
                if st.button("✍️ Generate Resolution Email", key=f"email_{i}", use_container_width=True, type="primary"):
                    with show_loading("Generating email with AI..."):
                        free_slots = st.session_state.assistant.find_free_slots(st.session_state.calendar_events, conflict['event1'].start, duration_minutes=60)
                        email_body = st.session_state.assistant.generate_conflict_email(conflict, free_slots)
                        show_success("Email generated successfully!")
                        st.text_area("📧 Generated Email:", value=email_body, height=350, key=f"gen_email_{i}")
                        if st.button("📨 Create Draft in Gmail", key=f"draft_{i}", use_container_width=True):
                            success = st.session_state.assistant.create_draft(
                                to=conflict['event2'].organizer_email or conflict['event2'].organizer,
                                subject=f"Re: {conflict['event2'].title} - Alternative Times",
                                body=email_body)
                            if success: show_success("Draft created in your Gmail account!")
                            else:       show_error("Failed to create draft")
            st.markdown("---")
    else:
        st.markdown('<div class="success-box" style="text-align:center;padding:2rem"><div style="font-size:4rem;margin-bottom:1rem">✅</div><h2 style="color:#00E5A0">No Conflicts Detected!</h2><p style="color:#A3A3A3;margin-top:1rem">Your calendar is clear of overlapping meetings.</p></div>', unsafe_allow_html=True)

elif st.session_state.current_view == 'compose':
    st.markdown('<h1 class="main-header">✍️ Compose Email</h1>', unsafe_allow_html=True)
    if st.session_state.selected_email:
        st.markdown(f'<div class="success-box"><strong>📧 Replying to:</strong> {st.session_state.selected_email.subject}<br><small>From: {st.session_state.selected_email.sender_email}</small></div>', unsafe_allow_html=True)
        default_to      = st.session_state.selected_email.sender_email
        default_subject = f"Re: {st.session_state.selected_email.subject}"
    else:
        default_to = default_subject = ""
    to_email = st.text_input("**To:**",      value=default_to,      placeholder="recipient@example.com")
    subject  = st.text_input("**Subject:**", value=default_subject, placeholder="Email subject")
    body     = st.text_area("**Message:**",  height=300,             placeholder="Write your email here...")
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("📨 Send Email", use_container_width=True, type="primary"):
            if not to_email or not subject or not body:
                show_error("Please fill in all fields (To, Subject, Message)")
            else:
                with show_loading("Sending email..."):
                    success = st.session_state.assistant.send_email(to=to_email, subject=subject, body=body)
                    if success:
                        show_success("Email sent successfully!")
                        st.session_state.selected_email = None; time.sleep(1); st.rerun()
                    else:
                        show_error("Failed to send email. Please try again.")
    with col2:
        if st.button("💾 Save Draft", use_container_width=True):
            if not to_email or not subject: show_error("Please fill in To and Subject fields")
            else:
                with show_loading("Saving draft..."):
                    success = st.session_state.assistant.create_draft(to=to_email, subject=subject, body=body)
                    if success: show_success("Draft saved in your Gmail!")
                    else:       show_error("Failed to save draft")
    with col3:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.selected_email = None; st.rerun()
    with col4:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.selected_email = None
            st.session_state.current_view   = 'dashboard'; st.rerun()

elif st.session_state.current_view == 'workflow':
    st.markdown('<h1 class="main-header">🤖 AI Workflow</h1>', unsafe_allow_html=True)
    st.markdown('<div class="success-box"><h3>🚀 Complete AI Workflow</h3><p>Run the full AI-powered analysis to:</p><ul><li>📧 Fetch and analyze your emails</li><li>📅 Sync calendar events</li><li>⚠️ Detect scheduling conflicts</li><li>🤖 Categorize emails with AI</li><li>💡 Generate smart suggestions</li><li>💾 Save results to memory</li></ul></div>', unsafe_allow_html=True)
    st.markdown("---")
    if st.button("🚀 Run Complete AI Workflow", use_container_width=True, type="primary"):
        result = run_workflow()
        if result:
            show_success("Workflow completed successfully!")
            st.markdown('<h2 class="sub-header">📊 Workflow Results</h2>', unsafe_allow_html=True)
            col1, col2, col3, col4 = st.columns(4)
            with col1: st.markdown(f'<div class="metric-card"><div class="stat-container"><div class="stat-value">{len(result.get("emails",[]))}</div><div class="stat-label">Emails Processed</div></div></div>', unsafe_allow_html=True)
            with col2: st.markdown(f'<div class="metric-card"><div class="stat-container"><div class="stat-value">{len(result.get("calendar_events",[]))}</div><div class="stat-label">Calendar Events</div></div></div>', unsafe_allow_html=True)
            with col3: st.markdown(f'<div class="metric-card"><div class="stat-container"><div class="stat-value">{len(result.get("conflicts",[]))}</div><div class="stat-label">Conflicts Found</div></div></div>', unsafe_allow_html=True)
            with col4: st.markdown(f'<div class="metric-card"><div class="stat-container"><div class="stat-value">{len(result.get("suggestions",[]))}</div><div class="stat-label">AI Suggestions</div></div></div>', unsafe_allow_html=True)
            st.markdown("---")
            if result.get('suggestions'):
                st.markdown('<h2 class="sub-header">💡 AI Suggestions</h2>', unsafe_allow_html=True)
                for i, sug in enumerate(result['suggestions'], 1):
                    title  = sug.get('title',       str(sug)) if isinstance(sug, dict) else str(sug)
                    desc   = sug.get('description', '')        if isinstance(sug, dict) else ''
                    stype  = sug.get('type',  '')              if isinstance(sug, dict) else ''
                    action = sug.get('action', '')             if isinstance(sug, dict) else ''
                    st.markdown(f'<div class="success-box"><h4>{i}. {title}</h4><p>{desc}</p><small style="color:#00B8D4">Type: {stype} | Action: {action}</small></div>', unsafe_allow_html=True)
            if result.get('error_logs'):
                st.markdown('<h2 class="sub-header">⚠️ Errors</h2>', unsafe_allow_html=True)
                for error in result['error_logs']: show_error(error)
    st.markdown("---")
    if st.session_state.workflow_result:
        st.markdown('<h2 class="sub-header">📜 Last Workflow Run</h2>', unsafe_allow_html=True)
        result = st.session_state.workflow_result
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Summary:**")
            st.write(f"- Emails: {len(result.get('emails', []))}")
            st.write(f"- Events: {len(result.get('calendar_events', []))}")
            st.write(f"- Conflicts: {len(result.get('conflicts', []))}")
            st.write(f"- Suggestions: {len(result.get('suggestions', []))}")
        with col2:
            st.write("**Status:**")
            if result.get('analysis_complete'): st.success("✅ Analysis complete")
            else: st.warning("⚠️ Analysis incomplete")

# Footer
st.markdown("---")
st.markdown('<div style="text-align:center;color:#A3A3A3;padding:2rem 0"><p>Made with ❤️ using Streamlit | Powered by LangGraph & OpenAI</p><p style="font-size:0.8rem">🔒 Your data is secure | Privacy-first design</p></div>', unsafe_allow_html=True)
