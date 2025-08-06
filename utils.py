from datetime import datetime


def get_timestamp() -> str:
    timestamp = datetime.now().strftime("%d%b%Y_%I%M%S%p").upper()
    return timestamp
