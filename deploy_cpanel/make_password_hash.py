import getpass
import json
import sys

import auth


def main():
    username = input("Usuario: ").strip()
    password = getpass.getpass("Clave: ")
    role = input("Rol [user/admin] (user): ").strip() or "user"
    if role not in ("user", "admin"):
        role = "user"
    data = {
        "username": username,
        "password_hash": auth.hash_password(password),
        "role": role,
    }
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
