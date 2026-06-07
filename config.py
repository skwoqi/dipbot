import os
from dotenv import load_dotenv

load_dotenv()


def _to_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

VK_BOT_TOKEN = os.getenv("VK_BOT_TOKEN", "")
GROUP_ID = _to_int(os.getenv("GROUP_ID", "0"))
ADMIN_PEER_ID = _to_int(os.getenv("ADMIN_PEER_ID", "0"))
ADMIN_DOMAIN = os.getenv("ADMIN_DOMAIN", "")
DB_PATH = os.getenv("DB_PATH", "vkbot.db")
