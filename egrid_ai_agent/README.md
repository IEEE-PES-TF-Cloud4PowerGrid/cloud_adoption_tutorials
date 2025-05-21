# eGRID AI AGENT
<p align="center">
  <a href="./README.md/#solution-overview"><img src="https://img.shields.io/badge/AWS-Agentic_AI-orange" /></a>
  <a href="./README.md/#setup-for-agent"><img src="https://img.shields.io/badge/Amazon-Bedrock_Inline_Agent-orange" /></a>
</p>

An AI agent for electric power grid analysis

## Introduction
This is a sample agentic AI solution for function-calling various power system analysis tools through a RESTful service. The solution is built with [Amazon Bedrock Inline Agent SDK](https://github.com/awslabs/amazon-bedrock-agent-samples/tree/main/src/InlineAgent).

## Solution Overview
![soln_overview](img/soln_overview.png?raw=true "Architectural overview for the eGrid Agentic AI")

## Get Started
### Prerequisites

1. AWS Command Line Interface (CLI), follow instructions [here](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html). Make sure to setup credentials, follow instructions [here](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html).
2. Requires [Python 3.11](https://www.python.org/downloads/) or later.
3. Enable Amazon Bedrock [model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html).

> [!NOTE] 
> If you don't set up your AWS profile as instructed in step 1. An exception `botocore.exceptions.ProfileNotFound` will raise
> when you run `InlineAgent_hello` test below

### Setup for Agent

```bash
# Retrieve the Inline Agent SDK
git clone https://github.com/awslabs/amazon-bedrock-agent-samples.git
cd amazon-bedrock-agent-samples/src/InlineAgent

# Activate the virtual environment (install python virtualenv first if not installed)
python3 -m venv .venv
source .venv/bin/activate

# Install the SDK packages
python3 -m pip install -e .

# Test run; ensure you have access to Claude 3.5 Haiku model via Bedrock
InlineAgent_hello us.anthropic.claude-3-5-haiku-20241022-v1:0

# Retrieve the tutorial
git clone https://github.com/IEEE-PES-TF-Cloud4PowerGrid/cloud_adoption_tutorials.git
cd cloud_adoption_tutorials/egrid_ai_agent/

# Install dependencies for the sample
python3 -m pip install -e .
```

### Setup for eGrid Analysis RESTful Service
> [!NOTE] 
> You can host the RESTful service for various power system analysis tools either on your local machine or a remote server.
> If you run the RESTful service on a remote server, just ensure to replace `localhost` in **API_BASE_URL** with the server's public IP address or DNS hostname. Also make sure the server's TCP port 5000 is accessible from the machine where you run the agent, then copy the script `egrid_rest_service.py` to the remote server


```bash
# install dependencies
python3 -m pip install dss-python GridCalEngine flask flask_restful matplotlib
```


### Start the RESTful Service
```bash
python3 egrid_rest_service.py
```

### Run Bedrock Inline Agent to Interact with the REST APIs
```bash
python3 run_egrid_agent.py
```

## Expected Results
### Power Flow Analysis
Uncomment the line in `run_egrid_agent` script where the prompt is `Run power flow analysis for case IEEE14_from_raw.gridcal` to run the power flow analysis example. Note that you need to download the power flow case from GridCal project repo "Grids_and_Profiles/grids/" folder
![Agent Response PF](img/agent_resp_pf.png?raw=true "Agent Response for Prompt to Run Power Flow Analysis")

### Hosting Capacity Analysis
![Agent Response HCA](img/agent_resp_hca.png?raw=true "Agent Response for Prompt to Run Hosting Capacity Analysis")
![HCA Result](img/hca_res.png?raw=true "Visual Representation of Hosting Capacity Analysis Results")
