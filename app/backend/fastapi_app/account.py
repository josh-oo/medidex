"""The account of the signed-in user: deleting it (src/services/account.py). The routes take a user signed in to the UI,
approved or not (a user waiting for approval can delete their account as well), never other credentials."""

from fastapi import APIRouter, Depends, HTTPException, Response

from src.context import RequestContext
from src.services.account import AccountOwnsResourcesError
from src.utils.dto import AccountDeletion

from .admin import delete_keycloak_user, is_only_admin
from .deps import get_account_context

router = APIRouter(tags=["account"])


async def _deletion(ctx: RequestContext) -> AccountDeletion:
    deletion = await ctx.account_service.get_deletion()
    deletion.onlyAdmin = ctx.is_admin and await is_only_admin(ctx.account_service.user_id)
    return deletion


@router.get(
    "/users/me/deletion",
    summary="What stands in the way of deleting the account of the caller.",
    description="The projects and study databases they own (hand them over first), whether they are the only administrator, "
    "and the projects they are assigned to and have not handed in every report of (their assignments go with the account).",
)
async def get_account_deletion(ctx: RequestContext = Depends(get_account_context)) -> AccountDeletion:
    return await _deletion(ctx)


@router.delete(
    "/users/me",
    summary="Delete the account of the caller.",
    description="Removes their assignments to projects with their commits and what the deployable keeps of them, then their "
    "user. What they contributed stays under their user id, which no longer resolves to a name. 409 while they own a "
    "project or a study database, or are the only administrator.",
    status_code=204,
)
async def delete_account(ctx: RequestContext = Depends(get_account_context)):
    deletion = await _deletion(ctx)
    if deletion.onlyAdmin:
        raise HTTPException(status_code=409, detail="You are the only administrator: make another user an administrator first")
    try:
        await ctx.account_service.delete()
    except AccountOwnsResourcesError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Last: if anything before failed, the user can sign in and try again.
    await delete_keycloak_user(ctx.account_service.user_id)
    return Response(status_code=204)
