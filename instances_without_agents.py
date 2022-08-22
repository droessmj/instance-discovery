from datetime import datetime, timedelta, timezone
from pickle import NONE
import re
from xml.dom.minidom import Identified
from laceworksdk import LaceworkClient
import json
import argparse
import logging
import os

MAX_RESULT_SET = 500_000
LOOKBACK_DAYS = 1
GCP_INVENTORY_CACHE = {}
AWS_INVENTORY_CACHE = {}
AZURE_INVENTORY_CACHE = {}
AGENT_CACHE = {}
INSTANCE_CLUSTER_CACHE = {}


class InstanceResult():
    def __init__(self, instances_without_agents, instances_with_agents, agents_without_inventory) -> None:
        self.instances_without_agents = instances_without_agents
        self.instances_with_agents = instances_with_agents
        self.agents_without_inventory = agents_without_inventory

        self.instances_without_agents.sort()
        self.instances_with_agents.sort()
        self.agents_without_inventory.sort()

    def toJson(self):
        return json.dumps(self.__dict__, indent=4, sort_keys=True)

    def standardPrint(self):
        if len(self.instances_without_agents) > 0:
            print(f'Instances without agent:')
            for instance in self.instances_without_agents:
                print(f'\t{instance}')
            print('\n')

        if len(self.instances_with_agents) > 0:
            print(f'Instances reconciled with agent:')
            for instance in self.instances_with_agents:
                print(f'\t{instance}')
            print('\n')

        if len(self.agents_without_inventory) > 0:
            print(f'Agents without corresponding inventory:')
            for instance in self.agents_without_inventory:
                print(f'\t{instance}')
            print('\n')


def check_truncation(results):
    if type(results) == list:
        if len(results) >= MAX_RESULT_SET:
            return True
    return False


def normalize_input(input, identifier):
    normalized_output = list()
    if len(input) > 0:
        data = input['data']
        for r in data:
            # TODO: cleanup this mess....
            if identifier == 'agent':
                if ('tags' in r.keys() 
                     and 'VmProvider' in r['tags'].keys() 
                     and r['tags']['VmProvider'] == 'GCE'):
                    
                    normalized_output.append(r['tags']['InstanceId'])
                    AGENT_CACHE[r['tags']['InstanceId']] = 'gcp' + '/' + r['tags']['ProjectId'] + '/' + r['tags']['Hostname']

                elif ('tags' in r.keys() 
                      and 'VmProvider' in r['tags'].keys() 
                      and r['tags']['VmProvider'] == 'AWS'):

                    if 'InstanceId' in r['tags'].keys(): # EC2 use case - InstanceId is in URN
                        normalized_output.append(r['tags']['InstanceId'])
                        AGENT_CACHE[r['tags']['InstanceId']] = 'aws' + '/' + r['tags']['Account'] + '/' + r['tags']['Hostname']
                    else: # Fargate use case 
                        normalized_output.append(r['tags']['Hostname'])
                else:
                    normalized_output.append(r['hostname'])

            elif identifier == 'Aws':
                normalized_output.append(r['resourceConfig']['InstanceId'])
                AWS_INVENTORY_CACHE[r['resourceConfig']['InstanceId']] = (r['urn'], is_kubernetes(r,identifier), r['resourceConfig']['LaunchTime'])

            elif identifier == 'Gcp':
                normalized_output.append(r['resourceConfig']['id'])
                GCP_INVENTORY_CACHE[r['resourceConfig']['id']] = (r['urn'], is_kubernetes(r,identifier), r['resourceConfig']['creationTimestamp'])

            else:
                raise Exception (f'Error normalizing data set inputs! input: {input}, identifier: {identifier}')
    else:
        raise Exception (f'Empty input passed to normalize!')

    return normalized_output


# inspect resource to determine if it matches known identifiers marking it as a k8s node
def is_kubernetes(resource, identifier):
    if identifier == "Aws":
        if 'Tags' in resource['resourceConfig']:
            for t in resource['resourceConfig']['Tags']:
                if t['Key'] == 'eks:cluster-name':
                    INSTANCE_CLUSTER_CACHE[resource['resourceConfig']['InstanceId']] = t['Value']
                    return True
    elif identifier == "Gcp":
        if 'labels' in resource['resourceConfig']:
            for l in resource['resourceConfig']['labels']:
                if 'goog-gke-node' in l:
                    # TODO: INSTANCE_CLUSTER_CACHE
                    return True
    elif identifier == "Azure":
        pass
    else:
        raise Exception("Identifer not correctly passed to is_kubernetes!")

    return False


def get_urn_from_instanceid(instanceId):
    if instanceId in AWS_INVENTORY_CACHE:
        return AWS_INVENTORY_CACHE[instanceId]
    elif instanceId in GCP_INVENTORY_CACHE:
        return GCP_INVENTORY_CACHE[instanceId]
    elif instanceId in AZURE_INVENTORY_CACHE:
        return AZURE_INVENTORY_CACHE[instanceId]
    else:
        raise Exception (f"Input instanceId {instanceId} not found in cache!")


def retrieve_all_data_results(generator):

    results = list()
    count = 0
    page = next(generator,None)

    while page is not None:
        for record in page['data']:
            results.append(record)
            count += 1
        logger.debug(f"Running count: {count}")
        page = next(generator,None)

    # patching the data structure to avoid downstream manipulation atm
    resultset = {'data':results}
    return resultset


def main(args):

    if not args.profile and not args.account and not args.subaccount and not args.api_key and not args.api_secret:
        args.profile = 'default'

    try:
        client = LaceworkClient(
            account=args.account,
            subaccount=args.subaccount,
            api_key=args.api_key,
            api_secret=args.api_secret,
            profile=args.profile
        )
    except Exception:
        raise

    if args.debug:
        logger.setLevel('DEBUG')
        logging.basicConfig(level=logging.DEBUG)

    current_time = datetime.now(timezone.utc)
    start_time = current_time - timedelta(days=LOOKBACK_DAYS)
    start_time = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_time = current_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    ########
    # Agents
    ########
    all_agent_instances = client.agent_info.search(json={
            'timeFilter': { 
                'startTime' : start_time, 
                'endTime'   : end_time
            } 
        })
    list_agent_instances = normalize_input(retrieve_all_data_results(all_agent_instances), 'agent')
    if check_truncation(list_agent_instances):
        logger.warning(f'WARNING: Agent Instances truncated at {MAX_RESULT_SET} records')
    logger.debug(f'Agent Instances: {list_agent_instances}\n')

    ######
    # GCP
    ######
    gcp_inventory = client.inventory.search(json={
            'timeFilter': { 
                'startTime' : start_time, 
                'endTime'   : end_time
            }, 
            'filters': [
                { 'field': 'resourceType', 'expression': 'eq', 'value':'compute.googleapis.com/Instance'}
            ],
            'dataset': 'GcpCompliance'
        })
    gcp_data = retrieve_all_data_results(gcp_inventory)
    list_gcp_instances = normalize_input(gcp_data, 'Gcp')
    if check_truncation(list_gcp_instances):
        logger.warning(f'WARNING: GCP Instances truncated at {MAX_RESULT_SET} records')
    logger.debug(f'GCP Instances: {list_gcp_instances}\n')


    ######
    # AWS
    ######
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
    aws_data = retrieve_all_data_results(aws_inventory)
    list_aws_instances = normalize_input(aws_data, 'Aws')
    if check_truncation(list_aws_instances):
        logger.warning(f'WARNING: AWS Instances truncated at {MAX_RESULT_SET} records')
    logger.debug(f'AWS Instances: {list_aws_instances}\n')


    ##################
    # k8s filtering
    ##################
    k8s_filter_list = list()
    if args.kubernetes_info:
        for k in AWS_INVENTORY_CACHE.keys():
            if AWS_INVENTORY_CACHE[k][1] == True:
                k8s_filter_list.append(k)

        for k in GCP_INVENTORY_CACHE.keys():
            if GCP_INVENTORY_CACHE[k][1] == True:
                k8s_filter_list.append(k)

        for k in AZURE_INVENTORY_CACHE.keys():
            if AZURE_INVENTORY_CACHE[k][1] == True:
                k8s_filter_list.append(k)
        
        logger.debug(f'List of k8s instances: {k8s_filter_list}')


    #########
    # Set Ops
    #########
    all_instances_inventory = set(list_aws_instances) | set(list_gcp_instances)
    if args.kubernetes_info:
        all_instances_inventory = [i for i in all_instances_inventory if i in k8s_filter_list]
        logger.debug(f'All_instances_inventory {all_instances_inventory}')

    instances_without_agents = list()
    matched_instances = list()

    for instance_id in all_instances_inventory:
        normalized_urn = get_urn_from_instanceid(instance_id)[0]

        # TODO: Fix this hacky formatting
        if args.kubernetes_info:
            normalized_urn = [normalized_urn, INSTANCE_CLUSTER_CACHE[instance_id]]
       
        # TODO: These should be composable 
        if args.creation_time:
            print("creation time retrieved!")
            normalized_urn = [normalized_urn, get_urn_from_instanceid(instance_id)[2]]
            print(normalized_urn)

        if all(agent_instance not in instance_id for agent_instance in list_agent_instances):
            instances_without_agents.append(normalized_urn)

            # TODO: add secondary check for "premptible instances"
        else:
            matched_instances.append(normalized_urn)

    agents_without_inventory = list()

    # if we're doing k8s only, we need a separate check for this 
    # and atm it's currently low value add so we're going to implement this
    # later in time and track as a todo for the moment
    if not args.kubernetes_info:
        for instance in list_agent_instances:
            if not any(instance in instance_urn for instance_urn in matched_instances):
                if instance in AGENT_CACHE:
                    # pull out host name if we have it
                    instance = AGENT_CACHE[instance]
                agents_without_inventory.append(instance)

    logger.debug(f'Instances_without_agents:{instances_without_agents}')
    logger.debug(f'Matched_Instances:{matched_instances}')
    logger.debug(f'Agents_without_inventory:{agents_without_inventory}')

    instance_result = InstanceResult(instances_without_agents, matched_instances, agents_without_inventory)
    if args.json:
        print(instance_result.toJson())
    else:
        instance_result.standardPrint()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='A script to automatically issue container vulnerability scans to Lacework based on running containers'
    )
    parser.add_argument(
        '--account',
        default=os.environ.get('LW_ACCOUNT', None),
        help='The Lacework account to use'
    )
    parser.add_argument(
        '--subaccount',
        default=os.environ.get('LW_SUBACCOUNT', None),
        help='The Lacework sub-account to use'
    )
    parser.add_argument(
        '--api-key',
        dest='api_key',
        default=os.environ.get('LW_API_KEY', None),
        help='The Lacework API key to use'
    )
    parser.add_argument(
        '--api-secret',
        dest='api_secret',
        default=os.environ.get('LW_API_SECRET', None),
        help='The Lacework API secret to use'
    )
    parser.add_argument(
        '-p', '--profile',
        default=os.environ.get('LW_PROFILE', None),
        help='The Lacework CLI profile to use'
    )
    parser.add_argument(
        '--json',
        default=False,
        action='store_true',
        help='Emit results as json for machine processing'
    )
    parser.add_argument(
        '-c', '--creation-time',
        default=False,
        action='store_true',
        help='Emit creation time for identified instances'
    )
    parser.add_argument(
        '-k','--kubernetes-info',
        default=False,
        action='store_true',
        help='Emit results for instances identified as Kubernetes nodes'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        default=os.environ.get('LW_DEBUG', False),
        help='Enable debug logging'
    )
    args = parser.parse_args()

    logging.basicConfig(
        format='%(asctime)s %(name)s [%(levelname)s] %(message)s'
    )
    logger = logging.getLogger('instance-discovery')
    logger.setLevel(os.getenv('LOG_LEVEL', logging.INFO))

    main(args)