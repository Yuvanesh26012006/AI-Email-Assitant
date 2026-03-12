#!/bin/bash

# Streamlit Email Assistant - Quick Start Script
# This script helps you set up and run the Streamlit email assistant

echo "╔══════════════════════════════════════════════════════════╗"
echo "║     🚀 Streamlit Email Assistant - Quick Start         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "ℹ️  $1"
}

# Step 1: Check Python version
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Checking Python version..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    print_success "Python $PYTHON_VERSION found"
else
    print_error "Python 3 not found. Please install Python 3.9+"
    exit 1
fi

# Step 2: Check for required files
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Checking required files..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -f "streamlit_app.py" ]; then
    print_success "streamlit_app.py found"
else
    print_error "streamlit_app.py not found!"
    exit 1
fi

if [ -f "ambient_email_assistant_enhanced.py" ]; then
    print_success "ambient_email_assistant_enhanced.py found"
else
    print_error "ambient_email_assistant_enhanced.py not found!"
    exit 1
fi

if [ -f "requirements_streamlit.txt" ]; then
    print_success "requirements_streamlit.txt found"
else
    print_warning "requirements_streamlit.txt not found, using requirements.txt"
fi

if [ -f "credentials.json" ]; then
    print_success "credentials.json found"
else
    print_warning "credentials.json not found - you'll need to add this"
    print_info "Follow GOOGLE_OAUTH_SETUP.md to get credentials.json"
fi

# Step 3: Install dependencies
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Installing dependencies..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

read -p "Install/update dependencies? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ -f "requirements_streamlit.txt" ]; then
        print_info "Installing from requirements_streamlit.txt..."
        pip install -r requirements_streamlit.txt
    else
        print_info "Installing from requirements.txt..."
        pip install -r requirements.txt
        pip install streamlit streamlit-extras plotly pandas
    fi
    print_success "Dependencies installed"
else
    print_warning "Skipping dependency installation"
fi

# Step 4: Check environment file
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4: Checking environment configuration..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -f ".env" ]; then
    print_success ".env file found"
    
    # Check for OpenAI API key
    if grep -q "OPENAI_API_KEY=" .env; then
        print_success "OPENAI_API_KEY configured"
    else
        print_warning "OPENAI_API_KEY not found in .env"
        print_info "AI features will be disabled"
    fi
else
    print_warning ".env file not found"
    
    if [ -f "env.example" ]; then
        read -p "Create .env from env.example? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            cp env.example .env
            print_success ".env created from template"
            print_info "Edit .env and add your OPENAI_API_KEY for AI features"
        fi
    fi
fi

# Step 5: Create Streamlit config (optional)
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 5: Setting up Streamlit configuration..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ ! -d ".streamlit" ]; then
    read -p "Create Streamlit config? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        mkdir -p .streamlit
        
        cat > .streamlit/config.toml << EOF
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
EOF
        print_success "Streamlit config created"
    fi
else
    print_success "Streamlit config already exists"
fi

# Step 6: Ready to launch
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Setup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

print_success "All checks passed! Ready to launch."
echo ""
print_info "To start the Streamlit app, run:"
echo "   streamlit run streamlit_app.py"
echo ""
print_info "The app will open automatically in your browser at:"
echo "   http://localhost:8501"
echo ""

read -p "Launch Streamlit app now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "🚀 Launching Streamlit Email Assistant..."
    echo ""
    streamlit run streamlit_app.py
else
    echo ""
    print_info "You can launch the app anytime with:"
    echo "   streamlit run streamlit_app.py"
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📚 Documentation:"
echo "   - STREAMLIT_GUIDE.md - Complete Streamlit guide"
echo "   - GOOGLE_OAUTH_SETUP.md - OAuth setup instructions"
echo "   - README_ENHANCED.md - Full documentation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
