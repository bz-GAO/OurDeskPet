# Runtime storage contract

- Resolve the installed project using the executable's `rinadesk-root.txt`; never use the working directory or a release build's source path.
- Chat's implicit default is `<Desk project>/Conversations`. A directory explicitly selected by the user remains unchanged. Existing files are not moved or deleted when changing the default.
- Yaki's implicit default is `<Yaki project>/output`. Native Yaki and Desk consume the same Yaki settings API. Persist an empty override for this default so relocation follows the installation.
- Generated conversation/output folders must be excluded from Git and source exports.
- The installed Desk uses the private data folder immediately above its anchored `bin` directory for encrypted billing authorization and local state. Do not let inherited `LOCALAPPDATA` redirect an installed copy. Development builds retain their user-data fallback.
- API configuration remains in the located project's `.env`; billing authorization is Windows-user DPAPI encrypted, outside source. These are separate stores, not a single project-local configuration folder.
- A successful isolated billing test is not proof of the installed UI. Verify the actual launcher, executable, data location, selected account and post-restart status. Never silently bind authorization to a different model API key.
