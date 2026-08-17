# Build the presentation decks.
#
#   make          all PDFs from the LaTeX sources
#   make pptx     all .pptx decks from the pptxgenjs generators
#
# Three decks: the simple 10-slide talk, the full 15-slide talk, and the code
# walkthrough. Each exists as both .pptx and .tex; use whichever your venue
# wants. The measured numbers in all of them come from `go run ./bench/dpsim`.

TEX := kubeedgeinfer-simple.tex kubeedgeinfer.tex kubeedgeinfer-code.tex
PDF := $(TEX:.tex=.pdf)

.PHONY: all pptx clean
all: $(PDF)

%.pdf: %.tex
	xelatex -interaction=nonstopmode $< >/dev/null
	xelatex -interaction=nonstopmode $< >/dev/null   # resolve outlines

pptx:
	node build_simple.js
	node build_main.js
	node build_code.js

clean:
	rm -f *.aux *.log *.nav *.out *.snm *.toc
