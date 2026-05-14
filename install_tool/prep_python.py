from logging import config
from re import match
import re
import shutil

import streamlit as st
import json
import os
import sys
import re
from datetime import datetime
import time

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

    with st.expander("🔐 Red Hat Registry Authentication", expanded=True):
        st.markdown("""
        請輸入您的 Red Hat 帳號以登入 `registry.redhat.io`。
        這將用於後續獲取 Operator Hub 的 Catalog 資訊。
        
        > 💡 **提示**：如果您沒有 Red Hat 帳號，可以註冊免費的 [Red Hat Developer 帳號](https://developers.redhat.com/register)
        """)
        
        col1, col2 = st.columns(2)
        with col1:
            rh_username = st.text_input(
                "Red Hat Username", 
                placeholder="您的 Red Hat 帳號",
                key="rh_username_input"
            )
        with col2:
            rh_password = st.text_input(
                "Red Hat Password", 
                type="password",
                placeholder="您的 Red Hat 密碼或 Service Account Token",
                key="rh_password_input"
            )
        
        # 儲存認證資訊到 session_state
        if rh_username and rh_password:
            st.session_state.rh_username = rh_username
            st.session_state.rh_password = rh_password
        
        # 登入按鈕
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            login_button = st.button("🔑 Login to Registry", type="primary", key="registry_login_btn")
        with col2:
            test_button = st.button("🔄 Test Login", key="registry_test_btn")
        
        if login_button:
            if not rh_username or not rh_password:
                st.error("請輸入 Username 和 Password")
            else:
                with st.spinner("正在登入 registry.redhat.io..."):
                    result, message = wizard.login_registry(rh_username, rh_password)
                    if result:
                        st.success(message)
                        st.session_state.registry_logged_in = True
                    else:
                        st.error(message)
                        st.session_state.registry_logged_in = False
        
        if test_button:
            if not st.session_state.get('registry_logged_in', False):
                st.warning("請先登入 Registry")
            else:
                with st.spinner("測試登入狀態..."):
                    result, message = wizard.test_registry_login()
                    if result:
                        st.success(message)
                    else:
                        st.error(message)

        # 顯示登入狀態
        if st.session_state.get('registry_logged_in', False):
            st.success("✅ 已成功登入 registry.redhat.io")
        else:
            st.info("ℹ️ 尚未登入 registry.redhat.io")

    st.divider()

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

    # Step 4: fetch_operator_catalog
    with st.expander("Step 4: Fetch Operator Catalog", expanded=True):
        # 檢查條件：tools_downloaded 且 oc-mirror 已解壓
        oc_mirror_binary = os.path.join(os.path.expanduser("~"), ".local/bin/oc-mirror")
        if not os.path.exists(oc_mirror_binary):
            oc_mirror_binary = os.path.join(CURRENT_DIR, "usr/bin/oc-mirror")
        
        if st.session_state.tools_downloaded and os.path.exists(oc_mirror_binary):
            catalog_file = os.path.join(CURRENT_DIR, "operator_catalog.json")
            
            if os.path.exists(catalog_file):
                # 顯示現有快取資訊
                try:
                    with open(catalog_file, 'r') as f:
                        catalog_data = json.load(f)
                        fetched_at = catalog_data.get('fetched_at', 'Unknown')
                        package_count = sum(
                            cat_info.get('package_count', 0) 
                            for cat_info in catalog_data.get('catalogs', {}).values()
                        )
                    
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        st.success(f"✅ Operator Catalog 就緒 ({package_count} packages)")
                    with col2:
                        st.caption(f"🕐 {fetched_at[:19]}")
                    with col3:
                        refresh_btn = st.button("🔄 刷新", key="refresh_catalog_btn", use_container_width=True)
                    
                    if refresh_btn:
                        # 使用 st.status 並傳入回調函數，加入動畫效果
                        with st.status("🔄 正在刷新 Operator Catalog...", expanded=True) as status_container:
                            
                            # 建立進度顯示元件
                            progress_bar = st.progress(0, "準備中...")
                            status_text = st.empty()
                            log_container = st.container()
                            
                            # 定義回調函數，用於更新狀態顯示
                            def update_status(msg):
                                """更新狀態訊息，同時模擬進度更新"""
                                with log_container:
                                    st.write(f"➤ {msg}")
                                
                                # 根據訊息內容更新進度
                                if "初始化" in msg:
                                    progress_bar.progress(5, "初始化中...")
                                elif "oc-mirror" in msg and "找到" in msg:
                                    progress_bar.progress(15, "已找到工具")
                                elif "認證" in msg:
                                    progress_bar.progress(25, "檢查認證...")
                                elif "連接到" in msg:
                                    progress_bar.progress(35, "連接 Registry...")
                                elif "執行" in msg:
                                    progress_bar.progress(40, "執行查詢中...")
                                    status_text.info("⏳ 正在從 Red Hat Registry 拉取 Operator 列表，請耐心等待...")
                                elif "解析" in msg:
                                    progress_bar.progress(75, "解析資料中...")
                                elif "找到" in msg and "packages" in msg:
                                    progress_bar.progress(90, "處理資料中...")
                                elif "儲存" in msg:
                                    progress_bar.progress(95, "儲存快取...")
                                elif "完成" in msg:
                                    progress_bar.progress(100, "完成!")
                            
                            # 執行獲取任務
                            if wizard.run_get_operator_catalog(config, status_callback=update_status):
                                progress_bar.progress(100, "完成!")
                                status_text.success("✅ 所有任務完成!")
                                status_container.update(
                                    label="✅ Operator Catalog 刷新完成!", 
                                    state="complete", 
                                    expanded=False
                                )
                                log_success("✅ Operator Catalog 刷新完成")
                                st.balloons()
                                time.sleep(1)
                                st.rerun()
                            else:
                                progress_bar.empty()
                                status_text.empty()
                                status_container.update(
                                    label="❌ 刷新失敗", 
                                    state="error", 
                                    expanded=True
                                )
                                st.error("❌ Operator Catalog 刷新失敗")
                                st.error("請確認網路連線和認證狀態")
                                log_error("❌ Operator Catalog 刷新失敗")
                                                    
                except Exception as e:
                    st.error(f"讀取快取失敗: {e}")
            else:
                # 首次獲取 - 使用動畫和進度條
                st.info("📡 尚未獲取 Operator Catalog")
                st.markdown("""
                獲取 Operator Catalog 可以讓您在後續步驟中：
                - 🔍 快速瀏覽可用的 Operators
                - ⚡ 即時選擇需要的套件
                - 📦 無需等待即可配置
                
                首次獲取約需 **3-5 分鐘**，請耐心等待。
                """)
                
                if st.button("🚀 開始獲取 Operator Catalog", type="primary", use_container_width=True):
                    # 建立任務狀態容器
                    with st.status("📡 正在獲取 Operator Catalog...", expanded=True) as status_container:
                        
                        # 建立進度顯示元件
                        progress_bar = st.progress(0, "準備開始...")
                        status_text = st.empty()
                        log_container = st.container()
                        
                        # 顯示動畫提示
                        status_text.info("🔍 初始化任務...")
                        
                        # 定義回調函數，加入詳細的進度更新
                        def update_status(msg):
                            """更新狀態訊息，同時更新進度條"""
                            # 在日誌容器中顯示訊息
                            with log_container:
                                st.write(f"➤ {msg}")
                            
                            # 根據關鍵字更新進度條
                            if "初始化" in msg:
                                progress_bar.progress(5, "初始化任務...")
                                status_text.info("🔍 正在初始化獲取任務...")
                            elif "版本" in msg:
                                progress_bar.progress(10, "讀取版本資訊...")
                            elif "尋找" in msg and "oc-mirror" in msg:
                                progress_bar.progress(15, "尋找 oc-mirror...")
                            elif "找到" in msg and "oc-mirror" in msg:
                                progress_bar.progress(20, "已找到 oc-mirror")
                                status_text.info("✅ 工具已就緒")
                            elif "認證" in msg:
                                progress_bar.progress(25, "檢查認證...")
                                status_text.info("🔐 檢查 Red Hat Registry 認證...")
                            elif "認證文件存在" in msg:
                                progress_bar.progress(30, "認證通過")
                            elif "連接到" in msg:
                                progress_bar.progress(35, "連接 Registry...")
                                status_text.info("📡 正在連接到 Red Hat Registry...")
                            elif "執行" in msg:
                                progress_bar.progress(40, "執行查詢命令...")
                                status_text.info("⏳ 正在執行 oc-mirror 查詢，這需要一些時間...")
                                # 顯示等待動畫（使用 spinner）
                                with st.spinner("🔄 從 Red Hat Registry 拉取 Operator 列表..."):
                                    pass
                            elif "解析" in msg:
                                progress_bar.progress(75, "解析資料...")
                                status_text.info("📊 正在解析 Operator 列表...")
                            elif "找到" in msg and "packages" in msg:
                                progress_bar.progress(90, "處理完成")
                                status_text.success(f"📦 {msg}")
                            elif "儲存" in msg:
                                progress_bar.progress(95, "儲存快取...")
                                status_text.info("💾 正在儲存快取檔案...")
                            elif "完成" in msg:
                                progress_bar.progress(100, "完成!")
                                status_text.success("✅ 所有任務完成!")
                        
                        # 執行獲取任務
                        success = wizard.run_get_operator_catalog(config, status_callback=update_status)
                        
                        if success:
                            progress_bar.progress(100, "完成!")
                            status_text.success("🎉 Operator Catalog 獲取完成!")
                            status_container.update(
                                label="✅ Operator Catalog 獲取完成!", 
                                state="complete", 
                                expanded=False
                            )
                            log_success("✅ Operator Catalog 獲取完成")
                            st.balloons()
                            time.sleep(1.5)
                            st.rerun()
                        else:
                            progress_bar.empty()
                            status_text.empty()
                            log_container.empty()
                            status_container.update(
                                label="❌ 獲取失敗", 
                                state="error", 
                                expanded=True
                            )
                            st.error("❌ Operator Catalog 獲取失敗")
                            st.markdown("""
                            ### 可能的解決方法：
                            1. 🔐 確認已成功登入 Red Hat Registry
                            2. 🌐 檢查網路連線是否正常
                            3. ⏱️ 嘗試增加 timeout 設定
                            4. 🔄 重新整理頁面後再試
                            """)
                            log_error("❌ Operator Catalog 獲取失敗")

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

    # 初始化節點計數 (只計算 _IP 結尾的配置)
    if 'master_count' not in st.session_state:
        st.session_state.master_count = max(1, sum(1 for k in config['install_env'] if k.startswith('MASTER') and k.endswith('_IP')))
    if 'infra_count' not in st.session_state:
        st.session_state.infra_count = sum(1 for k in config['install_env'] if k.startswith('INFRA') and k.endswith('_IP'))
    if 'worker_count' not in st.session_state:
        st.session_state.worker_count = sum(1 for k in config['install_env'] if k.startswith('WORKER') and k.endswith('_IP'))

    # 確保計數至少為 1 (Master) 或 0 (Infra/Worker)
    if st.session_state.master_count < 1:
        st.session_state.master_count = 1

    if 'version_info' not in config:
        config['version_info'] = {}

    if 'MACHINE_NETWORK_CIDR' not in config['install_env']:
        config['install_env']['MACHINE_NETWORK_CIDR'] = ''
    if 'CLUSTER_NETWORK_CIDR' not in config['install_env']:
        config['install_env']['CLUSTER_NETWORK_CIDR'] = '10.128.0.0/14'
    if 'CLUSTER_NETWORK_HOST_PREFIX' not in config['install_env']:
        config['install_env']['CLUSTER_NETWORK_HOST_PREFIX'] = 23
    if 'SERVICE_NETWORK_CIDR' not in config['install_env']:
        config['install_env']['SERVICE_NETWORK_CIDR'] = '172.30.0.0/16'
    if 'NETWORK_TYPE' not in config['install_env']:
        config['install_env']['NETWORK_TYPE'] = 'OVNKubernetes'

    def is_valid_ipv4(ip):
        if not ip:
            return True  # 空值不算錯誤
        import re
        pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
        match = re.match(pattern, ip)
        if not match:
            return False
        return all(0 <= int(g) <= 255 for g in match.groups())

    def is_valid_mac(mac):
        """驗證 MAC Address 格式"""
        if not mac:
            return True  # 空值不算錯誤
        pattern = r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'
        return bool(re.match(pattern, mac))

    st.subheader("Cluster Identity")
    col1, col2, col3 = st.columns(3)
    with col1:
        config['install_env']['INSTALL_MODE'] = st.selectbox(
            "Install Mode", 
            ["standard", "compact", "sno"], 
            index=["standard", "compact", "sno"].index(config['install_env']['INSTALL_MODE']),
            key="install_mode_select"
        )
        
    with col2:
        config['install_env']['CLUSTER_DOMAIN'] = st.text_input(
            "Cluster Name (metadata.name)", 
            value=config['install_env']['CLUSTER_DOMAIN'], 
            help="例如：ocp4",
            key="cluster_domain_input"
        )
        
    with col3:
        config['install_env']['BASE_DOMAIN'] = st.text_input(
            "Base Domain", 
            value=config['install_env']['BASE_DOMAIN'], 
            help="例如：demo.lab",
            key="base_domain_input"
        )

    # 從 tool_config.json 讀取 OCP_RELEASE，自動解析版本
    tool_config_manager = ConfigManager('tool_config.json')
    tool_config = tool_config_manager.get_config()
    ocp_release = tool_config.get('version_info', {}).get('OCP_RELEASE', '4.20.8')

    # 解析主版本號 (例如: 4.20.8 -> 4.20)
    match = re.match(r'(\d+\.\d+)', ocp_release)
    if match:
        ocp_version = match.group(1)
    else:
        ocp_version = '4.20'  # 預設值

    config['version_info']['OCP_VERSION'] = ocp_version
    config['version_info']['OCP_RELEASE'] = ocp_release

    # 顯示當前的 OCP Version (只讀)
    st.info(f"📦 OCP Version: **{ocp_version}** (Release: {ocp_release})")

    cluster_name = config['install_env']['CLUSTER_DOMAIN'].split('.')[0] if '.' in config['install_env']['CLUSTER_DOMAIN'] else config['install_env']['CLUSTER_DOMAIN']
    if cluster_name and config['install_env']['BASE_DOMAIN']:
        registry_fqdn = f"bastion.{cluster_name}.{config['install_env']['BASE_DOMAIN']}"
        st.info(f"📌 Registry URL will be: **{registry_fqdn}:8443**")

        st.divider()
        st.subheader("Network & Nodes")

    # ===== Master Node Count (在 form 外部) =====
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
        # 直接比較並更新，不需要在 form 內
        if new_master_count != st.session_state.master_count:
            old_count = st.session_state.master_count
            st.session_state.master_count = new_master_count
            
            # 清理多餘的 IP
            for i in range(new_master_count + 1, old_count + 1):
                ip_key = f"MASTER{i:02d}_IP"
                state_key = f"ip_{ip_key}"
                if state_key in st.session_state:
                    del st.session_state[state_key]
                if ip_key in config['install_env']:
                    del config['install_env'][ip_key]
            
            # 初始化新的 IP
            for i in range(old_count + 1, new_master_count + 1):
                ip_key = f"MASTER{i:02d}_IP"
                state_key = f"ip_{ip_key}"
                if state_key not in st.session_state:
                    st.session_state[state_key] = ""
            
            # 保存 config
            config_manager.save_config(config)
            st.rerun()

    # 動態生成 Master IP 輸入框
    for i in range(1, st.session_state.master_count + 1):
        ip_key = f"MASTER{i:02d}_IP"
        mac_key = f"MASTER{i:02d}_MAC"
        iface_key = f"MASTER{i:02d}_INTERFACE"
        device_key = f"MASTER{i:02d}_DEVICE"

        state_key = f"ip_{ip_key}"
        mac_state_key = f"mac_{mac_key}"
        iface_state_key = f"iface_{iface_key}"
        device_state_key = f"device_{device_key}"
        
        if state_key not in st.session_state:
            st.session_state[state_key] = config['install_env'].get(ip_key, "")
        if mac_state_key not in st.session_state:
            st.session_state[mac_state_key] = config['install_env'].get(mac_key, "BC:24:11:99:B8:1B")
        if iface_state_key not in st.session_state:
            st.session_state[iface_state_key] = config['install_env'].get(iface_key, "ens18")
        if device_state_key not in st.session_state:
            st.session_state[device_state_key] = config['install_env'].get(device_key, "/dev/sda")

        col1, col2, col3, col4 = st.columns([3, 3, 2, 2])
        with col1:
            ip_value = st.text_input(
                f"Master {i:02d} IP",
                value=st.session_state[state_key],
                key=f"input_{ip_key}"
            )
        with col2:
            mac_value = st.text_input(
                f"Master {i:02d} MAC",
                value=st.session_state[mac_state_key],
                key=f"input_{mac_key}"
            )
        with col3:
            iface_value = st.text_input(
                f"Master {i:02d} Interface",
                value=st.session_state[iface_state_key],
                key=f"input_{iface_key}"
            )
        with col4:
            device_value = st.text_input(
                f"Master {i:02d} Device",
                value=st.session_state[device_state_key],
                key=f"input_{device_key}"
            )

        # Validation
        if ip_value and not is_valid_ipv4(ip_value):
            st.error("❌ Invalid IP")
        if mac_value and not is_valid_mac(mac_value):
            st.error("❌ Invalid MAC")
        
        st.session_state[state_key] = ip_value
        st.session_state[mac_state_key] = mac_value
        st.session_state[iface_state_key] = iface_value
        st.session_state[device_state_key] = device_value
        config['install_env'][ip_key] = ip_value
        config['install_env'][mac_key] = mac_value
        config['install_env'][iface_key] = iface_value
        config['install_env'][device_key] = device_value

    # ===== Infra Node Count (在 form 外部) =====
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
            old_count = st.session_state.infra_count
            st.session_state.infra_count = new_infra_count
            
            for i in range(new_infra_count + 1, old_count + 1):
                ip_key = f"INFRA{i:02d}_IP"
                state_key = f"ip_{ip_key}"
                if state_key in st.session_state:
                    del st.session_state[state_key]
                if ip_key in config['install_env']:
                    del config['install_env'][ip_key]
            
            for i in range(old_count + 1, new_infra_count + 1):
                ip_key = f"INFRA{i:02d}_IP"
                state_key = f"ip_{ip_key}"
                if state_key not in st.session_state:
                    st.session_state[state_key] = ""
            
            config_manager.save_config(config)
            st.rerun()

    # 動態生成 Infra IP 輸入框
    for i in range(1, st.session_state.infra_count + 1):
        ip_key = f"INFRA{i:02d}_IP"
        mac_key = f"INFRA{i:02d}_MAC"
        iface_key = f"INFRA{i:02d}_INTERFACE"
        device_key = f"INFRA{i:02d}_DEVICE"

        state_key = f"ip_{ip_key}"
        mac_state_key = f"mac_{mac_key}"
        iface_state_key = f"iface_{iface_key}"
        device_state_key = f"device_{device_key}"
        
        if state_key not in st.session_state:
            st.session_state[state_key] = config['install_env'].get(ip_key, "")
        if mac_state_key not in st.session_state:
            st.session_state[mac_state_key] = config['install_env'].get(mac_key, "BC:24:11:99:B8:1B")
        if iface_state_key not in st.session_state:
            st.session_state[iface_state_key] = config['install_env'].get(iface_key, "ens18")
        if device_state_key not in st.session_state:
            st.session_state[device_state_key] = config['install_env'].get(device_key, "/dev/sda")

        col1, col2, col3, col4 = st.columns([3, 3, 2, 2])
        with col1:
            ip_value = st.text_input(
                f"INFRA {i:02d} IP",
                value=st.session_state[state_key],
                key=f"input_{ip_key}"
            )
        with col2:
            mac_value = st.text_input(
                f"INFRA {i:02d} MAC",
                value=st.session_state[mac_state_key],
                key=f"input_{mac_key}"
            )
        with col3:
            iface_value = st.text_input(
                f"INFRA {i:02d} Interface",
                value=st.session_state[iface_state_key],
                key=f"input_{iface_key}"
            )
        with col4:
            device_value = st.text_input(
                f"INFRA {i:02d} Device",
                value=st.session_state[device_state_key],
                key=f"input_{device_key}"
            )

        # Validation
        if ip_value and not is_valid_ipv4(ip_value):
            st.error("❌ Invalid IP")
        if mac_value and not is_valid_mac(mac_value):
            st.error("❌ Invalid MAC")
        
        st.session_state[state_key] = ip_value
        st.session_state[mac_state_key] = mac_value
        st.session_state[iface_state_key] = iface_value
        st.session_state[device_state_key] = device_value
        config['install_env'][ip_key] = ip_value
        config['install_env'][mac_key] = mac_value
        config['install_env'][iface_key] = iface_value
        config['install_env'][device_key] = device_value

    # ===== Worker Node Count (在 form 外部) =====
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
            old_count = st.session_state.worker_count
            st.session_state.worker_count = new_worker_count
            
            for i in range(new_worker_count + 1, old_count + 1):
                ip_key = f"WORKER{i:02d}_IP"
                state_key = f"ip_{ip_key}"
                if state_key in st.session_state:
                    del st.session_state[state_key]
                if ip_key in config['install_env']:
                    del config['install_env'][ip_key]
            
            for i in range(old_count + 1, new_worker_count + 1):
                ip_key = f"WORKER{i:02d}_IP"
                state_key = f"ip_{ip_key}"
                if state_key not in st.session_state:
                    st.session_state[state_key] = ""
            
            config_manager.save_config(config)
            st.rerun()

    # 動態生成 Worker IP 輸入框
    for i in range(1, st.session_state.worker_count + 1):
        ip_key = f"WORKER{i:02d}_IP"
        mac_key = f"WORKER{i:02d}_MAC"
        iface_key = f"WORKER{i:02d}_INTERFACE"
        device_key = f"WORKER{i:02d}_DEVICE"

        state_key = f"ip_{ip_key}"
        mac_state_key = f"mac_{mac_key}"
        iface_state_key = f"iface_{iface_key}"
        device_state_key = f"device_{device_key}"
        
        if state_key not in st.session_state:
            st.session_state[state_key] = config['install_env'].get(ip_key, "")
        if mac_state_key not in st.session_state:
            st.session_state[mac_state_key] = config['install_env'].get(mac_key, "BC:24:11:99:B8:1B")
        if iface_state_key not in st.session_state:
            st.session_state[iface_state_key] = config['install_env'].get(iface_key, "ens18")
        if device_state_key not in st.session_state:
            st.session_state[device_state_key] = config['install_env'].get(device_key, "/dev/sda")

        col1, col2, col3, col4 = st.columns([3, 3, 2, 2])
        with col1:
            ip_value = st.text_input(
                f"Worker {i:02d} IP",
                value=st.session_state[state_key],
                key=f"input_{ip_key}"
            )
        with col2:
            mac_value = st.text_input(
                f"Worker {i:02d} MAC",
                value=st.session_state[mac_state_key],
                key=f"input_{mac_key}"
            )
        with col3:
            iface_value = st.text_input(
                f"Worker {i:02d} Interface",
                value=st.session_state[iface_state_key],
                key=f"input_{iface_key}"
            )
        with col4:
            device_value = st.text_input(
                f"Worker {i:02d} Device",
                value=st.session_state[device_state_key],
                key=f"input_{device_key}"
            )

        # Validation
        if ip_value and not is_valid_ipv4(ip_value):
            st.error("❌ Invalid IP")
        if mac_value and not is_valid_mac(mac_value):
            st.error("❌ Invalid MAC")
        
        st.session_state[state_key] = ip_value
        st.session_state[mac_state_key] = mac_value
        st.session_state[iface_state_key] = iface_value
        st.session_state[device_state_key] = device_value
        config['install_env'][ip_key] = ip_value
        config['install_env'][mac_key] = mac_value
        config['install_env'][iface_key] = iface_value
        config['install_env'][device_key] = device_value

    # ===== 將提交部分包在 form 內 =====
    st.divider()
    with st.form("cluster_config_form"):
        st.subheader("Other IPs")
        col_bast, col_boot, col_gw = st.columns(3)
        with col_bast:
            bastion_ip = st.text_input(
                "Bastion IP", 
                value=config['install_env'].get('BASTION_IP', ''),
                key="bastion_ip_input"
            )
            if bastion_ip and not is_valid_ipv4(bastion_ip):
                st.error("❌ Invalid IP")
            config['install_env']['BASTION_IP'] = bastion_ip
        with col_gw:
            gateway_ip = st.text_input(
                "Gateway IP",
                value=config['install_env'].get('GATEWAY_IP', ''),
                key="gateway_ip_input"
            )
            if gateway_ip and not is_valid_ipv4(gateway_ip):
                st.error("❌ Invalid IP")
            config['install_env']['GATEWAY_IP'] = gateway_ip
        with col_boot:
            bootstrap_ip = st.text_input(
                "Bootstrap IP (optional)", 
                value=config['install_env'].get('BOOTSTRAP_IP', ''),
                key="bootstrap_ip_input"
            )
            if bootstrap_ip and not is_valid_ipv4(bootstrap_ip):
                st.error("❌ Invalid IP")
            config['install_env']['BOOTSTRAP_IP'] = bootstrap_ip

        st.subheader("Network Configuration")
        col1, col2 = st.columns(2)
        with col1:
            config['install_env']['MACHINE_NETWORK_CIDR'] = st.text_input(
                "Machine Network CIDR (optional, auto-generated from Bastion IP if empty)",
                value=config['install_env']['MACHINE_NETWORK_CIDR'],
                help="Leave empty to auto-generate from Bastion IP",
                key="machine_cidr_input"
            )
            config['install_env']['CLUSTER_NETWORK_CIDR'] = st.text_input(
                "Cluster Network CIDR",
                value=config['install_env']['CLUSTER_NETWORK_CIDR'],
                key="cluster_cidr_input"
            )
        with col2:
            config['install_env']['CLUSTER_NETWORK_HOST_PREFIX'] = st.number_input(
                "Host Prefix",
                min_value=1,
                max_value=32,
                value=int(config['install_env'].get('CLUSTER_NETWORK_HOST_PREFIX', '23')),
                key="host_prefix_input"
            )
            config['install_env']['SERVICE_NETWORK_CIDR'] = st.text_input(
                "Service Network CIDR",
                value=config['install_env']['SERVICE_NETWORK_CIDR'],
                key="service_cidr_input"
            )
        
        config['install_env']['NETWORK_TYPE'] = st.selectbox(
            "Network Type",
            ["OVNKubernetes", "OpenShiftSDN"],
            index=0 if config['install_env']['NETWORK_TYPE'] == 'OVNKubernetes' else 1,
            key="network_type_input"
        )

        st.subheader("Credentials & Keys")
        config['install_env']['REGISTRY_PASSWORD'] = st.text_input(
            "Registry Password", 
            value=config['install_env']['REGISTRY_PASSWORD'], 
            type="password", 
            key="registry_pwd_input"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            ssh_input = st.text_area(
                "SSH Public Key", 
                value=config['install_env']['SSH_KEY'], 
                height=100, 
                help="貼上 id_rsa.pub 內容或填寫路徑", 
                key="ssh_key_input"
            )
            if "ssh-" in ssh_input or "\n" in ssh_input:
                config['install_env']['SSH_KEY'] = ssh_input
            elif os.path.exists(ssh_input):
                with open(ssh_input, 'r') as f:
                    config['install_env']['SSH_KEY'] = f.read().strip()
            else:
                config['install_env']['SSH_KEY'] = ssh_input

        with col2:
            trust_input = st.text_area(
                "Additional Trust Bundle (CA Cert)", 
                value=config['install_env']['ADDITIONAL_TRUST_BUNDLE'], 
                height=150, 
                help="貼上 CA Certificate 內容", 
                key="trust_bundle_input"
            )
            if "BEGIN CERTIFICATE" in trust_input or os.path.exists(trust_input):
                if os.path.exists(trust_input):
                    with open(trust_input, 'r') as f:
                        config['install_env']['ADDITIONAL_TRUST_BUNDLE'] = f.read()
                else:
                    config['install_env']['ADDITIONAL_TRUST_BUNDLE'] = trust_input
            else:
                config['install_env']['ADDITIONAL_TRUST_BUNDLE'] = trust_input

        submitted = st.form_submit_button("💾 Save & Generate install-config.yaml")
        
        if submitted:
            # 驗證必填
            if not config['install_env']['CLUSTER_DOMAIN'] or not config['install_env']['BASE_DOMAIN']:
                st.error("Cluster Name 和 Base Domain 不能為空")
            elif not config['install_env'].get('SSH_KEY'):
                st.error("SSH Key 不能為空")
            elif not config['install_env'].get('REGISTRY_PASSWORD'):
                st.error("Registry Password 不能為空")
            else:
                try:
                    # 同步所有 node IP, MAC, Interface, Device (確保 form 外的值被保存)
                    for i in range(1, st.session_state.master_count + 1):
                        ip_key = f"MASTER{i:02d}_IP"
                        mac_key = f"MASTER{i:02d}_MAC"
                        iface_key = f"MASTER{i:02d}_INTERFACE"
                        device_key = f"MASTER{i:02d}_DEVICE"
                        config['install_env'][ip_key] = st.session_state.get(f"ip_{ip_key}", "")
                        config['install_env'][mac_key] = st.session_state.get(f"mac_{mac_key}", "")
                        config['install_env'][iface_key] = st.session_state.get(f"iface_{iface_key}", "")
                        config['install_env'][device_key] = st.session_state.get(f"device_{device_key}", "")
                    
                    for i in range(1, st.session_state.infra_count + 1):
                        ip_key = f"INFRA{i:02d}_IP"
                        mac_key = f"INFRA{i:02d}_MAC"
                        iface_key = f"INFRA{i:02d}_INTERFACE"
                        device_key = f"INFRA{i:02d}_DEVICE"
                        config['install_env'][ip_key] = st.session_state.get(f"ip_{ip_key}", "")
                        config['install_env'][mac_key] = st.session_state.get(f"mac_{mac_key}", "")
                        config['install_env'][iface_key] = st.session_state.get(f"iface_{iface_key}", "")
                        config['install_env'][device_key] = st.session_state.get(f"device_{device_key}", "")
                    
                    for i in range(1, st.session_state.worker_count + 1):
                        ip_key = f"WORKER{i:02d}_IP"
                        mac_key = f"WORKER{i:02d}_MAC"
                        iface_key = f"WORKER{i:02d}_INTERFACE"
                        device_key = f"WORKER{i:02d}_DEVICE"
                        config['install_env'][ip_key] = st.session_state.get(f"ip_{ip_key}", "")
                        config['install_env'][mac_key] = st.session_state.get(f"mac_{mac_key}", "")
                        config['install_env'][iface_key] = st.session_state.get(f"iface_{iface_key}", "")
                        config['install_env'][device_key] = st.session_state.get(f"device_{device_key}", "")
                    
                    config_manager.save_config(config)
                    
                    # 生成 YAML
                    from yaml_generator import YAMLGenerator
                    generator = YAMLGenerator(config, CURRENT_DIR)
                    yaml_content = generator.generate_install_config()
                    
                    output_path = os.path.join(CURRENT_DIR, "install/ocp/install-config.yaml")
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    
                    with open(output_path, 'w') as f:
                        f.write(yaml_content)

                    # 生成 AgentConfig
                    agent_yaml_content = generator.generate_agent_config()
                    agent_output_path = os.path.join(CURRENT_DIR, "install/ocp/agent-config.yaml")
                    with open(agent_output_path, 'w') as f:
                        f.write(agent_yaml_content)

                    st.session_state.cluster_configured = True
                    st.success(f"✅ Configuration saved & `install-config.yaml` generated!")
                    st.success(f"✅ `agent-config.yaml` generated!")

                    with st.expander("Preview install-config.yaml"):
                        st.code(yaml_content, language="yaml")

                    with st.expander("Preview agent-config.yaml"):
                        st.code(agent_yaml_content, language="yaml")

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
            ["nfs-csi", "trident", "none"], 
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
    
    # 檢查 oc-mirror 是否可用
    try:
        ocp_version = operator_tools.get_ocp_version()
        st.info(f"🎯 Target OCP Version: **{ocp_version}**")
    except Exception:
        st.warning("⚠️ 無法讀取 OCP 版本，將使用預設值 4.20")
        ocp_version = "4.20"

    st.divider()
    st.subheader("📦 Operator Hub Selection")
    
    # 獲取 Catalogs (需求1)
    with st.spinner("🔍 Fetching available catalogs from registry..."):
        try:
            catalogs = operator_tools.get_catalogs()
            if not catalogs:
                st.error("❌ 無法獲取 catalogs，請檢查網路連接和 oc-mirror 配置")
                return
            st.success(f"✅ Found {len(catalogs)} catalogs")
        except Exception as e:
            st.error(f"❌ Error fetching catalogs: {str(e)}")
            st.info("💡 請確保 oc-mirror 已正確安裝並可訪問 Red Hat Registry")
            return

    # Catalog 選擇
    selected_catalog = st.selectbox(
        "Select Catalog", 
        catalogs,
        key="catalog_select",
        help="選擇要瀏覽的 Operator Catalog"
    )
    
    if selected_catalog:
        # Load Packages 按鈕 (需求2)
        col1, col2 = st.columns([1, 3])
        with col1:
            load_packages = st.button("🔍 Load Packages", type="primary", key="load_packages_btn")
        
        if load_packages:
            with st.spinner(f"📥 Fetching packages from {selected_catalog.split('/')[-1]}..."):
                try:
                    packages = operator_tools.get_packages(selected_catalog)
                    if packages:
                        st.session_state.available_packages = packages
                        st.success(f"✅ Loaded {len(packages)} packages")
                    else:
                        st.error("❌ No packages found or failed to fetch")
                        st.session_state.available_packages = []
                except Exception as e:
                    st.error(f"❌ Error fetching packages: {str(e)}")
                    st.session_state.available_packages = []
        
        # 顯示可用 packages (需求3)
        if 'available_packages' in st.session_state and st.session_state.available_packages:
            st.markdown("---")
            st.markdown("### Select Packages")
            
            # 搜索過濾
            search_term = st.text_input("🔎 Search packages", key="package_search")
            
            filtered_packages = st.session_state.available_packages
            if search_term:
                filtered_packages = [p for p in filtered_packages if search_term.lower() in p.lower()]
            
            selected_packages = st.multiselect(
                f"Select Packages ({len(filtered_packages)} available)",
                filtered_packages,
                key="package_multiselect",
                help="選擇要包含在 imageset 中的 operators"
            )
            
            if selected_packages:
                st.markdown("---")
                st.markdown("### ⚙️ Configure Selected Operators")
                
                # 初始化 operator_configs
                if 'operator_configs' not in st.session_state:
                    st.session_state.operator_configs = {}
                
                # 為每個選中的 package 配置 channel 和版本
                for pkg in selected_packages:
                    with st.expander(f"📦 {pkg}", expanded=True):
                        # 獲取 channels
                        with st.spinner(f"Fetching channels for {pkg}..."):
                            try:
                                channel_info = operator_tools.get_package_channels(selected_catalog, pkg)
                                
                                if channel_info['channels']:
                                    # Channel 選擇
                                    channel_names = [ch['name'] for ch in channel_info['channels']]
                                    default_channel = channel_info.get('default_channel', channel_names[0])
                                    default_index = channel_names.index(default_channel) if default_channel in channel_names else 0
                                    
                                    selected_channel = st.selectbox(
                                        "Channel",
                                        channel_names,
                                        index=default_index,
                                        key=f"{pkg}_channel"
                                    )
                                    
                                    # 獲取該 channel 的版本
                                    with st.spinner(f"Fetching versions for {selected_channel}..."):
                                        versions = operator_tools.get_channel_versions(
                                            selected_catalog, pkg, selected_channel
                                        )
                                    
                                    if versions:
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            min_version = st.selectbox(
                                                "Min Version",
                                                versions,
                                                index=len(versions)-1,  # 預設選最新版本
                                                key=f"{pkg}_min_version"
                                            )
                                        with col2:
                                            max_version = st.selectbox(
                                                "Max Version",
                                                versions,
                                                index=len(versions)-1,  # 預設選最新版本
                                                key=f"{pkg}_max_version"
                                            )
                                        
                                        # 存儲配置
                                        st.session_state.operator_configs[pkg] = {
                                            "name": pkg,
                                            "channel": selected_channel,
                                            "minVersion": min_version,
                                            "maxVersion": max_version
                                        }
                                        
                                        st.success(f"✅ {pkg}: {selected_channel} ({min_version} - {max_version})")
                                    else:
                                        st.warning(f"⚠️ No versions found for channel {selected_channel}")
                                else:
                                    st.warning(f"⚠️ No channels found for {pkg}")
                                    
                            except Exception as e:
                                st.error(f"❌ Error configuring {pkg}: {str(e)}")
                
                # 保存按鈕
                st.markdown("---")
                if st.button("💾 Save operators.json & Generate Imageset", type="primary", use_container_width=True):
                    if st.session_state.operator_configs:
                        # 1. 準備 operators 數據
                        operators_list = []
                        for pkg_name, config in st.session_state.operator_configs.items():
                            operators_list.append({
                                "name": config["name"],
                                "channels": [{
                                    "name": config["channel"],
                                    "minVersion": config["minVersion"],
                                    "maxVersion": config["maxVersion"]
                                }]
                            })
                        
                        # 2. 保存 operators.json
                        ops_path = os.path.join(CURRENT_DIR, 'operators.json')
                        with open(ops_path, 'w') as f:
                            json.dump(operators_list, f, indent=2)
                        
                        # 3. 合併 CSI 配置
                        cluster_mgr = ConfigManager('cluster_config.json')
                        full_config = cluster_mgr.get_config()
                        full_config['csi_info'] = st.session_state.csi_config
                        full_config['operators'] = operators_list
                        
                        # 4. 生成 imageset-config.yaml
                        try:
                            from yaml_generator import YAMLGenerator
                            generator = YAMLGenerator(full_config, CURRENT_DIR)
                            yaml_content = generator.generate_imageset_config()
                            
                            output_path = os.path.join(CURRENT_DIR, "install/ocp", "imageset-config.yaml")
                            os.makedirs(os.path.dirname(output_path), exist_ok=True)
                            
                            with open(output_path, 'w') as f:
                                f.write(yaml_content)
                            
                            st.session_state.operators_saved = True
                            st.success(f"✅ Configuration saved! Files generated:")
                            st.info(f"📄 `operators.json`\n📄 `imageset-config.yaml`")
                            
                            with st.expander("Preview imageset-config.yaml"):
                                st.code(yaml_content, language="yaml")
                                
                        except Exception as e:
                            st.error(f"❌ Error generating imageset: {str(e)}")
                    else:
                        st.warning("⚠️ Please configure at least one operator")

    # 下一步按鈕
    if os.path.exists(os.path.join(CURRENT_DIR, 'operators.json')):
        st.divider()
        if st.button("➡️ Next: Final Review", use_container_width=True, type="primary"):
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