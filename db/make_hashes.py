import os
import sys
import bcrypt

password = os.environ.get("SEED_PASSWORD")
if not password:
    sys.exit("SEED_PASSWORD environment variable is not set")

for item in (password.split(",") if "," in password else [password]):
    print(bcrypt.hashpw(item.strip().encode("utf-8"), bcrypt.gensalt()).decode("utf-8"))
