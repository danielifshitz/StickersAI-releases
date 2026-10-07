# StickersAI desktop releases

This public repository hosts official installers, verified updates and release tooling. Application source remains in the private StickersAI repository.

## Current release status

Version [0.4.1](https://github.com/danielifshitz/StickersAI-releases/releases/tag/v0.4.1) is a validation prerelease. The corrected 0.4.2 Mac Apple Silicon and Windows x64 builds passed native CI. [Its protected publisher](https://github.com/danielifshitz/StickersAI-releases/actions/runs/37383701840) was approved and completed successfully on 2026-10-07; the manifest signature and uploaded package digests were independently verified. Version 0.4.2 remains a draft because GitHub returns server errors during publication. Native CI does not establish clean-machine or real public-feed update acceptance.

## Installation and updates

Once a stable release is published, download its installer from [Releases](https://github.com/danielifshitz/StickersAI-releases/releases).

- **Mac:** open the DMG and copy StickersAI to a writable Applications folder.
- **Windows:** run StickersAI Setup. Installed binaries use `%LOCALAPPDATA%\StickersAIDesktop`; your persistent workspace uses `%LOCALAPPDATA%\StickersAI`.

Installers include the Python runtime and assisted-selection model. No developer tools, WSL or GPU are required. Local editing works offline; generation and update downloads require connectivity. macOS Intel is deferred.

Use **Connect to Codex** once in the app. Later updates download in the background; choose **Restart and update** when your work is saved. The updater backs up the workspace database and installation, validates the replacement before committing, and restores the previous version on a failed trial. Preserve the workspace and its `updates` folder if recovery reports a persistent lock or permission error.

The original Windows 0.4.0 preview requires one manual upgrade to 0.4.2 because of its updater handshake. Quit the app and run the new Setup when available; do not run a legacy preview uninstaller against the workspace directory. Mac previews earlier than 0.4.0 also require one manual upgrade.

Update manifests are authenticated with the app's embedded Ed25519 public key, and package hashes are verified before installation. These builds do not carry paid Apple notarization or Windows publisher certificates; OS security prompts may remain. Ed25519 update authentication does not grant OS publisher trust.

## Publisher operation

The protected `stickersai-updates` environment requires human approval before signing. The publisher accepts successful tagged two-target builds from the private source repository and creates a draft release. Review manifest signatures, artifact hashes and acceptance results before manual publication. Published versions and assets remain immutable; fixes use a new version. Never commit the private signing key or tokens. Key rotation requires a transition app release trusted by the existing key.
