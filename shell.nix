let
  pkgs = import <nixpkgs> {};

  scrape = pkgs.writeShellScriptBin "scrape" ''
    run(){
      # start with a blank slate
      rm -rf pages/*
      clear

      # scrape
      python3 main.py "$1"

      # show changes
      git status
    }

    export -f run

    # watch relevant files and loop
    ls main.py scraper/* templates/* | entr bash -c "run ''${1}"
  '';

  wiki = pkgs.writeShellScriptBin "wiki" ''
    run(){
      # ensure clean state
      rm -rf pywikibot.lwp apicache throttle.ctrl

      # source bot secrets
      source .env

      # run upload
      python3 wiki.py

      # clean up env and state
      unset $(sed 's/export //g' .env | cut -d= -f1)
      rm -rf pywikibot.lwp apicache throttle.ctrl
    }

    export -f run

    # watch relevant files and loop
    ls wiki.py | entr bash -c "run"
  '';
in pkgs.mkShell {
  packages = [
    pkgs.entr
    pkgs.python312
    pkgs.python312Packages.venvShellHook

    scrape
    wiki
  ];

  venvDir = "./.venv";
  postVenvCreation = ''
    pip install -r requirements.txt
  '';
}
