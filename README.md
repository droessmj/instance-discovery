# Instance Discovery 

## Identify Instances without Lacework Agent

A script to review current Lacework instance inventories against active agents to help identify hosts lacking the Lacework agent.

Supports GCP & AWS. Azure to follow shortly.

## How to Run

`docker run -v ~/.lacework.toml:/home/user/.lacework.toml droessmj/instance-discovery --json`

``` python
pip install -r requirements.txt
python3 instances_without_agents.py --json
```

## Arguments

| short | long                              | default | help                                                                                                                                                                             |
| :---- | :-------------------------------- | :------ | :--------------------------------------------------------------------------------------------|
| `-h`  | `--help`                          |         | show this help message and exit                                                                                                                                                 |
|       | `--account`                       | `None`  | The Lacework account to use                                                                                                                                                  |
|       | `--subaccount`                    | `None`  | The Lacework sub-account to use                                                                                                                                                  |
|       | `--api-key`                       | `None`  | The Lacework API key to use                                                                                                                                                  |
|       | `--api-secret`                    | `None`  | The Lacework API secret to use                                                                                                                                                  |
| `-p`  | `--profile`                       | `None`  | The Lacework CLI profile to use                                                                                                                                                  |
|       | `--json`                          | `False` | Enable json output      
|       | `--debug`                         | `False` | Enable debug logging                                                                         |