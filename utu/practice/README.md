# Agent Practice Powered by Training-Free GRPO
<a href=https://arxiv.org/abs/2510.08191><img src=https://img.shields.io/badge/arXiv-2510.08191-b31b1b.svg></a>

This module provides the core functionality for agent practice within the Youtu-Agent framework, implemented with Training-Free Group Relative Policy Optimization (GRPO). 
Training-Free GRPO is a cost-effective solution that enhances agent performance without any LLM parameter updates by leveraging group relative semantic advantages and iteratively distilling high-quality experiential knowledge.

## 📁 Module Structure

```
utu/practice/
├── __init__.py                 # Module exports
├── training_free_grpo.py       # Main orchestrator
├── rollout_manager.py          # Rollout execution and batch processing
├── experience_updater.py       # Experience processing and integration
├── data_manager.py             # Dataset management
├── utils.py                    # Configuration parsing and utilities detailed below
├── dataset/                    # Dataset storage directory
└── verify/                     # Verification functions
```

**Configurations**:
The system uses a hierarchical configuration approach:
`TrainingFreeGRPOConfig` loaded from config files in `configs/practice/` directory. It is a unified configuration class with experiment ID and references to the following practice, data, and evaluation configs:
- `PracticeArguments`: Practice-specific parameters (epochs, batch size, GRPO settings, restart behavior)
- `DataArguments`: Data processing parameters like practice dataset name
- `EvalConfig`: Evaluation configuration loaded separately from configuration files in `configs/eval/` directory

**Utilities:**

- `TaskRecorder`: Records practice progress, experiences, and statistics
- `parse_training_free_grpo_config()`: Configuration parser supporting YAML files with command-line overrides

## 🚀 Usage

Here are step-by-step instructions to run the training-free GRPO process for agent practice and evaluation.
Please follow each step carefully to ensure proper setup and execution.
For built-in example workflows on math reasoning and web searching, please refer to the [📝 Example Workflows](#-example-workflows).

### Step 0. Environment Setup

Please refer to the [QuickStart](https://tencentcloudadp.github.io/youtu-agent/quickstart/) documentation for environment setup and installation of Youtu-Agent framework. If you are new to Python, please refer to [Beginner's QuickStart Guide](https://tencentcloudadp.github.io/youtu-agent/quickstart_beginner/) for detailed instructions. 

Please install all dependencies by:
```bash
uv sync --all-extras
source .venv/bin/activate
```

For tracing and monitoring the practice and evaluation process, you can enable Phoenix tracing by following the [Tracing & Monitoring Documentation](https://tencentcloudadp.github.io/youtu-agent/environment_variables/#tracing-monitoring). For simplicity, you can start a local Phoenix server by running:

```bash
pip install arize-phoenix
phoenix serve

# Remember to set the environment variables in a `.env` file at the project root:
# PHOENIX_ENDPOINT=http://127.0.0.1:6006/v1/traces
# PHOENIX_PROJECT_NAME=Youtu-Agent
```

### Step 1. Data Preparation

Before running the training-free GRPO process, you need to prepare your datasets for practice and evaluation by uploading them to the local database. There are two ways to upload and prepare data:

#### Option 1: Upload Datasets from HuggingFace

If you want to load datasets from HuggingFace to the database, you can reference the provided example script, `scripts/data/process_training_free_GRPO_data.py`. You can use this script directly for our built-in datasets, or adapt it to create your own upload code for other HuggingFace datasets:

```bash
# Example: Load built-in datasets for reproducing paper experiments
python scripts/data/process_training_free_GRPO_data.py
```

This example script will download and upload the following built-in datasets to the local database:
- AIME24: AIME 2024 competition problems
- AIME25: AIME 2025 competition problems  
- DAPO-Math-17k: 17k math problems from DAPO dataset
- AFM_web_RL: Web agent reinforcement learning dataset
- WebWalkerQA: Web navigation and answering dataset

**Important**: When uploading datasets, make sure that each `DatasetSample` includes the required fields: `dataset`, `source`, `question`, and `answer`, specifically, ensure to **set the `source` field as `"training_free_grpo"`** for proper data processing.

#### Option 2: Upload Custom Local Datasets

If you want to use your own custom datasets, you can upload them from local files using the upload script:

```bash
# Upload custom dataset from local file
python scripts/data/upload_dataset.py \
  --file_path path/to/your_dataset.jsonl \
  --dataset_name YourDataset
```

**Important**: Ensure your local data file contains samples with all required fields: `dataset`, `source`, `question`, and `answer`. Each sample should be a dictionary with the following structure:

```json
{
    "dataset": "YourDataset",       # Name of your dataset
    "source": "training_free_grpo", # Must be "training_free_grpo" for both practice and evaluation data
    "question": "What is 2+2?",     # The question or prompt
    "answer": "4"                   # The expected answer, set to None if not applicable
}
```

### Step 2. Setup the Verification Functions

Training-Free GRPO features a flexible and configurable reward calculation system through customizable verification functions. This modular design allows you to define domain-specific evaluation criteria that accurately assess agent performance across diverse tasks, ranging from mathematical reasoning requiring symbolic verification to web search tasks needing semantic understanding with LLMs.

#### Verification Function Interface

Verification functions must be placed in the `utu/practice/verify/` directory and follow this interface:

```python
from utu.db import EvaluationSample

def verify_func(sample: EvaluationSample, timeout_score: float = 0, **kwargs) -> dict:
    """
    Verify the correctness of an agent response.
    
    Args:
        sample: EvaluationSample containing:
            - raw_question: The original question, corresponding to the `question` field in DatasetSample
            - correct_answer: Ground truth answer, corresponding to the `answer` field in DatasetSample
            - response: Agent's final response to evaluate
            - other metadata fields
        timeout_score: Score to assign when verification times out
        **kwargs: Additional arguments passed by the processor, including:
            - llm: LLM client for verification that requires LLM judgment, please refer to `utu/practice/verify/webwalker.py` for example usage.
        
    Returns:
        dict: {
          "reward": float,          # ranges from 0.0 to 1.0
          "reasoning": str | None   # extra details provided for experience extraction in training-free GRPO
        }
    """
    # Your verification logic here
    pass
```

#### Built-in Verification Functions

The module provides two built-in verification functions for reproducing paper results:

1. Math Verification (`utu/practice/verify/math.py`)
- Verification function: `verify_func` 
- Purpose: Evaluates mathematical problem solutions using symbolic math verification
- Dependencies: Requires `math_verify` package for expression extraction and comparison
- Logic: Compares extracted mathematical expressions from agent response with ground truth using both LaTeX and expression extraction

2. Web Search Verification (`utu/practice/verify/webwalker.py`)
- Verification function: `verify_func` 
- Purpose: Evaluates web search task responses using LLM-based judgement
- Logic: Uses an LLM judge (passed via `llm` parameter in kwargs) to compare agent response with ground truth

#### Custom Verification Functions

To create custom verification functions:

1. Create a Python file in `utu/practice/verify/`
2. Implement a function matching the interface above. If LLM is needed, use kwargs['llm'] to access the LLM client. Refer to `utu/practice/verify/webwalker.py` for example.
3. Add any required dependencies to your environment (e.g., `uv pip install <package_name>`)

Example for a simple string matching verifier:

```python
# utu/practice/verify/str_match.py
from utu.db import EvaluationSample

def string_match_verify(sample: EvaluationSample, timeout_score: float = 0, **kwargs) -> dict:
    """Simple string matching verification."""
    if sample.correct_answer.lower() == sample.response.lower():
        return {"reward": 1.0, "reasoning": None}
    return {"reward": 0.0, "reasoning": None}
```

### Step 3. Prepare Configurations

The Training-Free GRPO module uses a hierarchical configuration system that prioritizes YAML configuration files.
There are three main configuration directories, in which you can find built-in configurations or create your own custom configurations:
```
configs/agents/                     # For agent configurations
├── practice/                       # Built-in simple agents for practice
│   ├── math_agent.yaml             # Built-in math agent config
│   ├── math_practice_agent.yaml    # Built-in math agent config after practice via training-free GRPO
│   ├── web_agent.yaml              # Built-in web search agent config
│   └── web_practice_agent.yaml     # Built-in web search agent config after practice via training-free GRPO

configs/eval/                       # For evaluation configurations
├── math/                         
│   ├── math_AIME24.yaml            # Built-in math evaluation settings for AIME24
│   ├── math_AIME25.yaml            # Built-in math evaluation settings for AIME25
│   ├── math_practice_AIME24.yaml   # Built-in math evaluation settings for AIME24 after practice via training-free GRPO
│   └── math_practice_AIME25.yaml   # Built-in math evaluation settings for AIME25 after practice via training-free GRPO
├── web/                         
│   ├── web.yaml                    # Built-in web evaluation settings for WebWalkerQA
│   └── web_practice.yaml           # Built-in web evaluation settings for WebWalkerQA after practice via training-free GRPO

configs/practice/                   # For practice configurations
├── math_reasoning.yaml             # Built-in configs for math practice
├── web_search.yaml                 # Built-in configs for web search practice
```

#### Agent Configuration

Ensure you have an agent configuration file in `configs/agents/practice` directory. You can use built-in agents or create your own custom agent configuration. For more details, please refer to [Agent Configuration](https://tencentcloudadp.github.io/youtu-agent/agents/).

#### Evaluation Configuration

Please create the evaluation configuration file in `configs/eval/my_domain` directory:
```yaml
# configs/eval/my_domain/my_eval.yaml
# @package _global_
defaults:
  - /agents/practice/my_agent@agent         # Reference your agent config
  - _self_

exp_id: "my_eval"                           # Experiment ID for evaluation

# Evaluation dataset configuration
data:
  dataset: "MyEvalDataset"                  # Name of evaluation dataset in database
  type: "single"                            # Dataset type

# Evaluation settings
concurrency: 64                             # Parallel evaluation processes
pass_k: 3                                   # Pass@K evaluation metric

# Verification function settings
verify_filename: "my_verify.py"             # Custom verification function file
verify_func_name: "my_verify_func"          # Function name in the file

# Optional: Custom judge model settings for LLM-based verification
judge_model:
  model_provider:
    type: ${oc.env:JUDGE_LLM_TYPE}          # define in environment variable (.env) for security
    model: ${oc.env:JUDGE_LLM_MODEL}        # define in environment variable (.env) for security
    base_url: ${oc.env:JUDGE_LLM_BASE_URL}
    api_key: ${oc.env:JUDGE_LLM_API_KEY}
  model_params:
    temperature: 0.5
```

#### Practice Configuration

Please create practice configuration** in `configs/practice/` directory:
```yaml
# configs/practice/my_practice.yaml
# @package _global_
defaults:
  - /eval/my_domain/my_eval@evaluation          # Reference your evaluation config
  - _self_

exp_id: "my_practice"                           # Experiment ID for practice

# Practice Arguments
practice:
  epochs: 5                                     # Number of epochs for practice
  batch_size: 32                                # Samples per batch
  grpo_n: 3                                     # Rollouts per GRPO group
  rollout_concurrency: 64                       # Parallel rollout processes
  rollout_temperature: 0.7                      # LLM temperature during rollouts
  task_timeout: 3600                            # Timeout per task (seconds)
  do_eval: false                                # Enable evaluation during Training-Free GRPO
  eval_strategy: "epoch"                        # Evaluate at end of each epoch / step, unused if do_eval is false
  restart_step: null                            # Use cache for all steps
  agent_objective: |                            # Briefly introduce the working agent to the learning process for experience extraction. Here is an example for a math reasoning agent:
    input: A math question that could falls into any areas of mathematics
    output: A step-by-step reasoning process that leads to the final answer
  learning_objective: |                         # Briefly describe the learning goal and expected experiences for the practice process. Here is an example for a math reasoning agent:
    Help the agent to improve the solving capability on math questions by extracting general and concise guidelines.
  num_experiences_per_query: 1                  # Number of experiences to extract per query

# Data Arguments  
data:
  practice_dataset_name: "MyPracticeDataset"    # Name of practice dataset in database
```

### Step 4. Evaluating Baseline

After preparation is complete, use the `scripts/run_eval.py` script with configuration files to evaluate the baseline agent before training-free GRPO:

```bash
python scripts/run_eval.py \
  --config_name my_domain/my_eval   # Your evaluation config name
```

### Step 5. Run Training-Free GRPO

After evaluating the baseline, we can proceed to the training-free GRPO process. The system now primarily uses YAML configuration files located in `configs/practice/` directory, with optional command-line parameter overrides:

```bash
# Using the configuration file
python scripts/run_training_free_GRPO.py \
  --config_name my_practice   # Your practice config name

# Using configuration file with custom parameter overrides the config
python scripts/run_training_free_GRPO.py \
    --config_name my_practice \
    --experiment_name my_practice \
    --epochs 5 \
    --batch_size 64
```

To control the restart behavior and caching mechanism, use the `--restart_step` argument:

```bash
# Complete restart (no caching)
python scripts/run_training_free_GRPO.py \
    --config_name my_practice \
    --restart_step 0

# Resume from cached results (default behavior)
python scripts/run_training_free_GRPO.py \
    --config_name my_practice \
    --restart_step null

# Partial restart: use cache for steps 0-2, restart from step 3
python scripts/run_training_free_GRPO.py \
    --config_name my_practice \
    --restart_step 3
```

The practice process will generates:
1. **Enhanced Agent Configuration**: A new YAML file with integrated experiences
2. **Tracing Logs**: A detailed log of the training-free GRPO process and progress through Phoenix if enabled, including the following key metrics:
   - The detailed trajectories during rollouts
   - The step-by-step outputs of experience extraction
   - The extracted experiences and the statistics at each step
   - Evaluation performance (if `do_eval` is enabled) at each epoch or step
3. **Experience Records**: Structured records of learned experiences in the database (configurable in the environment variables of `.env` file)

### Step 6. Evaluate the Enhanced Agent

When practice completes, you'll receive a path to the enhanced agent configuration file (e.g., `configs/agents/practice/my_practice_agent.yaml`).
Next, you can evaluate the enhanced agent configuration on your evaluation datasets. Similarly, create a new evaluation configuration file that references the enhanced agent configuration:

```yaml
# configs/eval/my_domain/my_practice.yaml
# @package _global_
defaults:
  - /agents/practice/my_practice_agent@agent  # Use your enhanced config after practice
  - _self_

exp_id: "my_practice_eval"

# Evaluation dataset configuration
data:
  dataset: "MyEvalDataset"                    # Name of evaluation dataset in database
  type: "single"                              # Dataset type

# Evaluation settings
concurrency: 64                               # Parallel evaluation processes
pass_k: 3                                     # Pass@K evaluation metric

# Verification function settings
verify_filename: "my_verify.py"               # Custom verification function file
verify_func_name: "my_verify_func"            # Function name in the file

# Optional: Custom judge model settings for LLM-based verification
judge_model:
  model_provider:
    type: ${oc.env:JUDGE_LLM_TYPE}            # define in environment variable (.env) for security
    model: ${oc.env:JUDGE_LLM_MODEL}          # define in environment variable (.env) for security
    base_url: ${oc.env:JUDGE_LLM_BASE_URL}
    api_key: ${oc.env:JUDGE_LLM_API_KEY}
  model_params:
    temperature: 0.5
```

Then run the evaluation with the enhanced agent configuration:
```bash
python scripts/run_eval.py \
  --config_name my_domain/my_practice     # Your evaluation config name for the enhanced agent
```

## 📝 Example Workflows

### Math Reasoning

**Step 0. Environment Setup**:
Besides the common environment setup in [Step 0](#step-0-environment-setup), please install the `math-verify` package for math verification:
```bash
uv pip install math-verify
```

**Step 1. Data Preparation**:
Use built-in datasets.
```bash
python scripts/data/process_training_free_GRPO_data.py
```

**Step 2. Setup the Verification Functions**:
The built-in math verification function is already provided in `utu/practice/verify/math.py`.

**Step 3. Prepare Configurations**:
For `deepseek-chat` LLM from DeepSeek official API, you can use the built-in math agent, evaluation and practice configurations, i.e., `configs/agents/practice/math_agent.yaml`, `configs/eval/math/*.yaml` and `configs/practice/math_reasoning.yaml`, respectively. Note that for different LLMs, the optimal configurations may vary. You can try to modify these configuration accordingly.

**Step 4. Evaluating Baseline**:
Use the built-in math evaluation configuration.
```bash
python scripts/run_eval.py --config_name math/math_AIME24
python scripts/run_eval.py --config_name math/math_AIME25
```

**Step 5. Run Training-Free GRPO**:
Use the built-in math reasoning practice configuration.
```bash
python scripts/run_training_free_GRPO.py --config_name math_reasoning
```
After practice, the enhanced agent configuration will be automatically saved as `configs/agents/practice/math_practice_agent.yaml`.

**Step 6. Evaluate the Enhanced Agent**:
Use the built-in math evaluation configuration with the enhanced agent.
```bash
python scripts/run_eval.py --config_name math/math_practice_AIME24
python scripts/run_eval.py --config_name math/math_practice_AIME25
```

### Web Searching

**Step 0. Environment Setup**:
Besides the common environment setup in in [Step 0](#step-0-environment-setup), please set up additional environment variables in `.env` for web search APIs (e.g., Serper, Jina).
```bash
SERPER_API_KEY=replace-with-your-serper-api-key
JINA_API_KEY=replace-with-your-jina-api-key
```

**Step 1. Data Preparation**:
Use built-in datasets.
```bash
python scripts/data/process_training_free_GRPO_data.py
```

**Step 2. Setup the Verification Functions**:
The built-in web search verification function is already provided in `utu/practice/verify/webwalker.py`.

**Step 3. Prepare Configurations**:
To run with DeepSeek-V3.2-Exp, you can use the built-in web search agent, evaluation and practice configurations, i.e., `configs/agents/practice/web_agent.yaml`, `configs/eval/web/web.yaml` and `configs/practice/web_search.yaml`, respectively. Note that for different LLMs, the optimal configurations may vary. You can try to modify these configuration accordingly.

**Step 4. Evaluating Baseline**:
Use the built-in web evaluation configuration.
```bash
python scripts/run_eval.py --config_name web/web
```

**Step 5. Run Training-Free GRPO**:
Use the built-in web searching practice configuration.
```bash
python scripts/run_training_free_GRPO.py --config_name web_search
```
After practice, the enhanced agent configuration will be automatically saved as `configs/agents/practice/web_practice_agent.yaml`.

**Step 6. Evaluate the Enhanced Agent**:
Use the built-in web evaluation configuration with the enhanced agent.
```bash
python scripts/run_eval.py --config_name web/web_practice
```

## 📚 Citation

If you find this work useful, please consider citing:

```bibtex
@misc{training_free_grpo,
      title={Training-Free Group Relative Policy Optimization}, 
      author={Tencent Youtu Lab},
      year={2025},
      eprint={2510.08191},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2510.08191}, 
}

@misc{youtu-agent-2025,
  title={Youtu-agent: A Simple yet Powerful Agent Framework},
  author={Tencent Youtu Lab},
  year={2025},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/TencentCloudADP/youtu-agent}},
}
```
