"""Create (or reset the password of) an instructor account — the way to get the first login on a
fresh production database, since the app itself only lets instructors create students.

Run from the institute-app/ directory (on Render: the service's Shell tab, from /app):
    python3 scripts/create_instructor.py --name "Anita Sharma" --email anita@example.com
The password is asked for interactively so it doesn't end up in shell history.
"""
import argparse
import getpass
import os
import sys

BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND_DIR)

from app.database import Base, engine, SessionLocal, ensure_columns  # noqa: E402
from app import models  # noqa: E402
from app.auth import find_user_by_email, hash_password, normalize_email  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    password = getpass.getpass("Password (min 10 chars): ")
    if len(password) < 10:
        sys.exit("Password must be at least 10 characters")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords don't match")

    Base.metadata.create_all(bind=engine)
    ensure_columns()
    db = SessionLocal()
    try:
        user = find_user_by_email(db, args.email)
        if user and user.role != "instructor":
            sys.exit(f"{args.email} already exists as a {user.role}")
        if user:
            user.name = args.name
            user.password_hash = hash_password(password)
            action = "Updated"
        else:
            db.add(models.User(name=args.name, email=normalize_email(args.email), password_hash=hash_password(password), role="instructor"))
            action = "Created"
        db.commit()
        print(f"{action} instructor {args.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
