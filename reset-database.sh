#!/bin/bash

echo "Resetting database schema for AI-Now..."

# Stop any running services
echo "Stopping services..."
pkill -f "python main.py" 2>/dev/null || true
pkill -f "tsx.*server/index.ts" 2>/dev/null || true
sleep 2

# Function to reset database
reset_database() {
    echo "Resetting database schema..."
    
    cd AI-Now
    
    # Create a temporary drizzle config that forces schema reset
    cat > drizzle.config.temp.ts << 'EOF'
import { defineConfig } from "drizzle-kit";

export default defineConfig({
  dialect: "postgresql",
  schema: "./shared/schema.ts",
  out: "./drizzle",
  dbCredentials: {
    url: process.env.DATABASE_URL!,
  },
  verbose: true,
  strict: true,
});
EOF

    # Force push schema (this will drop and recreate tables)
    echo "WARNING: This will DROP existing tables and recreate them!"
    echo "Pushing clean schema..."
    
    npx drizzle-kit push --config=drizzle.config.temp.ts --force
    
    # Clean up temp config
    rm drizzle.config.temp.ts
    
    cd ..
}

# Check if .env exists
if [ ! -f "AI-Now/.env" ]; then
    echo "ERROR: No .env file found in AI-Now/"
    echo "Please create AI-Now/.env with DATABASE_URL"
    exit 1
fi

# Reset the database
reset_database

echo "SUCCESS: Database schema reset complete!"
echo ""
echo "Now you can start the services:"
echo "   ./start-services.sh"
