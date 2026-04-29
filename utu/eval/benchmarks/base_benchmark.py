import asyncio
import json
import time

from agents import gen_trace_id, trace
from tqdm import tqdm

from ...agents import get_agent
from ...config import ConfigLoader, EvalConfig
from ...utils import AgentsUtils, get_logger
from ..data import DBDataManager, EvaluationSample
from ..processer import PROCESSER_FACTORY, BaseProcesser

logger = get_logger(__name__, "INFO")


class BaseBenchmark:
    """Base class for benchmarks.

    Evaluation phases:
      - preprocess: load and preprocess the data
      - rollout: rollout the predictions
      - judge: judge the correctness of a batch of predictions
      - stat: get metrics.
    """

    dataset: DBDataManager
    _source_to_processer: dict[str, BaseProcesser] = {}

    def __init__(self, config: EvalConfig | str) -> None:
        # config
        if isinstance(config, str):
            config = ConfigLoader.load_eval_config(name=config)
        self.config = config

        # dataset
        self.dataset = DBDataManager(config)
        _samples = self.dataset.load()
        if len(_samples) == 0:
            raise ValueError(f"No samples found for data config '{self.config.data}'! Please check the data config.")

    async def main(self):
        with trace(f"[{self.config.exp_id}] Evaluation", trace_id=gen_trace_id()):
            logger.info(
                f"> Running with config: \n{json.dumps(self.config.model_dump(), indent=2, ensure_ascii=False)}"
            )
            self.preprocess()
            await self.rollout()
            await self.judge()
            logger.info("> Running stat...")
            await self.stat()
            logger.info("> Cleaning up...")
            await self.cleanup()

    def preprocess(self) -> None:
        """Preprocess the dataset before rollout."""
        samples = self.dataset.get_samples(stage="init")
        logger.info(f"Preprocessing {len(samples)} samples...")
        results = []
        for sample in tqdm(samples, desc="Preprocessing"):
            processed_sample = self.preprocess_one(sample)
            if processed_sample is not None:
                results.append(processed_sample)
        logger.info(f"Successfully preprocessed {len(results)} samples. Updated to db.")
        return results

    def preprocess_one(self, sample: EvaluationSample) -> EvaluationSample:
        processer = self._get_processer(sample.source)
        processed_sample = processer.preprocess_one(sample)
        if processed_sample is None:
            return None
        self.dataset.save(processed_sample)
        return processed_sample

    async def rollout(self, max_retries: int = 3) -> None:
        """Rollout the datapoints."""
        samples = self.dataset.get_samples(stage="init")
        logger.info(f"Rollout {len(samples)} samples...")

        semaphore = asyncio.Semaphore(self.config.concurrency)

        async def rollout_with_semaphore(item: EvaluationSample):
            async with semaphore:
                for i in range(max_retries):
                    if i > 0:
                        logger.warning(f"Retrying rollout for sample '{item.raw_question}', attempt {i + 1}")
                    try:
                        return await self.rollout_one(item)
                    except Exception as e:  # pylint: disable=broad-except
                        logger.error(
                            f">>>>>>>>>>>>>\nError running rollout on sample '{item.raw_question}': {e}\n<<<<<<<<<<<<<",
                            exc_info=True,
                        )

        tasks = [rollout_with_semaphore(item) for item in samples]
        results = []
        for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Rolling out"):
            result = await task
            if result is not None:
                results.append(result)
        logger.info(f"Successfully rollout {len(results)} samples. Updated to db.")
        return results

    async def rollout_one(self, sample: EvaluationSample) -> EvaluationSample:
        agent = get_agent(self.config.agent)
        if hasattr(agent, "build"):  # hack, should be removed!
            await agent.build()
        trace_id = AgentsUtils.gen_trace_id()
        start_time = time.time()
        result = await agent.run(sample.augmented_question, trace_id=trace_id)
        end_time = time.time()

        # Update the sample with the predicted answer and trajectory
        sample.update(
            trace_id=trace_id,
            response=result.final_output,
            time_cost=end_time - start_time,
            trajectories=json.dumps(result.trajectories, ensure_ascii=False),
            stage="rollout",  # update stage to rollout!
        )
        self.dataset.save(sample)
        return sample

    async def judge(self, stage: str | None = "rollout") -> list[EvaluationSample]:
        """Judge samples.

        Args:
            stage (str|None, optional): The stage of samples to judge. If set to None, you can rejudge all samples.
        """
        if stage == "rollout":
            num_init_samples = len(self.dataset.get_samples(stage="init"))
            if num_init_samples > 0:
                logger.error(
                    f"There are {num_init_samples} samples might failed unexpectedly in rollout stage."
                    "Please rerun the benchmarking to continue for final results."
                )
                exit(1)
        samples = self.dataset.get_samples(stage=stage)
        logger.info(f"Judging {len(samples)} samples...")

        semaphore = asyncio.Semaphore(self.config.judge_concurrency)

        async def judge_with_semaphore(item: EvaluationSample):
            async with semaphore:
                try:
                    return await self.judge_one(item)
                except Exception as e:  # pylint: disable=broad-except
                    logger.error(f">>>>>>>>>>>>>\nError judging sample '{item}': {e}\n<<<<<<<<<<<<<", exc_info=True)
                    return None

        tasks = [judge_with_semaphore(item) for item in samples]
        results = []
        for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Judging"):
            result = await task
            if result is not None:
                results.append(result)
        logger.info(f"Successfully judged {len(results)} samples. Updated to db.")
        return results

    async def judge_one(self, data: EvaluationSample) -> EvaluationSample:
        judger = self._get_processer(data.source)
        result = await judger.judge_one(data)
        result.update(stage="judged")  # update stage to judged
        self.dataset.save(result)
        return result

    async def stat(self) -> list[dict]:
        # TODO: wrap the data like @verl / @torch
        # TODO: log to wandb
        judged_samples = self.dataset.get_samples(stage="judged")
        logger.info(f"Stat from {len(judged_samples)} samples:")

        data_by_benchmark = self._group_data_by_benchmark(judged_samples)
        overall_results: list[dict] = []
        for benchmark, data in data_by_benchmark.items():
            evaluator = self._get_processer(benchmark)
            result = await evaluator.stat(data)
            overall_results.append(result)

        logger.info(json.dumps(overall_results, indent=4, ensure_ascii=False))
        return overall_results

    def _get_processer(self, source: str) -> BaseProcesser:
        if source not in self._source_to_processer:
            processer = PROCESSER_FACTORY.get(source, self.config)
            self._source_to_processer[source] = processer
        return self._source_to_processer[source]

    def _group_data_by_benchmark(self, predict_data: list[EvaluationSample]) -> dict[str, list[EvaluationSample]]:
        # group data by benchmark
        data_by_benchmark: dict[str, list[EvaluationSample]] = {}
        for data in predict_data:
            benchmark = data.source
            if benchmark not in data_by_benchmark:
                data_by_benchmark[benchmark] = []
            data_by_benchmark[benchmark].append(data)
        return data_by_benchmark

    async def cleanup(self):
        pass
