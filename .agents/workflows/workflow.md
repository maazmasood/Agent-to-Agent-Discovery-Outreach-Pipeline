---
description: Start A2A Pipeline and Setup Environment
---

# A2A Pipeline Workflow

This document explains how the A2A pipeline operates and provides a step-by-step workflow for configuring and running the multi-agent system.

## How It Works

The A2A pipeline consists of an orchestrator and specialized agents working together:
1. **Director Agent (`main.py`)**: Analyzes the user's natural language input using `src.director_agent.agent`, extracts location/specialty, and determine the execution plan.
2. **Search Agent (Port 8001)**: Found in `src/search_agent/server.py`. It discovers local professionals by directly searching the Google Maps website using Playwright and automatically extracting contact emails from their official websites.
3. **Mail Agent (Port 8003)**: Found in `src/mail_agent/server.py`. It synthesizes premium, personalized email drafts based on specific user inquiry topics and handles the dispatch via SMTP.

## Environment Setup Workflow

Follow these steps to configure the application environment for successful execution.

1. **Install Dependencies:**
// turbo
```bash
pip install -r requirements.txt
playwright install chromium
```

2. **Configure Environment Variables:**
Ensure you have a `.env` file containing your credentials (Note: GOOGLE_MAPS_API_KEY is no longer required):
```bash
GROQ_API_KEY="your_groq_api_key"
GMAIL_USER="your_email@gmail.com"
GMAIL_APP_PASSWORD="your_gmail_app_password"
DEV_EMAIL="your_test_email@gmail.com"
```

3. **Gmail Setup:**
The Mail agent uses Gmail's SMTP server to send inquiry requests. 
- You MUST use an **App Password** if you have 2FA enabled (recommended). 
- Go to Google Account Settings -> Security -> App Passwords to generate one.

## Running the Pipeline

4. Start the Agent servers. You run these concurrently in separate terminals:
```bash
python src/search_agent/server.py
```
```bash
python src/mail_agent/server.py
```

5. With the servers active, run the Director from the root folder:
```bash
python main.py "Find me dentists in New York and inquire about annual checkup charges"
```
