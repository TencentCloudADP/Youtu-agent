
# How to Evaluate an Agent

This guide walks you through the complete process of evaluating an agent in Youtu-Agent, from implementation to analysis.

## Prerequisites

Before you begin, ensure that:

1. **Environment is set up**: You've completed the [Getting Started](https://tencentcloudadp.github.io/youtu-agent/quickstart/) setup
2. **Database is configured**: The `UTU_DB_URL` environment variable is set in your `.env` file (defaults to `sqlite:///test.db`)
3. **API keys are configured**: `UTU_LLM_API_KEY` and other required keys are set in `.env`

## Overview

The evaluation process consists of four main steps:

1. **Implement and debug your agent** - Test your agent interactively
2. **Prepare evaluation dataset** - Create and upload test cases
3. **Run evaluation** - Execute automated evaluation
4. **Analyze results** - Review performance using the analysis dashboard

## Step 1: Implement and Debug Your Agent

Before running formal evaluations, you should implement and test your agent interactively to ensure it works as expected.

### 1.1 Create Agent Configuration

Create an agent configuration file in `configs/agents/`. For example, `configs/agents/examples/svg_generator.yaml`:

```yaml
# @package _global_
defaults:
  - /model/base@orchestrator_model
  - /agents/router/force_plan@orchestrator_router
  - /agents/simple/search_agent@orchestrator_workers.SearchAgent
  - /agents/simple/svg_generator@orchestrator_workers.SVGGenerator
  - _self_

type: orchestrator

orchestrator_config:
  name: SVGGeneratorAgent
  add_chitchat_subagent: false
  additional_instructions: |-
    Your main objective is generating SVG code according to user's request.

orchestrator_workers_info:
  - name: SearchAgent
    description: Performs focused information retrieval
  - name: SVGGenerator
    description: Creates SVG cards
```

### 1.2 Test Interactively

Run the CLI chat interface to verify your agent works correctly:

```bash
python scripts/cli_chat.py --config examples/svg_generator
```

Try various inputs and verify the agent's responses meet your expectations. Debug and refine your agent configuration as needed.

## Step 2: Prepare Evaluation Dataset

Once your agent is working, create a dataset of test cases for evaluation.

### 2.1 Create Dataset File

Create a JSONL file (e.g., `data/svg_gen.jsonl`) where each line is a JSON object with your test case. Two data formats are supported:

**Format 1: LLaMA Factory format** (recommended for SFT data):

```jsonl
{"instruction": "Research Youtu-Agent and create an SVG summary"}
{"instruction": "Introduce the data formats in LLaMA Factory"}
{"instruction": "Summarize how to use Claude Code"}
{"input": "https://docs.claude.com/en/docs/claude-code/skills"}
{"input": "Please introduce Devin coding agent"}
{"instruction": "Summarize the following content", "input": "# Model Context Protocol servers\n\nThis repository is a collection of reference implementations..."}
{"input": "https://arxiv.org/abs/2502.05957"}
{"input": "https://github.com/microsoft/agent-lightning"}
{"input": "Summarize resources about MCP"}
{"input": "https://huggingface.co/papers/2510.19779"}
```

In LLaMA Factory format:
- `instruction` and/or `input` fields are combined to create the question
- `output` field (if present) becomes the ground truth answer

**Format 2: Default format**:

```jsonl
{"question": "What is Youtu-Agent?", "answer": "A flexible agent framework"}
{"question": "How to install?", "answer": "Run uv sync"}
```

### 2.2 Upload Dataset to Database

Upload your dataset using the `upload_dataset.py` script:

```bash
python scripts/data/upload_dataset.py \
  --file_path data/svg_gen.jsonl \
  --dataset_name example_svg_gen \
  --data_format llamafactory
```

**Parameters:**
- `--file_path`: Path to your JSONL file
- `--dataset_name`: Name to assign to this dataset in the database
- `--data_format`: Either `llamafactory` or `default`

The script will parse your JSONL file and store the test cases in the database. You should see output like:

```
Uploaded 10 datapoints from data/svg_gen.jsonl to dataset 'example_svg_gen'.
Upload complete.
```

## Step 3: Run Evaluation

Now run your agent on the evaluation dataset.

### 3.1 Create Evaluation Configuration

Create an evaluation config file in `configs/eval/examples/`. For example, `configs/eval/examples/eval_svg_generator.yaml`:

```yaml
# @package _global_
defaults:
  - /agents/examples/svg_generator@agent
  - _self_

exp_id: "example_svg_gen"

data:
  dataset: example_svg_gen

concurrency: 16
```

**Key fields:**
- `defaults`: Reference your agent configuration
- `exp_id`: Unique identifier for this evaluation run
- `data.dataset`: Name of the dataset you uploaded
- `concurrency`: Number of parallel evaluation tasks

### 3.2 Run the Evaluation Script

Execute the evaluation:

```bash
python scripts/run_eval.py \
  --config_name examples/eval_svg_generator \
  --exp_id example_svg_gen \
  --dataset example_svg_gen \
  --step rollout
```

**Parameters:**
- `--config_name`: Name of your eval config (without `.yaml` extension)
- `--exp_id`: Unique identifier for this evaluation run
- `--dataset`: Name of the dataset to evaluate on
- `--step`: Evaluation step to run
  - `rollout`: Run the agent on all test cases (collect trajectories)
  - `judge`: Evaluate the agent's outputs (requires ground truth answers)
  - `all`: Run both rollout and judge steps

**Note:** Use `--step rollout` when your dataset doesn't have ground truth answers (GT). If you have GT answers, you can run `--step all` or run judge separately:

```bash
# Run judge separately (requires rollout to be completed first)
python scripts/run_eval_judge.py \
  --config_name examples/eval_svg_generator \
  --exp_id example_svg_gen
```

### 3.3 Monitor Progress

During evaluation, you'll see progress indicators:

```
> Loading dataset 'example_svg_gen'...
> Found 10 test cases
> Starting rollout with concurrency 16...
[1/10] Processing: Research Youtu-Agent...
[2/10] Processing: Introduce LLaMA Factory...
...
> Evaluation complete. Results saved to database.
```

## Step 4: Analyze Results

After evaluation completes, analyze the results using the web-based analysis dashboard.

### 4.1 Set Up Analysis Dashboard

The evaluation analysis dashboard is a Next.js application located in `frontend/exp_analysis/`.

**First-time setup:**

```bash
cd frontend/exp_analysis

# Install dependencies
npm install --legacy-peer-deps

# Build the application
npm run build
```

### 4.2 Start the Dashboard

```bash
# Make sure you're in frontend/exp_analysis/
npm run start
```

The dashboard will be available at `http://localhost:3000` by default.

**Change the port** (optional):
Edit `package.json` and modify the start script:

```json
"scripts": {
  "start": "next start -p 8080"
}
```

### 4.3 View Evaluation Results

Open your browser and navigate to `http://localhost:3000`. The dashboard provides:

- **Overview**: Summary statistics for your evaluation runs
- **Experiment Comparison**: Compare multiple evaluation runs side-by-side
- **Detailed Trajectories**: Inspect individual agent execution traces
- **Success/Failure Analysis**: Identify patterns in successful vs. failed cases
- **Performance Metrics**: Accuracy, latency, token usage, etc.

**Key features:**
- Filter by experiment ID, dataset, or date range
- View full agent trajectories including tool calls and reasoning steps
- Export results for further analysis
- Compare different agent configurations

### 4.4 Verify Database Connection

If you encounter issues, test the database connection:

```bash
cd frontend/exp_analysis
npm run test:db
```

This will verify that the dashboard can connect to your database and retrieve evaluation data.

## Advanced Topics

### Evaluating on Standard Benchmarks

To evaluate on standard benchmarks like WebWalkerQA or GAIA:

```bash
# Prepare benchmark dataset (one-time setup)
python scripts/data/process_web_walker_qa.py

# Run evaluation on WebWalkerQA
python scripts/run_eval.py \
  --config_name ww \
  --exp_id my_ww_run \
  --dataset WebWalkerQA_15 \
  --concurrency 5
```

For GAIA, first accept the access conditions on the
[official dataset page](https://huggingface.co/datasets/gaia-benchmark/GAIA), set `HF_TOKEN`, and then run:

```bash
# Download the current Parquet-backed dataset and import the validation split
python scripts/data/process_gaia.py

# Run evaluation on the full official validation split
python scripts/run_eval.py \
  --config_name gaia \
  --exp_id my_gaia_run \
  --dataset GAIA_validation \
  --concurrency 5
```

The 72.8% result reported in the README uses the linked text-only validation subset. The command above imports the
full official validation split, including rows with attachments.

See the [Evaluation Documentation](https://tencentcloudadp.github.io/youtu-agent/eval) for more details on benchmarks.

### Configuring Judge Models

For evaluations with ground truth, configure judge models in your eval config:

```yaml
judge_model:
  model_provider:
    type: ${oc.env:JUDGE_LLM_TYPE}
    model: ${oc.env:JUDGE_LLM_MODEL}
    base_url: ${oc.env:JUDGE_LLM_BASE_URL}
    api_key: ${oc.env:JUDGE_LLM_API_KEY}
  model_params:
    temperature: 0.5
judge_concurrency: 16
```

Set the corresponding environment variables in your `.env` file:

```bash
JUDGE_LLM_TYPE=chat.completions
JUDGE_LLM_MODEL=deepseek-chat
JUDGE_LLM_BASE_URL=https://api.deepseek.com/v1
JUDGE_LLM_API_KEY=your-judge-api-key
```
