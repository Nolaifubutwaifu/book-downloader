"""The neutral data model every extractor produces and every exporter consumes."""

from dataclasses import dataclass, field


@dataclass
class Chapter:
    title: str
    blocks: list = field(default_factory=list)  # paragraphs (prose) or lines (verse)
    verse: bool = False

    def word_count(self):
        return sum(len(b.split()) for b in self.blocks)


@dataclass
class Book:
    title: str
    author: str = ""
    source_url: str = ""
    chapters: list = field(default_factory=list)

    def word_count(self):
        return sum(c.word_count() for c in self.chapters)

    def summary(self):
        return {
            "title": self.title,
            "author": self.author,
            "source_url": self.source_url,
            "chapters": [c.title for c in self.chapters],
            "chapter_count": len(self.chapters),
            "word_count": self.word_count(),
        }
