import streamlit as st
import json
import os
from datetime import datetime
import time

from src.config_manager import ConfigManager
from src.setup_wizard import SetupWizard

CURRENT_DIR = os.getcwd()
CONFIG_DIR = os.path.join(CURRENT_DIR, 'config')
os.makedirs(CONFIG_DIR, exist_ok=True)

def show_tool_config_page():
    """渲染工具配置頁面，包含 Pull Secret、工具版本設定及 Operator Index 獲取"""    
    st.title("1. 🔧 Tool Configuration & Environment Setup")
    st.markdown("配置需要下載的工具版本，並執行環境初始化。")
    
    config_manager = ConfigManager('tool_config.json')
    config = config_manager.get_config()
    wizard = SetupWizard(CURRENT_DIR)

    _render_pull_secret(wizard)
    st.divider()
    _render_tool_config_form(config_manager, config, wizard)
    _render_fetch_operator_catalog(config, wizard)
    st.divider()
    render_next_button()

def _render_pull_secret(wizard):
    """渲染 Pull Secret 上傳與驗證區塊，支援貼上 JSON 或上傳 txt 檔案"""
    with st.expander("🔐 OpenShift Pull Secret Configuration", expanded=True):
        st.markdown("""
        請提供 OpenShift Pull Secret。從 [Red Hat Console](https://console.redhat.com/openshift/downloads#tool-pull-secret) 下載。
        """)
        
        if st.session_state.get('pull_secret_merged', False):
            st.success("✅ Pull secret 已配置完成")
            if st.button("🔄 重新上傳"):
                st.session_state.pull_secret_merged = False
                st.rerun()
            return
        
        # 上傳方式選擇
        upload_method = st.radio(
            "選擇上傳方式",
            ["📋 貼上 JSON 內容", "📁 上傳 pull-secret.txt"],
            horizontal=True
        )
        
        pull_secret_json = None
        
        if upload_method == "📋 貼上 JSON 內容":
            pull_secret_text = st.text_area(
                "Pull Secret (JSON)", height=200,
                placeholder='{"auths":{"cloud.openshift.com":{...},...}}',
                key="pull_secret_text"
            )
            if pull_secret_text:
                try:
                    pull_secret_json = json.loads(pull_secret_text)
                except json.JSONDecodeError:
                    st.error("❌ 無效的 JSON 格式")
        else:
            uploaded_file = st.file_uploader(
                "上傳 pull-secret.txt",
                type=["txt", "json"],
                key="pull_secret_file"
            )
            if uploaded_file:
                try:
                    pull_secret_json = json.loads(uploaded_file.read().decode('utf-8'))
                    st.success(f"✅ 已讀取: {uploaded_file.name}")
                except json.JSONDecodeError:
                    st.error("❌ 無效的 JSON 格式")
        
        # 驗證並套用
        if pull_secret_json:
            if 'auths' not in pull_secret_json:
                st.error("❌ 缺少 'auths' 欄位")
            else:
                registries = list(pull_secret_json['auths'].keys())
                required = ['quay.io', 'registry.redhat.io']
                missing = [r for r in required if r not in registries]
                
                st.info(f"📋 包含 {len(registries)} 個 registry 認證")
                if missing:
                    st.error(f"❌ 缺少必要認證：{', '.join(missing)}")
                else:
                    st.success("✅ 包含 quay.io 和 registry.redhat.io 認證")
                    
                    if st.button("🔗 套用 Pull Secret", type="primary"):
                        if wizard.apply_pull_secret(pull_secret_json):
                            st.session_state.pull_secret_merged = True
                            st.session_state.registry_logged_in = True
                            st.rerun()
                        else:
                            st.error("❌ 寫入失敗")

def _render_tool_config_form(config_manager, config, wizard):
    """渲染工具版本配置表單，提交後依序執行 env_prep、get_tools、解壓"""
    with st.form("tool_config_form"):
        st.subheader("Version Information")
        col1, col2 = st.columns(2)
        with col1:
            config['version_info']['OCP_RELEASE'] = st.text_input("OCP Release (e.g. 4.20.8)", value=config['version_info']['OCP_RELEASE'])
            config['version_info']['RHEL_VERSION'] = st.selectbox("RHEL Version", ["rhel9", "rhel10"], index=0 if config['version_info']['RHEL_VERSION'] == 'rhel9' else 1)
        with col2:
            config['version_info']['ARCHITECTURE'] = st.selectbox("Architecture", ["amd64", "arm64"], index=0 if config['version_info']['ARCHITECTURE'] == 'amd64' else 1)
            config['version_info']['HELM_VERSION'] = st.text_input("Helm Version", value=config['version_info']['HELM_VERSION'])
            config['version_info']['MIRROR_REGISTRY_VERSION'] = st.text_input("Mirror Registry Version", value=config['version_info']['MIRROR_REGISTRY_VERSION'])

        if st.form_submit_button("Save & Run Environment Setup"):
            config_manager.save_config(config)
            st.success("配置已保存！開始執行環境初始化...")
            
            with st.expander("Step 1: Environment Preparation", expanded=True):
                if wizard.run_env_prep():
                    st.session_state.env_ready = True
                    st.success("✅ env_prep 完成")
                else:
                    st.error("❌ env_prep 失敗")
                    st.stop()

            with st.expander("Step 2: Download Tools", expanded=True):
                if st.session_state.env_ready:
                    progress_bar = st.progress(0)
                    if wizard.run_get_tools(config, progress_callback=lambda p: progress_bar.progress(p)):
                        st.session_state.tools_downloaded = True
                        st.success("✅ get_tools 完成")
                    else:
                        st.error("❌ get_tools 失敗")
                        st.stop()
            
            with st.expander("Step 3: Extract binary", expanded=True):
                if st.session_state.tools_downloaded:
                    if wizard.run_untar_oc_mirror(config):
                        st.success("✅ untar_oc_mirror 完成")
                    else:
                        st.error("❌ untar_oc_mirror 失敗")
                    if wizard.run_untar_grpcurl(config):
                        st.success("✅ untar_grpcurl 完成")
                    else:
                        st.error("❌ untar_grpcurl 失敗")
            
            st.success("✅ tool_config 配置完成！")

def _render_fetch_operator_catalog(config, wizard):
    """渲染 Operator Index 獲取區塊，檢查 grpcurl 後顯示現有索引"""
    grpcurl_binary = os.path.join(os.path.expanduser("~"), ".local/bin/grpcurl")
    if not os.path.exists(grpcurl_binary):
        grpcurl_binary = os.path.join(CURRENT_DIR, "usr/bin/grpcurl")

    if not (st.session_state.get('tools_downloaded', False) and os.path.exists(grpcurl_binary)):
        if st.session_state.get('tools_downloaded', False):
            st.warning("⚠️ grpcurl 未找到")
        return

    with st.expander("Step 4: Fetch Operator Index", expanded=True):
        index_file = os.path.join(CONFIG_DIR, "operator_index.json")
        
        if os.path.exists(index_file):
            _render_existing_index(index_file, config, wizard)
        else:
            _render_fetch_new_index(config, wizard)

def _render_existing_index(index_file, config, wizard):
    """顯示已存在的 Operator Index 及其資訊，提供刷新按鈕"""
    try:
        with open(index_file, 'r') as f:
            index_data = json.load(f)
        
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.success(f"✅ Operator Index 就緒 ({len(index_data)} packages)")
        with col2:
            mtime = os.path.getmtime(index_file)
            st.caption(f"🕐 {datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        with col3:
            if st.button("🔄 刷新", key="refresh_grpc_btn", use_container_width=True):
                _run_fetch_with_progress(config, wizard, "🔄 正在刷新 Operator Index...")
    except Exception as e:
        st.error(f"讀取快取失敗: {e}")

def _render_fetch_new_index(config, wizard):
    """渲染首次獲取 Operator Index 的說明與觸發按鈕"""
    st.info("📡 尚未獲取 Operator Index")
    st.markdown("""
    ### 🔄 獲取流程：
    1. 📦 啟動 Local Registry 容器
    2. 📡 透過 gRPC 查詢
    3. 💾 儲存為 operator_index.json
    4. 🧹 自動清除容器
    ⏱️ 首次獲取約需 **2-5 分鐘**
    """)
    
    if st.button("🚀 開始獲取 Operator Index (gRPC)", type="primary", use_container_width=True):
        _run_fetch_with_progress(config, wizard, "📡 正在獲取 Operator Index...")

def _run_fetch_with_progress(config, wizard, title):
    """執行 Operator Index 獲取並顯示進度條與即時日誌"""
    with st.status(title, expanded=True) as status_container:
        progress_bar = st.progress(0, "準備開始...")
        status_text = st.empty()
        log_container = st.container()
        
        def update_status(msg):
            with log_container:
                st.write(f"➤ {msg}")
            _update_progress(msg, progress_bar, status_text)
        
        if wizard.run_get_operator_catalog_via_grpc(config, status_callback=update_status):
            progress_bar.progress(100, "完成!")
            status_text.success("🎉 Operator Index 獲取完成!")
            status_container.update(label="✅ 完成!", state="complete", expanded=False)
            st.balloons()
            time.sleep(1)
            st.rerun()
        else:
            progress_bar.empty()
            status_text.empty()
            status_container.update(label="❌ 失敗", state="error", expanded=True)
            st.error("❌ Operator Index 獲取失敗")

def _update_progress(msg, progress_bar, status_text):
    """根據後端回傳的狀態訊息更新前端的進度條與狀態文字"""
    if "初始化" in msg:
        progress_bar.progress(5, "初始化任務...")
    elif "grpcurl" in msg and "找到" in msg:
        progress_bar.progress(10, "工具就緒")
    elif "檢查鏡像" in msg:
        progress_bar.progress(15, "檢查鏡像...")
    elif "鏡像已存在" in msg:
        progress_bar.progress(20, "鏡像就緒")
    elif "鏡像不存在" in msg or "開始拉取" in msg:
        progress_bar.progress(20, "拉取鏡像...")
        status_text.info("📥 鏡像不存在，正在拉取... (可能需要 3-10 分鐘)")
    elif "鏡像拉取完成" in msg:
        progress_bar.progress(35, "鏡像拉取完成")
    elif "啟動" in msg and "容器" in msg:
        progress_bar.progress(40, "啟動容器...")
    elif "容器已啟動" in msg:
        progress_bar.progress(45, "容器已啟動")
    elif "查詢" in msg and "Packages" in msg:
        progress_bar.progress(60, "查詢 Packages...")
    elif "找到" in msg and "packages" in msg:
        progress_bar.progress(70, "獲取詳細資訊...")
    elif "處理中" in msg:
        import re
        match = re.search(r'(\d+)/(\d+)', msg)
        if match:
            current, total = int(match.group(1)), int(match.group(2))
            pct = 70 + int((current / total) * 20)
            progress_bar.progress(pct, f"處理中... ({current}/{total})")
    elif "operator_index.json" in msg or "已創建" in msg:
        progress_bar.progress(95, "儲存中...")
    elif "容器已清除" in msg:
        progress_bar.progress(100, "完成!")
    elif "完成" in msg:
        progress_bar.progress(100, "完成!")

def render_next_button():
    """當 tools_downloaded 為 True 時渲染前往 Cluster Config 的按鈕"""
    if st.session_state.get('tools_downloaded', False):
        st.divider()
        if st.button("➡️ Next: Cluster Config", use_container_width=True):
            st.session_state.current_view = 'cluster_config'
            st.rerun()