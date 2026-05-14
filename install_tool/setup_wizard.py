import os
import sys
import json
import subprocess
import shutil
import re 
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

    def _find_podman_or_docker(self):
        """尋找可用的 container CLI 工具"""
        for cmd in ['podman', 'docker']:
            if shutil.which(cmd):
                return cmd
        return None

    def login_registry(self, username, password):
        """
        使用 podman 登入 registry.redhat.io，直接指定 authfile
        返回: (success: bool, message: str)
        """
        container_cmd = self._find_podman_or_docker()
        
        if not container_cmd:
            return False, "❌ 找不到 podman 或 docker 命令。請安裝其中之一。"
        
        try:
            # 指定 authfile 路徑為 ~/.docker/config.json
            home_docker_config = os.path.join(os.path.expanduser("~"), ".docker", "config.json")
            
            # 確保目錄存在
            os.makedirs(os.path.dirname(home_docker_config), exist_ok=True)
            
            log_info(f"使用 {container_cmd} 登入 registry.redhat.io，authfile: {home_docker_config}")
            
            # 執行登入命令，使用 --authfile 參數
            cmd = [
                container_cmd, 'login', 'registry.redhat.io',
                '-u', username,
                '--password-stdin',
                '--authfile', home_docker_config
            ]
            
            result = subprocess.run(
                cmd,
                input=password,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                log_success("成功登入 registry.redhat.io")
                
                # 複製到工作目錄的 .docker (可選，方便備份)
                work_docker_config = os.path.join(self.docker_config_dir, "config.json")
                if home_docker_config != work_docker_config:
                    try:
                        os.makedirs(os.path.dirname(work_docker_config), exist_ok=True)
                        shutil.copy2(home_docker_config, work_docker_config)
                        log_info(f"已備份認證配置到: {work_docker_config}")
                    except Exception as e:
                        log_error(f"備份認證配置失敗: {e}")
                
                return True, f"✅ 成功使用 {container_cmd} 登入 registry.redhat.io\n\n📁 認證文件: `{home_docker_config}`"
            else:
                error_msg = result.stderr.strip()
                log_error(f"登入失敗: {error_msg}")
                
                if "unauthorized" in error_msg.lower() or "authentication required" in error_msg.lower():
                    return False, "❌ 認證失敗：用戶名或密碼錯誤。"
                elif "cannot connect" in error_msg.lower() or "connection refused" in error_msg.lower():
                    return False, "❌ 無法連線到 registry.redhat.io。請檢查網路連線。"
                else:
                    return False, f"❌ 登入失敗: {error_msg[:300]}"
                    
        except subprocess.TimeoutExpired:
            return False, "❌ 登入逾時。請檢查網路連線。"
        except Exception as e:
            return False, f"❌ 登入時發生錯誤: {str(e)}"
    
    def test_registry_login(self):
        """
        測試是否已成功登入 registry.redhat.io
        """
        container_cmd = self._find_podman_or_docker()
        
        if not container_cmd:
            return False, "❌ 找不到 podman 或 docker 命令。"
        
        try:
            test_image = "registry.redhat.io/ubi9/ubi-minimal:latest"
            home_docker_config = os.path.join(os.path.expanduser("~"), ".docker", "config.json")
            
            # 檢查 authfile 是否存在
            if os.path.exists(home_docker_config):
                log_info(f"使用 authfile: {home_docker_config} 測試拉取鏡像")
            else:
                log_info("authfile 不存在，嘗試使用預設認證")
            
            result = subprocess.run(
                [container_cmd, 'pull', test_image],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, 'REGISTRY_AUTH_FILE': home_docker_config}
            )
            
            if result.returncode == 0:
                return True, f"✅ Registry 登入狀態有效。\n\n📁 認證文件: `{home_docker_config}`"
            elif "unauthorized" in result.stderr.lower():
                return False, "❌ 登入狀態已過期或無效，請重新登入。"
            else:
                return False, f"⚠️ 測試失敗: {result.stderr.strip()[:200]}"
                
        except subprocess.TimeoutExpired:
            return False, "⚠️ 測試逾時，但可能仍已登入。"
        except Exception as e:
            return False, f"⚠️ 測試時發生錯誤: {str(e)}"
        
    def is_registry_logged_in(self):
        """
        檢查是否已登入 registry（通過檢查 config 文件）
        """
        # 檢查多個可能的 config 文件位置
        config_paths = [
            os.path.join(os.path.expanduser("~"), ".docker", "config.json"),
            os.path.join(os.path.expanduser("~"), ".config", "containers", "auth.json"),
            os.path.join(self.docker_config_dir, "config.json"),
        ]
        
        # 也檢查 XDG_RUNTIME_DIR
        xdg_runtime = os.environ.get('XDG_RUNTIME_DIR', '')
        if xdg_runtime:
            config_paths.insert(0, os.path.join(xdg_runtime, "containers", "auth.json"))
        
        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        config_data = json.load(f)
                        auths = config_data.get('auths', {})
                        # 檢查是否包含 registry.redhat.io 的認證
                        for registry in ['registry.redhat.io', 'https://registry.redhat.io']:
                            if registry in auths:
                                return True
                except Exception:
                    pass
        
        return False

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

    def run_get_operator_catalog(self, config, status_callback=None):
        """
        在環境初始化階段預先獲取 operator catalog 資訊
        並儲存為 JSON 格式供後續使用
        
        Args:
            config: 配置字典
            status_callback: 可選的回調函數，用於更新 UI 狀態
        """
        if status_callback:
            status_callback("🔍 初始化 Operator Catalog 獲取任務...")
        
        log_info("開始獲取 Operator Catalog 資訊...")
        
        # 從 config 獲取 OCP 版本
        v_info = config.get('version_info', {})
        ocp_release = v_info.get('OCP_RELEASE', '4.20.8')
        # 提取主版本號 (例如: 4.20.8 -> 4.20)
        import re
        match = re.match(r'(\d+\.\d+)', ocp_release)
        ocp_version = match.group(1) if match else '4.20'
        
        if status_callback:
            status_callback(f"📋 目標 OCP 版本: {ocp_version}")
        
        # 定義要獲取的 catalogs
        catalogs = [
            {
                "name": "Red Hat Operators",
                "url": f"registry.redhat.io/redhat/redhat-operator-index:v{ocp_version}"
            },
            {
                "name": "Certified Operators",
                "url": f"registry.redhat.io/redhat/certified-operator-index:v{ocp_version}"
            },
            {
                "name": "Community Operators",
                "url": f"registry.redhat.io/redhat/community-operator-index:v{ocp_version}"
            },
            {
                "name": "Red Hat Marketplace",
                "url": f"registry.redhat.io/redhat/redhat-marketplace-index:v{ocp_version}"
            }
        ]
        
        operator_data = {
            "ocp_version": ocp_version,
            "fetched_at": datetime.now().isoformat(),
            "catalogs": {}
        }
        
        # 尋找 oc-mirror 命令
        if status_callback:
            status_callback("🔧 尋找 oc-mirror 命令...")
        
        oc_mirror_cmd = self._find_oc_mirror()
        if not oc_mirror_cmd:
            error_msg = "找不到 oc-mirror 命令"
            log_error(error_msg)
            if status_callback:
                status_callback(f"❌ {error_msg}")
            return False
        
        if status_callback:
            status_callback(f"✅ 找到 oc-mirror: {oc_mirror_cmd}")
        
        # 檢查認證
        if status_callback:
            status_callback("🔐 檢查 Red Hat Registry 認證...")
        
        authfile = os.path.join(os.path.expanduser("~"), ".docker", "config.json")
        if not os.path.exists(authfile):
            error_msg = "找不到 Docker 認證文件，請先登入 Red Hat Registry"
            log_error(error_msg)
            if status_callback:
                status_callback(f"❌ {error_msg}")
            return False
        
        if status_callback:
            status_callback("✅ 認證文件存在")
        
        # 只處理 Red Hat Operators catalog（最重要的一個）
        catalog = catalogs[0]
        catalog_url = catalog['url']
        
        if status_callback:
            status_callback(f"📡 連接到 {catalog['name']}...")
        
        log_info(f"正在獲取 {catalog['name']} 的 package 列表...")
        
        try:
            # 執行 oc-mirror list operators --catalog=<url>
            cmd = [oc_mirror_cmd, 'list', 'operators', '--catalog', catalog_url]
            
            # 從 config 獲取 timeout 設定
            catalog_timeout = int(v_info.get('CATALOG_TIMEOUT', '600'))
            
            if status_callback:
                status_callback(f"⏳ 執行 oc-mirror 命令，這可能需要 {catalog_timeout // 60} 分鐘...")
            
            log_info(f"執行命令: {' '.join(cmd)} (timeout: {catalog_timeout}s)")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=catalog_timeout
            )
            
            if result.returncode == 0:
                if status_callback:
                    status_callback("📊 解析 Operator 列表...")
                
                packages = self._parse_operator_packages(result.stdout)
                
                if status_callback:
                    status_callback(f"📦 找到 {len(packages)} 個 packages")
                
                operator_data["catalogs"][catalog_url] = {
                    "name": catalog['name'],
                    "packages": packages,
                    "package_count": len(packages)
                }
                
                log_success(f"成功獲取 {len(packages)} 個 packages")
            else:
                error_msg = f"oc-mirror 執行失敗: {result.stderr[:200]}"
                log_error(error_msg)
                if status_callback:
                    status_callback(f"❌ {error_msg}")
                return False
                
        except subprocess.TimeoutExpired:
            error_msg = f"獲取 catalog 資訊超時 ({catalog_timeout}秒)"
            log_error(error_msg)
            if status_callback:
                status_callback(f"❌ {error_msg}")
                status_callback(f"💡 建議：在 Tool Configuration 中增加 Catalog Timeout 設定")
            return False
        except Exception as e:
            error_msg = f"獲取 catalog 資訊失敗: {str(e)}"
            log_error(error_msg)
            if status_callback:
                status_callback(f"❌ {error_msg}")
            return False
        
        # 儲存為 JSON
        catalog_json_path = os.path.join(self.current_dir, "operator_catalog.json")
        
        if status_callback:
            status_callback(f"💾 儲存快取檔案...")
        
        try:
            with open(catalog_json_path, 'w', encoding='utf-8') as f:
                json.dump(operator_data, f, indent=2, ensure_ascii=False)
            
            log_success(f"Operator catalog 已儲存至: {catalog_json_path}")
            
            if status_callback:
                status_callback(f"✅ Operator Catalog 獲取完成! (共 {len(packages)} 個 packages)")
            
            return True
        except Exception as e:
            error_msg = f"儲存 operator catalog 失敗: {str(e)}"
            log_error(error_msg)
            if status_callback:
                status_callback(f"❌ {error_msg}")
            return False
       
    def _find_oc_mirror(self):
        """尋找 oc-mirror 命令"""
        # 優先使用 ~/.local/bin
        local_bin = os.path.join(os.path.expanduser("~"), ".local/bin/oc-mirror")
        if os.path.exists(local_bin):
            return local_bin
        
        # 然後是當前工作目錄
        current_bin = os.path.join(self.current_dir, "usr/bin/oc-mirror")
        if os.path.exists(current_bin):
            return current_bin
        
        # 最後嘗試系統 PATH
        if shutil.which('oc-mirror'):
            return 'oc-mirror'
        
        return None

    def _parse_operator_packages(self, output):
        """
        解析 oc-mirror list operators 的輸出
        輸入格式:
        NAME                                            DISPLAY NAME  DEFAULT CHANNEL
        3scale-operator                                               threescale-2.16
        advanced-cluster-management                                   release-2.16
        ...
        返回: [{"name": "3scale-operator", "default_channel": "threescale-2.16"}, ...]
        """
        packages = []
        lines = output.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            
            # 跳過空行、標題行和分隔線
            if not line or 'NAME' in line.upper() or '---' in line or 'Available' in line:
                continue
            
            # 解析：使用多個空格分割
            parts = re.split(r'\s{2,}', line)
            
            if len(parts) >= 1:
                package_name = parts[0].strip()
                
                # 獲取 default channel (最後一個非空值)
                default_channel = parts[-1].strip() if len(parts) > 1 else 'stable'
                
                # 獲取 display name (中間部分，可選)
                display_name = parts[1].strip() if len(parts) > 2 else ''
                
                # 如果 display name 看起來像 channel（包含數字和點），則調整
                if display_name and re.match(r'^[\d.]+|stable|latest|fast|alpha|beta|preview', display_name):
                    # display name 實際上是 channel
                    packages.append({
                        "name": package_name,
                        "display_name": "",
                        "default_channel": display_name
                    })
                else:
                    packages.append({
                        "name": package_name,
                        "display_name": display_name,
                        "default_channel": default_channel
                    })
        
        return packages

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

        if not os.path.exists(target_bin_dir):
            log_info(f"目錄不存在，正在創建: {target_bin_dir}")
            os.makedirs(target_bin_dir, exist_ok=True)

        try:
            log_info(f"正在解壓 {tar_path} 到 {target_bin_dir}...")
            subprocess.run(        
                ["tar", "-zxvf", tar_path, "-C", target_bin_dir],        
                check=True,
                capture_output=True,
                text=True
            )

            # 設定執行檔路徑
            target_binary = os.path.join(target_bin_dir, "oc-mirror")

            if not os.path.isfile(target_binary):
                log_error(f"解壓後未找到 oc-mirror 執行檔於 {target_binary}")
                log_info(f"目錄 {target_bin_dir} 內容：{os.listdir(target_bin_dir)}")
                return False

            # 調整操作權限
            log_info(f"正在設置執行權限：{target_binary}...")
            os.chmod(target_binary, 0o755)

            log_success(f"已設置執行權限：{target_binary}")
            log_info(f"請確保 {target_bin_dir} 已加入 $PATH")
            log_info(f"執行命令：export PATH=$PATH:{target_bin_dir}")
            
            # 注意：不再在這裡調用 run_get_operator_catalog
            # Catalog 獲取已移到前端的 Step 4 獨立處理

        except subprocess.CalledProcessError as e:
            log_error(f"解壓失敗：{e}")
            return False
        except Exception as e:
            log_error(f"發生錯誤：{e}")
            return False

        log_success("untar_oc_mirror 執行完成")
        return True