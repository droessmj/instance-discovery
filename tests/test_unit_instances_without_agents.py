import sys
# setting path
sys.path.append('../instance-discovery')

import instances_without_agents
from argparse import Namespace

#########################
# check_truncation
#########################
def test_check_trucation_true():
    results = list([i for i in range(600_000)])
    assert(instances_without_agents.check_truncation(results) == True)

def test_check_trucation_false():
    results = list([i for i in range(100)])
    assert(instances_without_agents.check_truncation(results) == False)


###################################
# get_fargate_with_lacework_agents
###################################
def test_get_fargate_with_lacework_agents_1():
    input_data = [
        {'data':
            [{
                'resourceConfig':{
                    'tags':{'a':'apple'},
                    'containers':[
                        { 'image':'datacollector',
                          'taskArn': 'abcd'
                        }
                    ],
                    'taskArn': 'abcd'
                }
             },
             {
                'resourceConfig':{
                    'tags': {'b':'banana'},
                    'containers':[
                        { 'image':'not-what-we-want',
                          'taskArn': 'vxyz'
                        }
                    ],
                    'taskArn': 'vxyz'
                }
             }]
        }
    ]
    lw_subaccount = 'test'
    results_with_agent, results_without_agent = instances_without_agents.get_fargate_with_lacework_agents(input_data, lw_subaccount)

    assert(results_with_agent != None)
    assert(len(results_with_agent) == 1)

    assert(results_without_agent != None)
    assert(len(results_without_agent) == 1)

    
###################################
# apply_fargate_filter
###################################
def test_apply_fargate_filter_1():
    # TODO: need to be able to mock LaceworkClinet.inventory.search
    return 0


###################################
# output_statistics
###################################
def test_output_statistics_current_account_1(capsys):
    instances_without_agents_set = set()
    instances_with_agents_set = set()
    agents_without_inventory_set = set()
    
    input_instance_result = instances_without_agents.InstanceResult(instances_without_agents_set, instances_with_agents_set, agents_without_inventory_set)
    input_user_profile_data = {'accounts':['test1']}
    input_args = Namespace(account='', api_key='', api_secret='', subaccount='', profile='default', csv=False, json=True, debug=False, current_sub_account_only=True, statistics=False)

    instances_without_agents.output_statistics(input_args, input_instance_result, input_user_profile_data)
    # capture output, k
    out, err = capsys.readouterr()
        
    assert('Number of distinct hosts identified during inventory assessment: 0')
    assert('Number of hosts which report successful agent operation: 0' in out)
    assert('Coverage Percentage: 0%' in out)
    assert(err == '')


def test_output_statistics_current_account_2(capsys):
    instances_without_agents_set = set()
    instances_with_agents_set = set([instances_without_agents.OutputRecord('test','',True,'test','test',{})])
    agents_without_inventory_set = set()
    
    input_instance_result = instances_without_agents.InstanceResult(instances_without_agents_set, instances_with_agents_set, agents_without_inventory_set)
    input_user_profile_data = {'accounts':['test1']}
    input_args = Namespace(account='', api_key='', api_secret='', subaccount='', profile='default', csv=False, json=True, debug=False, current_sub_account_only=True, statistics=False)

    instances_without_agents.output_statistics(input_args, input_instance_result, input_user_profile_data)
    # capture output, k
    out, err = capsys.readouterr()
        
    assert('Number of distinct hosts identified during inventory assessment: 1')
    assert('Number of hosts which report successful agent operation: 1' in out)
    assert('Coverage Percentage: 100.0%' in out)
    assert(err == '')
    

def test_output_statistics_current_account_3(capsys):
    instances_without_agents_set = set([instances_without_agents.OutputRecord('test2','',True,'test','test',{})])
    instances_with_agents_set = set([instances_without_agents.OutputRecord('test','',True,'test','test',{})])
    agents_without_inventory_set = set()
    
    input_instance_result = instances_without_agents.InstanceResult(instances_without_agents_set, instances_with_agents_set, agents_without_inventory_set)
    input_user_profile_data = {'accounts':['test1']}
    input_args = Namespace(account='', api_key='', api_secret='', subaccount='', profile='default', csv=False, json=True, debug=False, current_sub_account_only=True, statistics=False)

    instances_without_agents.output_statistics(input_args, input_instance_result, input_user_profile_data)
    # capture output, k
    out, err = capsys.readouterr()
        
    assert('Number of distinct hosts identified during inventory assessment: 2')
    assert('Number of hosts which report successful agent operation: 1' in out)
    assert('Number of hosts which report successful agent operation: 4' not in out)
    assert('Coverage Percentage: 50.0%' in out)
    assert(err == '')
