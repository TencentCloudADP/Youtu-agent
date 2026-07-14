from unittest.mock import Mock

from scripts.data import process_gaia


def test_download_gaia_snapshot_keeps_dataset_card(monkeypatch, tmp_path):
    snapshot_download = Mock(return_value=str(tmp_path))
    monkeypatch.setattr(process_gaia, "snapshot_download", snapshot_download)

    result = process_gaia.download_gaia_snapshot(tmp_path)

    assert result == str(tmp_path)
    snapshot_download.assert_called_once_with(
        repo_id="gaia-benchmark/GAIA",
        repo_type="dataset",
        local_dir=str(tmp_path),
        ignore_patterns=[".gitattributes"],
    )


def test_load_gaia_dataset_uses_parquet_directory_config(monkeypatch, tmp_path):
    dataset = object()
    load_dataset = Mock(return_value=dataset)
    monkeypatch.setattr(process_gaia.datasets, "load_dataset", load_dataset)

    result = process_gaia.load_gaia_dataset(tmp_path, "validation")

    assert result is dataset
    load_dataset.assert_called_once_with(str(tmp_path), "2023_all", split="validation")
