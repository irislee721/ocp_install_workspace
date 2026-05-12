import json
import os

class ConfigManager:
    def __init__(self, config_file='tool_config.json'):
        self.config_file = config_file
        if not os.path.exists(self.config_file):
            self.create_default_config()
        
    def create_default_config(self):
        # 根據文件名決定默認內容
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
                "install_env": {
                    "INSTALL_MODE": "standard",
                    "CLUSTER_DOMAIN": "",
                    "BASE_DOMAIN": "",
                    "BASTION_IP": "",
                    "BOOTSTRAP_IP": "",
                    "MASTER01_IP": "",
                    "MASTER02_IP": "",
                    "MASTER03_IP": "",
                    "INFRA01_IP": "",
                    "INFRA02_IP": "",
                    "INFRA03_IP": "",
                    "WORKER01_IP": "",
                    "WORKER02_IP": "",
                    "WORKER03_IP": "",
                    "REGISTRY_PASSWORD": "P@ssw0rd",
                    "SSH_KEY": "",
                    "ADDITIONAL_TRUST_BUNDLE": ""
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