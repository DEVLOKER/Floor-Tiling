from pydantic import BaseModel
from typing import Optional

class KeyRequest(BaseModel):
    force: bool = False
