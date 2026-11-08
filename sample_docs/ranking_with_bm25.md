# Ranking with BM25

BM25 is a ranking function used by search engines to estimate how relevant a document is to a query. It rewards documents that mention rare query terms many times, and it applies length normalization so that long documents do not win simply because they contain more words.

Two parameters control it: k1 sets how quickly repeated terms stop adding to the score, and b controls how strongly document length is penalized.
