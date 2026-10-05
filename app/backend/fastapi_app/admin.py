from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from dotenv import load_dotenv

from typing import Dict, List, Optional
import os

from keycloak import KeycloakAdmin

from .auth import KEYCLOAK_URL, KEYCLOAK_REALM, is_admin, get_user

load_dotenv()

"""
Keycloak administration

All Keycloak Admin REST API access (user management) is centralized here, authenticated as the
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
async def get_user_names(ids: str = "", _: dict = Depends(get_user)) -> Dict[str, str]:
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
