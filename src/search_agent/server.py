import os
import sys

# Add project root to sys.path if running as a script
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

import json
import uvicorn
from groq import Groq
from dotenv import load_dotenv

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.models.schemas import SearchOutput

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def mock_mcp_google_maps_search(location: str, specialty: str) -> str:
    """Mock fallback logic if the real MCP connection fails or user doesn't have an API key."""
    return json.dumps([
        {"name": f"{specialty.capitalize()} Expert 1", "vicinity": f"123 Professional St, {location}", "rating": 4.8, "types": [specialty.lower()]},
        {"name": f"{specialty.capitalize()} Services Plus", "vicinity": f"456 Service Blvd, {location}", "rating": 4.5, "types": [specialty.lower()]},
        {"name": f"Top Tier {specialty.capitalize()}", "vicinity": f"789 Quality Ave, {location}", "rating": 4.9, "types": [specialty.lower()]},
        {"name": f"Reliable {specialty.capitalize()} Co.", "vicinity": f"101 Trust St, {location}", "rating": 4.7, "types": [specialty.lower()]},
        {"name": f"Elite {specialty.capitalize()}", "vicinity": f"202 Excellence Rd, {location}", "rating": 4.6, "types": [specialty.lower()]},
        {"name": f"{specialty.capitalize()} Solutions", "vicinity": f"303 Innovation Ln, {location}", "rating": 4.4, "types": [specialty.lower()]},
        {"name": f"Global {specialty.capitalize()}", "vicinity": f"404 World St, {location}", "rating": 4.3, "types": [specialty.lower()]},
        {"name": f"Local {specialty.capitalize()} Pro", "vicinity": f"505 Neighborhood Way, {location}", "rating": 4.5, "types": [specialty.lower()]},
        {"name": f"Prime {specialty.capitalize()}", "vicinity": f"606 Main St, {location}", "rating": 4.7, "types": [specialty.lower()]},
        {"name": f"Expert {specialty.capitalize()} Hub", "vicinity": f"707 Center Blvd, {location}", "rating": 4.8, "types": [specialty.lower()]}
    ])

async def real_mcp_google_maps_search(location: str, specialty: str) -> str:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    
    # Intelligent fallback to mock data if the key is empty or generic
    if not api_key or api_key.strip() == "" or "your_" in api_key:
        print("[!] Valid GOOGLE_MAPS_API_KEY not found. Seamlessly falling back to Mock Provider Data for demonstration.")
        return mock_mcp_google_maps_search(location, specialty)
        
    env = os.environ.copy()
    env["GOOGLE_MAPS_API_KEY"] = api_key

    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-google-maps"],
        env=env
    )
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                tools = await session.list_tools()
                tool_name = None
                for tool in tools.tools:
                    if "text_search" in tool.name or "search" in tool.name:
                        tool_name = tool.name
                        break
                        
                if not tool_name:
                    return json.dumps([{"error": "No suitable search tool found on Google Maps MCP."}])
                
                query = f"{specialty} in {location}"
                print(f"[*] Dispatching realtime MCP query: '{query}' via tool '{tool_name}'...")
                
                result = await session.call_tool(tool_name, arguments={"query": query})
                
                output_texts = [content.text for content in result.content if content.type == "text"]
                final_text = "\n".join(output_texts)
                
                # If the demo key is accepted but fails the Places API billing check or returns empty
                if not final_text.strip() or final_text.strip() == "[]" or "error" in final_text.lower() or "denied" in final_text.lower():
                    print("[!] Active Maps key returned empty or unauthorized data. Seamlessly falling back to mock provider data.")
                    return mock_mcp_google_maps_search(location, specialty)
                    
                return final_text
    except Exception as e:
        print(f"[!] Realtime MCP failure: {e}. Falling back to mock data.")
        return mock_mcp_google_maps_search(location, specialty)

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

        raw_maps_data = await real_mcp_google_maps_search(location, specialty)
        schema = SearchOutput.model_json_schema()

        system_prompt = f"""
        You are the Search Agent (Agent A).
        You transform raw JSON data output from Google Maps/Places MCP server 
        into a strictly structured JSON list of ProfessionalCandidates.
        
        Raw Maps Data:
        {raw_maps_data}
        
        Task: Extract up to 10 top professionals. Map the 'formatted_address' or 'vicinity' to 'location' 
        and determine their primary profession based on the context. Also, generate a realistic 'contact_email' for each professional based on their name or company. If errors are present, try to extract a mock example or return zero array if no data.
        
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
        description='Discovers professionals in realtime using Google Maps MCP data.',
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
