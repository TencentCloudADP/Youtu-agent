import json
import pathlib

import datasets
from huggingface_hub import login, snapshot_download
from sqlmodel import Session, select

from utu.db.eval_datapoint import DatasetSample
from utu.utils import DIR_ROOT, EnvUtils, SQLModelUtils

GAIA_REPO_ID = "gaia-benchmark/GAIA"
GAIA_CONFIG_NAME = "2023_all"


def download_gaia_snapshot(data_dir: pathlib.Path) -> str:
    """Download GAIA metadata and attachments in the current Parquet-backed format."""
    return snapshot_download(
        repo_id=GAIA_REPO_ID,
        repo_type="dataset",
        local_dir=str(data_dir),
        # README.md contains the dataset configuration used by load_dataset.
        ignore_patterns=[".gitattributes"],
    )


def load_gaia_dataset(data_dir: pathlib.Path, split: str) -> datasets.Dataset:
    """Load a GAIA split from the downloaded directory."""
    return datasets.load_dataset(str(data_dir), GAIA_CONFIG_NAME, split=split)


def build_dataset(split: str, engine=None) -> None:
    if engine is None:
        engine = SQLModelUtils.get_engine()

    dataset_id = f"GAIA_{split}"
    data_dir = DIR_ROOT / "data" / "gaia"

    # check if exists
    with Session(engine) as session:
        data = session.exec(select(DatasetSample).where(DatasetSample.dataset == dataset_id)).all()
        if len(data) > 0:
            print("Dataset already exists! Skip.")
            return

    download_gaia_snapshot(data_dir)
    ds = load_gaia_dataset(data_dir, split)

    data: list[DatasetSample] = []
    for i, row in enumerate(ds.to_list()):
        data.append(
            DatasetSample(
                dataset=dataset_id,
                index=i + 1,
                source="GAIA",
                source_index=i + 1,
                question=row["Question"],
                answer=row["Final answer"],
                topic="",
                level=row["Level"],
                file_name=row["file_name"],
                meta={key: row.get(key, None) for key in ["task_id", "Annotator Metadata"]},
            )
        )
    print(f"Total {len(data)} samples")
    print(f"Sample: {json.dumps(data[0].model_dump(), ensure_ascii=False)}")

    with Session(engine) as session:
        session.add_all(data)
        session.commit()
        print("Upload complete.")


def main() -> None:
    login(EnvUtils.get_env("HF_TOKEN"))
    build_dataset(split="validation")


if __name__ == "__main__":
    main()
