import json
import os

class ConfigManager:
    def __init__(self, config_file='tool_config.json', config_dir=None):
        if config_dir is None:
            config_dir = os.path.join(os.getcwd(), 'config')
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, os.path.basename(config_file))

        os.makedirs(self.config_dir, exist_ok=True)

        if not os.path.exists(self.config_file):
            self.create_default_config()
        
    def create_default_config(self):
        if 'tool' in self.config_file:
            default_config = {
                "version_info": {
                    "OCP_RELEASE": "4.20.8",
                    "RHEL_VERSION": "rhel9",
                    "ARCHITECTURE": "amd64",
                    "HELM_VERSION": "3.17.1",
                    "MIRROR_REGISTRY_VERSION": "latest"
                }
            }
        elif 'cluster' in self.config_file:
            default_config = {
                "version_info": {
                    "OCP_VERSION": "4.20"
                },
                "install_env": {
                    "INSTALL_MODE": "standard",
                    "CLUSTER_DOMAIN": "ocp4",
                    "BASE_DOMAIN": "example.com",
                    "BASTION_IP": "",
                    "BOOTSTRAP_IP": "",
                    "REGISTRY_PASSWORD": "P@ssw0rd",
                    "SSH_KEY": "",
                    "ADDITIONAL_TRUST_BUNDLE": "",
                    "MACHINE_NETWORK_CIDR": "",
                    "CLUSTER_NETWORK_CIDR": "10.128.0.0/14",
                    "CLUSTER_NETWORK_HOST_PREFIX": 23,
                    "SERVICE_NETWORK_CIDR": "172.30.0.0/16",
                "NETWORK_TYPE": "OVNKubernetes"
                }
            }
        else:
            default_config = {}
            
        self.save_config(default_config)

    def get_config(self):
        with open(self.config_file, 'r') as f:
            return json.load(f)

    def save_config(self, config):
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)