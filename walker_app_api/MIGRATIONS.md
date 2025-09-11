# Database Migrations

This project uses Alembic for database schema management with a professional-grade migration management script.

## Quick Start

```bash
# Apply all pending migrations
python migrate.py upgrade

# Create a new migration after model changes
python migrate.py create "Add new field to user table"

# Check current migration status
python migrate.py current

# View migration history
python migrate.py history
```

## Migration Commands

### Basic Operations

```bash
# Apply migrations
python migrate.py upgrade              # Apply all pending migrations
python migrate.py upgrade +2           # Apply next 2 migrations
python migrate.py upgrade 1234abc      # Apply up to specific revision

# Rollback migrations
python migrate.py downgrade            # Rollback 1 migration
python migrate.py downgrade -2         # Rollback 2 migrations
python migrate.py downgrade 5678def    # Rollback to specific revision

# Status and information
python migrate.py current              # Show current migration version
python migrate.py history              # Show migration history
python migrate.py history --verbose    # Show detailed history
```

### Development Operations

```bash
# Create new migrations
python migrate.py create "Add user preferences table"
python migrate.py create "Update indexes" --no-autogenerate

# Database reset (DANGEROUS)
python migrate.py reset                # Interactive confirmation
python migrate.py reset --force        # Skip confirmation (CI/scripts only)
```

### Verbose Logging

Add `--verbose` or `-v` to any command for detailed logging:

```bash
python migrate.py upgrade --verbose
python migrate.py create "New feature" -v
```

## Migration Workflow

1. **Make model changes** in `app/db/models.py`
2. **Create migration**: 
   ```bash
   python migrate.py create "Descriptive message about changes"
   ```
3. **Review generated migration** in `alembic/versions/`
4. **Test migration** on development database:
   ```bash
   python migrate.py upgrade
   ```
5. **Deploy to production** using the same command

## Production Deployment

### Recommended Production Workflow

```bash
# 1. Backup database (outside this script)
pg_dump mydb > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Apply migrations
python migrate.py upgrade --verbose

# 3. Verify deployment
python migrate.py current
```

### CI/CD Integration

```yaml
# Example GitHub Actions step
- name: Apply Database Migrations
  run: |
    python migrate.py upgrade --verbose
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

## Error Handling and Recovery

### Common Issues

**"Target database is not up to date"**
```bash
python migrate.py current    # Check current version
python migrate.py history    # See available migrations
python migrate.py upgrade    # Apply pending migrations
```

**"Can't locate revision identified by 'xyz'"**
```bash
python migrate.py history    # Check migration files
# May need to manually fix alembic_version table
```

**Migration fails partway through**
```bash
# Check current state
python migrate.py current

# Manual intervention may be required
# Fix the issue, then resume
python migrate.py upgrade
```

### Recovery Options

```bash
# Rollback problematic migration
python migrate.py downgrade -1

# Reset to specific known-good revision
python migrate.py downgrade abc123

# Nuclear option (development only)
python migrate.py reset
```

## Configuration

- **Alembic configuration**: `alembic.ini`
- **Environment setup**: `alembic/env.py`
- **Database URL**: Automatically loaded from `app/core/config.py`
- **Logging**: Structured logging with timestamps

## Security Considerations

- **Never run `reset` in production**
- **Always backup before migrations**
- **Test migrations on staging first**
- **Use `--force` flag only in automated environments**
- **Review auto-generated migrations before applying**

## Monitoring and Maintenance

```bash
# Check migration status in monitoring
python migrate.py current --verbose

# Validate migration history integrity
python migrate.py history --verbose
```

## Troubleshooting

### Debug Mode
Use `--verbose` flag for detailed logging and debugging information.

### Manual Alembic Commands
The script wraps Alembic commands. You can still use Alembic directly if needed:
```bash
alembic current
alembic upgrade head
alembic revision --autogenerate -m "message"
```

### Timeout Issues
Long-running migrations have a 5-minute timeout. For very large datasets, consider:
- Breaking migrations into smaller chunks
- Running migrations during maintenance windows
- Using manual SQL for large data transformations