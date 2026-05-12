import os
import sys
import json
import subprocess
import shutil
from datetime import datetime

# 全局日誌輔助函數
def log_info(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] \033[32mINFO\033[0m: {msg}")

def log_error(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] \033[31mERROR\033[0m: {msg}", file=sys.stderr)

def log_success(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] \033[32mSUCCESS\033[0m: {msg}")

class SetupWizard:
    def __init__(self, current_dir=None):
        """初始化嚮導，設置當前工作目錄"""
        if current_dir:
            self.current_dir = current_dir
        else:
            self.current_dir = os.getcwd()
        
        # 定義基礎目錄結構
        self.install_source_dir = os.path.join(self.current_dir, "install_source")
        self.install_ocp_dir = os.path.join(self.current_dir, "install", "ocp")
        self.docker_config_dir = os.path.join(self.current_dir, ".docker")

    def run_env_prep(self):
        """Prepare environment: create directories and setup docker config"""
        log_info("開始執行 env_prep...")

        create_dirs = [
            self.install_source_dir,
            self.docker_config_dir,
            self.install_ocp_dir,
            os.path.join(self.install_source_dir, "mirror")
        ]

        for dir_path in create_dirs:
            if os.path.isdir(dir_path):
                log_info(f"目錄 {dir_path} 已存在，跳過創建")
            else:
                log_info(f"目錄 {dir_path} 不存在，正在創建...")
                try:
                    os.makedirs(dir_path, exist_ok=True)
                    log_success("創建成功")
                except Exception as e:
                    log_error(f"創建失敗：{e}")
                    return False

        # 處理 pull-secret
        possible_pull_secret_paths = [
            os.path.join(self.current_dir, "pull-secret"),
            os.path.join(os.path.expanduser("~"), "pull-secret"),
            "/root/pull-secret"
        ]
        
        pull_secret_path = None
        for path in possible_pull_secret_paths:
            if os.path.isfile(path):
                pull_secret_path = path
                break
        
        docker_config_path = os.path.join(self.docker_config_dir, "config.json")

        if pull_secret_path:
            log_info(f"找到 pull-secret 文件：{pull_secret_path}")
            try:
                with open(pull_secret_path, 'r', encoding='utf-8') as f:
                    pull_secret_data = f.read()

                pull_secret_json = json.loads(pull_secret_data)
                
                # 確保目錄存在
                os.makedirs(os.path.dirname(docker_config_path), exist_ok=True)
                
                with open(docker_config_path, 'w', encoding='utf-8') as f:
                    json.dump(pull_secret_json, f, indent=2)

                log_success(f"已從 pull-secret 產生 config.json: {docker_config_path}")
            except json.JSONDecodeError as e:
                log_error(f"解析 pull-secret JSON 失敗：{e}")
                return False
            except Exception as e:
                log_error(f"處理 pull-secret 時出錯：{e}")
                return False
        else:
            log_error("未找到 pull-secret 文件 (嘗試了 pull-secret, ~/pull-secret, /root/pull-secret)")
            log_info("跳過 docker config 生成，請手動放置 pull-secret 到當前目錄後重試此步驟")

        log_success("env_prep 執行完成")
        return True

    def download_file(self, url, destination_dir):
        """Download a file using wget"""
        # 清理 URL 中可能存在的空格
        url = url.strip().replace(" ", "")
        
        # 提取文件名用於檢查是否存在
        filename = os.path.basename(url.split('?')[0])
        dest_path = os.path.join(destination_dir, filename)

        # 如果文件已存在，直接返回成功
        if os.path.exists(dest_path):
            log_info(f"文件已存在，跳過下載：{filename}")
            return True

        try:
            log_info(f"正在下載：{filename}...")
            subprocess.run(['wget', '-q', '--show-progress', url, '-P', destination_dir], check=True)
            return True
        except subprocess.CalledProcessError as e:
            log_error(f"下載失敗：{filename}, 錯誤：{e}")
            return False
        except FileNotFoundError:
            log_error("未找到 wget 命令，請安裝 wget (sudo yum install wget)")
            return False

    def run_get_tools(self, config, progress_callback=None):
        """Download required installation tools"""
        log_info("開始執行 get_tools，檢查並下載安裝工具...")

        v_info = config.get('version_info', {})
        csi_info = config.get('csi_info', {})
        
        ocp_release = v_info.get('OCP_RELEASE', '')
        architecture = v_info.get('ARCHITECTURE', '')
        rhel_version = v_info.get('RHEL_VERSION', '')
        helm_version = v_info.get('HELM_VERSION', '')
        mirror_registry_version = v_info.get('MIRROR_REGISTRY_VERSION', '')
        trident_installer = csi_info.get('TRIDENT_INSTALLER', '')
        csi_type = csi_info.get('CSI_TYPE', 'nfs-csi')

        os.makedirs(self.install_source_dir, exist_ok=True)

        # 定義所有需要下載的文件清單 (URL, 相對文件名)
        # 注意：URL 模板中不再包含多餘空格，依賴 strip() 處理
        downloads = [
            (f"https://mirror.openshift.com/pub/openshift-v4/clients/ocp/{ocp_release}/openshift-client-linux-{architecture}-{rhel_version}-{ocp_release}.tar.gz", 
             f"openshift-client-linux-{architecture}-{rhel_version}-{ocp_release}.tar.gz"),
            
            (f"https://mirror.openshift.com/pub/openshift-v4/clients/ocp/{ocp_release}/openshift-install-{rhel_version}-{architecture}.tar.gz", 
             f"openshift-install-{rhel_version}-{architecture}.tar.gz"),
            
            (f"https://mirror.openshift.com/pub/openshift-v4/clients/ocp/{ocp_release}/oc-mirror.{rhel_version}.tar.gz", 
             f"oc-mirror.{rhel_version}.tar.gz"),
            
            (f"https://mirror.openshift.com/pub/openshift-v4/clients/butane/latest/butane-{architecture}", 
             f"butane-{architecture}"),
            
            (f"https://developers.redhat.com/content-gateway/file/pub/openshift-v4/clients/helm/{helm_version}/helm-linux-{architecture}.tar.gz", 
             f"helm-linux-{architecture}.tar.gz"),
            
            (f"https://mirror.openshift.com/pub/cgw/mirror-registry/{mirror_registry_version}/mirror-registry-{architecture}.tar.gz", 
             f"mirror-registry-{architecture}.tar.gz")
        ]

        # 如果是 trident，加入額外下載
        if csi_type == "trident":
            downloads.append(
                (f"https://github.com/NetApp/trident/releases/download/v{trident_installer}/trident-installer-{trident_installer}.tar.gz", 
                 f"trident-installer-{trident_installer}.tar.gz")
            )

        total_steps = len(downloads)
        current_step = 0

        def step_done():
            nonlocal current_step
            current_step += 1
            if progress_callback:
                progress_callback(current_step / total_steps)

        for url, filename in downloads:
            # 再次確認路徑
            dest_path = os.path.join(self.install_source_dir, filename)
            
            # 檢查文件是否已存在 (download_file 內部也會檢查，這裡是為了日誌和進度條準確)
            if os.path.exists(dest_path):
                log_info(f"文件已存在，跳過下載：{filename}")
                step_done()
                continue
            
            if not self.download_file(url, self.install_source_dir):
                log_error(f"下載失敗：{filename}")
                # 可選擇是否繼續，這裡選擇返回 False 停止流程
                return False
            
            step_done()

        log_info("get_tools 執行完成")
        return True

    def run_untar_oc_mirror(self, config):
        """Extract oc-mirror to install_source, then move binary to ~/usr/bin"""
        log_info("開始執行 untar_oc_mirror...")

        v_info = config.get('version_info', {})
        rhel_version = v_info.get('RHEL_VERSION', 'rhel9')
        
        tar_filename = f"oc-mirror.{rhel_version}.tar.gz"
        tar_path = os.path.join(self.install_source_dir, tar_filename)
        
        if not os.path.exists(tar_path):
            log_error(f"找不到 tar 包：{tar_path}")
            return False

        target_bin_dir = os.path.expanduser("~/.local/bin")

        if os.path.exists(target_bin_dir):
            print(f"目標目錄存在: {target_bin_dir}")
        else:
            print(f"目錄不存在: {target_bin_dir}")


        try:
            log_info(f"正在解壓 {tar_path} 到 {target_bin_dir}...")
            subprocess.run(        
                ["tar", "-zxvf", tar_path, "-C", target_bin_dir],        
                check=True,          # 命令失敗時拋出 CalledProcessError        
                capture_output=True, # 擷取輸出，避免干擾終端        
                text=True            # 以文字模式回傳 stdout/stderr    
            )

            # 設定執行檔路徑
            target_binary = os.path.join(target_bin_dir, "oc-mirror")

            if not os.path.isfile(target_binary):
                log_error(f"解壓後未找到 oc-mirror 執行檔於 {target_binary}")
                # 嘗試列出目錄內容以除錯
                log_info(f"目錄 {target_bin_dir} 內容：{os.listdir(target_bin_dir)}")
                return False

            # 調整操作權限
            log_info(f"正在設置執行權限：{target_binary}...")
            os.chmod(target_binary, 0o755)

            log_success(f"已設置執行權限：{target_binary}")
            log_info(f"請確保 {target_bin_dir} 已加入 $PATH")
            log_info(f"執行命令：export PATH=$PATH:{target_bin_dir}")

        except subprocess.CalledProcessError as e:
            log_error(f"解壓失敗：{e}")
            return False
        except Exception as e:
            log_error(f"發生錯誤：{e}")
            return False

        log_success("untar_oc_mirror 執行完成")
        return True