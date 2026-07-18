"""Book -> plain text."""


def book_to_txt(book):
    parts = [book.title]
    if book.author:
        parts.append(book.author)
    parts.append(f"Source: {book.source_url}")
    parts.append("")
    for chapter in book.chapters:
        parts.append("")
        parts.append(chapter.title.upper())
        parts.append("-" * min(len(chapter.title), 70))
        parts.append("")
        if chapter.verse:
            parts.extend(chapter.blocks)
        else:
            for block in chapter.blocks:
                parts.append(block)
                parts.append("")
    return "\n".join(parts) + "\n"
