@echo off
REM Streamlit Email Assistant - Quick Start Script for Windows

echo ================================================================
echo     Streamlit Email Assistant - Quick Start
echo ================================================================
echo.

REM Check Python
echo Step 1: Checking Python...
echo ------------------------------------------------
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.9+
    pause
    exit /b 1
)
echo [OK] Python found
echo.

REM Check files
echo Step 2: Checking required files...
echo ------------------------------------------------

if exist streamlit_app.py (
    echo [OK] streamlit_app.py found
) else (
    echo [ERROR] streamlit_app.py not found!
    pause
    exit /b 1
)

if exist ambient_email_assistant_enhanced.py (
    echo [OK] ambient_email_assistant_enhanced.py found
) else (
    echo [ERROR] ambient_email_assistant_enhanced.py not found!
    pause
    exit /b 1
)

if exist credentials.json (
    echo [OK] credentials.json found
) else (
    echo [WARNING] credentials.json not found
    echo You'll need to add this - see GOOGLE_OAUTH_SETUP.md
)
echo.

REM Install dependencies
echo Step 3: Installing dependencies...
echo ------------------------------------------------
set /p install="Install/update dependencies? (y/n): "
if /i "%install%"=="y" (
    if exist requirements_streamlit.txt (
        echo Installing from requirements_streamlit.txt...
        pip install -r requirements_streamlit.txt
    ) else (
        echo Installing from requirements.txt...
        pip install -r requirements.txt
        pip install streamlit streamlit-extras plotly pandas
    )
    echo [OK] Dependencies installed
) else (
    echo Skipping dependency installation
)
echo.

REM Check .env file
echo Step 4: Checking environment...
echo ------------------------------------------------
if exist .env (
    echo [OK] .env file found
    findstr /C:"OPENAI_API_KEY=" .env >nul
    if %errorlevel% equ 0 (
        echo [OK] OPENAI_API_KEY configured
    ) else (
        echo [WARNING] OPENAI_API_KEY not found in .env
        echo AI features will be disabled
    )
) else (
    echo [WARNING] .env file not found
    if exist env.example (
        set /p createenv="Create .env from env.example? (y/n): "
        if /i "!createenv!"=="y" (
            copy env.example .env
            echo [OK] .env created from template
            echo Edit .env and add your OPENAI_API_KEY
        )
    )
)
echo.

REM Create Streamlit config
echo Step 5: Setting up Streamlit config...
echo ------------------------------------------------
if not exist .streamlit (
    set /p createconfig="Create Streamlit config? (y/n): "
    if /i "!createconfig!"=="y" (
        mkdir .streamlit
        (
            echo [theme]
            echo primaryColor = "#00E5A0"
            echo backgroundColor = "#0D0D0F"
            echo secondaryBackgroundColor = "#1C1C21"
            echo textColor = "#FFFFFF"
            echo font = "sans serif"
            echo.
            echo [server]
            echo port = 8501
            echo enableCORS = false
            echo enableXsrfProtection = true
            echo.
            echo [browser]
            echo gatherUsageStats = false
        ) > .streamlit\config.toml
        echo [OK] Streamlit config created
    )
) else (
    echo [OK] Streamlit config already exists
)
echo.

REM Ready to launch
echo ================================================================
echo     Setup Complete!
echo ================================================================
echo.
echo [OK] All checks passed! Ready to launch.
echo.
echo To start the Streamlit app, run:
echo    streamlit run streamlit_app.py
echo.
echo The app will open at: http://localhost:8501
echo.

set /p launch="Launch Streamlit app now? (y/n): "
if /i "%launch%"=="y" (
    echo.
    echo Launching Streamlit Email Assistant...
    echo.
    streamlit run streamlit_app.py
) else (
    echo.
    echo You can launch the app anytime with:
    echo    streamlit run streamlit_app.py
    echo.
)

echo ================================================================
echo Documentation:
echo    - STREAMLIT_GUIDE.md - Complete Streamlit guide
echo    - GOOGLE_OAUTH_SETUP.md - OAuth setup instructions
echo    - README_ENHANCED.md - Full documentation
echo ================================================================

pause
