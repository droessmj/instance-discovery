from re import A
import instances_without_agents

# bad test I know..just working up to valuable stuff
def test_instance_result_json_result():
    object = instances_without_agents.InstanceResult(list("a"),list("b"),list("c"))
    json = object.toJson()
    assert('"a"' in json and '"b"' in json and '"c"' in json)

def test_check_trucation_true():
    results = list([i for i in range(600_000)])
    assert(instances_without_agents.check_truncation(results) == True)

def test_check_trucation_false():
    results = list([i for i in range(100)])
    assert(instances_without_agents.check_truncation(results) == False)

# def test_normalization_agent_data_ec2():

# def test_normalization_agent_data_fargate():

# def test_normalization_aws():

# def test_normalization_gcp():

# def test_normalization_azure():