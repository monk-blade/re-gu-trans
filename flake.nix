{
  description = "re-gu-trans: Gujarati roman-to-script transliteration for Rime";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forSystems = f: nixpkgs.lib.genAttrs systems f;

      ortAsset = system: {
        x86_64-linux = "onnxruntime-linux-x64-1.23.2";
        aarch64-linux = "onnxruntime-linux-aarch64-1.23.2";
      }.${system};
      ortHash = system: {
        x86_64-linux = "16sz3iaq400nl93dspvg2480qd8l0j0c4a0vv1f7svrgyapdr90z";
        aarch64-linux = "0p0y4h84h2gc699jnn6nf071izilzr7j1y6gqvxb2xpdc0swfqvw";
      }.${system};
    in
    {
      packages = forSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};

          librimeSrc = pkgs.fetchzip {
            url = "https://github.com/rime/librime/archive/refs/tags/1.16.1.tar.gz";
            sha256 = "1x8sa4y996kdvvkbk1aqa6jb7qhm19ir2n0b4wclsxvzzd53mfi5";
          };

          librimeQjsSrc = pkgs.fetchgit {
            url = "https://github.com/HuangJian/librime-qjs.git";
            rev = "7231b4ad0d1ee30f49f28c2943e1d8b59f9665d5"; # v1.3.0
            fetchSubmodules = true;
            sha256 = "0h9l3vjlbid83vxq6n6hm2s4ybdymk8bss9ngcia8dv3mv3jqbc2";
          };

          oriThemeSrc = pkgs.fetchgit {
            url = "https://github.com/Reverier-Xu/Ori-fcitx5.git";
            rev = "d2cf5df38f11e4e14dcf9436af5b9f8fa0087c55";
            sha256 = "104hj2a9vj3s1sv43pgfdqdq28fa5badpsr6c1j3b1k94k0bz8z3";
          };

          onnxruntimeDist = pkgs.fetchurl {
            url = "https://github.com/microsoft/onnxruntime/releases/download/v1.23.2/${ortAsset system}.tgz";
            sha256 = ortHash system;
          };
          onnxruntimeRoot = pkgs.runCommand "onnxruntime-extracted" { } ''
            mkdir -p $out
            tar xzf ${onnxruntimeDist} -C $out --strip-components=1
          '';

          # Repo checkout, minus large/irrelevant local dev state that would
          # otherwise bust the derivation's content hash on every unrelated
          # change (venvs, dist/ build output, external data caches).
          src = pkgs.lib.cleanSourceWith {
            src = ./.;
            filter = path: type:
              let base = baseNameOf path; in
              !(builtins.elem base [ ".venv" ".venv-indicxlit" ".venv-train-gpu" "dist" "node_modules" ]);
          };

          mkVariant = { modelArch, pname }:
            pkgs.stdenv.mkDerivation {
              inherit pname src;
              version = "4.0.0";

              nativeBuildInputs = with pkgs; [
                cmake ninja (python3.withPackages (ps: [ ps.marisa-trie ])) nodejs git curl unzip
                pkg-config
              ];
              buildInputs = with pkgs; [
                boost gflags glog leveldb marisa opencc yaml-cpp
              ];

              dontUseCmakeConfigure = true;

              buildPhase = ''
                runHook preBuild
                export HOME="$TMPDIR"
                export REQUIRE_BINARY_TRIES=1
                export MODEL_ARCH="${modelArch}"
                export TARGET_ARCH=${if system == "aarch64-linux" then "arm64" else "x64"}
                export LIBRIME_SRC_DIR="${librimeSrc}"
                export LIBRIME_QJS_SRC_DIR="${librimeQjsSrc}"
                export ONNXRUNTIME_ROOT="${onnxruntimeRoot}"
                # Cap parallelism: full -j$(nproc) on heavy boost-templated
                # librime translation units has triggered a transient GCC
                # internal-compiler-error under memory pressure in this
                # sandbox; a lower, steadier job count avoided it.
                export JOBS=8

                python3 scripts/build_qjs_tries.py --bin --exceptions

                chmod +x scripts/package/linux/*.sh scripts/package/*.sh scripts/*.py \
                  packaging/linux/*.sh
                patchShebangs scripts packaging
                ./scripts/package/linux/build_librime_qjs.sh

                mkdir -p dist/ori-fcitx5-theme
                cp -r "${oriThemeSrc}/OriDark" "${oriThemeSrc}/OriLight" dist/ori-fcitx5-theme/
                chmod -R u+w dist/ori-fcitx5-theme

                STAGE_ONLY=1 ./scripts/package/linux/build_packages.sh
                runHook postBuild
              '';

              installPhase = ''
                runHook preInstall
                mkdir -p $out
                cp -a dist/linux-root/. $out/
                runHook postInstall
              '';

              meta = with pkgs.lib; {
                description =
                  if modelArch == "ctc"
                  then "Gujarati Rime IME with the fast gu-transformer-ctc-v4 model (~2.3ms/query)"
                  else "Gujarati Rime IME with the IndicXlit model (~24ms/query, higher accuracy)";
                homepage = "https://github.com/monk-blade/re-gu-trans";
                license = licenses.mit;
                platforms = [ "x86_64-linux" "aarch64-linux" ];
              };
            };
        in
        {
          re-gu-trans-ctc = mkVariant { modelArch = "ctc"; pname = "re-gu-trans-ctc"; };
          re-gu-trans-xlit = mkVariant { modelArch = "indicxlit"; pname = "re-gu-trans-xlit"; };
          default = self.packages.${system}.re-gu-trans-xlit;
        });
    };
}
