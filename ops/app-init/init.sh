#!/bin/sh
# Combined init: prepares the qdrant collection, the logic data volume and Keycloak.
# Runs as the one-shot `app-init` service on `docker compose up`, before `logic` starts.
# It never touches postgres: the backend makes the schema of the resources database and syncs the
# vectorstore itself when it starts (app/backend/src/background/startup.py).
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
# resources/report_pdfs: the PDFs of the reports, named by report id (app/backend/src/utils/pdfs.py).
for dir in logs resources resources/report_pdfs resources/pdf_metadata; do
    mkdir -p "$DATABASE_VOLUME/$dir"
done
chown -R "$APP_UID:$APP_GID" "$DATABASE_VOLUME"
echo "app-init: data volume prepared for uid $APP_UID:$APP_GID"

# ============================================================================
# 3. KEYCLOAK ADMIN BOOTSTRAP
# ============================================================================
# Runs on every app-init run (idempotent). Two parts:
#   3a. grant the medidex-backoffice service account the realm-management
#       roles it needs (always).
#   3b. optionally create/approve an admin account, if ADMIN_EMAIL and
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

# --- 3a. grant medidex-backoffice its realm-management client roles -------
# Needed so the backend's admin API (app/backend/fastapi_app/admin.py) can
# manage users. realm-medidex.json
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

# --- 3b. optional admin bootstrap account ----------------------------------
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
