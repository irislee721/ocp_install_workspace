import os
import sys
import json
import subprocess
import shutil
import re
from datetime import datetime
import time

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
        self.config_dir = os.path.join(self.current_dir, 'config')
        os.makedirs(self.config_dir, exist_ok=True)
        
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

    def start_operator_registry(self, config, status_callback=None):
        """
        啟動 Operator Registry 容器（需求1）
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

        # 檢查鏡像是否已存在
        if status_callback:
            status_callback(f"📦 檢查鏡像是否存在: {catalog_image}")
        
        image_exists = False
        try:
            result = subprocess.run(
                [container_cmd, 'images', '--format', '{{.Repository}}:{{.Tag}}', catalog_image],
                capture_output=True, text=True, timeout=10
            )
            if catalog_image in result.stdout:
                image_exists = True
                if status_callback:
                    status_callback("✅ 鏡像已存在，跳過下載")
        except:
            pass
        
        # 如果鏡像不存在，先拉取
        if not image_exists:
            if status_callback:
                status_callback(f"📥 鏡像不存在，開始拉取...")
                status_callback("⏳ 這可能需要 3-10 分鐘，請耐心等待...")
            
            try:
                # 拉取鏡像（timeout 設為 600 秒 = 10 分鐘）
                result = subprocess.run(
                    [container_cmd, 'pull', '--authfile', authfile, catalog_image],
                    capture_output=True, text=True, timeout=600
                )
                if result.returncode != 0:
                    if status_callback:
                        status_callback(f"❌ 拉取鏡像失敗: {result.stderr[:200]}")
                    return False, container_name, port
                
                if status_callback:
                    status_callback("✅ 鏡像拉取完成")
            except subprocess.TimeoutExpired:
                if status_callback:
                    status_callback("❌ 拉取鏡像逾時 (10分鐘)")
                return False, container_name, port
        
        # 停止並移除舊容器
        if status_callback:
            status_callback(f"🧹 清理舊容器...")
        
        subprocess.run([container_cmd, 'stop', container_name], capture_output=True, timeout=10)
        subprocess.run([container_cmd, 'rm', container_name], capture_output=True, timeout=10)

        if status_callback:
            status_callback(f"📦 啟動 Operator Registry 容器...")
        
        # 停止並移除舊容器
        subprocess.run([container_cmd, 'stop', container_name], capture_output=True, timeout=10)
        subprocess.run([container_cmd, 'rm', container_name], capture_output=True, timeout=10)
        
        # 啟動新容器（使用 --rm 確保停止後自動清除）
        result = subprocess.run(
            [container_cmd, 'run', '-d', '--rm', '--name', container_name,
            '-p', f'{port}:{port}',
            '--authfile', authfile,
            catalog_image],
            capture_output=True, text=True, timeout=60
        )
        
        if result.returncode != 0:
            return False, container_name, port
        
        if status_callback:
            status_callback(f"✅ 容器已啟動，等待服務就緒...")
        
        # 等待 Registry 就緒
        time.sleep(5)
        
        return True, container_name, port

    def stop_operator_registry(self, container_name):
        """停止 Operator Registry 容器"""
        container_cmd = self._find_podman_or_docker()
        if container_cmd:
            subprocess.run([container_cmd, 'stop', container_name], capture_output=True, timeout=10)

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
             f"mirror-registry-{architecture}.tar.gz"),
            
            (f"https://github.com/fullstorydev/grpcurl/releases/download/v1.9.3/grpcurl_1.9.3_linux_x86_64.tar.gz",
             f"grpcurl_1.9.3_linux_x86_64.tar.gz")
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

    def run_get_operator_catalog_via_grpc(self, config, status_callback=None):
        """
        使用 gRPC 獲取 Operator Catalog 並創建 operator_index.json
        """
        import time
        
        if status_callback:
            status_callback("🔍 初始化 Operator Catalog 獲取任務...")
            status_callback("🔧 尋找 grpcurl 命令...")
        
        grpcurl_cmd = self._find_grpcurl()
        if not grpcurl_cmd:
            if status_callback:
                status_callback("❌ 找不到 grpcurl 命令")
            return False

        if status_callback:
            status_callback(f"✅ 找到 grpcurl: {grpcurl_cmd}")

        # 啟動 Registry 容器
        success, container_name, port = self.start_operator_registry(config, status_callback)
        if not success:
            if status_callback:
                status_callback("❌ 啟動 Registry 容器失敗")
            return False
        
        try:
            # 查詢所有 Packages
            if status_callback:
                status_callback("📡 查詢所有 Packages...")
            
            result = subprocess.run(
                [grpcurl_cmd, '-plaintext',
                f'localhost:{port}',
                'api.Registry/ListPackages'],
                capture_output=True, text=True, timeout=120
            )
            
            if result.returncode != 0 or not result.stdout.strip():
                if status_callback:
                    status_callback(f"❌ 查詢失敗: {result.stderr[:200]}")
                return False
            
            # 解析 package 名稱列表
            package_names = self._parse_grpcurl_list_output(result.stdout)
            
            if not package_names:
                if status_callback:
                    status_callback("❌ 解析失敗：未找到任何 package")
                return False
            
            if status_callback:
                status_callback(f"📦 找到 {len(package_names)} 個 packages，正在獲取詳細資訊...")
            
            # 獲取每個 package 的詳細資訊
            packages = []
            for i, pkg_name in enumerate(package_names):
                if status_callback and i % 20 == 0:
                    status_callback(f"⏳ 處理中... ({i+1}/{len(package_names)})")
                
                pkg_info = self._get_package_basic_info_grpc(grpcurl_cmd, port, pkg_name)
                if pkg_info:
                    packages.append(pkg_info)
            
            # 儲存 operator_index.json
            if status_callback:
                status_callback("💾 儲存 operator_index.json...")
            
            output_path = os.path.join(self.config_dir, "operator_index.json")
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(packages, f, indent=2, ensure_ascii=False)
            
            if status_callback:
                status_callback(f"✅ operator_index.json 已創建 ({len(packages)} packages)")
            
            return True
            
        finally:
            self.stop_operator_registry(container_name)
            if status_callback:
                status_callback("🧹 容器已清除")

    def _find_grpcurl(self):
        """尋找 grpcurl 命令"""
        # 優先使用 ~/.local/bin
        local_bin = os.path.join(os.path.expanduser("~"), ".local/bin/grpcurl")
        if os.path.exists(local_bin):
            log_info(f"找到 grpcurl: {local_bin}")
            return local_bin

        # 最後嘗試系統 PATH
        if shutil.which('grpcurl'):
            system_grpcurl = shutil.which('grpcurl')
            log_info(f"找到 grpcurl: {system_grpcurl}")
            return system_grpcurl
        
        log_error("找不到 grpcurl 命令")
        return None

    def _parse_grpcurl_list_output(self, output):
        """
        解析 ListPackages 輸出
        支援兩種格式：
        1. 連續 JSON: { "name": "xxx" } { "name": "yyy" }
        2. JSON Lines: 每行一個 {"name": "xxx"}
        """
        import re
        
        package_names = []
        
        # 方式1：使用正則提取所有 { "name": "..." } 
        pattern = r'\{\s*"name"\s*:\s*"([^"]+)"\s*\}'
        matches = re.findall(pattern, output)
        
        if matches:
            package_names = matches
            log_info(f"正則解析到 {len(package_names)} 個 packages")
            return package_names
        
        # 方式2：逐行解析 JSON Lines
        for line in output.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    name = item.get('name', '')
                    if name:
                        package_names.append(name)
            except json.JSONDecodeError:
                # 方式3：一行內可能有多個 JSON 物件
                objects = re.findall(r'\{[^{}]*\}', line)
                for obj_str in objects:
                    try:
                        obj = json.loads(obj_str)
                        name = obj.get('name', '')
                        if name:
                            package_names.append(name)
                    except json.JSONDecodeError:
                        continue
        
        log_info(f"解析到 {len(package_names)} 個 packages")
        return package_names

    def _get_package_basic_info_grpc(self, grpcurl_cmd, port, package_name):
        """
        獲取 package 的基本資訊（需求3）
        返回: {"package_name": ..., "default_channel": ..., "stable_channel": ...}
        """
        try:
            result = subprocess.run(
                [grpcurl_cmd, '-plaintext',
                '-d', json.dumps({"name": package_name}),
                f'localhost:{port}',
                'api.Registry/GetPackage'],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode != 0:
                return None
            
            pkg_data = json.loads(result.stdout)
            default_channel = pkg_data.get('defaultChannelName', '')
            
            # 找 stable channel
            channels = pkg_data.get('channels', [])
            stable_channel = ""
            for ch in channels:
                ch_name = ch.get('name', '')
                if 'stable' in ch_name.lower():
                    stable_channel = ch_name
                    break
            if not stable_channel and any(ch.get('name') == 'stable' for ch in channels):
                stable_channel = 'stable'
            
            return {
                "package_name": package_name,
                "default_channel": default_channel,
                "stable_channel": stable_channel
            }
        except Exception:
            return None

    def get_package_version_grpc(self, grpcurl_cmd, port, package_name, channel_name, max_retries=3):
        """
        獲取特定 channel 的最新版本，支援重試機制
        返回: version_string 或 None
        """
        import time
        
        for attempt in range(max_retries):
            try:
                # 建立查詢命令
                request_data = json.dumps({"pkgName": package_name, "channelName": channel_name})
                
                result = subprocess.run(
                    [grpcurl_cmd, '-plaintext',
                    '-d', request_data,
                    f'localhost:{port}',
                    'api.Registry/GetBundleForChannel'],
                    capture_output=True, text=True, timeout=30
                )
                
                # 檢查是否成功
                if result.returncode == 0 and result.stdout.strip():
                    try:
                        bundle_data = json.loads(result.stdout)
                        csv_json_str = bundle_data.get('csvJson', '{}')
                        csv_json = json.loads(csv_json_str)
                        version = csv_json.get('spec', {}).get('version', '')
                        
                        if version:
                            return version
                        else:
                            log_info(f"獲取 {package_name}/{channel_name} 版本為空 (嘗試 {attempt+1})")
                    except json.JSONDecodeError as e:
                        log_error(f"解析回應 JSON 失敗 (嘗試 {attempt+1}): {e}")
                else:
                    error_msg = result.stderr.strip() if result.stderr else "unknown error"
                    log_info(f"查詢失敗 (嘗試 {attempt+1}): {error_msg[:100]}")
                
                # 重試前等待
                if attempt < max_retries - 1:
                    wait_time = 2 * (attempt + 1)  # 逐漸增加等待時間
                    log_info(f"等待 {wait_time} 秒後重試...")
                    time.sleep(wait_time)
                    
            except subprocess.TimeoutExpired:
                log_error(f"查詢超時 (嘗試 {attempt+1})")
                if attempt < max_retries - 1:
                    time.sleep(3)
            except Exception as e:
                log_error(f"查詢出錯 (嘗試 {attempt+1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        
        return None

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
    
    def run_untar_grpcurl(self, config):
        """Extract grpcurl to ~/.local/bin"""
        log_info("開始執行 untar_grpcurl...")
        
        tar_filename = "grpcurl_1.9.3_linux_x86_64.tar.gz"
        tar_path = os.path.join(self.install_source_dir, tar_filename)
        
        if not os.path.exists(tar_path):
            log_error(f"找不到 tar 包：{tar_path}")
            return False

        target_bin_dir = os.path.expanduser("~/.local/bin")
        if not os.path.exists(target_bin_dir):
            os.makedirs(target_bin_dir, exist_ok=True)

        try:
            subprocess.run(["tar", "-zxvf", tar_path, "-C", target_bin_dir], 
                        check=True, capture_output=True, text=True)
            
            target_binary = os.path.join(target_bin_dir, "grpcurl")
            if not os.path.isfile(target_binary):
                return False
            
            os.chmod(target_binary, 0o755)
            log_success(f"已設置執行權限：{target_binary}")
            return True
        except Exception as e:
            log_error(f"解壓失敗：{e}")
            return False