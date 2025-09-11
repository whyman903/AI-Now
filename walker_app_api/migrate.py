#!/usr/bin/env python3
"""Database migration script using Alembic."""

import argparse
import subprocess
import sys
from pathlib import Path


def run_alembic(args: list[str]) -> bool:
    """Run an alembic command and return success status."""
    try:
        result = subprocess.run(
            ["alembic"] + args,
            check=True,
            text=True,
            cwd=Path(__file__).parent
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: Command failed with exit code {e.returncode}")
        return False
    except FileNotFoundError:
        print("Error: Alembic not found. Make sure it's installed.")
        return False


def confirm_reset() -> bool:
    """Confirm database reset operation."""
    try:
        response = input("WARNING: This will drop all tables! Type 'yes' to confirm: ")
        return response.lower() == 'yes'
    except (EOFError, KeyboardInterrupt):
        return False


def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(description="Database migration management")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    subparsers.add_parser('upgrade', help='Apply all pending migrations')
    subparsers.add_parser('downgrade', help='Rollback one migration')
    subparsers.add_parser('current', help='Show current migration')
    subparsers.add_parser('history', help='Show migration history')
    
    create_parser = subparsers.add_parser('create', help='Create new migration')
    create_parser.add_argument('message', help='Migration description')
    
    reset_parser = subparsers.add_parser('reset', help='Reset database (DANGEROUS)')
    reset_parser.add_argument('--force', action='store_true', help='Skip confirmation')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == 'upgrade':
        success = run_alembic(['upgrade', 'head'])
    
    elif args.command == 'downgrade':
        success = run_alembic(['downgrade', '-1'])
    
    elif args.command == 'current':
        success = run_alembic(['current'])
    
    elif args.command == 'history':
        success = run_alembic(['history'])
    
    elif args.command == 'create':
        success = run_alembic(['revision', '--autogenerate', '-m', args.message])
    
    elif args.command == 'reset':
        if not args.force and not confirm_reset():
            print("Reset cancelled")
            return
        
        print("Resetting database...")
        success = (run_alembic(['downgrade', 'base']) and 
                  run_alembic(['upgrade', 'head']))
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()