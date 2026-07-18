"""Extractor interface.

An extractor turns a pasted URL into a Book. Implement three things:

- name: human-readable adapter name shown in the UI
- matches(url): class/staticmethod - does this URL belong to this adapter?
- scrape(url, fetcher, progress): fetch + parse into a core.book.Book.
  Call progress(message, done, total) as you go so the UI can show a bar.
"""


class Extractor:
    name = "base"

    @staticmethod
    def matches(url):
        raise NotImplementedError

    def scrape(self, url, fetcher, progress):
        raise NotImplementedError
