# The Inverted Index

An inverted index maps every word to the list of documents that contain it. Instead of scanning each document for a query, a search engine looks up the query terms and reads only the matching lists. This is why searching millions of pages can take milliseconds.

Positional indexes also remember where each word occurs, which makes exact phrase queries possible.
