from InlineAgent.agent import InlineAgent
from InlineAgent.action_group import ActionGroup

import asyncio
import json
import requests
import botocore
from termcolor import colored

# Base URL for API endpoints
API_BASE_URL = "http://localhost:5000/api"   # if the RESTful service is hosted remotely, use either public IP address or the DNS hostname instead

# Foundation model candidates
FOUNDATION_MODELS = [
    "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "amazon.nova-micro-v1:0",
    "meta.llama4-scout-17b-instruct-v1:0"
]

# Create action group for making POST requests
def run_powerflow(case_name:str):
    """
    Run power flow analysis for a given case
    Parameters:
        case_name: The name of the power flow case file to analyze. Should include the file extension.
    Returns:
        Response data as string
    """
    
    url = f"{API_BASE_URL}/powerflow"
    request_data = {
        "case_name": case_name
    }
    response = requests.post(url, 
                             headers={'Content-Type': 'application/json'},
                             data=json.dumps(request_data))
    # Convert dictionary response to JSON string
    return json.dumps(response.json())

def run_hostcap(sim_hours:int):
    """
    Run hosting capacity analysis for a specified duration of hours
    Parameters:
        sim_hours: The number of hours you want to run the simulation
    Returns:
        Response data as string
    """
    
    url = f"{API_BASE_URL}/hostcap"
    request_data = {
        "sim_hours": sim_hours
    }
    response = requests.post(url, 
                             headers={'Content-Type': 'application/json'},
                             data=json.dumps(request_data)
                             )
    # Convert dictionary response to JSON string
    return json.dumps(response.json())

def get_hostcap_image(sim_hours:int):
    """
    Run hosting capacity analysis and get the generated image
    Parameters:
        sim_hours: The number of hours you want to run the simulation
    Returns:
        Path to saved image file
    """
    
    url = f"{API_BASE_URL}/hostcap/image"
    request_data = {
        "sim_hours": sim_hours
    }
    response = requests.post(url, 
                             headers={'Content-Type': 'application/json', 'Accept': 'image/png'},
                             data=json.dumps(request_data)
                             )
    
    if response.status_code == 200 or response.status_code == 201:
        # Save the image to a file
        image_path = "received_test_dss.png"
        with open(image_path, 'wb') as f:
            f.write(response.content)
        print(f"Image saved to {image_path}")
        return f"Image saved to {image_path}"
    else:
        return f"Error: {response.status_code}, {response.text}"

pf_actions = ActionGroup(
    name = "PFActionGroup", 
    description="This is action group to run power flow analysis",
    tools=[run_powerflow],
)

hc_actions = ActionGroup(
    name = "HCActionGroup",
    description="This is action group to run hosting capacity analysis",
    tools=[run_hostcap, get_hostcap_image],
)

# Initialize agent with API action group
agent = InlineAgent(
    foundation_model=FOUNDATION_MODELS[0],
    instruction="You are a power system analyst assistant that is able to run power flow analysis or hosting capacity analysis. You can also retrieve hosting capacity analysis images.",
    action_groups=[pf_actions, hc_actions],
    agent_name="eGridAgent")

def main():
    try:
    # user_input = input("Enter your power flow analysis request: ")
    # asyncio.run(agent.invoke(input_text=user_input))
    # asyncio.run(agent.invoke(input_text="Run power flow analysis for case IEEE14_from_raw.gridcal"))
        # Test regular hosting capacity analysis
        #asyncio.run(agent.invoke(input_text="Run DER hosting capacity analysis for 12 hours"))
        
        # Test getting the image from the hosting capacity analysis
        asyncio.run(agent.invoke(input_text="Run DER hosting capacity analysis for 12 hours and get the image"))
        #asyncio.run(agent.invoke(input_text="Run power flow analysis for case IEEE14_from_raw.gridcal"))
    except botocore.exceptions.ParamValidationError as e:
        if "ConnectionResetError" in str(e):
            print(
                colored("Connection reset error occurred. Please check if the service is up and the network connectivity is okay.\n" \
                "If you need to use SSH tunnel, please ensure the tunnel is up", "red")
            )
        else:
            print(
                colored(f"Other errors\n {str(e)}", "red")
            )

if __name__ == "__main__":
    main()
