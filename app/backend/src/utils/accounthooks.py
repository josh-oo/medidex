"""Extension point for what a deployable keeps of a user and removes when they delete their account (e.g. their
personal settings or keys). Downstream deployables register their hooks at startup.

A hook runs inside the transaction of the deletion (AccountService.delete), after the assignments of the user are
removed and before it is committed; it must not commit. An exception rolls the deletion back, and the user keeps their
account.
"""

from typing import List, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


class AccountHook(Protocol):
    async def on_delete(self, db: AsyncSession, user_id: str) -> None:
        """Called for a user whose account is being deleted, on the session of the deletion."""
        ...


class AccountHookRegistry:
    def __init__(self) -> None:
        self._hooks: List[AccountHook] = []

    def register(self, hook: AccountHook) -> None:
        self._hooks.append(hook)

    def all(self) -> List[AccountHook]:
        return list(self._hooks)


account_hook_registry = AccountHookRegistry()
