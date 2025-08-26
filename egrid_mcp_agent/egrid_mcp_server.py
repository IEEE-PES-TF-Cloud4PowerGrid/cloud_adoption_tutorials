#!/usr/bin/env python3
"""
This is a MCP server for power system analysis with GridCal and OpenDSS
Converts REST API endpoints to MCP tools
"""
import time
import matplotlib.pyplot as plt
import numpy as np
import GridCalEngine.api as gce
import dss
from fastmcp import FastMCP


# It's currently buggy to get a session ID before continuing to make tool calls. 
# See https://github.com/jlowin/fastmcp/issues/956
# The workaround is to use stateless session currently.
mcp = FastMCP("egrid-mcp-server", stateless_http=True)

class PowerFlowService:
    def __init__(self):
        print("PowerFlow service initialized")

class HostingCapService:
    def __init__(self):
        self.dss_via_python = dss.DSS
        self.dss_via_python.Start(0)
        self.dss_via_python.AllowForms = True
        print("HostingCap service initialized")
    
    def generate_commands(self, circuit_name: str, frequency: float, demand_mult: list, solar_mult: list, generator_type: str = "generator"):
        """Generate DSS commands with customizable parameters"""
        demand_str = ", ".join(map(str, demand_mult))
        solar_str = ", ".join(map(str, solar_mult))
        
        return [
            'clear',
            f'set DefaultBaseFrequency={frequency}',
            f'new circuit.{circuit_name} bus1=slack basekv=0.4 pu=1.0 angle=0 frequency={frequency} phases=3',
            'new line.slack-B1 phases=3 bus1=slack bus2=B1 r1=0.1 x1=0.1 r0=0.05 x0=0.05 length=1',
            'new line.B1-B2 phases=3 bus1=B1 bus2=B2 r1=0.1 x1=0.1 r0=0.05 x0=0.05 length=1',
            'new line.B2-B3 phases=3 bus1=B2 bus2=B3 r1=0.1 x1=0.1 r0=0.05 x0=0.05 length=1',
            f'new loadshape.demand npts={len(demand_mult)} interval=1.0 mult={{{demand_str}}}',
            f'new loadshape.solar npts={len(solar_mult)} interval=1.0 mult={{{solar_str}}}',
            'new load.house phases=1 bus1=B3.1 kv=0.23 kw=1 kvar=0 vmaxpu=1.5 vminpu=0.8 daily=demand',
            f'new {generator_type}.pv_system phases=1 bus1=B3.2 kv=0.23 kw=5 pf=1 vmaxpu=1.5 vminpu=0.8 daily=solar',
            'reset',
            'set ControlMode=Time',
            'set Mode=Daily StepSize=1h Number=1 Time=(0,0)',
            'set VoltageBases=[0.4]',
            'calcv',
        ]

# Initialize services
power_flow_service = PowerFlowService()
hosting_cap_service = HostingCapService()

@mcp.tool()
async def run_power_flow(case_name: str) -> str:
    """Run power flow analysis using GridCalEngine"""
    try:
        main_ckt = gce.open_file(case_name)
        results = gce.power_flow(main_ckt)

        response = {
            'Circuit Name': main_ckt.name,
            'Convergence': str(results.converged),
            'error': results.error
        }

        return f"Power Flow Results:\n{response}"
    except Exception as e:
        return f"Power flow analysis failed: {str(e)}"

@mcp.tool()
async def run_hosting_capacity_analysis(
    sim_hours: int = 24,
    circuit_name: str = "test_lv_feeder",
    frequency: float = 50.0,
    demand_multipliers: str = "1.0,1.0,1.0,1.0,1.0,1.0,3.0,5.0,3.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,3.0,5.0,7.0,7.0,5.0,3.0,1.0,1.0",
    solar_multipliers: str = "0.0,0.0,0.0,0.0,0.0,0.0,0.1,0.3,0.5,0.7,0.8,1.0,0.8,0.7,0.5,0.3,0.1,0.0,0.0,0.0,0.0,0.0,0.0,0.0",
    generator_type: str = "generator"
) -> str:
    """Run DER hosting capacity analysis using OpenDSS with customizable parameters"""
    try:
        start_time = time.time()
        
        # Parse multiplier strings to lists
        demand_mult = [float(x.strip()) for x in demand_multipliers.split(',')]
        solar_mult = [float(x.strip()) for x in solar_multipliers.split(',')]
        
        # Generate and execute DSS commands
        commands = hosting_cap_service.generate_commands(circuit_name, frequency, demand_mult, solar_mult, generator_type)
        for cmd in commands:
            hosting_cap_service.dss_via_python.Text.Command = cmd

        data_python = {
            'PV System': {'element_name': 'generator.pv_system', 'Power (kW)': [], 'Voltage (V)': []},
            'House': {'element_name': 'load.house', 'Power (kW)': [], 'Voltage (V)': []}
        }

        for t in range(sim_hours):
            hosting_cap_service.dss_via_python.ActiveCircuit.Solution.Solve()

            for element in data_python.keys():
                hosting_cap_service.dss_via_python.ActiveCircuit.SetActiveElement(data_python[element]['element_name'])
                data_python[element]['Power (kW)'].append(hosting_cap_service.dss_via_python.ActiveCircuit.ActiveElement.Powers[0])
                data_python[element]['Voltage (V)'].append(hosting_cap_service.dss_via_python.ActiveCircuit.ActiveElement.VoltagesMagAng[0])

        elapse_time = time.time() - start_time

        # Generate plot
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        fig.subplots_adjust(hspace=0.2, wspace=0.2)
        plt.suptitle('DER Hosting Capacity Analysis')

        primary_keys = list(data_python.keys())
        inner_keys = [key for key in data_python[primary_keys[0]].keys() if key != 'element_name']

        for i, primary_key in enumerate(primary_keys):
            for j, inner_key in enumerate(inner_keys):
                ax = axes[i, j]
                if i == 0: ax.set_title(inner_key, fontsize=12, fontweight='bold')
                if j == 0: ax.set_ylabel(primary_key, rotation=90, fontsize=12, fontweight='bold')
                ax.plot(data_python[primary_key][inner_key])
                ax.set_xticks(_generate_ticks(sim_hours).tolist())

        plt.savefig("hosting_capacity_analysis.png", dpi=300)
        plt.close()

        return f"Hosting Capacity Analysis completed in {elapse_time:.2f} seconds. Results saved to hosting_capacity_analysis.png"

    except Exception as e:
        return f"Hosting capacity analysis failed: {str(e)}"

def _generate_ticks(n: int):
    """Generate array with integer ticks"""
    num_intervals = 4
    step = (n - 1) / num_intervals

    if step != int(step):
        n = 1 + int(step) * num_intervals
        step = (n - 1) / num_intervals

    return np.arange(1, (int(step)+2) * num_intervals, num_intervals)


if __name__ == "__main__":
    # Run with Streamable HTTP (the most recommended way, SSE transport is deprecated)
    mcp.run(transport="streamable-http")
