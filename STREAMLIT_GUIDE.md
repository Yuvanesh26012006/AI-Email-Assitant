# 🎨 Streamlit Email Assistant - Setup Guide

## Beautiful AI Email Assistant with Calendar Integration

This is a complete Streamlit web application featuring:
- ✨ **Beautiful Modern UI/UX** - Clean, gradient-based design
- 📧 **Full Gmail Integration** - Real email management
- 📅 **Calendar Sync** - Events, conflicts, and free slots
- 🤖 **AI-Powered Features** - Smart categorization and analysis
- 💾 **Memory Persistence** - Learns your patterns
- 🚀 **Interactive Workflows** - Real-time updates

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements_streamlit.txt
```

### 2. Set Up Google Cloud Credentials

Follow the instructions in `GOOGLE_OAUTH_SETUP.md` to:
1. Create a Google Cloud Project
2. Enable Gmail API and Calendar API
3. Create OAuth 2.0 credentials
4. Download `credentials.json`

### 3. Configure Environment (Optional)

```bash
cp env.example .env
# Edit .env and add:
# OPENAI_API_KEY=sk-your-key-here
```

### 4. Run the Streamlit App

```bash
streamlit run streamlit_app.py
```

The app will open automatically in your browser at `http://localhost:8501`

---

## 📱 Features Overview

### 🏠 Dashboard
- Real-time metrics (emails, events, conflicts)
- Recent emails preview
- AI insights panel
- Today's calendar events
- Quick actions

### 📧 Email Manager
- Advanced search and filtering
- Sort by date, sender, or priority
- AI categorization with priority scores
- Sentiment analysis
- Full email viewing and replying

### 📅 Calendar Manager
- View all calendar events
- Grouped by date
- Event details with attendees
- Duration and location info
- Conflict detection button

### ⚠️ Conflicts Resolution
- Automatic conflict detection
- Side-by-side event comparison
- Find alternative time slots
- AI-generated resolution emails
- One-click draft creation

### ✍️ Compose Email
- Rich text editor
- Reply to emails
- AI enhancement tools (coming soon)
- Save drafts
- Send directly

### 🤖 AI Workflow
- Complete automated analysis
- Progress tracking
- Result visualization
- Smart suggestions
- Draft generation

---

## 🎨 UI/UX Features

### Design Elements

**Color Scheme:**
- Primary: `#00E5A0` (Mint Green)
- Secondary: `#00B8D4` (Cyan)
- Accent: `#FF6B6B` (Coral)
- Warning: `#FFB800` (Amber)
- Background: Dark theme with gradients

**Components:**
- Metric cards with hover effects
- Gradient buttons
- Animated transitions
- Custom scrollbars
- Badge system (Unread, Important, Calendar)
- Color-coded cards

**Layout:**
- Wide layout for maximum space
- Responsive columns
- Collapsible expanders
- Tabbed interfaces
- Sidebar navigation

### Interactive Features

1. **Real-time Updates** - Instant feedback on all actions
2. **Loading Indicators** - Progress bars and spinners
3. **Status Messages** - Success, error, warning, info boxes
4. **Smooth Animations** - Slide-in effects and transitions
5. **Responsive Design** - Works on different screen sizes

---

## 📊 Page-by-Page Guide

### Dashboard Page

**What You See:**
- 4 metric cards: Total Emails, Calendar Events, Conflicts, Important
- Recent emails list (8 most recent)
- AI insights panel
- Today's events sidebar

**Actions:**
- Click "View Details" on any email to see full content
- Click "Run AI Workflow" for analysis
- Use sidebar buttons for quick refresh

### Email Manager Page

**Features:**
- Search bar with Gmail query syntax
- Max results selector
- Fetch and Analyze buttons
- 4 filter tabs: All, Unread, Important, Calendar
- Sort options: Date, Sender, Priority

**Workflow:**
1. Enter search query (optional)
2. Set max results
3. Click "Fetch" to load emails
4. Click "Analyze" for AI categorization
5. Use tabs to filter
6. Click expander to view email details
7. Click "Reply" to compose response

### Calendar Manager Page

**Features:**
- Days ahead slider (7-90 days)
- Refresh button
- Check conflicts button
- Events grouped by date
- Full event details

**Workflow:**
1. Adjust "Days to look ahead" slider
2. Click "Refresh Calendar"
3. Browse events by date
4. Click "Check Conflicts" to find overlaps
5. Expand event for description

### Conflicts Page

**Features:**
- Conflict counter and alert
- Side-by-side event comparison
- Overlap duration display
- Alternative time finder
- AI email generator

**Workflow:**
1. Click "Detect Conflicts" to scan calendar
2. Review each conflict
3. Click "Find Alternative Times" for suggestions
4. Click "Generate Resolution Email" for AI draft
5. Review generated email
6. Click "Create Draft in Gmail" to save

### Compose Page

**Features:**
- To, Subject, Body fields
- Reply context (if replying)
- AI enhancement buttons (coming soon)
- Send, Save Draft, Clear, Cancel buttons

**Workflow:**
1. Fill in recipient, subject, message
2. (Optional) Use AI enhancement
3. Click "Send Email" or "Save Draft"
4. Confirmation message appears

### AI Workflow Page

**Features:**
- Workflow description
- Run button
- Progress tracking
- Results dashboard
- AI suggestions list
- Draft responses

**Workflow:**
1. Click "Run Complete AI Workflow"
2. Watch progress bar
3. Review results metrics
4. Read AI suggestions
5. Check generated drafts

---

## ⚙️ Configuration Options

### Streamlit Config

Create `.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#00E5A0"
backgroundColor = "#0D0D0F"
secondaryBackgroundColor = "#1C1C21"
textColor = "#FFFFFF"
font = "sans serif"

[server]
port = 8501
enableCORS = false
enableXsrfProtection = true

[browser]
gatherUsageStats = false
```

### Environment Variables

Edit `.env`:

```env
# Required for AI features
OPENAI_API_KEY=sk-your-key-here

# Optional customization
LLM_MODEL=gpt-4
LLM_TEMPERATURE=0.7
MAX_EMAILS=50
CALENDAR_DAYS_AHEAD=30
```

---

## 🔧 Customization

### Change Colors

Edit the CSS in `streamlit_app.py`:

```python
:root {
    --primary-color: #YOUR_COLOR;
    --secondary-color: #YOUR_COLOR;
    --accent-color: #YOUR_COLOR;
}
```

### Add New Pages

```python
# In sidebar navigation
nav_options = {
    '🆕 New Page': 'new_page',
    # ... existing pages
}

# In main content area
elif st.session_state.current_view == 'new_page':
    st.markdown('<h1 class="main-header">🆕 New Page</h1>')
    # Your page content
```

### Modify Workflow

Edit the `run_workflow()` function:

```python
def run_workflow():
    # Add custom steps
    result = st.session_state.assistant.run_ambient_agent()
    # Add custom processing
    return result
```

---

## 🐛 Troubleshooting

### Issue: "Module not found"

**Solution:**
```bash
pip install -r requirements_streamlit.txt --upgrade
```

### Issue: "Streamlit won't start"

**Solution:**
```bash
streamlit cache clear
streamlit run streamlit_app.py
```

### Issue: "Authentication failed"

**Solution:**
1. Delete `token.json`
2. Restart Streamlit
3. Re-authenticate when prompted

### Issue: "CSS not loading properly"

**Solution:**
- Clear browser cache
- Hard refresh (Ctrl+Shift+R or Cmd+Shift+R)
- Restart Streamlit

### Issue: "AI features not working"

**Solution:**
1. Check `.env` file has `OPENAI_API_KEY`
2. Verify API key is correct
3. Check OpenAI account has credits
4. Restart Streamlit

---

## 💡 Tips & Best Practices

### Performance

1. **Limit Email Fetching**
   - Start with 20-50 emails
   - Use search queries to filter
   - Increase gradually if needed

2. **Cache Results**
   - Streamlit automatically caches
   - Use session state for persistence
   - Avoid redundant API calls

3. **Optimize Workflow**
   - Run AI workflow once per session
   - Refresh only when needed
   - Use filters instead of re-fetching

### User Experience

1. **Use Progress Indicators**
   - Always show loading spinners
   - Display progress bars for long operations
   - Provide status messages

2. **Error Handling**
   - Show clear error messages
   - Provide recovery options
   - Log errors for debugging

3. **Navigation**
   - Use sidebar for main navigation
   - Keep current page highlighted
   - Provide "Back" or "Cancel" options

### Security

1. **Credentials**
   - Never commit `credentials.json` or `token.json`
   - Use `.gitignore` properly
   - Keep `.env` file secure

2. **API Keys**
   - Store in `.env`, never in code
   - Use environment variables
   - Rotate keys periodically

3. **User Data**
   - Data stays in browser session
   - Clear session on logout
   - No server-side storage

---

## 📈 Advanced Features

### Add Analytics

```python
# Track email statistics
if st.session_state.emails:
    unread_count = sum(1 for e in st.session_state.emails if e.is_unread)
    read_rate = (1 - unread_count / len(st.session_state.emails)) * 100
    st.metric("Read Rate", f"{read_rate:.1f}%")
```

### Add Charts

```python
import plotly.express as px

# Email volume by date
dates = [e.timestamp.date() for e in st.session_state.emails]
fig = px.histogram(x=dates, title="Email Volume")
st.plotly_chart(fig)
```

### Add Notifications

```python
# Show toast notification
st.toast("New email received!", icon="📧")
```

---

## 🚀 Deployment

### Deploy to Streamlit Cloud

1. Push code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect repository
4. Add secrets in dashboard:
   - `OPENAI_API_KEY`
5. Deploy!

### Deploy to Heroku

```bash
# Create Procfile
echo "web: streamlit run streamlit_app.py" > Procfile

# Create runtime.txt
echo "python-3.9.18" > runtime.txt

# Deploy
heroku create your-app-name
git push heroku main
```

### Deploy with Docker

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements_streamlit.txt .
RUN pip install -r requirements_streamlit.txt

COPY . .

EXPOSE 8501
CMD ["streamlit", "run", "streamlit_app.py"]
```

---

## 📚 Additional Resources

- [Streamlit Documentation](https://docs.streamlit.io)
- [Gmail API Guide](https://developers.google.com/gmail/api)
- [Calendar API Guide](https://developers.google.com/calendar/api)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)

---

## 🎯 Keyboard Shortcuts

When running locally:

- `r` - Rerun app
- `c` - Clear cache
- `Ctrl+C` - Stop server

---

## 🆘 Getting Help

1. Check this guide
2. Review error messages in terminal
3. Check browser console (F12)
4. Verify all files are in place
5. Test authentication separately

---

## 🎉 You're Ready!

Run the app and enjoy your beautiful AI email assistant:

```bash
streamlit run streamlit_app.py
```

Navigate to **http://localhost:8501** and start managing your emails with AI! 🚀

---

**Made with ❤️ using Streamlit | Last updated: 2024**
