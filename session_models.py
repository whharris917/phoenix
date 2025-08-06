from pydantic import BaseModel, ConfigDict
from memory_manager import MemoryManager
from proxies import HavenProxyWrapper


class ActiveSession(BaseModel):
    """Represents a live user session with all its associated objects."""

    # This config allows the model to handle complex, non-pydantic
    # objects like MemoryManager without validation errors.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    chat: HavenProxyWrapper
    memory: MemoryManager
    name: str
