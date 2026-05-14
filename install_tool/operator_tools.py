import subprocess
import os
import re
import json
from datetime import datetime

class OperatorTools:
    def __init__(self):
        self.current_dir = os.getcwd()
        self.catalog_file = os.path.join(self.current_dir, "operator_catalog.json")
        
        # 尋找 oc-mirror（僅用於獲取詳細資訊）
        self.oc_mirror_cmd = self._find_oc_mirror()
    
    def _find_oc_mirror(self):
        # 僅在 ~/.local/bin 尋找 oc-mirror
        home_dir = os.path.expanduser("~")
        local_bin = os.path.join(home_dir, ".local/bin/oc-mirror")
        if os.path.exists(local_bin):
            self.oc_mirror_cmd = local_bin
        else:
            self.oc_mirror_cmd = "oc-mirror"
        
        self.authfile = os.path.join(os.path.expanduser("~"), ".docker", "config.json")

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
                    return {
                        'default_channel': pkg.get('default_channel', 'stable'),
                        'channels': []  # 詳細 channel 需要即時查詢
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
            config_path = os.path.join(self.current_dir, 'tool_config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    ocp_release = config.get('version_info', {}).get('OCP_RELEASE', '4.20')
                    match = re.match(r'(\d+\.\d+)', ocp_release)
                    if match:
                        return match.group(1)
            return '4.20'
        except Exception:
            return '4.20'
    
    def _fetch_package_channels_online(self, catalog, package):
        """在線查詢 package channels"""
        if not self.oc_mirror_cmd:
            return {'default_channel': 'stable', 'channels': []}
        
        try:
            cmd = [self.oc_mirror_cmd, 'list', 'operators', '--catalog', catalog, '--package', package]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                return self._parse_channels_output(result.stdout, package)
            
        except Exception as e:
            print(f"Error fetching channels: {e}")
        
        return {'default_channel': 'stable', 'channels': []}
    
    def _fetch_channel_versions_online(self, catalog, package, channel):
        """在線查詢 channel 版本"""
        if not self.oc_mirror_cmd:
            return []
        
        try:
            cmd = [self.oc_mirror_cmd, 'list', 'operators', '--catalog', catalog, 
                   '--package', package, '--channel', channel]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                versions = re.findall(r'v?(\d+\.\d+\.\d+)', result.stdout)
                return sorted(list(set(versions)), reverse=True)
            
        except Exception as e:
            print(f"Error fetching versions: {e}")
        
        return []