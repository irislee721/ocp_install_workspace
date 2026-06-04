#!/usr/bin/env python3
import streamlit as st
import time
import os
from setup_manager import SetupManager


def render_step4_mirror():
    """步驟4: 鏡像同步"""
    st.header("🪞 步驟4: Mirror Registry 與鏡像同步")
    
    config_params = st.session_state.get('config_params', {})
    file_paths = st.session_state.get('file_paths', {})
    
    # === Registry 連線狀態檢查 ===
    st.subheader("🔗 Registry 連線狀態")
    
    manager = SetupManager(config_params)
    
    # 檢查 Registry 是否已安裝
    installed, install_msg = manager.mirror_registry_manager.check_installed()
    
    if installed:
        st.success(f"✅ {install_msg}")
        
        # 嘗試驗證連線
        with st.spinner("正在驗證 Registry 連線..."):
            connected, connect_msg = manager.mirror_registry_manager.verify_connection()
            if connected:
                st.success(f"✅ {connect_msg}")
            else:
                st.warning(f"⚠️ {connect_msg}")
                st.info("請確認 Mirror Registry 已正確安裝並運行。")
    else:
        st.warning(f"⚠️ {install_msg}")
        st.info("請返回步驟3安裝 Mirror Registry，或確認 Registry 服務正在運行。")
        
        col_back, _ = st.columns([1, 3])
        with col_back:
            if st.button("⬅️ 返回步驟3", type="primary"):
                st.session_state.current_step = 3
                st.rerun()
        return
    
    st.markdown("---")
    
    # === 鏡像同步配置 ===
    st.subheader("🪞 鏡像同步配置")
    
    col_mir1, col_mir2 = st.columns(2)
    
    with col_mir1:
        ocmirror_source = st.text_input(
            "OC Mirror 安裝包路徑",
            value=file_paths.get('ocmirrorSource', '/root/oc-mirror.tar.gz'),
            help="oc-mirror 工具的 tar.gz 檔案路徑"
        )
        image_set_file = st.text_input(
            "ImageSet 配置目錄",
            value=file_paths.get('imageSetFile', '/root/oc-mirror-workspace'),
            help="包含 imageset-config.yaml 的目錄路徑"
        )
    
    with col_mir2:
        reponame = st.text_input(
            "目標倉庫名稱",
            value=file_paths.get('reponame', 'ocp420'),
            help="在 Mirror Registry 中的 repository 名稱"
        )
        
        # 顯示倉庫 URL 預覽
        bastion_name = config_params.get('bastion', {}).get('name', 'bastion')
        cluster_name = config_params.get('clusterName', 'ocp4')
        base_domain = config_params.get('baseDomain', 'example.com')
        bastion_fqdn = f"{bastion_name}.{cluster_name}.{base_domain}"
        
        st.info(f"目標 Registry: `{bastion_fqdn}:8443/{reponame}`")
    
    st.markdown("---")
    
    # === 任務定義 ===
    st.subheader("📋 本步驟將執行的操作")
    
    active_tasks = [
        {
            'icon': '🔧',
            'name': '安裝 oc-mirror 工具',
            'detail': '從安裝包解壓並設定執行權限',
            'method': 'install_oc_mirror',
        },
        {
            'icon': '🔑',
            'name': '登入 Mirror Registry',
            'detail': '使用 podman login 驗證',
            'method': 'login_registry',
        },
        {
            'icon': '🪞',
            'name': '執行鏡像同步',
            'detail': f'同步至 {bastion_fqdn}:8443/{reponame}',
            'method': 'mirror_images',
        }
    ]
    
    for task in active_tasks:
        st.markdown(f"{task['icon']} **{task['name']}** - {task['detail']}")
    
    # 檢查必要檔案
    st.markdown("---")
    _check_mirror_files(ocmirror_source, image_set_file)
    
    st.markdown("---")
    
    # === 步驟執行狀態追蹤 ===
    if 'step4_executed' not in st.session_state:
        st.session_state.step4_executed = False
        st.session_state.step4_results = {}
    
    # === 執行按鈕 ===
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
    
    with col_btn1:
        if not st.session_state.step4_executed:
            if st.button("🚀 開始鏡像同步", type="primary"):
                # 更新配置到 session state
                _update_mirror_config(ocmirror_source, image_set_file, reponame)
                
                # 使用更新後的 config_params 重新初始化 manager
                manager = SetupManager(st.session_state.config_params)
                _execute_step4_tasks(manager, active_tasks)
                st.rerun()
    
    # === 顯示執行結果 ===
    if st.session_state.step4_executed:
        st.markdown("---")
        st.subheader("📊 執行結果")
        
        results = st.session_state.step4_results
        success_count = sum(1 for r in results.values() if r.get('success', False))
        total_count = len(results)
        
        # 顯示進度摘要
        col_prog1, col_prog2 = st.columns([1, 3])
        with col_prog1:
            st.metric("完成進度", f"{success_count}/{total_count}")
        
        all_success = success_count == total_count
        
        # 顯示每個步驟的詳細結果
        for method, result in results.items():
            task_name = method
            for task in active_tasks:
                if task['method'] == method:
                    task_name = f"{task['icon']} {task['name']}"
                    break
            
            if result.get('success', False):
                st.success(f"{task_name}: {result.get('message', '')}")
            else:
                st.error(f"{task_name}: {result.get('message', '')}")
        
        if all_success:
            st.success("🎉 鏡像同步完成！")
            st.balloons()
            
            # 顯示同步後檢查（需要重新初始化 manager）
            manager = SetupManager(st.session_state.config_params)
            _display_mirror_status(manager)
        else:
            st.warning("⚠️ 部分步驟失敗，請檢查上方錯誤訊息。")
    
    # === 導航按鈕 ===
    st.markdown("---")
    col_nav1, col_nav2, col_nav3 = st.columns([1, 1, 2])
    
    with col_nav1:
        if st.button("⬅️ 返回步驟3", use_container_width=True):
            st.session_state.current_step = 3
            st.rerun()
    
    with col_nav2:
        if st.session_state.step4_executed:
            if st.button("🏁 完成安裝", type="primary", use_container_width=True):
                st.session_state.step4_complete = True
                st.session_state.current_step = 5
                st.rerun()
    
    # === 重試按鈕 ===
    if st.session_state.step4_executed:
        results = st.session_state.step4_results
        has_failures = any(not r.get('success', False) for r in results.values())
        
        if has_failures:
            with col_nav3:
                if st.button("🔄 重新執行所有步驟", use_container_width=True):
                    st.session_state.step4_executed = False
                    st.session_state.step4_results = {}
                    st.rerun()


def _check_mirror_files(ocmirror_source: str, image_set_file: str):
    """檢查鏡像同步相關檔案"""
    st.subheader("🔍 檔案檢查")
    
    # 檢查 oc-mirror 安裝包
    if os.path.exists(ocmirror_source):
        size_bytes = os.path.getsize(ocmirror_source)
        size_str = f"{size_bytes / (1024*1024):.1f} MB" if size_bytes > 1024*1024 else f"{size_bytes / 1024:.1f} KB"
        st.success(f"✅ oc-mirror 安裝包: {ocmirror_source} ({size_str})")
    else:
        st.warning(f"⚠️ oc-mirror 安裝包: {ocmirror_source} - 檔案不存在")
    
    # 檢查 ImageSet 配置目錄
    if os.path.exists(image_set_file):
        config_yaml = os.path.join(image_set_file, 'imageset-config.yaml')
        if os.path.exists(config_yaml):
            st.success(f"✅ ImageSet 配置: {config_yaml}")
        else:
            st.warning(f"⚠️ ImageSet 目錄存在但缺少 imageset-config.yaml: {image_set_file}")
    else:
        st.warning(f"⚠️ ImageSet 目錄不存在: {image_set_file}")


def _update_mirror_config(ocmirror_source: str, image_set_file: str, reponame: str):
    """更新鏡像同步配置到 session state"""
    new_config = {
        'ocmirrorSource': ocmirror_source,
        'imageSetFile': image_set_file,
        'reponame': reponame,
    }
    st.session_state.file_paths.update(new_config)
    st.session_state.config_params.update(new_config)


def _execute_step4_tasks(manager: SetupManager, active_tasks: list):
    """執行步驟4的所有任務"""
    st.session_state.step4_executed = True
    st.session_state.step4_results = {}
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total = len(active_tasks)
    
    for i, task in enumerate(active_tasks):
        task_name = f"{task['icon']} {task['name']}"
        method = task['method']
        
        status_text.text(f"正在執行: {task_name}...")
        
        with st.expander(f"{task_name} - {task['detail']}", expanded=True):
            st.info(f"⏳ 執行中...（可能需要較長時間）")
            
            # 對於鏡像同步，使用較長的等待提示
            if method == 'mirror_images':
                st.info("💡 鏡像同步可能需要 10-60 分鐘，請耐心等待...")
            
            # 執行步驟
            success, message = manager.execute_step(method)
            
            if success:
                st.success(f"✅ {message}")
            else:
                st.error(f"❌ {message}")
                
                # 提供重試和跳過選項
                col_r, col_s = st.columns(2)
                with col_r:
                    if st.button("🔄 重試此步驟", key=f"retry_{method}"):
                        retry_success, retry_message = manager.execute_step(method)
                        if retry_success:
                            st.success(f"✅ {retry_message}")
                            success = True
                            message = retry_message
                        else:
                            st.error(f"❌ 重試仍失敗: {retry_message}")
                        st.rerun()
                with col_s:
                    if st.button("⏭️ 跳過此步驟", key=f"skip_{method}"):
                        st.warning(f"⏭️ 已跳過: {task_name}")
                        st.session_state.step4_results[method] = {
                            'success': False,
                            'message': f'已跳過: {message}',
                            'skipped': True
                        }
                        continue
            
            # 記錄結果
            st.session_state.step4_results[method] = {
                'success': success,
                'message': message
            }
        
        progress_bar.progress((i + 1) / total)
        time.sleep(0.3)
    
    status_text.text("✅ 鏡像同步程序完成！")


def _display_mirror_status(manager: SetupManager):
    """顯示鏡像同步後的狀態檢查"""
    st.markdown("---")
    st.subheader("🔍 鏡像倉庫狀態檢查")
    
    with st.spinner("正在檢查鏡像倉庫狀態..."):
        success, msg = manager.mirror_image_manager.check_mirror_status()
        if success:
            st.success(f"✅ {msg}")
        else:
            st.warning(f"⚠️ {msg}")