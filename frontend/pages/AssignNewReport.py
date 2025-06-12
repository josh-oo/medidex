import streamlit as st
import pandas as pd
import requests
import os
from dotenv import load_dotenv
from utils.login import show_login

load_dotenv()

BACKEND_API = os.getenv('BACKEND_API')

current_embedding = None
current_aspect_embeddings = None
current_model = None

def get_headers():
    headers = {}
    if "access_token" in st.session_state:
        headers = {"Authorization": f"Bearer {st.session_state['access_token']}"}
    return headers

def get_embeddings(text):
    payload = {"text": text}
    response = requests.post(BACKEND_API + "/embedding/aspects", json=payload, headers=get_headers())

    if response.status_code == 200:
        data = response.json()
        embedding = data.pop("embedding")
        model = data.pop("model_id")
        aspect_embeddings = data

        return model, embedding, aspect_embeddings
        
    else:
        print("Request failed:", response.status_code, response.text)
        return None, None, None
    
def get_similar_studies(embedding, model):
    payload = {"embedding": embedding, "model_id": model}
    response = requests.post(BACKEND_API + "/similarity_search/studies", json=payload, headers=get_headers())

    if response.status_code == 200:
        return pd.DataFrame(response.json())
    else:
        print("Request failed:", response.status_code, response.text)
        return None

def get_similar_tags(embedding, model, tag):
    payload = {"embedding": embedding, "model_id": model}
    response = requests.post(BACKEND_API + f"/similarity_search/tags/{tag}", json=payload, headers=get_headers())

    if response.status_code == 200:
        return pd.DataFrame(response.json())
    else:
        print("Request failed:", response.status_code, response.text)
        return None

study_search_results = None
intervention_search_results = None
condition_search_results = None
outcome_search_results = None

uploaded_file = st.file_uploader("Upload your RIS, CGI or NBIB file", type=["ris", "nbib", "cgi"])
if uploaded_file is not None:
    # Read the file content as bytes
    file_content = uploaded_file.getvalue()
    
    # Create a multipart form-data request
    files = {'file': (uploaded_file.name, file_content, 'application/octet-stream')}
    headers = {"Authorization": f"Bearer {st.session_state.get('access_token',None)}"}
    
    # Send the file to FastAPI server for processing
    response = requests.post(BACKEND_API + f"/upload", files=files, headers=get_headers())
    
    if response.status_code != 200:
        st.error(f"Error: {response.text}")
    else:
        #st.json(response.json())  # Display parsed JSON response from FastAPI
        index = st.slider("Select loaded report", 0, len(response.json()), 0)
        selected_report = response.json()[index]
    
        title = selected_report['title']
        abstract = selected_report['abstract']
        st.header(title)
        st.write(abstract)

        if st.button("Search", icon=":material/search:", use_container_width=True,  key="search_1") and title + abstract != "":
            text_to_process = []
            if title:
                text_to_process.append(title)
            if abstract:
                text_to_process.append(abstract)
            text_to_process = "\n".join(text_to_process)
            current_model, current_embedding, current_aspect_embeddings = get_embeddings(text_to_process)
            if current_model is None or current_embedding is None or current_aspect_embeddings is None:
                st.error("Could not parse inputs")

            study_search_results = get_similar_studies(current_embedding, current_model)
            intervention_search_results = get_similar_tags(current_aspect_embeddings['intervention'], current_model, "interventions")
            condition_search_results = get_similar_tags(current_aspect_embeddings['condition'], current_model, "conditions")
            outcome_search_results = get_similar_tags(current_aspect_embeddings['outcome'], current_model, "outcomes")

if study_search_results is not None:
    tab1, tab2, tab3, tab4 = st.tabs(["Studies", "Interventions", "Conditions", "Outcomes"])

    with tab1:
        if study_search_results is not None:
            st.dataframe(study_search_results)
        else:
            st.write("No search results")

    with tab2:
        if intervention_search_results is not None:
            st.dataframe(intervention_search_results)
        else:
            st.write("No search results")

    with tab3:
        if condition_search_results is not None:
            st.dataframe(condition_search_results)
        else:
            st.write("No search results")

    with tab4:
        if outcome_search_results is not None:
            st.dataframe(outcome_search_results)
        else:
            st.write("No search results")

with st.sidebar:
    show_login()