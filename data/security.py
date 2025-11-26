import bcrypt

def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt.
    Returns a UTF-8 string representation of the hash.
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")

def verify_password(password: str, stored_hash: str) -> bool:
    """
    Check a plaintext password against a stored bcrypt hash.
    """
    password_bytes = password.encode("utf-8")
    hash_bytes = stored_hash.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hash_bytes)
