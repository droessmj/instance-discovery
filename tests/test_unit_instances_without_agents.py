import sys
# setting path
sys.path.append('../instance-discovery')

import instances_without_agents

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

    


# def test_normalization_agent_data_ec2():

# def test_normalization_agent_data_fargate():

# def test_normalization_aws():

# def test_normalization_gcp():

# def test_normalization_azure():