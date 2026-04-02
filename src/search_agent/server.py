import os
import sys

# Add project root to sys.path if running as a script
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

import json
import uvicorn
import re
import asyncio
from groq import Groq
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message

# Removed MCP client imports
# from mcp import ClientSession, StdioServerParameters
# from mcp.client.stdio import stdio_client

from src.models.schemas import SearchOutput

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

async def find_email_on_website(page, website_url):
    """Attempt a more thorough search for an email address on the provided website URL."""
    if not website_url or "google.com" in website_url or "facebook.com" in website_url:
        return None
    
    try:
        print(f"[*] Browsing website for contact info: {website_url}")
        # Use a more relaxed wait to avoid total timeout
        await page.goto(website_url, wait_until="domcontentloaded", timeout=20000)
        
        async def scrape_from_current_page(p):
            content = await p.content()
            # Regex for visible emails, excluding images/junk
            email_pattern = r'[a-zA-Z0-9._%+-]+@(?!(?:example|domain|name)\.)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            emails = re.findall(email_pattern, content)
            return [e for e in emails if not e.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'))]

        found_emails = await scrape_from_current_page(page)
        if found_emails:
            return found_emails[0]
            
        # If no email on home, check common sub-pages
        common_pages = ["contact", "about", "support", "info"]
        all_links = await page.query_selector_all("a")
        
        target_hrefs = []
        for link in all_links:
            try:
                href = await link.get_attribute("href")
                text = await link.inner_text()
                if href and any(p in href.lower() or p in text.lower() for p in common_pages):
                    if not href.startswith("http"):
                        from urllib.parse import urljoin
                        href = urljoin(website_url, href)
                    if href not in target_hrefs:
                        target_hrefs.append(href)
            except:
                continue

        for href in target_hrefs[:3]: # Check top 3 likely pages
            try:
                print(f"[*] Checking sub-page: {href}")
                await page.goto(href, wait_until="domcontentloaded", timeout=10000)
                sub_emails = await scrape_from_current_page(page)
                if sub_emails:
                    return sub_emails[0]
            except:
                continue
                
        return None
    except Exception as e:
        print(f"[!] Email scraping error for {website_url}: {e}")
        return None

async def web_mcp_google_maps_search(location: str, specialty: str) -> str:
    """Uses Playwright to scrape Google Maps website directly for professionals."""
    print(f"[*] Starting web-based Google Maps search for: {specialty} in {location}")
    
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Go to Google Maps search
        search_query = f"{specialty} in {location}"
        url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"
        print(f"[*] Navigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait for result cards to appear
        try:
            await page.wait_for_selector('div[role="article"]', timeout=20000)
        except Exception as e:
            print(f"[!] No results found or page load timeout: {e}")
            await browser.close()
            return json.dumps([])

        # Extract up to 5 top results to avoid long wait times for email scraping
        articles = await page.query_selector_all('div[role="article"]')
        for article in articles[:5]:
            try:
                # Get Name
                name_el = await article.query_selector('div.fontHeadlineSmall')
                name = await name_el.inner_text() if name_el else "Unknown"
                
                # Get Rating
                rating_el = await article.query_selector('span.MW4etd')
                rating_str = await rating_el.inner_text() if rating_el else "0.0"
                rating = float(rating_str.strip()) if rating_str else 0.0
                
                # Get Location/Address
                # This is tricky as structure varies, but often the 2nd line of text
                address_container = await article.query_selector('div.W4Efsd:nth-of-type(2)')
                address = await address_container.inner_text() if address_container else location
                
                # Get Website URL
                website_el = await article.query_selector('a[aria-label*="website"]')
                website_url = await website_el.get_attribute("href") if website_el else None
                
                email = None
                if website_url:
                    # Create a new page for website scraping to keep maps session clean
                    site_page = await context.new_page()
                    email = await find_email_on_website(site_page, website_url)
                    await site_page.close()
                
                results.append({
                    "name": name,
                    "location": address.split('·')[0].strip() if '·' in address else address.strip(),
                    "rating": rating,
                    "website": website_url,
                    "email": email,
                    "types": [specialty]
                })
                print(f"[+] Found: {name} | Rating: {rating} | Email: {email}")
            except Exception as e:
                print(f"[!] Error extracting article details: {e}")
                continue
                
        await browser.close()
    
    return json.dumps(results)

class SearchAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        try:
            # 1. Collect all text from every possible place in context
            text_input = ""
            
            # Identify parts of the message
            if hasattr(context, 'message') and hasattr(context.message, 'parts'):
                parts = context.message.parts
            elif hasattr(context, 'model_dump'):
                parts = context.model_dump().get('message', {}).get('parts', [])
            elif isinstance(context, dict):
                parts = context.get('message', {}).get('parts', [])
            else:
                parts = []
            
            # Extract text from parts (handling different SDK versions)
            for p in parts:
                if isinstance(p, dict):
                    if p.get('kind') == 'text':
                        text_input += p.get('text', '')
                    elif 'text' in p:
                        text_input += p['text']
                elif hasattr(p, 'text'):
                    text_input += str(p.text)
                elif hasattr(p, 'root') and hasattr(p.root, 'text'):
                    # Handles newer SDK where Part has a 'root' attribute
                    text_input += str(p.root.text)
                elif hasattr(p, 'kind') and p.kind == 'text' and hasattr(p, 'text'):
                    text_input += str(p.text)
                elif isinstance(p, str):
                    text_input += p

            # Fallback if no text collected but context is string-like
            if not text_input and not isinstance(context, (dict, list)):
                text_input = str(context)

            # 2. Parse text as JSON
            try:
                # Cleanup text_input if it looks like a repr
                if text_input.startswith('<') and text_input.endswith('>'):
                    import re
                    json_match = re.search(r'(\{.*\})', text_input)
                    if json_match:
                        text_input = json_match.group(1)
                
                input_data = json.loads(text_input)
                location = input_data.get("location", "Chicago")
                specialty = input_data.get("specialty", "clinical psychologist")
            except Exception:
                # If not JSON, it might be raw text; we use defaults as fallback
                location = "Chicago"
                specialty = "clinical psychologist"
                
        except Exception as e:
            print(f"Exception extracting inputs: {e}")
            location = "Chicago"
            specialty = "clinical psychologist"
            
        print(f"[*] Search Agent Server processing request for {specialty} in {location}")

        raw_maps_data = await web_mcp_google_maps_search(location, specialty)
        schema = SearchOutput.model_json_schema()

        system_prompt = f"""
        You are the Search Agent (Agent A).
        You transform raw JSON data output from Google Maps/Places MCP server 
        into a strictly structured JSON list of ProfessionalCandidates.
        
        Raw Maps Data:
        {raw_maps_data}
        
        Task: Extract up to 10 top professionals. Map the 'formatted_address' or 'vicinity' to 'location' 
        and determine their primary profession based on the context. You MUST preserve the 'website' field if provided in the raw data.
        If an email is provided in the raw data, use it for 'contact_email'. Otherwise, generate a realistic 'contact_email' for each professional based on their name or company.
        
        You must output valid JSON strictly matching this exact schema:
        {json.dumps(schema, indent=2)}
        """

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Extract the professional candidates into the JSON schema."}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )

        content = response.choices[0].message.content
        await event_queue.enqueue_event(new_agent_text_message(content))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass

if __name__ == '__main__':
    skill = AgentSkill(
        id='professional_discovery',
        name='Professional Discovery',
        description='Finds highly rated professionals based on location and profession via Google Maps MCP.',
        tags=['search', 'discovery', 'professionals', 'maps'],
        examples=['{"location": "London", "specialty": "plumber"}'],
    )

    agent_card = AgentCard(
        name='Search Agent',
        description='Discovers professionals by directly searching the Google Maps website and extracting contact emails.',
        url='http://localhost:8001/',
        version='2.0.0',
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=False),
        skills=[skill],
        supports_authenticated_extended_card=False,
    )

    request_handler = DefaultRequestHandler(
        agent_executor=SearchAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    uvicorn.run(server.build(), host='0.0.0.0', port=8001)
