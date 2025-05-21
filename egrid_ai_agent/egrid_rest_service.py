from flask import Flask, request, jsonify, send_file
from flask_restful import Api, Resource
import io
import logging
import GridCalEngine.api as gce
import dss
import time   # to capture the time taken to run the simulations
import matplotlib.pyplot as plt # to plot the results
import numpy as np # to handle numerical data

app = Flask(__name__)
api = Api(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RunPowerFlow(Resource):
    def __init__(self):
        # Initialize connection to Software A - GridCal
        try:
            #self.gce_client = gce.open(fname)  # Replace with actual initialization
            print("initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Software A client: {str(e)}")
            raise

    # /POST method implementation
    def post(self):
        """
        REST endpoint to run a power flow example using GridCalEngine
        """
        try:
            # Get request data
            request_data = request.get_json()

            # Validate required parameters
            required_params = ['case_name']  # Add your required parameters
            for param in required_params:
                if param not in request_data:
                    return {
                        'error': f'Missing required parameter: {param}'
                    }, 400

            # Extract parameters from request
            model_params = {
                'case_name': request_data['case_name'],
                # Add any other parameters needed by Software A's CreateModel API
            }

            # Call GridCalEngine API
            main_ckt = gce.open_file(model_params['case_name'])
            results = gce.power_flow(main_ckt)
            print(model_params['case_name'])
            print(main_ckt)
            print(results)

            # Transform the response to REST API format
            api_response = {
                'Circuit Name': main_ckt.name,  # Adjust based on actual response
                'Convergence': str(results.converged),
                'error': results.error
            }

            return api_response, 201
        except Exception as e:
            print(f"error: {str(e)}")
            raise

        ### if the tool API provides find-grained error handling
        # except software_a_sdk.ValidationError as ve:
        #     # Handle Software A validation errors
        #     return {
        #         'error': 'Validation error',
        #         'message': str(ve)
        #     }, 400

        # except software_a_sdk.AuthenticationError as ae:
        #     # Handle authentication errors
        #     return {
        #         'error': 'Authentication error',
        #         'message': str(ae)
        #     }, 401

        # except Exception as e:
        #     # Log unexpected errors
        #     logger.error(f"Error creating model: {str(e)}")
        #     return {
        #         'error': 'Internal server error',
        #         'message': 'An unexpected error occurred'
        #     }, 500

    ### Example for /GET method implementation
    # def get(self):
    #     try:
    #         model_id = request.args.get('model_id')
    #         if model_id:
    #             # Get specific model status
    #             model = self.software_a_client.get_model(model_id)
    #             return {
    #                 'model_id': model_id,
    #                 'status': model.status,
    #                 'details': model.details
    #             }
    #         else:
    #             # List all models
    #             models = self.software_a_client.list_models()
    #             return {'models': models}

    #     except Exception as e:
    #         logger.error(f"Error retrieving model(s): {str(e)}")
    #         return {'error': str(e)}, 500

class RunHostingCapAnalysis(Resource):
    def __init__(self):
        # Initialize connection to Software B - OpenDSS
        try:
            self.dss_via_python = dss.DSS
            # only run this once
            self.dss_via_python.Start(0)
            self.dss_via_python.AllowForms = True
            self.text_commands = [
                'clear',
                'set DefaultBaseFrequency=50',
                'new circuit.test_lv_feeder bus1=slack basekv=0.4 pu=1.0 angle=0 frequency=50 phases=3',
                'new line.slack-B1 phases=3 bus1=slack bus2=B1 r1=0.1 x1=0.1 r0=0.05 x0=0.05 length=1',
                'new line.B1-B2 phases=3 bus1=B1 bus2=B2 r1=0.1 x1=0.1 r0=0.05 x0=0.05 length=1',
                'new line.B2-B3 phases=3 bus1=B2 bus2=B3 r1=0.1 x1=0.1 r0=0.05 x0=0.05 length=1',
                'new loadshape.demand npts=24 interval=1.0 mult={1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 3.0, 5.0, 3.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 3.0, 5.0, 7.0, 7.0, 5.0, 3.0, 1.0, 1.0,}',
                'new loadshape.solar  npts=24 interval=1.0 mult={0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.3, 0.5, 0.7, 0.8, 1.0, 0.8, 0.7, 0.5, 0.3, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,}',
                'new load.house phases=1 bus1=B3.1 kv=0.23 kw=1 kvar=0 vmaxpu=1.5 vminpu=0.8 daily=demand',
                'new generator.pv_system phases=1 bus1=B3.2 kv=0.23 kw=5 pf=1 vmaxpu=1.5 vminpu=0.8 daily=solar',
                'reset',
                'set ControlMode=Time',
                'set Mode=Daily StepSize=1h Number=1 Time=(0,0)',
                'set VoltageBases=[0.4]',
                'calcv',
            ]
            # Store the last generated image data
            self.last_image_data = None
            print(self.dss_via_python)      # check object type
            print("initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Software B client: {str(e)}")
            raise
            
    def get(self):
        """
        GET endpoint to retrieve the last generated image
        """
        if self.last_image_data:
            return send_file(
                self.last_image_data,
                mimetype='image/png',
                as_attachment=True,
                download_name='test_dss.png'
            )
        else:
            return {'error': 'No image available. Run a simulation first.'}, 404
    def post(self):
        """
        REST endpoint to run a DER hosting capacity analysis using dss_python
        """
        try:
            # Get request data
            request_data = request.get_json()

            # Validate required parameters
            required_params = ['sim_hours']  # Add your required parameters
            for param in required_params:
                if param not in request_data:
                    return {
                        'error': f'Missing required parameter: {param}'
                    }, 400

            print(f"requested simulation hours: {request_data['sim_hours']}")
            res, elapse_time, img_data = self._run(sim_hours=int(request_data['sim_hours']))
            
            # Store the image data for later retrieval
            self.last_image_data = img_data
            
            # Check if the client wants the image or JSON response
            if request.headers.get('Accept') == 'image/png' or request.path.endswith('/image'):
                # Return the image directly
                return send_file(
                    img_data,
                    mimetype='image/png',
                    as_attachment=True,
                    download_name='test_dss.png'
                )
            else:
                # Return JSON response
                if res:
                    api_response = {
                        'Results': res,
                        'Used Time': f"{elapse_time} second(s)",
                        'Status': "Success",
                        'Image': 'Available at /api/hostcap/image'  # Inform about image endpoint
                    }
                else:
                    api_response = {
                        'Results': '',
                        'Status': 'Fail'
                    }
                return api_response, 201
        except Exception as e:
            print(f"error: {str(e)}")
            raise

    def _run(self, sim_hours=24):
        start_com = time.time()   # to capture the starting time dss via com
        # Read the commands
        for cmd in self.text_commands:
            self.dss_via_python.Text.Command = cmd

        #sim_hours = 24 # Set the number of hours to run the simulation
        data_python = {
            'PV System': {'element_name': 'generator.pv_system', 'Power (kW)': [], 'Voltage (V)': []},
            'House': {'element_name': 'load.house', 'Power (kW)': [], 'Voltage (V)': []}
        }
        for t in range(sim_hours):
            self.dss_via_python.ActiveCircuit.Solution.Solve()

            for element in data_python.keys():
                self.dss_via_python.ActiveCircuit.SetActiveElement(data_python[element]['element_name'])
                data_python[element]['Power (kW)'].append(self.dss_via_python.ActiveCircuit.ActiveElement.Powers[0])
                data_python[element]['Voltage (V)'].append(self.dss_via_python.ActiveCircuit.ActiveElement.VoltagesMagAng[0])

        elapse_time = time.time() - start_com
        print(f"Elapse time: {elapse_time}")
        print(f"data objects: {data_python}")


        # Create a figure and subplots
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        fig.subplots_adjust(hspace=0.2, wspace=0.2)
        plt.suptitle('DER Hosting Capacity Analysis')

        primary_keys = list(data_python.keys())
        inner_keys = [key for key in data_python[primary_keys[0]].keys() if key != 'element_name']

        # Iterate over rows (primary keys) and columns (inner keys)
        for i, primary_key in enumerate(primary_keys):
            for j, inner_key in enumerate(inner_keys):
                ax = axes[i, j]  # Select subplot
                # Set column title for the first row only
                if i == 0: ax.set_title(inner_key, fontsize=12, fontweight='bold')
                # Set row label for the first column only
                if j == 0: ax.set_ylabel(primary_key, rotation=90, fontsize=12, fontweight='bold')


                # Example placeholder for empty data
                ax.plot(data_python[primary_key][inner_key])  # Replace with actual data if available
                ax.set_xticks(self.generate_array_with_integer_ticks(sim_hours).tolist())

        print("saving plot to file...")
        # Save the plot to a BytesIO object instead of a file
        img_data = io.BytesIO()
        plt.savefig(img_data, format='png', dpi=300)
        img_data.seek(0)  # Move to the beginning of the BytesIO object
        
        # Also save to disk for reference
        plt.savefig("test_dss.png", dpi=300)
        
        return data_python, elapse_time, img_data

    def generate_array_with_integer_ticks(self, n: int):
        """
        Generates an array from 1 to n (or nearest integer number > n ) at step size 4, ensuring integer tick numbers.

        Args:
        n: The upper bound of the array (inclusive).

        Returns:
        A NumPy array with a dynamic number of elements at integers.
        """
        num_intervals = 4

        # Calculate the step size
        step = (n - 1) / num_intervals

        print(step, int(step))

        # If the step is not an integer, adjust n to make it an integer
        if step != int(step):
            n = 1 + int(step) * num_intervals
            step = (n - 1) / num_intervals

        # Generate the array using numpy.arange
        arr = np.arange(1, (int(step)+2) * num_intervals, num_intervals)
        return arr


# Register the resource
api.add_resource(RunPowerFlow, '/api/powerflow')
api.add_resource(RunHostingCapAnalysis, '/api/hostcap', '/api/hostcap/image')

# Add middleware for request logging
@app.before_request
def log_request_info():
    logger.info('Headers: %s', request.headers)
    logger.info('Body: %s', request.get_data())

# Add error handlers
@app.errorhandler(404)
def not_found(error):
    return {'error': 'Resource not found'}, 404

@app.errorhandler(500)
def internal_error(error):
    return {'error': 'Internal server error'}, 500

if __name__ == '__main__':
    # Configuration
    config = {
        'host': '0.0.0.0',
        'port': 5000,
        'debug': False  # Set to False in production
    }

    # Run the application
    app.run(**config)
