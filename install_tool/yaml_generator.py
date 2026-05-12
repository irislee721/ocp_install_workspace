import json
import os
import yaml
import base64

class YAMLGenerator:
    def __init__(self, config, current_dir):
        self.config = config
        self.current_dir = current_dir
        self.v_info = config.get('version_info', {})
        # 兼容舊版結構或新版分離結構
        self.csi_info = config.get('csi_info', {}) 
        self.env = config.get('install_env', {})

    def generate_install_config(self):
        registry_auth = f"init:{self.env['REGISTRY_PASSWORD']}"
        auth_b64 = base64.b64encode(registry_auth.encode()).decode()
        registry_url = f"{self.env['BASTION_IP']}:8443"
        
        pull_secret_obj = {
            "auths": { f"{registry_url}": {"auth": auth_b64} }
        }

        cluster_name = self.env['CLUSTER_DOMAIN'].split('.')[0] if '.' in self.env['CLUSTER_DOMAIN'] else self.env['CLUSTER_DOMAIN']
        if not cluster_name: cluster_name = "ocp4"

        config_map = {
            "apiVersion": "v1",
            "baseDomain": self.env['BASE_DOMAIN'],
            "metadata": { "name": cluster_name },
            "networking": {
                "machineNetwork": [{"cidr": ".".join(self.env['BASTION_IP'].split('.')[:3]) + ".0/24"}],
                "clusterNetwork": [{"cidr": "10.128.0.0/14", "hostPrefix": 23}],
                "serviceNetwork": ["172.30.0.0/16"],
                "networkType": "OVNKubernetes"
            },
            "platform": {"none": {}},
            "fips": False,
            "pullSecret": json.dumps(pull_secret_obj),
            "sshKey": self.env['SSH_KEY'],
            "additionalTrustBundle": self.env['ADDITIONAL_TRUST_BUNDLE'],
            "imageDigestSources": [
                {"mirrors": [f"{registry_url}/ocp420/openshift/release"], "source": "quay.io/openshift-release-dev/ocp-v4.0-art-dev"},
                {"mirrors": [f"{registry_url}/ocp420/openshift/release-images"], "source": "quay.io/openshift-release-dev/ocp-release"}
            ]
        }

        mode = self.env['INSTALL_MODE']
        if mode == "compact":
            config_map["controlPlane"] = {"architecture": self.v_info.get('ARCHITECTURE', 'amd64'), "hyperthreading": "Enabled", "name": "master", "replicas": 3}
            config_map["compute"] = [{"architecture": self.v_info.get('ARCHITECTURE', 'amd64'), "hyperthreading": "Enabled", "name": "worker", "replicas": 0}]
        elif mode == "sno":
            config_map["controlPlane"] = {"architecture": self.v_info.get('ARCHITECTURE', 'amd64'), "hyperthreading": "Enabled", "name": "master", "replicas": 1}
            config_map["compute"] = []
        else:
            config_map["controlPlane"] = {"architecture": self.v_info.get('ARCHITECTURE', 'amd64'), "hyperthreading": "Enabled", "name": "master", "replicas": 3}
            config_map["compute"] = [{"architecture": self.v_info.get('ARCHITECTURE', 'amd64'), "hyperthreading": "Enabled", "name": "worker", "replicas": 3}]

        def str_representer(dumper, data):
            if len(data.splitlines()) > 1:
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        yaml.add_representer(str, str_representer)
        
        return yaml.dump(config_map, sort_keys=False, allow_unicode=True)

    def generate_imageset_config(self):
        operators_file = os.path.join(self.current_dir, 'operators.json')
        operators_list = []
        if os.path.exists(operators_file):
            with open(operators_file, 'r') as f:
                operators_list = json.load(f)
        
        op_blocks = []
        if operators_list:
            # 假設單一 Catalog，實際可擴展
            catalog = "registry.redhat.io/redhat/redhat-operator-index:v4.20"
            packages = []
            for op in operators_list:
                packages.append({
                    "name": op['name'],
                    "channels": [{"name": op.get('channel', 'stable'), "minVersion": op['minVersion'], "maxVersion": op['maxVersion']}]
                })
            op_blocks.append({"catalog": catalog, "packages": packages})

        # CSI Images
        additional_images = [
            {"name": "registry.redhat.io/ubi8/ubi:latest"},
            {"name": "registry.redhat.io/ubi9/ubi:latest"}
        ]
        
        csi_type = self.csi_info.get('CSI_TYPE', 'nfs-csi')
        
        if csi_type == 'nfs-csi':
            additional_images.extend([
                {"name": "registry.k8s.io/sig-storage/csi-resizer:v1.14.0"},
                {"name": "registry.k8s.io/sig-storage/csi-provisioner:v5.3.0"},
                {"name": "registry.k8s.io/sig-storage/nfsplugin:v4.12.1"}
            ])
        elif csi_type == 'trident':
            ver = self.csi_info.get('TRIDENT_INSTALLER', '25.02.1')
            additional_images.extend([
                {"name": f"docker.io/netapp/trident:{ver}"},
                {"name": f"docker.io/netapp/trident-operator:{ver}"},
                {"name": "registry.k8s.io/sig-storage/csi-provisioner:v5.2.0"}
            ])
        # 其他 CSI 類型可在此擴展

        ocp_major_minor = self.v_info.get('OCP_RELEASE', '4.20').rsplit('.', 1)[0]
        
        config_map = {
            "apiVersion": "mirror.openshift.io/v2alpha1",
            "kind": "ImageSetConfiguration",
            "archiveSize": 5,
            "mirror": {
                "platform": {
                    "channels": [{"name": f"stable-{ocp_major_minor}", "minVersion": self.v_info.get('OCP_RELEASE'), "maxVersion": self.v_info.get('OCP_RELEASE')}],
                    "graph": True
                },
                "operators": op_blocks,
                "additionalImages": additional_images
            }
        }

        return yaml.dump(config_map, sort_keys=False, allow_unicode=True)