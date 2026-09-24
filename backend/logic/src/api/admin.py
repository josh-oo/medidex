from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from dotenv import load_dotenv

from typing import Dict, List, Optional
import os
import secrets

from keycloak import KeycloakAdmin

from .auth import KEYCLOAK_URL, KEYCLOAK_REALM, is_admin, is_verified, verify_token, revoke_api_key_cache

load_dotenv()

"""
Keycloak administration

All Keycloak Admin REST API access (user management, and API keys modeled as
Keycloak client_credentials clients) is centralized here, authenticated as the
"medidex-backoffice" service account. This credential must never be handed to
the frontend - the frontend calls the routes below (forwarding the caller's own
user token), and this module is the only place that holds admin-level Keycloak
access.
"""

KEYCLOAK_ADMIN_CLIENT_ID = os.getenv("KEYCLOAK_ADMIN_CLIENT_ID")
KEYCLOAK_ADMIN_CLIENT_SECRET = os.getenv("KEYCLOAK_ADMIN_CLIENT_SECRET")

if not KEYCLOAK_ADMIN_CLIENT_ID or not KEYCLOAK_ADMIN_CLIENT_SECRET:
    raise RuntimeError("KEYCLOAK_ADMIN_CLIENT_ID and KEYCLOAK_ADMIN_CLIENT_SECRET must be set")

router = APIRouter(tags=["admin"])

keycloak_admin = KeycloakAdmin(
    server_url=KEYCLOAK_URL,
    realm_name=KEYCLOAK_REALM,
    client_id=KEYCLOAK_ADMIN_CLIENT_ID,
    client_secret_key=KEYCLOAK_ADMIN_CLIENT_SECRET,
    grant_type="client_credentials",
)

APP_ROLE_NAMES = {"USER", "ADMIN"}

# Cache of the "/approved-users" group id - it never changes at runtime.
_approved_group_id_cache: Optional[str] = None

async def get_approved_group_id() -> str:
    global _approved_group_id_cache
    if _approved_group_id_cache:
        return _approved_group_id_cache
    group = await keycloak_admin.a_get_group_by_path("/approved-users")
    _approved_group_id_cache = group["id"]
    return _approved_group_id_cache

async def get_approved_user_ids() -> set:
    group_id = await get_approved_group_id()
    members = await keycloak_admin.a_get_group_members(group_id, query={"max": 1000})
    return {member["id"] for member in members}

def display_name(user: dict) -> str:
    full_name = f"{user.get('firstName', '')} {user.get('lastName', '')}".strip()
    return full_name or user.get("username", "")

async def get_user_roles(user_id: str) -> List[str]:
    role_reps = await keycloak_admin.a_get_realm_roles_of_user(user_id)
    roles = [r["name"] for r in role_reps if r["name"] in APP_ROLE_NAMES]
    return roles or ["USER"]

async def build_user_summary(user_id: str, approved_ids: Optional[set] = None) -> "UserSummary":
    try:
        user = await keycloak_admin.a_get_user(user_id)
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")
    if approved_ids is None:
        approved_ids = await get_approved_user_ids()
    return UserSummary(
        id=user_id,
        name=display_name(user),
        email=user.get("email"),
        roles=await get_user_roles(user_id),
        is_approved=user_id in approved_ids,
    )

class UserSummary(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    roles: List[str]
    is_approved: bool

class UpdateRolesRequest(BaseModel):
    roles: List[str]

@router.get("/admin/users", summary="List all users.")
async def list_users(_: str = Depends(is_admin)) -> List[UserSummary]:
    users = await keycloak_admin.a_get_users({"max": 1000})
    approved_ids = await get_approved_user_ids()
    return [
        await build_user_summary(user["id"], approved_ids)
        for user in users
    ]

@router.get("/admin/users/names", summary="Resolve display names for a comma-separated list of user ids.")
async def get_user_names(ids: str = "", _: str = Depends(is_verified)) -> Dict[str, str]:
    names: Dict[str, str] = {}
    for user_id in [i for i in ids.split(",") if i]:
        try:
            user = await keycloak_admin.a_get_user(user_id)
            names[user_id] = display_name(user)
        except Exception:
            continue
    return names

@router.get("/admin/users/{user_id}", summary="Get a single user.")
async def get_user(user_id: str, _: str = Depends(is_admin)) -> UserSummary:
    return await build_user_summary(user_id)

@router.put("/admin/users/{user_id}/roles", summary="Replace a user's application roles.")
async def update_user_roles(user_id: str, body: UpdateRolesRequest, _: str = Depends(is_admin)) -> UserSummary:
    current = await keycloak_admin.a_get_realm_roles_of_user(user_id)
    current_names = {r["name"] for r in current}

    to_add_names = [name for name in body.roles if name in APP_ROLE_NAMES and name not in current_names]
    to_remove = [r for r in current if r["name"] in APP_ROLE_NAMES and r["name"] not in body.roles]

    if to_add_names:
        to_add = [await keycloak_admin.a_get_realm_role(name) for name in to_add_names]
        await keycloak_admin.a_assign_realm_roles(user_id, to_add)
    if to_remove:
        await keycloak_admin.a_delete_realm_roles_of_user(user_id, to_remove)

    return await build_user_summary(user_id)

@router.put("/admin/users/{user_id}/approve", summary="Approve a user.")
async def approve_user(user_id: str, _: str = Depends(is_admin)) -> UserSummary:
    group_id = await get_approved_group_id()
    await keycloak_admin.a_group_user_add(user_id, group_id)
    return await build_user_summary(user_id)

@router.delete("/admin/users/{user_id}", summary="Delete a user.", status_code=204)
async def delete_user(user_id: str, _: str = Depends(is_admin)):
    await keycloak_admin.a_delete_user(user_id)
    return Response(status_code=204)


"""
API keys

Modeled as Keycloak client_credentials service-account clients rather than a
local table: the returned key is "<client_id>.<client_secret>", sent as a
plain X-API-Key header exactly like the old locally-issued keys. Verifying
one (exchanging it for a token at Keycloak's token endpoint, cached) is
handled in api/auth.py's verify_api_key/is_verified_api_call - this module
only creates/lists/deletes the underlying client.
"""

API_KEY_CLIENT_PREFIX = "apikey-"
OWNER_ATTRIBUTE = "medidex.owner"
# Kept short so a token exchanged just before a key is deleted (racing the cache
# eviction in delete_api_key below) still expires quickly on its own, instead of
# living for the realm's default access-token lifespan.
API_KEY_ACCESS_TOKEN_LIFESPAN_SECONDS = "60"

# Must mirror the protocol mappers on the "medidex-frontend" client in
# keycloak/realm-medidex.json, so tokens issued for API-key clients also carry
# the flattened "roles" claim verify_token() reads and validate the audience
# checks the rest of the app relies on.
API_KEY_PROTOCOL_MAPPERS = [
    {
        "name": "flat-realm-roles",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-usermodel-realm-role-mapper",
        "consentRequired": False,
        "config": {
            "multivalued": "true",
            "userinfo.token.claim": "true",
            "id.token.claim": "true",
            "access.token.claim": "true",
            "claim.name": "roles",
            "jsonType.label": "String",
        },
    },
    {
        "name": "audience-medidex-frontend",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-audience-mapper",
        "consentRequired": False,
        "config": {
            "included.client.audience": "medidex-frontend",
            "id.token.claim": "false",
            "access.token.claim": "true",
        },
    },
]

class ApiKeyResponse(BaseModel):
    api_key: str

async def find_api_key_client(key_id: str, owner_id: str) -> dict:
    clients = await keycloak_admin.a_get_clients()
    for client in clients:
        if client.get("clientId") == key_id and client.get("attributes", {}).get(OWNER_ATTRIBUTE) == owner_id:
            return client
    raise HTTPException(status_code=404, detail="API key not found or does not belong to user")

@router.put("/users/me/api_keys", summary="Create a new API key for the given user.", status_code=201)
async def create_api_key(token: str = Depends(is_verified)) -> ApiKeyResponse:
    decoded = await verify_token(token)
    user_id = decoded["sub"]

    client_id_str = API_KEY_CLIENT_PREFIX + secrets.token_urlsafe(8)
    internal_id = await keycloak_admin.a_create_client({
        "clientId": client_id_str,
        "protocol": "openid-connect",
        "publicClient": False,
        "standardFlowEnabled": False,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": True,
        "attributes": {
            OWNER_ATTRIBUTE: user_id,
            "access.token.lifespan": API_KEY_ACCESS_TOKEN_LIFESPAN_SECONDS,
        },
        "protocolMappers": API_KEY_PROTOCOL_MAPPERS,
    })

    secret = await keycloak_admin.a_get_client_secrets(internal_id)
    service_account_user = await keycloak_admin.a_get_client_service_account_user(internal_id)
    group_id = await get_approved_group_id()
    await keycloak_admin.a_group_user_add(service_account_user["id"], group_id)

    return ApiKeyResponse(api_key=f"{client_id_str}.{secret['value']}")

@router.get("/users/me/api_keys", summary="Get all API keys created by the given user.")
async def get_api_keys(token: str = Depends(is_verified)) -> List[str]:
    decoded = await verify_token(token)
    user_id = decoded["sub"]

    clients = await keycloak_admin.a_get_clients()
    return [
        client["clientId"] for client in clients
        if client.get("clientId", "").startswith(API_KEY_CLIENT_PREFIX)
        and client.get("attributes", {}).get(OWNER_ATTRIBUTE) == user_id
    ]

@router.delete("/users/me/api_keys/{key_id}", summary="Delete an API key belonging to the given user.", status_code=204)
async def delete_api_key(key_id: str, token: str = Depends(is_verified)):
    decoded = await verify_token(token)
    user_id = decoded["sub"]

    client = await find_api_key_client(key_id, user_id)
    await keycloak_admin.a_delete_client(client["id"])
    revoke_api_key_cache(key_id)
    return Response(status_code=204)
