from __future__ import annotations

import secrets

# Friendly enough to type on an iPad, while still much stronger than a 4-digit PIN.
alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
raw = "".join(secrets.choice(alphabet) for _ in range(12))
access_code = "-".join(raw[index:index + 4] for index in range(0, 12, 4))

print("Copy these into the hosting service Variables page. Do NOT commit them to Git.")
print()
print(f"CLOUD_ACCESS_CODE={access_code}")
print(f"APP_SECRET_KEY={secrets.token_urlsafe(48)}")
