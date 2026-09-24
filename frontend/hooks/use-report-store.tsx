import { ReportDetailDto, StudyDto } from "@/types/apiDTOs"
import { create } from "zustand"
import {
    assignStudyToReportByReportId,
    removeStudyFromReportByReportId,
} from "@/lib/api/reportApi"

const hasStudyById = (studies: StudyDto[] = [], studyId: number) =>
    studies.some((candidate) => candidate.studyId === studyId)

const assignStudyViaApi = async (reportId: number, studyId: number) => {
    await assignStudyToReportByReportId(reportId, studyId)
}

const removeStudyViaApi = async (reportId: number, studyId: number) => {
    await removeStudyFromReportByReportId(reportId, studyId)
}

type ReportState = {
    reports: Record<number, ReportDetailDto>
    setReports: (reports: ReportDetailDto[]) => void
    getReport: (reportId: number) => ReportDetailDto
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
            reports.map((r) => [r.report.reportId, r]),
        ),
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