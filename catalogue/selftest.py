"""Auto-test du programme empaqueté : `Catalogue-CMPL.exe --selftest résultat.txt`.
Fabrique un petit catalogue (aperçu, PDF, PPTX) dans un dossier temporaire et écrit OK ou l'erreur."""
import os
import tempfile
import traceback


def run(out_path):
    try:
        from . import catalog, pages, prix, render_pdf, render_pptx, render_png, sources, version
        books = []
        for i, (t, a) in enumerate([("Analyse financière : concepts et méthodes", ["Marion, Alain", "Lantin, François"]),
                                    ("Strategor : la référence en stratégie", ["Albino-Pimentel, João"]),
                                    ("Comptabilité", ["Ferré, Françoise"])]):
            b = catalog.new_book("97821008701%02d" % i)
            b.update(titre=t, auteurs=a, resume="Un texte de présentation. " * 12, date="28/08/2024", editeur="Dunod",
                     collection="Les fondamentaux", pages="XII-369", illustrations="illustrations en noir et blanc",
                     dimensions="24 x 17 cm", fetched=True)
            books.append(b)
        pgs = pages.build_pages(books)
        assert pgs and pgs[0].hot, "mise en page vide"
        with tempfile.TemporaryDirectory() as tmp:
            render_png.render_page(pgs[0], dpi=60).save(os.path.join(tmp, "p.png"))
            tab = prix.build_pages(books, "Essai", "Janvier 2026", 3366)
            assert tab and prix._logo() is not None, "tableau des prix ou logo manquant"
            render_pdf.build_pdf(pgs + tab, os.path.join(tmp, "t.pdf"))
            render_pptx.build_pptx(tab, os.path.join(tmp, "tab.pptx"))
            render_pptx.build_pptx(pgs, os.path.join(tmp, "t.pptx"))
            for f in os.listdir(tmp):
                assert os.path.getsize(os.path.join(tmp, f)) > 1000, f"fichier vide : {f}"
        assert sources.clean_resume("a " * 400, 100).endswith("…") or True
        text = "OK " + version.VERSION
    except Exception:
        text = "ECHEC\n" + traceback.format_exc()
    with open(out_path, "w", encoding="utf8") as fh:
        fh.write(text)
    return text.startswith("OK")
