"""Page B: Upload and Process. Preview, validation controls and batch summary."""
import streamlit as st

from src import config
from src.ingestion import IngestionError, load_csv
from src.pipeline import ProcessingResult, process_file


def render() -> None:
    st.header("Upload & Process")
    st.caption("Validate a sales CSV, load accepted records and record every batch in the audit trail.")

    source = st.radio("Data source", ["Upload a CSV file", "Use a sample dataset"], horizontal=True)
    raw, name = None, None

    if source == "Upload a CSV file":
        upload = st.file_uploader("Choose a CSV file", type=["csv"])
        if upload is not None:
            raw, name = upload.getvalue(), upload.name
    else:
        choice = st.selectbox("Sample dataset", [
            "Clean sample (sample_sales.csv)",
            "Sample with deliberate errors (sample_sales_with_errors.csv)",
        ])
        path = config.SAMPLE_CLEAN_FILE if choice.startswith("Clean") else config.SAMPLE_DIRTY_FILE
        if path.exists():
            raw, name = path.read_bytes(), path.name
        else:
            st.error("Sample file not found. Run `python scripts/generate_sample_data.py` first.")

    if raw is None:
        st.info("Choose a file to see a preview.")
        return

    try:
        loaded = load_csv(raw, name)
    except IngestionError as exc:
        st.error(f"This file cannot be processed: {exc}")
        return

    st.subheader("Preview")
    st.caption(
        f"{len(loaded.frame):,} data row(s) detected in {name}. "
        f"{loaded.malformed_count} malformed line(s) will be skipped."
    )
    if loaded.malformed_samples:
        with st.expander("Malformed lines that will be skipped"):
            for sample in loaded.malformed_samples:
                st.code(sample)
    st.dataframe(loaded.frame.drop(columns=["row_number"]).head(10), use_container_width=True, hide_index=True)

    force = st.checkbox(
        "Reprocess even if an identical file was processed before (audit history is kept)",
        help="Existing orders are never overwritten, so sales totals stay the same.",
    )
    if st.button("Validate & process", type="primary"):
        with st.spinner("Validating records and loading accepted sales..."):
            st.session_state["last_result"] = (name, process_file(raw, name, force=force))

    if "last_result" in st.session_state:
        shown_name, result = st.session_state["last_result"]
        st.divider()
        _show_result(shown_name, result)


def _show_result(name: str, result: ProcessingResult) -> None:
    st.subheader(f"Batch summary · {name}")
    if result.status == "Blocked":
        st.warning(result.message)
        return
    if result.status == "Failed":
        st.error(result.message)
        return
    if result.status == "Completed":
        st.success(result.message)
    else:
        st.warning(result.message)

    c = result.counts
    cols = st.columns(6)
    cols[0].metric("Received", f"{c['total_received']:,}")
    cols[1].metric("Accepted", f"{c['accepted_count']:,}")
    cols[2].metric("Flagged", f"{c['flagged_count']:,}")
    cols[3].metric("Rejected", f"{c['rejected_count']:,}")
    cols[4].metric("Duplicates", f"{c['duplicate_count']:,}")
    cols[5].metric("Loaded to sales", f"{c['loaded_count']:,}")
    st.caption(f"Batch ID: {result.batch_id}. Open 'Data Quality' for the scorecard and error details.")
