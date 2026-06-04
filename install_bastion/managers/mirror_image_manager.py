import os
from typing import Dict, Tuple
from .base_manager import BaseManager


class MirrorImageManager(BaseManager):
    """鏡像同步管理類別"""
    
    def install_oc_mirror(self) -> Tuple[bool, str]:
        """安裝 oc-mirror 工具"""
        self._log("安裝 oc-mirror...")
        
        ocmirror_source = self.config.get('ocmirrorSource', '/root/oc-mirror.tar.gz')
        target_path = '/usr/bin/oc-mirror'
        
        # 檢查是否已安裝
        if os.path.exists(target_path):
            success, stdout, _ = self._run_command(f"{target_path} version")
            version = stdout.strip() if success else "unknown"
            return True, f"oc-mirror 已安裝 (版本: {version})"
        
        # 檢查安裝包
        if not os.path.exists(ocmirror_source):
            return False, f"找不到 oc-mirror 安裝包: {ocmirror_source}"
        
        # 解壓並設定權限
        success, _, err = self._run_command(
            f"tar -xzf {ocmirror_source} -C /usr/bin/ && chmod +x /usr/bin/oc-mirror"
        )
        
        if not success:
            return False, f"安裝 oc-mirror 失敗: {err}"
        
        if os.path.exists(target_path):
            return True, "oc-mirror 安裝成功"
        else:
            return False, "oc-mirror 安裝後無法找到執行檔"
    
    def login_registry(self) -> Tuple[bool, str]:
        """登入 Mirror Registry"""
        self._log("登入 Mirror Registry...")
        
        bastion_name = self.config.get('bastion', {}).get('name', 'bastion')
        cluster_name = self.config.get('clusterName', 'ocp4')
        base_domain = self.config.get('baseDomain', 'example.com')
        registry_password = self.config.get('registryPassword', 'password')
        
        bastion_fqdn = f"{bastion_name}.{cluster_name}.{base_domain}"
        
        login_cmd = (
            f"podman login {bastion_fqdn}:8443 "
            f"-u init "
            f"-p {registry_password}"
        )
        
        success, stdout, stderr = self._run_command(login_cmd)
        
        if success:
            return True, f"登入 Mirror Registry 成功"
        else:
            return False, f"登入 Mirror Registry 失敗: {stderr}"
    
    def execute_mirror(self) -> Tuple[bool, str]:
        """執行鏡像同步"""
        self._log("開始鏡像同步...")
        
        image_set_file = self.config.get('imageSetFile', '/root/oc-mirror-workspace')
        reponame = self.config.get('reponame', 'ocp416')
        
        bastion_name = self.config.get('bastion', {}).get('name', 'bastion')
        cluster_name = self.config.get('clusterName', 'ocp4')
        base_domain = self.config.get('baseDomain', 'example.com')
        
        bastion_fqdn = f"{bastion_name}.{cluster_name}.{base_domain}"
        
        # 檢查 ImageSet 配置目錄
        if not os.path.exists(image_set_file):
            return False, f"找不到 ImageSet 配置目錄: {image_set_file}"
        
        # 檢查 imageset-config.yaml
        config_file = f"{image_set_file}/imageset-config.yaml"
        if not os.path.exists(config_file):
            return False, f"找不到 imageset-config.yaml: {config_file}"
        
        # 建立 cache 目錄
        cache_dir = "/root/mirror-cache"
        os.makedirs(cache_dir, exist_ok=True)
        
        # 執行鏡像同步
        mirror_cmd = (
            f"oc mirror -c {config_file} "
            f"--from file://{image_set_file} "
            f"docker://{bastion_fqdn}:8443/{reponame} "
            f"--cache-dir {cache_dir} "
            f"--v2"
        )
        
        self._log(f"執行鏡像同步命令: {mirror_cmd}")
        
        # 鏡像同步可能需要很長時間，設定較長的超時
        success, stdout, stderr = self._run_command(mirror_cmd, timeout=3600)  # 60分鐘
        
        if success:
            # 檢查同步結果
            result_msg = "鏡像同步完成"
            if "Wrote release signatures" in stdout:
                result_msg += " (包含 release signatures)"
            return True, result_msg
        else:
            return False, f"鏡像同步失敗: {stderr[:500]}"
    
    def run_full_mirror_workflow(self) -> Tuple[bool, str]:
        """執行完整的鏡像同步工作流程"""
        self._log("開始完整鏡像同步工作流程...")
        
        results = []
        
        # 1. 安裝 oc-mirror
        success, msg = self.install_oc_mirror()
        results.append(("安裝 oc-mirror", success, msg))
        if not success:
            return False, f"步驟失敗 - {msg}"
        
        # 2. 登入 Registry
        success, msg = self.login_registry()
        results.append(("登入 Registry", success, msg))
        if not success:
            return False, f"步驟失敗 - {msg}"
        
        # 3. 執行鏡像同步
        success, msg = self.execute_mirror()
        results.append(("鏡像同步", success, msg))
        
        # 彙總結果
        for step_name, step_success, step_msg in results:
            status = "✅" if step_success else "❌"
            self._log(f"{status} {step_name}: {step_msg}")
        
        if success:
            return True, "鏡像同步工作流程完成"
        else:
            return False, f"鏡像同步失敗 - {msg}"
    
    def check_mirror_status(self) -> Tuple[bool, str]:
        """檢查鏡像同步狀態"""
        self._log("檢查鏡像同步狀態...")
        
        bastion_name = self.config.get('bastion', {}).get('name', 'bastion')
        cluster_name = self.config.get('clusterName', 'ocp4')
        base_domain = self.config.get('baseDomain', 'example.com')
        reponame = self.config.get('reponame', 'ocp416')
        
        bastion_fqdn = f"{bastion_name}.{cluster_name}.{base_domain}"
        
        # 檢查 Registry 中的 repository
        success, stdout, _ = self._run_command(
            f"curl -sk -u init:{self.config.get('registryPassword', '')} "
            f"https://{bastion_fqdn}:8443/v2/_catalog 2>/dev/null"
        )
        
        if success and reponame in stdout:
            return True, f"鏡像倉庫中已有 {reponame} repository"
        elif success:
            return False, f"鏡像倉庫中未找到 {reponame} repository，可用: {stdout[:200]}"
        else:
            return False, "無法檢查鏡像倉庫狀態"