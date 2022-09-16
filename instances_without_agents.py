from datetime import datetime, timedelta, timezone
from pickle import NONE
from pydoc import cli
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


class OutputRecord():
    def __init__(self, urn, creation_time, is_kubernetes, subaccount, os_image):
        self.urn = urn
        self.creation_time = creation_time
        self.is_kubernetes = is_kubernetes
        self.os_image = os_image
        self.subaccount = subaccount
    
    def __str__(self) -> str:
        return json.dumps(self.__dict__, indent=4, sort_keys=True)

    def __repr__(self) -> str:
        return json.dumps(self.__dict__, indent=4, sort_keys=True)
    
    def __eq__(self, o: object) -> bool:
        return self.urn == o.urn


class InstanceResult():
    def __init__(self, instances_without_agents, instances_with_agents, agents_without_inventory) -> None:
        self.instances_without_agents = instances_without_agents
        self.instances_with_agents = instances_with_agents
        self.agents_without_inventory = agents_without_inventory

        self.instances_without_agents.sort(key=lambda x: x.urn)
        self.instances_with_agents.sort(key=lambda x: x.urn)
        self.agents_without_inventory.sort(key=lambda x: x.urn)

    def printJson(self):
        print(json.dumps(self.__dict__, indent=4, sort_keys=True, default=serialize))

    def printCsv(self):
        print("Identifier,CreationTime,Instance_without_agent,Instance_reconciled_with_agent,Agent_without_inventory,Os_image,Subaccount")
        for i in self.instances_without_agents:
            print(f'{i.urn},{i.creation_time},true,,,{i.os_image},{i.subaccount}')

        for i in self.instances_with_agents:
            print(f'{i.urn},{i.creation_time},,true,,{i.os_image},{i.subaccount}')

        for i in self.agents_without_inventory:
            print(f'{i.urn},{i.creation_time},,,true,{i.os_image},{i.subaccount}')


    def printStandard(self):
        if len(self.instances_without_agents) > 0:
            print(f'Instances without agent:')
            for instance in self.instances_without_agents:
                print(f'\t{instance.urn}')
            print('\n')

        if len(self.instances_with_agents) > 0:
            print(f'Instances reconciled with agent:')
            for instance in self.instances_with_agents:
                print(f'\t{instance.urn}')
            print('\n')

        if len(self.agents_without_inventory) > 0:
            print(f'Agents without corresponding inventory:')
            for instance in self.agents_without_inventory:
                print(f'\t{instance.urn}')
            print('\n')


def serialize(obj):
    """JSON serializer for objects not serializable by default json code"""
    return obj.__dict__


def get_all_tenant_subaccounts(client):
    return [i['accountName'] for i in client.user_profile.get()['data'][0]['accounts']]


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
                        if 'Account' in r['tags'].keys():
                            AGENT_CACHE[r['tags']['InstanceId']] = 'aws' + '/' + r['tags']['Account'] + '/' + r['tags']['Hostname']
                        else: # random Windows agent use case?
                            AGENT_CACHE[r['tags']['InstanceId']] = 'aws' + '/' + r['tags']['ProjectId'] + '/' + r['tags']['Hostname']
                    else: # Fargate use case 
                        normalized_output.append(r['tags']['Hostname'])

                elif ('tags' in r.keys() 
                      and 'VmProvider' in r['tags'].keys() 
                      and r['tags']['VmProvider'] == 'Microsoft.Compute'):

                    normalized_output.append(r['tags']['InstanceId'])
                    if 'Account' in r['tags'].keys():
                        AGENT_CACHE[r['tags']['InstanceId']] = 'azure' + '/' + r['tags']['Account'] + '/' + r['tags']['Hostname']
                    else: # random Windows agent use case?
                        AGENT_CACHE[r['tags']['InstanceId']] = 'azure' + '/' + r['tags']['ProjectId'] + '/' + r['tags']['Hostname']

                else:
                    normalized_output.append(r['hostname'])

            elif identifier == 'Aws':
                normalized_output.append(r['resourceConfig']['InstanceId'])
                os_image = str()
                AWS_INVENTORY_CACHE[r['resourceConfig']['InstanceId']] = (r['urn'], is_kubernetes(r,identifier), r['resourceConfig']['LaunchTime'], os_image)
            elif identifier == 'Gcp':
                # wrapping in a try/execpt so that a single parsing failure doesn't take out the entire output
                try:
                    normalized_output.append(r['resourceConfig']['id'])
                    # identify OS image from GCP instance
                    os_image = str()
                    try:
                        count = 0
                        for disk in r['resourceConfig']['disks']:
                            if 'licenses' in disk.keys():
                                os_image = r['resourceConfig']['disks'][count]['licenses']
                                break
                            elif 'initializeParams' in disk.keys():
                                params = r['resourceConfig']['disks']['initializeParams'] 
                                if 'sourceImage' in params:
                                    os_image = r['resourceConfig']['disks']['initializeParams']['sourceImage']
                                    break
                            count += 1
                    except:
                        logger.error('unable to parse os_image info for instance')

                    GCP_INVENTORY_CACHE[r['resourceConfig']['id']] = (r['urn'], is_kubernetes(r,identifier), r['resourceConfig']['creationTimestamp'], os_image)
                except Exception as ex:
                    logger.warning(f'Host with URN could not be parsed due to incomplete inventory information {r}')
                    pass
                
            elif identifier == 'Azure':
                normalized_output.append(r['resourceConfig']['vmId'])
                os_image = str()
                AZURE_INVENTORY_CACHE[r['resourceConfig']['vmId']] = (r['urn'], is_kubernetes(r,identifier), r['resourceConfig']['timeCreated'], os_image)

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
    for row in generator:
        for record in row['data']:
            results.append(record)

    # patching the data structure to avoid downstream manipulation atm
    resultset = {'data':results}
    return resultset


def main(args):

    if not args.profile and not args.account and not args.subaccount and not args.api_key and not args.api_secret:
        args.profile = 'default'


    # TODO: Implement input flag validations
    if args.csv and args.json:
        logger.error('Please specify only one of --csv or --json for output formatting')
        exit(1)
    elif args.profile and any([args.account, args.api_key, args.api_secret]):
        logger.error('If passing a profile, other credential values should not be specified.')
        exit(1)
    elif not args.profile and not all([args.account, args.api_key, args.api_secret]):
        logger.error('If passing credentials, please specify at least --account, --api-key, and --api-secret. --sub-account is optional for this input format.')
        exit(1)


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

    # magic to get the current subaccount for reporting on where things are
    lw_subaccount = client.account._session.__dict__['_subaccount'] 
    if lw_subaccount == None:
        # very hacky pull of the subdomain off the base_url
        lw_subaccount = client.account._session.__dict__['_base_url'].split('.')[0].split(':')[1][2::]

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
            'csp': 'GCP'
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
            'csp': 'AWS'
        })
    aws_data = retrieve_all_data_results(aws_inventory)
    list_aws_instances = normalize_input(aws_data, 'Aws')
    if check_truncation(list_aws_instances):
        logger.warning(f'WARNING: AWS Instances truncated at {MAX_RESULT_SET} records')
    logger.debug(f'AWS Instances: {list_aws_instances}\n')

    ######
    # Azure
    ######
    # TODO: Get VMSS instances
    azure_inventory = client.inventory.search(json={
            'timeFilter': { 
                'startTime' : start_time, 
                'endTime'   : end_time
            }, 
            'filters': [
                { 'field': 'resourceType', 'expression': 'eq', 'value':'microsoft.compute/virtualmachines'}
            ],
            'csp': 'Azure'
        })
    azure_data = retrieve_all_data_results(azure_inventory)
    list_azure_instances = normalize_input(azure_data, 'Azure')
    if check_truncation(list_azure_instances):
        logger.warning(f'WARNING: Azure Instances truncated at {MAX_RESULT_SET} records')
    logger.debug(f'Azure Instances: {list_azure_instances}\n')

    ##################

    #########
    # Set Ops
    #########
    all_instances_inventory = set(list_aws_instances) | set(list_gcp_instances) | set(list_azure_instances)

    instances_without_agents = list()
    matched_instances = list()

    for instance_id in all_instances_inventory:

        urn_result = get_urn_from_instanceid(instance_id)
        is_kubernetes = INSTANCE_CLUSTER_CACHE[instance_id] if instance_id in INSTANCE_CLUSTER_CACHE else False
        normalized_urn = OutputRecord(urn_result[0], urn_result[2], is_kubernetes, lw_subaccount, urn_result[3])

        if all(agent_instance not in instance_id for agent_instance in list_agent_instances):
            instances_without_agents.append(normalized_urn)

            # TODO: add secondary check for "premptible instances"
        else:
            matched_instances.append(normalized_urn)

    agents_without_inventory = list()

    for instance in list_agent_instances:
        if not any(instance in instance_urn.urn for instance_urn in matched_instances):
            if instance in AGENT_CACHE:
                # pull out host name if we have it
                instance = AGENT_CACHE[instance]
            o = OutputRecord(instance,'','',lw_subaccount,'')
            agents_without_inventory.append(o)

    logger.debug(f'Instances_without_agents:{instances_without_agents}')
    logger.debug(f'Matched_Instances:{matched_instances}')
    logger.debug(f'Agents_without_inventory:{agents_without_inventory}')

    instance_result = InstanceResult(instances_without_agents, matched_instances, agents_without_inventory)
    if args.json:
        instance_result.printJson()
    elif args.csv:
        instance_result.printCsv()
    else:
        instance_result.printStandard()


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
        '--csv',
        default=False,
        action='store_true',
        help='Emit results as csv'
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