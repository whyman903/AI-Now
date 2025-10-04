#!/usr/bin/env python3
"""
Generate secure random keys for deployment.
Run this to generate AGGREGATION_SERVICE_TOKEN.
"""

import secrets

def generate_key(length=32):
    """Generate a secure random key."""
    return secrets.token_urlsafe(length)

if __name__ == "__main__":
    print("=" * 60)
    print("🔐 Secure Key Generator")
    print("=" * 60)
    print()
    print("Copy this value into your Render environment variables:")
    print()
    print("-" * 60)
    print("AGGREGATION_SERVICE_TOKEN:")
    print(generate_key(32))
    print()
    print("-" * 60)
    print()
    print("✅ Keep this secure! Don't commit it to Git.")
    print("=" * 60)

