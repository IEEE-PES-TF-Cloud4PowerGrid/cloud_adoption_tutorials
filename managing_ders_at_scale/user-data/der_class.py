import random
import csv
import os
from datetime import datetime
import numpy as np
from scipy.stats import norm

# generate a random number between min and max value
def get_random_number_between(lower_value, upper_value):
    value = 0.0
    assert(upper_value > lower_value > 0)
    value = random.random() * (upper_value - lower_value) + lower_value
    return value

# create a normal distribution curve to mimic PV power generation curve
def create_a_normal_dist_curve(data):
    pdf = norm.pdf(data, loc = 12, scale = 1)
    return pdf

class Battery:
    def __init__(self, device_id, capacity):
        random.seed(datetime.now())
        self.device_id = device_id
        self.capacity = capacity               # set initial capacity
        self.nameplate_capacity = capacity     # save the initial capacity value for next cycle
        self.run_time = random.random() * 2 + 3   # generate a random time in 3-5 hours for battery discharge
        self.discharge_power = self.capacity / self.run_time   # unit: kW
        self.cycle_life = int(get_random_number_between(1500, 2000))   # most EV batteries will last somewhere between 1500 and 2000 charge cycles
        self.dischargable = True               # the battery is dischargable so it can be aggregated to provide power generating capacity
        self.time_to_fullcharge = random.random() * 1 + 1   # time for the battery in charging mode, 1-2 hours
        self.time_in_charge = 0

    # get the discharge power
    def get_discharge_power(self):
        return round(self.discharge_power, 1)

    # update the current battery capacity
    def get_current_capacity(self, sampling_interval):
        if self.capacity > 0 and self.dischargable == True:
            self.capacity = self.capacity - self.discharge_power * (sampling_interval / 3600)
        if self.capacity < 0:
            self.capacity = 0
        # when the battery is fully discharged, flip the dischargable flag and reduce the cycle life by 1
        # ps. realistically, most batteries should NOT be fully discharged
        if self.capacity == 0 and self.dischargable == True:
            # flip the dischargable flag to disable it
            self.dischargable = False
            self.cycle_life = self.cycle_life - 1
            self.discharge_power = 0
            self.time_to_fullcharge = random.random() * 1 + 1
        if self.dischargable == False and self.time_in_charge < self.time_to_fullcharge:
            self.time_in_charge = self.time_in_charge + sampling_interval / 3600
        if self.time_in_charge >= self.time_to_fullcharge:   # battery is fully charged and can provide power output again
            self.dischargable = True
            self.run_time = random.random() * 2 + 3
            self.capacity = self.nameplate_capacity
            self.discharge_power = self.capacity / self.run_time
            self.time_in_charge = 0

        return round(self.capacity, 1)

    def get_run_time(self, sampling_interval):
        self.run_time = self.run_time - sampling_interval / 3600
        return round(self.run_time, 1) if self.discharge_power != 0 else 0

    # get the metric value
    def get_metric_value(self, metric, sampling_interval = 60):
        if metric == 'capacity':
            return self.get_current_capacity(sampling_interval)
        elif metric == 'power_output':
            return self.get_discharge_power()
        elif metric == 'run_time':
            return self.get_run_time(sampling_interval)
        elif metric == 'cycle_life':
            return self.cycle_life
        elif metric == "dischargable":
            return self.dischargable

class PV:
    def __init__(self, device_id, nominal_power):
        random.seed(datetime.now())
        self.device_id = device_id
        self.nominal_power = nominal_power     # set the PV system nameplate power, unit: kW
        self.power_ouptut = self.nominal_power
        self.performance_ratio = 100           # PR = (actual power output / nominal power output)
        self.pr_var = get_random_number_between(0.85, 1.0)   # performance variance

    # get the nameplate power of the PV system
    def get_nominal_power(self):
        return self.nominal_power

    # get the current PV system power output
    def get_power_output(self):
        data = np.arange(0, 23, 0.01)
        pdf = create_a_normal_dist_curve(data)
        curr_hour = datetime.now().hour
        index = np.where((data > curr_hour) & (data < curr_hour + .05))
        self.power_output = round(self.nominal_power * sum(pdf[index]) * self.pr_var, 1)
        return self.power_output

    # get the performance ratio
    def get_performance_ratio(self):
        self.performance_ratio = int(self.power_output / self.nominal_power * 100)  # round to the nearest integer
        return self.performance_ratio
    
    # get the metric value
    def get_metric_value(self, metric):
        if metric == 'nominal_power':
            return self.get_nominal_power()
        elif metric == 'power_output':
            return self.get_power_output()
        elif metric == 'performance_ratio':
            return self.get_performance_ratio()

class WindMachine:
    def __init__(self, device_id, nameplate_capacity):
        self.device_id = device_id
        self.nameplate_capacity = nameplate_capacity
        self.wind_speed = 0
        self.power_output = 0
        self.power_at_speed = {}
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(curr_dir, 'speed2power.csv'), newline='') as csvfile:
            csvReader = csv.DictReader(csvfile)
            for row in csvReader:
                self.power_at_speed[int(row['WindSpeed'])] = float(row['PowerOutput'])

    # set the class variable value and also return it
    def get_wind_speed(self, wind_speed):
        self.wind_speed = wind_speed
        return self.wind_speed

    # get the power output according to the Speed-Power curve. The curve is plotted based on a 95kW wind turbine,
    # we simply prorate it here. Ref. https://www.e-education.psu.edu/emsc297/node/649
    def get_power_output(self, wind_speed):
        if self.power_at_speed:
            self.power_output = round(self.power_at_speed[wind_speed] * self.nameplate_capacity / 95, 1)
        return self.power_output

    # get the metric value
    def get_metric_value(self, metric, wind_speed=0):
        if metric == 'nameplate_capacity':
            return self.nameplate_capacity
        elif metric == 'power_output':
            return self.get_power_output(wind_speed)
        elif metric == 'wind_speed':
            return self.get_wind_speed(wind_speed)



