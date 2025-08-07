from datetime import datetime
from tracer import trace

@trace
def get_timestamp() -> str:
    timestamp = datetime.now().strftime("%d%b%Y_%I%M%S%p").upper()
    return timestamp
