#!/usr/bin/env python3
"""
Bedrock Agent with remote MCP server integration via Streamable HTTP
"""

from InlineAgent.agent import InlineAgent
from InlineAgent.action_group import ActionGroup
import aiohttp
import asyncio
import json
import random
import uuid
from typing import Dict, Any, Optional, List

# Foundation model candidates 
FOUNDATION_MODELS = [
    "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "amazon.nova-micro-v1:0",
    "meta.llama4-scout-17b-instruct-v1:0"
]

class MCPHttpClient:
    def __init__(self, server_url, timeout: int = 30):
        self.server_url = server_url
        self.session = None
        self.session_id = None
        self.request_id = 0
        self.timeout = timeout

    def _get_next_request_id(self) -> int:
        """Generate next request ID for JSON-RPC."""
        self.request_id += 1
        return self.request_id
    
    async def _make_request(self, method: str, params: Dict[str, Any] = None, 
                     notification: bool = False) -> Optional[Dict[str, Any]]:
        """
        Make a JSON-RPC request to the MCP server.
        
        Args:
            method: JSON-RPC method name
            params: Method parameters
            notification: If True, don't expect a response
            
        Returns:
            Response data or None for notifications
        """
        if not self.session:
            await self.connect()
            
        # Construct JSON-RPC message
        message = {
            "jsonrpc": "2.0",
            "method": method
        }
        
        if not notification:
            message["id"] = self._get_next_request_id()
            
        if params:
            message["params"] = params
            
        # Set required headers for Streamable HTTP
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }

        # if method == "initialize":
        #     headers["mcp-session-id"] = self.session_id
            
        print(f"→ Sending payload: {json.dumps(message, indent=2)}")
        print(f"→ Sending headers: {json.dumps(headers, indent=2)}")
        
        try:
            async with self.session.post(
                f"{self.server_url}/mcp/",
                json=message,
                headers=headers,
                timeout=self.timeout
            ) as response:
                print(f"← Status: {response.status}")
                
                if response.status == 404:
                    print("❌ 404 Error - Try alternative endpoints:")
                    return None
                    
                if response.status != 200:
                    error_text = await response.text()
                    print(f"❌ HTTP Error: {response.status}")
                    print(f"   Response: {error_text}")
                    return None
                
                # Handle different response types
                content_type = response.headers.get("Content-Type", "")
                
                if "application/json" in content_type:
                    result = await response.json()
                    print(f"← Response: {json.dumps(result, indent=2)}")
                    return result
                    
                elif "text/event-stream" in content_type:
                    # Handle Server-Sent Events
                    print("📡 Received SSE stream:")
                    async for line in response.content:
                        line = line.decode('utf-8').strip()
                        if line.startswith("data: "):
                            data = line[6:]  # Remove "data: " prefix
                            try:
                                event_data = json.loads(data)
                                print(f"← SSE Event: {json.dumps(event_data, indent=2)}")
                                return event_data
                            except json.JSONDecodeError:
                                print(f"← SSE Data: {data}")
                                
                else:
                    text = await response.text()
                    print(f"← Raw Response: {text}")
                    
        except Exception as e:
            print(f"❌ Error: {e}")
            
        return None
    
    async def create_session(self) -> bool:
        """
        Create a new session with the MCP server.
        
        Returns:
            True if session created successfully
        """
        print("🔄 Creating new session...")
        
        # Generate session ID (some servers expect client to provide it)
        self.session_id = str(uuid.uuid4())
        
        # Try to initialize - this often creates the session
        return await self.initialize()
    
    async def initialize(self) -> bool:
        """
        Initialize the MCP connection.
        
        Returns:
            True if initialization successful
        """
        print("🤝 Initializing MCP connection...")
        
        response = await self._make_request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {
                "roots": {
                    "listChanged": True
                },
                "sampling": {},
                "tools": {},
                # "resources": {},
                # "prompts": {}
            },
            "clientInfo": {
                "name": "egrid-mcp-client",
                "version": "1.0.0"
            }
        })
        
        print(f"initialize response: {response}")

        if response and "result" in response:
            print("✅ MCP initialization successful!")
            print(f"   Server: {response['result'].get('serverInfo', {}).get('name', 'Unknown')}")
            print(f"   Version: {response['result'].get('serverInfo', {}).get('version', 'Unknown')}")
            
            # Send initialized notification
            await self._make_request("notifications/initialized", notification=True)
            
            # Set server log level to debug
            await self._make_request("logging/setLevel", {"level": "debug"})
            
            return True
        else:
            print("❌ MCP initialization failed")
            return False
        
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the MCP server."""
        print("🔧 Listing available tools...")
        
        response = await self._make_request("tools/list")
        
        if response and "result" in response:
            tools = response["result"].get("tools", [])
            print(f"✅ Found {len(tools)} tools:")
            for tool in tools:
                print(f"   - {tool.get('name', 'Unknown')}: {tool.get('description', 'No description')}")
            return tools
        else:
            print("❌ Failed to list tools")
            return []
    
    async def connect(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

        # if not self.session_id:
        #     await self.create_session()

        # if not self.session_id:
        #     async with self.session.post(
        #         f"{self.server_url}/mcp/v1/session",
        #         headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        #     ) as response:
        #         if response.status == 200:
        #             result = await response.json()
        #             self.session_id = result.get("session_id")
        #         else:
        #             raise Exception(f"Failed to create session: {response.status}")
    
    async def call_tool(self, tool_name, arguments):
        """Call MCP tool via HTTP streaming"""
        await self.connect()
        
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call", 
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        try:
            async with self.session.post(
                f"{self.server_url}/mcp/",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                }
            ) as response:
                if response.status == 200:
                    # Read and parse event stream response
                    async for line in response.content:
                        line = line.decode('utf-8').strip()
                        if line.startswith('data: '):
                            try:
                                data = json.loads(line[6:])  # Skip 'data: ' prefix
                                if "result" in data and "content" in data["result"]:
                                    return data["result"]["content"][0]["text"]
                                return str(data)
                            except json.JSONDecodeError:
                                continue
                    return "No valid response data received"
                else:
                    error_text = await response.text()
                    return f"HTTP Error {response.status}: {error_text}"
        except Exception as e:
            return f"Connection failed: {str(e)}"
    
    async def close(self):
        if self.session:
            await self.session.close()

# Initialize remote MCP client
mcp_client = MCPHttpClient("http://localhost:8000")

async def remote_power_flow_tool(case_name: str) -> str:
    """
    Run power flow analysis for a given case
    Parameters:
        case_name: The name of the power flow case file to analyze. Should include the file extension.
    Returns:
        Response data as string
    """
    return await mcp_client.call_tool("run_power_flow", {"case_name": case_name})

async def remote_hosting_capacity_tool(sim_hours: int = 24) -> str:
    """
    Run hosting capacity analysis for a specified duration of hours
    Parameters:
        sim_hours: The number of hours you want to run the simulation
    Returns:
        Response data as string
    """
    return await mcp_client.call_tool("run_hosting_capacity_analysis", {"sim_hours": sim_hours})

# def get_hostcap_image(sim_hours:int):
#     """
#     Run hosting capacity analysis and get the generated image
#     Parameters:
#         sim_hours: The number of hours you want to run the simulation
#     Returns:
#         Path to saved image file
#     """
    
#     url = f"{API_BASE_URL}/hostcap/image"
#     request_data = {
#         "sim_hours": sim_hours,
#         "analysis_type": "hostcap_image"
#     }
#     response = requests.post(url, 
#                              headers={'Content-Type': 'application/json', 'Accept': 'image/png'},
#                              data=json.dumps(request_data)
#                              )
    
#     if response.status_code == 200 or response.status_code == 201:
#         # Save the image to a file
#         image_path = "received_test_dss.png"
#         with open(image_path, 'wb') as f:
#             f.write(response.content)
#         print(f"Image saved to {image_path}")
#         return f"Image saved to {image_path}"
#     else:
#         return f"Error: {response.status_code}, {response.text}"

def create_remote_power_analysis_agent():
    """Create Bedrock agent with remote MCP-backed tools"""
    
    pf_actions = ActionGroup(
        name="PFActionGroup",
        description="This is action group to run power flow analysis",
        tools=[remote_power_flow_tool],
    )

    hc_actions = ActionGroup(
    name = "HCActionGroup", 
    description="This is action group to run hosting capacity analysis",
    tools=[remote_hosting_capacity_tool],
)
    
    agent = InlineAgent(
        agent_name="RemotePowerSystemMCPAgent",
        instruction="AI agent for remote electrical power system analysis. It is able to run power flow analysis or hosting capacity analysis through the eGrid MCP server.",
        foundation_model=FOUNDATION_MODELS[0],
        action_groups=[pf_actions, hc_actions],
    )
    
    return agent

async def main():
    """Run Bedrock agent with remote MCP server"""
    try:
        agent = create_remote_power_analysis_agent()
        prompts = ["Run power flow analysis for case IEEE14_from_raw.gridcal",
                   "Run DER hosting capacity analysis for 12 hours",
                   "Run DER hosting capacity analysis for 24 hours and get the image"]

        response = await agent.invoke(prompts[random.randint(0, 1)])
        
        print("Agent Response:", response)
        
    finally:
        await mcp_client.close()

if __name__ == "__main__":
    asyncio.run(main())
