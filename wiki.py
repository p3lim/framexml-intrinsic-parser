import os
import sys
import difflib
import tempfile
import urllib
from pathlib import Path

import pywikibot
from pywikibot.comms import http
from pywikibot.xmlreader import XmlDump

SUMMARY = "Automated upload"
CATEGORIES = [
  "Intrinsic frames",
  "Intrinsic methods",
  "FrameXML types",
  "Structures",
]

# create family, as it's not supported in pywikibot
class Family(pywikibot.family.FandomFamily):
  name = "warcraft"
  domain = "warcraft.wiki.gg"
  codes = {"en"}

# track pages that won't be uploaded
changed = []

def upload(page, name: str, file: Path) -> None:
  # print(f"Processing {name}...", file=sys.stderr)
  with open(file) as f:
    content = f.read()
    content = content.rstrip('\r\n') # strip trailing newlines as the wiki does that too

    if page.exists() and hasattr(page, "_text") and page._text == content:
      # there are no changes, bail
      return

    # check if there were actually any changes
    diff = difflib.unified_diff(page.text.splitlines(keepends=True), content.splitlines(keepends=True))
    if len("".join(diff)) == 0:
      return

    # track changed pages
    changed.append(name)

    print(f"Uploading {name}...", file=sys.stderr)
    page.text = content
    page.save(summary=SUMMARY, watch="nochange", bot=True)

def login(user: str, bot: str, pw: str) -> pywikibot.Site:
  # configure user directly for the family
  pywikibot.config.usernames["warcraft"]["en"] = user

  # create a temporary password file for the bot password
  with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
    f.write(f"('{user}', BotPassword('{bot}', '{pw}'))")
    pywikibot.config.password_file = f.name

  # log in
  site = pywikibot.site.APISite("en", Family())
  site.login()
  # ^ this creates a session file in the current directory named "pywikibot.lmp",
  #   as well as an apicache directory and more junk like a file named "throttle.ctrl"

  return site

def main() -> None:
  username = os.getenv("WIKI_USERNAME") # Myuser

  site = login(
    # grab credentials from environment (i.e. secrets in GitHub workflows)
    # https://warcraft.wiki.gg/wiki/Special:ApplicationPasswords
    username,
    os.getenv("WIKI_BOTNAME"), # the part after Myuser@
    os.getenv("WIKI_BOTPASSWORD"), # the application password
  )

  print("Fetching category pages...", file=sys.stderr)
  pages = {}
  for category in CATEGORIES:
    cat = pywikibot.Category(site, category)
    for page in cat.members(member_type="page"):
      pages[page.title().replace(" ", "_")] = page

  print(f"Found {len(pages.keys())} pages to export, exporting...")
  res = http.request(
    site=site,
    uri="/wiki/Special:Export",
    method="POST",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={
      "title": "Special:Export",
      "catname": "",
      "pages": "\n".join(pages),
      "curonly": "1",
      "wpDownload": "1",
      "wpEditToken": site.tokens["csrf"]
    },
  )

  if res.status_code != 200:
    print(f"Error: failed to export pages (code {res.status_code})", file=sys.stderr)
    # TODO: improve error output
    sys.exit(1)

  print("Storing and parsing export...")
  blocked = {}
  with tempfile.NamedTemporaryFile(mode="w", suffix=".xml") as f:
    f.write(res.text)
    f.flush()

    dump = XmlDump(f.name, revisions="latest")
    for entry in dump.parse():
      title = urllib.parse.quote(entry.title.replace(" ", "_"))

      # ensure someone else didn't alter the page
      if entry.username != username and entry.username != "P3lim": # my user will do too
        blocked[title] = entry.username
        continue

      # inject data from dump
      page = pages.get(title)
      if page:
        page._text = entry.text

  # keep a set of the names of pages we process
  page_names = set()

  print("Processing pages...", file=sys.stderr)
  for file in Path("pages").rglob("*.txt"):
    # get the file name without the file extension suffix, and do replacements
    name = f"{file.relative_to(file.parts[0]).with_suffix('').as_posix()}"

    if name.startswith("API/"):
      # API pages are namespaced
      name = "API:" + name[4:]

    # track the page name
    page_names.add(name)

    # get (cached) page reference and call for an upload
    if name in pages:
      if name not in blocked:
        upload(pages[name], name, file)
    else:
      page = pywikibot.Page(site, name)
      upload(page, name, file)

  # delete temporary password file when done
  Path(pywikibot.config.password_file).unlink()

  if len(changed) > 0:
    print("The following pages were changed:", file=sys.stderr)
    for name in changed:
      print(f"- https://warcraft.wiki.gg/wiki/{name}", file=sys.stderr)

  # prune blocked sites that we don't process (since categories are vast)
  for name in list(blocked):
    if name not in page_names:
      del blocked[name]

  if blocked:
    # fail execution if there were any blocked pages, so we get alerted
    print("The following pages were modified by someone else, upload blocked:", file=sys.stderr)
    for page, user in blocked.items():
      print(f"- https://warcraft.wiki.gg/wiki/{page} last modified by '{user}'", file=sys.stderr)
    sys.exit(1)

  print("Done!")

if __name__ == "__main__":
  main()
