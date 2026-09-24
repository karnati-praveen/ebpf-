# Build the presentation decks.
#
#   make          all PDFs from the LaTeX sources
#   make pptx     all .pptx decks from the pptxgenjs generators
#
# Four decks: the reference-template talk, the simple 10-slide talk, the full
# 15-slide talk, and the code walkthrough. Each exists as both .pptx and .tex.
# The measured numbers in all of them come from `go run ./bench/dpsim`.

TEX := kubeedgeinfer-classic.tex kubeedgeinfer-simple.tex \
       kubeedgeinfer.tex kubeedgeinfer-code.tex
PDF := $(TEX:.tex=.pdf)

.PHONY: all pptx clean
all: $(PDF)

# kubeedgeinfer-classic.tex needs only pdfLaTeX; the others use fontspec, so
# XeLaTeX is required. XeLaTeX builds all four, so use it throughout.
%.pdf: %.tex
	xelatex -interaction=nonstopmode $< >/dev/null
	xelatex -interaction=nonstopmode $< >/dev/null   # resolve page totals

pptx:
	node build_classic.js
	node build_simple.js
	node build_main.js
	node build_code.js

clean:
	rm -f *.aux *.log *.nav *.out *.snm *.toc
