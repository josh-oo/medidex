import streamlit as st
import pandas as pd
import requests
import os
from dotenv import load_dotenv

load_dotenv()

BACKEND_API = os.getenv('BACKEND_API')

current_embedding = None
current_model = None

def get_embeddings(text):
    payload = {"text": text}
    response = requests.post(BACKEND_API + "/embedding", json=payload)

    if response.status_code == 200:
        data = response.json()
        embedding = data.pop("embedding")
        model = data.pop("model_id")

        return model, embedding
        
    else:
        print("Request failed:", response.status_code, response.text)
        return None, None
    
def get_similar_studies(embedding, model, aspect):
    payload = {"embedding": embedding, "model_id": model}
    params = {"aspect":aspect}
    response = requests.post(BACKEND_API + f"/similarity_search/studies", json=payload, params=params)

    if response.status_code == 200:
        return pd.DataFrame(response.json())
    else:
        print("Request failed:", response.status_code, response.text)
        return None

options = ["Participants", "Intervention", "Condition", "Outcome"]

selection = st.segmented_control(
    "Aspect", options, selection_mode="single", default=options[0], label_visibility="hidden",
)
if selection == options[0]:
    st.write("Type something like '100' or '42' ")
if selection == options[1]:
    st.write("Type something like 'risperidone' or 'family therapy' ")
if selection == options[2]:
    st.write("Type something like 'first episode' or 'depression' ")
if selection == options[3]:
    st.write("Type something like 'negative symptome scale' or 'blood pressure' ")


search_string = st.text_input("Search string", label_visibility="hidden", placeholder="Search string")
#abstract = st.text_area("Abstract")

study_search_results = None

if st.button("Search", icon=":material/search:", use_container_width=True,  key="search_1") and search_string != "":
    study_indices = None
    current_model, current_embedding = get_embeddings(search_string)

    study_search_results = get_similar_studies(current_embedding, current_model, selection.lower())

if study_search_results is not None:
    st.dataframe(study_search_results)
else:
    st.write("No search results")

