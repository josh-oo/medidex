from __future__ import annotations

from .schemas import StudyDto


def summarize_stream_event(event: dict) -> dict:
    if not isinstance(event, dict) or not event:
        return {"event": "unknown", "message": "Empty stream event."}

    node, update = next(iter(event.items()))
    update = update or {}
    summary: dict[str, object] = {"event": "node", "node": node}

    def extract_study_info(value: object) -> dict:
        if isinstance(value, StudyDto):
            return {"study_id": value.studyId, "short_name": value.shortName}
        if isinstance(value, dict):
            return {
                "study_id": value.get("studyId"),
                "short_name": value.get("shortName"),
            }
        return {}

    match node:
        case "load_next_initial":
            current = update.get("current")
            info = extract_study_info(current)
            if info.get("study_id") is None:
                summary["message"] = "No more studies."
            else:
                summary["message"] = f"Initial classification for {info.get('short_name')}."
                summary["details"] = info
        case "load_next_unsure":
            current = update.get("current")
            info = extract_study_info(current)
            if info.get("study_id") is None:
                summary["message"] = "No more studies."
            else:
                summary["message"] = f"Review of the unsure study {info.get('short_name')}."
                summary["details"] = info
        case "load_next_likely":
            current = update.get("current")
            info = extract_study_info(current)
            if info.get("study_id") is None:
                summary["message"] = "No more likely studies to review."
            else:
                summary["message"] = f"Review of the likely study {info.get('short_name')}."
                summary["details"] = info
        case "prepare_report_pdf":
            status = update.get("pdf_status")
            if status == "disabled":
                summary["message"] = "Report PDF inclusion disabled."
            else:
                attachment = update.get("report_pdf_attachment")
                if attachment:
                    summary["message"] = "Attached report PDF for evaluation."
                    summary["details"] = {
                        "report_id": attachment.get("report_id"),
                        "title": attachment.get("title"),
                    }
                else:
                    summary["message"] = "No report PDF attached."
        case "classify_initial":
            decision = update.get("decision")
            reason = update.get("reason")
            idx = update.get("idx")
            study_id = update.get("study_id")
            if study_id:
                summary["message"] = (
                    f"Initial classification: {decision}. {reason}"
                )
            else:
                summary["message"] = f"Initial classification: {decision}. {reason}"
            summary["details"] = {
                "study_id": study_id,
                "decision": update.get("decision"),
                "reason": reason,
                "idx": idx,
            }
        case "select_very_likely":
            very_likely = update.get("very_likely", []) or []
            selected_ids = [
                item.get("study_id") for item in very_likely if isinstance(item, dict)
            ]
            selected_names = []
            for item in very_likely:
                if not isinstance(item, dict):
                    continue
                short_name = item.get("short_name")
                if isinstance(short_name, str) and short_name.strip():
                    selected_names.append(short_name)
                    continue
                study_id = item.get("study_id")
                if study_id is not None:
                    selected_names.append(str(study_id))
            reason = update.get("reason")
            summary["message"] = "Selected very_likely candidates."
            summary["details"] = {
                "very_likely_study_ids": selected_ids,
                "very_likely_names": selected_names,
                "reason": reason,
            }
            if selected_names:
                summary["message"] = (
                    f"Selected very_likely candidates: {', '.join(selected_names)}. {reason}"
                )
            else:
                summary["message"] = f"No very_likely candidates selected. {reason}"
        case "compare_very_likely":
            match = update.get("match")
            decision = update.get("decision")
            reason = update.get("reason")
            match_id = match.get("study_id") if isinstance(match, dict) else None
            summary["message"] = "Compared very_likely candidates."
            summary["details"] = {
                "decision": decision,
                "match_study_id": match_id,
                "reason": reason,
            }
            if decision == "match" and match_id:
                summary["message"] = f"Match found! {reason}"
            else:
                summary["message"] = f"No match from very_likely. {reason}"
        case "prepare_unsure_review":
            queue = update.get("unsure_queue", []) or []
            summary["message"] = f"Prepared unsure review queue ({len(queue)} studies)."
            summary["details"] = {"count": len(queue)}
        case "prepare_likely_review":
            count = update.get("count")
            if isinstance(count, int):
                summary["message"] = f"Prepared likely review queue ({count} studies)."
                summary["details"] = {"count": count}
            else:
                summary["message"] = "Prepared likely review queue."
        case "classify_unsure":
            decision = update.get("decision")
            reason = update.get("reason")
            study_id = update.get("study_id")
            summary["message"] = f"Unsure re-evaluation: {decision}. {reason}"
            summary["details"] = {
                "study_id": study_id,
                "decision": decision,
                "reason": reason,
            }
        case "classify_likely_review":
            decision = update.get("decision")
            reason = update.get("reason")
            study_id = update.get("study_id")
            summary["message"] = f"Likely re-evaluation: {decision}. {reason}"
            summary["details"] = {
                "study_id": study_id,
                "decision": decision,
                "reason": reason,
            }
        case "summarize_evaluation":
            evaluation_summary = (
                update.get("evaluation_summary", {}) if isinstance(update, dict) else {}
            )

            summary_text = evaluation_summary.get("summary")
            summary["message"] = f"\n{summary_text}"
            summary["details"] = evaluation_summary
        case "suggest_new_study":
            new_study = update.get("new_study_suggestion") if isinstance(update, dict) else None
            if new_study:
                summary["message"] = "AI suggested a new study draft."
                summary["details"] = {"new_study": new_study}
            else:
                summary["message"] = "No new study suggestion available."
        case "match_not_found_end":
            summary["message"] = "No match found after all reviews."
        case _:
            summary["message"] = "Node completed."
            summary["details"] = update

    return summary
