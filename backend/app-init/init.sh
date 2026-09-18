#!/bin/sh
# Combined init: prepares both the qdrant collection and the logic data volume.
# Runs as the one-shot `app-init` service on `docker compose up`, before `logic` starts.
set -eu

echo "app-init: starting initialization..."

# ============================================================================
# 1. QDRANT COLLECTION
# ============================================================================
QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
COLLECTION="${VECTORSTORE_COLLECTION_NAME:-report_embeddings_medidex}"
DIM="${EMBEDDING_MODEL_DIM:-1024}"

echo "app-init: waiting for qdrant at $QDRANT_URL..."
attempt=1
until curl -sf -o /dev/null "$QDRANT_URL/collections"; do
    if [ "$attempt" -ge 30 ]; then
        echo "app-init: ERROR: $QDRANT_URL is not reachable after 60s" >&2
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 2
done
echo "app-init: qdrant is ready"

if [ "$(curl -s -o /dev/null -w '%{http_code}' "$QDRANT_URL/collections/$COLLECTION")" = "200" ]; then
    echo "app-init: qdrant collection '$COLLECTION' already exists"
else
    echo "app-init: creating qdrant collection '$COLLECTION' ($DIM dimensions, cosine distance)"
    curl -sf -o /dev/null -X PUT "$QDRANT_URL/collections/$COLLECTION" \
        -H 'Content-Type: application/json' \
        -d "{\"vectors\":{\"size\":$DIM,\"distance\":\"Cosine\"},\"on_disk_payload\":true}"

    # Index payload fields used by logic filters
    for field in is_report source tree_ids source_id belongs_to_trial_id belongs_to_study date_entered; do
        schema="keyword"
        [ "$field" = "is_report" ] && schema="bool"
        [ "$field" = "belongs_to_trial_id" ] && schema="bool"
        [ "$field" = "source_id" ] && schema="uuid"
        [ "$field" = "date_entered" ] && schema="datetime"
        
        curl -sf -o /dev/null -X PUT "$QDRANT_URL/collections/$COLLECTION/index?wait=true" \
            -H 'Content-Type: application/json' \
            -d "{\"field_name\":\"$field\",\"field_schema\":\"$schema\"}"
    done
    echo "app-init: qdrant collection '$COLLECTION' is ready"
fi

# ============================================================================
# 2. LOGIC DATA VOLUME
# ============================================================================
DATABASE_VOLUME="${DATABASE_VOLUME:?is not set; must point to the data volume}"
APP_UID="${APP_UID:-999}"
APP_GID="${APP_GID:-999}"

echo "app-init: preparing data volume at $DATABASE_VOLUME..."
for dir in logs resources resources/pdfs resources/pdf_metadata resources/fulltexts; do
    mkdir -p "$DATABASE_VOLUME/$dir"
done
chown -R "$APP_UID:$APP_GID" "$DATABASE_VOLUME"
echo "app-init: data volume prepared for uid $APP_UID:$APP_GID"

echo "app-init: initialization complete"
