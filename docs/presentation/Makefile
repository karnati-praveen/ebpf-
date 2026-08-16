# Build the two presentation decks.
#
#   make          both PDFs from the LaTeX sources
#   make pptx     both .pptx decks from the pptxgenjs generators
#
# The .pptx and .tex decks carry the same content and palette; use whichever
# your venue wants. Slide-11 numbers in both come from `go run ./bench/dpsim`.

TEX := kubeedgeinfer.tex kubeedgeinfer-code.tex
PDF := $(TEX:.tex=.pdf)

.PHONY: all pptx clean
all: $(PDF)

%.pdf: %.tex
	xelatex -interaction=nonstopmode $< >/dev/null
	xelatex -interaction=nonstopmode $< >/dev/null   # resolve outlines

pptx:
	node build_main.js
	node build_code.js

clean:
	rm -f *.aux *.log *.nav *.out *.snm *.toc
