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
The application is divided into multiple services to facilitate hosting on different machines later
## frontend
This is just a prototype to visualize and test the applications features.  
### Env Vars:
`BACKEND_API=http://logic:8002`
## logic
This services manages the incoming requests from the frontend and calls the appropriate sub-services in the backend
### Env Vars:
`DATABASE_HOST=database`
`DATABASE_PORT=8001`
`EMBEDDING_HOST=embedding`
`EMBEDDING_PORT=50051`
`VECTORSTORE_HOST=qdrant`
`VECTORSTORE_PORT=6334`
## database
Currently this service hosts the meerkat (sql) database and provides a simple REST interface to execute queries. However, in future it might make more sense to run this service, where the meerkat data is actually hosted, so that we don't need a copy of meerkat data in this app.
### Env Vars:
`DATABASE_VOLUME="/data"`
## embedding
This service is used to transform plain text into vector embeddings using a self-trained model. Currently this service runs on a CPU machine. Depending on the workload it might make sense to move this service to a GPU machine later. The model is hosted at https://huggingface.co/josh-oo/aspect-based-embeddings-v3
### Env Vars:
`MODEL_PATH="josh-oo/aspect-based-embeddings-v3"`
`MODEL_REVISION="6b211a8f4e27b904ab146da7d63a084c2fd94223"`
`MODEL_DTYPE="bfloat16"`
`TOKENIZER_PATH="josh-oo/aspect-based-embeddings-v3"`
`TOKENIZER_REVISION="6b211a8f4e27b904ab146da7d63a084c2fd94223"`
`ASPECTS="participants,intervention,condition,outcome"`
`MODEL_DIM=1024`
If you use another model please adapt the parameters accordingly
## qdrant
This is where all the vectores are stored to index the meerkat reports based on their similarity.
### Env Vars:
No environment variables
## routines
This service hosts routínes like searching for unindexed reports in meerkat to add them to the index properly.
### Env Vars:
`DATABASE_HOST=database`
`DATABASE_PORT=8001`
`EMBEDDING_HOST=embedding`
`EMBEDDING_PORT=50051`
`VECTORSTORE_HOST=qdrant`
`VECTORSTORE_PORT=6334`

# Rules for editing this repository
1. If you are working on this repository please create a new branch for every feature / bugfix and use meaningful prefixes.
   For example: `bugfix/embedding-model-data-type` or `feature/new-upload-button`
2. If the bugfix is done you can create a pull request, to merge it back to `main`
3. The `prod` branch is currently empty we will use it later for CI/CD as soon as we are ready for production.

# Local Development
To run a the project locally you need to start the vectorstore first: `docker run -p 6333:6333 -p 6334:6334 -v /backend/_data/qdrant:/qdrant/storage qdrant/qdrant`. For the host location an absolute path is required.
