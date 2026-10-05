"""Tiny stdlib reader for artificial flat-table test fixtures only."""
from html.parser import HTMLParser


class FixtureReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.headers = []
        self.rows = []
        self.row = []
        self.cell = None
        self.head = False
    def handle_starttag(self, tag, attrs):
        if tag == 'thead': self.head = True
        if tag == 'tr': self.row = []
        if tag in ('th','td'): self.cell = {'text':'', 'links':[]}
        if tag == 'a' and self.cell is not None:
            href = dict(attrs).get('href')
            if href: self.cell['links'].append(href)
        if tag == 'br' and self.cell is not None: self.cell['text'] += '\n'
    def handle_data(self, data):
        if self.cell is not None: self.cell['text'] += data
    def handle_endtag(self, tag):
        if tag in ('th','td') and self.cell is not None:
            if self.head: self.headers.append(self.cell['text'].strip())
            else: self.row.append(self.cell)
            self.cell = None
        if tag == 'tr' and not self.head and self.row: self.rows.append(self.row)
        if tag == 'thead': self.head = False


def read_fixture(html):
    reader = FixtureReader()
    reader.feed(html)
    return {'headers': reader.headers, 'rows': reader.rows}
