# A2A: Agent-to-Agent Professional Discovery & Outreach Pipeline

This project implements an automated pipeline for discovering professionals (via Google Maps) and drafting/sending personalized inquiry emails. It uses a multi-agent architecture where agents communicate over HTTP/JSON-RPC.

## Architecture

1.  **Director Agent**: Analyzes the user's query and routes it to the appropriate agents (Search and/or Mail).
2.  **Search Agent (Port 8001)**: Interacts with the Google Maps MCP server to find professionals based on specialty and location.
3.  **Mail Agent (Port 8003)**: Synthesizes personalized email drafts for the discovered professionals and handles the actual dispatch via SMTP.

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
python main.py "find me plumbers in newyork and send them an inquiry email"
```

## Developer Notes

### Google Maps Integration
> [!IMPORTANT]
> This project has been primarily tested using the **Google Maps Mock API** fallback logic. 
> 
> If you are using a real API key, please ensure the **Places API** is enabled and billing is active in your Google Cloud Console. If you encounter any issues with the realtime MCP connection while using a real key, please **create an issue** in the repository.

### Known Limitations/Gotchas
- **Import Path**: If running servers directly as scripts, the project root is automatically added to `sys.path` to resolve the `src` package.
- **A2A SDK Compatibility**: The agents use a robust extraction logic to handle various formats of `RequestContext` and `Message` parts across different A2A SDK versions.
- **Dev Mode**: Emails are redirected to `DEV_EMAIL` by default to prevent accidental outreach during testing.
