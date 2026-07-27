# -*- coding: utf-8 -*-
"""阶段二:代码功能卡片提取(AST 静态分析,只读)。
输入: project_analysis/00_file_inventory.csv
输出: project_analysis/01_function_cards.json
     project_analysis/01_extraction_report.md (提取质量报告:语法错误/编码问题清单)
"""
import ast, csv, json, os, re, sys
from collections import defaultdict

ROOT = r"E:\3-其他资料\数据分析"
ANALYSIS_DIR = os.path.join(ROOT, "project_analysis")
INV_CSV = os.path.join(ANALYSIS_DIR, "00_file_inventory.csv")
OUT_JSON = os.path.join(ANALYSIS_DIR, "01_function_cards.json")
OUT_MD = os.path.join(ANALYSIS_DIR, "01_extraction_report.md")

READ_FUNCS = {  # pandas / 内置读取
    "read_csv", "read_excel", "read_json", "read_pickle", "read_parquet",
    "read_html", "read_sql", "read_table", "read_fwf", "load_workbook", "load",
}
WRITE_FUNCS = {"to_csv", "to_excel", "to_json", "to_pickle", "to_parquet", "to_html", "to_sql", "save", "dump", "savefig"}
SHUTIL_OPS = {"copy", "copy2", "copyfile", "move"}
KNOWN_LIBS = {"pandas", "numpy", "openpyxl", "matplotlib", "statsmodels", "sklearn",
              "rapidfuzz", "chinese_calendar", "calamine", "xlrd", "xlsxwriter",
              "seaborn", "plotly", "scipy", "pyarrow", "jupyter"}

ABS_PATH_RE = re.compile(r"([A-Za-z]:[\\/]|\\\\|/)")

def read_source(path):
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(), enc
        except (UnicodeDecodeError, UnicodeError):
            continue
        except OSError:
            return None, None
    return None, None

def const_str(node):
    """解析字符串常量;支持 'a' 'b' 拼接、f-string 静态部分、os.path.join(常量...)"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):  # f-string:取静态片段拼骨架
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            else:
                parts.append("{}")
        return "".join(parts)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr in ("join",) and node.args:
            parts = [const_str(a) for a in node.args]
            if all(p is not None for p in parts):
                return os.path.join(*parts)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str" and node.args:
        return const_str(node.args[0])
    return None

class CardExtractor(ast.NodeVisitor):
    def __init__(self, source, local_modules):
        self.source = source
        self.local_modules = local_modules
        self.var_map = {}           # 变量名 -> 字符串常量(一层解析)
        self.inputs, self.outputs = [], []
        self.imports_ext, self.imports_internal = set(), set()
        self.has_main_guard = False
        self.hardcoded = []
        self.argparse_params = []
        self.module_consts = []
        self.docstring = ""
        self.syntax_fallback = False

    # ---- 变量赋值跟踪 ----
    def visit_Assign(self, node):
        val = const_str(node.value)
        for t in node.targets:
            if isinstance(t, ast.Name):
                if val is not None:
                    self.var_map[t.id] = val
                # 模块级大写常量 -> 可配置参数候选
                if t.id.isupper() and val is not None and len(t.id) > 2:
                    self.module_consts.append(f"{t.id}={val[:60]}")
        self.generic_visit(node)

    def _resolve(self, node):
        v = const_str(node)
        if v is not None:
            return v
        if isinstance(node, ast.Name) and node.id in self.var_map:
            return self.var_map[node.id]
        return None

    def _func_name(self, func):
        if isinstance(func, ast.Attribute):
            return func.attr
        if isinstance(func, ast.Name):
            return func.id
        return ""

    def visit_Call(self, node):
        name = self._func_name(node.func)
        if name in READ_FUNCS and node.args:
            v = self._resolve(node.args[0])
            if v and not v.startswith(("http", "SELECT", "select")):
                self.inputs.append(v)
        elif name in WRITE_FUNCS and node.args:
            v = self._resolve(node.args[0])
            if v:
                self.outputs.append(v)
        elif name == "open" and node.args:
            v = self._resolve(node.args[0])
            mode = const_str(node.args[1]) if len(node.args) > 1 else "r"
            if v:
                (self.outputs if any(m in (mode or "r") for m in "wax+") else self.inputs).append(v)
        elif name in SHUTIL_OPS and isinstance(node.func, ast.Attribute) and \
             isinstance(node.func.value, ast.Name) and node.func.value.id == "shutil":
            src = self._resolve(node.args[0]) if node.args else None
            dst = self._resolve(node.args[1]) if len(node.args) > 1 else None
            if src: self.inputs.append(src)
            if dst: self.outputs.append(dst)
        elif name == "add_argument" and node.args:
            v = const_str(node.args[0])
            if v: self.argparse_params.append(v)
        self.generic_visit(node)

    def visit_Import(self, node):
        for a in node.names:
            top = a.name.split(".")[0]
            (self.imports_internal if top in self.local_modules else self.imports_ext).add(a.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.level and node.level > 0:
            self.imports_internal.add("(relative)." + (node.module or ""))
        elif node.module:
            top = node.module.split(".")[0]
            (self.imports_internal if top in self.local_modules else self.imports_ext).add(node.module)
        self.generic_visit(node)

    def visit_If(self, node):
        # if __name__ == '__main__'
        try:
            if isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name) \
               and node.test.left.id == "__name__":
                self.has_main_guard = True
        except Exception:
            pass
        self.generic_visit(node)

def regex_fallback(source):
    """语法错误时的正则兜底提取"""
    inputs = re.findall(r"""(?:read_csv|read_excel|read_json|read_pickle|load_workbook)\s*\(\s*[rf]?['"]([^'"]+)['"]""", source)
    outputs = re.findall(r"""(?:to_csv|to_excel|to_json|to_pickle|savefig)\s*\(\s*[rf]?['"]([^'"]+)['"]""", source)
    imports = re.findall(r"^\s*(?:import|from)\s+([A-Za-z_][\w.]*)", source, re.M)
    return inputs, outputs, imports, "__main__" in source and "if __name__" in source

def build_card(rel_path, local_modules):
    abs_path = os.path.join(ROOT, rel_path)
    source, enc = read_source(abs_path)
    card = {
        "file": rel_path.replace(os.sep, "/"),
        "summary": "",
        "inputs": [], "outputs": [],
        "key_libraries": [],
        "internal_imports": [],
        "configurable_params": [],
        "has_main_guard": False,
        "quality_notes": "",
    }
    if source is None:
        card["quality_notes"] = "无法读取文件(编码或IO错误)"
        return card, {"status": "unreadable"}
    lines = source.splitlines()
    card["loc"] = len(lines)
    notes = []
    tree = None
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        notes.append(f"语法错误(ast 解析失败,已用正则兜底): L{e.lineno}")
    if enc != "utf-8" and enc != "utf-8-sig":
        notes.append(f"非UTF-8编码({enc})")

    if tree is not None:
        ex = CardExtractor(source, local_modules)
        ex.visit(tree)
        card["inputs"] = sorted(set(i for i in ex.inputs if i.strip()))
        card["outputs"] = sorted(set(o for o in ex.outputs if o.strip()))
        card["internal_imports"] = sorted(ex.imports_internal)
        card["has_main_guard"] = ex.has_main_guard
        card["configurable_params"] = (ex.argparse_params + ex.module_consts)[:15]
        doc = ast.get_docstring(tree) or ""
        card["docstring"] = doc.strip()[:300]
        libs = {i.split(".")[0] for i in ex.imports_ext}
        card["key_libraries"] = sorted(libs & KNOWN_LIBS | (libs & {"pandas", "numpy"}))
        card["all_ext_imports_top"] = sorted(libs)[:20]
        hc = [s for s in card["inputs"] + card["outputs"] if ABS_PATH_RE.match(s)]
        if hc:
            notes.append(f"硬编码绝对路径x{len(hc)}(如 {hc[0][:50]})")
        if not ex.has_main_guard:
            notes.append("无 __main__ 保护(可能被import即执行)")
        if "try" not in source:
            notes.append("无异常处理")
    else:
        inputs, outputs, imports, mg = regex_fallback(source)
        card["inputs"] = sorted(set(inputs))
        card["outputs"] = sorted(set(outputs))
        card["has_main_guard"] = mg
        libs = {i.split(".")[0] for i in imports}
        card["key_libraries"] = sorted(libs & KNOWN_LIBS)
        card["all_ext_imports_top"] = sorted(libs)[:20]
        card["docstring"] = ""
    # 头部注释(前5行的 # 注释)作为摘要线索
    head_comments = []
    for ln in lines[:8]:
        s = ln.strip()
        if s.startswith("#") and not s.startswith("#!"):
            head_comments.append(s.lstrip("#").strip())
    card["head_comment"] = " ".join(head_comments)[:200]
    card["quality_notes"] = "; ".join(notes)
    status = "ok" if tree is not None else "syntax_error"
    return card, {"status": status}

def main():
    with open(INV_CSV, "r", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["extension"] == ".py"]
    # 项目内模块集合:所有 .py 的去后缀文件名 + 一级/二级目录名
    local_modules = set()
    for r in rows:
        stem = os.path.splitext(os.path.basename(r["file_path"]))[0]
        local_modules.add(stem)
        parts = r["file_path"].split(os.sep)
        for p in parts[1:-1]:
            if p.isidentifier():
                local_modules.add(p)
    cards, stats = [], {"ok": 0, "syntax_error": 0, "unreadable": 0}
    err_files = []
    for r in rows:
        card, st = build_card(r["file_path"], local_modules)
        card["sha1"] = r["sha1"]
        card["size_kb"] = float(r["size_kb"])
        card["last_modified"] = r["last_modified"]
        cards.append(card)
        stats[st["status"]] = stats.get(st["status"], 0) + 1
        if st["status"] != "ok":
            err_files.append((r["file_path"], st["status"], card["quality_notes"]))
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)
    md = ["# 01 功能卡片提取质量报告\n",
          f"- 处理 .py 文件: {len(cards)}",
          f"- AST 解析成功: {stats.get('ok',0)}",
          f"- 语法错误(正则兜底): {stats.get('syntax_error',0)}",
          f"- 无法读取: {stats.get('unreadable',0)}\n",
          "## 问题文件清单\n", "| 文件 | 状态 | 备注 |\n|---|---|---|"]
    for fp, st, note in err_files:
        md.append(f"| {fp} | {st} | {note[:80]} |")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(json.dumps({"cards": len(cards), **stats}, ensure_ascii=False))

if __name__ == "__main__":
    main()
