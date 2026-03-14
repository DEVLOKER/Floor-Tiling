from pydantic import BaseModel
from typing import Optional

class BuildClientRequest(BaseModel):
    partition: str
    license_data: Optional[str] = None
    public_key: Optional[str] = None
