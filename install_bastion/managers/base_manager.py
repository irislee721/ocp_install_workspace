import subprocess
import os
import json
from typing import Dict, Tuple, Any
from datetime import datetime


class BaseManager:
    """基礎管理類別，提供共用功能"""
    
    def __init__(self, config: Dict[str, Any], config_dir: str = "/tmp/ocp-install-config"):
        """
        初始化基礎管理器
        
        Args:
            config: 配置參數字典
            config_dir: 配置目錄路徑
        """
        self.config = config
        self.config_dir = config_dir
        self.logs = []
        
        # 建立配置目錄
        os.makedirs(self.config_dir, exist_ok=True)
        
        # 初始化 logger
        self._init_logger()
    
    def _init_logger(self):
        """初始化日誌"""
        self.log_file = os.path.join(
            self.config_dir,
            f"install_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
    
    def _log(self, message: str, level: str = "INFO"):
        """記錄日誌"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.logs.append(log_entry)
        
        # 寫入日誌檔案
        try:
            with open(self.log_file, 'a') as f:
                f.write(log_entry + '\n')
        except Exception:
            pass
        
        print(log_entry)
    
    def _run_command(self, command: str, shell: bool = True, timeout: int = 300) -> Tuple[bool, str, str]:
        """
        執行系統命令
        
        Args:
            command: 要執行的命令
            shell: 是否使用 shell 執行
            timeout: 超時時間（秒）
            
        Returns:
            (success, stdout, stderr)
        """
        try:
            self._log(f"執行命令: {command}")
            
            result = subprocess.run(
                command,
                shell=shell,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                if result.stdout.strip():
                    self._log(f"命令成功: {result.stdout.strip()[:200]}")
                return True, result.stdout.strip(), result.stderr.strip()
            else:
                self._log(f"命令失敗 (rc={result.returncode}): {result.stderr.strip()[:200]}", "ERROR")
                return False, result.stdout.strip(), result.stderr.strip()
                
        except subprocess.TimeoutExpired:
            self._log(f"命令超時: {command}", "ERROR")
            return False, "", "Command timeout"
        except Exception as e:
            self._log(f"命令執行異常: {str(e)}", "ERROR")
            return False, "", str(e)
    
    def _check_service_status(self, service_name: str) -> bool:
        """檢查服務是否運行中"""
        success, stdout, _ = self._run_command(f"systemctl is-active {service_name}")
        return success and "active" in stdout
    
    def _backup_file(self, file_path: str) -> bool:
        """備份檔案"""
        if os.path.exists(file_path):
            backup_path = f"{file_path}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            try:
                import shutil
                shutil.copy(file_path, backup_path)
                self._log(f"已備份 {file_path} -> {backup_path}")
                return True
            except Exception as e:
                self._log(f"備份失敗: {str(e)}", "WARNING")
                return False
        return False
    
    def _write_file(self, file_path: str, content: str) -> bool:
        """寫入檔案"""
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as f:
                f.write(content)
            self._log(f"已寫入檔案: {file_path}")
            return True
        except Exception as e:
            self._log(f"寫入檔案失敗 {file_path}: {str(e)}", "ERROR")
            return False
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """安全取得配置值"""
        return self.config.get(key, default)