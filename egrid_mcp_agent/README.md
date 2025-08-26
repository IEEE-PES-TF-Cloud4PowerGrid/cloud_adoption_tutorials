# eGRID MCP AGENT
This is an MCP version of the eGrid Agentic AI example
<p align="left">
  <a href="./README.md/#solution-overview"><img src="https://img.shields.io/badge/AWS-Agentic_AI-orange" /></a>
  <a href="./README.md/#setup-for-agent"><img src="https://img.shields.io/badge/Amazon-Bedrock_Inline_Agent-orange" /></a>
  <a href="./README.md/#setup-for-agent"><img src="https://img.shields.io/badge/MCP-FastMCP-blue" /></a>
</p>


## Introduction
This tutorial demonstrates an MCP agent implementation that integrates multiple power system analysis tools via an MCP server. The server utilizes [FastMCP](https://github.com/jlowin/fastmcp) for its foundation, while the client leverages the [Amazon Bedrock Inline Agent SDK](https://github.com/awslabs/amazon-bedrock-agent-samples/tree/main/src/InlineAgent). The example showcases tool integration using open source power system software such as [OpenDSS (DSS-Python)](https://github.com/dss-extensions/DSS-Python) and [GridCal](https://github.com/SanPen/GridCal) to illustrate the operational workflow.

## Solution Overview
![soln_overview](img/soln_overview.png?raw=true "Architectural overview for the eGrid Agentic AI harnessing MCP")

## Get Started
### Prerequisites

1. AWS Command Line Interface (CLI), follow instructions [here](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html). Make sure to setup credentials, follow instructions [here](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html).
2. Install [UV](https://docs.astral.sh/uv/getting-started/installation/)
3. Install [Python](https://docs.astral.sh/uv/guides/install-python/) 3.11 or above in UV
4. Enable Amazon Bedrock [model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html).

> [!NOTE] 
> If you don't set up your AWS profile as instructed in step 1. An exception `botocore.exceptions.ProfileNotFound` will raise
> when you run `InlineAgent_hello` test below

### Setup Agent for MCP Client

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
cd cloud_adoption_tutorials/egrid_mcp_agent/

# Install dependencies for the sample
python3 -m pip install -e .
```

### Setup for eGrid Analysis MCP Server
> [!NOTE] 
> You can host the MCP server for various power system analysis tools either on your local machine or a remote server.
> When deploying the MCP server on a remote machine, update the **API_BASE_URL** by substituting `localhost` with the server's public IP address or domain name.
> Verify that TCP port 8000 is open and reachable from the machine running the agent, then transfer the `egrid_mcp_server.py` script to the remote server.


```bash
# install dependencies
uv add dss-python GridCalEngine numpy matplotlib "fastmcp>=0.1.0"
```


### Start the MCP Server
```bash
uv run egrid_mcp_server.py
```

### Run MCP client built with Bedrock Inline Agent to Interact with MCP Server
```bash
python3 run_egrid_agent_mcp_client.py
```

## Expected Results
### Power Flow Analysis
You need to download the power flow cases from GridCal project repo ["Grids_and_Profiles/grids/"](https://github.com/SanPen/GridCal/tree/master/Grids_and_profiles) folder

![Agent Response PF](img/agent_resp_pf.png?raw=true "Agent Response for Prompt to Run Power Flow Analysis")
<p align=center>Agent Response for Prompt to Run Power Flow Analysis</p>

![MCP Server Response PF](img/mcp_resp_pf.png?raw=true "MCP Server Response for Prompt to Run Power Flow Analysis")
<p align=center>MCP Server Response for Prompt to Run Power Flow Analysis</p>
