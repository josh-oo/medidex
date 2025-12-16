from fastapi import APIRouter, Depends
from .auth import is_verified_api_call
from .utils.vectorstore import get_all_saved_crg_report_ids, delete_vectors_by_crg_report_ids
from .resources import get_all_reports_internal
from dotenv import load_dotenv
import asyncio

load_dotenv()

router = APIRouter(tags=["maintenance"], dependencies=[Depends(is_verified_api_call)])

@router.post("/maintenance/vectorstore/clean_up", summary="Clean up vectorstore, remove orphan nodes.")
async def vectorstore_clean_up():
    all_report_ids_vectorstore, all_report_ids_db = await asyncio.gather(
        get_all_saved_crg_report_ids(),
        get_all_reports_internal(None, None, None)
    )

    all_report_ids_vectorstore = set(all_report_ids_vectorstore)
    all_report_ids_db = set([item.CRGReportID for item in all_report_ids_db])

    # Find orphan IDs (in vectorstore but not in database)
    orphan_ids =  all_report_ids_vectorstore - all_report_ids_db
    
    # Delete orphan vectors
    if orphan_ids:
        await delete_vectors_by_crg_report_ids(list(orphan_ids),)
    
    return {
        "unique_vectorstore_points": len(all_report_ids_vectorstore),
        "unique_report_ids": len(all_report_ids_db),
        "orphan_ids_found": len(orphan_ids),
        "orphan_ids_deleted": list(orphan_ids)
    }


