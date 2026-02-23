import json
import graphviz
import os

os.environ["PATH"] += os.pathsep + r"C:\Program Files\Graphviz\bin"

input_filename = "function_info.json"

# 1. 讀取 JSON 檔案
try:
    with open(input_filename, 'r', encoding='utf-8') as f:
        functions = json.load(f)
except FileNotFoundError:
    print(f"錯誤：找不到 '{input_filename}'。")
    exit(1)

# 2. 建立主圖表
dot = graphviz.Digraph(comment='Call Graph with Classes', format='png')
dot.attr(rankdir='LR') # 從左到右排列
dot.attr('node', fontname='Consolas') 

# --- 輔助函式：產生節點的文字標籤 ---
def generate_label(func_info):
    lines = func_info.get('decorators', []).copy()
    params_str = ", ".join(func_info.get('params', []))
    return_type = func_info.get('return_type')
    return_str = f" -> {return_type}" if return_type else ""
    
    # 如果是 Method，我們在框框內只顯示簡稱 (例如 execute)，隱藏 Test. 前綴
    display_name = func_info['name'].split('.')[-1] if func_info.get('type') == 'method' else func_info['name']
    lines.append(f"def {display_name}({params_str}){return_str}")
    return "\n".join(lines)
# -----------------------------------

# 3. 將資料分組：全域函式 vs 類別方法
globals_funcs = []
class_groups = {}

for func in functions:
    if func.get('type') == 'method':
        # 從 "Test.execute" 中拆分出 "Test" 和 "execute"
        cls_name, method_name = func['name'].split('.', 1)
        if cls_name not in class_groups:
            class_groups[cls_name] = []
        class_groups[cls_name].append(func)
    else:
        globals_funcs.append(func)

# 4. 繪製全域函式 (淺藍色)
for func in globals_funcs:
    dot.node(func['name'], generate_label(func), shape='box', style='filled', fillcolor='lightblue')

# 5. 繪製 Class 區塊與內部的方法
for cls_name, methods in class_groups.items():
    # Graphviz 規定子圖名稱必須以 'cluster_' 開頭才會畫出外框
    with dot.subgraph(name=f'cluster_{cls_name}') as cluster:
        cluster.attr(label=f'class {cls_name}', style='dashed', color='gray', fontname='Consolas', fontsize='14')
        cluster.attr('node', style='filled', fillcolor='honeydew', shape='box') # 類別內的方法設定為淺綠色
        
        for method in methods:
            # 注意：節點的 ID 依然要用完整的 "Test.execute"，以確保連線正確
            cluster.node(method['name'], generate_label(method))

# 6. 繪製呼叫關係 (Edges)
# 收集所有我們自己定義的函式/方法 ID
all_internal_ids = [f['name'] for f in functions]

for func in functions:
    caller = func['name']
    for dependency in func.get('dependencies', []):
        # 如果是外部呼叫 (例如 print, test.execute)
        if dependency not in all_internal_ids:
            dot.node(dependency, f"{dependency}()", shape='ellipse', style='filled', fillcolor='lightgray')
            
        dot.edge(caller, dependency)

# 7. 輸出圖表
output_filename = "call_graph"
try:
    dot.render(output_filename, view=True)
    print(f"成功！圖表已生成：{output_filename}.png")
except Exception as e:
    print(f"繪圖失敗，錯誤訊息：{e}")