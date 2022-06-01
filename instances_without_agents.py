from datetime import datetime, timedelta, timezone
from laceworksdk import LaceworkClient
import json

def check_truncation(results):
    if results is list:
        if len(results) == MAX_RESULT_SET:
            return True
    return False

# WHAT METADATA DO WE HAVE AVAILABLE TO CONSISTENTLY CHECK UNIQUENESS ACROSS GCP & AWS? 
# AWS - ARN
# GCP - ???
def normalize_input(input, identifier):
    normalized_output = list()
    if len(input) > 0:
        data = input[0]['data']
        for r in data:
            if identifier == 'agent':
                # print(r)
                if 'VmProvider' in r['tags'].keys() and r['tags']['VmProvider'] == 'GCE':
                    normalized_output.append(r['hostname'])
                elif 'VmProvider' in r['tags'].keys() and r['tags']['VmProvider'] == 'AWS':
                    normalized_output.append(r['tags']['InstanceId'])
                else:
                    normalized_output.append(r['hostname'])
            elif identifier == 'Gcp':
                normalized_output.append(r['urn'])
            elif identifier == 'Aws':
                normalized_output.append(r['urn'])
            else:
                raise Exception (f'Error normalizing data set inputs! input: {input}, identifier: {identifier}')
    else:
        raise Exception (f'Empty input passed to normalize!')

    return normalized_output


MAX_RESULT_SET = 500_000
LOOKBACK_DAYS = 1

# lookback time can be configured for any value between 1 hour and 7 days
current_time = datetime.now(timezone.utc)
start_time = current_time - timedelta(days=LOOKBACK_DAYS)
start_time = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
end_time = current_time.strftime('%Y-%m-%dT%H:%M:%SZ')

client = LaceworkClient(profile='lwcs')

all_agent_instances = client.agent_info.search(json={
        'timeFilter': { 
            'startTime' : start_time, 
            'endTime'   : end_time
        } 
    })
list_agent_instances = normalize_input(list(all_agent_instances), 'agent')
if check_truncation(list_agent_instances):
    print(f'WARNING: Agent Instances truncated at {MAX_RESULT_SET} records')

print(f'Agent Instances: {list_agent_instances}\n')


gcp_inventory = client.inventory.search(json={
        'timeFilter': { 
            'startTime' : start_time, 
            'endTime'   : end_time
        }, 
        'filters': [
            # pubsub.googleapis.com/Topic
            { 'field': 'resourceType', 'expression': 'eq', 'value':'compute.googleapis.com/Instance'}
        ],
        'dataset': 'GcpCompliance'
    })
list_gcp_instances = normalize_input(list(gcp_inventory), 'Gcp')
if check_truncation(list_gcp_instances):
    print(f'WARNING: GCP Instances truncated at {MAX_RESULT_SET} records')
print(f'GCP Instances: {list_gcp_instances}\n')


aws_inventory = client.inventory.search(json={
        'timeFilter': { 
            'startTime' : start_time, 
            'endTime'   : end_time
        }, 
        'filters': [
            { 'field': 'resourceType', 'expression': 'eq', 'value':'ec2:instance'}
        ],
        'dataset': 'AwsCompliance'
    })
list_aws_instances = normalize_input(list(aws_inventory), 'Aws')
if check_truncation(list_aws_instances):
    print(f'WARNING: AWS Instances truncated at {MAX_RESULT_SET} records')
print(f'AWS Instances: {list_aws_instances}\n')

# SET WORK
all_instances = set(list_aws_instances) | set(list_gcp_instances)

# difference, not symmetric difference (^)
instances_without_agents = all_instances - set(list_agent_instances)

if len(instances_without_agents) > 0:
    print (f'Instances without agent:')
    for instance in instances_without_agents:
        print(f'\t{instance}')

print('\n')

if len(list_agent_instances) > 0:
    print(f'Instances with agent:')
    for instance in list_agent_instances:
        print(f'\t{instance}')
