from pathlib import Path
import pypdfium2 as pdfium,pdfplumber
p=Path('output/pdf/RF1-Registry-Training-Correction-Plan-Shelbi-2026-11-12.pdf');r=pdfium.PdfDocument(str(p));out=Path('tmp/pdfs/registry-correction-plan');out.mkdir(parents=True,exist_ok=True);print('Pages',len(r))
for i in range(len(r)):r[i].render(scale=1.2).to_pil().save(out/f'page-{i+1}.png')
with pdfplumber.open(p) as d:
 for i,page in enumerate(d.pages):print(i+1,(page.extract_text() or '')[:95],len(page.extract_text() or ''))
