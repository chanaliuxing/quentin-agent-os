#!/bin/bash
set -e

echo "🚀 AutoLoop Quick Start Script"
echo "================================"

if [ ! -f "pyproject.toml" ]; then
    echo "❌ Error: Please run this script from the autoloop/ directory"
    exit 1
fi

echo ""
echo "📦 Step 1: Installing dependencies..."
if command -v poetry &> /dev/null; then
    poetry install
else
    echo "⚠️  Poetry not found. Installing with pip..."
    pip install -e .
fi

echo ""
echo "📝 Step 2: Creating .env file..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✅ Created .env file (please configure before running)"
else
    echo "ℹ️  .env already exists, skipping"
fi

echo ""
echo "🔧 Step 3: Initializing project structure..."
if command -v poetry &> /dev/null; then
    poetry run python -m app.main init
else
    python -m app.main init
fi

echo ""
echo "✅ Step 4: Creating example PRD..."
if [ ! -f "prd.md" ]; then
    cp prd_example.md prd.md
    echo "✅ Created prd.md (example calculator API project)"
else
    echo "ℹ️  prd.md already exists, skipping"
fi

echo ""
echo "🧪 Step 5: Running tests..."
if command -v poetry &> /dev/null; then
    poetry run pytest tests/ -v
else
    pytest tests/ -v
fi

echo ""
echo "================================"
echo "✅ AutoLoop is ready!"
echo ""
echo "📚 Next steps:"
echo ""
echo "1. Configure .env file:"
echo "   vi .env"
echo ""
echo "2. Review/edit the sample PRD:"
echo "   cat prd.md"
echo ""
echo "3. Run a workflow (LangGraph mode):"
if command -v poetry &> /dev/null; then
    echo "   poetry run python -m app.main run prd.md --mode graph"
else
    echo "   python -m app.main run prd.md --mode graph"
fi
echo ""
echo "4. Run a workflow (Temporal mock mode):"
if command -v poetry &> /dev/null; then
    echo "   poetry run python -m app.main run prd.md --mode temporal"
else
    echo "   python -m app.main run prd.md --mode temporal"
fi
echo ""
echo "5. Check results:"
echo "   cat phases/phase_01/phase_report.md"
echo "   tail -f runtime/logs/*.log"
echo ""
echo "📖 Read the docs:"
echo "   cat README.md"
echo "   cat CLAUDE.md"
echo ""
echo "================================"
