import os
import subprocess
import json

# 導入抽離的模組
from src.logger import log_info, log_error, log_success
from src.operator_manager import OperatorManager
from src.registry_manager import RegistryManager

class SetupWizard:
    def __init__(self, current_dir=None):
        """初始化基礎目錄結構與子模組"""
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
        
        # 初始化子模組
        self.op_mgr = OperatorManager(current_dir)
        self.registry = RegistryManager(current_dir)

    def apply_pull_secret(self, pull_secret_json):
        """將使用者提供的 pull secret 合併到認證配置中"""
        docker_config_path = os.path.join(os.path.expanduser("~"), ".docker", "config.json")
        
        existing = {}
        if os.path.exists(docker_config_path):
            try:
                with open(docker_config_path, 'r') as f:
                    existing = json.load(f)
            except Exception:
                pass
        
        existing_auths = existing.get('auths', {})
        for registry, auth in pull_secret_json.get('auths', {}).items():
            existing_auths[registry] = auth
        existing['auths'] = existing_auths
        
        try:
            os.makedirs(os.path.dirname(docker_config_path), exist_ok=True)
            with open(docker_config_path, 'w') as f:
                json.dump(existing, f, indent=2)
            
            # 同步到 config 目錄
            config_path = os.path.join(self.config_dir, 'pull-secret.json')
            with open(config_path, 'w') as f:
                json.dump(existing, f, indent=2)
            
            # 同步到工作目錄
            work_dir = os.path.join(self.current_dir, ".docker")
            os.makedirs(work_dir, exist_ok=True)
            with open(os.path.join(work_dir, "config.json"), 'w') as f:
                json.dump(existing, f, indent=2)
            
            log_success("Pull secret 已合併到 Docker 認證")
            return True
        except Exception as e:
            log_error(f"合併 pull secret 失敗: {e}")
            return False 

    def run_env_prep(self):
        """建立 install_source、.docker、install/ocp 等工作目錄"""
        log_info("開始執行 env_prep...")
        
        create_dirs = [
            self.install_source_dir,
            self.docker_config_dir,
            self.install_ocp_dir,
            os.path.join(self.install_source_dir, "mirror")
        ]
        
        for dir_path in create_dirs:
            if not os.path.isdir(dir_path):
                try:
                    os.makedirs(dir_path, exist_ok=True)
                    log_success(f"創建成功: {dir_path}")
                except Exception as e:
                    log_error(f"創建失敗：{e}")
                    return False
        
        log_success("env_prep 執行完成")
        return True

    def download_file(self, url, destination_dir):
        """使用 wget 下載單一檔案，若已存在則跳過"""
        url = url.strip().replace(" ", "")
        filename = os.path.basename(url.split('?')[0])
        dest_path = os.path.join(destination_dir, filename)
        
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
            log_error("未找到 wget 命令")
            return False

    def run_get_tools(self, config, progress_callback=None):
        """根據 config 版本資訊下載 oc-mirror、grpcurl 等必要工具"""
        log_info("開始執行 get_tools...")
        
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
            dest_path = os.path.join(self.install_source_dir, filename)
            if os.path.exists(dest_path):
                log_info(f"文件已存在，跳過下載：{filename}")
                step_done()
                continue
            
            if not self.download_file(url, self.install_source_dir):
                log_error(f"下載失敗：{filename}")
                return False
            
            step_done()
        
        log_info("get_tools 執行完成")
        return True

    def run_get_operator_catalog_via_grpc(self, config, status_callback=None):
        """使用 gRPC 獲取 Operator Catalog 並創建 operator_index.json"""
        if status_callback:
            status_callback("🔍 初始化 Operator Catalog 獲取任務...")
            status_callback("🔧 尋找 grpcurl 命令...")
        
        # 改用 self.op_mgr
        grpcurl_cmd = self.op_mgr.find_grpcurl()
        if not grpcurl_cmd:
            if status_callback:
                status_callback("❌ 找不到 grpcurl 命令")
            return False
        
        if status_callback:
            status_callback(f"✅ 找到 grpcurl: {grpcurl_cmd}")
        
        # 啟動 Registry 容器
        success, container_name, port = self.registry.start_operator_registry(config, status_callback)
        if not success:
            if status_callback:
                status_callback("❌ 啟動 Registry 容器失敗")
            return False
        
        try:
            if status_callback:
                status_callback("📡 查詢所有 Packages...")
            
            # 改用 self.op_mgr
            output = self.op_mgr.list_packages_grpc(grpcurl_cmd, port)
            if not output:
                if status_callback:
                    status_callback("❌ 查詢失敗")
                return False
            
            # 改用 self.op_mgr
            package_names = self.op_mgr.parse_list_output(output)
            if not package_names:
                if status_callback:
                    status_callback("❌ 解析失敗：未找到任何 package")
                return False
            
            if status_callback:
                status_callback(f"📦 找到 {len(package_names)} 個 packages，正在獲取詳細資訊...")
            
            packages = []
            for i, pkg_name in enumerate(package_names):
                if status_callback and i % 20 == 0:
                    status_callback(f"⏳ 處理中... ({i+1}/{len(package_names)})")
                
                # 改用 self.op_mgr
                pkg_info = self.op_mgr.get_package_basic_info(grpcurl_cmd, port, pkg_name)
                if pkg_info:
                    packages.append(pkg_info)
            
            if status_callback:
                status_callback("💾 儲存 operator_index.json...")
            
            # 改用 self.op_mgr 的儲存方法
            self.op_mgr.save_operator_index(packages)
            
            if status_callback:
                status_callback(f"✅ operator_index.json 已創建 ({len(packages)} packages)")
            
            return True
            
        finally:
            self.registry.stop_operator_registry(container_name)
            if status_callback:
                status_callback("🧹 容器已清除")
    
    def get_package_version_grpc(self, grpcurl_cmd, port, package_name, channel_name, max_retries=3):
        """透過 gRPC 查詢指定 channel 的最新版本，委派給 OperatorManager 處理"""
        # 改用 self.op_mgr
        return self.op_mgr.get_bundle_version(grpcurl_cmd, port, package_name, channel_name, max_retries)
    
    def _find_grpcurl(self):
        """尋找 grpcurl 命令路徑，向後相容的封裝方法"""
        return self.op_mgr.find_grpcurl()
  
    def _extract_tar(self, tar_path, target_dir, binary_name):
        """解壓 tar.gz 檔案並設定執行權限，回傳解壓後的二進位檔路徑"""
        if not os.path.exists(tar_path):
            log_error(f"找不到 tar 包：{tar_path}")
            return None
        
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
        
        try:
            subprocess.run(["tar", "-zxvf", tar_path, "-C", target_dir],
                          check=True, capture_output=True, text=True)
            
            target_binary = os.path.join(target_dir, binary_name)
            if os.path.isfile(target_binary):
                os.chmod(target_binary, 0o755)
                log_success(f"已設置執行權限：{target_binary}")
                return target_binary
            return None
        except subprocess.CalledProcessError as e:
            log_error(f"解壓失敗：{e}")
            return None
    
    def run_untar_oc_mirror(self, config):
        """解壓 oc-mirror 工具到 ~/.local/bin"""
        v_info = config.get('version_info', {})
        rhel_version = v_info.get('RHEL_VERSION', 'rhel9')
        tar_filename = f"oc-mirror.{rhel_version}.tar.gz"
        tar_path = os.path.join(self.install_source_dir, tar_filename)
        
        result = self._extract_tar(tar_path, os.path.expanduser("~/.local/bin"), "oc-mirror")
        return result is not None
    
    def run_untar_grpcurl(self, config):
        """解壓 grpcurl 工具到 ~/.local/bin"""
        tar_filename = "grpcurl_1.9.3_linux_x86_64.tar.gz"
        tar_path = os.path.join(self.install_source_dir, tar_filename)
        
        result = self._extract_tar(tar_path, os.path.expanduser("~/.local/bin"), "grpcurl")
        return result is not None