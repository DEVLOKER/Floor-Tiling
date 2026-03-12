from pydantic import BaseModel

class FingerprintRequest(BaseModel):
    storage_serial: str
    cpu_serial: str = ""
    board_serial: str = ""
    mac_serial: str = ""
