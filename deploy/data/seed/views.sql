-- OPTIONAL adapter: conventional-naming views over a domain-specific physical
-- schema that doesn't already match what the application expects.
--
-- The bundled demo data (synthetic_seed.sql) creates its tables directly
-- under the generic snake_case names the application code
-- (app/backend/src/database/models.py) expects, so it has no need for this
-- file. This file exists for the case where the resources database is
-- instead pointed at a real physical schema that keeps its own naming --
-- e.g. a Cochrane-style database using CRG/CENTRAL table/column names
-- (tblReport, tblStudy, ...), which is what the view definitions below
-- adapt. These views re-expose that data under the generic snake_case names
-- the application expects, so the application code never has to know about
-- the domain-specific schema.
--
-- Each view is a simple 1:1 column projection over a single base table (no
-- joins, no computed columns), which makes it "automatically updatable" in
-- PostgreSQL: INSERT/UPDATE/DELETE (including INSERT ... ON CONFLICT) against
-- the view are rewritten straight onto the base table, so the ORM can treat
-- the view exactly like a table. Only applied when explicitly enabled (see
-- deploy/data/seed/schema-adapter.conf and ops/app-init/init.sh) -- adjust
-- the base table/column names below to match whatever physical schema is
-- actually in use before enabling it.
--
-- Views are dropped and recreated rather than CREATE OR REPLACE'd: Postgres
-- only allows CREATE OR REPLACE to append columns, not remove or reorder
-- them, and report/study intentionally expose fewer columns than their
-- physical tables (see below).

BEGIN;

DROP VIEW IF EXISTS "report";
-- report/study only expose columns the application actually reads or
-- writes (app/backend/src/database/models.py). tblReport also has
-- CENTRALReportID, Notes, OriginalTitle, CENTRALSubmissionStatus,
-- DatetoCENTRAL, Editors, DupString, CopyStatus, TypeofReportID, Edition,
-- Medium, StudyDesign, UDef3, ISBN, UDef5, PMID, UDef9, UDef10, UDef8 --
-- unused CRG/CENTRAL bookkeeping and legacy fields, left out on purpose.
CREATE VIEW "report" AS
SELECT
    "CRGReportID" AS id,
    "ReportNumber" AS report_number,
    "Title" AS title,
    "Authors" AS authors,
    "Journal" AS journal,
    "Year" AS year,
    "Volume" AS volume,
    "Issue" AS issue,
    "Pages" AS pages,
    "Language" AS language,
    "Abstract" AS abstract,
    "Dateentered" AS date_entered,
    "DateEdited" AS date_edited,
    "Publisher" AS publisher,
    "City" AS city,
    "PublicationTypeID" AS publication_type_id,
    "DOI" AS doi,
    "TrialRegistrationID" AS trial_registration_id
FROM "tblReport";
-- PublicationTypeID is NOT NULL with no base-table default, but the model
-- above no longer sets it, so the ORM's INSERT never mentions this column.
-- A view-level default fills it in for every insert made through the view
-- (PostgreSQL applies a view's own column default, if set, ahead of the
-- base table's when a column is omitted from an updatable-view INSERT).
ALTER VIEW "report" ALTER COLUMN publication_type_id SET DEFAULT 1;

DROP VIEW IF EXISTS "study";
-- Likewise, tblStudy also has CENTRALStudyID, CENTRALSubmissionStatus,
-- Notes, DateToCENTRAL, Search_Tagged, UDef4, UDef6 -- unused, left out.
-- ISRCTN and TrialRegistrationID are both trial-identifier columns on the
-- physical table; merged into one trial_registration_id here (concatenated
-- with "; " when both are set) since the application only needs one.
CREATE VIEW "study" AS
SELECT
    "CRGStudyID" AS id,
    "ShortName" AS short_name,
    "StatusofStudy" AS status,
    "TrialistContactDetails" AS trialist_contact_details,
    "DateEntered" AS date_entered,
    "DateEdited" AS date_edited,
    "NumberParticipants" AS number_participants,
    "Countries" AS countries,
    "Duration" AS duration,
    "Comparison" AS comparison,
    CASE
        WHEN "ISRCTN" IS NOT NULL AND "TrialRegistrationID" IS NOT NULL
            THEN "ISRCTN" || '; ' || "TrialRegistrationID"
        ELSE COALESCE("ISRCTN", "TrialRegistrationID")
    END AS trial_registration_id
FROM "tblStudy";

DROP VIEW IF EXISTS "study_report";
CREATE VIEW "study_report" AS
SELECT
    "StudyReportID" AS id,
    "CRGStudyID" AS study_id,
    "CRGReportID" AS report_id
FROM "tblStudyReport";

DROP VIEW IF EXISTS "participant";
CREATE VIEW "participant" AS
SELECT
    "ParticipantsID" AS id,
    "ParticipantDescription" AS description
FROM "tblParticipant";

DROP VIEW IF EXISTS "study_participant";
CREATE VIEW "study_participant" AS
SELECT
    "CRGStudyID" AS study_id,
    "ParticipantsID" AS participant_id
FROM "tblStudyParticipant";

DROP VIEW IF EXISTS "design";
CREATE VIEW "design" AS
SELECT
    "DesignID" AS id,
    "DesignDescription" AS description
FROM "tblDesign";

DROP VIEW IF EXISTS "study_design";
CREATE VIEW "study_design" AS
SELECT
    "CRGStudyID" AS study_id,
    "DesignID" AS design_id
FROM "tblStudyDesign";

DROP VIEW IF EXISTS "intervention";
CREATE VIEW "intervention" AS
SELECT
    "InterventionID" AS id,
    "InterventionDescription" AS description
FROM "tblIntervention";

DROP VIEW IF EXISTS "study_intervention";
CREATE VIEW "study_intervention" AS
SELECT
    "CRGStudyID" AS study_id,
    "InterventionID" AS intervention_id
FROM "tblStudyIntervention";

DROP VIEW IF EXISTS "condition";
CREATE VIEW "condition" AS
SELECT
    "HealthCareConditionID" AS id,
    "HealthCareConditionDescription" AS description
FROM "tblHealthCareCondition";

DROP VIEW IF EXISTS "study_condition";
CREATE VIEW "study_condition" AS
SELECT
    "CRGStudyID" AS study_id,
    "HealthCareConditionID" AS condition_id
FROM "tblStudyHealthCareCondition";

DROP VIEW IF EXISTS "outcome";
CREATE VIEW "outcome" AS
SELECT
    "OutcomeID" AS id,
    "OutcomeDescription" AS description
FROM "tblOutcome";

DROP VIEW IF EXISTS "study_outcome";
CREATE VIEW "study_outcome" AS
SELECT
    "CRGStudyID" AS study_id,
    "OutcomeID" AS outcome_id
FROM "tblStudyOutcome";

DROP VIEW IF EXISTS "project";
CREATE VIEW "project" AS
SELECT
    "BatchHash" AS id,
    "BatchDescription" AS description,
    "DateCreated" AS date_created,
    "UploadedBy" AS uploaded_by
FROM "tblBatch";

DROP VIEW IF EXISTS "project_assignee";
CREATE VIEW "project_assignee" AS
SELECT
    "BatchHash" AS project_id,
    "Assignee" AS assignee
FROM "tblBatchAssignees";

DROP VIEW IF EXISTS "fulltext_extraction";
CREATE VIEW "fulltext_extraction" AS
SELECT
    "CRGReportID" AS report_id,
    "data" AS data
FROM "tblFulltextExtractions";

DROP VIEW IF EXISTS "report_added";
CREATE VIEW "report_added" AS
SELECT
    "CRGReportID" AS report_id,
    "BatchHash" AS project_id,
    "AutoSearchedPdf" AS auto_searched_pdf
FROM "tblReportAdded";

DROP VIEW IF EXISTS "project_inner_score";
CREATE VIEW "project_inner_score" AS
SELECT
    "CRGReportID" AS report_id,
    "OtherID" AS other_id,
    "Score" AS score
FROM "tblBatchInnerScore";

DROP VIEW IF EXISTS "study_added";
CREATE VIEW "study_added" AS
SELECT
    "CRGStudyID" AS study_id,
    "DateCreated" AS date_created,
    "CreatedBy" AS created_by
FROM "tblStudyAdded";

DROP VIEW IF EXISTS "study_report_added";
CREATE VIEW "study_report_added" AS
SELECT
    "StudyReportID" AS study_report_id,
    "DateCreated" AS date_created,
    "CreatedBy" AS created_by,
    "Confirmed" AS confirmed
FROM "tblStudyReportAdded";

DROP VIEW IF EXISTS "report_flag";
CREATE VIEW "report_flag" AS
SELECT
    "CRGReportID" AS report_id,
    "CreatedBy" AS created_by,
    "DateCreated" AS date_created,
    "Message" AS message,
    "Public" AS public
FROM "tblReportFlag";

DROP VIEW IF EXISTS "analytics_event";
CREATE VIEW "analytics_event" AS
SELECT
    "EventID" AS id,
    "DateCreated" AS date_created,
    "CreatedBy" AS created_by,
    "Type" AS type,
    "RelatedReport" AS related_report_id
FROM "tblEvent";

COMMIT;
