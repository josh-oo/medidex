from typing import List

from ..context import RequestContext
from ..database.sessions import AsyncSessionLocal
from ..database.models import Report as DbReport
from ..services.agent import AutomationService
from ..utils.llm.agent import get_checkpointer


async def run_process_report_background(
    project_id: str,
    report_ids: List[int],
    user_id: str,
    process_report,
) -> None:
    async with AsyncSessionLocal() as db:
        ctx = RequestContext(db=db, user_id=user_id)

        reports: List[DbReport] = []
        for report_id in report_ids:
            report = await ctx.report_repo.get_report_by_id(report_id)
            if report is not None:
                reports.append(report)

        await process_report(reports, project_id, ctx)



async def run_start_automation_background(
    project_id: str,
    user_id: str,
    model: str,
    start_automation,
) -> None:
    async with AsyncSessionLocal() as db:
        ctx = RequestContext(db=db, user_id=user_id)

        async for checkpointer in get_checkpointer():
            agent_service = AutomationService(
                user_id=user_id,
                report_repo=ctx.report_repo,
                study_repo=ctx.study_repo,
                document_service=ctx.document_service,
                study_similarity_service=ctx.study_similarity_service,
                checkpointer=checkpointer,
                model=model,
            )
            await start_automation(project_id, ctx, agent_service)
            break
