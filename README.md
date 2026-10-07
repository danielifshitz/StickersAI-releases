# StickersAI desktop releases

This public repository hosts official installers, verified updates and release tooling. Application source remains in the private StickersAI repository.

## Current release status

Version [0.4.2](https://github.com/danielifshitz/StickersAI-releases/releases/tag/v0.4.2) is the latest stable release for macOS Apple Silicon and Windows x64. Both native builds passed CI. [The protected publisher](https://github.com/danielifshitz/StickersAI-releases/actions/runs/37383701840) was approved, and signatures/package metadata were independently verified before publication. Real public-feed updates committed on the Mac and repaired Windows preview, preserving workspace and Codex configuration; bundled SAM/image/PDF checks passed on both. Clean-machine, OS-reboot and fully offline reopening acceptance remain outstanding. Version [0.4.1](https://github.com/danielifshitz/StickersAI-releases/releases/tag/v0.4.1) remains a validation prerelease.

**Clean Mac installation is currently blocked:** on 2026-10-07, a fresh macOS 26.6.2 Apple Silicon VM downloaded the public 0.4.2 DMG in Safari and copied the app into Applications, but macOS refused first launch as “damaged”. A matching public download confirmed an incomplete application code/resource signature. Update-manifest authentication still passed; it does not establish macOS bundle integrity. The source now applies a complete local integrity signature even without paid certificates, and verifies the actual DMG and ZIP contents. A corrected new release and clean first-launch acceptance are required. Published 0.4.2 artifacts and tags remain unchanged; do not remove quarantine or disable OS protections to work around this failure.

## Installation and updates

Download installers from [the latest stable release](https://github.com/danielifshitz/StickersAI-releases/releases/latest).

- **Mac:** open the DMG and copy StickersAI to a writable Applications folder.
- **Windows:** run StickersAI Setup. Installed binaries use `%LOCALAPPDATA%\StickersAIDesktop`; your persistent workspace uses `%LOCALAPPDATA%\StickersAI`.

Installers include the Python runtime and assisted-selection model. No developer tools, WSL or GPU are required. Local editing works offline; generation and update downloads require connectivity. macOS Intel is deferred.

Use **Connect to Codex** once in the app. Later updates download in the background; choose **Restart and update** when your work is saved. The updater backs up the workspace database and installation, validates the replacement before committing, and restores the previous version on a failed trial. Preserve the workspace and its `updates` folder if recovery reports a persistent lock or permission error.

The original Windows 0.4.0 preview requires one manual upgrade to 0.4.2 because of its updater handshake. Quit the app and run the new Setup when available; do not run a legacy preview uninstaller against the workspace directory. Mac previews earlier than 0.4.0 also require one manual upgrade.

Update manifests are authenticated with the app's embedded Ed25519 public key, and package hashes are verified before installation. These builds do not carry paid Apple notarization or Windows publisher certificates; OS security prompts may remain. Ed25519 update authentication does not grant OS publisher trust.

## Publisher operation

The protected `stickersai-updates` environment requires human approval before signing. The publisher accepts successful tagged two-target builds from the private source repository and creates a draft release. Review manifest signatures, artifact hashes and acceptance results before manual publication. Published versions and assets remain immutable; fixes use a new version. Never commit the private signing key or tokens. Key rotation requires a transition app release trusted by the existing key.
