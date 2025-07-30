import streamlit as st
import pandas as pd
import requests
import os
from dotenv import load_dotenv
from utils.login import show_logout, get_headers

load_dotenv()

BACKEND_API = os.getenv('BACKEND_API')

current_embedding = None
current_model = None

def get_embeddings(text):
    payload = {"text": text}
    response = requests.post(BACKEND_API + "/embed/aspect", json=payload, headers=get_headers())

    if response.status_code == 200:
        data = response.json()
        embedding = data.pop("embedding")
        model = data.pop("model_id")

        return model, embedding
        
    else:
        st.error("Error: " + response.text)
        return None, None
    
def get_similar_studies(embedding, model, aspect):
    payload = {"main_embedding": embedding, "author_embedding":None, "model_id": model}
    params = {"aspect":aspect}
    response = requests.post(BACKEND_API + f"/similarity_search/studies", json=payload, params=params, headers=get_headers())

    if response.status_code == 200:
        return pd.DataFrame(response.json())
    else:
        st.error("Error: " + response.text)
        return None

options = ["Participants", "Intervention", "Condition", "Outcome"]

col1, col2 = st.columns(2)

selection = st.segmented_control(
    "Aspect", options, selection_mode="single", default=options[0], label_visibility="hidden", width="stretch"
)
placeholder = "Search string"
if selection == options[0]:
    placeholder = "Type something like '100' or '42' "
if selection == options[1]:
    placeholder = "Type something like 'risperidone' or 'family therapy' "
if selection == options[2]:
    placeholder = "Type something like 'first episode' or 'depression' "
if selection == options[3]:
    placeholder = "Type something like 'negative symptome scale' or 'blood pressure' "

search_string = st.text_input("Search string", label_visibility="hidden", placeholder=placeholder)
#abstract = st.text_area("Abstract")

study_search_results = None

if st.button("Search", icon=":material/search:", use_container_width=True,  key="search_1") and search_string != "":
    study_indices = None
    current_model, current_embedding = get_embeddings(search_string)

    study_search_results = get_similar_studies(current_embedding, current_model, selection.lower())

if study_search_results is not None:
    st.dataframe(study_search_results)

