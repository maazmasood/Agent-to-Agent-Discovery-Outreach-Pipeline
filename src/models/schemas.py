from pydantic import BaseModel, Field
from typing import List, Optional, Literal

# Handshake Models

class ExecutionPlan(BaseModel):
    agents_to_invoke: List[Literal["SearchAgent", "MailAgent"]] = Field(
        description="The sequence of agents to invoke based on user query."
    )
    extracted_location: Optional[str] = Field(None, description="Location extracted from the query, if any.")
    extracted_specialty: Optional[str] = Field(None, description="Profession/Specialty requested, if any.")

class ProfessionalCandidate(BaseModel):
    name: str = Field(..., description="Name of the professional or company")
    location: str = Field(..., description="City or address of the professional")
    rating: float = Field(..., description="Star rating representing quality")
    profession: str = Field(..., description="Profession like 'Doctor', 'Engineer', 'Plumber'")
    contact_email: Optional[str] = Field(None, description="Contact email of the professional")

class SearchOutput(BaseModel):
    professionals: List[ProfessionalCandidate]

class MailConfirmation(BaseModel):
    sent_to: str = Field(..., description="Email address the message was sent to")
    subject: str = Field(..., description="Subject line of the email")
    body_preview: str = Field(..., description="A short preview of the email content")
    status: str = Field(..., description="Status of the dispatch (e.g., 'Sent Successfully')")

class BulkMailConfirmation(BaseModel):
    confirmations: List[MailConfirmation]
