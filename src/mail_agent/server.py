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
import base64
from email.message import EmailMessage
import smtplib

from src.models.schemas import MailConfirmation, BulkMailConfirmation

def send_professional_email(to_email: str, name: str, profession: str, body: str, dev_email: str = None):
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    
    if not gmail_user or not gmail_password:
        print("[!] GMAIL_USER or GMAIL_APP_PASSWORD not set in .env. Skipping email.")
        return False
        
    print(f"[*] Sending email to {name} ({to_email}) via SMTP...")
    
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = f"Inquiry for {profession} services - {name}"
    msg['From'] = gmail_user
    
    # Devmode logic: override recipient if dev_email is provided
    if dev_email:
        msg['To'] = dev_email
        print(f"      [DEVMODE] Redirecting from {to_email} to {dev_email}")
    else:
        msg['To'] = to_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_password)
            server.send_message(msg)
        print(f"[+] Email sent successfully via SMTP!")
        return True
    except Exception as e:
        print(f"[!] Errored while sending via SMTP: {e}")
        return False

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class NavigatorAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        try:
            # 1. Collect all text from every possible place in context
            text_input = ""
            
            if hasattr(context, 'message') and hasattr(context.message, 'parts'):
                parts = context.message.parts
            elif hasattr(context, 'model_dump'):
                parts = context.model_dump().get('message', {}).get('parts', [])
            elif isinstance(context, dict):
                parts = context.get('message', {}).get('parts', [])
            else:
                parts = []
            
            for p in parts:
                if isinstance(p, dict):
                    if p.get('kind') == 'text':
                        text_input += p.get('text', '')
                    elif 'text' in p:
                        text_input += p['text']
                elif hasattr(p, 'text'):
                    text_input += str(p.text)
                elif hasattr(p, 'root') and hasattr(p.root, 'text'):
                    text_input += str(p.root.text)
                elif hasattr(p, 'kind') and p.kind == 'text' and hasattr(p, 'text'):
                    text_input += str(p.text)
                elif isinstance(p, str):
                    text_input += p

            if not text_input and not isinstance(context, (dict, list)):
                text_input = str(context)

            input_data = json.loads(text_input)
            
            # Case 1: Real Send (Confirmed by user in main.py)
            if isinstance(input_data, dict) and input_data.get("action") == "send":
                mail_data_list = input_data.get("mail_data_list", [])
                dev_email = input_data.get("dev_email")
                
                confirmations = []
                for mail in mail_data_list:
                    contact_email = mail.get("sent_to")
                    body = mail.get("body", "")
                    name = mail.get("name", "Professional")
                    profession = mail.get("profession", "Services")
                    
                    success = send_professional_email(contact_email, name, profession, body, dev_email)
                    
                    confirmations.append(MailConfirmation(
                        sent_to=dev_email if dev_email else contact_email,
                        subject=mail.get("subject", ""),
                        body_preview=body[:100] + "...",
                        status="Sent Successfully" if success else "Failed"
                    ))
                
                bulk_conf = BulkMailConfirmation(confirmations=confirmations)
                await event_queue.enqueue_event(new_agent_text_message(bulk_conf.model_dump_json()))
                return

            # Case 2: Draft (Default flow from pipeline)
            professionals_data = input_data.get("scout_data", text_input)
            dev_email = input_data.get("dev_email")
                
        except Exception as e:
            print(f"Exception parsing input: {e}")
            professionals_data = text_input
            dev_email = None
            
        print("[*] Mail Sending Agent synthesizing bulk dispatch confirmation (DRAFT)...")
        
        schema = BulkMailConfirmation.model_json_schema()
        
        system_prompt = f"""
        You are the Mail Sending Agent (Agent B).
        You generate personalized emails for the list of professionals provided.
        
        Professionals Data:
        {professionals_data}
        
        Tasks:
        1. For EACH professional in the list, compose a short, professional inquiry email.
        2. Set 'subject' to something relevant like "Inquiry for [Profession] services".
        3. Include the original 'contact_email', 'name', and 'profession' in each draft object.
        4. Produce a BulkMailConfirmation JSON object.
        5. CRITICAL: For each confirmation, set 'status' to 'DRAFT - Pending Confirmation'.
        6. Include a 'body' field in each confirmation object containing the full email text.
        
        You must output valid JSON strictly matching this exact schema:
        {json.dumps(schema, indent=2)}
        """
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Create drafts for all professionals."}
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
        id='mail_dispatch',
        name='Mail Dispatcher',
        description='Dispatches inquiry emails to selected professionals.',
        tags=['mail', 'dispatch', 'professional'],
        examples=['JSON Professional Array'],
    )

    agent_card = AgentCard(
        name='Mail Agent',
        description='Automatically sends inquiry requests to discovered professionals.',
        url='http://localhost:8003/',
        version='2.0.0',
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=False),
        skills=[skill],
        supports_authenticated_extended_card=False,
    )

    request_handler = DefaultRequestHandler(
        agent_executor=NavigatorAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    uvicorn.run(server.build(), host='0.0.0.0', port=8003)
