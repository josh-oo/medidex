#!/bin/bash
# Test runner script for meerkat-tool tests

set -e

cd "$(dirname "$0")"

echo "========================================="
echo "Meerkat Tool Test Suite"
echo "========================================="
echo ""

# Check if dependencies are installed
if ! command -v pytest &> /dev/null; then
    echo "Installing test dependencies..."
    pip install -q -r requirements.txt
    pip install -q -r ../backend/logic/requirements.txt
fi

# Parse arguments
RUN_UNIT_TESTS=true
RUN_CONTAINER_TESTS=false
VERBOSE=""
COVERAGE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --container)
            RUN_CONTAINER_TESTS=true
            shift
            ;;
        --container-only)
            RUN_UNIT_TESTS=false
            RUN_CONTAINER_TESTS=true
            shift
            ;;
        --all)
            RUN_UNIT_TESTS=true
            RUN_CONTAINER_TESTS=true
            shift
            ;;
        -v|--verbose)
            VERBOSE="-v"
            shift
            ;;
        --coverage)
            COVERAGE="--cov=../backend/logic/src --cov-report=term-missing --cov-report=html"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--container] [--container-only] [--all] [-v|--verbose] [--coverage]"
            exit 1
            ;;
    esac
done

if [ "$RUN_UNIT_TESTS" = true ]; then
    echo "Running unit/integration tests..."
    echo ""
    pytest test_auth.py test_logic.py test_resources.py $VERBOSE $COVERAGE
fi

if [ "$RUN_CONTAINER_TESTS" = true ]; then
    echo ""
    echo "Running Docker container tests..."
    echo "Note: Requires running Docker containers (docker compose up -d)"
    echo ""
    
    # Check if container is accessible using httpx (Python) instead of curl for portability
    CONTAINER_URL="${CONTAINER_URL:-http://localhost:8002}"
    if python3 -c "import httpx; r = httpx.get('${CONTAINER_URL}/readyz', timeout=5); exit(0 if r.status_code == 200 else 1)" 2>/dev/null; then
        pytest test_docker_container.py $VERBOSE
    else
        echo "Warning: Container at ${CONTAINER_URL} is not accessible."
        echo "Please start the containers with: docker compose up -d"
        echo "Skipping container tests."
    fi
fi

echo ""
echo "========================================="
echo "Test Summary:"
echo "========================================="
if [ -n "$COVERAGE" ]; then
    echo "- HTML coverage report: htmlcov/index.html"
fi
echo "- To run specific tests: pytest test_auth.py -v"
echo "- To run container tests: ./run_tests.sh --container"
echo "- To run all tests: ./run_tests.sh --all"
echo "========================================="
