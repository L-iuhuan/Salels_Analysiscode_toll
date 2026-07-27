"""Word: 所有表格首行设为跨页重复表头,只改格式不动内容"""
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

DOC_PATH = r"C:\Users\45091\Desktop\2026H1销售分析报告_分析+附件.docx"
doc = Document(DOC_PATH)

count = 0
for tbl in doc.tables:
    if len(tbl.rows) == 0:
        continue
    first_row = tbl.rows[0]
    trPr = first_row._tr.find(qn('w:trPr'))
    if trPr is None:
        trPr = OxmlElement('w:trPr')
        first_row._tr.insert(0, trPr)
    # Remove existing tblHeader if any
    for existing in trPr.findall(qn('w:tblHeader')):
        trPr.remove(existing)
    # Add tblHeader
    trPr.append(OxmlElement('w:tblHeader'))
    count += 1

doc.save(DOC_PATH)
print(f"DONE: {count}个表格已设置跨页重复表头")
