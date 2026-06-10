"""Encrypted wallet custody boundary.

Raw private keys must never be stored in environment files, source code, logs, or
plaintext repository files. Later steps must decrypt encrypted key material only
in memory and must keep passphrases outside the repository.
"""
