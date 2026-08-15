import json

import pytest

from scripts.data import upload_dataset as upload_dataset_module


@pytest.fixture
def capture_uploaded_samples(monkeypatch):
    uploaded_samples = []
    monkeypatch.setattr(upload_dataset_module.SQLModelUtils, "check_db_available", lambda: True)
    monkeypatch.setattr(upload_dataset_module.DBService, "add", uploaded_samples.extend)
    return uploaded_samples


def write_jsonl(tmp_path, sample):
    file_path = tmp_path / "dataset.jsonl"
    file_path.write_text(json.dumps(sample) + "\n", encoding="utf-8")
    return file_path


def test_upload_dataset_uses_default_format_when_unspecified(tmp_path, capture_uploaded_samples):
    file_path = write_jsonl(
        tmp_path,
        {
            "dataset": "original-dataset",
            "source": "training_free_grpo",
            "question": "What is 2+2?",
            "answer": "4",
        },
    )

    upload_dataset_module.upload_dataset(str(file_path), "uploaded-dataset")

    assert len(capture_uploaded_samples) == 1
    sample = capture_uploaded_samples[0]
    assert sample.dataset == "uploaded-dataset"
    assert sample.source == "training_free_grpo"
    assert sample.question == "What is 2+2?"
    assert sample.answer == "4"


def test_upload_dataset_supports_explicit_llamafactory_format(tmp_path, capture_uploaded_samples):
    file_path = write_jsonl(
        tmp_path,
        {
            "instruction": "Answer the question.",
            "input": "What is 2+2?",
            "output": "4",
        },
    )

    upload_dataset_module.upload_dataset(str(file_path), "uploaded-dataset", data_format="llamafactory")

    assert len(capture_uploaded_samples) == 1
    sample = capture_uploaded_samples[0]
    assert sample.dataset == "uploaded-dataset"
    assert sample.question == "Answer the question.\n\nWhat is 2+2?"
    assert sample.answer == "4"
