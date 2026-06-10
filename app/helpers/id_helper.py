import uuid


def generate_id() -> str:
    """Return a new random UUID string."""
    return str(uuid.uuid4())
