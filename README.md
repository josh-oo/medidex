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

6. Run `docker compose up` (it may take a while building all the images)  
7. If it is done you can use the tool at http://localhost:8051
