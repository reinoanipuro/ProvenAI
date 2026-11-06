from pathlib import Path

import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000"
SAMPLES_PATH = Path(__file__).parent.parent / "data" / "samples"

st.set_page_config(page_title="ProvenAI", page_icon="✅")
st.title("ProvenAI")
st.caption("Evidence first. Deterministic decisions.")

sample_names = sorted(path.name for path in SAMPLES_PATH.glob("*.md"))
selected = st.selectbox("Sample plan", sample_names)
text = (SAMPLES_PATH / selected).read_text(encoding="utf-8")
st.text_area("Document", text, height=180)

if st.button("Check compliance", type="primary"):
    try:
        response = requests.post(f"{API_URL}/inspect", json={"text": text}, timeout=30)
        response.raise_for_status()
    except requests.RequestException as error:
        st.error(f"Could not reach the backend: {error}")
    else:
        result = response.json()
        st.subheader(f"Overall: {result['overall']}")
        for finding in result["findings"]:
            with st.container(border=True):
                st.write(f"**{finding['status']}** — {finding['rule_id']}")
                st.write(finding["reason"])
                if finding["evidence"]:
                    st.code(finding["evidence"]["quote"])
