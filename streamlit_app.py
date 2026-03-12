"""
AI Email Assistant — Multi-User Edition
HOW THE AUTH FLOW WORKS:
  1. Click "Connect to Gmail"
  2. Open the Google link → sign in → click Allow
  3. Browser shows "This site can't be reached" — THAT IS NORMAL AND EXPECTED
  4. Copy the full URL from your browser address bar and paste it in the sidebar
  5. Click Connect — done!
"""

import streamlit as st
import os, json, time, socket
from datetime import datetime
from urllib.parse import urlparse, parse_qs

st.set_page_config(page_title="AI Email Assistant", page_icon="📧",
                   layout="wide", initial_sidebar_state="expanded")

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import requests as http_req

try:
    from ambient_email_assistant_enhanced import EnhancedEmailAssistant
except ImportError:
    st.error("Cannot find ambient_email_assistant_enhanced.py — put it in the same folder.")
    st.stop()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]
CREDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")

st.markdown("""
<style>
:root{--g:#00E5A0;--b:#00B8D4;--r:#FF6B6B;--y:#FFB800;}
#MainMenu,footer{visibility:hidden;}
::-webkit-scrollbar{width:8px;}::-webkit-scrollbar-thumb{background:var(--g);border-radius:4px;}
.mhdr{font-size:2.4rem;font-weight:700;text-align:center;padding:1rem 0;
  background:linear-gradient(135deg,#00E5A0,#00B8D4);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.shdr{font-size:1.7rem;font-weight:600;color:var(--g);
  border-bottom:2px solid var(--g);padding-bottom:.4rem;margin:1.2rem 0 .8rem;}
.card{background:linear-gradient(135deg,#1C1C21,#232328);padding:1.4rem;border-radius:12px;
  border:1px solid var(--g);box-shadow:0 4px 16px rgba(0,229,160,.1);margin-bottom:1rem;}
.ecard{background:#1C1C21;padding:1rem;border-radius:10px;
  border-left:4px solid var(--g);margin-bottom:.8rem;transition:all .2s;}
.ecard:hover{background:#232328;border-left-color:var(--b);transform:translateX(4px);}
.ccard{background:#1C1C21;padding:1rem;border-radius:8px;
  border-left:4px solid var(--b);margin-bottom:.6rem;}
.cfcard{background:linear-gradient(135deg,#2a1a1a,#3a2020);padding:1.2rem;
  border-radius:10px;border-left:4px solid var(--r);margin-bottom:.8rem;}
.ok{background:linear-gradient(135deg,#1a2a1a,#1a3a1a);border:1px solid var(--g);
  padding:1rem;border-radius:8px;margin:.8rem 0;}
.wn{background:linear-gradient(135deg,#2a2a1a,#3a3020);border:1px solid var(--y);
  padding:1rem;border-radius:8px;margin:.8rem 0;}
.er{background:linear-gradient(135deg,#2a1a1a,#3a2020);border:1px solid var(--r);
  padding:1rem;border-radius:8px;margin:.8rem 0;}
.ob{background:linear-gradient(135deg,#0f1f2f,#1a2a3a);border:1px solid var(--b);
  padding:1.2rem;border-radius:10px;margin:.6rem 0;}
.stButton>button{background:linear-gradient(135deg,#00E5A0,#00B8D4);color:#000;
  font-weight:700;border:none;padding:.6rem 2rem;border-radius:8px;
  box-shadow:0 2px 8px rgba(0,229,160,.2);transition:all .3s;}
.stButton>button:hover{transform:translateY(-2px);}
.badge{display:inline-block;padding:.25rem .7rem;border-radius:20px;
  font-size:.8rem;font-weight:600;margin-right:.4rem;}
.bu{background:#00B8D4;color:#000;}.bi{background:#FFB800;color:#000;}
.bc{background:#8B5CF6;color:#fff;}
.sv{font-size:2.5rem;font-weight:700;
  background:linear-gradient(135deg,#00E5A0,#00B8D4);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.sl{font-size:.9rem;color:#A3A3A3;margin-top:.4rem;}
.stProgress>div>div>div>div{background:linear-gradient(90deg,#00E5A0,#00B8D4);}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0D0D0F,#18181B);}
.stTabs [data-baseweb="tab-list"]{gap:8px;background:#1C1C21;padding:.5rem;border-radius:10px;}
.stTabs [data-baseweb="tab"]{background:transparent;border-radius:8px;
  color:#A3A3A3;font-weight:600;padding:.8rem 1.5rem;}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg,#00E5A0,#00B8D4);color:#000;}
</style>
""", unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────────────────
for k, v in {
    "authenticated": False, "user_email": None, "creds_json": None,
    "assistant": None, "show_ai": False,
    "oauth_step": 0,   # 0=idle  1=waiting for URL paste
    "_auth_url": None, "_oauth_port": None,
    "emails": [], "calendar_events": [], "conflicts": [],
    "workflow_result": None,
    "current_view": "dashboard", "selected_email": None, "_etab": "all",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════════════════════════
# OAUTH
# ══════════════════════════════════════════════════════════════════════════════

def _free_port():
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]

def _load_cfg():
    if not os.path.exists(CREDS_FILE): return None
    try:
        with open(CREDS_FILE) as f: return json.load(f)
    except: return None

def _make_flow(port):
    cfg = _load_cfg()
    if not cfg: return None
    return Flow.from_client_config(cfg, scopes=SCOPES,
                                   redirect_uri=f"http://localhost:{port}")

def _build_auth_url(port):
    flow = _make_flow(port)
    if not flow: return None
    url, _ = flow.authorization_url(access_type="offline",
                                    include_granted_scopes="true", prompt="consent")
    return url

def _extract_code(pasted: str):
    """Pull the auth code out of a pasted redirect URL (or bare code)."""
    pasted = pasted.strip()
    if not pasted: return None
    if pasted.startswith("http"):
        qs = parse_qs(urlparse(pasted).query)
        return qs.get("code", [None])[0]
    return pasted   # treat as bare code

def _exchange(port, code):
    try:
        flow = _make_flow(port)
        if not flow: return None
        flow.fetch_token(code=code)
        return flow.credentials
    except Exception as e:
        st.error(f"❌ Token exchange failed: {e}")
        return None

def _save_creds(c): st.session_state.creds_json = c.to_json()

def _load_creds():
    raw = st.session_state.creds_json
    if not raw: return None
    try:
        c = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
        if c.expired and c.refresh_token:
            c.refresh(Request()); _save_creds(c)
        return c
    except: return None

def _get_email(c):
    try:
        r = http_req.get("https://www.googleapis.com/oauth2/v2/userinfo",
                         headers={"Authorization": f"Bearer {c.token}"}, timeout=5)
        return r.json().get("email") if r.ok else None
    except: return None

def _connect(c):
    try:
        a = EnhancedEmailAssistant()
        if not a.inject_credentials(c):
            st.error("❌ Could not connect. Try signing in again."); return False
        st.session_state.assistant = a
        st.session_state.authenticated = True
        try:
            from dotenv import load_dotenv; load_dotenv()
            key = os.getenv("OPENAI_API_KEY")
            if key: a.initialize_llm(api_key=key); st.session_state.show_ai = True
        except: pass
        return True
    except Exception as e:
        st.error(f"❌ {e}"); return False

# Auto-restore on refresh
if not st.session_state.authenticated and st.session_state.creds_json:
    _c = _load_creds()
    if _c: _connect(_c)

# ── Data helpers ───────────────────────────────────────────────────────────────
def fetch_emails(n=50, q=""):
    with st.spinner(f"Fetching {n} emails…"):
        try:
            e = st.session_state.assistant.fetch_emails(max_results=n, query=q)
            st.session_state.emails = e; return e
        except Exception as ex: st.error(f"❌ {ex}"); return []

def fetch_cal(days=30):
    with st.spinner("Fetching calendar…"):
        try:
            ev = st.session_state.assistant.fetch_calendar_events(days_ahead=days)
            st.session_state.calendar_events = ev; return ev
        except Exception as ex: st.error(f"❌ {ex}"); return []

def detect_conflicts():
    with st.spinner("Detecting conflicts…"):
        try:
            c = st.session_state.assistant.detect_conflicts(st.session_state.calendar_events)
            st.session_state.conflicts = c; return c
        except Exception as ex: st.error(f"❌ {ex}"); return []

def run_wf():
    with st.spinner("Running AI workflow…"):
        try:
            pb = st.progress(0); pb.progress(20)
            r = st.session_state.assistant.run_ambient_agent(thread_id="st-session")
            pb.progress(100); pb.empty()
            st.session_state.workflow_result = r
            if r.get("emails"):          st.session_state.emails          = r["emails"]
            if r.get("calendar_events"): st.session_state.calendar_events = r["calendar_events"]
            if r.get("conflicts"):       st.session_state.conflicts       = r["conflicts"]
            return r
        except Exception as ex: st.error(f"❌ {ex}"); return None

def _filt(emails, t):
    if t=="unread":    return [e for e in emails if e.is_unread]
    if t=="important": return [e for e in emails if e.is_important]
    if t=="calendar":  return [e for e in emails if e.has_calendar_event]
    return emails

def _sort(emails, k):
    if k=="asc":    return sorted(emails, key=lambda e: e.timestamp)
    if k=="sender": return sorted(emails, key=lambda e: e.sender)
    if k=="pri":    return sorted(emails, key=lambda e: e.priority_score or 0, reverse=True)
    return sorted(emails, key=lambda e: e.timestamp, reverse=True)

def _b(t, c): return f'<span class="badge {c}">{t}</span>'

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown('<h2 style="text-align:center;">📧 AI Email Assistant</h2>',
                unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("🔐 Your Account")

    if not st.session_state.authenticated:

        if _load_cfg() is None:
            st.markdown('<div class="er">❌ <strong>credentials.json not found</strong></div>',
                        unsafe_allow_html=True)

        # STEP 0 ── show Connect button
        elif st.session_state.oauth_step == 0:
            st.markdown('<div class="wn">Sign in with <strong>any Google account</strong>.<br>'
                        '<small>Token never stored on disk.</small></div>',
                        unsafe_allow_html=True)
            if st.button("🔑 Connect to Gmail", use_container_width=True, type="primary"):
                port = _free_port()
                url  = _build_auth_url(port)
                if url:
                    st.session_state._auth_url   = url
                    st.session_state._oauth_port = port
                    st.session_state.oauth_step  = 1
                    st.rerun()
                else:
                    st.error("Could not build auth URL — check credentials.json.")

        # STEP 1 ── show link + URL paste box
        elif st.session_state.oauth_step == 1:
            url  = st.session_state._auth_url  or ""
            port = st.session_state._oauth_port

            st.markdown(f"""
            <div class="ob">
              <b>Step 1 — Open Google sign-in:</b><br><br>
              <a href="{url}" target="_blank"
                 style="color:#00B8D4;font-weight:600;font-size:1rem;">
                🔗 Click here to sign in with Google
              </a><br><br>
              <small style="color:#A3A3A3;">
                Sign in with any Google account, click <em>Allow</em>.
              </small>
            </div>""", unsafe_allow_html=True)

            st.markdown("""
            <div class="ob">
              <b>Step 2 — Paste the redirect URL:</b><br>
              <small style="color:#A3A3A3;">
                After clicking Allow, your browser will show<br>
                <b style="color:#FFB800;">"This site can't be reached"</b> — that's normal!<br><br>
                Copy the <b>full URL</b> from your address bar<br>
                (starts with <code>http://localhost:PORT/?...code=...</code>)<br>
                and paste it below.
              </small>
            </div>""", unsafe_allow_html=True)

            pasted = st.text_input(
                "Redirect URL:",
                placeholder="http://localhost:58518/?state=...&code=4/0Afr...",
                key="pasted_url",
            )

            ca, cb = st.columns(2)
            with ca:
                if st.button("✅ Connect", use_container_width=True, type="primary"):
                    code = _extract_code(pasted)
                    if code:
                        with st.spinner("Connecting…"):
                            creds = _exchange(port, code)
                        if creds:
                            _save_creds(creds)
                            st.session_state.user_email = _get_email(creds)
                            st.session_state.oauth_step = 0
                            if _connect(creds):
                                st.success("✅ Connected!")
                                st.rerun()
                    else:
                        st.warning("Paste the full redirect URL first.")
            with cb:
                if st.button("↩ Cancel", use_container_width=True):
                    st.session_state.oauth_step = 0; st.rerun()

    else:
        lbl = st.session_state.user_email or "Google Account"
        st.markdown(f'<div class="ok">✅ <strong>Connected</strong><br>'
                    f'<small style="color:#A3A3A3;">{lbl}</small></div>',
                    unsafe_allow_html=True)
        if st.session_state.show_ai:
            st.markdown('<div class="ok">🤖 <strong>AI features on</strong></div>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<div class="wn">⚠️ <strong>AI off</strong> — add OPENAI_API_KEY to .env</div>',
                        unsafe_allow_html=True)

        if st.button("🚪 Sign Out", use_container_width=True):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()

        st.markdown("---")
        st.subheader("🧭 Navigate")
        for lbl, vid in [("📊 Dashboard","dashboard"),("📧 Emails","emails"),
                          ("📅 Calendar","calendar"),("⚠️ Conflicts","conflicts"),
                          ("✍️ Compose","compose"),("🤖 AI Workflow","workflow")]:
            bt = "primary" if st.session_state.current_view == vid else "secondary"
            if st.button(lbl, use_container_width=True, key=f"nav_{vid}", type=bt):
                st.session_state.current_view = vid; st.rerun()

        st.markdown("---")
        q1, q2 = st.columns(2)
        with q1:
            if st.button("🔄", use_container_width=True, help="Refresh"):
                fetch_emails(); fetch_cal(); st.rerun()
        with q2:
            if st.button("🤖", use_container_width=True, help="AI workflow"):
                run_wf(); st.rerun()
        st.markdown("---")
        st.metric("Emails",    len(st.session_state.emails))
        st.metric("Events",    len(st.session_state.calendar_events))
        st.metric("Conflicts", len(st.session_state.conflicts))


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if not st.session_state.authenticated:
    st.markdown('<h1 class="mhdr">🚀 AI Email Assistant</h1>', unsafe_allow_html=True)

    for col, icon, title, color, desc in zip(
        st.columns(3),
        ["📧","📅","🤖"],
        ["Smart Inbox","Calendar Sync","AI Insights"],
        ["#00E5A0","#00B8D4","#8B5CF6"],
        ["Read, search, filter and reply to your Gmail",
         "Events, conflicts, free slot finder",
         "Categorise, priority, sentiment & auto-draft"],
    ):
        with col:
            st.markdown(f'<div class="card" style="text-align:center;">'
                        f'<div style="font-size:3rem;">{icon}</div>'
                        f'<h3 style="color:{color};">{title}</h3>'
                        f'<p style="color:#A3A3A3;">{desc}</p></div>',
                        unsafe_allow_html=True)

    st.markdown("---")
    L, R = st.columns([2,1])
    with L:
        st.markdown('<h2 class="shdr">How to connect</h2>', unsafe_allow_html=True)
        st.markdown("""
**1.** Click **"Connect to Gmail"** in the sidebar.

**2.** Click the Google sign-in link that appears. Sign in with any Google account and click **Allow**.

**3.** Your browser will show **"This site can't be reached"** — this is completely normal!
Google has sent the auth code in the URL. Copy the **full URL** from your browser's address bar.

**4.** Paste that URL into the sidebar text box and click **Connect**.
        """)
    with R:
        st.markdown('<div class="wn"><h4>⚠️ &ldquo;This site can&rsquo;t be reached&rdquo;</h4>'
                    '<p>This is <strong>expected</strong> &mdash; Google sent the auth code successfully. '
                    'Copy the URL and paste it back in the sidebar.</p></div>',
                    unsafe_allow_html=True)
    st.info("👈 Click **Connect to Gmail** in the sidebar to begin.")


elif st.session_state.current_view == "dashboard":
    st.markdown('<h1 class="mhdr">📊 Dashboard</h1>', unsafe_allow_html=True)
    emails = st.session_state.emails
    events = st.session_state.calendar_events
    cc = len(st.session_state.conflicts)
    unread = sum(1 for e in emails if e.is_unread)
    imp = sum(1 for e in emails if e.is_important)

    for col, v, lbl, sub, color in zip(
        st.columns(4),
        [len(emails), len(events), cc, imp],
        ["Total Emails","Cal Events","Conflicts","Important"],
        [f"{unread} unread","Next 30 days","Needs attention" if cc else "All clear","Starred"],
        ["#00B8D4","#8B5CF6","#FF6B6B" if cc else "#00E5A0","#FFB800"],
    ):
        with col:
            st.markdown(f'<div class="card"><div style="text-align:center;">'
                        f'<div class="sv" style="background:linear-gradient(135deg,{color},{color});'
                        f'-webkit-background-clip:text;">{v}</div>'
                        f'<div class="sl">{lbl}</div>'
                        f'<div style="color:{color};font-size:.85rem;">{sub}</div>'
                        f'</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    CL, CR = st.columns([2,1])
    with CL:
        st.markdown('<h2 class="shdr">📬 Recent Emails</h2>', unsafe_allow_html=True)
        if emails:
            for em in emails[:8]:
                b = ((_b("Unread","bu") if em.is_unread else "") +
                     (_b("Important","bi") if em.is_important else "") +
                     (_b("Calendar","bc") if em.has_calendar_event else ""))
                st.markdown(f'<div class="ecard"><div style="margin-bottom:.4rem;">{b}</div>'
                            f'<strong>{em.subject}</strong><br>'
                            f'<small style="color:#00B8D4;">{em.sender}</small> · '
                            f'<small style="color:#A3A3A3;">{em.timestamp.strftime("%b %d, %I:%M %p")}</small><br>'
                            f'<p style="color:#A3A3A3;font-size:.9rem;">{em.snippet[:100]}…</p></div>',
                            unsafe_allow_html=True)
                if st.button("View →", key=f"dv_{em.id}"):
                    st.session_state.selected_email = em
                    st.session_state.current_view = "emails"; st.rerun()
        else:
            st.markdown('<div class="wn">📭 No emails — click 🔄 in sidebar to load.</div>',
                        unsafe_allow_html=True)
    with CR:
        st.markdown('<h2 class="shdr">🎯 AI Insights</h2>', unsafe_allow_html=True)
        wr = st.session_state.workflow_result
        if wr:
            for i,s in enumerate(wr.get("suggestions",[])[:5],1):
                t = s.get("title",s) if isinstance(s,dict) else s
                st.markdown(f'<div style="background:#1C1C21;padding:.8rem;border-radius:6px;'
                            f'margin-bottom:.5rem;border-left:3px solid #00E5A0;">'
                            f'<strong>{i}. {t}</strong></div>', unsafe_allow_html=True)
        else:
            if st.button("🚀 Run AI Workflow", use_container_width=True, type="primary"):
                run_wf(); st.rerun()
        st.markdown("---")
        today = datetime.now().date()
        tevs  = [e for e in events if e.start.date()==today]
        st.write("**📅 Today**")
        if tevs:
            for ev in tevs[:5]:
                st.markdown(f'<div class="ccard"><strong>{ev.title}</strong><br>'
                            f'<small>⏰ {ev.start.strftime("%I:%M %p")} – {ev.end.strftime("%I:%M %p")}</small></div>',
                            unsafe_allow_html=True)
        else:
            st.info("No events today.")


elif st.session_state.current_view == "emails":
    st.markdown('<h1 class="mhdr">📧 Email Manager</h1>', unsafe_allow_html=True)
    s1,s2,s3,s4 = st.columns([2,1,1,1])
    with s1: q = st.text_input("Search", placeholder="is:unread from:boss@company.com",
                                label_visibility="collapsed")
    with s2: n = st.number_input("Max", 10, 200, 50, label_visibility="collapsed")
    with s3:
        if st.button("🔄 Fetch", use_container_width=True, type="primary"):
            fetch_emails(n, q); st.rerun()
    with s4:
        if st.button("🤖 Analyse", use_container_width=True):
            a = st.session_state.assistant
            if a and getattr(a,"llm",None):
                with st.spinner("Analysing…"):
                    st.session_state.emails = a.categorize_emails_ai(st.session_state.emails)
                st.rerun()
            else: st.warning("AI off — add OPENAI_API_KEY to .env")
    st.markdown("---")
    t1,t2,t3,t4 = st.tabs(["📬 All","🔵 Unread","⭐ Important","📅 Calendar"])
    with t1: st.session_state._etab = "all"
    with t2: st.session_state._etab = "unread"
    with t3: st.session_state._etab = "important"
    with t4: st.session_state._etab = "calendar"
    _, sc = st.columns([4,1])
    with sc:
        sl = st.selectbox("Sort",["Date ↓","Date ↑","Sender","Priority"],
                          label_visibility="collapsed")
    sm = {"Date ↓":"desc","Date ↑":"asc","Sender":"sender","Priority":"pri"}
    shown = _sort(_filt(st.session_state.emails, st.session_state._etab), sm[sl])
    st.write(f"**Showing {len(shown)} emails**")
    for em in shown:
        ico  = "🔵" if em.is_unread else "✅"
        star = "⭐ " if em.is_important else ""
        shrt = em.subject[:55]+("…" if len(em.subject)>55 else "")
        with st.expander(f"{ico} {star}{shrt} — {em.sender}", expanded=False):
            lc, rc = st.columns([3,1])
            with lc:
                st.write(f"**From:** {em.sender} ({em.sender_email})")
                st.write(f"**Date:** {em.timestamp.strftime('%A, %B %d, %Y at %I:%M %p')}")
                if em.category or em.priority_score or em.sentiment:
                    ic = st.columns(3)
                    if em.category:       ic[0].metric("Category", em.category)
                    if em.priority_score: ic[1].metric("Priority",  f"{em.priority_score}/10")
                    if em.sentiment:      ic[2].metric("Sentiment", em.sentiment)
            with rc:
                if st.button("📧 Reply", key=f"rp_{em.id}", use_container_width=True):
                    st.session_state.selected_email = em
                    st.session_state.current_view = "compose"; st.rerun()
            st.markdown("---")
            st.text_area("Body", value=em.body, height=250, key=f"bd_{em.id}",
                         disabled=True, label_visibility="collapsed")


elif st.session_state.current_view == "calendar":
    st.markdown('<h1 class="mhdr">📅 Calendar Manager</h1>', unsafe_allow_html=True)
    c1,c2,c3 = st.columns([2,1,1])
    with c1: days = st.slider("Days ahead", 7, 90, 30)
    with c2:
        if st.button("🔄 Refresh", use_container_width=True, type="primary"):
            fetch_cal(days); st.rerun()
    with c3:
        if st.button("⚠️ Conflicts", use_container_width=True):
            if not st.session_state.calendar_events: fetch_cal()
            detect_conflicts(); st.rerun()
    st.markdown("---")
    evs = st.session_state.calendar_events
    if evs:
        by_d: dict = {}
        for ev in evs: by_d.setdefault(ev.start.date(),[]).append(ev)
        for dt in sorted(by_d):
            st.markdown(f'<h3 style="color:#00B8D4;">📆 {dt.strftime("%A, %B %d, %Y")}</h3>',
                        unsafe_allow_html=True)
            for ev in sorted(by_d[dt], key=lambda e: e.start):
                dur = (ev.end-ev.start).total_seconds()/60
                st.markdown(f'<div class="ccard"><strong>{ev.title}</strong><br>'
                            f'<small style="color:#A3A3A3;">⏰ {ev.start.strftime("%I:%M %p")} – {ev.end.strftime("%I:%M %p")} ({dur:.0f} min)</small>'
                            f'{"<br><small style=color:#8B5CF6;>📍 "+ev.location+"</small>" if ev.location else ""}'
                            f'</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="wn">📭 No events — click Refresh.</div>', unsafe_allow_html=True)


elif st.session_state.current_view == "conflicts":
    st.markdown('<h1 class="mhdr">⚠️ Calendar Conflicts</h1>', unsafe_allow_html=True)
    _, bc = st.columns([3,1])
    with bc:
        if st.button("🔍 Detect", use_container_width=True, type="primary"):
            if not st.session_state.calendar_events: fetch_cal()
            detect_conflicts(); st.rerun()
    st.markdown("---")
    cfs = st.session_state.conflicts
    if cfs:
        st.markdown(f'<div class="er">⚠️ <strong>{len(cfs)} conflict(s) found</strong></div>',
                    unsafe_allow_html=True)
        for i,cf in enumerate(cfs,1):
            st.markdown(f'<h3 style="color:#FF6B6B;">Conflict #{i}</h3>', unsafe_allow_html=True)
            cl, cr = st.columns(2)
            for col,ev,color in [(cl,cf["event1"],"#00E5A0"),(cr,cf["event2"],"#FF6B6B")]:
                with col:
                    st.markdown(f'<div style="background:#1C1C21;padding:1rem;border-radius:8px;'
                                f'border-left:3px solid {color};margin-bottom:.5rem;">'
                                f'<strong>{ev.title}</strong><br>'
                                f'{ev.start.strftime("%I:%M %p")} – {ev.end.strftime("%I:%M %p")}</div>',
                                unsafe_allow_html=True)
            if st.button("✍️ Generate Resolution Email", key=f"ge_{i}",
                         use_container_width=True, type="primary"):
                with st.spinner("Generating…"):
                    slots = st.session_state.assistant.find_free_slots(
                        st.session_state.calendar_events, cf["event1"].start, duration_minutes=60)
                    body = st.session_state.assistant.generate_conflict_email(cf, slots)
                st.text_area("Email:", value=body, height=300, key=f"gn_{i}")
            st.markdown("---")
    else:
        st.markdown('<div class="ok" style="text-align:center;padding:2rem;">'
                    '<div style="font-size:4rem;">✅</div>'
                    '<h2 style="color:#00E5A0;">No Conflicts!</h2></div>',
                    unsafe_allow_html=True)


elif st.session_state.current_view == "compose":
    st.markdown('<h1 class="mhdr">✍️ Compose Email</h1>', unsafe_allow_html=True)
    re_em = st.session_state.selected_email
    to_val   = re_em.sender_email  if re_em else ""
    subj_val = f"Re: {re_em.subject}" if re_em else ""
    if re_em:
        st.markdown(f'<div class="ok">📧 Replying to: <strong>{re_em.subject}</strong></div>',
                    unsafe_allow_html=True)
    to   = st.text_input("To:",      value=to_val)
    subj = st.text_input("Subject:", value=subj_val)
    body = st.text_area("Message:",  height=300)
    b1,b2,b3,b4 = st.columns(4)
    with b1:
        if st.button("📨 Send", use_container_width=True, type="primary"):
            if not all([to,subj,body]): st.error("Fill all fields.")
            else:
                with st.spinner("Sending…"):
                    ok = st.session_state.assistant.send_email(to=to, subject=subj, body=body)
                if ok: st.success("✅ Sent!"); st.session_state.selected_email=None; time.sleep(1); st.rerun()
                else: st.error("❌ Failed.")
    with b2:
        if st.button("💾 Draft", use_container_width=True):
            ok = st.session_state.assistant.create_draft(to=to, subject=subj, body=body)
            st.success("✅ Saved!") if ok else st.error("❌ Failed.")
    with b3:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.selected_email = None; st.rerun()
    with b4:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.selected_email = None
            st.session_state.current_view = "dashboard"; st.rerun()


elif st.session_state.current_view == "workflow":
    st.markdown('<h1 class="mhdr">🤖 AI Workflow</h1>', unsafe_allow_html=True)
    if st.button("🚀 Run Complete AI Workflow", use_container_width=True, type="primary"):
        r = run_wf()
        if r:
            st.success("✅ Done!")
            for col, v, lbl in zip(st.columns(4),
                [r.get("emails_fetched",len(st.session_state.emails)),
                 r.get("events_fetched",len(st.session_state.calendar_events)),
                 r.get("conflicts_found",len(st.session_state.conflicts)),
                 len(r.get("suggestions",[]))],
                ["Emails","Events","Conflicts","Suggestions"]):
                with col:
                    st.markdown(f'<div class="card" style="text-align:center;">'
                                f'<div class="sv">{v}</div><div class="sl">{lbl}</div></div>',
                                unsafe_allow_html=True)

st.markdown("---")
st.markdown('<div style="text-align:center;color:#A3A3A3;padding:1rem 0;">'
            '<small>🔒 Credentials stored only in browser session — never on disk</small></div>',
            unsafe_allow_html=True)
