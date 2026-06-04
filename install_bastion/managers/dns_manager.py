import os
from typing import Dict, Tuple
from .base_manager import BaseManager


class DNSManager(BaseManager):
    """DNS 管理類別"""
    
    def generate_config(self) -> str:
        """
        根據配置生成 DNS 設定檔內容
        """
        config = self.config
        bastion = config.get('bastion', {})
        bootstrap = config.get('bootstrap', {})
        master_nodes = config.get('master', [])
        worker_nodes = config.get('worker', [])
        infra_nodes = config.get('infra', [])
        cluster_name = config.get('clusterName', 'ocp4')
        base_domain = config.get('baseDomain', 'example.com')
        dns_upstream = config.get('dns_upstream', '8.8.8.8')
        
        bastion_ip = bastion.get('ip', '')
        bastion_name = bastion.get('name', 'bastion')
        bootstrap_ip = bootstrap.get('ip', '')
        bootstrap_name = bootstrap.get('name', 'bootstrap')
        
        dns_config = f"""domain={cluster_name}.{base_domain},{bastion_ip}/24,local
server={dns_upstream}

host-record={bastion_name}.{cluster_name}.{base_domain},{bastion_ip}
host-record={bootstrap_name}.{cluster_name}.{base_domain},{bootstrap_ip}
"""
        
        # Master 節點記錄
        for node in master_nodes:
            node_name = node.get('name', '')
            node_ip = node.get('ip', '')
            if node_name and node_ip:
                dns_config += f"host-record={node_name}.{cluster_name}.{base_domain},{node_ip}\n"
        
        # Worker/Infra 節點記錄（非 compact 模式）
        if config.get('mode') != 'compact':
            if infra_nodes:
                for node in infra_nodes:
                    node_name = node.get('name', '')
                    node_ip = node.get('ip', '')
                    if node_name and node_ip:
                        dns_config += f"host-record={node_name}.{cluster_name}.{base_domain},{node_ip}\n"
            if worker_nodes:
                for node in worker_nodes:
                    node_name = node.get('name', '')
                    node_ip = node.get('ip', '')
                    if node_name and node_ip:
                        dns_config += f"host-record={node_name}.{cluster_name}.{base_domain},{node_ip}\n"
        
        # API 和應用程式記錄
        dns_config += f"""
host-record=api.{cluster_name}.{base_domain},{bastion_ip}
host-record=api-int.{cluster_name}.{base_domain},{bastion_ip}
host-record=apps.{cluster_name}.{base_domain},{bastion_ip}
host-record=.apps.{cluster_name}.{base_domain},{bastion_ip}

address=/.apps.{cluster_name}.{base_domain}/{bastion_ip}
address=/api.{cluster_name}.{base_domain}/{bastion_ip}
address=/api-int.{cluster_name}.{base_domain}/{bastion_ip}
"""
        
        return dns_config
    
    def install(self) -> Tuple[bool, str]:
        """安裝並設定 DNS 伺服器"""
        self._log("開始設定 DNS 伺服器 (dnsmasq)...")
        
        # 安裝 dnsmasq
        success, _, err = self._run_command("yum install -y dnsmasq")
        if not success:
            return False, f"dnsmasq 安裝失敗: {err}"
        
        # 設定 dnsmasq 主配置
        interface = self.config.get('interface', 'eth0')
        self._run_command(
            f"sed -i 's/^#interface=/interface={interface}/' /etc/dnsmasq.conf"
        )
        # 如果沒有 interface 行，添加一個
        self._run_command(
            f"grep -q '^interface=' /etc/dnsmasq.conf || echo 'interface={interface}' >> /etc/dnsmasq.conf"
        )
        
        # 生成並寫入 DNS 配置
        dns_config = self.generate_config()
        dns_conf_dir = '/etc/dnsmasq.d'
        os.makedirs(dns_conf_dir, exist_ok=True)
        
        if not self._write_file(f'{dns_conf_dir}/dns.conf', dns_config):
            return False, "寫入 DNS 配置檔失敗"
        
        # 啟動 dnsmasq
        success, _, err = self._run_command("systemctl start dnsmasq")
        if not success:
            return False, f"dnsmasq 啟動失敗: {err}"
        
        self._run_command("systemctl enable dnsmasq")
        
        # 設定 NetworkManager DNS
        bastion_ip = self.config.get('bastion', {}).get('ip', '')
        if bastion_ip and interface:
            nmcli_cmd = f"nmcli connection modify {interface} ipv4.dns {bastion_ip}"
            self._run_command(nmcli_cmd)
            self._run_command("systemctl restart NetworkManager")
        
        if self._check_service_status("dnsmasq"):
            return True, "DNS 伺服器已成功配置並啟動"
        else:
            return False, "DNS 伺服器啟動失敗"
    
    def check_records(self) -> Tuple[bool, str]:
        """檢查 DNS 記錄"""
        self._log("開始檢查 DNS 記錄...")
        
        cluster_name = self.config.get('clusterName', 'ocp4')
        base_domain = self.config.get('baseDomain', 'example.com')
        
        # 測試 DNS 解析
        test_records = [
            f"api.{cluster_name}.{base_domain}",
            f"api-int.{cluster_name}.{base_domain}",
            f"bastion.{cluster_name}.{base_domain}",
        ]
        
        all_success = True
        failed_records = []
        success_records = []
        
        for record in test_records:
            success, stdout, _ = self._run_command(f"nslookup {record} 127.0.0.1")
            if success:
                success_records.append(f"{record} -> {stdout.split('Address: ')[-1].split('\n')[0] if 'Address:' in stdout else 'resolved'}")
            else:
                all_success = False
                failed_records.append(record)
        
        if all_success:
            return True, f"所有 DNS 記錄檢查通過: {'; '.join(success_records)}"
        else:
            return False, f"DNS 記錄檢查失敗: {', '.join(failed_records)}"