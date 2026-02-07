#!/usr/bin/env bash
# Dataset testing: ingest data/ documents, run extraction, validate table output.
# Prerequisites: Backend running (npm run start:dev), DB with default template created.

set -e
API="${API:-http://localhost:4000}"
# From backend/ directory, data is at ../data
DATA_DIR="${DATA_DIR:-../data}"

echo "=== Legal Tabular Review — Dataset Test ==="
echo "API: $API"
echo ""

# 1) Ensure default template
echo "1. Ensuring default template..."
TEMPLATE_ID=$(curl -s -X POST "$API/templates/ensure-default" | jq -r '.id')
if [ -z "$TEMPLATE_ID" ] || [ "$TEMPLATE_ID" = "null" ]; then
  echo "   Failed to get template. Create one via POST /templates/ensure-default"
  exit 1
fi
echo "   Template ID: $TEMPLATE_ID"

# 2) Create project
echo "2. Creating project..."
PROJECT=$(curl -s -X POST "$API/projects" -H "Content-Type: application/json" -d '{"name":"Dataset Test Project"}')
PROJECT_ID=$(echo "$PROJECT" | jq -r '.id')
echo "   Project ID: $PROJECT_ID"

# 3) Link template
curl -s -X PUT "$API/projects/$PROJECT_ID/template" -H "Content-Type: application/json" -d "{\"templateId\":\"$TEMPLATE_ID\"}" > /dev/null

# 4) Add documents from data/
echo "3. Adding documents from $DATA_DIR..."
# Paths relative to backend cwd (e.g. ../data/EX-10.2.html when run from backend/)
PATHS=$(find "$DATA_DIR" -type f \( -name "*.html" -o -name "*.htm" -o -name "*.pdf" -o -name "*.txt" \) 2>/dev/null | jq -R -s -c 'split("\n") | map(select(length>0))')
curl -s -X POST "$API/projects/$PROJECT_ID/documents" -H "Content-Type: application/json" -d "{\"paths\":$PATHS}" | jq -r 'if type == "array" then "   Added \(length) document(s)" else . end'

# 5) Run extraction
echo "4. Running extraction..."
EXTRACT=$(curl -s -X POST "$API/projects/$PROJECT_ID/extract")
echo "   $EXTRACT" | jq -r '.results[] | "   \(.documentName): \(.status)"'

# 6) Get table and validate
echo "5. Fetching table and validating..."
TABLE=$(curl -s "$API/projects/$PROJECT_ID/table")
ROWS=$(echo "$TABLE" | jq '.rows | length')
DOCS=$(echo "$TABLE" | jq '.documents | length')
echo "   Rows (fields): $ROWS, Columns (documents): $DOCS"

FIELDS_OK=$(echo "$TABLE" | jq '[.rows[].cells[] | select(.value != null and .value != "") or select(.citation != null) or (.confidence != null and .confidence >= 0)] | length')
CELLS=$(echo "$TABLE" | jq '[.rows[].cells[]] | length')
echo "   Cells with value/citation/confidence: $FIELDS_OK / $CELLS"

echo ""
echo "=== Test complete. Open table in UI: $API or frontend /project/$PROJECT_ID ==="
echo "To test template update: change a field in the template, call POST /projects/$PROJECT_ID/extract again, then GET table."
