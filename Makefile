SHELL=/bin/bash

sample :
	cat data/ic16core_csen/ackroyd-londyn.cs-00.tag.xml | sed '27289,323760d' > data/sample.cs.xml
	cat data/ic16core_csen/ackroyd-londyn.en-00.tag.xml | sed '31667,371796d' > data/sample.en.xml
	cat data/ic16core_csen/ackroyd-londyn.cs-00.en-00.alignment.xml | sed '1157,13508d' > data/sample.cs-en.align.xml

convert-sample :
	cat data/sample.en.xml | python scripts/ic2teitok.py --salign-file data/sample.cs-en.align.xml --align-ord 0 | sed 's/ xmlns="[^"]*"//g' > teitok/sample-en.xml
	cat data/sample.cs.xml | python scripts/ic2teitok.py --salign-file data/sample.cs-en.align.xml --align-ord 1 | sed 's/ xmlns="[^"]*"//g' > teitok/sample-cs.xml

convert-sample-noalign :
	cat data/sample.en.xml | python scripts/ic2teitok.py | sed 's/xmlns="[^"]*"//g' > teitok/sample-noalign-en.xml
	cat data/sample.cs.xml | python scripts/ic2teitok.py | sed 's/xmlns="[^"]*"//g' > teitok/sample-noalign-cs.xml

word-align :
	mkdir -p walign/ic16core_csen
	python scripts/add_w_ids.py \
		< data/ic16core_csen/ackroyd-londyn.en-00.tag.xml \
		> walign/ic16core_csen/ackroyd-londyn.en-00.tag.with_wid.xml
	python scripts/add_w_ids.py \
		< data/ic16core_csen/ackroyd-londyn.cs-00.tag.xml \
		> walign/ic16core_csen/ackroyd-londyn.cs-00.tag.with_wid.xml
	python scripts/ic4aligner.py \
		data/ic16core_csen/ackroyd-londyn.cs-00.en-00.alignment.xml \
		walign/ic16core_csen/ackroyd-londyn.en-00.tag.with_wid.xml \
		walign/ic16core_csen/ackroyd-londyn.cs-00.tag.with_wid.xml \
		--output-ids walign/ic16core_csen/ackroyd-londyn.for_align_ids.txt \
		> walign/ic16core_csen/ackroyd-londyn.for_align.txt
	python scripts/compile_walign_xml.py \
			walign/ic16core_csen/ackroyd-londyn.for_align_ids.txt \
			walign/ic16core_csen/ackroyd-londyn.align-pcedt.txt \
		| xmllint --format - \
			> walign/ic16core_csen/ackroyd-londyn.cs-00.en-00.walign.xml
