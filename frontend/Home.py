import streamlit as st
import requests
import os
from dotenv import load_dotenv

load_dotenv()

BACKEND_API = os.getenv('BACKEND_API')

st.set_page_config(
    page_title="Meerkat AI",
    page_icon="🤖",
)

if "name" in st.session_state:
    with st.sidebar:
        st.write(st.session_state.name)

with st.form("login"):
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    response = None
    if st.form_submit_button("Sign Up", use_container_width=True, type="secondary"):
        payload = {"email": email, "password": password}
        response = requests.post(BACKEND_API + "/signup", json=payload)
        

    if st.form_submit_button("Login", use_container_width=True, type="primary"):
        data = {
            "username": email,
            "password": password,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        response = requests.post(BACKEND_API + "/login", data=data, headers=headers)

        st.session_state['access_token'] = response.json()['access_token']
        st.session_state['name'] = response.json()['name']
    
    if response:
        if response.status_code != 200:
            st.error(f"Error: {response.status_code} - {response.text}")
        #else:
        #    st.write(response.text)