#!/usr/bin/env python3
"""Mint anon/service_role JWTs for PostgREST, replacing the Supabase key pair.

These are the direct equivalent of Supabase's "anon" (publishable) and
"service_role" (secret) API keys: static JWTs signed with the project's JWT
secret, carrying only a `role` claim that PostgREST maps to a Postgres role.

Usage:
    pip install pyjwt
    PGRST_JWT_SECRET=... python3 gen_jwt.py
"""
import datetime
import os
import sys

import jwt

secret = os.environ.get("PGRST_JWT_SECRET")
if not secret or len(secret) < 32:
    sys.exit("Set PGRST_JWT_SECRET to the same 32+ char value used in .env")

iat = datetime.datetime.now(datetime.timezone.utc)
exp = iat + datetime.timedelta(days=3650)  # 10 years, matches Supabase's own long-lived keys

for role in ("anon", "service_role"):
    payload = {"role": role, "iss": "warescalation-selfhost", "iat": int(iat.timestamp()), "exp": int(exp.timestamp())}
    token = jwt.encode(payload, secret, algorithm="HS256")
    print(f"{role.upper()}_KEY={token}")
