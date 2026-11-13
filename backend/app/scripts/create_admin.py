"""Create or promote an admin: python -m app.scripts.create_admin EMAIL "Full Name" """
import getpass
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models import User


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit('Usage: python -m app.scripts.create_admin EMAIL "Full Name"')
    email, name = sys.argv[1].lower(), sys.argv[2]
    password = getpass.getpass("Admin password (min 8 chars, letters+digits): ")
    if len(password) < 8 or not any(c.isdigit() for c in password) or not any(c.isalpha() for c in password):
        sys.exit("Password too weak")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user:
            user.role = "admin"
            user.password_hash = hash_password(password)
        else:
            db.add(User(email=email, full_name=name, password_hash=hash_password(password), role="admin"))
        db.commit()
    print(f"Admin ready: {email}")


if __name__ == "__main__":
    main()
