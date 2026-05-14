import json
import os
import yaml
import re
import base64

class LiteralString(str):
    """用於標記需要在 YAML 中使用 | 的字串"""
    pass

class QuotedString(str):
    """用於標記需要在 YAML 中使用引號的字串"""
    pass

class YAMLGenerator:
    def __init__(self, config, current_dir):
        self.config = config
        self.current_dir = current_dir
        self.v_info = config.get('version_info', {})
        self.csi_info = config.get('csi_info', {}) 
        self.env = config.get('install_env', {})

    @staticmethod
    def is_valid_ipv4(ip):
        """驗證 IPv4 格式"""
        if not ip:
            return False
        pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
        match = re.match(pattern, ip)
        if not match:
            return False
        # 檢查每個數字是否在 0-255 範圍內
        for group in match.groups():
            if int(group) > 255:
                return False
        return True

    def validate_ips(self):
        """驗證所有 IP 欄位"""
        ip_fields = []
        
        # Master IPs
        for i in range(1, 4):
            key = f"MASTER{i:02d}_IP"
            if key in self.env and self.env[key]:
                ip_fields.append((key, self.env[key]))
        
        # Infra IPs
        for i in range(1, 4):
            key = f"INFRA{i:02d}_IP"
            if key in self.env and self.env[key]:
                ip_fields.append((key, self.env[key]))
        
        # Worker IPs
        for i in range(1, 10):
            key = f"WORKER{i:02d}_IP"
            if key in self.env and self.env[key]:
                ip_fields.append((key, self.env[key]))
        
        # Bastion IP
        if 'BASTION_IP' in self.env:
            ip_fields.append(('BASTION_IP', self.env['BASTION_IP']))
        
        # Bootstrap IP
        if 'BOOTSTRAP_IP' in self.env and self.env['BOOTSTRAP_IP']:
            ip_fields.append(('BOOTSTRAP_IP', self.env['BOOTSTRAP_IP']))
        
        invalid_ips = []
        for field_name, ip in ip_fields:
            if not self.is_valid_ipv4(ip):
                invalid_ips.append(f"{field_name}: {ip}")
        
        return invalid_ips

    def get_ocp_version_path(self):
        """從 OCP_RELEASE 提取版本號用於 image path"""
        ocp_release = self.v_info.get('OCP_RELEASE', '4.20.8')
        # 提取主版本和次版本，例如 4.20.8 -> 4.20
        match = re.match(r'(\d+)\.(\d+)', ocp_release)
        if match:
            major = match.group(1)
            minor = match.group(2)
            return f"ocp{major}{minor}"
        return "ocp420"  # 預設值

    def get_registry_fqdn(self):
        """生成 registry 的 FQDN"""
        cluster_name = self.env.get('CLUSTER_DOMAIN', 'ocp4')
        base_domain = self.env.get('BASE_DOMAIN', 'example.com')
        
        # 如果 CLUSTER_DOMAIN 已經包含完整域名，就使用它
        if '.' in cluster_name:
            hostname = cluster_name
        else:
            hostname = f"{cluster_name}.{base_domain}"
        
        return f"bastion.{hostname}"

    def generate_install_config(self):
        # 驗證 IP 格式
        invalid_ips = self.validate_ips()
        if invalid_ips:
            raise ValueError(f"Invalid IPv4 addresses found:\n" + "\n".join(invalid_ips))
        
        # 生成 Registry URL (需求1)
        registry_fqdn = self.get_registry_fqdn()
        registry_url = f"{registry_fqdn}:8443"

        registry_password = self.env.get('REGISTRY_PASSWORD', '')
        registry_auth = f"init:{registry_password}"
        auth_b64 = base64.b64encode(registry_auth.encode()).decode()
        
        pull_secret_obj = {
            "auths": {
                registry_url: {"auth": auth_b64}
            }
        }

        # 提取 cluster name
        cluster_domain = self.env.get('CLUSTER_DOMAIN', 'ocp4')
        if '.' in cluster_domain:
            cluster_name = cluster_domain.split('.')[0]
            if not cluster_name:
                cluster_name = "ocp4"
        else:
            cluster_name = cluster_domain
        if not cluster_name:
            cluster_name = "ocp4"

        master_count = sum(1 for k in self.env if k.startswith('MASTER') and k.endswith('_IP') and self.env[k])
        worker_count = sum(1 for k in self.env if k.startswith('WORKER') and k.endswith('_IP') and self.env[k])

        if master_count == 0:
            master_count = 3  # 預設值

        config_map = {
            "apiVersion": "v1",
            "baseDomain": self.env.get('BASE_DOMAIN', ''),
            "metadata": {"name": cluster_name},
            "networking": {},
            "platform": {"none": {}},
            "fips": False,
            "pullSecret": json.dumps(pull_secret_obj),
            "sshKey": self.env.get('SSH_KEY', ''),  # 需求2: 字串處理在 YAML dump 時處理
            "additionalTrustBundle": self.env.get('ADDITIONAL_TRUST_BUNDLE', ''),
            "imageDigestSources": [
                {
                    "mirrors": [f"{registry_url}/{self.get_ocp_version_path()}/openshift/release"],
                    "source": "quay.io/openshift-release-dev/ocp-v4.0-art-dev"
                },
                {
                    "mirrors": [f"{registry_url}/{self.get_ocp_version_path()}/openshift/release-images"],
                    "source": "quay.io/openshift-release-dev/ocp-release"
                }
            ]
        }

        # 需求4: Networking 配置
        networking = {}

        # machineNetwork (可選，若沒有輸入則不產生)
        machine_cidr = self.env.get('MACHINE_NETWORK_CIDR', '').strip()
        
        # 只有當 machine_cidr 不為空時才添加到 networking
        if machine_cidr:
            networking["machineNetwork"] = [{"cidr": machine_cidr}]
        
        # clusterNetwork (預設 10.128.0.0/14)
        cluster_cidr = self.env.get('CLUSTER_NETWORK_CIDR', '10.128.0.0/14')
        host_prefix = int(self.env.get('CLUSTER_NETWORK_HOST_PREFIX', 23))
        networking["clusterNetwork"] = [{"cidr": cluster_cidr, "hostPrefix": host_prefix}]
        
        # serviceNetwork (預設 172.30.0.0/16)
        service_cidr = self.env.get('SERVICE_NETWORK_CIDR', '172.30.0.0/16')
        networking["serviceNetwork"] = [service_cidr]
        
        networking["networkType"] = self.env.get('NETWORK_TYPE', 'OVNKubernetes')
        config_map["networking"] = networking

        install_mode = self.env.get('INSTALL_MODE', 'standard')
        architecture = self.v_info.get('ARCHITECTURE', 'amd64')
        
        if install_mode == "sno":
            config_map["controlPlane"] = {
                "architecture": architecture,
                "hyperthreading": "Enabled",
                "name": "master",
                "replicas": 1
            }
            config_map["compute"] = []
        elif install_mode == "compact":
            config_map["controlPlane"] = {
                "architecture": architecture,
                "hyperthreading": "Enabled",
                "name": "master",
                "replicas": master_count
            }
            config_map["compute"] = [{
                "architecture": architecture,
                "hyperthreading": "Enabled",
                "name": "worker",
                "replicas": 0
            }]
        else:  # standard
            config_map["controlPlane"] = {
                "architecture": architecture,
                "hyperthreading": "Enabled",
                "name": "master",
                "replicas": master_count
            }
            if worker_count > 0:
                config_map["compute"] = [{
                    "architecture": architecture,
                    "hyperthreading": "Enabled",
                    "name": "worker",
                    "replicas": worker_count
                }]
            else:
                config_map["compute"] = [{
                    "architecture": architecture,
                    "hyperthreading": "Enabled",
                    "name": "worker",
                    "replicas": 0
                }]

        return self._dump_yaml(config_map)

    def _dump_yaml(self, config_map):
        """自定義 YAML dump，處理特殊格式需求"""
        # additionalTrustBundle 且包含換行，替換為 LiteralString
        if 'additionalTrustBundle' in config_map:
            trust_bundle = config_map['additionalTrustBundle']
            if trust_bundle and '\n' in trust_bundle:
                config_map['additionalTrustBundle'] = LiteralString(trust_bundle)
    
        # SSH Key 使用單引號
        if 'sshKey' in config_map:
            config_map['sshKey'] = QuotedString(config_map['sshKey'])
    
        # 定義 representer
        def literal_str_representer(dumper, data):
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    
        def quoted_str_representer(dumper, data):
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style="'")
        
        def str_representer(dumper, data):
            if '\n' in data:
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        
        # 註冊 representer
        yaml.add_representer(LiteralString, literal_str_representer)
        yaml.add_representer(QuotedString, quoted_str_representer)
        yaml.add_representer(str, str_representer)
        
        return yaml.dump(config_map, sort_keys=False, allow_unicode=True, default_flow_style=False)

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
    
    def generate_agent_config(self):
        """生成 AgentConfig YAML"""
        # 驗證 IP 格式
        invalid_ips = self.validate_ips()
        if invalid_ips:
            raise ValueError(f"Invalid IPv4 addresses found:\n" + "\n".join(invalid_ips))

        cluster_name = self.env.get('CLUSTER_DOMAIN', 'ocp4')
        if '.' in cluster_name:
            cluster_name = cluster_name.split('.')[0]
        if not cluster_name:
            cluster_name = "ocp4"

        # rendezvousIP 等於 MASTER01_IP
        rendezvous_ip = self.env.get('MASTER01_IP', '')
        if not rendezvous_ip:
            raise ValueError("MASTER01_IP is required for AgentConfig")

        bastion_ip = self.env.get('BASTION_IP', '')
        gateway_ip = self.env.get('GATEWAY_IP', '')

        # 構建 hosts 列表
        hosts = []

        # Master nodes
        for i in range(1, 4):
            ip_key = f"MASTER{i:02d}_IP"
            mac_key = f"MASTER{i:02d}_MAC"
            iface_key = f"MASTER{i:02d}_INTERFACE"
            device_key = f"MASTER{i:02d}_DEVICE"

            ip = self.env.get(ip_key, '')
            if ip:
                mac = self.env.get(mac_key, 'BC:24:11:99:B8:1B')
                interface = self.env.get(iface_key, 'ens18')
                device = self.env.get(device_key, '/dev/sda')

                host = self._build_host_entry(
                    hostname=f"master-{i}",
                    role="master",
                    ip=ip,
                    mac=mac,
                    interface=interface,
                    device=device,
                    bastion_ip=bastion_ip,
                    gateway_ip=gateway_ip
                )
                hosts.append(host)

        # Infra nodes
        for i in range(1, 4):
            ip_key = f"INFRA{i:02d}_IP"
            mac_key = f"INFRA{i:02d}_MAC"
            iface_key = f"INFRA{i:02d}_INTERFACE"
            device_key = f"INFRA{i:02d}_DEVICE"

            ip = self.env.get(ip_key, '')
            if ip:
                mac = self.env.get(mac_key, 'BC:24:11:99:B8:1B')
                interface = self.env.get(iface_key, 'ens18')
                device = self.env.get(device_key, '/dev/sda')

                host = self._build_host_entry(
                    hostname=f"infra-{i}",
                    role="worker",
                    ip=ip,
                    mac=mac,
                    interface=interface,
                    device=device,
                    bastion_ip=bastion_ip,
                    gateway_ip=gateway_ip
                )
                hosts.append(host)

        # Worker nodes
        for i in range(1, 10):
            ip_key = f"WORKER{i:02d}_IP"
            mac_key = f"WORKER{i:02d}_MAC"
            iface_key = f"WORKER{i:02d}_INTERFACE"
            device_key = f"WORKER{i:02d}_DEVICE"

            ip = self.env.get(ip_key, '')
            if ip:
                mac = self.env.get(mac_key, 'BC:24:11:99:B8:1B')
                interface = self.env.get(iface_key, 'ens18')
                device = self.env.get(device_key, '/dev/sda')

                host = self._build_host_entry(
                    hostname=f"worker-{i}",
                    role="worker",
                    ip=ip,
                    mac=mac,
                    interface=interface,
                    device=device,
                    bastion_ip=bastion_ip,
                    gateway_ip=gateway_ip
                )
                hosts.append(host)

        config_map = {
            "apiVersion": "v1alpha1",
            "kind": "AgentConfig",
            "metadata": {
                "name": cluster_name
            },
            "rendezvousIP": rendezvous_ip,
            "additionalNTPSources": [bastion_ip] if bastion_ip else [],
            "hosts": hosts
        }

        return self._dump_yaml(config_map)

    def _build_host_entry(self, hostname, role, ip, mac, interface, device, bastion_ip, gateway_ip):
        """構建單個 host 條目"""
        # 計算 prefix-length (從 MACHINE_NETWORK_CIDR 或預設 24)
        machine_cidr = self.env.get('MACHINE_NETWORK_CIDR', '')
        prefix_length = 24
        if machine_cidr and '/' in machine_cidr:
            try:
                prefix_length = int(machine_cidr.split('/')[1])
            except:
                pass

        return {
            "hostname": hostname,
            "role": role,
            "interfaces": [
                {
                    "name": interface,
                    "macAddress": mac.upper()
                }
            ],
            "networkConfig": {
                "interfaces": [
                    {
                        "name": interface,
                        "type": "ethernet",
                        "state": "up",
                        "mac-address": mac.upper(),
                        "ipv4": {
                            "enabled": True,
                            "address": [
                                {
                                    "ip": ip,
                                    "prefix-length": prefix_length
                                }
                            ],
                            "dhcp": False
                        }
                    }
                ],
                "dns-resolver": {
                    "config": {
                        "server": [bastion_ip] if bastion_ip else []
                    }
                },
                "routes": {
                    "config": [
                        {
                            "destination": "0.0.0.0/0",
                            "next-hop-address": gateway_ip if gateway_ip else "",
                            "next-hop-interface": interface,
                            "table-id": 254
                        }
                    ]
                }
            },
            "rootDeviceHints": {
                "deviceName": device
            }
        }