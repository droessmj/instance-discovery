# Instance Discovery 

## Identify Instances without Lacework Agent

A script to review current Lacework instance inventories against active agents to help identify hosts lacking the Lacework agent.

Supports GCP & AWS. Azure to follow shortly.

## How to Run

`docker run -v ~/.lacework.toml:/home/user/.lacework.toml droessmj/instance-discovery`

``` python
pip install -r requirements.txt
python3 instances_without_agents.py 
```
