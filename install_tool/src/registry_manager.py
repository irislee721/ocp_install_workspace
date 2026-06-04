import subprocess
import shutil
import os
import re
import time
from typing import Tuple, Optional, Callable

"""
RegistryManager	ContainerCommand 策略類別	將容器命令檢測封裝為獨立類別
類別常數	DEFAULT_*、TIMEOUT_*、WAIT_* 提取為常數
屬性裝飾器	container_cmd 使用 @property 延遲初始化
單一職責方法	每個方法只做一件事（如 _ensure_image_exists）
"""

class ContainerCommand:
    """容器命令封裝類別 - 策略模式"""
    
    SUPPORTED_COMMANDS = ['podman', 'docker']
    
    @classmethod
    def detect(cls) -> Optional[str]:
        """檢測可用的容器命令"""
        for cmd in cls.SUPPORTED_COMMANDS:
            if shutil.which(cmd):
                return cmd
        return None
    
    @classmethod
    def is_available(cls) -> bool:
        """檢查是否有可用的容器工具"""
        return cls.detect() is not None

class RegistryManager:

    DEFAULT_OCP_VERSION = '4.20'
    DEFAULT_OCP_RELEASE = '4.20.8'
    DEFAULT_PORT = 50051
    DEFAULT_IMAGE_TEMPLATE = "registry.redhat.io/redhat/redhat-operator-index:v{version}"
    CONTAINER_NAME_TEMPLATE = "operator-registry-{version}"

    TIMEOUT_IMAGE_CHECK = 30
    TIMEOUT_PULL = 600
    TIMEOUT_RUN = 60
    TIMEOUT_STOP = 30
    TIMEOUT_LOG = 10

    WAIT_AFTER_START = 15
    WAIT_SERVICE_READY = 20

    def __init__(self, current_dir=None):
        self.current_dir = current_dir or os.getcwd()
        self.docker_config_dir = os.path.join(self.current_dir, ".docker")
        self._container_cmd = None 

    @property
    def container_cmd(self) -> Optional[str]:
        """取得可用的容器命令（延遲載入）"""
        if self._container_cmd is None:
            self._container_cmd = ContainerCommand.detect()
        return self._container_cmd    

    @property
    def is_available(self) -> bool:
        """檢查容器工具是否可用"""
        return self.container_cmd is not None

    def start_operator_registry(
        self, 
        config: dict, 
        status_callback: Optional[Callable[[str], None]] = None
    ) -> Tuple[bool, str, int]:
        """
        啟動 Operator Registry 容器
        
        Args:
            config: 配置字典，包含 version_info
            status_callback: 狀態回調函數
            
        Returns:
            (success, container_name, port)
        """
        if not self.is_available:
            self._notify(status_callback, "❌ 找不到 podman 或 docker 命令")
            return False, "", self.DEFAULT_PORT
        
        # 解析版本資訊
        ocp_version = self._parse_ocp_version(config)
        catalog_image = self.DEFAULT_IMAGE_TEMPLATE.format(version=ocp_version)
        container_name = self.CONTAINER_NAME_TEMPLATE.format(version=ocp_version)
        
        # 取得認證檔案
        authfile = self._get_authfile()
        
        # 步驟1: 檢查並拉取映像
        if not self._ensure_image_exists(catalog_image, authfile, status_callback):
            return False, container_name, self.DEFAULT_PORT
        
        # 步驟2: 清理舊容器
        self._cleanup_old_container(container_name, status_callback)
        
        # 步驟3: 啟動容器
        if not self._start_new_container(container_name, catalog_image, authfile, status_callback):
            return False, container_name, self.DEFAULT_PORT
        
        # 步驟4: 等待服務就緒
        self._notify(status_callback, f"⏳ 等待服務就緒 ({self.WAIT_SERVICE_READY}秒)...")
        time.sleep(self.WAIT_SERVICE_READY)
        
        return True, container_name, self.DEFAULT_PORT
    
    def stop_operator_registry(self, container_name: str) -> bool:
        """
        停止 Operator Registry 容器
        
        Args:
            container_name: 容器名稱
            
        Returns:
            是否成功停止
        """
        if not self.is_available:
            return False
        
        try:
            subprocess.run(
                [self.container_cmd, 'stop', container_name],
                capture_output=True,
                timeout=self.TIMEOUT_STOP
            )
            return True
        except Exception:
            return False

    def check_container_running(self, container_name: str) -> bool:
        """檢查容器是否正在運行"""
        return self._check_container_status(container_name, running_only=True)
    
    def check_container_exists(self, container_name: str) -> bool:
        """檢查容器是否存在（包括已停止的）"""
        return self._check_container_status(container_name, running_only=False)

    def get_container_details(self, container_name: str) -> Optional[str]:
        """取得容器詳細資訊"""
        if not self.is_available:
            return None
        
        try:
            result = subprocess.run(
                [self.container_cmd, 'ps', '--filter', f'name={container_name}',
                 '--format', 'ID: {{.ID}}\nImage: {{.Image}}\nStatus: {{.Status}}\nPorts: {{.Ports}}'],
                capture_output=True, text=True, timeout=self.TIMEOUT_LOG
            )
            return result.stdout.strip() if result.stdout.strip() else None
        except Exception:
            return None
    
    def get_container_logs(self, container_name: str, tail: int = 20) -> Optional[str]:
        """取得容器日誌"""
        if not self.is_available:
            return None
        
        try:
            result = subprocess.run(
                [self.container_cmd, 'logs', '--tail', str(tail), container_name],
                capture_output=True, text=True, timeout=self.TIMEOUT_LOG
            )
            return result.stdout.strip() or result.stderr.strip() or None
        except Exception:
            return None

    def _parse_ocp_version(self, config: dict) -> str:
        """從配置中解析 OCP 版本"""
        v_info = config.get('version_info', {})
        ocp_release = v_info.get('OCP_RELEASE', self.DEFAULT_OCP_RELEASE)
        match = re.match(r'(\d+\.\d+)', ocp_release)
        return match.group(1) if match else self.DEFAULT_OCP_VERSION
    
    def _get_authfile(self) -> str:
        """取得認證檔案路徑"""
        return os.path.join(os.path.expanduser("~"), ".docker", "config.json")

    def _notify(self, callback: Optional[Callable], message: str) -> None:
        """發送狀態通知"""
        if callback:
            callback(message)
    
    def _ensure_image_exists(
        self, 
        image: str, 
        authfile: str, 
        status_callback: Optional[Callable] = None
    ) -> bool:
        """確保映像存在，不存在則拉取"""
        self._notify(status_callback, f"📦 檢查鏡像是否存在: {image}")
        
        if self._image_exists(image):
            self._notify(status_callback, "✅ 鏡像已存在")
            return True
        
        return self._pull_image(image, authfile, status_callback)

    def _image_exists(self, image: str) -> bool:
        """檢查本地是否存在指定映像"""
        if not self.is_available:
            return False
        
        try:
            result = subprocess.run(
                [self.container_cmd, 'images', '--format', '{{.Repository}}:{{.Tag}}', image],
                capture_output=True, text=True, timeout=self.TIMEOUT_IMAGE_CHECK
            )
            return image in result.stdout
        except Exception:
            return False

    def _pull_image(
        self, 
        image: str, 
        authfile: str, 
        status_callback: Optional[Callable] = None
    ) -> bool:
        """拉取容器映像"""
        self._notify(status_callback, "📥 鏡像不存在，開始拉取...")
        self._notify(status_callback, "⏳ 這可能需要 3-10 分鐘，請耐心等待...")
        
        try:
            result = subprocess.run(
                [self.container_cmd, 'pull', '--authfile', authfile, image],
                capture_output=True, text=True, timeout=self.TIMEOUT_PULL
            )
            
            if result.returncode == 0:
                self._notify(status_callback, "✅ 鏡像拉取完成")
                return True
            
            self._notify(status_callback, f"❌ 拉取鏡像失敗: {result.stderr[:200]}")
            return False
            
        except subprocess.TimeoutExpired:
            self._notify(status_callback, "❌ 拉取鏡像逾時 (10分鐘)")
            return False
    
    def _cleanup_old_container(
        self, 
        container_name: str, 
        status_callback: Optional[Callable] = None
    ) -> None:
        """清理舊容器（停止並移除）"""
        self._notify(status_callback, "🧹 清理舊容器...")
        
        # 停止
        try:
            subprocess.run(
                [self.container_cmd, 'stop', container_name],
                capture_output=True, timeout=self.TIMEOUT_STOP
            )
        except Exception:
            pass
        
        # 移除
        try:
            subprocess.run(
                [self.container_cmd, 'rm', container_name],
                capture_output=True, timeout=self.TIMEOUT_STOP
            )
        except Exception:
            pass
 
    def _start_new_container(
        self,
        container_name: str,
        image: str,
        authfile: str,
        status_callback: Optional[Callable] = None
    ) -> bool:
        """啟動新容器並驗證運行狀態"""
        self._notify(status_callback, "📦 啟動 Operator Registry 容器...")
        
        # 構建啟動命令
        cmd = self._build_run_command(container_name, image, authfile)
        
        # 執行啟動
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.TIMEOUT_RUN)
        except subprocess.TimeoutExpired:
            self._notify(status_callback, "❌ 啟動容器超時")
            return False
        
        if result.returncode != 0:
            self._notify(status_callback, f"❌ 啟動失敗: {result.stderr[:200]}")
            return False
        
        self._notify(status_callback, f"✅ 容器已啟動，等待服務就緒...")
        time.sleep(self.WAIT_AFTER_START)
        
        # 驗證容器狀態
        return self._verify_container_running(container_name, status_callback)
    
    def _build_run_command(self, container_name: str, image: str, authfile: str) -> list:
        """構建容器啟動命令"""
        cmd = [
            self.container_cmd, 'run', '-d', '--rm',
            '--name', container_name,
            '-p', f'{self.DEFAULT_PORT}:{self.DEFAULT_PORT}',
            '--security-opt', 'label=disable',
        ]
        
        if authfile and os.path.exists(authfile):
            cmd.extend(['--authfile', authfile])
        
        cmd.append(image)
        return cmd
    
    def _verify_container_running(
        self, 
        container_name: str, 
        status_callback: Optional[Callable] = None
    ) -> bool:
        """驗證容器是否成功運行"""
        try:
            check = subprocess.run(
                [self.container_cmd, 'ps', '--filter', f'name={container_name}',
                 '--format', '{{.Status}}'],
                capture_output=True, text=True, timeout=self.TIMEOUT_LOG
            )
            
            if 'Up' not in check.stdout:
                logs = self.get_container_logs(container_name)
                self._notify(status_callback, f"❌ 容器已停止: {logs[:200] if logs else '無日誌'}")
                return False
            
            return True
        except Exception as e:
            self._notify(status_callback, f"❌ 驗證容器狀態失敗: {e}")
            return False
    
    def _check_container_status(self, container_name: str, running_only: bool = True) -> bool:
        """檢查容器狀態"""
        if not self.is_available:
            return False
        
        filters = ['--filter', f'name={container_name}']
        if running_only:
            filters.extend(['--filter', 'status=running'])
        
        try:
            result = subprocess.run(
                [self.container_cmd, 'ps' if running_only else 'ps', '-a'] + filters[2:] + 
                ['--format', '{{.Names}}'],
                capture_output=True, text=True, timeout=self.TIMEOUT_LOG
            )
            return container_name in result.stdout
        except Exception:
            return False