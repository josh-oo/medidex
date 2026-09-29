import { ReportCurationDto, StudyDto, StudyPreviewDto } from "@/types/apiDTOs"
import { create } from "zustand"
import {
    assignStudyToReportByReportId,
    removeStudyFromReportByReportId,
} from "@/lib/api/reportApi"

const hasStudyById = (studies: StudyPreviewDto[] = [], studyId: number) =>
    studies.some((candidate) => candidate.studyId === studyId)

const assignStudyViaApi = async (reportId: number, studyId: number) => {
    await assignStudyToReportByReportId(reportId, studyId)
}

const removeStudyViaApi = async (reportId: number, studyId: number) => {
    await removeStudyFromReportByReportId(reportId, studyId)
}

type ReportState = {
    reports: Record<number, ReportCurationDto>
    setReports: (reports: ReportCurationDto[]) => void
    addReports: (reports: ReportCurationDto[]) => void
    getReport: (reportId: number) => ReportCurationDto
    addAssignedStudy: (reportId: number, study: StudyDto) => Promise<void>
    syncAssignedStudy: (reportId: number, study: StudyDto) => void
    removeAssignedStudy: (reportId: number, studyId: number) => Promise<void>
    setHasPdf: (reportId: number, hasPdf : boolean) => void;
    setFlag: (reportId: number, flag: string | undefined) => void;
}

export const useReportStore = create<ReportState>((set, get) => ({
    reports: {},

    setReports: (reports) => set({
        reports: Object.fromEntries(
            reports.map((r) => [r.reportId, r]),
        ),
    }),

    // Merges pages into the existing set instead of replacing it, so loading further pages
    // (or a filtered/search fetch that only covers a subset) never drops reports the store
    // already knows about - unlike setReports, which is only for a full reset (e.g. project
    // switch). Only ADDS reports the store doesn't already have; never overwrites an
    // existing entry. Without that, a slow filter/search fetch that started before a local
    // mutation (flag/study assignment) but resolves after it would clobber that mutation
    // back to the stale pre-mutation snapshot it fetched - the report's own dedicated
    // actions (setFlag/syncAssignedStudy/removeAssignedStudy/setHasPdf) are always the
    // source of truth for a report already in the store.
    addReports: (reports) => set((state) => {
        const additions = Object.fromEntries(
            reports
                .filter((r) => !(r.reportId in state.reports))
                .map((r) => [r.reportId, r]),
        );
        if (Object.keys(additions).length === 0) {
            return state;
        }
        return {
            reports: {
                ...state.reports,
                ...additions,
            },
        };
    }),

    getReport: (reportId) => {
        const report = get().reports[reportId]
        if (!report) {
            throw new Error(`Report ${reportId} not available`)
        }
        return report
    },

    syncAssignedStudy: (reportId, study) => {
        const report = get().reports[reportId]
        if (!report) {
            throw new Error(`Report ${reportId} not available`)
        }

        const currentStudies = report.assignedStudies ?? []
        if (hasStudyById(currentStudies, study.studyId)) {
            return
        }

        set((state) => {
            const updatedReport = state.reports[reportId]
            if (!updatedReport) {
                return state
            }
            const nextStudies = updatedReport.assignedStudies ?? []
            return {
                reports: {
                    ...state.reports,
                    [reportId]: {
                        ...updatedReport,
                        assignedStudies: [...nextStudies, study],
                    },
                },
            }
        })
    },

    addAssignedStudy: async (reportId, study) => {
        const report = get().reports[reportId]
        if (!report) {
            throw new Error(`Report ${reportId} not available`)
        }
        const currentStudies = report.assignedStudies ?? []
        if (hasStudyById(currentStudies, study.studyId)) {
            return
        }
        await assignStudyViaApi(reportId, study.studyId)
        get().syncAssignedStudy(reportId, study)
    },

    removeAssignedStudy: async (reportId, studyId) => {
        const report = get().reports[reportId]
        if (!report) {
            throw new Error(`Report ${reportId} not available`)
        }
        const currentStudies = report.assignedStudies ?? []
        if (!hasStudyById(currentStudies, studyId)) {
            return
        }
        await removeStudyViaApi(reportId, studyId)
        set((state) => {
            const updatedReport = state.reports[reportId]
            if (!updatedReport) {
                return state
            }
            return {
                reports: {
                    ...state.reports,
                    [reportId]: {
                        ...updatedReport,
                        assignedStudies: (updatedReport.assignedStudies ?? []).filter(
                            (item) => item.studyId !== studyId,
                        ),
                    },
                },
            }
        })
    },

    setHasPdf(reportId, hasPdf) {
        set((state) => {
            const updatedReport = state.reports[reportId];
            if (!updatedReport) {
                return state;
            }
            return {
                reports: {
                    ...state.reports,
                    [reportId]: {
                        ...updatedReport,
                        hasPdf,
                    },
                },
            };
        });
    },

    setFlag(reportId, flag) {
        set((state) => {
            const updatedReport = state.reports[reportId];
            if (!updatedReport) {
                return state;
            }
            return {
                reports: {
                    ...state.reports,
                    [reportId]: {
                        ...updatedReport,
                        flag,
                    },
                },
            };
        });
    },
}))