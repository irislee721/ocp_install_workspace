import subprocess
import os

class OperatorTools:
    def __init__(self):
        # 嘗試從環境變量或當前目錄尋找 oc-mirror
        self.oc_mirror_cmd = "oc-mirror"
        # 如果當前目錄下有 usr/bin/oc-mirror，優先使用
        current_dir = os.getcwd()
        local_bin = os.path.join(current_dir, "usr/bin/oc-mirror")
        if os.path.exists(local_bin):
            self.oc_mirror_cmd = local_bin

    def get_catalogs(self):
        try:
            # 模擬或實際執行
            # result = subprocess.run([self.oc_mirror_cmd, 'list', 'operators', '--catalogs', '--version=4.20'], capture_output=True, text=True)
            # 解析 result.stdout
            return [
                "registry.redhat.io/redhat/redhat-operator-index:v4.20",
                "registry.redhat.io/redhat/certified-operator-index:v4.20",
                "registry.redhat.io/redhat/community-operator-index:v4.20"
            ]
        except Exception as e:
            print(f"Error: {e}")
            return []

    def get_packages(self, catalog):
        try:
            # result = subprocess.run([self.oc_mirror_cmd, 'list', 'operators', '--catalog', catalog], capture_output=True, text=True)
            return [
                "cluster-logging",
                "kubevirt-hyperconverged",
                "openshift-gitops-operator",
                "advanced-cluster-management",
                "metallb-operator"
            ]
        except Exception as e:
            return []

    def get_package_versions(self, catalog, package):
        try:
            # result = subprocess.run([self.oc_mirror_cmd, 'list', 'operators', '--catalog', catalog, '--package', package], capture_output=True, text=True)
            return [
                "1.0.0", "1.0.1", "1.1.0", "1.2.0", "2.0.0"
            ]
        except Exception as e:
            return []