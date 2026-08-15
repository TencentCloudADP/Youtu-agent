import argparse
import json
from typing import Literal

from utu.db import DatasetSample, DBService
from utu.utils import SQLModelUtils


def convert_format_default(data: dict) -> DatasetSample:
    if "id" in data:
        data.pop("id")
    # Create a DatasetSample object from the dictionary
    dataset_sample = DatasetSample(**data)
    return dataset_sample


def convert_format_llamafactory(data: dict) -> DatasetSample:
    """Convert SFT data with Alpaca format. see https://github.com/hiyouga/LLaMA-Factory/blob/main/data/README.md
    keys map:
        insturction, input -> question
        output -> answer
    """
    question = [data.get("instruction", None), data.get("input", None)]
    question = [s for s in question if s is not None and s.strip() != ""]
    assert len(question) > 0, "Either 'instruction' or 'input' must be provided."
    question_str = "\n\n".join(question)
    answer_str = data.get("output", "")
    return DatasetSample(question=question_str, answer=answer_str)


def upload_dataset(file_path: str, dataset_name: str, data_format: Literal["default", "llamafactory"] = "default"):
    """
    Connects to the database and uploads datapoints from a local JSONL file.
    """
    if not SQLModelUtils.check_db_available():
        print("Error: Database is not available. Please check your UTU_DB_URL environment variable.")
        return

    dataset_samples = []
    with open(file_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            data: dict = json.loads(line.strip())
            match data_format:
                case "default":
                    dataset_sample = convert_format_default(data)
                case "llamafactory":
                    dataset_sample = convert_format_llamafactory(data)
                case _:
                    raise ValueError(f"Unsupported data format: {data_format}")
            # setup dataset name & index
            dataset_sample.dataset = dataset_name
            dataset_sample.index = i
            dataset_samples.append(dataset_sample)

    DBService.add(dataset_samples)
    print(f"Uploaded {len(dataset_samples)} datapoints from {file_path} to dataset '{dataset_name}'.")

    print("Upload complete.")


def main():
    parser = argparse.ArgumentParser(description="Upload a dataset from a JSONL file to the database.")
    parser.add_argument("--file_path", type=str, help="The path to the input JSONL file.")
    parser.add_argument("--dataset_name", type=str, help="The name to assign to the dataset in the database.")
    parser.add_argument(
        "--data_format",
        type=str,
        default="default",
        choices=["default", "llamafactory"],
        help="The format of the input data. Supported formats: 'default', 'llamafactory'.",
    )
    args = parser.parse_args()

    upload_dataset(args.file_path, args.dataset_name, data_format=args.data_format)


if __name__ == "__main__":
    main()
