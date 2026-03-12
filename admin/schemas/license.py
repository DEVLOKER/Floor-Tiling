from pydantic import BaseModel
from typing import Optional

class IssueRequest(BaseModel):
    customer: str
    fingerprint: str
    expires: Optional[str] = None
    out: str = ""
