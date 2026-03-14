import os

# ── Ed25519 public key (baked in at build time) ──────────────────────────────
# To rotate: use the admin dashboard (Key Generation), paste new PEM here.
# The private key NEVER goes into this file, this repo, or the build.
PUBLIC_KEY_PEM = b"""\
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAOKHXJyBFNnuMSX41K/1/27j61soby9g+A2MpzrRYf/U=
-----END PUBLIC KEY-----
"""

# License file location on USB drive (relative to root of drive)
LICENSE = b"""
{
  "payload": "eyJ2ZXJzaW9uIjoxLCJjdXN0b21lciI6IkFjbWUgQ29ycCIsImZpbmdlcnByaW50IjoiZTIwODY3MWQxNDZlMjU2NGRiYzcwYTE1YzAwNTc2YjFmODJiNzI1YzgzNGY0Y2YyMGRmOGU2YTA3MzUxZWZlMCIsImV4cGlyZXNfYXQiOm51bGwsImlzc3VlZF9hdCI6IjIwMjYtMDMtMTQifQ==",
  "signature": "3iO3Ji3qLzzDzeTtWBJ8eBG4culRhOwc9PMJ-ZC_ErQvCFspRmix20UiIobtGx4m6tGI1r_zzVU9scQQ4RzbBg=="
}
"""