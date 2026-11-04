type Timestamp = Date | string | number | null | undefined;

const toTimestamp = (value: Timestamp): number | null => {
  if (value === null || value === undefined) {
    return null;
  }
  const date = value instanceof Date ? value : new Date(value);
  const timestamp = date.getTime();
  return Number.isFinite(timestamp) ? timestamp : null;
};

/** The study was created after the report, i.e. it was added as a new study for it. */
export const isNewStudyAssignment = (studyCreatedAt: Timestamp, reportCreatedAt: Timestamp): boolean => {
  const studyTimestamp = toTimestamp(studyCreatedAt);
  const reportTimestamp = toTimestamp(reportCreatedAt);
  return studyTimestamp !== null && reportTimestamp !== null && studyTimestamp > reportTimestamp;
};
