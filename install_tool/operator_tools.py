import subprocess
import os
import re
import json
from datetime import datetime

class OperatorTools:
    def __init__(self):
        self.current_dir = os.getcwd()
        self.config_dir = os.path.join(self.current_dir, 'config')
        os.makedirs(self.config_dir, exist_ok=True)

        self.catalog_file = os.path.join(self.config_dir, "operator_catalog.json")
        self.authfile = os.path.join(os.path.expanduser("~"), ".docker", "config.json")
        
        # 尋找 oc-mirror（僅用於獲取詳細資訊）
        self.oc_mirror_cmd = self._find_oc_mirror()
    
    def _find_oc_mirror(self):
        """尋找 oc-mirror 命令，返回路徑或 None"""
        # 優先使用 ~/.local/bin
        local_bin = os.path.join(os.path.expanduser("~"), ".local/bin/oc-mirror")
        if os.path.exists(local_bin):
            return local_bin
        
        # 然後是當前工作目錄
        current_bin = os.path.join(self.current_dir, "usr/bin/oc-mirror")
        if os.path.exists(current_bin):
            return current_bin
        
        # 最後嘗試系統 PATH
        import shutil
        if shutil.which('oc-mirror'):
            return 'oc-mirror'
        
        return None

    def get_ocp_version(self):
        """從 tool_config.json 或 operator_catalog.json 獲取 OCP 版本"""
        # 先嘗試從 operator_catalog.json 獲取
        catalog_data = self._load_catalog_data()
        if catalog_data and 'ocp_version' in catalog_data:
            return catalog_data['ocp_version']
        
        # 再嘗試從 tool_config.json 獲取
        return self._get_ocp_version_from_config()

    def _load_catalog_data(self):
        """從快取檔案載入 catalog 資料"""
        if not os.path.exists(self.catalog_file):
            return None
        
        try:
            with open(self.catalog_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading catalog data: {e}")
            return None

    def get_catalogs(self):
        """
        需求1: 從快取檔案獲取 catalog 列表
        """
        catalog_data = self._load_catalog_data()
        if catalog_data and 'catalogs' in catalog_data:
            return list(catalog_data['catalogs'].keys())
        
        # 如果沒有快取，返回預設值
        version = self._get_ocp_version_from_config()
        return [f"registry.redhat.io/redhat/redhat-operator-index:v{version}"]
    
    def get_packages(self, catalog):
        """
        需求2: 從快取檔案獲取 package 列表（快速響應）
        """
        catalog_data = self._load_catalog_data()
        if catalog_data and 'catalogs' in catalog_data:
            catalog_info = catalog_data['catalogs'].get(catalog, {})
            packages = catalog_info.get('packages', [])
            # 返回 package 名稱列表
            return [p['name'] for p in packages]
        
        return []
    
    def get_package_channels(self, catalog, package):
        """
        需求3: 獲取指定 package 的 channel 資訊
        如果快取中有，直接返回；否則使用 oc-mirror 查詢
        """
        # 先從快取中查找
        catalog_data = self._load_catalog_data()
        if catalog_data and 'catalogs' in catalog_data:
            catalog_info = catalog_data['catalogs'].get(catalog, {})
            packages = catalog_info.get('packages', [])
            
            for pkg in packages:
                if pkg['name'] == package:
                    default_channel = pkg.get('default_channel', 'stable')
                    # 如果快取中只有 default_channel 而沒有詳細 channels，
                    # 返回 default_channel 作為唯一選項
                    return {
                        'default_channel': default_channel,
                        'channels': [{'name': default_channel}]  # 使用 default_channel 作為可用 channel
                    }
        
        # 如果快取中沒有，使用 oc-mirror 查詢
        return self._fetch_package_channels_online(catalog, package)
    
    def get_channel_versions(self, catalog, package, channel):
        """
        獲取指定 channel 的版本列表（需要即時查詢）
        """
        return self._fetch_channel_versions_online(catalog, package, channel)
    
    def _get_ocp_version_from_config(self):
        """從 tool_config.json 獲取 OCP 版本"""
        try:
            # 嘗試多個可能的路徑
            possible_paths = [
                os.path.join(self.config_dir, 'tool_config.json'),
                os.path.join(os.getcwd(), 'tool_config.json')
            ]

            for config_path in possible_paths:
                if os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                        ocp_release = config.get('version_info', {}).get('OCP_RELEASE', '4.20')
                        match = re.match(r'(\d+\.\d+)', ocp_release)
                        if match:
                            return match.group(1)
                        break

            return '4.20'
        except Exception as e:
            print(f"Error reading OCP version: {e}")
            return '4.20'    

    def _fetch_channel_versions_online(self, catalog, package, channel):
        """在線查詢 channel 版本"""
        if not self.oc_mirror_cmd:
            return []
        
        try:
            cmd = [self.oc_mirror_cmd, 'list', 'operators', '--catalog', catalog, 
                   '--package', package, '--channel', channel]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode == 0:
                versions = re.findall(r'v?(\d+\.\d+\.\d+)', result.stdout)
                return sorted(list(set(versions)), reverse=True)
            
        except Exception as e:
            print(f"Error fetching versions: {e}")
        
        return []