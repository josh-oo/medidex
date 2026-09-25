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
    # The postgres container runs ops/app-init/postgres-init.sh (which creates
    # POSTGRES_DB_RESOURCES/LANGGRAPH/KEYCLOAK) before it accepts connections here,
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
        --command "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'study')")
    resource_data_exists="no"
    if [ "$resource_table_exists" = "t" ]; then
        resource_data_exists=$(PGPASSWORD="$POSTGRES_PASSWORD" psql \
            --host "$POSTGRES_HOST" \
            --port "$POSTGRES_PORT" \
            --username "$POSTGRES_USER" \
            --dbname "$POSTGRES_DB_RESOURCES" \
            --tuples-only --no-align \
            --command 'SELECT EXISTS (SELECT 1 FROM "study")')
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
# 2b. CONVENTIONAL-NAMING VIEWS (optional schema adapter)
# ============================================================================
# Only needed when the resources database uses a physical schema that
# doesn't already match the application's (e.g. an imported Cochrane-style
# CRG/CENTRAL database) -- the bundled synthetic_seed.sql demo data creates
# its tables directly under the schema the application expects, so this is
# off by default. Toggle it via deploy/data/seed/schema-adapter.conf.
# See deploy/data/seed/views.sql for what the adapter does and why.
SCHEMA_ADAPTER_CONFIG="/seed/schema-adapter.conf"
APPLY_SCHEMA_VIEWS=false
if [ -f "$SCHEMA_ADAPTER_CONFIG" ]; then
    # shellcheck disable=SC1090
    . "$SCHEMA_ADAPTER_CONFIG"
fi

VIEWS_FILE="/seed/views.sql"
if [ "$APPLY_SCHEMA_VIEWS" = "true" ]; then
    if [ -f "$VIEWS_FILE" ]; then
        echo "app-init: APPLY_SCHEMA_VIEWS=true; applying conventional-naming views"
        PGPASSWORD="$POSTGRES_PASSWORD" psql \
            --host "$POSTGRES_HOST" \
            --port "$POSTGRES_PORT" \
            --username "$POSTGRES_USER" \
            --dbname "$POSTGRES_DB_RESOURCES" \
            --set ON_ERROR_STOP=1 \
            --file "$VIEWS_FILE"
    else
        echo "app-init: APPLY_SCHEMA_VIEWS=true but views.sql not mounted; skipping view setup" >&2
        exit 1
    fi
else
    echo "app-init: APPLY_SCHEMA_VIEWS is not 'true'; skipping conventional-naming views"
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
# 4. VECTORSTORE SYNC (reports, interventions, conditions, outcomes)
# ============================================================================
# Reconciles the qdrant collection with the current contents of report,
# intervention, condition and outcome on every run, instead of relying on a
# one-time "already initialized" marker: rows that aren't
# embedded yet are added, and points whose row no longer exists in postgres
# (e.g. deleted directly in the database) are removed. Point ids follow the
# same deterministic scheme as transform_to_uuid() in
# app/backend/src/services/vectorstore.py, so this only ever touches
# points produced by that scheme (report/tag ids, not e.g. mesh tags) and
# leaves everything else in the collection untouched.
echo "app-init: waiting for postgres at $POSTGRES_HOST:$POSTGRES_PORT..."
attempt=1
until pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB_RESOURCES" >/dev/null 2>&1; do
    if [ "$attempt" -ge 60 ]; then
        echo "app-init: ERROR: postgres is not reachable after 120s" >&2
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 2
done

REPORT_RECORDS="/tmp/report-records.jsonl"
TAG_RECORDS="/tmp/tag-records.jsonl"
ID_RECORD_TSV="/tmp/vectorstore-id-record.tsv"
DESIRED_IDS="/tmp/vectorstore-desired-ids.txt"
EXISTING_IDS="/tmp/vectorstore-existing-ids.txt"
EXISTING_MANAGED_IDS="/tmp/vectorstore-existing-managed-ids.txt"
MISSING_IDS="/tmp/vectorstore-missing-ids.txt"
STALE_IDS="/tmp/vectorstore-stale-ids.txt"
MISSING_RECORDS="/tmp/vectorstore-missing-records.jsonl"
trap 'rm -f "$REPORT_RECORDS" "$TAG_RECORDS" "$ID_RECORD_TSV" "$DESIRED_IDS" \
    "$EXISTING_IDS" "$EXISTING_MANAGED_IDS" "$MISSING_IDS" "$STALE_IDS" "$MISSING_RECORDS"' EXIT

psql_query=$(cat <<'SQL'
SELECT json_build_object(
    'id', format('00000000-0000-4000-a000-%s', lpad(r."id"::text, 12, '0')),
    'text', btrim(coalesce(r."title", '') || E'\n' || coalesce(r."abstract", '')),
    'payload', json_build_object(
        'is_report', true,
        'belongs_to_study', coalesce((SELECT json_agg(sr."study_id") FROM "study_report" sr WHERE sr."report_id" = r."id"), '[]'::json),
        'report_id', r."id",
        'date_entered', r."date_entered",
        'authors', coalesce((SELECT json_agg(trim(author)) FROM unnest(string_to_array(coalesce(r."authors", ''), '//')) author WHERE trim(author) <> ''), '[]'::json),
        'title', r."title",
        'abstract', r."abstract",
        'belongs_to_trial_id', EXISTS (SELECT 1 FROM "study_report" sr WHERE sr."report_id" = r."id")
    )
) FROM "report" r ORDER BY r."id";
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
        'source', 'internal',
        'source_id', id::text,
        'display_name', description,
        'is_report', false
    )
) FROM (
    SELECT "id", "description", 'interventions' AS source, '0001' AS tag FROM "intervention"
    UNION ALL
    SELECT "id", "description", 'conditions', '0002' FROM "condition"
    UNION ALL
    SELECT "id", "description", 'outcomes', '0003' FROM "outcome"
) tags ORDER BY tag, id;
SQL
)
PGPASSWORD="$POSTGRES_PASSWORD" psql \
    --host "$POSTGRES_HOST" \
    --port "$POSTGRES_PORT" \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB_RESOURCES" \
    --tuples-only --no-align --command "$tag_query" > "$TAG_RECORDS"

# Desired = every report/tag row that currently exists in postgres.
jq -r '.id' "$REPORT_RECORDS" "$TAG_RECORDS" | sort -u > "$DESIRED_IDS"

# Existing = every point currently in qdrant, paginated via scroll.
echo "app-init: reading existing vectorstore point ids..."
: > "$EXISTING_IDS"
offset="null"
while :; do
    if [ "$offset" = "null" ]; then
        body='{"limit":1000,"with_payload":false,"with_vector":false}'
    else
        body=$(jq -cn --argjson offset "$offset" '{limit:1000,with_payload:false,with_vector:false,offset:$offset}')
    fi
    response=$(curl -sf -X POST "$QDRANT_URL/collections/$COLLECTION/points/scroll" \
        -H 'Content-Type: application/json' --data "$body")
    printf '%s' "$response" | jq -r '.result.points[].id' >> "$EXISTING_IDS"
    offset=$(printf '%s' "$response" | jq -c '.result.next_page_offset')
    [ "$offset" = "null" ] && break
done
# Restrict to ids in the report (tag 0000) / tag (0001-0003) id space this
# script owns, e.g. never touch mesh tags (tag 1000) or anything else.
grep -E '^00000000-000[0-3]-4000-a000-' "$EXISTING_IDS" | sort -u > "$EXISTING_MANAGED_IDS"

comm -23 "$DESIRED_IDS" "$EXISTING_MANAGED_IDS" > "$MISSING_IDS"
comm -13 "$DESIRED_IDS" "$EXISTING_MANAGED_IDS" > "$STALE_IDS"
missing_count=$(wc -l < "$MISSING_IDS" | tr -d ' ')
stale_count=$(wc -l < "$STALE_IDS" | tr -d ' ')
echo "app-init: vectorstore sync: $missing_count missing, $stale_count stale (of $(wc -l < "$DESIRED_IDS" | tr -d ' ') expected points)"

if [ "$missing_count" -gt 0 ]; then
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

    # Use an ASCII unit separator (not a literal in the JSON) to join id/record
    # so the join survives arbitrary title/abstract text without re-escaping it.
    us=$(printf '\037')
    jq -r --arg us "$us" '[.id, tostring] | join($us)' "$REPORT_RECORDS" "$TAG_RECORDS" > "$ID_RECORD_TSV"
    awk -v FS="$us" 'NR==FNR{miss[$0]=1;next} ($1 in miss){print $2}' "$MISSING_IDS" "$ID_RECORD_TSV" > "$MISSING_RECORDS"

    upsert_records "$MISSING_RECORDS"
    echo "app-init: embedded and upserted $missing_count missing point(s)"
fi

if [ "$stale_count" -gt 0 ]; then
    echo "app-init: deleting $stale_count stale point(s) from vectorstore"
    delete_ids_json=$(jq -R -s -c 'split("\n") | map(select(length > 0))' "$STALE_IDS")
    curl -sf -X POST "$QDRANT_URL/collections/$COLLECTION/points/delete?wait=true" \
        -H 'Content-Type: application/json' \
        --data "{\"points\": $delete_ids_json}" >/dev/null
fi

if [ "$missing_count" -eq 0 ] && [ "$stale_count" -eq 0 ]; then
    echo "app-init: vectorstore already in sync with the database"
fi

# ============================================================================
# 5. KEYCLOAK ADMIN BOOTSTRAP
# ============================================================================
# Runs on every app-init run (idempotent). Two parts:
#   5a. grant the medidex-backoffice service account the realm-management
#       roles it needs (always).
#   5b. optionally create/approve an admin account, if ADMIN_EMAIL and
#       ADMIN_PASSWORD are both set.
KEYCLOAK_URL="${KEYCLOAK_URL:-http://keycloak:8080}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-medidex}"
KEYCLOAK_ADMIN_CLIENT_ID="${KEYCLOAK_ADMIN_CLIENT_ID:-medidex-backoffice}"
KEYCLOAK_ADMIN_CLIENT_SECRET="${KEYCLOAK_ADMIN_CLIENT_SECRET:?is not set; must be the medidex-backoffice client secret}"
KC_ADMIN_URL="$KEYCLOAK_URL/admin/realms/$KEYCLOAK_REALM"
KC_RESPONSE_BODY="/tmp/kc-admin-response.json"

# Runs a Keycloak Admin API call. Prints the response body to stdout on
# one of the given (space-separated) acceptable status codes, otherwise
# prints the status and body to stderr and aborts. Without this, a
# non-2xx response from any of these calls previously failed silently
# (curl -f + set -e, no diagnostic output).
kc_call() {
    method="$1"; url="$2"; ok_codes="$3"; shift 3
    status=$(curl -s -o "$KC_RESPONSE_BODY" -w '%{http_code}' -X "$method" "$url" \
        -H "Authorization: Bearer $kc_token" "$@")
    case " $ok_codes " in
        *" $status "*) cat "$KC_RESPONSE_BODY" ;;
        *)
            echo "app-init: ERROR: $method $url returned $status" >&2
            cat "$KC_RESPONSE_BODY" >&2
            exit 1
            ;;
    esac
}

# URL-encodes its single argument (e.g. an email address) for use in a query string.
urlencode() {
    jq -rn --arg v "$1" '$v|@uri'
}

echo "app-init: waiting for keycloak realm '$KEYCLOAK_REALM' at $KEYCLOAK_URL..."
attempt=1
until curl -sf -o /dev/null "$KEYCLOAK_URL/realms/$KEYCLOAK_REALM"; do
    if [ "$attempt" -ge 60 ]; then
        echo "app-init: ERROR: keycloak realm '$KEYCLOAK_REALM' is not reachable after 120s" >&2
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 2
done

kc_backoffice_token=$(curl -sf -X POST "$KEYCLOAK_URL/realms/$KEYCLOAK_REALM/protocol/openid-connect/token" \
    -d "grant_type=client_credentials" \
    -d "client_id=$KEYCLOAK_ADMIN_CLIENT_ID" \
    -d "client_secret=$KEYCLOAK_ADMIN_CLIENT_SECRET" | jq -r '.access_token // empty')
if [ -z "$kc_backoffice_token" ]; then
    echo "app-init: ERROR: could not obtain a Keycloak admin token" >&2
    exit 1
fi

# --- 5a. grant medidex-backoffice its realm-management client roles -------
# Needed so the backend's admin API (app/backend/fastapi_app/admin.py) can
# manage users and manage Keycloak clients (API keys). realm-medidex.json
# declares these too, but that file is only applied on a fresh realm import,
# so this makes an already-provisioned realm self-heal on every run.
#
# This has to run as the actual Keycloak master-realm admin, not as
# medidex-backoffice itself: granting the role requires view-clients to even
# look up the realm-management client's id, which is exactly the permission
# medidex-backoffice doesn't have yet (chicken-and-egg).
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:?is not set; must be the Keycloak master-realm admin password}"

kc_master_token=$(curl -sf -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
    -d "grant_type=password" \
    -d "client_id=admin-cli" \
    -d "username=$KEYCLOAK_ADMIN" \
    -d "password=$KEYCLOAK_ADMIN_PASSWORD" | jq -r '.access_token // empty')
if [ -z "$kc_master_token" ]; then
    echo "app-init: ERROR: could not obtain a Keycloak master-realm admin token" >&2
    exit 1
fi

kc_token="$kc_master_token"
realm_mgmt_client_id=$(kc_call GET "$KC_ADMIN_URL/clients?clientId=realm-management&exact=true" "200" \
    | jq -r '.[0].id // empty')
backoffice_sa_user_id=$(kc_call GET "$KC_ADMIN_URL/users?username=service-account-$KEYCLOAK_ADMIN_CLIENT_ID&exact=true" "200" \
    | jq -r '.[0].id // empty')

if [ -n "$realm_mgmt_client_id" ] && [ -n "$backoffice_sa_user_id" ]; then
    current_roles=$(kc_call GET "$KC_ADMIN_URL/users/$backoffice_sa_user_id/role-mappings/clients/$realm_mgmt_client_id" "200" \
        | jq -r '[.[].name] | join(",")')
    roles_to_grant=""
    for role_name in manage-clients view-clients; do
        case ",$current_roles," in
            *",$role_name,"*) ;;
            *) roles_to_grant="$roles_to_grant $role_name" ;;
        esac
    done
    if [ -n "$roles_to_grant" ]; then
        echo "app-init: granting$roles_to_grant to $KEYCLOAK_ADMIN_CLIENT_ID's service account"
        available_roles=$(kc_call GET "$KC_ADMIN_URL/clients/$realm_mgmt_client_id/roles" "200")
        grant_payload=$(printf '%s\n' $roles_to_grant | jq -R . | jq -s --argjson available "$available_roles" \
            '[ .[] as $name | $available[] | select(.name == $name) ]')
        kc_call POST "$KC_ADMIN_URL/users/$backoffice_sa_user_id/role-mappings/clients/$realm_mgmt_client_id" "204" \
            -H 'Content-Type: application/json' --data "$grant_payload" >/dev/null
    else
        echo "app-init: $KEYCLOAK_ADMIN_CLIENT_ID's service account already has manage-clients/view-clients"
    fi
else
    echo "app-init: WARNING: could not resolve realm-management client or $KEYCLOAK_ADMIN_CLIENT_ID's service account; skipping client-role grant" >&2
fi

# Back to medidex-backoffice's own token for everything below - it already
# has the permissions (manage-users) that the rest of this script needs.
kc_token="$kc_backoffice_token"

# --- 5b. optional admin bootstrap account ----------------------------------
# Set both ADMIN_EMAIL and ADMIN_PASSWORD to create an approved admin in
# Keycloak on startup (idempotent: safe to run on every app-init run).
if [ -n "${ADMIN_EMAIL:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
    ADMIN_NAME="${ADMIN_NAME:-Administrator}"

    admin_email_encoded=$(urlencode "$ADMIN_EMAIL")
    admin_user_id=$(kc_call GET "$KC_ADMIN_URL/users?email=$admin_email_encoded&exact=true" "200" \
        | jq -r '.[0].id // empty')

    if [ -z "$admin_user_id" ]; then
        echo "app-init: creating Keycloak admin account for $ADMIN_EMAIL"
        admin_first_name=$(printf '%s' "$ADMIN_NAME" | awk '{print $1}')
        admin_last_name=$(printf '%s' "$ADMIN_NAME" | awk '{$1=""; sub(/^ /,""); print}')
        # ADMIN_NAME may be a single word (e.g. the "Administrator" default),
        # which would otherwise leave lastName empty.
        [ -n "$admin_last_name" ] || admin_last_name="User"
        create_payload=$(jq -cn \
            --arg username "$ADMIN_EMAIL" --arg email "$ADMIN_EMAIL" \
            --arg firstName "$admin_first_name" --arg lastName "$admin_last_name" \
            --arg password "$ADMIN_PASSWORD" \
            '{username:$username, email:$email, firstName:$firstName, lastName:$lastName,
              enabled:true, emailVerified:true,
              credentials:[{type:"password", value:$password, temporary:false}]}')
        # 409 means a matching user already exists (e.g. left over from an
        # earlier run) - fall through to the lookups below instead of
        # treating it as fatal.
        kc_call POST "$KC_ADMIN_URL/users" "201 409" \
            -H 'Content-Type: application/json' --data "$create_payload" >/dev/null
        admin_user_id=$(kc_call GET "$KC_ADMIN_URL/users?email=$admin_email_encoded&exact=true" "200" \
            | jq -r '.[0].id // empty')
        if [ -z "$admin_user_id" ]; then
            # Fall back to a username search in case the email lookup missed
            # it (e.g. a differently-cased email from an earlier run).
            admin_user_id=$(kc_call GET "$KC_ADMIN_URL/users?username=$admin_email_encoded&exact=true" "200" \
                | jq -r '.[0].id // empty')
        fi
    else
        echo "app-init: Keycloak admin account for $ADMIN_EMAIL already exists"
    fi

    if [ -z "$admin_user_id" ]; then
        echo "app-init: ERROR: admin user was not created/found in Keycloak" >&2
        exit 1
    fi

    admin_role=$(kc_call GET "$KC_ADMIN_URL/roles/ADMIN" "200")
    kc_call POST "$KC_ADMIN_URL/users/$admin_user_id/role-mappings/realm" "204" \
        -H 'Content-Type: application/json' --data "[$admin_role]" >/dev/null

    approved_group_id=$(kc_call GET "$KC_ADMIN_URL/groups?search=approved-users" "200" | jq -r '.[0].id // empty')
    if [ -n "$approved_group_id" ]; then
        kc_call PUT "$KC_ADMIN_URL/users/$admin_user_id/groups/$approved_group_id" "204" >/dev/null
    fi

    echo "app-init: Keycloak admin account is ready for $ADMIN_EMAIL"
else
    echo "app-init: ADMIN_EMAIL/ADMIN_PASSWORD not set; skipping Keycloak admin bootstrap"
fi

echo "app-init: initialization complete"
