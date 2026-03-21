import sys
import json
import asyncio
from uuid import uuid4
import httpx

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest

from src.director_agent.agent import invoke_director

async def a2a_invoke(port: int, input_text: str) -> str:
    base_url = f'http://localhost:{port}'
    
    # Increase timeout to 60 seconds to allow for MCP cold-starts and LLM reasoning
    async with httpx.AsyncClient(timeout=60.0) as httpx_client:
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=base_url)
        
        try:
            agent_card = await resolver.get_agent_card()
        except Exception as e:
            print(f"[!] Server at {base_url} is not responding. Ensure it is running.")
            return "{}"

        client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)

        send_message_payload = {
            'message': {
                'role': 'user',
                'parts': [{'kind': 'text', 'text': input_text}],
                'messageId': uuid4().hex,
            },
        }

        request = SendMessageRequest(
            id=str(uuid4()), params=MessageSendParams(**send_message_payload)
        )

        response = await client.send_message(request)
        
        try:
            return response.model_dump_json(indent=2)
        except Exception as e:
            return str(response)

async def async_main():
    if len(sys.argv) < 2:
        print("Usage: python main.py \"Your query here\"")
        print("Example 1: python main.py \"Find me a clinical psychologist in Chicago\"")
        print("Example 2: python main.py \"What is my out of network deductible?\"")
        sys.exit(1)
        
    user_query = sys.argv[1]
    
    print("="*70)
    print(f"USER QUERY: {user_query}")
    print("="*70)
    
    # --- Agent 0: The Director ---
    plan = invoke_director(user_query)
    print(f"> Execution Plan: {plan.agents_to_invoke}")
    print(f"> Extracted Loc: {plan.extracted_location} | Spec: {plan.extracted_specialty}")
    print("-" * 70)
    
    scout_data_str = "{}"
    
    # --- Agent A: The Search Agent (Port 8001) ---
    if "SearchAgent" in plan.agents_to_invoke:
        print("[*] Contacting Search Agent Server on port 8001...")
        loc = plan.extracted_location or "Unknown Location"
        spec = plan.extracted_specialty or "Professional"
        payload = json.dumps({"location": loc, "specialty": spec})
        
        scout_data_raw = await a2a_invoke(8001, payload)
        try:
            scout_data_str = json.loads(scout_data_raw).get("result", {}).get("parts", [{}])[0].get("text", scout_data_raw)
        except Exception:
            scout_data_str = scout_data_raw
            
        print("[+] A2A Handshake successful: Retrieved Scout Data.")
        print(f"      [DEBUG] Scout Output -> {scout_data_str}")
        print("-" * 70)
        
    # --- Agent B: The Mail Agent (Port 8003) ---
    if "MailAgent" in plan.agents_to_invoke:
        print("[*] Contacting Mail Agent Server on port 8003...")
        
        # User requested devmode with a specific temp email
        dev_email = env.get("DEV_EMAIL") 
        print(f"[*] DEVMODE ACTIVE: All emails will be redirected to {dev_email}")

        # Step 1: Draft the emails
        draft_payload = json.dumps({
            "scout_data": scout_data_str,
            "dev_email": dev_email
        })
        bulk_draft_raw = await a2a_invoke(8003, draft_payload)
        
        try:
            # Parse the inner JSON that strictly matches BulkMailConfirmation
            inner_text = json.loads(bulk_draft_raw).get("result", {}).get("parts", [{}])[0].get("text", "")
            bulk_conf = json.loads(inner_text)
            confirmations = bulk_conf.get("confirmations", [])
            
            print("\n" + "="*70)
            print("                        DRAFT EMAILS PREVIEW")
            print("="*70)
            for idx, conf in enumerate(confirmations):
                print(f"[{idx+1}] To: {conf.get('sent_to')} | Subject: {conf.get('subject')}")
                print(f"    Preview: {conf.get('body_preview')}")
            print("-" * 70)
            
            # Step 2: Confirmation
            confirm = input(f"\n[?] SEND {len(confirmations)} EMAILS? (y/N): ").lower().strip()
            
            if confirm == 'y':
                print("[*] Dispatching confirmed emails...")
                final_payload = json.dumps({
                    "action": "send", 
                    "mail_data_list": confirmations,
                    "dev_email": dev_email
                })
                final_conf_raw = await a2a_invoke(8003, final_payload)
                
                final_text = json.loads(final_conf_raw).get("result", {}).get("parts", [{}])[0].get("text", "")
                final_bulk_conf = json.loads(final_text)
                
                print("\n" + "="*70)
                print("                        FINAL DISPATCH STATUS")
                print("="*70)
                for conf in final_bulk_conf.get("confirmations", []):
                    print(f"To: {conf.get('sent_to')} -> {conf.get('status')}")
                print("="*70)
            else:
                print("[!] Email dispatch cancelled by user.")
                print("="*70)
                
        except Exception as e:
            print(f"\n[!] Failed to process Mail Confirmation: {e}")
            print(f"Raw Output: {bulk_draft_raw}")
            
    elif "MailAgent" not in plan.agents_to_invoke and scout_data_str:
        print("\n" + "="*70)
        print("                      SEARCH RESULT")
        print("="*70)
        print(scout_data_str)
        print("="*70)

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
