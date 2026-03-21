import os
import json
from groq import Groq
from src.models.schemas import ExecutionPlan
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def invoke_director(user_query: str) -> ExecutionPlan:
    schema = ExecutionPlan.model_json_schema()
    
    system_prompt = f"""
    You are the Director Orchestrator (Agent 0).
    You are an intelligent LLM router. Your job is to analyze the user's query and 
    decide which specialized agents need to be invoked to fulfill the request.
    
    Agents available:
    1. 'SearchAgent' - Discovers professionals (e.g., plumbers, doctors, engineers) based on location and profession.
    2. 'MailAgent' - Generates personalized inquiry emails for all discovered professionals.
    
    Routing Rules:
    - If the user wants to find professionals and contact them, you MUST chain ["SearchAgent", "MailAgent"].
    - If the user ONLY wants to find professionals without emailing, invoke ONLY ["SearchAgent"].
    
    Extraction Rules:
    - Always extract the 'extracted_location' and 'extracted_specialty' (which is the profession requested).
    
    You must output valid JSON strictly matching this exact schema:
    {json.dumps(schema, indent=2)}
    """
    
    print(f"[*] Director is analyzing: '{user_query}'...")
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ],
        response_format={"type": "json_object"},
        temperature=0.0
    )
    
    content = response.choices[0].message.content
    try:
        plan = ExecutionPlan.model_validate_json(content)
        print(f"[+] Director routing plan: {plan.agents_to_invoke}")
        return plan
    except Exception as e:
        print(f"[!] Director output failed validation: {e}")
        print(f"Raw output: {content}")
        raise
