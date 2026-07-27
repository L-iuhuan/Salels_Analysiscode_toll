"""Word: 所有表格单元格垂直居中"""
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

DOC_PATH = r"C:\Users\45091\Desktop\2026H1销售分析报告_分析+附件.docx"
doc = Document(DOC_PATH)

count = 0
for tbl in doc.tables:
    for row in tbl.rows:
        for cell in row.cells:
            tcPr = cell._tc.find(qn('w:tcPr'))
            if tcPr is None:
                tcPr = OxmlElement('w:tcPr')
                cell._tc.insert(0, tcPr)
            # Remove existing vAlign
            for old in tcPr.findall(qn('w:vAlign')):
                tcPr.remove(old)
            # Add center
            va = OxmlElement('w:vAlign')
            va.set(qn('w:val'), 'center')
            tcPr.append(va)
            count += 1

doc.save(DOC_PATH)
print(f"DONE: {count}个单元格已设置垂直居中")
