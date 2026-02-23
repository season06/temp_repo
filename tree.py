import json
from tree_sitter import Language, Parser
import tree_sitter_python

# 1. 初始化解析器
PY_LANGUAGE = Language(tree_sitter_python.language())
parser = Parser(PY_LANGUAGE)

# 2. 指定要分析的目標檔案路徑
target_file_path = "./main.py"

# 3. 讀取檔案內容 (以 'rb' 二進位模式讀取，直接產生 bytes)
try:
    with open(target_file_path, "rb") as f:
        source_code = f.read()
except FileNotFoundError:
    print(f"找不到檔案: {target_file_path}")
    exit(1)

# 4. 建立語法樹
tree = parser.parse(source_code)
root = tree.root_node

# --- 輔助函式：遞迴尋找區塊內所有的 Function Calls ---
def find_calls(node, calls_list):
    if node.type == 'call':
        func_node = node.child_by_field_name('function')
        if func_node:
            calls_list.append(func_node.text.decode('utf8'))
            
    for child in node.children:
        find_calls(child, calls_list)

# --- 輔助函式：解析 Function/Method 節點 ---
def parse_function(node, class_name=None):
    decorators = []
    func_node = None

    if node.type == 'decorated_definition':
        for child in node.children:
            if child.type == 'decorator':
                decorators.append(child.text.decode('utf8'))
            elif child.type == 'function_definition':
                func_node = child
    elif node.type == 'function_definition':
        func_node = node

    if not func_node:
        return None

    # 提取名稱 (如果是 Method，加上 Class 前綴)
    name_node = func_node.child_by_field_name('name')
    raw_name = name_node.text.decode('utf8') if name_node else "unknown"
    full_name = f"{class_name}.{raw_name}" if class_name else raw_name

    # 提取回傳型別與參數
    return_type_node = func_node.child_by_field_name('return_type')
    return_type = return_type_node.text.decode('utf8') if return_type_node else None

    params = []
    params_node = func_node.child_by_field_name('parameters')
    if params_node:
        for p in params_node.children:
            if p.is_named: 
                params.append(p.text.decode('utf8'))

    # 尋找依賴
    body_node = func_node.child_by_field_name('body')
    calls = []
    if body_node:
        find_calls(body_node, calls)
        
    calls = list(dict.fromkeys(calls))

    return {
        "type": "method" if class_name else "function",
        "name": full_name,
        "decorators": decorators,
        "params": params,
        "return_type": return_type,
        "dependencies": calls
    }
# ---------------------------------------------------

result = []

# 3. 遍歷根節點
for node in root.children:
    # 處理 Class
    if node.type == 'class_definition':
        class_name_node = node.child_by_field_name('name')
        class_name = class_name_node.text.decode('utf8') if class_name_node else "unknown"
        
        # 尋找 Class 內部的 Methods
        body_node = node.child_by_field_name('body')
        if body_node:
            for child in body_node.children:
                if child.type in ('function_definition', 'decorated_definition'):
                    func_info = parse_function(child, class_name)
                    if func_info:
                        result.append(func_info)

    # 處理全域 Function
    elif node.type in ('function_definition', 'decorated_definition'):
        func_info = parse_function(node)
        if func_info:
            result.append(func_info)

# 4. 匯出成 JSON 檔案
output_filename = "function_info.json"
with open(output_filename, 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=4, ensure_ascii=False)

print(f"成功解析 {target_file_path}，並將結果匯出至 {output_filename}")