import argparse
from pathlib import Path

from sqlalchemy import select

from .auth import create_key
from .db import Session
from .models import ApiKey, Project, User
from .service import index_project


def main():
    parser = argparse.ArgumentParser(description="Conceptualize local development and indexing")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed", help="Create a project and print its API key once")
    seed.add_argument("--name", default="My project")
    seed.add_argument("--email", default="developer@localhost")
    index = sub.add_parser("index", help="Incrementally index a local repository")
    index.add_argument("path", type=Path)
    index.add_argument("--project", required=True)
    index.add_argument("--base", help="Optional Git base ref for branch comparison")
    revoke = sub.add_parser("revoke-key")
    revoke.add_argument("--prefix", required=True)
    args = parser.parse_args()
    with Session() as db:
        if args.command == "seed":
            user = db.scalar(select(User).where(User.email == args.email)) or User(email=args.email)
            db.add(user)
            db.flush()
            project = Project(user_id=user.id, name=args.name)
            db.add(project)
            db.flush()
            raw = create_key(db, project.id)
            db.commit()
            print(f"Project: {project.id}\nAPI key (shown once): {raw}")
        elif args.command == "index":
            project = db.get(Project, args.project)
            if not project:
                parser.error("Project not found")
            try:
                print(index_project(db, project, args.path, args.base))
            except (OSError, ValueError) as exc:
                db.rollback()
                parser.error(str(exc))
        else:
            keys = list(db.scalars(select(ApiKey).where(ApiKey.prefix == args.prefix)))
            if len(keys) != 1:
                parser.error("Prefix must uniquely identify one API key")
            keys[0].revoked = True
            db.commit()
            print("API key revoked")


if __name__ == "__main__":
    main()
