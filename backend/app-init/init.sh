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
EMBEDDING_URL="${EMBEDDING_MODEL_BASE_URL:-http://embedding:80/v1}"
EMBEDDING_API_KEY="${EMBEDDING_MODEL_API_KEY:-unused}"

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
# 2. SYNTHETIC RESOURCE DATA
# ============================================================================
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
POSTGRES_DB_RESOURCES="${POSTGRES_DB_RESOURCES:-resources}"
SEED_FILE="/seed/synthetic_seed.sql"

if [ -f "$SEED_FILE" ]; then
    echo "app-init: waiting for postgres at $POSTGRES_HOST:$POSTGRES_PORT..."
    attempt=1
    # The postgres container runs backend/app-init/postgres-init.sh (which creates
    # POSTGRES_DB_RESOURCES/USERS/FRONTEND) before it accepts connections here,
    # so by the time this succeeds the resource database already exists.
    until pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB_RESOURCES" >/dev/null 2>&1; do
        if [ "$attempt" -ge 60 ]; then
            echo "app-init: ERROR: postgres is not reachable after 120s" >&2
            exit 1
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    resource_table_exists=$(PGPASSWORD="$POSTGRES_PASSWORD" psql \
        --host "$POSTGRES_HOST" \
        --port "$POSTGRES_PORT" \
        --username "$POSTGRES_USER" \
        --dbname "$POSTGRES_DB_RESOURCES" \
        --tuples-only --no-align \
        --command "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'tblStudy')")
    resource_data_exists="no"
    if [ "$resource_table_exists" = "t" ]; then
        resource_data_exists=$(PGPASSWORD="$POSTGRES_PASSWORD" psql \
            --host "$POSTGRES_HOST" \
            --port "$POSTGRES_PORT" \
            --username "$POSTGRES_USER" \
            --dbname "$POSTGRES_DB_RESOURCES" \
            --tuples-only --no-align \
            --command 'SELECT EXISTS (SELECT 1 FROM "tblStudy")')
        [ "$resource_data_exists" = "t" ] && resource_data_exists="yes" || resource_data_exists="no"
    fi
    if [ "$resource_data_exists" = "yes" ]; then
        echo "app-init: resource data already exists; preserving it"
    else
        echo "app-init: resource data is empty; loading synthetic seed data"
        PGPASSWORD="$POSTGRES_PASSWORD" psql \
            --host "$POSTGRES_HOST" \
            --port "$POSTGRES_PORT" \
            --username "$POSTGRES_USER" \
            --dbname "$POSTGRES_DB_RESOURCES" \
            --set ON_ERROR_STOP=1 \
            --file "$SEED_FILE"
    fi
else
    echo "app-init: synthetic seed file not mounted; skipping demo data"
fi

# ============================================================================
# 3. LOGIC DATA VOLUME
# ============================================================================
DATABASE_VOLUME="${DATABASE_VOLUME:?is not set; must point to the data volume}"
APP_UID="${APP_UID:-999}"
APP_GID="${APP_GID:-999}"

echo "app-init: preparing data volume at $DATABASE_VOLUME..."
for dir in logs resources resources/pdfs resources/pdf_metadata resources/fulltexts; do
    mkdir -p "$DATABASE_VOLUME/$dir"
done
if [ ! -f "$DATABASE_VOLUME/resources/pdfs/00000.pdf" ]; then
    cp /app-init/data/placeholder.pdf "$DATABASE_VOLUME/resources/pdfs/00000.pdf"
fi
if [ -d /seed/pdfs ]; then
    seed_pdf_count=$(find /seed/pdfs -type f -name '*.pdf' | wc -l | tr -d ' ')
    echo "app-init: copying $seed_pdf_count seeded PDFs from /seed/pdfs to $DATABASE_VOLUME/resources/pdfs"
    find /seed/pdfs -type f -name '*.pdf' -exec sh -c '
        target="$1/resources/pdfs/$(basename "$2")"
        [ -f "$target" ] || cp "$2" "$target"
    ' sh "$DATABASE_VOLUME" {} \;
    runtime_pdf_count=$(find "$DATABASE_VOLUME/resources/pdfs" -type f -name '*.pdf' | wc -l | tr -d ' ')
    echo "app-init: runtime PDF count is $runtime_pdf_count"
fi
chown -R "$APP_UID:$APP_GID" "$DATABASE_VOLUME"
echo "app-init: data volume prepared for uid $APP_UID:$APP_GID"

# ============================================================================
# 4. SYNTHETIC VECTORSTORE DATA
# ============================================================================
MARKER="$DATABASE_VOLUME/resources/vectorstore.initialized"
if [ -f "$MARKER" ]; then
    echo "app-init: static vectors already initialized; skipping"
else
    echo "app-init: waiting for embedding service at $EMBEDDING_URL..."
    attempt=1
    until curl -sf "$EMBEDDING_URL/embeddings" \
        -H 'Content-Type: application/json' \
        -H "Authorization: Bearer $EMBEDDING_API_KEY" \
        --data '{"input":["initialization probe"],"model":null}' >/dev/null; do
        if [ "$attempt" -ge 90 ]; then
            echo "app-init: ERROR: embedding service is not reachable after 180s" >&2
            exit 1
        fi
        attempt=$((attempt + 1))
        sleep 2
    done

    REPORT_RECORDS="/tmp/report-records.jsonl"
    TAG_RECORDS="/tmp/tag-records.jsonl"
    trap 'rm -f "$REPORT_RECORDS" "$TAG_RECORDS"' EXIT

    psql_query=$(cat <<'SQL'
SELECT json_build_object(
    'id', format('00000000-0000-4000-a000-%s', lpad(r."CRGReportID"::text, 12, '0')),
    'text', btrim(coalesce(r."Title", '') || E'\n' || coalesce(r."Abstract", '')),
    'payload', json_build_object(
        'is_report', true,
        'belongs_to_study', coalesce((SELECT json_agg(sr."CRGStudyID") FROM "tblStudyReport" sr WHERE sr."CRGReportID" = r."CRGReportID"), '[]'::json),
        'report_id', r."CRGReportID",
        'date_entered', r."Dateentered",
        'authors', coalesce((SELECT json_agg(trim(author)) FROM unnest(string_to_array(coalesce(r."Authors", ''), '//')) author WHERE trim(author) <> ''), '[]'::json),
        'title', r."Title",
        'abstract', r."Abstract",
        'belongs_to_trial_id', EXISTS (SELECT 1 FROM "tblStudyReport" sr WHERE sr."CRGReportID" = r."CRGReportID")
    )
) FROM "tblReport" r ORDER BY r."CRGReportID";
SQL
)
    PGPASSWORD="$POSTGRES_PASSWORD" psql \
        --host "$POSTGRES_HOST" \
        --port "$POSTGRES_PORT" \
        --username "$POSTGRES_USER" \
        --dbname "$POSTGRES_DB_RESOURCES" \
        --tuples-only --no-align --command "$psql_query" > "$REPORT_RECORDS"

    tag_query=$(cat <<'SQL'
SELECT json_build_object(
    'id', format('00000000-%s-4000-a000-%s', tag, lpad(id::text, 12, '0')),
    'text', description,
    'payload', json_build_object(
        'tree_ids', json_build_array(source),
        'source', 'meerkat',
        'source_id', id::text,
        'display_name', description,
        'is_report', false
    )
) FROM (
    SELECT "InterventionID" AS id, "InterventionDescription" AS description, 'interventions' AS source, '0001' AS tag FROM "tblIntervention"
    UNION ALL
    SELECT "HealthCareConditionID", "HealthCareConditionDescription", 'conditions', '0002' FROM "tblHealthCareCondition"
    UNION ALL
    SELECT "OutcomeID", "OutcomeDescription", 'outcomes', '0003' FROM "tblOutcome"
) tags ORDER BY tag, id;
SQL
)
    PGPASSWORD="$POSTGRES_PASSWORD" psql \
        --host "$POSTGRES_HOST" \
        --port "$POSTGRES_PORT" \
        --username "$POSTGRES_USER" \
        --dbname "$POSTGRES_DB_RESOURCES" \
        --tuples-only --no-align --command "$tag_query" > "$TAG_RECORDS"

    upsert_records() {
        records_file="$1"
        while IFS= read -r record; do
            [ -n "$record" ] || continue
            point_id=$(printf '%s' "$record" | jq -r '.id')
            text=$(printf '%s' "$record" | jq -r '.text')
            payload=$(printf '%s' "$record" | jq -c '.payload')
            request=$(jq -cn --arg text "$text" '{input: [$text], model: null}')
            response=$(curl -sf "$EMBEDDING_URL/embeddings" \
                -H 'Content-Type: application/json' \
                -H "Authorization: Bearer $EMBEDDING_API_KEY" \
                --data "$request")
            vector=$(printf '%s' "$response" | jq -c '.data[0].embedding')
            [ "$vector" != "null" ] || {
                echo "app-init: ERROR: embedding response did not contain a vector for $point_id" >&2
                exit 1
            }
            point=$(jq -cn \
                --arg id "$point_id" \
                --argjson vector "$vector" \
                --argjson payload "$payload" \
                '{points: [{id: $id, vector: $vector, payload: $payload}]}')
            curl -sf -X PUT "$QDRANT_URL/collections/$COLLECTION/points?wait=true" \
                -H 'Content-Type: application/json' \
                --data "$point" >/dev/null
        done < "$records_file"
    }

    upsert_records "$REPORT_RECORDS"
    upsert_records "$TAG_RECORDS"
    printf 'reports=%s\ntags=%s\n' "$(wc -l < "$REPORT_RECORDS")" "$(wc -l < "$TAG_RECORDS")" > "$MARKER"
    chown "$APP_UID:$APP_GID" "$MARKER"
    echo "app-init: static vectors embedded and upserted"
fi

echo "app-init: initialization complete"
