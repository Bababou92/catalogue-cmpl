import sys, os, tempfile; sys.path.insert(0,'.'); sys.path.insert(0,'tests')
os.environ.setdefault("CMPL_CAT_DATA_DIR", tempfile.mkdtemp())
import fakenet
from catalogue import sources as S, catalog as C, store, pages, render_png
S.http_get=fakenet.http_get
st=store.load_settings(); cov=tempfile.mkdtemp(); books=[]
for isbn in ["9782200623296","9782200620035","9782200611545","9782100861514","9782100865420","9782100824243","9782100870165","9782100000000"]:
    b=C.new_book(isbn); raw=S.fetch_raw(isbn,"K"); C.apply_fetch(b,raw,st,cov); C.resolve_cover(b,raw,cov); books.append(b)
books[6]["collection"]="Les fondamentaux business"
pg=pages.build_pages(books)
print(len(pg),'pages')
os.makedirs('/tmp/claude-0/-home-claude/e73f0ac5-e6ef-5700-906f-be0dc71915d8/scratchpad/cat',exist_ok=True)
render_png.render_page(pg[0],dpi=110).save('/tmp/claude-0/-home-claude/e73f0ac5-e6ef-5700-906f-be0dc71915d8/scratchpad/cat/p1.png')
from catalogue import render_pdf, render_pptx
render_pdf.build_pdf(pg, '/tmp/claude-0/-home-claude/e73f0ac5-e6ef-5700-906f-be0dc71915d8/scratchpad/cat/demo.pdf', "Demo")
render_pptx.build_pptx(pg, '/tmp/claude-0/-home-claude/e73f0ac5-e6ef-5700-906f-be0dc71915d8/scratchpad/cat/demo.pptx', "Demo")
print("pdf+pptx ok")
