import subprocess
import shutil
import os
import re
import time

class RegistryManager:
    def __init__(self, current_dir=None):
        self.current_dir = current_dir or os.getcwd()
        self.docker_config_dir = os.path.join(self.current_dir, ".docker")
    
    def _find_podman_or_docker(self):
        """尋找可用的 container CLI 工具"""
        for cmd in ['podman', 'docker']:
            if shutil.which(cmd):
                return cmd
        return None
    
    def start_operator_registry(self, config, status_callback=None):
        """
        啟動 Operator Registry 容器
        容器會在程式中斷時自動清除
        
        Returns:
            tuple: (success: bool, container_name: str, port: int)
        """
        v_info = config.get('version_info', {})
        ocp_release = v_info.get('OCP_RELEASE', '4.20.8')
        match = re.match(r'(\d+\.\d+)', ocp_release)
        ocp_version = match.group(1) if match else '4.20'
        
        catalog_image = f"registry.redhat.io/redhat/redhat-operator-index:v{ocp_version}"
        container_name = f"operator-registry-{ocp_version}"
        port = 50051
        
        container_cmd = self._find_podman_or_docker()
        if not container_cmd:
            return False, container_name, port
        
        authfile = os.path.join(os.path.expanduser("~"), ".docker", "config.json")
        
        # 檢查鏡像是否存在
        if status_callback:
            status_callback(f"📦 檢查鏡像是否存在: {catalog_image}")
        
        if not self._image_exists(container_cmd, catalog_image):
            if not self._pull_image(container_cmd, catalog_image, authfile, status_callback):
                return False, container_name, port
        
        # 清理舊容器
        self._cleanup_container(container_cmd, container_name, status_callback)
        
        # 啟動新容器
        if not self._start_container(container_cmd, container_name, port, authfile, catalog_image, status_callback):
            return False, container_name, port
        
        # 等待服務就緒
        time.sleep(5)
        
        return True, container_name, port
    
    def stop_operator_registry(self, container_name):
        """停止 Operator Registry 容器"""
        container_cmd = self._find_podman_or_docker()
        if container_cmd:
            subprocess.run([container_cmd, 'stop', container_name], capture_output=True, timeout=30)
    
    def _image_exists(self, container_cmd, catalog_image):
        """檢查鏡像是否存在"""
        try:
            result = subprocess.run(
                [container_cmd, 'images', '--format', '{{.Repository}}:{{.Tag}}', catalog_image],
                capture_output=True, text=True, timeout=30
            )
            return catalog_image in result.stdout
        except:
            return False
    
    def _pull_image(self, container_cmd, catalog_image, authfile, status_callback=None):
        """拉取鏡像"""
        if status_callback:
            status_callback(f"📥 鏡像不存在，開始拉取...")
            status_callback("⏳ 這可能需要 3-10 分鐘，請耐心等待...")
        
        try:
            result = subprocess.run(
                [container_cmd, 'pull', '--authfile', authfile, catalog_image],
                capture_output=True, text=True, timeout=600
            )
            if result.returncode != 0:
                if status_callback:
                    status_callback(f"❌ 拉取鏡像失敗: {result.stderr[:200]}")
                return False
            
            if status_callback:
                status_callback("✅ 鏡像拉取完成")
            return True
        except subprocess.TimeoutExpired:
            if status_callback:
                status_callback("❌ 拉取鏡像逾時 (10分鐘)")
            return False
    
    def _cleanup_container(self, container_cmd, container_name, status_callback=None):
        """清理舊容器"""
        if status_callback:
            status_callback(f"🧹 清理舊容器...")
        subprocess.run([container_cmd, 'stop', container_name], capture_output=True, timeout=30)
        subprocess.run([container_cmd, 'rm', container_name], capture_output=True, timeout=30)
    
    def _start_container(self, container_cmd, container_name, port, authfile, catalog_image, status_callback=None):
        """啟動容器"""
        if status_callback:
            status_callback(f"📦 啟動 Operator Registry 容器...")
        
        result = subprocess.run(
            [container_cmd, 'run', '-d', '--rm', '--name', container_name,
             '-p', f'{port}:{port}',
             '--authfile', authfile,
             catalog_image],
            capture_output=True, text=True, timeout=60
        )
        
        if result.returncode != 0:
            return False
        
        if status_callback:
            status_callback(f"✅ 容器已啟動，等待服務就緒...")
        
        return True