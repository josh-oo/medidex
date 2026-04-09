# About
This is the backend (including a frontend prototype) of the meerkat tool.
# Building
This is a dockerized applicatiion. The most simple way to install this project is therefore using docker:  
Please install *docker* if not already done: [Windows](https://docs.docker.com/desktop/setup/install/windows-install/), [Mac](https://docs.docker.com/desktop/setup/install/mac-install/), [Linux](https://docs.docker.com/desktop/setup/install/linux/)  
Now you are ready to install this app on your machine:
1. Clone this repo either by `git clone https://github.com/josh-oo/meerkat-tool.git` or by just downloading and unzipping the .zip file. You should find it clicking on the green "code" button above.
2. Use your command line to navigate to the projects location for example if you it is on your desktop `cd desktop/meerkat-tool`.
3. To provide the tool with access to the meerkat data. Please copy the meerkat sqlite (.db) file to `_data/database/` and name it *meerkat.db*
4. OPTIONAL: If you want to skip the vector indexing process (which can take about 8h since it runs on cpu only) you can also put precomputed indices to the folder `_data/qdrant/`. It should then look like:
If you leave the `qdrant` folder empty the app starts indexing the reports after running the next step.  
<pre> 📁 <b>_data</b> 
  ├── 📁 <b>database</b> 
  │ └── 📄 <b>meerkat.db</b> 
  └── 📁 <b>qdrant</b> 
    ├── 📁 <b>aliases</b> 
    ├── 📁 <b>collections</b> 
    └── 📄 <b>raft_state.json</b> 
</pre> 

6. Place .env.production files for all services in the corresponding folders. The env vars needed are described in the section below.
7. Run `docker network create internal_net` and `docker network create public_net`
8. Run `docker compose up` (it may take a while building all the images)  
9. If it is done you can use the tool at http://localhost:8051
   
# Services
The application is divided into multiple services to facilitate hosting it on different machines later.
## frontend
This is just a prototype to visualize and test the applications features.  
### Env Vars (development):
`BACKEND_API_URL=http://logic:8002`  
## logic
This services manages the incoming requests from the frontend and calls the appropriate sub-services in the backend
### Env Vars (development):
`EMBEDDING_SERVICE_HOST=localhost` 
`EMBEDDING_SERVICE_PORT=50051`  
`VECTORSTORE_SERVICE_HOST=localhost`  
`VECTORSTORE_SERVICE_PORT=6334`  
`DATABASE_VOLUME="../_data/backend"`  
`JWT_SECRET=DEBUG_SECRET_KEY`  
`DEBUG=true`   
## embedding
This service is used to transform plain text into vector embeddings using a fine-tuned embedding model. Currently this service runs on a CPU machine. Depending on the workload it might make sense to move this service to a GPU machine later. The model is publicly available on huggingface (https://huggingface.co/josh-oo/aspect-based-embeddings-v3).
### Env Vars (development):
`MODEL_PATH="josh-oo/aspect-based-embeddings-v3"`  
`MODEL_REVISION="6b211a8f4e27b904ab146da7d63a084c2fd94223"`  
`MODEL_DTYPE="bfloat16"`  
`TOKENIZER_PATH="josh-oo/aspect-based-embeddings-v3"`  
`TOKENIZER_REVISION="6b211a8f4e27b904ab146da7d63a084c2fd94223"`  
`ASPECTS="participants,intervention,condition,outcome"`  
`MODEL_DIM=1024`  
`MODEL_MAX_INPUT_LENGTH=8192`  
If you use another model please adapt the parameters accordingly
## tools
This service hosts routínes like searching for unindexed reports in meerkat to add them to the index properly.
### Env Vars (development):
`EMBEDDING_SERVICE_HOST=localhost`  
`EMBEDDING_SERVICE_PORT=50051`  
`VECTORSTORE_SERVICE_HOST=localhost`  
`VECTORSTORE_SERVICE_PORT=6334`  
`MESH_DUMP_LOCATION="../_data/backend/tools/desc2025.xml"`  
`BACKEND_API_URL=http://localhost:8002`  
`BACKEND_API_KEY=PLEASE_CREATE_YOUR_OWN_API_KEY`  
## qdrant
This is where all the vectores are stored to index the meerkat reports based on their similarity.
### Env Vars:
No environment variables

# Rules for editing this repository
1. If you are working on this repository please create a new branch for every feature / bugfix and use meaningful prefixes.
   For example: `bugfix/embedding-model-data-type` or `feature/new-upload-button`
2. If the bugfix is done you can create a pull request, to merge it back to `main`
3. The `prod` branch is currently empty we will use it later for CI/CD as soon as we are ready for production.

# Local Development
Running the project locally (without docker) requires you to run a local vectorstor: `docker run -p 6333:6333 -p 6334:6334 -v /backend/_data/qdrant:/qdrant/storage qdrant/qdrant`. For the storage location (backend/_data/qdrant in this case) an absolute path is required.

# Database schema (important resource classes)  
```
CREATE TABLE IF NOT EXISTS "tblStudy" (  
    CENTRALStudyID INTEGER,  
    CRGStudyID INTEGER PRIMARY KEY AUTOINCREMENT,  
    ShortName TEXT,  
    StatusofStudy TEXT,  
    TrialistContactDetails TEXT,  
    CENTRALSubmissionStatus TEXT,  
    Notes TEXT,  
    DateEntered TEXT,  
    DateToCENTRAL TEXT,  
    DateEdited TEXT,  
    Search_Tagged INTEGER,  
    NumberParticipants TEXT,  
    Countries TEXT,  
    Duration TEXT,  
    UDef4 TEXT,  
    Comparison TEXT,  
    ISRCTN TEXT,  
    UDef6 TEXT,  
    TrialRegistrationID TEXT,  
    UDef8 REAL,  
    UDef10 REAL,  
    UDef9 REAL  
);  

CREATE TABLE IF NOT EXISTS "tblReport" (  
    CENTRALReportID INTEGER, 
    CRGReportID INTEGER PRIMARY KEY AUTOINCREMENT,  
    Title TEXT,  
    Notes TEXT,  
    ReportNumber INTEGER,  
    OriginalTitle TEXT,  
    Authors TEXT,  
    Journal TEXT,  
    Year INTEGER,  
    Volume TEXT,  
    Issue TEXT,  
    Pages TEXT,  
    Language TEXT,  
    Abstract TEXT,  
    CENTRALSubmissionStatus INTEGER,  
    CopyStatus TEXT,  
    DatetoCENTRAL TEXT,  
    Dateentered TEXT,  
    DateEdited TEXT,  
    Editors TEXT,  
    Publisher TEXT,  
    City TEXT,  
    DupString TEXT,  
    TypeofReportID INTEGER,  
    PublicationTypeID INTEGER,  
    Edition TEXT,  
    Medium TEXT,  
    StudyDesign TEXT,  
    DOI TEXT,  
    UDef3 TEXT,  
    ISBN TEXT,  
    UDef5 TEXT,  
    PMID TEXT,  
    TrialRegistrationID TEXT,  
    UDef9 REAL,  
    UDef10 REAL,  
    UDef8 REAL  
);

CREATE TABLE IF NOT EXISTS "tblStudyReport" (
  "StudyReportID" INTEGER PRIMARY KEY AUTOINCREMENT,
  "CRGStudyID" INTEGER NOT NULL,
  "CRGReportID" INTEGER NOT NULL,
  FOREIGN KEY("CRGStudyID") REFERENCES "tblStudy"("CRGStudyID") ON DELETE CASCADE,
  FOREIGN KEY("CRGReportID") REFERENCES "tblReport"("CRGReportID") ON DELETE CASCADE
);

CREATE TABLE sqlite_sequence(name,seq);  
CREATE INDEX idx_tblReport ON tblReport(CRGReportID);  
CREATE INDEX idx_tblStudy ON tblStudy(CRGStudyID); 
CREATE INDEX idx_tblStudyReport_r ON tblStudyReport(CRGReportID);
CREATE INDEX idx_tblStudyReport_s ON tblStudyReport(CRGStudyID); 
```

# Database schema (user management and temporary values)

```
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE IF NOT EXISTS "users" (
	"id"	INTEGER,
	"email"	TEXT NOT NULL,
	"password"	TEXT NOT NULL,
	"role"	TEXT NOT NULL DEFAULT 'user' CHECK("role" IN ('user', 'editor', 'admin')),
	"verified"	BOOLEAN NOT NULL DEFAULT 0,
	PRIMARY KEY("id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "api_keys" (
	"hash"	TEXT NOT NULL,
	"id"	TEXT NOT NULL,
	"owner"	INTEGER NOT NULL,
	PRIMARY KEY("id")
);
CREATE TABLE tmp_report_batches (
    batch_hash TEXT PRIMARY KEY,
    batch_description TEXT,
    number_reports INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE tmp_reports (
    CRGReportID INTEGER,
	batch_hash TEXT,
    batch_inner_id INTEGER,
	PRIMARY KEY (batch_hash, batch_inner_id)
    FOREIGN KEY(batch_hash) REFERENCES tmp_report_batches(batch_hash) ON DELETE CASCADE
);
```

# Important
In the sqlite table:  
tblStudy Dateentered and tblReport Dateentered need to be in iso format YYYY-MM-DD HH:MM:SS, use the script database/helper.py.
