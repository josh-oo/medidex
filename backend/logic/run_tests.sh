#!/bin/bash
# Test runner script for meerkat-tool backend tests

set -e

cd "$(dirname "$0")"

echo "========================================="
echo "Meerkat Tool Backend Test Suite"
echo "========================================="
echo ""

# Check if dependencies are installed
if ! command -v pytest &> /dev/null; then
    echo "Installing test dependencies..."
    pip install -q -r requirements.txt -r requirements-test.txt
fi

echo "Running tests..."
echo ""

# Run tests with coverage
pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html

echo ""
echo "========================================="
echo "Test Summary:"
echo "========================================="
echo "- HTML coverage report: htmlcov/index.html"
echo "- To run specific tests: pytest tests/test_auth.py -v"
echo "- To run with detailed output: pytest tests/ -vv"
echo "========================================="
