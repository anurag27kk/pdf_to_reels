# Streamlit Cloud entry point — delegates to app.py
exec(open(__file__.replace("streamlit_app.py", "app.py")).read())
