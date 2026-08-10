import os
import sys
import tempfile
from pathlib import Path

import pywikibot

SUMMARY = "Automated upload"

# create family, as it's not supported in pywikibot
class Family(pywikibot.family.FandomFamily):
  name = "warcraft"
  domain = "warcraft.wiki.gg"
  codes = {"en"}

# track pages that won't be uploaded
blocked = {}
changed = []

def upload(page, name: str, file: Path, username: str) -> None:
  with open(file) as f:
    content = f.read()
    content = content.rstrip('\r\n') # strip trailing newlines as the wiki does that too

    if content == page.text:
      # there are no changes, bail
      return

    # we could show the diff if we wanted to :)
    # diff = difflib.unified_diff(page.text.splitlines(keepends=True), content.splitlines(keepends=True))
    # print("".join(diff))

    if page.exists():
      # ensure someone else didn't alter the page first
      last = None
      for rev in page.revisions(total=1): # we have to iterate, ugh
        if not (rev.user == username or rev.user == "P3lim"): # edits by my main account is fine too
          # store the name of the last editor and bail
          blocked[name] = rev.user
          return

    # track changed pages
    changed.append(name)

    print(f"Uploading '{name}'...")
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

  print("Processing pages...", file=sys.stderr)
  for file in Path("pages").rglob("*.txt"):
    # get the name without the file extension suffix, and do replacements
    path = file.with_suffix("")
    name = path.name.replace(":", "/")

    # get the page reference and call for an upload
    page = pywikibot.Page(site, name)
    upload(page, name, file, username)

  # delete temporary password file when done
  Path(pywikibot.config.password_file).unlink()

  if len(changed) > 0:
    print("The following pages were changed:", file=sys.stderr)
    for name in changed:
      print(f"- https://warcraft.wiki.gg/wiki/{name}", file=sys.stderr)

  if blocked:
    # fail execution if there were any blocked pages, so we get alerted
    print("The following pages were modified by someone else, upload blocked:", file=sys.stderr)
    for page, user in blocked.items():
      print(f"- https://warcraft.wiki.gg/wiki/{page} last modified by '{user}'", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
  main()
