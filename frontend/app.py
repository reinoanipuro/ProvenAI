"""ProvenAI engineer interface.

Run the backend first (uvicorn backend.api:app), then: streamlit run frontend/app.py
"""

import os
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

API_URL = os.environ.get("PROVENAI_API_URL", "http://127.0.0.1:8000").rstrip("/")
SAMPLES_PATH = Path(__file__).parent.parent / "data" / "samples"
EXAMPLES = {
    "Accessible passenger areas, deck 5": (
        "Deck 5 passenger corridor: clear width 800 mm.\n"
        "Cabin door clear opening 850 mm.\n"
        "Ramp to the pool deck has a running slope of 1:10.\n"
        "Stair handrail height 900 mm."
    ),
    "Open deck and superstructure": (
        "Superstructure end bulkhead door: sill height 300 mm.\n"
        "Open deck guard rail height 1100 mm."
    ),
    "Accessible cabin": (
        "Accessible cabin turning space diameter 1500 mm.\n"
        "Toilet seat height 450 mm.\n"
        "Cabin desk top height 750 mm.\n"
        "Light switch high forward reach 1300 mm."
    ),
    "Ballast water system": "Ballast water exchange efficiency of the system is 92 %.",
    "Regulation question": "Do stationary hotel ships need oil filtering equipment under MARPOL?",
    "Not covered (no DNV rules)": "Hull bottom plate thickness 12 mm.",
}
OVERALL = {
    "FAIL": ("error", "Not compliant: an approved rule fails."),
    "ISSUES_FOUND": ("warning", "Possible issues found from the regulation text. An engineer must confirm them."),
    "NEEDS_REVIEW": ("info", "Needs review: some items could not be checked reliably."),
    "PASS": ("success", "Compliant with every approved rule checked."),
    "NO_ISSUES_FOUND": ("success", "No issues found. Results read from regulation text must be confirmed."),
    "ANSWERED": ("info", "Answered from the regulation text. Confirm before relying on it."),
}
STATUS_ICON = {"FAIL": "❌", "PASS": "✅", "UNKNOWN": "❔", "NO_RULE": "🔎", "REQUIREMENT_FOUND": "📘"}
LEVEL_TEXT = {
    "verified": "Approved rule",
    "ai_read": "Read from regulation by AI",
    "manual_review": "Manual review",
}

st.set_page_config(page_title="ProvenAI", page_icon="✅", layout="wide")


def api_get(path: str, timeout: int = 30, **params):
    response = requests.get(f"{API_URL}{path}", params=params, timeout=timeout)
    response.raise_for_status()
    return response


def api_post(path: str, body: dict, timeout: int = 1800) -> dict:
    response = requests.post(f"{API_URL}{path}", json=body, timeout=timeout)
    if response.status_code >= 400:
        detail = response.json().get("detail", response.text) if response.content else response.text
        raise RuntimeError(f"{response.status_code}: {detail}")
    return response.json()


@st.cache_data(ttl=60)
def load_rules() -> dict:
    return api_get("/rules").json()


@st.cache_data(show_spinner=False)
def load_page_image(filename: str, page: int, quote: str) -> bytes:
    return api_get("/source/page", timeout=120, filename=filename, page=page, quote=quote).content


def show_citation(result: dict, key: str) -> None:
    citation = result.get("citation")
    if not citation:
        return
    verified = "✅ quote confirmed on the page" if citation["verified"] else f"⚠️ not confirmed: {citation['reason']}"
    st.markdown(
        f"**Source:** {result.get('regulation', '')} ({result.get('source_status', '')}), "
        f"{citation['filename']}, PDF page {citation['page']}, {citation['section']}  \n{verified}"
    )
    st.markdown(f"> {citation['quote']}")
    if st.toggle("Show the regulation page", key=f"page-{key}"):
        try:
            st.image(load_page_image(citation["filename"], citation["page"], citation["quote"]),
                     caption=f"{citation['filename']}, PDF page {citation['page']}. The requirement is highlighted.")
        except requests.RequestException as error:
            st.warning(f"Could not load the page: {error}")


def show_result(result: dict, index: int) -> None:
    status = result["status"]
    level = result.get("level", "")
    title = result.get("rule_id") or result.get("property") or ""
    confidence = f", {result['confidence']} confidence" if result.get("confidence") else ""
    with st.container(border=True):
        st.markdown(
            f"### {STATUS_ICON.get(status, '•')} {status.replace('_', ' ')} · {result['element']}"
            f"  \n<small>{title} · {LEVEL_TEXT.get(level, level)}{confidence}</small>",
            unsafe_allow_html=True,
        )
        if result.get("source"):
            st.caption(f"Design value found in {result['source']}")
        if result.get("comparison"):
            columns = st.columns(3)
            columns[0].metric("Design", result.get("design") or result.get("value_text", ""))
            columns[1].metric("Required", result.get("required", ""))
            columns[2].metric("Short by / over by", result.get("margin") or "within limit")
            st.markdown(f"**Why:** {result['comparison']}. {result.get('reason', '')}")
        elif result.get("answer"):
            st.markdown(f"**Answer:** {result['answer']}")
        else:
            st.markdown(f"**Why:** {result.get('reason', '')}")

        show_citation(result, f"{index}")

        if result.get("verification_steps"):
            with st.expander("How to verify this by hand"):
                for number, step in enumerate(result["verification_steps"], start=1):
                    st.markdown(f"{number}. {step}")
        if result.get("review"):
            with st.expander("Python's review of the AI reading"):
                st.dataframe(
                    pd.DataFrame([
                        {"Check": check["check"], "Passed": "✅" if check["passed"] else "❌", "Detail": check["detail"]}
                        for check in result["review"]
                    ]),
                    hide_index=True, width="stretch",
                )
        if result.get("passages") and level == "manual_review":
            with st.expander("Closest regulation passages to review"):
                for passage in result["passages"]:
                    st.markdown(
                        f"**{passage.get('regulation', '')}** ({passage.get('status', '')}), "
                        f"{passage['filename']}, PDF page {passage['page']}, {passage.get('section', '')}"
                    )
                    st.text(passage["text"][:700])
        if result.get("proposed_rule"):
            with st.expander("Approve this requirement as a rule"):
                st.caption(
                    "Only approve after checking the regulation page. Approved rules are checked "
                    "automatically next time and can fail a design."
                )
                st.json(result["proposed_rule"], expanded=False)
                if st.button("Approve as rule", key=f"approve-{index}"):
                    try:
                        answer = api_post("/rules/approve", {"proposal": result["proposed_rule"]}, timeout=60)
                    except (RuntimeError, requests.RequestException) as error:
                        st.error(f"Not approved: {error}")
                    else:
                        load_rules.clear()
                        st.success(f"Saved as {answer['approved']}.")


def _set_items(parsed: dict) -> None:
    st.session_state["items"] = parsed["items"]
    st.session_state["parse_warnings"] = parsed["warnings"]
    st.session_state["documents"] = parsed.get("documents", [])
    st.session_state.pop("result", None)


def design_check_tab(attributes: dict) -> None:
    st.subheader("1. Drop the design documents")
    files = st.file_uploader(
        "Text files, Word files, PDFs, or 2D pictures such as drawings",
        type=["pdf", "docx", "txt", "md", "csv", "png", "jpg", "jpeg", "webp", "bmp"],
        accept_multiple_files=True,
    )
    st.caption(
        "Values with units are read from the text. Pictures and drawing pages without text are "
        "stored for 2D reading, which is a later step."
    )
    if st.button("Read the documents", type="primary", disabled=not files):
        with st.spinner("Reading the documents. Mistral takes about a minute per part on this laptop."):
            try:
                response = requests.post(
                    f"{API_URL}/upload",
                    files=[("files", (file.name, file.getvalue(), file.type or "application/octet-stream")) for file in files],
                    timeout=1800,
                )
                if response.status_code >= 400:
                    raise RuntimeError(f"{response.status_code}: {response.json().get('detail', response.text)}")
            except (RuntimeError, requests.RequestException) as error:
                st.error(f"Could not read the documents: {error}")
            else:
                _set_items(response.json())

    with st.expander("Or type a description or question instead"):
        example = st.selectbox("Example", ["(write your own)", *EXAMPLES])
        text = st.text_area("Design description or question", EXAMPLES.get(example, ""),
                            height=110, key=f"text-{example}")
        if st.button("Read the text", disabled=not text.strip()):
            with st.spinner("Mistral is reading the text. This takes about a minute on this laptop."):
                try:
                    _set_items(api_post("/parse", {"text": text}, timeout=900))
                except (RuntimeError, requests.RequestException) as error:
                    st.error(f"Could not read the text: {error}")

    documents = st.session_state.get("documents", [])
    if documents:
        st.dataframe(
            pd.DataFrame([
                {
                    "File": document["filename"],
                    "Type": document["kind"],
                    "Pages with text": document["text_pages"],
                    "Pictures read with OCR": len(document["pictures"]),
                }
                for document in documents
            ]),
            hide_index=True, width="stretch",
        )
    for warning in st.session_state.get("parse_warnings", []):
        st.warning(warning)

    st.subheader("2. Confirm the values")
    st.caption(
        "Check each value against the document it was found in, then fix or add rows. Rows with an "
        "attribute from the rule library are checked against approved rules; the rest are "
        "looked up in the regulations."
    )
    items = st.session_state.get("items", [])
    frame = pd.DataFrame(items or [], columns=["element", "property", "attribute", "value_text", "source"])
    edited = st.data_editor(
        frame,
        num_rows="dynamic",
        width="stretch",
        column_config={
            "element": st.column_config.TextColumn("Design element", required=True),
            "property": st.column_config.TextColumn("What is measured or asked"),
            "attribute": st.column_config.SelectboxColumn(
                "Rule library attribute", options=["unknown", *attributes], default="unknown"
            ),
            "value_text": st.column_config.TextColumn("Value with unit (empty for a question)"),
            "source": st.column_config.TextColumn("Found in", disabled=True),
        },
        key="items-editor",
    )

    st.subheader("3. Check")
    columns = st.columns(2)
    use_rules = columns[0].toggle("Use approved rules", value=True,
                                  help="Off: every item is checked with Mistral and the regulation text only.")
    summarize = columns[1].toggle("Write a summary with Mistral", value=True,
                                  help="Adds about a minute. Off uses a short template summary.")
    rows = [
        {key: ("" if pd.isna(value) else str(value)) for key, value in row.items()}
        for row in edited.to_dict("records")
    ]
    rows = [row for row in rows if row.get("element") or row.get("value_text")]
    if st.button("Check the design", type="primary", disabled=not rows):
        with st.spinner("Checking. Items without an approved rule take 1 to 3 minutes each."):
            try:
                st.session_state["result"] = api_post(
                    "/check", {"items": rows, "summarize": summarize, "use_rule_library": use_rules}
                )
            except (RuntimeError, requests.RequestException) as error:
                st.error(f"The check failed: {error}")

    result = st.session_state.get("result")
    if not result:
        return
    st.divider()
    kind, message = OVERALL.get(result["overall"], ("info", result["overall"]))
    getattr(st, kind)(f"**{result['overall'].replace('_', ' ')}**: {message}")
    source = "Mistral, numbers checked by Python" if result["summary_source"] == "mistral" else "template"
    st.markdown(f"**Summary** ({source}): {result['summary']}")
    for warning in result["warnings"]:
        st.warning(warning)
    for index, item in enumerate(result["results"]):
        show_result(item, index)


def rule_library_tab(rules: dict) -> None:
    st.caption(
        "Approved rules are checked automatically by Python, and each quote is confirmed in the "
        "regulation PDF every time. Add a rule by approving an AI-read requirement on the check page."
    )
    st.dataframe(
        pd.DataFrame(rules["rules"])[["id", "title", "requirement", "filename", "page", "section"]],
        hide_index=True, width="stretch",
    )


def search_tab() -> None:
    query = st.text_input("Search the regulations", "minimum clear width of walking surfaces")
    if st.button("Search") and query.strip():
        try:
            found = api_post("/rag/search", {"query": query, "top_k": 5}, timeout=120)
        except (RuntimeError, requests.RequestException) as error:
            st.error(f"Search failed: {error}")
            return
        for passage in found["results"]:
            with st.container(border=True):
                st.markdown(
                    f"**{passage.get('regulation', '')}** ({passage.get('status', '')}), "
                    f"{passage['filename']}, PDF page {passage['page']}, {passage.get('section', '')} "
                    f"· score {passage['rerank_score']}"
                )
                st.text(passage["text"])


def simple_check_tab() -> None:
    st.caption("The original keyword-based check of the sample plans.")
    sample_names = sorted(path.name for path in SAMPLES_PATH.glob("*.md"))
    selected = st.selectbox("Sample plan", sample_names)
    text = (SAMPLES_PATH / selected).read_text(encoding="utf-8")
    st.text_area("Document", text, height=180)
    if st.button("Check compliance"):
        try:
            result = api_post("/inspect", {"text": text}, timeout=30)
        except (RuntimeError, requests.RequestException) as error:
            st.error(f"Could not reach the backend: {error}")
            return
        st.subheader(f"Overall: {result['overall']}")
        for finding in result["findings"]:
            with st.container(border=True):
                st.write(f"**{finding['status']}** · {finding['rule_id']}")
                st.write(finding["reason"])
                if finding["evidence"]:
                    st.code(finding["evidence"]["quote"])


st.title("ProvenAI")
st.caption(
    "Checks ship designs against regulations. Python makes every decision; Mistral only reads "
    "text and writes summaries; every result links to the regulation page."
)
try:
    api_get("/health", timeout=5)
    rule_data = load_rules()
except requests.RequestException:
    st.error(f"The backend is not running at {API_URL}. Start it with: uvicorn backend.api:app")
    st.stop()

check_tab, library_tab, regulation_tab, simple_tab = st.tabs(
    ["Design check", f"Rule library ({len(rule_data['rules'])})", "Regulation search", "Simple check"]
)
with check_tab:
    design_check_tab(rule_data["attributes"])
with library_tab:
    rule_library_tab(rule_data)
with regulation_tab:
    search_tab()
with simple_tab:
    simple_check_tab()
