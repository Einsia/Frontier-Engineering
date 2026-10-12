# -*- coding: utf-8 -*-
"""
Created on Fri Aug  9 16:39:09 2019
Lasrt update on Wed Feb 12 10:35:00 2020

@author: rte-challenge-roadef-2020-team
"""
import os
import sys
import numpy as np
import json


####################
### Utils ##########
####################

## Global variables
CUR_DIR = os.getcwd()
PAR_DIR = os.path.dirname(CUR_DIR)
RESOURCES_STR = 'Resources'
SEASONS_STR = 'Seasons'
INTERVENTIONS_STR = 'Interventions'
EXCLUSIONS_STR = 'Exclusions'
T_STR = 'T'
SCENARIO_NUMBER = 'Scenarios_number'
RESOURCE_CHARGE_STR = 'workload'
TMAX_STR = 'tmax'
DELTA_STR = 'Delta'
MAX_STR = 'max'
MIN_STR = 'min'
RISK_STR = 'risk'
START_STR = 'start'
QUANTILE_STR = "Quantile"
ALPHA_STR = "Alpha"

## Json reader
def read_json(filename: str):
    """Read a json file and return data as a dict object"""

    print('Reading json file ' + filename + '...')
    f = open(filename, 'r')
    Instance = json.load(f)
    f.close()
    print('Done')

    return Instance

## Txt Solution reader
def read_solution_from_txt(Instance: dict, solution_filename: str):
    """Read a txt formated Solution file, and store the solution informations in Instance"""

    print('Loading solution from ' + solution_filename + '...')
    # Load interventions
    Interventions = Instance[INTERVENTIONS_STR]
    # Read file line by line, and store starting time value (no checks yet, except format and duplicate)
    solution_file = open(solution_filename, 'r')
    for line in solution_file:
        # Split line to retrive infos: Intervention name and decided starting date
        tmp = line.split(' ')
        intervention_name = tmp[0]
        start_time_str = tmp[1].split('\n')[0]
        # Assert Intervention exists
        if not intervention_name in Interventions:
            print('ERROR: Unexpected Intervention ' + intervention_name + ' in solution file ' + solution_filename + '.')
            continue
        # Assert starting date is an integer
        start_time: int
        try:
            start_time = int(start_time_str)
        except ValueError:
            print('ERROR: Unexpected starting time ' + start_time_str + ' for Intervention ' + intervention_name + '. Expect integer value.')
            continue
        # Assert no duplicate
        if START_STR in Interventions[intervention_name]:
            print('ERROR: Duplicate entry for Intervention ' + intervention_name + '. Only first read value is being considered.')
            continue
        # Store starting time
        Interventions[intervention_name][START_STR] = start_time
    solution_file.close()
    print('Done')


################################
## Results processing ##########
################################

## Compute effective worload
def compute_resources(Instance: dict):
    """Compute effective workload (i.e. resources consumption values) for every resource and every time step"""

    # Retrieve usefull infos
    Interventions = Instance[INTERVENTIONS_STR]
    T_max = Instance[T_STR]
    Resources = Instance[RESOURCES_STR]
    # Init resource usage dictionnary for each resource and time
    resources_usage = {}
    for resource_name in Resources.keys():
        resources_usage[resource_name] = np.zeros(T_max)
    # Compute value for each resource and time step
    for intervention_name, intervention in Interventions.items():
        # start time should be defined (already checked in scheduled constraint checker)
        if not START_STR in intervention:
            continue
        start_time = intervention[START_STR]
        start_time_idx = start_time - 1 #index of list starts at 0
        intervention_worload = intervention[RESOURCE_CHARGE_STR]
        intervention_delta = int(intervention[DELTA_STR][start_time_idx])
        # compute effective worload
        for resource_name, intervention_resource_worload in intervention_worload.items():
            for time in range(start_time_idx, start_time_idx + intervention_delta):
                # null values are not available
                if str(time+1) in intervention_resource_worload and str(start_time) in intervention_resource_worload[str(time+1)]:
                    resources_usage[resource_name][time] += intervention_resource_worload[str(time+1)][str(start_time)]

    return resources_usage


## Retrieve effective risk distribution given starting times solution
def compute_risk_distribution(Interventions: dict, T_max: int, scenario_numbers):
    """Compute risk distributions for all time steps, given the interventions starting times"""

    print('\tComputing risk...')
    # Init risk table
    risk = [scenario_numbers[t] * [0] for t in range(T_max)]
    # Compute for each intervention independently
    for intervention in Interventions.values():
        # Retrieve Intervention's usefull infos
        intervention_risk = intervention[RISK_STR]
        # start time should be defined (already checked in scheduled constraint checker)
        if not START_STR in intervention:
            continue
        start_time = intervention[START_STR]
        start_time_idx = int(start_time) - 1 # index for list getter
        delta = int(intervention[DELTA_STR][start_time_idx])
        for time in range(start_time_idx, start_time_idx + delta):
            for i, additional_risk in enumerate(intervention_risk[str(time + 1)][str(start_time)]):
                risk[time][i] += additional_risk
    print('\tDone')

    return risk

## Compute mean for each period
def compute_mean_risk(risk, T_max: int, scenario_numbers):
    """Compute mean risk values over each time period"""

    print('\tComputing mean risk...')
    # Init mean risk
    mean_risk = np.zeros(T_max)
    # compute mean
    for t in range(T_max):
        mean_risk[t] = sum(risk[t]) / scenario_numbers[t]
    print('\tDone')

    return mean_risk

## Compute quantile for each period
def compute_quantile(risk, T_max: int, scenario_numbers, quantile):
    """Compute Quantile values over each time period"""

    print('\tComputing Quantile...')
    # Init quantile
    q = np.zeros(T_max)
    for t in range(T_max):
        risk[t].sort()
        q[t] = risk[t][int(np.ceil(scenario_numbers[t] * quantile))-1]
    print('\tDone')

    return q

## Compute both objectives: mean risk and quantile
def compute_objective(Instance: dict):
    """Compute objectives (mean and expected excess)"""

    print('Computing objectives values...')
    # Retrieve usefull infos
    T_max = Instance[T_STR]
    scenario_numbers = Instance[SCENARIO_NUMBER]
    Interventions = Instance[INTERVENTIONS_STR]
    quantile = Instance[QUANTILE_STR]
    # Retrieve risk final distribution
    risk = compute_risk_distribution(Interventions, T_max, scenario_numbers)
    # Compute mean risk
    mean_risk = compute_mean_risk(risk, T_max, scenario_numbers)
    # Compute quantile
    q = compute_quantile(risk, T_max, scenario_numbers, quantile)
    print('Done')

    return mean_risk, q



##################################
## Constraints checkers ##########
##################################

## Launch each Constraint checks
def check_all_constraints(Instance: dict):
    """Run all constraint checks"""

    print('Checking constraints...')
    # Schedule constraints
    check_schedule(Instance)
    # Resources constraints
    check_resources(Instance)
    # Exclusions constraints
    check_exclusions(Instance)
    print('Done')

## Schedule constraints: §4.1 in model description
def check_schedule(Instance: dict):
    """Check schedule constraints"""

    print('\tChecking schedule constraints...')
    # Continuous interventions: §4.1.1
    #   This constraint is implicitly checked by the resource computation:
    #   computation is done under continuity hypothesis, and resource bounds will ensure the feasibility
    # Checks is done on each Intervention
    Interventions = Instance[INTERVENTIONS_STR]
    for intervention_name, intervention in Interventions.items():
        # Interventions are planned once: §4.1.2
        #   assert a starting time has been assigned to the intervention
        if not START_STR in intervention:
            print('ERROR: Schedule constraint 4.1.2: Intervention ' + intervention_name + ' has not been scheduled.')
            continue
        # Starting time validity: no explicit constraint
        start_time = intervention[START_STR]
        horizon_end = Instance[T_STR]
        if not (1 <= start_time <= horizon_end):
            print('ERROR: Schedule constraint 4.1 time validity: Intervention ' + intervention_name + ' starting time ' + str(start_time)
            + ' is not a valid starting date. Expected value between 1 and ' + str(horizon_end) + '.')
            # Remove start time to avoid later access errors
            del intervention[START_STR]
            continue
        # No work left: §4.1.3
        #   assert intervention is not ongoing after time limit or end of horizon
        time_limit = int(intervention[TMAX_STR])
        if time_limit < start_time:
            print('ERROR: Schedule constraint 4.1.3: Intervention ' + intervention_name + ' realization exceeds time limit.'
            + ' It starts at ' + str(start_time) + ' while time limit is ' + str(time_limit) + '.')
            # Remove start time to avoid later access errors
            del intervention[START_STR]
            continue
    print('\tDone')

## Resources constraints: §4.2 in model description
def check_resources(Instance: dict):
    """Check resources constraints"""

    print('\tChecking resources constraints...')
    T_max = Instance[T_STR]
    Resources = Instance[RESOURCES_STR]
    # Bounds are checked with a tolerance value
    tolerance = 1e-5
    # Compute resource usage
    resource_usage = compute_resources(Instance) # dict on resources and time
    # Compare bounds to usage
    for resource_name, resource in Resources.items():
        for time in range(T_max):
            # retrieve bounds values
            upper_bound = resource[MAX_STR][time]
            lower_bound = resource[MIN_STR][time]
            # Consumed value
            worload = resource_usage[resource_name][time]
            # Check max
            if worload > upper_bound + tolerance:
                print('ERROR: Resources constraint 4.2 upper bound: Worload on Resource ' + resource_name + ' at time ' + str(time+1) + ' exceeds upper bound.'
                + ' Value ' + str(worload) + ' is greater than bound ' + str(upper_bound) + ' plus tolerance ' + str(tolerance) + '.')
            # Check min
            if worload < lower_bound - tolerance:
                print('ERROR: Resources constraint 4.2 lower bound: Worload on Resource ' + resource_name + ' at time ' + str(time+1) + ' does not match lower bound.'
                + ' Value ' + str(worload) + ' is lower than bound ' + str(lower_bound) + ' minus tolerance ' + str(tolerance) + '.')
    print('\tDone')

## Exclusions constraints: §4.3 in model description
def check_exclusions(Instance: dict):
    """Check exclusions constraints"""

    print('\tChecking exclusions constraints...')
    # Retrieve Interventions and Exclusions
    Interventions = Instance[INTERVENTIONS_STR]
    Exclusions = Instance[EXCLUSIONS_STR]
    # Assert every exclusion holds
    for exclusion in Exclusions.values():
        # Retrieve exclusion infos
        [intervention_1_name, intervention_2_name, season] = exclusion
        # Retrieve concerned interventions...
        intervention_1 = Interventions[intervention_1_name]
        intervention_2 = Interventions[intervention_2_name]
        # start time should be defined (already checked in scheduled constraint checker)
        if (not START_STR in intervention_1) or (not START_STR in intervention_2):
            continue
        # ... their respective starting times...
        intervention_1_start_time = intervention_1[START_STR]
        intervention_2_start_time = intervention_2[START_STR]
        # ... and their respective deltas (duration)
        intervention_1_delta = int(intervention_1[DELTA_STR][intervention_1_start_time - 1]) # get index in list
        intervention_2_delta = int(intervention_2[DELTA_STR][intervention_2_start_time - 1]) # get index in list
        # Check overlaps for each time step of the season
        for time_str in Instance[SEASONS_STR][season]:
            time = int(time_str)
            if (intervention_1_start_time <= time < intervention_1_start_time + intervention_1_delta) and (intervention_2_start_time <= time < intervention_2_start_time + intervention_2_delta):
                print('ERROR: Exclusions constraint 4.3: Interventions ' + intervention_1_name + ' and ' + intervention_2_name
                    + ' are both ongoing at time ' + str(time) + '.')
    print('\tDone')


#######################
## Displayer ##########
#######################

## Basic printing
def display_basic(Instance: dict, mean_risk, quantile):
    """Print main infos"""

    # Usefull infos
    alpha = Instance[ALPHA_STR]
    q = Instance[QUANTILE_STR]
    # Infos about instance
    print('Instance infos:')
    print('\tInterventions number: ', len(Instance[INTERVENTIONS_STR]))
    print('\tScenario numbers: ', len(Instance[SCENARIO_NUMBER]))
    # Computed infos about solution
    print('Solution evaluation:')
    # print('\tmean_risk over time: ', mean_risk)
    obj_1 = np.mean(mean_risk)
    print('\tObjective 1 (mean risk): ', obj_1)
    # print('\tQuantile (Q' + str(q) + ') over time: ', quantile)
    tmp = np.zeros(len(quantile))
    obj_2 = np.mean(np.max(np.vstack((quantile - mean_risk, tmp)), axis=0))
    print('\tObjective 2 (expected excess  (Q' + str(q) + ')): ', obj_2)
    obj_tot = alpha * obj_1 + (1-alpha)*obj_2
    print('\tTotal objective (alpha*mean_risk + (1-alpha)*expected_excess): ', obj_tot)


######################
## Launcher ##########
######################

def check_and_display(instance_file, solution_file):
    """Control checker actions"""

    # Read Instance
    instance = read_json(instance_file)
    # Read Solution
    read_solution_from_txt(instance, solution_file)
    # Check all constraints
    check_all_constraints(instance)
    # Compute indicators
    mean_risk, quantile = compute_objective(instance)
    # Display Solution
    display_basic(instance, mean_risk, quantile)


if __name__ == '__main__':

    if len(sys.argv) != 3:
        print('ERROR: expecting 2 arguments: paths to instance and solution files')
    else:
        instance_file = sys.argv[1]
        solution_file = sys.argv[2]
        check_and_display(instance_file, solution_file)
