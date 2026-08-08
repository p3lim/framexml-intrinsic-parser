let
  pkgs = import <nixpkgs> {};
in pkgs.mkShell {
  packages = [
    pkgs.python312
    pkgs.python312Packages.venvShellHook
  ];

  venvDir = "./.venv";
  postVenvCreation = ''
    pip install -r requirements.txt
  '';
}
