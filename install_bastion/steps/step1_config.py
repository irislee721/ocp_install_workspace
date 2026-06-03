import streamlit as st
import time


def render_readonly_field(label: str, value: str):
    """渲染唯讀欄位"""
    st.text_input(label, value=value, disabled=True)


def render_step1_config():
    """步驟1: 確認環境配置"""
    st.header("📝 步驟1: 確認環境配置與安裝選項")
    st.markdown("以下配置來自 `config/cluster_config.json`，僅供確認，不可修改。")
    
    config = st.session_state.get('config_params', {})
    
    # === 基本環境資訊（唯讀） ===
    st.subheader("🏗️ 基本環境資訊")
    
    col1, col2 = st.columns(2)
    
    with col1:
        render_readonly_field("叢集名稱 (clusterName)", config.get('clusterName', 'N/A'))
        render_readonly_field("基礎網域 (baseDomain)", config.get('baseDomain', 'N/A'))
        render_readonly_field("網路介面 (interface)", config.get('interface', 'N/A'))
        
    with col2:
        render_readonly_field("堡壘主機 IP", config.get('bastion', {}).get('ip', 'N/A'))
        render_readonly_field("部署模式", config.get('mode', 'N/A'))
        render_readonly_field("上游 DNS", config.get('dns_upstream', 'N/A'))
    
    # === 版本資訊（唯讀） ===
    version_info = config.get('versionInfo', {})
    if version_info:
        st.subheader("📦 版本資訊")
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            render_readonly_field("OCP Version", version_info.get('ocpVersion', 'N/A'))
        with col_v2:
            render_readonly_field("OCP Release", version_info.get('ocpRelease', 'N/A'))
    
    # === 節點配置（唯讀） ===
    st.subheader("🖥️ 節點配置")
    
    # Master 節點
    master_nodes = config.get('master', [])
    if master_nodes:
        st.markdown("**Master 節點**")
        for node in master_nodes:
            cols = st.columns(4)
            with cols[0]:
                render_readonly_field(f"名稱", node.get('name', 'N/A'))
            with cols[1]:
                render_readonly_field(f"IP", node.get('ip', 'N/A'))
            with cols[2]:
                render_readonly_field(f"MAC", node.get('mac', 'N/A'))
            with cols[3]:
                render_readonly_field(f"裝置", node.get('device', 'N/A'))
    
    # Bootstrap 節點
    bootstrap = config.get('bootstrap', {})
    st.markdown("**Bootstrap 節點**")
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        render_readonly_field("Bootstrap 名稱", bootstrap.get('name', 'N/A'))
    with col_b2:
        render_readonly_field("Bootstrap IP", bootstrap.get('ip', 'N/A'))
    
    # Worker 節點
    worker_nodes = config.get('worker', [])
    if worker_nodes:
        st.markdown("**Worker 節點**")
        for node in worker_nodes:
            cols = st.columns(4)
            with cols[0]:
                render_readonly_field(f"名稱", node.get('name', 'N/A'))
            with cols[1]:
                render_readonly_field(f"IP", node.get('ip', 'N/A'))
            with cols[2]:
                render_readonly_field(f"MAC", node.get('mac', 'N/A'))
            with cols[3]:
                render_readonly_field(f"裝置", node.get('device', 'N/A'))
    
    # Infra 節點
    infra_nodes = config.get('infra', [])
    if infra_nodes:
        st.markdown("**Infra 節點**")
        for node in infra_nodes:
            cols = st.columns(4)
            with cols[0]:
                render_readonly_field(f"名稱", node.get('name', 'N/A'))
            with cols[1]:
                render_readonly_field(f"IP", node.get('ip', 'N/A'))
            with cols[2]:
                render_readonly_field(f"MAC", node.get('mac', 'N/A'))
            with cols[3]:
                render_readonly_field(f"裝置", node.get('device', 'N/A'))
    
    # === 網路配置（唯讀） ===
    net_config = config.get('networkConfig', {})
    if net_config:
        st.subheader("🌐 網路配置")
        col_n1, col_n2 = st.columns(2)
        with col_n1:
            if 'machineNetworkCidr' in net_config:
                render_readonly_field("Machine Network CIDR", net_config['machineNetworkCidr'])
            if 'clusterNetworkCidr' in net_config:
                render_readonly_field("Cluster Network CIDR", net_config['clusterNetworkCidr'])
            if 'serviceNetworkCidr' in net_config:
                render_readonly_field("Service Network CIDR", net_config['serviceNetworkCidr'])
        with col_n2:
            if 'networkType' in net_config:
                render_readonly_field("Network Type", net_config['networkType'])
            if 'clusterNetworkHostPrefix' in net_config:
                render_readonly_field("Host Prefix", str(net_config['clusterNetworkHostPrefix']))
            if 'gatewayIp' in net_config:
                render_readonly_field("Gateway IP", net_config['gatewayIp'])
    
    st.markdown("---")
    
    # === 安裝選項（可修改的勾選） ===
    st.subheader("⚙️ 預計安裝的工具")
    
    install_options = st.session_state.get('install_options', {})
    
    col_opt1, col_opt2, col_opt3 = st.columns(3)
    
    with col_opt1:
        firewalld_disable = st.checkbox(
            "停用防火牆", 
            value=install_options.get('firewalld_disable', True),
            key="opt_firewalld"
        )
        selinux_disable = st.checkbox(
            "停用 SELinux", 
            value=install_options.get('selinux_disable', True),
            key="opt_selinux"
        )
        dns_configure = st.checkbox(
            "設定 DNS", 
            value=install_options.get('dns_configure', True),
            key="opt_dns"
        )
        
    with col_opt2:
        dns_check = st.checkbox(
            "檢查 DNS", 
            value=install_options.get('dns_check', True),
            key="opt_dns_check"
        )
        haproxy_configure = st.checkbox(
            "設定 HAProxy", 
            value=install_options.get('haproxy_configure', True),
            key="opt_haproxy"
        )
        ntp_server_configure = st.checkbox(
            "設定 NTP 伺服器", 
            value=install_options.get('ntp_server_configure', True),
            key="opt_ntp"
        )
        
    with col_opt3:
        registry_configure = st.checkbox(
            "設定鏡像倉庫", 
            value=install_options.get('registry_configure', True),
            key="opt_registry"
        )
        mirror_enable = st.checkbox(
            "啟用鏡像同步", 
            value=install_options.get('mirror_enable', False),
            key="opt_mirror"
        )
    
    st.markdown("---")
    
    # === 確認按鈕 ===
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
    
    with col_btn1:
        if st.button("✅ 確認配置，進入下一步", type="primary"):
            # 保存安裝選項
            st.session_state.install_options = {
                'firewalld_disable': firewalld_disable,
                'selinux_disable': selinux_disable,
                'dns_configure': dns_configure,
                'dns_check': dns_check,
                'haproxy_configure': haproxy_configure,
                'ntp_server_configure': ntp_server_configure,
                'registry_configure': registry_configure,
                'mirror_enable': mirror_enable,
            }
            
            # 合併到 config_params
            st.session_state.config_params.update(st.session_state.install_options)
            
            st.session_state.step1_complete = True
            st.session_state.current_step = 2
            st.success("配置已確認！進入步驟2...")
            time.sleep(1)
            st.rerun()
    
    with col_btn2:
        if st.button("🔄 重設選項"):
            st.session_state.install_options = {
                'firewalld_disable': True,
                'selinux_disable': True,
                'dns_configure': True,
                'dns_check': True,
                'haproxy_configure': True,
                'ntp_server_configure': True,
                'registry_configure': True,
                'mirror_enable': False,
            }
            st.rerun()