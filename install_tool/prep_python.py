import streamlit as st
import json
import os
import sys
from datetime import datetime

# 導入自定義模組
from config_manager import ConfigManager
from setup_wizard import SetupWizard
from operator_tools import OperatorTools
from yaml_generator import YAMLGenerator

# 獲取當前工作目錄 (取代 /root)
CURRENT_DIR = os.getcwd()

# 頁面配置
st.set_page_config(
    page_title="OpenShift Prep Tool",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化會話狀態
if 'current_view' not in st.session_state:
    st.session_state.current_view = 'tool_config'
if 'env_ready' not in st.session_state:
    st.session_state.env_ready = False
if 'tools_downloaded' not in st.session_state:
    st.session_state.tools_downloaded = False
if 'cluster_configured' not in st.session_state:
    st.session_state.cluster_configured = False
if 'operators_saved' not in st.session_state:
    st.session_state.operators_saved = False

def log_info(msg):
    st.info(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def log_error(msg):
    st.error(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def log_success(msg):
    st.success(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def main():
    # 側邊欄導航
    with st.sidebar:
        st.title("🛠️ OpenShift Prep")
        st.markdown("---")
        
        st.button("1. 🔧 Tool Config & Setup", use_container_width=True, key="nav_step1", disabled=False)
        st.button("2. 🏗️ Cluster Config", use_container_width=True, key="nav_step2", disabled=not st.session_state.tools_downloaded)
        st.button("3. 📦 Operators & CSI", use_container_width=True, key="nav_step3", disabled=not st.session_state.cluster_configured)
        st.button("4. ✅ Final Review", use_container_width=True, key="nav_step4", disabled=not os.path.exists(os.path.join(CURRENT_DIR, 'operators.json')))

        st.markdown("---")
        # 顯示當前進度
        st.write(f"**Current Step:** {st.session_state.current_view.replace('_', ' ').title()}")

    # 視圖路由
    if st.session_state.current_view == 'tool_config':
        show_tool_config_page()
    elif st.session_state.current_view == 'cluster_config':
        show_cluster_config_page()
    elif st.session_state.current_view == 'operators':
        show_operators_page()
    elif st.session_state.current_view == 'review':
        show_review_page()

def show_tool_config_page():
    st.title("1. 🔧 Tool Configuration & Environment Setup")
    st.markdown("配置需要下載的工具版本，並執行環境初始化。")
    
    config_manager = ConfigManager('tool_config.json')
    config = config_manager.get_config()
    wizard = SetupWizard(CURRENT_DIR)
    
    with st.form("tool_config_form"):
        st.subheader("Version Information")
        col1, col2 = st.columns(2)
        with col1:
            config['version_info']['OCP_RELEASE'] = st.text_input("OCP Release (e.g. 4.20.8)", value=config['version_info']['OCP_RELEASE'])
            config['version_info']['RHEL_VERSION'] = st.selectbox("RHEL Version", ["rhel9", "rhel8"], index=0 if config['version_info']['RHEL_VERSION'] == 'rhel9' else 1)
        with col2:
            config['version_info']['ARCHITECTURE'] = st.selectbox("Architecture", ["amd64", "arm64"], index=0 if config['version_info']['ARCHITECTURE'] == 'amd64' else 1)
            config['version_info']['HELM_VERSION'] = st.text_input("Helm Version", value=config['version_info']['HELM_VERSION'])
            config['version_info']['MIRROR_REGISTRY_VERSION'] = st.text_input("Mirror Registry Version", value=config['version_info']['MIRROR_REGISTRY_VERSION'])

        submitted = st.form_submit_button("Save & Run Environment Setup")
        
        if submitted:
            # 保存配置
            config_manager.save_config(config)
            st.success("配置已保存！開始執行環境初始化...")
            
            # Step 1: env_prep
            with st.expander("Step 1: Environment Preparation (Directories & Docker)", expanded=True):
                if wizard.run_env_prep():
                    st.session_state.env_ready = True
                    log_success("✅ env_prep 完成")
                else:
                    log_error("❌ env_prep 失敗")
                    st.stop()

            # Step 2: get_tools
            with st.expander("Step 2: Download Tools", expanded=True):
                if st.session_state.env_ready:
                    progress_bar = st.progress(0)
                    if wizard.run_get_tools(config, progress_callback=lambda p: progress_bar.progress(p)):
                        st.session_state.tools_downloaded = True
                        log_success("✅ get_tools 完成")
                    else:
                        log_error("❌ get_tools 失敗")
                        st.stop()
            
            # Step 3: untar_oc_mirror
            with st.expander("Step 3: Extract oc-mirror", expanded=True):
                if st.session_state.tools_downloaded:
                    if wizard.run_untar_oc_mirror(config):
                        log_success("✅ untar_oc_mirror 完成")
                        st.success("✅ tool_config 配置完成！")
                    else:
                        log_error("❌ untar_oc_mirror 失敗")
    # 下一步按鈕
    if st.session_state.tools_downloaded:
        st.divider()
        if st.button("➡️ Next: Cluster Config", use_container_width=True):
            st.session_state.current_view = 'cluster_config'
            st.rerun()

def show_cluster_config_page():
    st.title("2. 🏗️ Cluster Configuration")
    st.markdown("配置集群網絡、節點 IP 及認證信息，用於生成 `install-config.yaml`。")
    
    config_manager = ConfigManager('cluster_config.json')
    config = config_manager.get_config()

    if 'master_count' not in st.session_state:
        st.session_state.master_count = sum(1 for k in config['install_env'] if k.startswith('MASTER'))
    if 'infra_count' not in st.session_state:
        st.session_state.infra_count = sum(1 for k in config['install_env'] if k.startswith('INFRA'))
    if 'worker_count' not in st.session_state:
        st.session_state.worker_count = sum(1 for k in config['install_env'] if k.startswith('WORKER'))

    with st.form("cluster_config_form"):
        st.subheader("Cluster Identity")
        col1, col2 = st.columns(2)
        with col1:
            config['install_env']['INSTALL_MODE'] = st.selectbox("Install Mode", ["standard", "compact", "sno"], index=["standard", "compact", "sno"].index(config['install_env']['INSTALL_MODE']))
            config['install_env']['CLUSTER_DOMAIN'] = st.text_input("Cluster Name (metadata.name)", value=config['install_env']['CLUSTER_DOMAIN'], help="例如：ocp4")
        with col2:
            config['install_env']['BASE_DOMAIN'] = st.text_input("Base Domain", value=config['install_env']['BASE_DOMAIN'], help="例如：demo.lab")

        st.divider()
        st.subheader("Network & Nodes")

       # Master Node 配置
        st.markdown("#### Master Nodes")
        master_cols = st.columns([3, 1])
        with master_cols[0]:
            st.write(f"Current Master Count: {st.session_state.master_count}")
        with master_cols[1]:
            new_master_count = st.number_input(
                "Master Count",
                min_value=1,
                max_value=3,
                value=st.session_state.master_count,
                key="master_count_input"
            )
            if new_master_count != st.session_state.master_count:
                st.session_state.master_count = new_master_count
                st.rerun()

        # 動態生成 Master IP 輸入框
        for i in range(1, st.session_state.master_count + 1):
            ip_key = f"MASTER{i:02d}_IP"
            if ip_key not in config['install_env']:
                config['install_env'][ip_key] = ""
            config['install_env'][ip_key] = st.text_input(f"Master {i:02d} IP", value=config['install_env'].get(ip_key, ""), key=f"master_{i}_ip")

        # Infra Node 配置
        st.markdown("#### Infra Nodes")
        infra_cols = st.columns([3, 1])
        with infra_cols[0]:
            st.write(f"Current Infra Count: {st.session_state.infra_count}")
        with infra_cols[1]:
            new_infra_count = st.number_input(
                "Infra Count",
                min_value=0,
                max_value=3,
                value=st.session_state.infra_count,
                key="infra_count_input"
            )
            if new_infra_count != st.session_state.infra_count:
                st.session_state.infra_count = new_infra_count
                st.rerun()

        # 動態生成 Infra IP 輸入框
        for i in range(1, st.session_state.infra_count + 1):
            ip_key = f"INFRA{i:02d}_IP"
            if ip_key not in config['install_env']:
                config['install_env'][ip_key] = ""
            config['install_env'][ip_key] = st.text_input(f"Infra {i:02d} IP", value=config['install_env'].get(ip_key, ""), key=f"infra_{i}_ip")

        # Worker Node 配置
        st.markdown("#### Worker Nodes")
        worker_cols = st.columns([3, 1])
        with worker_cols[0]:
            st.write(f"Current Worker Count: {st.session_state.worker_count}")
        with worker_cols[1]:
            new_worker_count = st.number_input(
                "Worker Count",
                min_value=0,
                max_value=9,
                value=st.session_state.worker_count,
                key="worker_count_input"
            )
            if new_worker_count != st.session_state.worker_count:
                st.session_state.worker_count = new_worker_count
                st.rerun()

        # 動態生成 Worker IP 輸入框
        for i in range(1, st.session_state.worker_count + 1):
            ip_key = f"WORKER{i:02d}_IP"
            if ip_key not in config['install_env']:
                config['install_env'][ip_key] = ""
            config['install_env'][ip_key] = st.text_input(f"Worker {i:02d} IP", value=config['install_env'].get(ip_key, ""), key=f"worker_{i}_ip")

        # Bastion 和 Bootstrap IP
        st.markdown("#### Other IPs")
        col_bast, col_boot = st.columns(2)
        with col_bast:
            config['install_env']['BASTION_IP'] = st.text_input("Bastion IP", value=config['install_env']['BASTION_IP'])
        with col_boot:
            config['install_env']['BOOTSTRAP_IP'] = st.text_input("Bootstrap IP", value=config['install_env']['BOOTSTRAP_IP'])
            
        st.divider()
        st.subheader("Credentials & Keys")
        config['install_env']['REGISTRY_PASSWORD'] = st.text_input("Registry Password", value=config['install_env']['REGISTRY_PASSWORD'], type="password")
        
        col1, col2 = st.columns(2)
        with col1:
            # 支援輸入路徑或直接貼內容
            ssh_input = st.text_area("SSH Public Key", value=config['install_env']['SSH_KEY'], height=100, help="貼上 id_rsa.pub 內容或填寫路徑")
            # 簡單判斷：如果包含換行或 SSH 標頭則是內容，否則嘗試讀取文件
            if "ssh-" in ssh_input or "\n" in ssh_input:
                config['install_env']['SSH_KEY'] = ssh_input
            elif os.path.exists(ssh_input):
                with open(ssh_input, 'r') as f:
                    config['install_env']['SSH_KEY'] = f.read().strip()
            else:
                config['install_env']['SSH_KEY'] = ssh_input # 暫時存著，驗證時再檢查

        with col2:
            trust_input = st.text_area("Additional Trust Bundle (CA Cert)", value=config['install_env']['ADDITIONAL_TRUST_BUNDLE'], height=150, help="貼上 CA Certificate 內容")
            if "BEGIN CERTIFICATE" in trust_input or os.path.exists(trust_input):
                 if os.path.exists(trust_input):
                    with open(trust_input, 'r') as f:
                        config['install_env']['ADDITIONAL_TRUST_BUNDLE'] = f.read()
                 else:
                    config['install_env']['ADDITIONAL_TRUST_BUNDLE'] = trust_input
            else:
                config['install_env']['ADDITIONAL_TRUST_BUNDLE'] = trust_input

        submitted = st.form_submit_button("Save & Generate install-config.yaml")
        
        if submitted:
            # 驗證必填
            if not config['install_env']['CLUSTER_DOMAIN'] or not config['install_env']['BASE_DOMAIN']:
                st.error("Cluster Name 和 Base Domain 不能為空")
            elif not config['install_env']['SSH_KEY'] or not config['install_env']['ADDITIONAL_TRUST_BUNDLE']:
                st.error("SSH Key 和 Trust Bundle 不能為空")
            else:
                try:
                    config_manager.save_config(config)
                    
                    # 生成 YAML
                    from yaml_generator import YAMLGenerator
                    generator = YAMLGenerator(config, CURRENT_DIR)
                    yaml_content = generator.generate_install_config()
                    
                    output_path = os.path.join(CURRENT_DIR, "install/ocp", "install-config.yaml")
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    
                    with open(output_path, 'w') as f:
                        f.write(yaml_content)
                    
                    st.session_state.cluster_configured = True
                    st.success(f"✅ Configuration saved & `install-config.yaml` generated!<br>Path: `{output_path}`", unsafe_allow_html=True)
                    
                    with st.expander("Preview install-config.yaml"):
                        st.code(yaml_content, language="yaml")
                        
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    # 下一步按鈕
    if st.session_state.cluster_configured:
        st.divider()
        if st.button("➡️ Next: Operators & CSI", use_container_width=True):
            st.session_state.current_view = 'operators'
            st.rerun()

def show_operators_page():
    st.title("3. 📦 Operator Selection & CSI Configuration")
    st.markdown("選擇 CSI 驅動程序與需要的 Operators，生成 `imageset-config.yaml`。")
    
    # 初始化 CSI 配置 (若尚未存在)
    if 'csi_config' not in st.session_state:
        st.session_state.csi_config = {
            "CSI_TYPE": "nfs-csi",
            "TRIDENT_INSTALLER": "25.02.1"
        }
    
    # --- CSI 配置區塊 ---
    with st.expander("🖥️ CSI Driver Configuration", expanded=True):
        csi_type = st.selectbox(
            "Select CSI Type", 
            ["nfs-csi", "trident", "aws-ebs-csi", "vsphere-csi", "none"], 
            index=0 if st.session_state.csi_config['CSI_TYPE'] == 'nfs-csi' else (1 if st.session_state.csi_config['CSI_TYPE'] == 'trident' else 2)
        )
        st.session_state.csi_config['CSI_TYPE'] = csi_type
        
        trident_ver = ""
        if csi_type == 'trident':
            trident_ver = st.text_input("Trident Installer Version", value=st.session_state.csi_config['TRIDENT_INSTALLER'])
            st.session_state.csi_config['TRIDENT_INSTALLER'] = trident_ver
        else:
            st.session_state.csi_config['TRIDENT_INSTALLER'] = ""

    # --- Operator 選擇區塊 ---
    operator_tools = OperatorTools()
    
    if not os.path.exists(os.path.join(CURRENT_DIR, 'usr/bin/oc-mirror')) and not os.path.exists('/usr/bin/oc-mirror'):
        st.warning("⚠️ 未找到 oc-mirror，請確認第一步環境初始化已成功執行。")
        # 嘗試在当前目录查找
        oc_mirror_path = os.path.join(CURRENT_DIR, 'usr/bin/oc-mirror')
        if not os.path.exists(oc_mirror_path):
             st.error(f"找不到 oc-mirror 於 {CURRENT_DIR}/usr/bin 或 /usr/bin")
             return

    st.divider()
    st.subheader("Operator Hub Selection")
    
    # 獲取 Catalogs
    with st.spinner("Fetching available catalogs..."):
        try:
            catalogs = operator_tools.get_catalogs()
            if not catalogs:
                catalogs = ["registry.redhat.io/redhat/redhat-operator-index:v4.20"]
        except Exception as e:
            st.error(f"Error fetching catalogs: {str(e)}")
            catalogs = []

    selected_catalog = st.selectbox("Select Catalog", catalogs) if catalogs else ""
    
    if selected_catalog:
        if st.button("Load Packages"):
            with st.spinner("Fetching packages..."):
                try:
                    packages = operator_tools.get_packages(selected_catalog)
                    st.session_state.available_packages = packages
                except Exception as e:
                    st.error(f"Error fetching packages: {str(e)}")
        
        if 'available_packages' in st.session_state:
            selected_packages = st.multiselect("Select Packages to Include", st.session_state.available_packages)
            
            if selected_packages:
                st.session_state.selected_operators = []
                st.markdown("#### Configure Versions")
                
                for pkg in selected_packages:
                    with st.expander(f"Package: {pkg}"):
                        with st.spinner(f"Fetching versions for {pkg}..."):
                            try:
                                versions = operator_tools.get_package_versions(selected_catalog, pkg)
                                if versions:
                                    col1, col2 = st.columns([3, 1])
                                    with col1:
                                        min_v = st.selectbox("Min Version", versions, key=f"{pkg}_min", index=len(versions)-1)
                                        max_v = st.selectbox("Max Version", versions, key=f"{pkg}_max", index=len(versions)-1)
                                    with col2:
                                        st.write("Channel: stable") 
                                    
                                    st.session_state.selected_operators.append({
                                        "name": pkg,
                                        "channel": "stable",
                                        "minVersion": min_v,
                                        "maxVersion": max_v
                                    })
                                else:
                                    st.warning(f"No versions found for {pkg}")
                            except Exception as e:
                                st.error(f"Error fetching versions for {pkg}: {str(e)}")
                
                if st.button("💾 Save operators.json & Generate Imageset"):
                    # 1. 保存 operators.json
                    ops_path = os.path.join(CURRENT_DIR, 'operators.json')
                    with open(ops_path, 'w') as f:
                        json.dump(st.session_state.selected_operators, f, indent=2)
                    
                    # 2. 合併 CSI 配置到臨時 config 供生成器使用
                    # 讀取 cluster_config 作為基礎
                    cluster_mgr = ConfigManager('cluster_config.json')
                    full_config = cluster_mgr.get_config()
                    # 注入 CSI 配置
                    full_config['csi_info'] = st.session_state.csi_config
                    
                    # 3. 生成 imageset-config.yaml
                    try:
                        from yaml_generator import YAMLGenerator
                        generator = YAMLGenerator(full_config, CURRENT_DIR)
                        yaml_content = generator.generate_imageset_config()
                        
                        output_path = os.path.join(CURRENT_DIR, "install/ocp", "imageset-config.yaml")
                        with open(output_path, 'w') as f:
                            f.write(yaml_content)
                        
                        st.session_state.operators_saved = True
                        st.success(f"✅ `operators.json` & `imageset-config.yaml` generated!<br>Path: `{output_path}`", unsafe_allow_html=True)
                        
                        with st.expander("Preview imageset-config.yaml"):
                            st.code(yaml_content, language="yaml")
                            
                    except Exception as e:
                        st.error(f"Error generating imageset: {str(e)}")

    # 下一步按鈕
    if os.path.exists(os.path.join(CURRENT_DIR, 'operators.json')):
        st.divider()
        if st.button("➡️ Next: Final Review", use_container_width=True):
            st.session_state.current_view = 'review'
            st.rerun()

def show_review_page():
    st.title("4. ✅ Final Review")
    st.markdown("檢查所有生成的配置文件。")
    
    install_path = os.path.join(CURRENT_DIR, "install/ocp/install-config.yaml")
    imageset_path = os.path.join(CURRENT_DIR, "install/ocp/imageset-config.yaml")
    ops_path = os.path.join(CURRENT_DIR, "operators.json")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("install-config.yaml")
        if os.path.exists(install_path):
            with open(install_path, 'r') as f:
                st.code(f.read(), language="yaml")
        else:
            st.warning("File not found.")
            
    with col2:
        st.subheader("imageset-config.yaml")
        if os.path.exists(imageset_path):
            with open(imageset_path, 'r') as f:
                st.code(f.read(), language="yaml")
        else:
            st.warning("File not found.")
            
    st.divider()
    st.subheader("operators.json")
    if os.path.exists(ops_path):
        with open(ops_path, 'r') as f:
            st.json(json.load(f))
    else:
        st.warning("File not found.")

    # 完成提示
    st.divider()
    st.success("🎉 所有步驟已完成！配置文件已準備就緒。")

if __name__ == "__main__":
    main()