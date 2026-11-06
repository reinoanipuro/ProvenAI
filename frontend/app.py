"""Streamlit UI. It only displays results: every decision comes from the FastAPI backend."""

import html
import os

import httpx
import streamlit as st

API_URL = os.environ.get("PROVENAI_API_URL", "http://127.0.0.1:8000")
STATUS_ORDER = {"FAIL": 0, "UNKNOWN": 1, "PASS": 2}
OVERALL_TEXT = {
    "PASS": ("All checks passed", "Every value was found, sourced, and within its limit."),
    "FAIL": ("Requirements not met", "At least one value breaks a rule."),
    "UNKNOWN": (
        "Could not check everything",
        "No violations so far, but a specialist must review the UNKNOWN items.",
    ),
}

st.set_page_config(page_title="ProvenAI Compliance Checker", page_icon="✅", layout="wide")
st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; max-width: 1400px; }
    .pill { padding: .1rem .6rem; border-radius: 999px; font-size: .75rem;
            font-weight: 700; color: #fff; }
    .is-PASS { background: #1b7a4b; }
    .is-FAIL { background: #b3261e; }
    .is-UNKNOWN { background: #a15c00; }
    .head { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem; }
    .title { font-weight: 600; }
    .muted { color: #5b6673; font-size: .85rem; overflow-wrap: anywhere; }
    .reason { margin: .35rem 0 .2rem; overflow-wrap: anywhere; }
    .banner { border-radius: 10px; padding: .9rem 1.1rem; color: #fff; margin-bottom: .75rem; }
    .banner b { display: block; font-size: 1.25rem; }
    .step { font-weight: 600; margin-top: .6rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def api(method: str, path: str, **kwargs):
    try:
        response = httpx.request(method, f"{API_URL}{path}", timeout=180, **kwargs)
        response.raise_for_status()
    except httpx.HTTPError as error:
        st.error(f"Backend error at {API_URL}: {error}")
        st.stop()
    return response.json()


def safe_html(template: str, **values) -> None:
    """Render trusted markup with every dynamic value escaped."""
    escaped = {key: html.escape(str(value)) for key, value in values.items()}
    st.markdown(template.format(**escaped), unsafe_allow_html=True)


def clear_results() -> None:
    """Results must never appear beside a different plan from the one they belong to."""
    st.session_state.pop("inspection", None)


def show_evidence(finding: dict, min_confidence: float) -> None:
    rule, evidence = finding["rule"], finding["rule_evidence"]
    extraction, decision = finding["extraction"], finding["decision"]

    st.markdown('<div class="step">1 · Regulatory RAG</div>', unsafe_allow_html=True)
    safe_html('<div class="muted">{note}</div>', note=evidence["note"])
    if passage := evidence["passage"]:
        safe_html(
            '<div class="muted">{file} · clause {clause} · page {page} · relevance {rel}</div>',
            file=passage["file"], clause=passage["clause"],
            page=passage["page"], rel=f"{passage['relevance']:.2f}",
        )
        st.code(passage["text"], language=None, wrap_lines=True)

    st.markdown('<div class="step">2 · Document Intelligence</div>', unsafe_allow_html=True)
    value = f"{extraction['value']} {extraction['unit']}".strip() if extraction["value"] else "none"
    safe_html(
        '<div class="muted">Value: {value} · status: {status} · '
        "confidence: {confidence} (required {required})</div>",
        value=value, status=extraction["status"],
        confidence=f"{extraction['confidence']:.2f}", required=f"{min_confidence:.2f}",
    )
    if extraction["note"]:
        safe_html('<div class="muted">{note}</div>', note=extraction["note"])
    for source in extraction["sources"]:
        safe_html(
            '<div class="muted">{file} · section "{section}" · page {page}</div>',
            file=source["file"], section=source["section"], page=source["page"],
        )
        st.code(source["quote"], language=None, wrap_lines=True)

    st.markdown('<div class="step">3 · Rule engine (no LLM)</div>', unsafe_allow_html=True)
    target = f"{rule['operator']} {rule['threshold']} {rule['unit']}".strip()
    safe_html('<div class="muted">Rule {id}: value must be {target}</div>', id=rule["id"], target=target)
    if decision["computation"]:
        st.code(decision["computation"], language=None)
    else:
        safe_html('<div class="muted">No comparison was run, so the result is UNKNOWN.</div>')


def show_results(inspection: dict) -> None:
    overall = inspection["overall"]
    title, detail = OVERALL_TEXT[overall]
    safe_html(
        '<div class="banner is-{overall}"><b>{title}</b>{detail}</div>',
        overall=overall, title=title, detail=detail,
    )
    findings = inspection["findings"]
    statuses = [f["decision"]["status"] for f in findings]
    areas = len({f["rule"]["domain"] for f in findings})
    safe_html(
        '<div class="muted">{document} · {rules} rules across {areas} rule areas · '
        "{passed} passed, {failed} failed, {unknown} unknown</div><br>",
        document=inspection["document"], rules=len(findings), areas=areas,
        passed=statuses.count("PASS"), failed=statuses.count("FAIL"),
        unknown=statuses.count("UNKNOWN"),
    )

    for finding in sorted(findings, key=lambda f: STATUS_ORDER[f["decision"]["status"]]):
        rule, decision = finding["rule"], finding["decision"]
        with st.container(border=True):
            safe_html(
                '<div class="head"><span class="pill is-{status}">{status}</span>'
                '<span class="title">{title}</span>'
                '<span class="muted">{domain} · clause {clause}</span></div>'
                '<div class="reason">{reason}</div>',
                status=decision["status"], title=rule["title"], domain=rule["domain"],
                clause=rule["clause"], reason=decision["reason"],
            )
            with st.expander("Evidence chain"):
                show_evidence(finding, inspection["min_confidence"])

    with st.expander("Audit log"):
        st.dataframe(
            [
                {
                    "#": event["seq"],
                    "Time (UTC)": event["ts"][:19].replace("T", " "),
                    "Event": event["event"],
                    "Rule": event["payload"].get("rule", ""),
                }
                for event in api("GET", f"/inspections/{inspection['id']}/audit")
            ],
            hide_index=True,
            width="stretch",
        )


st.title("ProvenAI Compliance Checker")
st.caption("AI finds the evidence. Deterministic code makes the decision. If unsure, it says so.")
st.warning("Demo only: the regulations and plans are fictional.", icon="⚠️")

left, right = st.columns([2, 3], gap="large")
with left:
    st.subheader("Plan to check")
    filename = st.selectbox(
        "Sample plan", api("GET", "/samples"), label_visibility="collapsed", on_change=clear_results
    )
    text = api("GET", f"/samples/{filename}")["text"]
    if st.button("Run compliance check", type="primary", width="stretch"):
        with st.spinner("Running the checks..."):
            st.session_state.inspection = api(
                "POST", "/inspections", json={"filename": filename, "text": text}
            )
    st.code(text, language="markdown", height=420, wrap_lines=True)

with right:
    st.subheader("Results")
    if inspection := st.session_state.get("inspection"):
        show_results(inspection)
    else:
        st.info("Choose a plan and select **Run compliance check**.")
