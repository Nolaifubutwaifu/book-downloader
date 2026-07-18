"""Extractor registry: the first adapter whose matches() accepts the URL wins.

The generic extractor matches everything, so it must stay last.
"""

from .archive_org import ArchiveOrgExtractor
from .digital_dante import DigitalDanteExtractor
from .generic import GenericExtractor
from .mit_classics import MitClassicsExtractor

EXTRACTORS = [
    DigitalDanteExtractor,
    MitClassicsExtractor,
    ArchiveOrgExtractor,
    GenericExtractor,
]


def pick_extractor(url):
    for cls in EXTRACTORS:
        if cls.matches(url):
            return cls()
    return GenericExtractor()
