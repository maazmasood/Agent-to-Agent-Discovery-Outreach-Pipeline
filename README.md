# A2A: Agent-to-Agent Professional Discovery & Outreach Pipeline

This project implements an automated pipeline for discovering professionals (via Google Maps) and drafting/sending personalized inquiry emails. It uses a multi-agent architecture where agents communicate over HTTP/JSON-RPC.

## Architecture

1.  **Director Agent**: Analyzes the user's natural language query using the Director LLM to route to the appropriate agents and extract specific location, specialty, and inquiry details.

2.  **Search Agent (Port 8001)**: Directly search the **Google Maps website** using Playwright. It automatically visits professional websites and extracts contact emails for inquiry outreach.

3.  **Mail Agent (Port 8003)**: A specialized LLM-powered agent that synthesizes high-quality, professional inquiry drafts based on the user's specific topic and handles the dispatch via Gmail SMTP.

## Getting Started

### 1. Environment Setup
Create a `.env` file with the following variables:
```env
GROQ_API_KEY=your_groq_key
GOOGLE_MAPS_API_KEY=your_google_maps_key
GMAIL_USER=your_email@gmail.com
GMAIL_APP_PASSWORD=your_app_password
DEV_EMAIL=your_test_email@gmail.com
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Run the Agents
You need to start the agent servers in separate terminals:
```powershell
# Terminal 1: Search Agent
python src/search_agent/server.py

# Terminal 2: Mail Agent
python src/mail_agent/server.py
```

### 4. Run the Pipeline
Execute the main script with your query:
```powershell
python main.py "find me dentists in New York and inquire about checkup costs"
```

## Developer Notes

### Web-Based Professional Discovery
> [!IMPORTANT]
> This project now uses **Playwright** to search the Google Maps website directly. This means it can discover contact email addresses that are not available through the official Google Maps API.

### Known Limitations/Gotchas
- **Import Path**: If running servers directly as scripts, the project root is automatically added to `sys.path` to resolve the `src` package.
- **A2A SDK Compatibility**: The agents use a robust extraction logic to handle various formats of `RequestContext` and `Message` parts across different A2A SDK versions.
- **Dev Mode**: Emails are redirected to `DEV_EMAIL` by default to prevent accidental outreach during testing.
