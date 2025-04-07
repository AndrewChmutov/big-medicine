{
  description = "A very basic flake";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
  };

  outputs = { self, nixpkgs }:
  let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};
  in {
    devShells.${system}.default = (pkgs.buildFHSEnv {
      name = "python-fhs";
      targetPkgs = pkgs: with pkgs; [
        glibc
        texlive.combined.scheme-full
        zlib
        zsh
      ];
      runScript = "zsh";
    }).env;
  };
}
