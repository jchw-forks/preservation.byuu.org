import io
import os
import re
from glob import glob
from hashlib import sha256
from pathlib import Path
from typing import Optional


OUTPATH="public"

# BML implementation
class Node:
  def __init__(self, parent, name: str, data = None):
    self.parent = parent
    self.name = name
    self.data = data
    self.children = []

  def __repr__(self):
    if len(self.children):
      return f"Node(name={repr(self.name)}, data={repr(self.data)}, children={repr(self.children)})"
    else:
      return f"Node(name={repr(self.name)}, data={repr(self.data)})"

  def append(self, node: 'Node'):
    self.children.append(node)
    return node

  def path(self, key, *keys) -> Optional['Node']:
    for child in self.children:
      if child.name == key:
        if len(keys) == 0:
          return child
        else:
          return child.path(*keys)

  def elements(self, key) -> list:
    children = []
    for child in self.children:
      if child.name == key:
        children.append(child)
    return children

  def text(self) -> str:
    if self.data is not None:
      return str(self.data)
    return ""

def re_eat(pattern: str, text: str):
  match = re.match(pattern, text)
  if match:
    return text[len(match[0]):], match
  return text, None

def parse_bml(file) -> Node:
  r = n = Node(None, 'root')
  hang = False
  indents = []
  for line in file:
    if line.strip(" \t\r\n") == "":
      continue
    line = line.rstrip('\r\n')
    for indent in reversed(indents):
      if line.startswith(indent):
        line = line[len(indent):]
      else:
        if hang:
          hang = False
          n = n.parent
        n = n.parent
        indents.pop()
    # Indent
    part = line.lstrip(' \t')
    if len(part) != len(line):
      indents.append(line[:len(line)-len(part)])
    elif hang:
      n = n.parent
    hang = False
    # Block syntax
    if part.startswith(":"):
      if n.data is None:
        n.data = part[1:]
      else:
        n.data += "\n" + part[1:]
      continue
    # Node syntax
    part, match = re_eat(r'^([A-Za-z0-9-.]{1,})', part)
    if not match:
      raise SyntaxError("expected node name")
    n = n.append(Node(n, match[1]))
    hang = True
    # Direct value
    if part.startswith(":"):
      n.data = part[1:].strip(" \t")
      continue
    # Key-value pairs
    part = part.lstrip(" \t")
    while part != "":
      part, match = re_eat(r'^([A-Za-z0-9-.]{1,})=', part)
      if not match:
        raise SyntaxError("expected pair key")
      key = match[1]
      part, match = re_eat(r'^([^\s"]+)|^"([^"]*)"', part)
      if not match:
        raise SyntaxError("expected pair value")
      value = match[1]
      n.append(Node(n, key, value))
      part = part.lstrip(" \t")

  return r

# Base62 encoding
b62charset = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
def b62encode(n):
  s = ""
  while n > 0:
    s = b62charset[n % 62] + s
    n //= 62
  return s

def manifest_url_hash(name):
  return b62encode(int.from_bytes(sha256(name.encode('utf8')).digest(), "big"))[:4]

def game_url_hash(hexdigest):
  return b62encode(int.from_bytes(bytes.fromhex(hexdigest), "big"))[:8]

def html_page(body: str):
  return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Preservation — byuu.org</title>
</head>
<body>
  {}
</body>
</html>
""".format(body)

class Board:
  def __init__(self, parent, manifest: Node):
    self.name = manifest.text()
    self.hash = manifest_url_hash(self.name)
    self.manifest = manifest

  def url(self):
    return '{self.parent.url()}/{}'.format(self.hash)

class BoardList:
  def __init__(self, name, manifest: Node):
    self.name = name
    self.revision = manifest.path("database", "revision").text()
    self.hash = manifest_url_hash(name)
    self.boards = [Board(self, board) for board in manifest.elements('board')]
    self.manifest = manifest

  def html(self):
    html = '<section><header>{}<span>{}</span></header>'.format(self.name, self.revision)
    html += '<div>Total: {}</div>'.format(len(self.boards))
    html += '<table><thead><tr><th>Name</th><tbody>'
    for board in self.boards:
      html += '<tr>'
      html += '<td>{}</td>'.format(board.name)
      html += '</tr>'
    html += '</tbody></table></section>'
    return html

  def generate(self):
    Path(os.path.join(OUTPATH, "boards", self.hash)).mkdir(parents=True, exist_ok=True)
    Path(os.path.join(OUTPATH, "boards", self.hash, "index.html")).open("w").write(html_page(self.html()))

  def url(self):
    return f'/boards/{self.hash}'

class Game:
  def __init__(self, parent, manifest: Node):
    self.parent = parent
    self.name = manifest.path("name").text()
    self.region = manifest.path("region").text()
    self.revision = manifest.path("revision").text()
    self.board = manifest.path("board").text()
    self.hash = game_url_hash(manifest.path("sha256").text())
    self.manifest = manifest

  def rom_size(self):
    size = 0
    for component in self.manifest.path("board").elements("memory"):
      if component.path("type").text() == "ROM":
        size += int(component.path("size").text(), 16)
    return size

  def html(self):
    return 'TODO'

  def generate(self):
    Path(os.path.join(OUTPATH, "games", self.parent.hash, self.hash)).mkdir(parents=True, exist_ok=True)
    Path(os.path.join(OUTPATH, "games", self.parent.hash, self.hash, "index.html")).open("w").write(html_page(self.html()))

  def url(self):
    return f'{self.parent.url()}/{self.hash}'

class GameList:
  def __init__(self, name, manifest: Node):
    self.name = name
    self.revision = manifest.path("database", "revision").text()
    self.hash = manifest_url_hash(name)
    self.manifest = manifest
    self.games = [Game(self, game) for game in manifest.elements('game')]

  def html(self):
    html = '<section><header>{}<span>{}</span></header>'.format(self.name, self.revision)
    html += '<div>Total: {}</div>'.format(len(self.games))
    html += '<table><thead><tr><th>Name</th><th>Region</th><th>Revision</th><th>Board</th><th>Size</th></tr></thead><tbody>'
    for game in self.games:
      html += '<tr>'
      html += '<td><a href="{}" target="_blank">{}</a></td>'.format(game.url(), game.name)
      html += '<td><code>{}</code></td>'.format(game.region)
      html += '<td><code>{}</code></td>'.format(game.revision)
      html += '<td><code>{}</code></td>'.format(game.board)
      html += '<td><code>{}</code></td>'.format(hex(game.rom_size()))
      html += '</tr>'
    html += '</tbody></table></section>'
    return html

  def generate(self):
    for game in self.games:
      game.generate()

    Path(os.path.join(OUTPATH, "games", self.hash)).mkdir(parents=True, exist_ok=True)
    Path(os.path.join(OUTPATH, "games", self.hash, "index.html")).open("w").write(html_page(self.html()))

  def url(self):
    return f'/games/{self.hash}'

class Index:
  def __init__(self, categories: dict):
    self.categories = categories

  def html(self):
    html = ""
    for name, pages in sorted(self.categories.items()):
      html += '<section><header>{}</header><div>'.format(name)
      for page in pages:
        html += '<a href="{}" target="_blank">{}</a><br/>'.format(page.url(), page.name)
      html += '</div></section>'
    return html

  def generate(self):
    for pages in self.categories.values():
      for page in pages:
        page.generate()

    Path(OUTPATH).mkdir(parents=True, exist_ok=True)
    Path(os.path.join(OUTPATH, "index.html")).open("w").write(html_page(self.html()))

# Static site generation
categories = {}
for filename in glob("Manifests/**/*.bml", recursive=True):
  name, _ = os.path.splitext(os.path.basename(filename))
  path = os.path.split(filename)[0].split("/")
  category = " — ".join(path[1:])
  if path[1] == "Boards":
    page = BoardList(name, parse_bml(open(filename)))
  elif path[1] == "Games":
    page = GameList(name, parse_bml(open(filename)))
  else:
    raise Exception(f"unexpected path {path[0]}")
  categories.setdefault(category, []).append(page)

Index(categories).generate()
