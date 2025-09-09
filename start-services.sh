#!/bin/bash
set -e

echo "Launcher"
echo "================================================"

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null ; then
        echo "WARNING: Port $port is already in use"
        return 1
    fi
    return 0
}

# Global variables for process IDs
PYTHON_PID=""
FRONTEND_PID=""

# Function to start Python backend
start_python_backend() {
    echo "Starting Python FastAPI backend (port 8000)..."
    
    # Force kill any process on port 8000 before starting
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    
    if check_port 8000; then
        cd walker_app_api
        if [ ! -f "pyproject.toml" ]; then
            echo "ERROR: pyproject.toml not found in walker_app_api/"
            exit 1
        fi
        
        # Create virtual environment if it doesn't exist using uv
        if [ ! -d ".venv" ]; then
            echo "Creating Python virtual environment with uv..."
            uv venv
        fi
        
        echo "Installing Python dependencies with uv..."
        uv sync
        
        echo "Running Python backend with uv..."
        uv run python main.py &
        PYTHON_PID=$!
        echo "SUCCESS: Python backend started (PID: $PYTHON_PID)"
        cd ..
    else
        echo "ERROR: Cannot start Python backend - port 8000 in use"
        exit 1
    fi
}

# Function to start React frontend  
start_react_frontend() {
    echo "Starting React frontend (port 5173)..."
    
    # Force kill any process on port 5173 before starting
    lsof -ti:5173 | xargs kill -9 2>/dev/null || true
    
    if check_port 5173; then
        cd AI-Now
        if [ ! -f "package.json" ]; then
            echo "ERROR: package.json not found in AI-Now/"
            exit 1
        fi
        
        echo "Installing Node.js dependencies..."
        npm install
        
        echo "Running React frontend..."
        npm run dev &
        FRONTEND_PID=$!
        echo "SUCCESS: React frontend started (PID: $FRONTEND_PID)"
        cd ..
    else
        echo "ERROR: Cannot start React frontend - port 5173 in use"
        exit 1
    fi
}

# Function to wait for services to be ready
wait_for_services() {
    echo "Waiting for services to start..."
    sleep 5
    
    echo "Checking Python backend..."
    if curl -s http://localhost:8000/health > /dev/null; then
        echo "SUCCESS: Python backend is ready"
    else
        echo "WARNING: Python backend may not be ready yet"
    fi
    
    echo "Checking React frontend..."
    if curl -s http://localhost:5173 > /dev/null; then
        echo "SUCCESS: React frontend is ready"
    else
        echo "WARNING: React frontend may not be ready yet"
    fi
}

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down services..."
    
    # Kill Python backend
    if [ ! -z "$PYTHON_PID" ]; then
        echo "Stopping Python backend (PID: $PYTHON_PID)..."
        kill $PYTHON_PID 2>/dev/null || true
        sleep 2
        # Force kill if still running
        kill -9 $PYTHON_PID 2>/dev/null || true
        echo "Python backend stopped"
    fi
    
    # Kill React frontend
    if [ ! -z "$FRONTEND_PID" ]; then
        echo "Stopping React frontend (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID 2>/dev/null || true
        sleep 2
        # Force kill if still running
        kill -9 $FRONTEND_PID 2>/dev/null || true
        echo "React frontend stopped"
    fi
    
    # Also kill any remaining processes on ports 8000 and 5173
    echo "Cleaning up any remaining processes..."
    pkill -f "python main.py" 2>/dev/null || true
    pkill -f "npm run dev" 2>/dev/null || true
    
    # Kill processes by port
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    lsof -ti:5173 | xargs kill -9 2>/dev/null || true
    
    echo "All services stopped"
    exit 0
}

# Set up signal handlers
trap cleanup INT TERM

# Main execution
main() {
    echo "Checking prerequisites..."
    
    # Check if directories exist
    if [ ! -d "walker_app_api" ]; then
        echo "ERROR: walker_app_api directory not found"
        exit 1
    fi
    
    if [ ! -d "AI-Now" ]; then
        echo "ERROR: AI-Now directory not found"
        exit 1
    fi
    
    # Check if Python is available
    if ! command -v python &> /dev/null; then
        echo "ERROR: Python not found. Please install Python 3.9+"
        exit 1
    fi
    
    # Check if uv is available
    if ! command -v uv &> /dev/null; then
        echo "ERROR: uv not found. Please install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
    
    # Check if Node.js is available
    if ! command -v node &> /dev/null; then
        echo "ERROR: Node.js not found. Please install Node.js 18+"
        exit 1
    fi
    
    # Check if npm is available
    if ! command -v npm &> /dev/null; then
        echo "ERROR: npm not found. Please install npm"
        exit 1
    fi
    
    echo "SUCCESS: Prerequisites check passed"
    echo ""
    
    # Start services
    start_python_backend
    start_react_frontend
    
    # Wait for services to be ready
    wait_for_services
    
    echo ""
    echo "TrendCurate is now running!"
    echo ""
    echo "Service URLs:"
    echo "   Frontend:       http://localhost:5173"
    echo "   Python API:     http://localhost:8000"
    echo "   API Docs:       http://localhost:8000/docs"
    echo ""
    echo "Useful commands:"
    echo "   Content API:    curl http://localhost:8000/api/v1/content"
    echo "   Health Check:   curl http://localhost:8000/health"
    echo "   API Status:     curl http://localhost:8000/api/v1/aggregation/status"
    echo ""
    echo "Press Ctrl+C to stop all services"
    
    # Keep script running
    wait
}

# Run main function
main