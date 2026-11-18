import os
import sys

# Let pages import `api_client` the same way they do when Streamlit runs them.
FRONTEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, FRONTEND_DIR)
os.chdir(FRONTEND_DIR)
