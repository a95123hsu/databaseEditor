import streamlit as st
import json
from pathlib import Path

# --- Language Management Functions ---
def load_translations():
    """
    Load translation dictionaries from JSON files.
    Creates default files if they don't exist.
    
    Returns:
        dict: Dictionary with language codes as keys and translation dictionaries as values
    """
    translations_dir = Path("translations")
    translations_dir.mkdir(exist_ok=True)
    
    # Default translations
    default_translations = {
        "en": {
            "app_title": "Pump Selection Data Manager",
            "app_description": "View, add, edit, and delete pump selection data",
            "current_time": "Current time (Taiwan)",
            "actions": "Actions",
            "choose_action": "Choose an action:",
            "view_data": "View Data",
            "add_new_pump": "Add New Pump",
            "edit_pump": "Edit Pump",
            "delete_pump": "Delete Pump",
            "bulk_delete": "Bulk Delete",
            "filters": "Filters",
            "filter_by_model_group": "Filter by Model Group",
            "filter_by_category": "Filter by Category",
            "refresh_data": "Refresh Data",
            "logout": "Logout",
            "search_by_model": "Search by Model No.",
            "no_data_found": "No data found in 'pump_selection_data'.",
            "loaded_records": "Successfully loaded {} pump records",
            "no_match": "No pumps match your filter criteria.",
            "pump_data_table": "Pump Data Table",
            "sort_by": "Sort by:",
            "sort_order": "Sort order:",
            "ascending": "Ascending",
            "descending": "Descending",
            "rows_per_page": "Rows per page:",
            "showing_rows": "Showing {}-{} of {} rows",
            "model_group_summary": "Model Group Summary",
            "model_group": "Model Group",
            "count": "Count",
            "required_field": "Required field",
            "predicted_model_group": "Predicted Model Group: {}",
            "add_pump_button": "Add Pump",
            "model_no_required": "Model No. is required.",
            "pump_data_added": "Pump data added successfully with DB ID: {}!",
            "error_adding_pump": "Error adding pump data: {}",
            "update_pump_button": "Update Pump",
            "pump_data_updated": "Pump data updated successfully!",
            "error_updating_pump": "Error updating pump data: {}",
            "delete_confirmation": "Warning: This action cannot be undone!",
            "confirm_delete": "Confirm Delete",
            "pump_data_deleted": "Pump data deleted successfully!",
            "error_deleting_pump": "Error deleting pump data: {}",
            "bulk_delete_title": "Bulk Delete Pumps",
            "current_filter_showing": "Current filter showing {} records",
            "select_records_to_delete": "Select Records to Delete",
            "select_deletion_method": "Select deletion method:",
            "by_category": "By Category",
            "by_model_group": "By Model Group",
            "manual_selection": "Manual Selection",
            "no_categories_found": "No categories found in the filtered data.",
            "select_category_to_delete": "Select category to delete:",
            "about_to_delete_category": "You are about to delete {} pumps in category '{}'",
            "preview_records": "Preview of records to be deleted ({} of {})",
            "no_model_groups_found": "No model groups found in the filtered data.",
            "select_model_group_to_delete": "Select model group to delete:",
            "about_to_delete_group": "You are about to delete {} pumps in model group '{}'",
            "select_pumps_to_delete": "Select pumps to delete:",
            "too_many_records": "Too many records ({}) for manual selection. Please use filters or search to narrow down the results.",
            "no_pumps_match": "No pumps match your search criteria.",
            "reason_for_deletion": "Reason for deletion (optional)",
            "deletion_warning": "Warning: You are about to delete {} pump records! This action cannot be undone!",
            "confirm_bulk_delete": "Confirm Bulk Delete",
            "deleted_with_errors": "Deleted {} records successfully with {} errors.",
            "please_select_records": "Please select records to delete using one of the methods above.",
            "change_description": "Change Description (optional)",
            "change_description_placeholder": "Why are you adding this pump?",
            "edit_change_description_placeholder": "Describe why you're updating this pump...",
            "delete_reason_placeholder": "Why are you deleting this pump?",
            "bulk_delete_reason_placeholder": "Why are you deleting these pumps?",
            "live_database_activity": "Live Database Activity",
            "no_recent_activity": "No recent database activity. Changes will appear here in real-time.",
            "realtime_updates": "Realtime Updates",
            "enable_auto_refresh": "Enable auto-refresh",
            "refresh_interval": "Refresh interval (seconds)",
            "manual_refresh": "Manual Refresh",
            "last_checked": "Last checked for updates: {}",
            "by": "By",
            "pump_details": "Pump Details",
            "select_pump_edit": "Select pump to edit (by {}):",
            "select_pump_delete": "Select pump to delete (by {}):",
            "current_model_group": "Current Model Group: {}",
            "new_model_group": "New Model Group: {}",
            "could_not_generate_db_id": "Could not generate a new DB ID. Please check database permissions.",
            "fetching_data": "Fetching data...",
            "loading_records": "Loading records {}-{}...",
            "all_option": "All",
            "page": "Page",
            "no_data_to_display": "No data to display",
            "matching": "matching",
            "records": "records",
            "found": "Found",
            "matching_pumps": "matching pumps",
            "model_no": "Model No.",
            "category": "Category",
            "power": "Power",
            "max_flow": "Max Flow",
            "max_head": "Max Head",
            "outlet": "Outlet",
            "frequency": "Frequency",
            "deleting_records": "Deleting records...",
            "deleted_all_successfully": "Successfully deleted all {} records!",
            "last_updated": "Last updated"
        },
        "zh_TW": {
            "app_title": "幫浦選型資料管理器",
            "app_description": "查看、新增、編輯和刪除幫浦選型資料",
            "current_time": "目前時間（台灣）",
            "actions": "操作",
            "choose_action": "選擇操作：",
            "view_data": "查看資料",
            "add_new_pump": "新增幫浦",
            "edit_pump": "編輯幫浦",
            "delete_pump": "刪除幫浦",
            "bulk_delete": "批量刪除",
            "filters": "篩選器",
            "filter_by_model_group": "按型號組篩選",
            "filter_by_category": "按類別篩選",
            "refresh_data": "重新整理資料",
            "logout": "登出",
            "search_by_model": "按型號搜尋",
            "no_data_found": "'pump_selection_data' 中未找到資料。",
            "loaded_records": "成功載入 {} 個幫浦記錄",
            "no_match": "沒有幫浦符合您的篩選條件。",
            "pump_data_table": "幫浦資料表",
            "sort_by": "排序依據：",
            "sort_order": "排序順序：",
            "ascending": "升序",
            "descending": "降序",
            "rows_per_page": "每頁行數：",
            "showing_rows": "顯示 {}-{} 共 {} 行",
            "model_group_summary": "型號組摘要",
            "model_group": "型號組",
            "count": "數量",
            "required_field": "必填欄位",
            "predicted_model_group": "預測型號組：{}",
            "add_pump_button": "新增幫浦",
            "model_no_required": "型號為必填項。",
            "pump_data_added": "幫浦資料成功新增，DB ID：{}！",
            "error_adding_pump": "新增幫浦資料時出錯：{}",
            "update_pump_button": "更新幫浦",
            "pump_data_updated": "幫浦資料更新成功！",
            "error_updating_pump": "更新幫浦資料時出錯：{}",
            "delete_confirmation": "警告：此操作無法撤銷！",
            "confirm_delete": "確認刪除",
            "pump_data_deleted": "幫浦資料已成功刪除！",
            "error_deleting_pump": "刪除幫浦資料時出錯：{}",
            "bulk_delete_title": "批量刪除幫浦",
            "current_filter_showing": "當前篩選顯示 {} 條記錄",
            "select_records_to_delete": "選擇要刪除的記錄",
            "select_deletion_method": "選擇刪除方法：",
            "by_category": "按類別",
            "by_model_group": "按型號組",
            "manual_selection": "手動選擇",
            "no_categories_found": "在篩選的資料中未找到類別。",
            "select_category_to_delete": "選擇要刪除的類別：",
            "about_to_delete_category": "您即將刪除類別 '{}' 中的 {} 個幫浦",
            "preview_records": "預覽將要刪除的記錄（{} / {}）",
            "no_model_groups_found": "在篩選的資料中未找到型號組。",
            "select_model_group_to_delete": "選擇要刪除的型號組：",
            "about_to_delete_group": "您即將刪除型號組 '{}' 中的 {} 個幫浦",
            "select_pumps_to_delete": "選擇要刪除的幫浦：",
            "too_many_records": "記錄太多（{}）無法手動選擇。請使用篩選器或搜尋縮小結果範圍。",
            "no_pumps_match": "沒有幫浦符合您的搜尋條件。",
            "reason_for_deletion": "刪除原因（選填）",
            "deletion_warning": "警告：您即將刪除 {} 個幫浦記錄！此操作無法撤銷！",
            "confirm_bulk_delete": "確認批量刪除",
            "deleted_with_errors": "成功刪除 {} 條記錄，有 {} 個錯誤。",
            "please_select_records": "請使用上述方法之一選擇要刪除的記錄。",
            "change_description": "變更描述（選填）",
            "change_description_placeholder": "為什麼要新增此幫浦？",
            "edit_change_description_placeholder": "描述為什麼要更新此幫浦...",
            "delete_reason_placeholder": "為什麼要刪除此幫浦？",
            "bulk_delete_reason_placeholder": "為什麼要刪除這些幫浦？",
            "live_database_activity": "即時資料庫活動",
            "no_recent_activity": "最近沒有資料庫活動。變更將會即時顯示在此處。",
            "realtime_updates": "即時更新",
            "enable_auto_refresh": "啟用自動重新整理",
            "refresh_interval": "重新整理間隔（秒）",
            "manual_refresh": "手動重新整理",
            "last_checked": "上次檢查更新時間：{}",
            "by": "操作者",
            "pump_details": "幫浦詳情",
            "select_pump_edit": "選擇要編輯的幫浦（按{}）：",
            "select_pump_delete": "選擇要刪除的幫浦（按{}）：",
            "current_model_group": "當前型號組：{}",
            "new_model_group": "新型號組：{}",
            "could_not_generate_db_id": "無法生成新的 DB ID。請檢查資料庫權限。",
            "fetching_data": "獲取資料中...",
            "loading_records": "載入記錄 {}-{}...",
            "all_option": "全部",
            "page": "頁面",
            "no_data_to_display": "沒有資料可顯示",
            "matching": "符合",
            "records": "記錄",
            "found": "找到",
            "matching_pumps": "個符合的幫浦",
            "model_no": "型號",
            "category": "類別",
            "power": "功率",
            "max_flow": "最大流量",
            "max_head": "最大揚程",
            "outlet": "出口",
            "frequency": "頻率",
            "deleting_records": "刪除記錄中...",
            "deleted_all_successfully": "成功刪除所有 {} 條記錄！",
            "last_updated": "最後更新"
        }
    }
    
    translations = {}
    
    # Try to load existing translation files or create them with defaults
    for lang_code, default_dict in default_translations.items():
        lang_file = translations_dir / f"{lang_code}.json"
        
        if not lang_file.exists():
            # Create the file with default translations
            with open(lang_file, 'w', encoding='utf-8') as f:
                json.dump(default_dict, f, ensure_ascii=False, indent=2)
            translations[lang_code] = default_dict
        else:
            # Load existing translations
            try:
                with open(lang_file, 'r', encoding='utf-8') as f:
                    translations[lang_code] = json.load(f)
            except json.JSONDecodeError:
                # If file is corrupted, use defaults
                translations[lang_code] = default_dict
    
    return translations

def get_text(key, *args, **format_args):
    """
    Get translated text for the given key in the selected language.
    Falls back to English if translation is not available.
    
    Args:
        key (str): The translation key
        *args: Positional arguments for string formatting
        **format_args: Keyword arguments for string formatting
        
    Returns:
        str: Translated text
    """
    # Get the currently active language
    lang = st.session_state.get('language', 'en')
    
    # Get translations dict from session state
    translations = st.session_state.get('translations', {})
    
    # Try to get the translation in the selected language
    if lang in translations and key in translations[lang]:
        text = translations[lang][key]
    # Fall back to English
    elif 'en' in translations and key in translations['en']:
        text = translations['en'][key]
    # Last resort: return the key itself
    else:
        return key
    
    # Apply string formatting if args or format_args are provided
    if args:
        try:
            return text.format(*args)
        except (IndexError, ValueError):
            return text
    elif format_args:
        try:
            return text.format(**format_args)
        except (KeyError, ValueError):
            return text
    return text

def setup_language_selector():
    """
    Set up language selector in the sidebar
    
    Returns:
        str: Selected language code
    """
    # Make sure translations are loaded
    if 'translations' not in st.session_state:
        st.session_state.translations = load_translations()
    
    # Get available languages
    available_languages = {
        'en': 'English',
        'zh_TW': '繁體中文'
    }
    
    # Initialize language selection if not set
    if 'language' not in st.session_state:
        st.session_state.language = 'en'
    
    # Add the language selector to sidebar
    with st.sidebar:
        # Create columns for the language selector
        lang_col1, lang_col2 = st.columns([3, 2])
        
        with lang_col1:
            st.write("🌐 Language / 語言")
        
        with lang_col2:
            # Use a selectbox for language selection
            selected_lang = st.selectbox(
                "",
                options=list(available_languages.keys()),
                format_func=lambda x: available_languages[x],
                index=list(available_languages.keys()).index(st.session_state.language),
                key="language_selector",
                label_visibility="collapsed"
            )
            
            # Update session state if language changed
            if selected_lang != st.session_state.language:
                st.session_state.language = selected_lang
                # Force app rerun to apply language change
                st.rerun()
    
    return st.session_state.language
