import pytest

from src import config
from src.ingestion import IngestionError, compute_checksum, load_csv
from src.transformation import standardise_columns
from tests.helpers import HEADER, make_csv, make_row


def test_valid_csv_loads_with_row_numbers():
    loaded = load_csv(make_csv([make_row(), make_row(order_id="ORD-1002")]), "ok.csv")
    assert len(loaded.frame) == 2
    assert list(loaded.frame["row_number"]) == [1, 2]
    assert loaded.malformed_count == 0


def test_empty_file_is_rejected():
    with pytest.raises(IngestionError, match="empty"):
        load_csv(b"", "empty.csv")


def test_header_only_file_is_rejected():
    with pytest.raises(IngestionError, match="no data rows"):
        load_csv(make_csv([]), "header_only.csv")


def test_missing_required_column_is_named_in_message():
    header_without_quantity = HEADER.replace("quantity,", "")
    row = make_row().replace(",2,79.99", ",79.99")
    with pytest.raises(IngestionError, match="quantity"):
        load_csv(make_csv([row], header=header_without_quantity), "bad.csv")


def test_wrong_extension_is_rejected():
    with pytest.raises(IngestionError, match=".csv"):
        load_csv(make_csv([make_row()]), "sales.xlsx")


def test_file_size_limit(monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 20)
    with pytest.raises(IngestionError, match="larger than"):
        load_csv(make_csv([make_row()]), "big.csv")


def test_malformed_line_is_skipped_and_counted():
    bad = make_row() + ",EXTRA,FIELDS"
    loaded = load_csv(make_csv([make_row(order_id="ORD-2001"), bad, make_row(order_id="ORD-2002")]), "m.csv")
    assert loaded.malformed_count == 1
    assert list(loaded.frame["order_id"]) == ["ORD-2001", "ORD-2002"]


def test_checksum_is_stable_and_content_sensitive():
    assert compute_checksum(b"abc") == compute_checksum(b"abc")
    assert compute_checksum(b"abc") != compute_checksum(b"abd")


def test_column_names_are_standardised():
    import pandas as pd
    renamed = standardise_columns(pd.DataFrame({" Order Date ": ["x"], "Unit-Price": ["1"]}))
    assert list(renamed.columns) == ["order_date", "unit_price"]
