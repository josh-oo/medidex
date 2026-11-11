"""Deleting the account of a user, by the user themselves: what stands in the way, and what goes.

A user who owns a study database (and so its updates) cannot delete their account: nobody else could finish or look
after them. They hand it over to another user first. What goes with the account: their assignments to projects
with their commits (whatever they did not commit no longer counts) and what the deployable keeps of them
(src/utils/accounthooks.py). What they contributed stays under their user id (links, studies, flags), which no longer
resolves to a name once their user is gone. The user itself lives in Keycloak and is deleted by the caller
(fastapi_app/account.py) after this.
"""

from ..database.repositories.database import DatabaseRepository
from ..database.repositories.project import ProjectRepository
from ..utils.accounthooks import AccountHookRegistry, account_hook_registry
from ..utils.dto import AccountDeletion, OpenTask, OwnedDatabase
from .project import ProjectResourceService
from .pubsub import ProjectPubSubService


class AccountOwnsResourcesError(Exception):
    """The user owns projects or study databases."""


class AccountService:
    def __init__(
        self,
        project_repo: ProjectRepository,
        database_repo: DatabaseRepository,
        project_service: ProjectResourceService,
        pubsub_service: ProjectPubSubService,
        account_hooks: AccountHookRegistry = account_hook_registry,
    ):
        self.project_repo = project_repo
        self.database_repo = database_repo
        self.project_service = project_service
        self.pubsub_service = pubsub_service
        self.account_hooks = account_hooks

    @property
    def user_id(self) -> str:
        if not self.project_repo.user_id:
            raise ValueError("A user is required")
        return self.project_repo.user_id

    async def get_deletion(self) -> AccountDeletion:
        """What the caller owns (which blocks the deletion) and the tasks they have not handed in (which they are
        warned about). Whether they are the only administrator is for the caller to fill in (it asks Keycloak)."""
        databases = await self.database_repo.get_databases_of_owner(self.user_id)
        tasks = await self.project_service.get_user_tasks()
        return AccountDeletion(
            ownedDatabases=[OwnedDatabase(databaseId=database.id, name=database.name) for database in databases],
            openTasks=[
                OpenTask(
                    projectId=task.projectId,
                    name=task.name,
                    numberReportsUncommitted=max(task.numberReportsCompleted - task.numberReportsCommitted, 0),
                    numberReportsOpen=max(task.numberReportsTotal - task.numberReportsCompleted, 0),
                )
                for task in tasks
                if not task.committed
            ],
        )

    async def delete(self) -> None:
        """Removes what medidex keeps of the caller, in one transaction: their assignments with their commits, and what
        the account hooks remove. Raises AccountOwnsResourcesError while they own a study database."""
        user_id = self.user_id
        deletion = await self.get_deletion()
        if deletion.ownedDatabases:
            raise AccountOwnsResourcesError("Hand over your study databases to another user before deleting your account")
        try:
            project_ids = await self.project_repo.remove_assignments_of(user_id)
            for hook in self.account_hooks.all():
                await hook.on_delete(self.project_repo.db, user_id)
            await self.project_repo.commit()
        except Exception:
            await self.project_repo.rollback()
            raise
        for project_id in project_ids:
            # Its assignees changed: its owner sees it on the Curation page.
            await self.pubsub_service.publish_project_update(project_id)
